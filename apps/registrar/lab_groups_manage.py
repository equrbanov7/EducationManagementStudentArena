"""«Lab qrupları» ekranı — jurnalda laboratoriya qruplarını yaratmaq, adlandırmaq, tələbə yerləşdirmək, silmək.

Sahib 2026-11-06: «lab qruplarını əlavə etməyə yer olsun, yaratmaq üçün». Əvvəl qruplar yalnız data əmri
(``apply_lab_groups_20261106``) ilə yazılırdı. Bölgü qaydaları (kimin xanası, saat həddi) DƏYİŞMİR —
:mod:`apps.registrar.lab_groups`-dadır; bu modul yalnız qrupların özünü idarə edir.

MODEL: ``LabGroup(offering, number, name)`` — qrupun mövcudluğu + adı; üzvlük ``Enrollment.lab_group``-da qalır.

QAYDALAR:

* **Yaratmaq** — ən kiçik boş nömrə (1..9; dərsə bağlı nömrə də «məşğul» sayılır ki, köhnə dərs təsadüfən yeni
  qrupa keçməsin); ad istəyə bağlıdır.
* **Ad** — ≤ 40 simvol, boş = «Lab-N»; başqa qrupun adı ilə eyni ola bilməz (qridda iki eyni nişan olmasın).
* **Yerləşdirmək / köçürmək / qrupsuz etmək** — yalnız jurnalın AKTİV tələbələri. Tələbənin ÖZ qrupunun dərslərində
  (``Lesson.lab_group`` = tələbənin qrupu) qeydi varsa o tələbə köçürülmür: köhnə qeydlər başqa qrupun bağlı «·»
  xanasına çevrilərdi, qayıb saatı isə yenə sayılardı (dərsin qrupu ilə eyni qayda — ``gradebook_lessons``).
* **Silmək** — yalnız qrupa heç bir dərs bağlı deyilsə; üzvlər qrupsuz qalır; təsdiq (``confirm=1``) məcburidir.
* Siyahı qapısı alt qrup əməli ilə EYNİDİR (:func:`guest_roster.roster_block_reason`): bağlı jurnalda və keçmiş
  dövrdə tərkib dəyişmir.

SƏLAHİYYƏT (:func:`can_manage`) — jurnalın müəllimi (açılışın canlı müəllimi və ya «lab» növünü daşıyan aktiv
pay), açılışın KAFEDRASINI əhatə edən ``workload.distribute`` daşıyıcısı (kafedra müdiri — «Praktiki məşğələ»
açarı ilə eyni əhatə, :mod:`apps.registrar.practical_toggle`), RİM rəhbəri, təşkilat sahibi və superadmin.
Müşahidəçi, başqa müəllim və tələbə heç nə dəyişmir (HTTP 403). Hər dəyişiklik ``core.audit``-ə yazılır.
"""

from __future__ import annotations

import re

from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action, log_actions
from core.constants import AuditAction

from . import lab_groups
from .models import LAB_GROUP_NAME_MAX_LENGTH, CourseOffering, Enrollment, LabGroup, Lesson, LessonKind, LessonMark

_CTX = "registrar.lab_groups"
RESOURCE = "registrar.lab_groups"
#: Kafedra müdirinin açarı (dərs yükünün bölgüsü — lab yarım qrupları da yükün hissəsidir).
CHAIR_PERMISSION = "workload.distribute"


class LabGroupManageError(ValueError):
    """İstifadəçiyə göstərilən xəta (kod + mətn)."""

    def __init__(self, code, message):
        super().__init__(code, message)
        self.code = code
        self.message = str(message)


# ── Səlahiyyət ───────────────────────────────────────────────────────────────


def can_manage(user, offering) -> bool:
    """Aktor bu jurnalın lab qruplarını dəyişə bilərmi (fail-closed)."""
    from .journal_access import _is_live_assigned_instructor, offering_accepts_writes

    if offering is None or not getattr(user, "is_authenticated", False) or not offering_accepts_writes(offering):
        return False
    if any(getattr(user, flag, False) for flag in ("is_superuser", "is_superadmin", "is_ikt_rehber")):
        return True
    if offering.organization.owner_id == user.pk or _is_live_assigned_instructor(user, offering):
        return True
    from .journal_shares import share_for

    share = share_for(user, offering)
    if share is not None and (not share.kinds or LessonKind.LAB in share.kinds):
        return True
    return _chair_scope_covers(user, offering)


