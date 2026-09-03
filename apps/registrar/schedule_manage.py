"""Dərs cədvəlinin İDARƏSİ — icazə, əhatə və slot validasiyası (OXU qatı).

Yazma qatı ayrıdır: :mod:`apps.registrar.schedule_manage_actions`.

──────────────────────────────────────────────────────────────────────────────
QƏRAR (sahibin tələbi, 2026-09)
──────────────────────────────────────────────────────────────────────────────
Əvvəllər cədvəl slotunu YALNIZ dərsi aparan müəllim (və org sahibi/superuser)
əlavə edib silə bilirdi (``journal_access.is_direct_editor``). Bu, universitet
reallığına ziddir: cədvəli müəllim yox, **proqram koordinatoru / dekanlıq /
RİM** qurur. Ona görə qapı indi kanonik icazə açarındadır::

    schedule.manage   → slot əlavəsi/silinməsi (UNIT rollarında `scope_unit` alt-ağacı)

* ``program_coordinator`` — öz ixtisasının alt-ağacı (əsas sahib);
* ``ikt_rehber`` (RİM)    — org-wide;
* ``dean`` / ``chair_head`` — öz fakültə/kafedra alt-ağacı;
* ``rector`` / ``vice_rector`` / sahib / superuser — ``*`` ilə org-wide.

**Adi müəllimdə açar QƏSDƏN YOXDUR.** Müəllim öz həftəlik cədvəlini görür
(``my-schedule``), amma slot yaza/silə bilmir — açılışın müəllimi olmaq artıq
səlahiyyət vermir. Açarı olan müəllimə isə ADİ qaydalar tətbiq olunur (əhatə +
konflikt), yəni açar permission-editordan verilə bilər.

MODUL SƏRHƏDİ: registrar ``apps.organizations``-u Python səviyyəsində İMPORT
ETMİR (dövr yaranardı) — model app registry ilə həll olunur və alt-ağac
yoxlaması ``OrgUnit.user_permission_scope`` daxilindədir (``journal_scope`` naxışı).
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import journal_scope, schedule
from apps.registrar.models import CourseOffering, ScheduleSlot, SlotKind, WeekType

#: Cədvəl slotlarını idarə etmək icazəsi (kataloq: organizations.permissions).
SCHEDULE_PERMISSION = "schedule.manage"

#: Yalnız-baxış açarı (kataloq bütövlüyü; şəxsi cədvəl onsuz da hər kəsə açıqdır).
SCHEDULE_VIEW_PERMISSION = "schedule.view"

_CTX = "registrar.schedule_manage"


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


# ── İcazə + əhatə ────────────────────────────────────────────────────────────


def actor_scope(user, organization):
    """Aktorun ``schedule.manage`` struktur əhatəsi (``UnitScope``)."""
    return _org_unit_model().user_permission_scope(user, organization, SCHEDULE_PERMISSION)


def can_manage(user, organization) -> bool:
    """İcazə struktur əhatəsi verirmi (org və ya unit) — fail-closed."""
    if organization is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    return actor_scope(user, organization).has_structure_access


def can_manage_offering(user, organization, offering) -> bool:
    """Bu KONKRET açılışın cədvəlini aktor idarə edə bilirmi (fail-closed).

    Superuser/org sahibi həmişə; qalanlar üçün ``schedule.manage`` + açılışın
    QRUP bölməsinin aktorun alt-ağacında olması. Açılışın MÜƏLLİMİ olmaq tək
    başına səlahiyyət VERMİR (sahibin qərarı).
    """
    if offering is None or organization is None:
        return False
    if getattr(offering, "organization_id", None) != getattr(organization, "pk", None):
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    return journal_scope.offering_in_actor_scope(user, organization, offering, permission=SCHEDULE_PERMISSION)


def scoped_groups(user, organization):
    """Aktorun cədvəlini qura biləcəyi QRUP bölmələri (fail-closed queryset)."""
    from core.constants import OrgUnitType

    org_unit_model = _org_unit_model()
    if organization is None:
        return org_unit_model.objects.none()
    base = org_unit_model.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.GROUP)
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return base.order_by("name")
    scope = actor_scope(user, organization)
    if not scope.has_structure_access:
        return org_unit_model.objects.none()
    if scope.is_org_wide:
        return base.order_by("name")
    return base.filter(scope.unit_subtree_q()).order_by("name")


def scoped_offerings(user, organization, *, period=None, group=None):
    """Aktorun cədvəlinə slot yaza biləcəyi açılışlar (fail-closed queryset)."""
    if organization is None:
        return CourseOffering.objects.none()
    queryset = CourseOffering.objects.filter(organization=organization, is_active=True)
    if period is not None:
        queryset = queryset.filter(period=period)
    if group is not None:
        queryset = queryset.filter(group=group)
    if getattr(user, "is_superuser", False) or getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return queryset
    scope = actor_scope(user, organization)
    if not scope.has_structure_access:
        return CourseOffering.objects.none()
    if scope.is_org_wide:
        return queryset
    units = _org_unit_model().objects.filter(organization=organization).filter(scope.unit_subtree_q())
    return queryset.filter(group__in=units.values("pk"))


# ── Slot validasiyası (PREVENT, don't save) ──────────────────────────────────


def parse_payload(data) -> tuple[dict, dict]:
    """Xam POST/JSON sözlüyünü təmizlənmiş dəyərlərə çevirir.

    Qaytarır ``(cleaned, errors)``. Vaxt həm standart dərs saatı seçimi
    (``time_slot`` = "HH:MM|HH:MM"), həm də sərbəst ``start_time``/``end_time``
    ilə verilə bilər — birincinin üstünlüyü var.
    """
    from django.utils.dateparse import parse_time

    errors: dict = {}
    cleaned: dict = {}

    try:
        weekday = int(str(data.get("weekday") or "").strip() or 0)
    except (TypeError, ValueError):
        weekday = 0
    if not 1 <= weekday <= 7:
        errors["weekday"] = pgettext(_CTX, "Həftənin günü 1–7 aralığında olmalıdır.")
    cleaned["weekday"] = weekday

    start_time, end_time = schedule.parse_time_slot(data.get("time_slot"))
    if start_time is None:
        start_time = parse_time(str(data.get("start_time") or "").strip())
        end_time = parse_time(str(data.get("end_time") or "").strip())
    if start_time is None or end_time is None:
        errors["time_slot"] = pgettext(_CTX, "Başlama və bitmə vaxtı düzgün seçilməlidir.")
    elif end_time <= start_time:
        errors["time_slot"] = pgettext(_CTX, "Bitmə vaxtı başlama vaxtından sonra olmalıdır.")
    cleaned["start_time"] = start_time
    cleaned["end_time"] = end_time

    week_type = str(data.get("week_type") or "").strip()
    cleaned["week_type"] = week_type if week_type in dict(WeekType.choices) else WeekType.ALL
    slot_kind = str(data.get("slot_kind") or data.get("kind") or "").strip()
    cleaned["kind"] = slot_kind if slot_kind in dict(SlotKind.choices) else SlotKind.LECTURE
    cleaned["room"] = str(data.get("room") or "").strip()[:64]
    return cleaned, errors


def period_window_error(offering) -> str:
    """Açılışın dövrü cədvəl yazmağa açıqdırmı — bağlıdırsa səbəb mətni."""
    period = getattr(offering, "period", None)
    end_date = getattr(period, "end_date", None)
    if isinstance(end_date, str):
        try:
            end_date = datetime.date.fromisoformat(end_date)
        except ValueError:
            end_date = None
    elif isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    if end_date and end_date < timezone.localdate():
        return pgettext(_CTX, "Bu semestr bitib — cədvəl slotu əlavə edilə bilməz.")
    return ""


def duplicate_slot(*, offering, weekday, start_time, end_time, week_type, room, exclude_id=None):
    """Eyni açılış üçün EYNİ slot artıq varmı (təkrar yazılış)."""
    queryset = ScheduleSlot.objects.filter(
        organization_id=offering.organization_id,
        offering=offering,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        week_type=week_type,
    )
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    room_norm = (room or "").strip().lower()
    for slot in queryset:
        if (slot.room or "").strip().lower() == room_norm:
            return slot
    return None


def conflict_reason(*, offering, conflict) -> str:
    """Konfliktin SƏBƏBİ (qrup / müəllim / otaq) — istifadəçiyə açıq mətn."""
    other = conflict.offering
    if offering.group_id and other.group_id == offering.group_id:
        return pgettext(_CTX, "qrup")
    if offering.instructor_id and other.instructor_id == offering.instructor_id:
        return pgettext(_CTX, "müəllim")
    return pgettext(_CTX, "auditoriya")


def describe_conflict(conflict, *, offering=None) -> dict:
    """Konflikt slotunun UI müqaviləsi (JSON) — açar adları dəyişməz."""
    other = conflict.offering
    return {
        "id": str(conflict.pk),
        "reason": conflict_reason(offering=offering, conflict=conflict) if offering is not None else "",
        "subject_code": getattr(other.subject, "code", "") or "",
        "subject_name": getattr(other.subject, "name", "") or "",
        "group": getattr(other.group, "name", "") or "",
        "instructor": (getattr(other.instructor, "get_full_name", lambda: "")() or "").strip()
        or str(getattr(other.instructor, "username", "") or ""),
        "room": conflict.room or "",
        "weekday": conflict.weekday,
        "start_time": conflict.start_time.strftime("%H:%M"),
        "end_time": conflict.end_time.strftime("%H:%M"),
        "week_type": conflict.week_type,
    }


def check_slot(*, offering, cleaned, exclude_id=None) -> dict:
    """Bütün saxlama-öncəsi yoxlamalar — ``{sahə: mətn}`` (boşdursa təmizdir).

    Sıra qəsdən belədir: dövr pəncərəsi → təkrar → konflikt. Birinci tapılan
    problemə görə qalanları hesablamaq mənasızdır (istifadəçi onsuz da düzəldib
    yenidən göndərəcək), amma sahələr fərqli olduğu üçün hamısı toplanır.
    """
    errors: dict = {}
    window = period_window_error(offering)
    if window:
        errors["period"] = window
    if errors:
        return errors

    duplicate = duplicate_slot(
        offering=offering,
        weekday=cleaned["weekday"],
        start_time=cleaned["start_time"],
        end_time=cleaned["end_time"],
        week_type=cleaned["week_type"],
        room=cleaned["room"],
        exclude_id=exclude_id,
    )
    if duplicate is not None:
        errors["time_slot"] = pgettext(_CTX, "Bu slot artıq cədvəldədir.")
        return errors

    conflict = schedule.find_conflict(
        organization=offering.organization,
        offering=offering,
        weekday=cleaned["weekday"],
        start_time=cleaned["start_time"],
        end_time=cleaned["end_time"],
        week_type=cleaned["week_type"],
        room=cleaned["room"],
        exclude_id=exclude_id,
    )
    if conflict is not None:
        errors["conflict"] = pgettext(_CTX, "Bu vaxt %(subject)s ilə üst-üstə düşür (%(reason)s).") % {
            "subject": getattr(conflict.offering.subject, "code", "") or "",
            "reason": conflict_reason(offering=offering, conflict=conflict),
        }
        errors["_conflict"] = describe_conflict(conflict, offering=offering)
    return errors


__all__ = [
    "SCHEDULE_PERMISSION",
    "SCHEDULE_VIEW_PERMISSION",
    "actor_scope",
    "can_manage",
    "can_manage_offering",
    "check_slot",
    "conflict_reason",
    "describe_conflict",
    "duplicate_slot",
    "parse_payload",
    "period_window_error",
    "scoped_groups",
    "scoped_offerings",
]
