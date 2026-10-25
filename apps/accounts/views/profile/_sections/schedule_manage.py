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
    subjects / teachers / week_types / slot_kinds / weekdays / shifts
    rooms / room_buildings / room_default_building — dialoqun «Korpus → Otaq» seçiciləri
    lesson_periods         — dialoqun «Dərs saatı» seçicisi
    editor_url / reload_url
"""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import schedule as schedule_service
from apps.registrar.public import schedule_conflicts, schedule_editor
from apps.registrar.public import schedule_editor_actions as editor
from apps.registrar.public import schedule_grid, schedule_manage, schedule_rooms

from .kollokvium_windows import _current_semester, _season_label

_CTX = "accounts.schedule_manage"
PREFIX = "sm_"


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


def _teachers_in_scope(offerings_qs, *, organization=None, period=None, assignments=None):
    """Seçilmiş dövrdə AKTİV müəllimlər (müəllim görünüşü seçicisi; sahib 2026-10-25).

    Dövrün bölgüsü / jurnal sahibi / dərsi / slotu olan müəllimlər; cari dövrdə əlavə olaraq aktiv hesab +
    aktiv müəllim üzvlüyü, bitmiş dövrdə o vaxt dərs deyən hər kəs. 2026-09-25 (bölünmüş tədris): seminarı
    aparan assistentin öz açılışı olmaya bilər — o da siyahıdadır. Hesab registrar-dadır (``schedule_teachers``)."""
    return schedule_manage.scoped_teacher_rows(
        offerings_qs, organization=organization, period=period, assignments=assignments
    )


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


def _selection(section, request, organization, period, *, permission):
    """Qrup / müəllim seçimi — YALNIZ aktorun ``permission`` əhatəsindən (fail-closed)."""
    from apps.organizations.models import OrgUnit

    # Redaktorun OXU görünüşü genişlənmiş əhatədir (kafedra fənni olan qruplar, FIX-D 2026-10-17).
    groups = list(
        schedule_manage.scoped_groups(request.user, organization, permission=permission, widened=True).values(
            "id", "name"
        )
    )
    section["groups"] = groups
    requested = (request.GET.get(PREFIX + "group") or "").strip()
    group = None
    if groups:
        known = {str(row["id"]) for row in groups}
        chosen = requested if requested in known else str(groups[0]["id"])
        group = OrgUnit.objects.filter(pk=chosen).first()
    section["group"] = group

    scoped = schedule_manage.scoped_offerings(
        request.user, organization, period=period, permission=permission, widened=True
    )
    assignments = schedule_manage.scoped_assignments(
        request.user, organization, period=period, permission=permission, widened=True
    )
    teachers = _teachers_in_scope(scoped, organization=organization, period=period, assignments=assignments)
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
    # 2026-10-13 (rol auditi B11): `schedule.view` daşıyan (prorektor, Tədris şöbəsi, RİM əməkdaşı…)
    # bölməni YALNIZ-OXU görür — matris kartları detal rejimindədir, yaratma/redaktə/köçürmə/park
    # idarələri və dialoqlar render OLUNMUR. Yazı endpoint-ləri `schedule.manage`-i ayrıca yoxlayır.
    can_manage = bool(active_organization is not None and schedule_manage.can_manage(request.user, active_organization))
    has_access = can_manage or bool(
        active_organization is not None and schedule_manage.can_view(request.user, active_organization)
    )
    section["has_access"] = has_access
    section["read_only"] = not can_manage
    if not has_access:
        return

    organization = active_organization
    permission = schedule_manage.SCHEDULE_PERMISSION if can_manage else schedule_manage.SCHEDULE_VIEW_PERMISSION
    scope = schedule_manage.actor_scope(request.user, organization, permission)
    org_wide = scope.is_org_wide or request.user.is_superuser or organization.owner_id == request.user.pk
    section["scope_label"] = (
        pgettext(_CTX, "Bütün universitet") if org_wide else pgettext(_CTX, "Yalnız öz struktur bölmələriniz")
    )
    section["header_subtitle"] = (
        pgettext(
            _CTX,
            "Qrupu seçin, boş xanaya klikləyib dərs qoyun, dərsi sürüşdürüb yerini dəyişin. "
            "Toqquşmalar saxlamadan əvvəl göstərilir; hər dəyişiklik müəllimə və qrupun tələbələrinə bildiriş kimi gedir.",
        )
        if can_manage
        else pgettext(_CTX, "Cədvələ yalnız baxış icazəniz var — qrup və ya müəllim seçib həftəlik cədvələ baxın.")
    )

    period = _periods(section, request, organization)
    group, teacher, view_mode, teachers = _selection(section, request, organization, period, permission=permission)
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
        editor.parked_rows(organization=organization, period=period, actor=request.user)
        if (period is not None and can_manage)
        else []
    )
    # Müəllim görünüşündə dialoqun ilk fənn siyahısı MÜƏLLİMİN fənləridir (qrup dialoqda seçilir;
    # seçiləndə siyahı `action=options` ilə qrup + müəllimə görə yenilənir).
    section["subjects"] = (
        schedule_editor.allowed_subjects(organization=organization, group=None, period=period, instructor=teacher)
        if view_mode == "teacher" and teacher is not None
        else schedule_editor.allowed_subjects(organization=organization, group=group, period=period)
    )
    section["teachers"] = schedule_editor.teacher_choices(organization)
    # «Korpus → Otaq» seçiciləri (2026-10-17): otaqlar korpusu + tutumu ilə; yeni xanada korpus qrupun
    # ixtisas korpusudur (`default_building`), redaktədə kartın otağının korpusu (JS).
    catalog = schedule_rooms.dialog_rooms(organization, group if view_mode == "group" else None)
    section["rooms"] = catalog["rooms"]
    section["room_buildings"] = catalog["buildings"]
    section["room_default_building"] = catalog["default_building"]
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
    # 2026-10-14 (sahib: «müəllim seçiləndə də yerini dəyişmək olmalıdır»): müəllim görünüşü də
    # REDAKTORDUR — yalnız `schedule.manage` daşıyana; hər kartın redaktəsi ayrıca öz qrupunun
    # əhatəsinə bağlıdır (müəllimin başqa fakültədəki dərsi detal modalında açılır, sürüklənmir).
    owner_ready = (group is not None) if view_mode == "group" else (teacher is not None)
    section["can_edit"] = bool(can_manage and period is not None and owner_ready)
    section["teacher_pick_needed"] = view_mode == "teacher" and teacher is None
    _mark_editable(section["matrix"], {str(row["id"]) for row in section["groups"]}, enabled=section["can_edit"])
    _dialog_labels(section)


def _mark_editable(matrix, group_ids, *, enabled):
    """Hər matris elementinə ``editable`` — redaktor yalnız ÖZ əhatəsindəki qrupun dərsini dəyişir.

    Müəllim görünüşündə müəllimin başqa fakültə/kafedradakı dərsi də görünür; o kart detal
    modalında açılır (``data-sgx-slot``), sürüklənmir. Server bunu ayrıca yoxlayır
    (``can_manage_offering``) — bu, yalnız UI-nın düzgün idarə göstərməsi üçündür."""
    for rows in (matrix.get("rows") or [], matrix.get("extra_rows") or []):
        for row in rows:
            for cell in row["cells"]:
                for item in cell["items"]:
                    item["editable"] = bool(enabled and str(item["slot"].offering.group_id) in group_ids)


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