def _chair_scope_covers(user, offering) -> bool:
    """``workload.distribute`` əhatəsi açılışın kafedrasını örtürmü (``practical_toggle.can_toggle`` ilə eyni)."""
    from django.apps import apps as django_apps

    from .journal_scope import permission_scope_for
    from .offering_chairs import offering_chairs

    scope = permission_scope_for(user, offering.organization, CHAIR_PERMISSION)
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    units = {
        str(unit_id)
        for unit_id in django_apps.get_model("organizations", "OrgUnit")
        .objects.filter(organization_id=offering.organization_id)
        .filter(scope.unit_subtree_q())
        .values_list("pk", flat=True)
    }
    chairs = offering_chairs(CourseOffering.objects.filter(pk=offering.pk), offering.organization_id)
    return bool(units & set(chairs.get(offering.pk, ())))


def block_reason(offering) -> str:
    """Tərkib dəyişikliyi qadağandırsa səbəb (alt qrup əməli ilə eyni qapı), açıqdırsa boş sətir."""
    from .guest_roster import roster_block_reason

    return roster_block_reason(offering)


# ── Oxu ──────────────────────────────────────────────────────────────────────


def _roster(offering) -> list:
    return list(
        Enrollment.objects.filter(
            organization_id=offering.organization_id, offering_id=offering.pk, status=Enrollment.Status.ENROLLED
        )
        .select_related("student", "student__profile")
        .order_by("student__last_name", "student__username")
    )


def _locked_enrollment_ids(offering) -> set:
    """Öz qrupunun dərslərində qeydi olan aktiv qeydiyyatlar (köçürülmür) — bir sorğu."""
    return set(
        LessonMark.objects.filter(
            lesson__offering_id=offering.pk,
            lesson__lab_group__isnull=False,
            lesson__lab_group=F("enrollment__lab_group"),
            enrollment__status=Enrollment.Status.ENROLLED,
        )
        .values_list("enrollment_id", flat=True)
        .distinct()
    )


def panel(offering) -> dict:
    """Ekranın datası: qruplar (ad, üzvlər, bağlı dərs sayı) + qrupsuz tələbələr."""
    lab_groups.forget(offering)
    numbers = lab_groups.offering_groups(offering)
    names = lab_groups.names(offering)
    lessons = dict(
        Lesson.objects.filter(offering_id=offering.pk, lab_group__isnull=False)
        .order_by()
        .values("lab_group")
        .annotate(total=Count("id"))
        .values_list("lab_group", "total")
    )
    locked = _locked_enrollment_ids(offering)
    rows = [{"enrollment": row, "student": row.student, "locked": row.pk in locked} for row in _roster(offering)]
    groups = []
    for number in numbers:
        members = [row for row in rows if row["enrollment"].lab_group == number]
        groups.append(
            {
                "number": number,
                "label": lab_groups.label(number, offering),
                "default_label": lab_groups.default_label(number),
                "name": names.get(number, ""),
                "members": members,
                "lessons": lessons.get(number, 0),
                "can_delete": not lessons.get(number, 0),
            }
        )
    ungrouped = [row for row in rows if row["enrollment"].lab_group is None]
    return {
        "groups": groups,
        "ungrouped": ungrouped,
        "total": len(rows),
        "can_create": len(_busy_numbers(offering, numbers)) < lab_groups.MAX_LAB_GROUP,
        "name_max_length": LAB_GROUP_NAME_MAX_LENGTH,
    }


def _busy_numbers(offering, numbers) -> set:
    lesson_numbers = Lesson.objects.filter(offering_id=offering.pk, lab_group__isnull=False).values_list(
        "lab_group", flat=True
    )
    return set(numbers) | set(lesson_numbers)


# ── Giriş datası ─────────────────────────────────────────────────────────────


def clean_name(raw) -> str:
    return " ".join(str(raw or "").split())[:LAB_GROUP_NAME_MAX_LENGTH]


def _name_key(text) -> str:
    """Müqayisə açarı: registr, boşluq və defis fərqi sayılmır («Lab 2» = «lab-2»)."""
    return re.sub(r"[\s\-]+", "", str(text or "").casefold())


