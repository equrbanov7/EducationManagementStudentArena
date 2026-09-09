"""Profil «schedule-manage» bölməsi — həftəlik cədvəl REDAKTORU.

Bölmə profil shell-inin İÇİNDƏ açılır və SERVER-RENDER-lidir: filtr paneli
(tədris ili / semestr / görünüş / qrup) fraqmenti avtomatik yenidən yükləyir
(`ems_ui/_filter_bar.html`, `filter_auto`), interaktiv əməllər isə TƏK JSON
giriş nöqtəsinə gedir (`accounts:schedule_editor_action`).

──────────────────────────────────────────────────────────────────────────────
ƏSAS QAYDA (sahib, 2026-09-09): CƏDVƏL HƏMİŞƏ GÖRÜNÜR
──────────────────────────────────────────────────────────────────────────────
Matris sətirləri MÖVCUD slotlardan yox, təşkilatın nömrələnmiş dərs
saatlarından qurulur (`registrar.schedule_grid`) — slot sıfır olsa da grid tam
render olunur və hər boş hüceyrə «klik → slot yarat» hədəfidir.

CONTEXT MÜQAVİLƏSİ (`schedule_manage_section`; UI buna söykənir)
    has_access / state_title / state_body / scope_label / header_subtitle
    kpi_tiles              — `ems_ui/_kpi_row.html`
    filters                — `ems_ui/_filter_bar.html` (fields/applied/prefix)
    period / group / view_mode / teacher
    matrix                 — `registrar/partials/_schedule_matrix.html`
    week / week_nav_prefix — üst/alt həftə pilləri
    parked                 — «yenidən yerləşdirilməli» slot sətirləri
    subjects / teachers / rooms / week_types / slot_kinds / weekdays / shifts
    lesson_periods         — dialoqun «Dərs saatı» seçicisi
    editor_url / reload_url
"""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import schedule as schedule_service
from apps.registrar import schedule_conflicts, schedule_editor
from apps.registrar import schedule_editor_actions as editor
from apps.registrar import schedule_grid, schedule_manage

from .kollokvium_windows import _current_semester, _season_label

_CTX = "accounts.schedule_manage"
PREFIX = "sm_"

#: Auditoriya təklifləri (`exams.ExamRoom` kataloqu) — məcburi seçim DEYİL.
_ROOM_SUGGESTION_LIMIT = 200


def _person_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def _endpoints(section):
    section["editor_url"] = reverse("accounts:schedule_editor_action")
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
    requested_year = (request.GET.get(PREFIX + "year") or "").strip()
    selected_year = requested_year if requested_year in seen else None
    if selected_year is None and default_period is not None:
        selected_year = default_period.year_display
    if selected_year is None and years:
        selected_year = years[0]

    periods_in_year = [p for p in all_periods if p.year_display == selected_year]
    requested_period = (request.GET.get(PREFIX + "period") or "").strip()
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
    try:
        from apps.exams.models import ExamRoom
    except Exception:  # pragma: no cover — imtahan modulu söndürülübsə
        return []
    return list(
        ExamRoom.objects.filter(organization=organization, is_active=True)
        .order_by("name")
        .values_list("name", flat=True)[:_ROOM_SUGGESTION_LIMIT]
    )


def _teachers_in_scope(offerings_qs):
    """Əhatədəki açılışların müəllimləri (müəllim görünüşü seçicisi üçün)."""
    rows = {}
    for offering in offerings_qs.select_related("instructor").exclude(instructor__isnull=True):
        rows.setdefault(str(offering.instructor_id), _person_name(offering.instructor))
    return [{"id": key, "name": name} for key, name in sorted(rows.items(), key=lambda item: item[1])]


