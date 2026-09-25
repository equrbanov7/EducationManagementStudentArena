"""Profil «exam-score-entry» bölməsi — İmtahan Mərkəzi: yazılı imtahan ballarının köçürülməsi.

``section`` dict-ini YERİNDƏ mutasiya edir (``journal_close`` pattern-i).
Superadmin cross-org (təşkilat seçici); imtahan mərkəzi istifadəçisi yalnız
aktiv təşkilatı görür.

Axın (2026-09-12, sahibin tələbi «qrup seçilsin, müəllim, tarix və s.»):
tədris ili → semestr → **QRUP** → fənn (qrupun açılışları, müəllim adı ilə) →
tələbə siyahısı. Köhnə fənn-əvvəl sıra (``ese_mode=subject``) saxlanılır —
hər iki sıra eyni açılışa çıxır; qrup-əvvəl DEFOLTDUR.

Seçicilər ``ems_ui/_filter_bar`` (avto rejim) ilə render olunur: dəyişiklik
paneli SPA ilə yenidən yükləyir, server isə kaskadı tolerant həll edir
(il dəyişəndə semestr defolta düşür, qrup dəyişəndə açılış birinciyə).

2026-09-14 (W2 `w2paper`, sahib: «filter, search, müəllim seçmək və s. — hər
şey orada; dəyişən nəticələrin izlənməsi»): ``ese_teacher`` (müəllim seçici),
``ese_q`` (tələbə axtarışı), ``ese_status`` (hamısı · boş · yazılıb ·
dəyişdirilib çipləri) — hamısı YADDAŞDA süzülür, sorğu büdcəsi siyahı
ölçüsündən asılı deyil; ``ese_view=changes`` — «Dəyişən nəticələr»
alt-görünüşü (``exam_score_changes`` qardaş modulu). Sual şəbəkəsi
(``question_count`` / ``question_max``) vərəq kartındadır, defoltu sonuncu
vərəqdən gəlir; siyahı hər tələbə üçün S1..S10 sahəsi render edir, JS sual
sayından artıq olanları söndürür.
"""

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

from .exam_score_entry_lock import fill_period_lock
from .exam_score_entry_offering import _fill_offering, _steps
from .kollokvium_windows import _current_semester, _season_label

SECTION = "exam-score-entry"
_CTX = "registrar.exam_score_entry"

MODE_GROUP = "group"
MODE_SUBJECT = "subject"

VIEW_ENTRY = "entry"
VIEW_CHANGES = "changes"


def _selected_org(request, *, is_superadmin, active_organization):
    from apps.organizations.models import Organization

    if not is_superadmin:
        return [], active_organization
    org_options = list(Organization.objects.filter(is_active=True).order_by("name").values("id", "name"))
    requested = (request.GET.get("ese_org") or "").strip()
    selected = Organization.objects.filter(pk=requested).first() if requested else None
    if selected is None and org_options:
        selected = Organization.objects.filter(pk=org_options[0]["id"]).first()
    return org_options, selected


def _resolve_period(request, all_periods, today):
    """Tədris ili + semestr seçimi — jurnal bağlama bölməsi ilə eyni heuristika."""
    years, seen = [], set()
    for period in all_periods:
        label = period.year_display
        if label and label not in seen:
            seen.add(label)
            years.append(label)

    default_period = _current_semester(all_periods, today)
    requested_year = (request.GET.get("ese_year") or "").strip()
    selected_year = requested_year if requested_year in seen else None
    if selected_year is None and default_period is not None:
        selected_year = default_period.year_display
    if selected_year is None and years:
        selected_year = years[0]

    periods_in_year = [p for p in all_periods if p.year_display == selected_year]
    # ``ese_period`` — filtr paneli; köhnə ``period`` parametri geriyə uyğunluq üçün oxunur.
    requested_period = (request.GET.get("ese_period") or request.GET.get("period") or "").strip()
    period = next((p for p in periods_in_year if str(p.id) == requested_period), None)
    if period is None and default_period is not None and default_period.year_display == selected_year:
        period = default_period
    if period is None and periods_in_year:
        period = periods_in_year[0]
    return years, selected_year, periods_in_year, period