def _own_name(number, name) -> str:
    """Ad qrupun öz defolt adıdırsa («Lab-N» istənilən dildə) boş saxlanır."""
    defaults = {_name_key(lab_groups.default_label(number)), f"lab{number}"}
    return "" if _name_key(name) in defaults else name


def parse_number(raw) -> int:
    try:
        number = lab_groups.parse(raw)
    except lab_groups.LabGroupError as exc:
        raise LabGroupManageError("invalid_group", str(exc)) from exc
    if number is None:
        raise LabGroupManageError("invalid_group", pgettext(_CTX, "Laboratoriya qrupu düzgün seçilməyib."))
    return number


def _require_group(offering, number) -> None:
    if number not in lab_groups.offering_groups(offering):
        raise LabGroupManageError("not_found", pgettext(_CTX, "Bu jurnalda belə laboratoriya qrupu yoxdur."))


def _check_name_unique(offering, number, name) -> None:
    if not name:
        return
    others = [other for other in lab_groups.offering_groups(offering) if other != number]
    taken = {_name_key(lab_groups.label(other, offering)) for other in others} | {f"lab{other}" for other in others}
    if _name_key(name) in taken:
        raise LabGroupManageError("duplicate_name", pgettext(_CTX, "Bu adda laboratoriya qrupu artıq var."))


def _lock_offering(offering) -> None:
    """Eyni jurnalda paralel əməllər sıralansın (nömrə seçimi, silmə)."""
    CourseOffering.objects.select_for_update().filter(pk=offering.pk).values_list("pk", flat=True).first()
    lab_groups.forget(offering)


def _audit(action, *, offering, actor, request, changes, reason, old=None, new=None):
    log_action(
        action,
        user=actor,
        organization=offering.organization,
        obj=offering,
        old_values=old,
        new_values=new,
        changes=changes,
        reason=reason,
        request=request,
        resource_type=RESOURCE,
        resource_id=str(offering.pk),
    )


# ── Əməllər ──────────────────────────────────────────────────────────────────


def create_group(*, offering, actor, name="", request=None) -> int:
    """Yeni qrup: ən kiçik boş nömrə. Qaytarır: nömrə."""
    name = clean_name(name)
    with transaction.atomic():
        _lock_offering(offering)
        busy = _busy_numbers(offering, lab_groups.offering_groups(offering))
        free = [number for number in range(1, lab_groups.MAX_LAB_GROUP + 1) if number not in busy]
        if not free:
            raise LabGroupManageError(
                "too_many",
                pgettext(_CTX, "Jurnalda ən çox %(max)s laboratoriya qrupu ola bilər.")
                % {"max": lab_groups.MAX_LAB_GROUP},
            )
        number = free[0]
        name = _own_name(number, name)
        _check_name_unique(offering, number, name)
        LabGroup.objects.create(organization_id=offering.organization_id, offering=offering, number=number, name=name)
        _audit(
            AuditAction.CREATE,
            offering=offering,
            actor=actor,
            request=request,
            new={"lab_group": number, "name": name},
            changes={"verb": "lab_group_create", "lab_group": number},
            reason=f"Laboratoriya qrupu yaradıldı: {name or lab_groups.default_label(number)}",
        )
    lab_groups.forget(offering)
    return number


def rename_group(*, offering, number, name, actor, request=None) -> bool:
    """Qrupun adı (boş = «Lab-N»). Qaytarır: dəyişdimi."""
    name = _own_name(number, clean_name(name))
    with transaction.atomic():
        _lock_offering(offering)
        _require_group(offering, number)
        _check_name_unique(offering, number, name)
        row = LabGroup.objects.select_for_update().filter(offering_id=offering.pk, number=number).first()
        old = row.name if row is not None else ""
        if old == name:
            return False
        if row is None:
            LabGroup.objects.create(
                organization_id=offering.organization_id, offering=offering, number=number, name=name
            )
        else:
            row.name = name
            row.save(update_fields=["name", "updated_at"])
        _audit(
            AuditAction.UPDATE,
            offering=offering,
            actor=actor,
            request=request,
            old={"name": old},
            new={"name": name},
            changes={"verb": "lab_group_rename", "lab_group": number},
            reason=f"Laboratoriya qrupunun adı: {old or '—'} → {name or lab_groups.default_label(number)}",
        )
    lab_groups.forget(offering)
    return True


