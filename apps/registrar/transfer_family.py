"""Ana qrup ↔ alt qrup: ana qrupun jurnalı TƏK jurnal qalır (sahib 2026-11-07/08).

Sahib: «ana qrup alt qrupların cəmidir»; ana jurnal 0 göstərirsə, alt qruplarda isə tələbə varsa — bu, xətadır.
Mühazirə bir dəfə ana jurnalda yazılır, alt qruplar həmin jurnalın İÇİNDƏ seminar alt qrupudur
(:class:`~apps.registrar.models.SeminarGroup`, ``Enrollment.seminar_group``). Ailə yalnız reyestr bölgüsünün
izi ilə tanınır (``OrgUnit.settings["parent_group"]``) — ad oxşarlığı burada SAYILMIR.

Forma: alt qrupun (A1) tələbəsinin bu fənn üzrə aktiv sətri ANA qrupun (A) aktiv açılışındadır, provenans
``source_group`` = A1. Alt qrupun öz açılışı ya yoxdur, ya da passivdir (bölmənin boş varisi / birləşdirilmiş jurnal).

Rəsmi köçürmə xidməti (:func:`apps.registrar.transfer.transfer_student_group`) bu köməkçiləri çağırır:

* :func:`redirect_target` — varis alt qrupun açılışına düşməli idisə, amma ana jurnal TƏK jurnaldırsa (A1-in açılışı
  passivdir; və ya bölmədə A1-in canlı jurnalı yoxdur) ana qrupun aktiv açılışı. DB qapısı (0045,
  ``registrar_finalize_student_group_transfer``) köçürmənin özündə varisin YENİ qrupun açılışında aktiv olmasını
  tələb edir — ona görə köçürmə adi qaydada yekunlaşır, SONRA eyni tranzaksiyada :func:`return_to_parent`: ana
  qrupdakı sətir yaradılır / yenidən ``enrolled`` olur (qeydləri yerində; boş provenansa alt qrup yazılır — 0056
  trigger-i bir dəfə yazmağa icazə verir), varis ``dropped`` + ``superseded_by`` = ana sətir, bu köçürmədə yaranmış
  boş alt qrup açılışı passivləşir (``is_active=False``), tələbə alt qrupunun seminar sırasına düşür;
* :func:`carry_rows` — ailədən KƏNAR qrupa köçəndə (A1 → B) tələbənin ana jurnaldakı sətirləri də köçürülür
  (yoxsa A1-in açılışında sətri olmadığından köçürmə «0 sətir» ilə keçər, tələbə A-nın jurnalında qalardı);
* :func:`sync_seminar_groups` — ailə daxilində (qardaş alt qrup, ana qrupa qayıdış) seminar yerinin yenilənməsi;
* :func:`is_chain_undo` — A → A1 → A2 → A kimi zəncirin geri qaytarılması.

Silmə yoxdur; bütün iz audit sətirlərindədir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.registrar.models import CourseOffering, Enrollment, Lesson, SeminarGroup
from apps.registrar.models.lab_group import LAB_GROUP_MAX_NUMBER, LAB_GROUP_NAME_MAX_LENGTH
from core import audit as audit_service
from core.constants import AuditAction

#: Zəncir yoxlamasında ən çox addım (dövr və ya çox uzun zəncir — yoxlama tələb olunur).
CHAIN_LIMIT = 20
RESOURCE = "registrar.subgroup_parent_journal"
REASON = "Sahib 2026-11-08: ana qrup alt qrupların cəmidir — ana jurnal tək jurnal qalır (seminar alt qrupu)"


def trail_parent_id(group) -> str:
    """Reyestr bölgüsünün izi: alt qrupun ana qrupunun id-si (yoxdursa boş sətir)."""
    raw = group.settings if isinstance(getattr(group, "settings", None), dict) else {}
    return str(raw.get("parent_group") or "")


def family_parent_id(old_group, new_group) -> str:
    """Köçürmə bir ailə daxilindədirsə ana qrupun id-si: bölmə, geri qayıdış və ya qardaş alt qruplar arası."""
    if old_group is None or new_group is None:
        return ""
    old_trail, new_trail = trail_parent_id(old_group), trail_parent_id(new_group)
    if new_trail == str(old_group.pk):
        return new_trail
    if old_trail == str(new_group.pk):
        return old_trail
    if old_trail and old_trail == new_trail:
        return old_trail
    return ""


def is_live(offering) -> bool:
    """Alt qrupun öz jurnalı «canlıdır»: aktivdir və siyahısında tələbə və ya dərsi var."""
    if offering is None or not offering.is_active:
        return False
    return (
        Enrollment.objects.filter(offering=offering, status=Enrollment.Status.ENROLLED).exists()
        or Lesson.objects.filter(offering=offering).exists()
    )


def parent_offering(*, organization, group, subject_id, period):
    """Alt qrupun ana qrupunun bu fənn üzrə AKTİV açılışı (yoxdursa ``None``)."""
    parent_id = trail_parent_id(group)
    if not parent_id or period is None:
        return None
    return CourseOffering.objects.filter(
        organization=organization, subject_id=subject_id, period=period, group_id=parent_id, is_active=True
    ).first()


def parent_journal_for(*, organization, group, subject_id, period):
    """Alt qrupun tələbəsi bu fənn üzrə ANA jurnala yazılmalıdırsa onun açılışı: alt qrupun öz aktiv açılışı yoxdur
    (yoxdur və ya passivdir), ana qrupun isə aktiv açılışı var. Mandat / seçmə qeydiyyatı üçün."""
    own = CourseOffering.objects.filter(
        organization=organization, subject_id=subject_id, period=period, group=group, is_active=True
    ).exists()
    return (
        None if own else parent_offering(organization=organization, group=group, subject_id=subject_id, period=period)
    )


@transaction.atomic
def enroll_in_parent_journal(offering, student, group, kind):
    """Ana jurnala «alt qrupdan» sətir (idempotent) + alt qrupun seminar sırası. Tarixçə sətri bərpa olunmur."""
    enrollment, created = Enrollment.objects.get_or_create(
        organization_id=offering.organization_id,
        student=student,
        offering=offering,
        defaults={"kind": kind, "source_group": group},
    )
    if created:
        number = seminar_number(offering, group, create=True)
        if number is not None:
            enrollment.seminar_group = number
            enrollment.save(update_fields=["seminar_group", "updated_at"])
    return enrollment, created


def redirect_target(*, record, new_group, subject_id, period, target, keep_parent):
    """Köçürmənin varisi ana jurnala qaytarılmalıdırsa ana qrupun aktiv açılışı, əks halda ``None``.

    * alt qrupun bu fənn üzrə açılışı PASSİVDİR (bölmənin varisi / ana jurnala birləşdirilib) — hər köçürmədə;
    * alt qrupun açılışı YOXDUR, ana jurnal isə artıq alt qrup formasındadır (ailənin seminar alt qrupu var) — hər
      köçürmədə; ailə hələ bölünməyibsə (təzə alt qrup) adi köçürmə köhnə qayda ilə gedir (sahibin açıq qərarı);
    * bölmə (``keep_parent``): alt qrupun canlı jurnalı yoxdur. Canlı (aktiv + doldurulmuş) köhnə formalı jurnal
      varsa bölmə dayanır — iki jurnal yaranmasın (əvvəlcə alt qrup jurnalı ana jurnala birləşdirilməlidir).
    """
    parent = parent_offering(organization=record.organization, group=new_group, subject_id=subject_id, period=period)
    if parent is None:
        return None
    if target is not None and not target.is_active:
        return parent
    if target is None and (keep_parent or is_family_journal(parent)):
        return parent
    if not keep_parent:
        return None
    if is_live(target):
        raise ValidationError(
            f"«{new_group.name}» alt qrupunun «{target.subject.name}» fənni üzrə ayrıca aktiv jurnalı var. "
            "İki jurnal yaranmasın deyə bölmə dayandırıldı: əvvəlcə alt qrup jurnalı ana qrupun jurnalı ilə "
            "birləşdirilməlidir (RİM — alt qrup jurnallarının birləşdirilməsi)."
        )
    return parent


def is_family_journal(offering) -> bool:
    """Ana jurnal alt qrup formasındadırmı: reyestr alt qrupuna bağlı seminar alt qrupu var (bölmə / birləşdirmə)."""
    return SeminarGroup.objects.filter(offering=offering, unit__isnull=False).exists()


def carry_rows(*, record, old_group, new_group, period) -> list:
    """Ailədən KƏNAR qrupa köçəndə (A1 → B) tələbənin ana qrupun (A) jurnallarındakı aktiv sətirləri."""
    parent_id = trail_parent_id(old_group)
    if not parent_id or period is None or family_parent_id(old_group, new_group) or str(new_group.pk) == parent_id:
        return []
    return list(
        Enrollment.objects.select_for_update(of=("self",))
        .filter(
            organization=record.organization,
            student=record.student,
            offering__period=period,
            offering__group_id=parent_id,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering__subject", "offering__instructor")
    )


def _save(enrollment, fields) -> None:
    enrollment.full_clean(validate_unique=False, validate_constraints=False)
    enrollment.save(update_fields=[*fields, "updated_at"])


def _parent_row(successor, offering, *, subgroup, by_user):
    """Tələbənin ana jurnaldakı sətri: yoxdursa yaradılır, tarixçədədirsə bərpa olunur."""
    row = (
        Enrollment.objects.select_for_update(of=("self",))
        .filter(organization_id=successor.organization_id, student_id=successor.student_id, offering=offering)
        .first()
    )
    if row is None:
        return Enrollment.objects.create(
            organization_id=successor.organization_id,
            student_id=successor.student_id,
            offering=offering,
            kind=successor.kind,
            status=Enrollment.Status.ENROLLED,
            source_group=subgroup,
            added_by=by_user,
            added_at=timezone.now(),
        )
    if row.status == Enrollment.Status.DROPPED:
        # Yalnız köçürmə zəncirinin sübut etdiyi sətir bərpa olunur (bölmə: ana sətir → varis; geri dönüş: ana sətir
        # → B → varis). Əl ilə çıxarılmış / jurnal təmizliyi qərarı ilə düşmüş sətir səssiz bərpa OLUNMUR.
        if not is_chain_undo(row, successor):
            raise ValidationError(
                "Yeni qrupun açılışında bu tələbəyə aid tarixi qeydiyyat var; "
                "tarixçəni yenidən aktivləşdirmədən əvvəl inzibati yoxlama tələb olunur."
            )
        # Sıra vacibdir: ``superseded_by`` əvvəl boşalır ki, zəncirdə dövr yaranmasın.
        row.status, row.superseded_by = Enrollment.Status.ENROLLED, None
        fields = ["status", "superseded_by"]
        if row.source_group_id is None:
            row.source_group = subgroup
            fields.append("source_group")
        _save(row, fields)
    elif row.status != Enrollment.Status.ENROLLED:
        raise ValidationError(
            "Tələbənin ana qrupun jurnalındakı sətri dondurulub və ya bağlanıb — ana jurnala qaytarmaq üçün "
            "inzibati yoxlama tələb olunur."
        )
    return row


def return_to_parent(redirects, *, subgroup, by_user) -> dict:
    """``redirects`` = ``[(varis, ana açılış, açılış bu köçürmədə yarandı)]`` (bax modul şərhi)."""
    restored, placed, fresh = [], [], {}
    for successor, offering, offering_is_new in redirects:
        row = _parent_row(successor, offering, subgroup=subgroup, by_user=by_user)
        successor.status, successor.superseded_by = Enrollment.Status.DROPPED, row
        _save(successor, ["status", "superseded_by"])
        restored.append(row.pk)
        if row.seminar_group is None or _is_registry_seminar(offering, row.seminar_group):
            # Boş və ya başqa reyestr alt qrupunun (köhnə) sırası → yeni alt qrupun sırası; əl ilə qoyulan qalır.
            number = seminar_number(offering, subgroup, create=True)
            if number is not None and number != row.seminar_group:
                row.seminar_group = number
                row.save(update_fields=["seminar_group", "updated_at"])
                placed.append(row.pk)
        if offering_is_new:
            fresh[successor.offering_id] = successor.offering
    retired = []
    for offering in fresh.values():
        offering.refresh_from_db(fields=["is_active"])
        if offering.is_active and not is_live(offering):
            offering.is_active = False
            offering.save(update_fields=["is_active", "updated_at"])
            retired.append(offering.pk)
    return {
        "kept_in_parent_enrollment_ids": restored,
        "seminar_placed_enrollment_ids": placed,
        "retired_offering_ids": retired,
    }


def _is_registry_seminar(offering, number) -> bool:
    """Bu nömrə reyestr alt qrupuna bağlı seminar alt qrupudurmu (əl ilə yaradılmış deyil)."""
    return SeminarGroup.objects.filter(offering=offering, number=number, unit__isnull=False).exists()


def _used_numbers(offering, rows) -> set:
    """Jurnalda tutulmuş seminar nömrələri: ``SeminarGroup`` ∪ siyahı ∪ dərslər (toqquşma olmasın)."""
    used = {row.number for row in rows}
    used.update(
        Enrollment.objects.filter(offering=offering, seminar_group__isnull=False).values_list(
            "seminar_group", flat=True
        )
    )
    used.update(
        Lesson.objects.filter(offering=offering, seminar_group__isnull=False).values_list("seminar_group", flat=True)
    )
    return used


def seminar_number(offering, unit, *, create: bool):
    """Alt qrupun bu jurnaldakı seminar nömrəsi; ``create`` olduqda yoxdursa ilk boş nömrə ilə yaradılır."""
    rows = list(SeminarGroup.objects.select_for_update().filter(offering=offering))
    for row in rows:
        if row.unit_id == unit.pk:
            return row.number
    if not create:
        return None
    used = _used_numbers(offering, rows)
    free = [number for number in range(1, LAB_GROUP_MAX_NUMBER + 1) if number not in used]
    if not free:
        return None
    row = SeminarGroup.objects.create(
        organization_id=offering.organization_id,
        offering=offering,
        number=free[0],
        name=unit.name[:LAB_GROUP_NAME_MAX_LENGTH],
        unit=unit,
    )
    return row.number


def sync_seminar_groups(*, record, old_group, new_group, period) -> dict:
    """Ailə daxilində köçürmədən sonra ana jurnaldakı seminar yeri (bax modul şərhi). Audit üçün id-lər."""
    parent_id = family_parent_id(old_group, new_group)
    if not parent_id or period is None:
        return {}
    entering = str(new_group.pk) != parent_id
    leaving = str(old_group.pk) != parent_id
    rows = (
        Enrollment.objects.select_for_update(of=("self",))
        .filter(
            organization=record.organization,
            student=record.student,
            offering__period=period,
            offering__group_id=parent_id,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering")
    )
    placed, cleared = [], []
    for row in rows:
        old_number = seminar_number(row.offering, old_group, create=False) if leaving else None
        if row.seminar_group is not None and row.seminar_group != old_number:
            continue  # əl ilə başqa seminar sırasına qoyulub — toxunulmur
        target = seminar_number(row.offering, new_group, create=True) if entering else None
        if row.seminar_group == target:
            continue
        row.seminar_group = target
        row.save(update_fields=["seminar_group", "updated_at"])
        (placed if target is not None else cleared).append(row.pk)
    return {"seminar_placed_enrollment_ids": placed, "seminar_cleared_enrollment_ids": cleared}


def after_transfer(*, record, old_group, new_group, period, by_user, redirects, carried=()) -> None:
    """Köçürmə yekunlaşdıqdan sonra (eyni tranzaksiya): ana jurnala qayıdış + seminar yeri + audit (fail-closed)."""
    changes = return_to_parent(redirects, subgroup=new_group, by_user=by_user) if redirects else {}
    for key, values in sync_seminar_groups(
        record=record, old_group=old_group, new_group=new_group, period=period
    ).items():
        changes[key] = [*changes.get(key, []), *values]
    if carried:
        changes["family_carried_enrollment_ids"] = [row.pk for row in carried]
        changes["family_carried_successor_ids"] = [row.superseded_by_id for row in carried]
    changes = {key: [str(value) for value in values] for key, values in changes.items() if values}
    if not changes:
        return
    audit_service.log_action(
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=record.organization,
        obj=record,
        action=AuditAction.UPDATE,
        resource_type=RESOURCE,
        resource_id=str(record.pk),
        old_values={"group_id": str(getattr(old_group, "pk", "") or "")},
        new_values={"group_id": str(new_group.pk)},
        changes=changes,
        reason=REASON,
    )


def is_chain_undo(successor, current) -> bool:
    """Hədəf tarixçə sətri əvəzləmə zənciri boyu MƏHZ cari sətirə çatırmı (A → A1 → A2 → A)."""
    if successor.status != Enrollment.Status.DROPPED or successor.superseded_by_id is None:
        return False
    cursor, seen = successor.superseded_by_id, set()
    for _step in range(CHAIN_LIMIT):
        if cursor == current.pk:
            return True
        if cursor is None or cursor in seen:
            return False
        seen.add(cursor)
        cursor = Enrollment.objects.filter(pk=cursor).values_list("superseded_by_id", flat=True).first()
    return False


__all__ = [
    "after_transfer",
    "carry_rows",
    "enroll_in_parent_journal",
    "family_parent_id",
    "is_chain_undo",
    "is_family_journal",
    "is_live",
    "parent_journal_for",
    "parent_offering",
    "redirect_target",
    "return_to_parent",
    "seminar_number",
    "sync_seminar_groups",
    "trail_parent_id",
]