def _resolve_subject(request, subjects):
    requested = (request.GET.get("ese_subject") or "").strip()
    ids = {row["id"] for row in subjects}
    if requested in ids:
        return requested
    return subjects[0]["id"] if subjects else ""


def _resolve_group(request, groups):
    requested = (request.GET.get("ese_group") or "").strip()
    ids = {row["id"] for row in groups}
    if requested in ids:
        return requested
    return groups[0]["id"] if groups else ""


def _resolve_offering(request, offerings):
    requested = (request.GET.get("ese_offering") or "").strip()
    match = next((o for o in offerings if str(o.id) == requested), None)
    if match is not None:
        return match
    return offerings[0] if offerings else None


def _resolve_mode(request) -> str:
    return MODE_SUBJECT if (request.GET.get("ese_mode") or "").strip() == MODE_SUBJECT else MODE_GROUP


def _resolve_view(request) -> str:
    return VIEW_CHANGES if (request.GET.get("ese_view") or "").strip() == VIEW_CHANGES else VIEW_ENTRY


def _resolve_teacher(request, instructors) -> str:
    requested = (request.GET.get("ese_teacher") or "").strip()
    return requested if requested in {row["id"] for row in instructors} else ""


def _teacher_field(instructors, selected):
    """Müəllim seçici — «Hamısı» + dövrün müəllimləri (menyu içi axtarış)."""
    return _select_field(
        "ese_teacher",
        pgettext(_CTX, "Müəllim"),
        [{"value": "", "label": pgettext(_CTX, "Bütün müəllimlər")}]
        + [{"value": row["id"], "label": row["name"]} for row in instructors],
        selected,
        searchable=len(instructors) > 8,
    )


def _scope_group_ids(user, organization, service):
    """Unit-scoped aktorun görə bildiyi qrup id-ləri (``None`` = org-wide, hamısı)."""
    from apps.registrar.public import journal_scope

    scope = journal_scope.permission_scope_for(user, organization, service.ENTRY_PERMISSION)
    if not scope.has_structure_access:
        return set()
    if scope.is_org_wide:
        return None
    from apps.organizations.models import OrgUnit

    return {
        str(pk)
        for pk in OrgUnit.objects.filter(organization=organization)
        .filter(scope.unit_subtree_q())
        .values_list("pk", flat=True)
    }


def _select_field(name, label, options, value, *, searchable=False, wide=False):
    return {
        "name": name,
        "label": label,
        "kind": "select",
        "options": options,
        "value": value,
        "searchable": searchable,
        "wide": wide,
    }