def assign(*, offering, enrollment_ids, target, actor, request=None) -> dict:
    """Tələbələri ``target`` qrupuna yerləşdir (``None`` = qrupsuz). Qaytarır: ``moved`` / ``locked`` / ``unchanged``."""
    ids = list(dict.fromkeys(enrollment_ids))
    if not ids:
        raise LabGroupManageError("empty", pgettext(_CTX, "Tələbə seçilməyib."))
    with transaction.atomic():
        _lock_offering(offering)
        if target is not None:
            _require_group(offering, target)
        rows = list(
            Enrollment.objects.select_for_update(of=("self",))
            .select_related("student")
            .filter(
                organization_id=offering.organization_id,
                offering_id=offering.pk,
                status=Enrollment.Status.ENROLLED,
                pk__in=ids,
            )
        )
        if len(rows) != len(ids):
            raise LabGroupManageError("not_found", pgettext(_CTX, "Seçilən tələbələrdən biri bu jurnalda deyil."))
        locked = _locked_enrollment_ids(offering)
        now = timezone.now()
        changed, counts = [], {"moved": 0, "locked": 0, "unchanged": 0}
        for row in rows:
            if row.lab_group == target:
                counts["unchanged"] += 1
            elif row.pk in locked:
                counts["locked"] += 1
            else:
                changed.append((row, row.lab_group))
                row.lab_group, row.updated_at = target, now
        if changed:
            Enrollment.objects.bulk_update([row for row, _old in changed], ["lab_group", "updated_at"])
            log_actions(
                {
                    "action": AuditAction.UPDATE,
                    "user": actor,
                    "organization": offering.organization,
                    "obj": row,
                    "old_values": {"lab_group": old},
                    "new_values": {"lab_group": target},
                    "changes": {"verb": "lab_group_assign", "offering_id": str(offering.pk)},
                    "reason": "Laboratoriya qrupu: "
                    f"{lab_groups.label(old, offering) if old else '—'} → "
                    f"{lab_groups.label(target, offering) if target else '—'}",
                    "request": request,
                    "resource_type": RESOURCE,
                    "resource_id": str(row.pk),
                }
                for row, old in changed
            )
        counts["moved"] = len(changed)
    lab_groups.forget(offering)
    return counts


def delete_group(*, offering, number, actor, confirmed, request=None) -> int:
    """Qrupu sil: dərs bağlı deyilsə; üzvlər qrupsuz qalır. Qaytarır: qrupsuz qalan tələbə sayı."""
    if not confirmed:
        raise LabGroupManageError("confirm", pgettext(_CTX, "Silməni təsdiqləyin."))
    with transaction.atomic():
        _lock_offering(offering)
        _require_group(offering, number)
        bound = Lesson.objects.filter(offering_id=offering.pk, lab_group=number).count()
        if bound:
            raise LabGroupManageError(
                "has_lessons",
                pgettext(
                    _CTX,
                    "Bu qrupa %(n)s dərs bağlıdır — əvvəlcə həmin dərslərin qrupunu dəyişin və ya dərsləri silin.",
                )
                % {"n": bound},
            )
        label = lab_groups.label(number, offering)
        members = list(
            Enrollment.objects.select_for_update(of=("self",))
            .filter(organization_id=offering.organization_id, offering_id=offering.pk, lab_group=number)
            .values_list("pk", flat=True)
        )
        Enrollment.objects.filter(pk__in=members).update(lab_group=None, updated_at=timezone.now())
        LabGroup.objects.filter(offering_id=offering.pk, number=number).delete()
        _audit(
            AuditAction.DELETE,
            offering=offering,
            actor=actor,
            request=request,
            old={"lab_group": number, "name": label, "members": [str(pk) for pk in members]},
            changes={"verb": "lab_group_delete", "lab_group": number, "unassigned": len(members)},
            reason=f"Laboratoriya qrupu silindi: {label} ({len(members)} tələbə qrupsuz qaldı)",
        )
    lab_groups.forget(offering)
    return len(members)


__all__ = [
    "CHAIR_PERMISSION",
    "LabGroupManageError",
    "assign",
    "block_reason",
    "can_manage",
    "clean_name",
    "create_group",
    "delete_group",
    "panel",
    "parse_number",
    "rename_group",
]