def _filter_fields(section, *, groups, teachers, view_mode, group, teacher):
    """`ems_ui/_filter_bar.html` sahələri — avto rejim (Tətbiq düyməsi yoxdur)."""
    fields = [
        {
            "name": PREFIX + "year",
            "label": pgettext(_CTX, "Tədris ili"),
            "kind": "select",
            "value": section.get("selected_year") or "",
            "options": [{"value": year, "label": year} for year in section.get("years") or []],
        },
        {
            "name": PREFIX + "period",
            "label": pgettext(_CTX, "Semestr"),
            "kind": "select",
            "value": str(section["period"].id) if section.get("period") else "",
            "options": [{"value": str(row.id), "label": row.season_label} for row in section.get("periods") or []],
        },
        {
            "name": PREFIX + "view",
            "label": pgettext(_CTX, "Görünüş"),
            "kind": "select",
            "value": view_mode,
            "default": "group",
            "options": [
                {"value": "group", "label": pgettext(_CTX, "Qrup cədvəli")},
                {"value": "teacher", "label": pgettext(_CTX, "Müəllim cədvəli")},
            ],
        },
    ]
    if view_mode == "teacher":
        fields.append(
            {
                "name": PREFIX + "teacher",
                "label": pgettext(_CTX, "Müəllim"),
                "kind": "select",
                "value": str(teacher.pk) if teacher is not None else "",
                "default": "",
                "searchable": True,
                "options": [{"value": "", "label": pgettext(_CTX, "Seçin…")}]
                + [{"value": row["id"], "label": row["name"]} for row in teachers],
            }
        )
    else:
        fields.append(
            {
                "name": PREFIX + "group",
                "label": pgettext(_CTX, "Qrup"),
                "kind": "select",
                "value": str(group.id) if group is not None else "",
                "searchable": True,
                "options": [{"value": str(row["id"]), "label": row["name"]} for row in groups],
            }
        )
    return {"fields": fields, "applied": [], "section": "schedule-manage", "prefix": PREFIX}


def _kpi_tiles(*, slots, parked, matrix, subjects):
    free_cells = sum(1 for row in matrix["rows"] for cell in row["cells"] if cell["is_empty"])
    return [
        {"label": pgettext(_CTX, "CƏDVƏLDƏ DƏRS"), "value": len(slots), "tone": "accent-primary"},
        {"label": pgettext(_CTX, "BOŞ XANA"), "value": free_cells},
        {
            "label": pgettext(_CTX, "YENİDƏN YERLƏŞDİRİLMƏLİ"),
            "value": len(parked),
            "tone": "accent-warning" if parked else None,
        },
        {"label": pgettext(_CTX, "PLANDAKI FƏNN"), "value": len(subjects)},
    ]


def _week(section, request, period):
    try:
        offset = max(-8, min(16, int(request.GET.get("w") or 0)))
    except (TypeError, ValueError):
        offset = 0
    section["week"] = schedule_service.build_week_context(period, offset=offset)
    return section["week"]


def _nav_prefix(*, period, view_mode, group, teacher, selected_year):
    params = {
        key: value
        for key, value in (
            ("section", "schedule-manage"),
            (PREFIX + "year", selected_year or ""),
            (PREFIX + "period", str(period.id) if period is not None else ""),
            (PREFIX + "view", view_mode),
            (PREFIX + "group", str(group.id) if group is not None else ""),
            (PREFIX + "teacher", str(teacher.pk) if teacher is not None else ""),
        )
        if value
    }
    return "%s?%s&" % (reverse("accounts:profile"), urlencode(params))


def _selection(section, request, organization, period):
    """Qrup / müəllim seçimi — YALNIZ aktorun əhatəsindən (fail-closed)."""
    from apps.organizations.models import OrgUnit

    groups = list(schedule_manage.scoped_groups(request.user, organization).values("id", "name"))
    section["groups"] = groups
    requested = (request.GET.get(PREFIX + "group") or "").strip()
    group = None
    if groups:
        known = {str(row["id"]) for row in groups}
        chosen = requested if requested in known else str(groups[0]["id"])
        group = OrgUnit.objects.filter(pk=chosen).first()
    section["group"] = group

    scoped = schedule_manage.scoped_offerings(request.user, organization, period=period)
    teachers = _teachers_in_scope(scoped)
    section["scope_teachers"] = teachers

    view_mode = "teacher" if (request.GET.get(PREFIX + "view") or "").strip() == "teacher" else "group"
    section["view_mode"] = view_mode
    teacher = None
    if view_mode == "teacher":
        requested_teacher = (request.GET.get(PREFIX + "teacher") or "").strip()
        if requested_teacher in {row["id"] for row in teachers}:
            from django.contrib.auth import get_user_model

            teacher = get_user_model().objects.filter(pk=requested_teacher).first()
    section["teacher"] = teacher
    return group, teacher, view_mode, teachers