def build_exam_score_entry_section(
    request, section, *, is_superadmin, active_organization, allowed_sections, active_section
):
    if SECTION not in allowed_sections or active_section != SECTION:
        return

    from apps.organizations.models import AcademicPeriod
    from apps.registrar.models import CorrectionReason, ExamScoreEntryKind
    from apps.registrar.public import exam_score_entry as service
    from apps.registrar.public import exam_score_sheets as sheets_service

    org_options, selected_org = _selected_org(
        request, is_superadmin=is_superadmin, active_organization=active_organization
    )
    mode = _resolve_mode(request)
    view = _resolve_view(request)
    section["is_superadmin"] = is_superadmin
    section["org_options"] = org_options
    section["selected_org"] = selected_org
    section["mode"] = mode
    section["is_group_mode"] = mode == MODE_GROUP
    section["view"] = view
    section["is_changes_view"] = view == VIEW_CHANGES
    section["reasons"] = [{"value": value, "label": str(label)} for value, label in CorrectionReason.choices]
    section["change_kinds"] = [
        {"value": value, "label": str(label)}
        for value, label in ExamScoreEntryKind.choices
        if value in ExamScoreEntryKind.change_kinds()
    ]
    section["question_count_max"] = service.exam_score_questions.QUESTION_COUNT_MAX
    section["question_labels"] = service.exam_score_questions.question_labels(
        service.exam_score_questions.QUESTION_COUNT_MAX
    )
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section=SECTION)
    section["saved_flag"] = (request.GET.get("ese_saved") or "").strip() == "1"
    section["filter_fields"] = []
    section["steps"] = _steps(offering=None, saved=False)
    section["groups"] = []
    section["selected_group_id"] = ""
    section["sheets"] = []
    section["sheet_defaults"] = sheets_service.latest_sheet_defaults([])
    section["import_columns"] = []

    if selected_org is None:
        return

    filter_fields = []
    if is_superadmin:
        filter_fields.append(
            _select_field(
                "ese_org",
                pgettext(_CTX, "Təşkilat"),
                [{"value": str(o["id"]), "label": o["name"]} for o in org_options],
                str(selected_org.pk),
                searchable=len(org_options) > 8,
            )
        )

    today = timezone.localdate()
    all_periods = list(AcademicPeriod.objects.filter(organization=selected_org).order_by("-start_date"))
    for period in all_periods:
        period.season_label = _season_label(period)
    years, selected_year, periods_in_year, period = _resolve_period(request, all_periods, today)

    section["years"] = years
    section["selected_year"] = selected_year
    section["periods"] = periods_in_year
    section["period"] = period
    filter_fields.append(
        _select_field(
            "ese_year", pgettext(_CTX, "Tədris ili"), [{"value": y, "label": y} for y in years], selected_year or ""
        )
    )
    filter_fields.append(
        _select_field(
            "ese_period",
            pgettext(_CTX, "Semestr"),
            [{"value": str(p.id), "label": f"{p.season_label} — {p.name}"} for p in periods_in_year],
            str(period.id) if period is not None else "",
        )
    )
    section["filter_fields"] = filter_fields
    if period is None:
        return

    base_params = {
        **({"ese_org": str(selected_org.pk)} if is_superadmin else {}),
        **({"ese_year": selected_year} if selected_year else {}),
        "ese_period": str(period.id),
    }
    section["mode_group_url"] = _append_query_params(
        reverse("accounts:profile"), section=SECTION, ese_mode=MODE_GROUP, **base_params
    )
    section["mode_subject_url"] = _append_query_params(
        reverse("accounts:profile"), section=SECTION, ese_mode=MODE_SUBJECT, **base_params
    )
    section["view_entry_url"] = _append_query_params(
        reverse("accounts:profile"), section=SECTION, ese_mode=mode, **base_params
    )
    section["view_changes_url"] = _append_query_params(
        reverse("accounts:profile"), section=SECTION, ese_mode=mode, ese_view=VIEW_CHANGES, **base_params
    )

    # Unit-scoped aktor (dekan/kafedra müdiri `exam.*` ilə) yalnız öz
    # alt-ağacının qruplarını görür — yazı qapısı ilə eyni əhatə.
    allowed_group_ids = None if is_superadmin else _scope_group_ids(request.user, selected_org, service)

    if view == VIEW_CHANGES:
        from .exam_score_changes import build_changes_view

        build_changes_view(
            request,
            section,
            filter_fields,
            service=service,
            sheets_service=sheets_service,
            organization=selected_org,
            period=period,
            base_params={"ese_mode": mode, **base_params},
            allowed_group_ids=allowed_group_ids,
            is_superadmin=is_superadmin,
        )
        return

    instructors = service.instructors_for_period(organization=selected_org, period=period, group_ids=allowed_group_ids)
    teacher_id = _resolve_teacher(request, instructors)
    section["selected_teacher_id"] = teacher_id
    filter_fields.append(_teacher_field(instructors, teacher_id))
    selection = _Selection(allowed_group_ids=allowed_group_ids, teacher_id=teacher_id)

    if mode == MODE_GROUP:
        offering, extra_params = _group_first(
            request, section, filter_fields, service, sheets_service, selected_org, period, selection
        )
    else:
        offering, extra_params = _subject_first(
            request, section, filter_fields, service, selected_org, period, selection
        )
    section["offering"] = offering
    roster_params = {"ese_mode": mode, **base_params, **extra_params}
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section=SECTION, **roster_params)
    if offering is None:
        return

    sheet_kind = _resolve_exam_kind(request, "ese_sheet_kind")
    _fill_offering(section, offering, period, service, sheets_service, selected_org, is_superadmin, sheet_kind)
    fill_period_lock(  # bitmiş dövr kilidi + RİM düzəliş rejimi (2026-09-26)
        request, section, period=period, organization=selected_org, service=service, is_superadmin=is_superadmin
    )
    if section["correction_mode"]:  # çiplər / süzgəc keçidləri rejimi saxlasın
        roster_params[service.exam_score_period_lock.CORRECTION_MODE_QUERY] = "1"
    _apply_roster_filters(request, section, filter_fields, service, roster_params)
    section["sheet_kind_chips"] = _exam_kind_chips(
        service,
        sheet_kind,
        "ese_sheet_kind",
        {**roster_params, "ese_q": section["roster_search"], "ese_status": section["roster_status"]},
    )


