"""Tələbənin SEMESTR kredit yükü — öz fənləri + alt qrup fənləri (sahib 2026-10-18).

Sahib: «Hər tələbənin bir semestrdə götürə biləcəyi max kredit var — alt qrupa və s. yazılanda o hesablanır;
bunu sistem tərəfindən tənzimləmək olsun». Bu modul YEGANƏ hesablama nöqtəsidir: kabinet («Bu semestr:
27 / 30 kredit»), əməkdaş səthləri (reyestr çekməcəsi, «Alt qrupa tələbə əlavə et») və yerləşdirmə qapısı
(:mod:`apps.registrar.subgroup_placement`) hamısı buradan oxuyur.

QAYDA
─────
* Sayılan yazılışlar — dövrün ``enrolled`` / ``completed`` qeydiyyatları. ``dropped`` (geri götürülmüş, «Fəndən
  azad», birləşmədə əvəzlənmiş) və ``suspended`` (akademik məzuniyyət / xaric — dondurulmuş) SAYILMIR.
* Fənnin krediti — tələbənin TƏDRİS PLANI sətrindəki kredit (həmin fənn + həmin SEMESTR, ``credits`` > 0), yoxdursa
  kataloq dəyəri ``Subject.ects``. Qayda və semestr seçimi YEGANƏ yerdədir: :mod:`apps.registrar.credit_source`
  (R01, 2026-10-21 — transkript / ÜOMG / 25% haqqı da eyni həlledicidən oxuyur).
* «Alt qrup» — ``source_group`` dolu VƏ açılışın qrupu tələbənin CARİ qrupu deyil VƏ yerləşdirmə SƏNƏDLƏ
  təsdiqlənib (:mod:`apps.registrar.subgroup_evidence`, sahib 2026-10-25: «bilməsən yazma»). Köçürmənin sənədsiz
  sətirləri (ana qrup / bölgü jurnalı) «öz» fənni sayılır.
* Eyni fənn dövrdə bir neçə jurnalda (mühazirə ana qrupda, seminar bölgüdə) — kredit BİR dəfə sayılır.
* Hədd — «Sistem tənzimləmələri» (``credits.max_per_semester`` / ``credits.max_with_subgroup``,
  :mod:`core.runtime_settings_credits`). Alt qrup krediti olan (və ya alınacaq) tələbəyə «alt qrupla birlikdə»
  həddi tətbiq olunur; o 0-dırsa adi hədd. Öz fənləri (tədris planı) heç vaxt bloklanmır — yalnız
  ``over_limit`` xəbərdarlığı.

Sorğu büdcəsi: 3 sabit sorğu (qeyd + yazılışlar + plan kreditləri; sənəd yoxlaması EXISTS ilə yazılış sorğusundadır).
"""

from __future__ import annotations

from core import runtime_settings

from . import credit_source, subgroup_evidence
from .models import AcademicStatus, Enrollment, StudentAcademicRecord

#: Kredit yükünə düşən qeydiyyat statusları (bax modul şərhi).
LOAD_STATUSES = (Enrollment.Status.ENROLLED, Enrollment.Status.COMPLETED)


def limits() -> dict:
    """Cari hədlər: ``base`` (adi) və ``with_subgroup`` (alt qrupla birlikdə; 0 → adi hədd)."""
    base = runtime_settings.get_int("credits.max_per_semester")
    with_subgroup = runtime_settings.get_int("credits.max_with_subgroup") or base
    return {"base": base, "with_subgroup": with_subgroup}


def active_record(student, organization, *, lock=False):
    """Tələbənin AKTİV, oxuyan (``enrolled``) akademik qeydi — ən yenisi; yoxdursa ``None``."""
    organization_id = getattr(organization, "pk", organization)
    queryset = StudentAcademicRecord.objects.filter(
        organization_id=organization_id, student=student, is_active=True, status=AcademicStatus.ENROLLED
    )
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    return queryset.select_related("group", "program", "curriculum").order_by("-created_at").first()


def plan_credit_map(curriculum_id, subject_ids, *, period=None) -> dict:
    """``{subject_id: plan krediti}`` — planın override-ı (yalnız > 0), TƏK sorğu.

    Semestrə həssasdır (R01 nit): fənn planda bir neçə semestrdədirsə *period*-un plan semestri seçilir
    (:func:`credit_source.pick_credit`); ``period`` verilməsə ən kiçik semestr (köhnə davranış).
    """
    subject_ids = [value for value in subject_ids if value]
    if not curriculum_id or not subject_ids:
        return {}
    resolver = credit_source.resolver_for_curriculum(curriculum_id, subject_ids)
    result: dict = {}
    for subject_id in subject_ids:
        value = resolver.curriculum_credit(curriculum_id, subject_id, period=period, catalogue=0)
        if value > 0:
            result[subject_id] = value
    return result


