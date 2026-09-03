"""Profil «schedule-manage» bölməsi — Cədvəl idarəetməsi (`schedule.manage`).

Bölmə profil shell-inin İÇİNDƏ açılır (sol sidebar qalır, panel sağdadır) və
SERVER-RENDER-lidir: dövr/qrup seçimi panel fraqmentini yenidən yükləyir
(``EMSProfileLoadSection``), yalnız İKİ əməl JSON-la gedir — saxlama-öncəsi
konflikt yoxlaması və slot əlavəsi/silinməsi.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (UI buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``schedule_manage_section`` (dict):

    has_access      bool   — `schedule.manage` + struktur əhatəsi
    scope_label     str    — «Bütün universitet» / «Yalnız öz bölmələriniz»
    years           list   — tədris illəri (year_display)
    selected_year   str
    periods         list   — seçilmiş ilin semestrləri (season_label ilə)
    period          obj    — seçilmiş semestr
    groups          list   — əhatədəki qruplar [{id, name}]
    group           obj    — seçilmiş qrup
    view_mode       str    — "group" | "teacher"
    teachers        list   — əhatədəki müəllimlər [{id, name}]
    teacher         obj    — seçilmiş müəllim (teacher rejimi)
    offerings       list   — slot formasının fənn seçimi (qrup+dövr üzrə)
    slots           list   — cari görünüşün slotları (silmə siyahısı üçün)
    rooms           list   — auditoriya adları (datalist)
    week / time_grid       — həftə grid-i (registrar.schedule)
    check_url / action_url str — JSON endpoint-ləri
    reload_url      str    — panelin öz fraqment/URL prefiksi (?section=…&)
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import schedule as schedule_service
from apps.registrar import schedule_manage

from .kollokvium_windows import _current_semester, _season_label

_CTX = "accounts.schedule_manage"

#: Cədvəl otağı CharField-dir; `exams.ExamRoom` adları YALNIZ datalist təklifi
#: kimi verilir (məcburi seçim DEYİL — bir çox tenantda zal kataloqu boşdur).
_ROOM_SUGGESTION_LIMIT = 200


def _person_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def _endpoints(section):
    section["check_url"] = reverse("accounts:schedule_manage_check")
    section["action_url"] = reverse("accounts:schedule_manage_action")
    section["reload_url"] = "%s?section=schedule-manage&" % reverse("accounts:profile")


def _periods(section, request, organization):
    """Tədris ili + semestr seçimi — kollokvium panelindəki qayda ilə eyni."""
    from django.utils import timezone

    from apps.organizations.models import AcademicPeriod

    all_periods = list(AcademicPeriod.objects.filter(organization=organization).order_by("-start_date"))
    for period in all_periods:
        period.season_label = _season_label(period)

    years, seen = [], set()
    for period in all_periods:
        year = period.year_display
        if year and year not in seen:
            seen.add(year)
            years.append(year)

    default_period = _current_semester(all_periods, timezone.localdate())
    requested_year = (request.GET.get("sm_year") or "").strip()
    selected_year = requested_year if requested_year in seen else None
    if selected_year is None and default_period is not None:
        selected_year = default_period.year_display
    if selected_year is None and years:
        selected_year = years[0]

    periods_in_year = [p for p in all_periods if p.year_display == selected_year]
    requested_period = (request.GET.get("sm_period") or "").strip()
    period = next((p for p in periods_in_year if str(p.id) == requested_period), None)
    if period is None and default_period is not None and default_period.year_display == selected_year:
        period = default_period
    if period is None:
        period = next((p for p in periods_in_year if p.is_current), None)
    if period is None and periods_in_year:
        period = periods_in_year[0]

    section["years"] = years
    section["selected_year"] = selected_year
    section["periods"] = periods_in_year
    section["period"] = period
    return period


def _rooms(organization):
    """Auditoriya adı təklifləri — `exams.ExamRoom` kataloqu (varsa)."""
    try:
        from apps.exams.models import ExamRoom
    except Exception:  # pragma: no cover — imtahan modulu söndürülübsə
        return []
    return list(
        ExamRoom.objects.filter(organization=organization, is_active=True)
        .order_by("name")
        .values_list("name", flat=True)[:_ROOM_SUGGESTION_LIMIT]
    )


def _teachers(offerings_qs):
    """Əhatədəki açılışların müəllimləri (təkrarsız, ada görə)."""
    rows = {}
    for offering in offerings_qs.select_related("instructor").exclude(instructor__isnull=True):
        rows.setdefault(str(offering.instructor_id), _person_name(offering.instructor))
    return [{"id": key, "name": name} for key, name in sorted(rows.items(), key=lambda item: item[1])]


def _grid(section, request, organization, period, slots):
    try:
        week_offset = max(-8, min(16, int(request.GET.get("w") or 0)))
    except (TypeError, ValueError):
        week_offset = 0
    week_context = schedule_service.build_week_context(period, offset=week_offset)
    section["week"] = week_context
    section["time_grid"] = schedule_service.build_time_grid(slots, week_context=week_context)


def build_schedule_manage_section(request, section, *, active_organization, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir (handover/kollokvium naxışı)."""
    if "schedule-manage" not in allowed_sections or active_section != "schedule-manage":
        return

    _endpoints(section)
    section["access_denied_message"] = pgettext(
        _CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür."
    )
    has_access = bool(active_organization is not None and schedule_manage.can_manage(request.user, active_organization))
    section["has_access"] = has_access
    if not has_access:
        return

    organization = active_organization
    scope = schedule_manage.actor_scope(request.user, organization)
    section["scope_label"] = (
        pgettext(_CTX, "Bütün universitet")
        if (scope.is_org_wide or request.user.is_superuser or organization.owner_id == request.user.pk)
        else pgettext(_CTX, "Yalnız öz struktur bölmələriniz")
    )

    period = _periods(section, request, organization)

    groups = list(schedule_manage.scoped_groups(request.user, organization).values("id", "name"))
    section["groups"] = groups
    requested_group = (request.GET.get("sm_group") or "").strip()
    group = None
    if groups:
        group_ids = {str(row["id"]) for row in groups}
        from apps.organizations.models import OrgUnit

        chosen = requested_group if requested_group in group_ids else str(groups[0]["id"])
        group = OrgUnit.objects.filter(pk=chosen).first()
    section["group"] = group

    scoped = schedule_manage.scoped_offerings(request.user, organization, period=period)
    section["teachers"] = _teachers(scoped)

    view_mode = "teacher" if (request.GET.get("sm_view") or "").strip() == "teacher" else "group"
    section["view_mode"] = view_mode
    teacher = None
    if view_mode == "teacher":
        requested_teacher = (request.GET.get("sm_teacher") or "").strip()
        known = {row["id"] for row in section["teachers"]}
        if requested_teacher in known:
            from django.contrib.auth import get_user_model

            teacher = get_user_model().objects.filter(pk=requested_teacher).first()
    section["teacher"] = teacher

    slots = []
    if period is not None:
        if view_mode == "teacher" and teacher is not None:
            slots = schedule_service.get_teacher_schedule(organization=organization, teacher=teacher, period=period)
        elif group is not None:
            slots = schedule_service.get_group_schedule(organization=organization, group=group, period=period)
    weekday_labels = dict(schedule_service.WEEKDAYS)
    for slot in slots:
        # Şablon gün NÖMRƏSİNİ yox, ADINI göstərir (cədvəl sətri oxunaqlı olsun).
        slot.weekday_label = str(weekday_labels.get(slot.weekday, slot.weekday))
    section["slots"] = slots

    section["offerings"] = (
        list(
            schedule_manage.scoped_offerings(request.user, organization, period=period, group=group)
            .select_related("subject", "group", "instructor")
            .order_by("subject__code")
        )
        if (period is not None and group is not None)
        else []
    )
    section["rooms"] = _rooms(organization)
    section["weekdays"] = schedule_service.WEEKDAYS
    section["standard_times"] = schedule_service.STANDARD_LESSON_TIMES

    from apps.registrar.models import SlotKind, WeekType

    section["week_types"] = WeekType.choices
    section["slot_kinds"] = SlotKind.choices
    # Həftə naviqasiyası (ÖNCƏKİ/NÖVBƏTİ həftə) cari seçimi İTİRMƏMƏLİDİR —
    # `?w=` prefiksinə bütün aktiv filtrlər yapışdırılır.
    from urllib.parse import urlencode

    nav_params = {
        key: value
        for key, value in (
            ("section", "schedule-manage"),
            ("sm_year", section.get("selected_year") or ""),
            ("sm_period", str(period.id) if period is not None else ""),
            ("sm_view", view_mode),
            ("sm_group", str(group.id) if group is not None else ""),
            ("sm_teacher", str(teacher.pk) if teacher is not None else ""),
        )
        if value
    }
    section["week_nav_prefix"] = "%s?%s&" % (reverse("accounts:profile"), urlencode(nav_params))
    section["owner_label"] = (
        _person_name(teacher) if (view_mode == "teacher" and teacher is not None) else getattr(group, "name", "")
    )
    _grid(section, request, organization, period, slots)


__all__ = ["build_schedule_manage_section"]