def _resolve_exam_kind(request, name) -> str:
    from apps.registrar.models.exam_score_entry import ExamScoreSheetKind

    requested = (request.GET.get(name) or "").strip()
    return requested if requested in ExamScoreSheetKind.values else ""


def _exam_kind_chips(service, current, name, params) -> list:
    """Yazılı / Praktiki / Hamısı çipləri (addendum 2026-09-14) — SPA linkləri."""
    return [
        {
            "key": option["value"],
            "label": option["label"],
            "current": option["value"] == current,
            "url": _append_query_params(
                reverse("accounts:profile"), section=SECTION, **params, **{name: option["value"]}
            ),
        }
        for option in service.exam_score_changes.exam_kind_options()
    ]


class _Selection:
    """Seçim kontekstinin daşıyıcısı — əhatə (qrup id-ləri) + müəllim filtri."""

    def __init__(self, *, allowed_group_ids, teacher_id):
        self.allowed_group_ids = allowed_group_ids
        self.teacher_id = teacher_id

    def offerings(self, offerings):
        """Açılışları əhatə + müəllim filtri ilə süz (yaddaşda)."""
        result = list(offerings)
        if self.allowed_group_ids is not None:
            result = [o for o in result if str(getattr(o, "group_id", "")) in self.allowed_group_ids]
        if self.teacher_id:
            result = [o for o in result if str(getattr(o, "instructor_id", "")) == self.teacher_id]
        return result

    def groups(self, groups, group_ids_with_teacher=None):
        result = list(groups)
        if self.allowed_group_ids is not None:
            result = [g for g in result if g["id"] in self.allowed_group_ids]
        if group_ids_with_teacher is not None:
            result = [g for g in result if g["id"] in group_ids_with_teacher]
        return result


def _apply_roster_filters(request, section, filter_fields, service, roster_params):
    """Tələbə axtarışı + vəziyyət çipləri — siyahı YADDAŞDA süzülür (sorğu yoxdur).

    KPI kartları süzülməmiş siyahını sayır; cədvəl süzülmüş sətirləri göstərir.
    Göstərilməyən sətir formada da yoxdur → POST ona toxunmur.
    """
    search = (request.GET.get("ese_q") or "").strip()[:100]
    status = (request.GET.get("ese_status") or "").strip()
    status = status if status in service.STATUS_CHOICES else service.STATUS_ALL
    all_rows = section["rows"]
    section["rows"] = service.filter_roster_rows(all_rows, search=search, status=status)
    section["roster_search"] = search
    section["roster_status"] = status
    section["roster_total"] = len(all_rows)
    section["roster_shown"] = len(section["rows"])
    counts = service.status_counts(all_rows)
    labels = {
        service.STATUS_ALL: pgettext(_CTX, "hamısı"),
        service.STATUS_EMPTY: pgettext(_CTX, "boş"),
        service.STATUS_RECORDED: pgettext(_CTX, "yazılıb"),
        service.STATUS_CHANGED: pgettext(_CTX, "dəyişdirilib"),
    }
    section["status_chips"] = [
        {
            "key": key,
            "label": labels[key],
            "count": counts[key],
            "current": key == status,
            "url": _append_query_params(
                reverse("accounts:profile"),
                section=SECTION,
                **roster_params,
                ese_q=search,
                ese_status="" if key == service.STATUS_ALL else key,
                ese_sheet_kind=_resolve_exam_kind(request, "ese_sheet_kind"),
            ),
        }
        for key in service.STATUS_CHOICES
    ]
    filter_fields.append(
        {
            "name": "ese_q",
            "label": pgettext(_CTX, "Tələbə axtarışı"),
            "kind": "search",
            "value": search,
            "placeholder": pgettext(_CTX, "ad · istifadəçi adı · FİN · tələbə №"),
        }
    )