def offering_credit(offering, plan_credits=None) -> int:
    """Açılışın tələbəyə görə krediti — plan override, yoxdursa ``Subject.ects``."""
    plan_credits = plan_credits or {}
    value = plan_credits.get(offering.subject_id)
    if value:
        return int(value)
    return int(getattr(offering.subject, "ects", 0) or 0)


def is_subgroup_row(enrollment, current_group_id) -> bool:
    """``guest_roster.row_is_guest``-in sorğusuz güzgüsü (cari qrup hazır verilir)."""
    if getattr(enrollment, "source_group_id", None) is None:
        return False
    group_id = enrollment.offering.group_id
    return group_id is None or group_id != current_group_id


def _empty(limit_values) -> dict:
    return {
        "has_record": False,
        "total": 0,
        "own": 0,
        "subgroup": 0,
        "limit": limit_values["base"],
        "base_limit": limit_values["base"],
        "subgroup_limit": limit_values["with_subgroup"],
        "remaining": limit_values["base"],
        "over_limit": False,
        "items": [],
        "subgroup_enrollment_ids": [],
        "group_name": "",
    }


def credit_load(student, period, *, organization=None, record=None) -> dict:
    """``{"total", "own", "subgroup", "limit", "remaining", …}`` — tələbənin *period* yükü.

    ``limit`` — tələbəyə hazırda tətbiq olunan hədd (alt qrup krediti varsa «alt qrupla birlikdə»).
    ``items`` — sətirlər (fənn, kredit, alt qrupdurmu) — UI və yoxlama üçün.
    """
    limit_values = limits()
    if period is None:
        return _empty(limit_values)
    # ``period.organization`` oxumaq əlavə sorğudur — id kifayətdir (sorğu büdcəsi).
    organization_id = getattr(organization, "pk", None) or period.organization_id
    if record is None:
        record = active_record(student, organization_id)
    if record is None:
        return _empty(limit_values)
    enrollments = list(
        subgroup_evidence.annotate_documented(Enrollment.objects)
        .filter(organization_id=organization_id, student=student, offering__period=period, status__in=LOAD_STATUSES)
        .select_related("offering__subject", "offering__group")
        .order_by("offering__subject__code")
    )
    plan_credits = plan_credit_map(record.curriculum_id, [e.offering.subject_id for e in enrollments], period=period)
    items = []
    own = subgroup = 0
    counted_subjects: set = set()
    for enrollment in enrollments:
        credits = offering_credit(enrollment.offering, plan_credits)
        guest = enrollment.subgroup_documented and is_subgroup_row(enrollment, record.group_id)
        subject_id = enrollment.offering.subject_id
        if subject_id in counted_subjects:
            pass  # eyni fənnin ikinci jurnalı — kredit artıq sayılıb
        elif guest:
            subgroup += credits
        else:
            own += credits
        counted_subjects.add(subject_id)
        offering = enrollment.offering
        items.append(
            {
                "enrollment_id": str(enrollment.pk),
                "offering_id": str(offering.pk),
                "subject_id": str(offering.subject_id),
                "subject_code": offering.subject.code,
                "subject_name": offering.subject.name,
                "group_name": getattr(offering.group, "name", "") or "",
                "credits": credits,
                "is_subgroup": guest,
                "kind": enrollment.kind,
            }
        )
    total = own + subgroup
    limit = limit_values["with_subgroup"] if subgroup else limit_values["base"]
    return {
        "has_record": True,
        "total": total,
        "own": own,
        "subgroup": subgroup,
        "limit": limit,
        "base_limit": limit_values["base"],
        "subgroup_limit": limit_values["with_subgroup"],
        "remaining": max(0, limit - total),
        "over_limit": total > limit,
        "items": items,
        "subgroup_enrollment_ids": [item["enrollment_id"] for item in items if item["is_subgroup"]],
        "group_name": getattr(record.group, "name", "") or "",
    }


def projected(load: dict, *, add_credits: int, release_credits: int = 0) -> dict:
    """Yerləşdirmədən SONRAKI yük: alt qrup həddi ilə müqayisə (``fits``)."""
    total_after = load["total"] + int(add_credits) - int(release_credits)
    limit = load["subgroup_limit"]
    return {
        "total_before": load["total"],
        "total_after": total_after,
        "subgroup_after": load["subgroup"] + int(add_credits),
        "limit": limit,
        # Kredit artırmayan əməl (birləşmə: öz jurnalından azad + bura) heç vaxt bloklanmır.
        "fits": total_after <= limit or int(add_credits) - int(release_credits) <= 0,
        "remaining_after": max(0, limit - total_after),
    }


__all__ = [
    "LOAD_STATUSES",
    "active_record",
    "credit_load",
    "is_subgroup_row",
    "limits",
    "offering_credit",
    "plan_credit_map",
    "projected",
]