def build_schedule_manage_section(request, section, *, active_organization, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir (handover/kollokvium naxışı)."""
    if "schedule-manage" not in allowed_sections or active_section != "schedule-manage":
        return

    _endpoints(section)
    section["state_title"] = pgettext(_CTX, "Bu bölmə sizin üçün bağlıdır")
    section["state_body"] = pgettext(
        _CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür."
    )
    section["access_denied_message"] = section["state_body"]
    has_access = bool(active_organization is not None and schedule_manage.can_manage(request.user, active_organization))
    section["has_access"] = has_access
    if not has_access:
        return

    organization = active_organization
    scope = schedule_manage.actor_scope(request.user, organization)
    org_wide = scope.is_org_wide or request.user.is_superuser or organization.owner_id == request.user.pk
    section["scope_label"] = (
        pgettext(_CTX, "Bütün universitet") if org_wide else pgettext(_CTX, "Yalnız öz struktur bölmələriniz")
    )
    section["header_subtitle"] = pgettext(
        _CTX,
        "Qrupu seçin, boş xanaya klikləyib dərs qoyun, dərsi sürüşdürüb yerini dəyişin. "
        "Toqquşmalar saxlamadan əvvəl göstərilir; hər dəyişiklik müəllimə və qrupun tələbələrinə bildiriş kimi gedir.",
    )

    period = _periods(section, request, organization)
    group, teacher, view_mode, teachers = _selection(section, request, organization, period)
    section["filters"] = _filter_fields(
        section, groups=section["groups"], teachers=teachers, view_mode=view_mode, group=group, teacher=teacher
    )

    slots = []
    if period is not None:
        if view_mode == "teacher" and teacher is not None:
            slots = schedule_service.get_teacher_schedule(organization=organization, teacher=teacher, period=period)
        elif group is not None:
            slots = schedule_service.get_group_schedule(organization=organization, group=group, period=period)
    section["slots"] = slots

    week_context = _week(section, request, period)
    section["matrix"] = schedule_grid.build_matrix(slots=slots, organization=organization, week_context=week_context)
    # Parklanmış dərslər SEÇİLMİŞ QRUPLA məhdudlaşmır: məcburi dəyişiklikdə
    # yerindən çıxan dərs adətən BAŞQA qrupundur və dərhal görünməlidir.
    # Əhatə isə fail-closed — yalnız aktorun `schedule.manage` alt-ağacı.
    section["parked"] = (
        editor.parked_rows(organization=organization, period=period, actor=request.user) if period is not None else []
    )
    section["subjects"] = schedule_editor.allowed_subjects(organization=organization, group=group, period=period)
    section["teachers"] = schedule_editor.teacher_choices(organization)
    section["rooms"] = _rooms(organization)
    section["lesson_periods"] = schedule_grid.lesson_periods(organization)
    section["shifts"] = [
        {"value": key, "label": str(label)}
        for key, label in (
            (schedule_grid.SHIFT_MORNING, schedule_grid.SHIFT_LABELS[schedule_grid.SHIFT_MORNING]),
            (schedule_grid.SHIFT_AFTERNOON, schedule_grid.SHIFT_LABELS[schedule_grid.SHIFT_AFTERNOON]),
            (schedule_grid.SHIFT_EVENING, schedule_grid.SHIFT_LABELS[schedule_grid.SHIFT_EVENING]),
        )
    ]
    section["kpi_tiles"] = _kpi_tiles(
        slots=slots, parked=section["parked"], matrix=section["matrix"], subjects=section["subjects"]
    )

    from apps.registrar.models import SlotKind, WeekType

    section["week_types"] = WeekType.choices
    section["slot_kinds"] = SlotKind.choices
    section["weekdays"] = schedule_grid.TEACHING_WEEKDAYS
    section["conflict_kinds"] = schedule_conflicts.KIND_ORDER
    section["week_nav_prefix"] = _nav_prefix(
        period=period,
        view_mode=view_mode,
        group=group,
        teacher=teacher,
        selected_year=section.get("selected_year"),
    )
    section["owner_label"] = (
        _person_name(teacher) if (view_mode == "teacher" and teacher is not None) else getattr(group, "name", "")
    )
    section["can_edit"] = view_mode == "group" and group is not None and period is not None
    _dialog_labels(section)


def _dialog_labels(section):
    """Dialoq/çekmecə başlıqları — şablonda literal yazılmasın deyə kontekstdə."""
    section["dialog_title"] = pgettext(_CTX, "Xanaya dərs qoy")
    section["dialog_subtitle"] = pgettext(
        _CTX, "Müəllim, fənn, dərs növü və həftə seçin; otaq opsionaldır. Toqquşma varsa saxlamadan əvvəl göstərilir."
    )
    section["dialog_submit_label"] = pgettext(_CTX, "Cədvələ yaz")
    section["dialog_data"] = {"data-sedit-form": "1"}
    section["move_title"] = pgettext(_CTX, "Dərsin yerini dəyişmək")
    section["parked_title"] = pgettext(_CTX, "Yenidən yerləşdirilməli dərslər")
    section["parked_subtitle"] = pgettext(
        _CTX, "Məcburi dəyişiklik zamanı yerindən çıxarılan dərslər silinmir — buradan yeni xanaya qoyulur."
    )


__all__ = ["PREFIX", "build_schedule_manage_section"]