def _group_first(request, section, filter_fields, service, sheets_service, selected_org, period, selection):
    """Qrup → fənn (qrupun açılışları). Unit-scoped aktor yalnız öz alt-ağacının qruplarını görür.

    Müəllim seçilibsə qrup siyahısı həmin müəllimin açılışı olan qruplara daralır
    (BİR sorğu), fənn siyahısı isə yalnız onun açılışlarını göstərir.
    """
    groups = sheets_service.groups_for_period(organization=selected_org, period=period)
    group_ids_with_teacher = None
    if selection.teacher_id:
        group_ids_with_teacher = service.group_ids_for_instructor(
            organization=selected_org, period=period, instructor_id=selection.teacher_id
        )
    groups = selection.groups(groups, group_ids_with_teacher)
    selected_group_id = _resolve_group(request, groups)
    section["groups"] = groups
    section["selected_group_id"] = selected_group_id
    filter_fields.append(
        _select_field(
            "ese_group",
            pgettext(_CTX, "Qrup"),
            [{"value": g["id"], "label": g["name"]} for g in groups],
            selected_group_id,
            searchable=True,
        )
    )
    offerings = selection.offerings(
        sheets_service.offerings_for_group(organization=selected_org, period=period, group_id=selected_group_id)
    )
    for offering in offerings:
        offering.group_label = service.offering_label(offering)
        offering.subject_label = sheets_service.subject_label(offering)
        offering.instructor_label = sheets_service.instructor_label(offering)
    offering = _resolve_offering(request, offerings)
    section["offerings"] = offerings
    section["subjects"] = []
    section["selected_subject_id"] = ""
    filter_fields.append(
        _select_field(
            "ese_offering",
            pgettext(_CTX, "Fənn"),
            [{"value": str(o.id), "label": _offering_option_label(o)} for o in offerings],
            str(offering.id) if offering is not None else "",
            searchable=True,
            wide=True,
        )
    )
    return offering, {
        **({"ese_group": selected_group_id} if selected_group_id else {}),
        **({"ese_offering": str(offering.id)} if offering is not None else {}),
    }


def _offering_option_label(offering) -> str:
    """«CS101 — Proqramlaşdırma · Müəllim Adı» — sahib: müəllim adı seçimdə görünsün."""
    if offering.instructor_label:
        return f"{offering.subject_label} · {offering.instructor_label}"
    return offering.subject_label


def _subject_first(request, section, filter_fields, service, selected_org, period, selection):
    """Köhnə sıra: fənn → qrup (açılış). Davranış dəyişməyib (2026-09-14: + müəllim filtri)."""
    subjects = service.subjects_for_period(organization=selected_org, period=period)
    selected_subject_id = _resolve_subject(request, subjects)
    section["subjects"] = subjects
    section["selected_subject_id"] = selected_subject_id
    filter_fields.append(
        _select_field(
            "ese_subject",
            pgettext(_CTX, "Fənn"),
            [{"value": s["id"], "label": f"{s['code']} — {s['name']}"} for s in subjects],
            selected_subject_id,
            searchable=True,
            wide=True,
        )
    )
    offerings = selection.offerings(
        service.offerings_for_subject(organization=selected_org, period=period, subject_id=selected_subject_id)
    )
    from apps.registrar.public import exam_score_sheets as sheets_service

    for offering in offerings:
        offering.group_label = service.offering_label(offering)
        offering.subject_label = sheets_service.subject_label(offering)
        offering.instructor_label = sheets_service.instructor_label(offering)
    offering = _resolve_offering(request, offerings)
    section["offerings"] = offerings
    filter_fields.append(
        _select_field(
            "ese_offering",
            pgettext(_CTX, "Qrup"),
            [{"value": str(o.id), "label": o.group_label} for o in offerings],
            str(offering.id) if offering is not None else "",
            searchable=True,
        )
    )
    return offering, {
        **({"ese_subject": selected_subject_id} if selected_subject_id else {}),
        **({"ese_offering": str(offering.id)} if offering is not None else {}),
    }
