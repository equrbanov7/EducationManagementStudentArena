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
"""

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

from .kollokvium_windows import _current_semester, _season_label

SECTION = "exam-score-entry"
_CTX = "registrar.exam_score_entry"

MODE_GROUP = "group"
MODE_SUBJECT = "subject"


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
    from apps.registrar.models import CorrectionReason
    from apps.registrar.public import exam_score_entry as service
    from apps.registrar.public import exam_score_sheets as sheets_service

    org_options, selected_org = _selected_org(
        request, is_superadmin=is_superadmin, active_organization=active_organization
    )
    mode = _resolve_mode(request)
    section["is_superadmin"] = is_superadmin
    section["org_options"] = org_options
    section["selected_org"] = selected_org
    section["mode"] = mode
    section["is_group_mode"] = mode == MODE_GROUP
    section["reasons"] = [{"value": value, "label": str(label)} for value, label in CorrectionReason.choices]
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

    if mode == MODE_GROUP:
        offering, extra_params = _group_first(
            request, section, filter_fields, service, sheets_service, selected_org, period, is_superadmin
        )
    else:
        offering, extra_params = _subject_first(
            request, section, filter_fields, service, selected_org, period, is_superadmin
        )
    section["offering"] = offering
    section["post_next_url"] = _append_query_params(
        reverse("accounts:profile"), section=SECTION, ese_mode=mode, **base_params, **extra_params
    )
    if offering is None:
        return

    _fill_offering(section, offering, period, service, sheets_service, selected_org, is_superadmin)


def _group_first(request, section, filter_fields, service, sheets_service, selected_org, period, is_superadmin):
    """Qrup → fənn (qrupun açılışları). Unit-scoped aktor yalnız öz alt-ağacının qruplarını görür."""
    groups = sheets_service.groups_for_period(organization=selected_org, period=period)
    if not is_superadmin:
        groups = _groups_in_actor_scope(request.user, selected_org, groups, service)
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
    offerings = sheets_service.offerings_for_group(organization=selected_org, period=period, group_id=selected_group_id)
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


def _subject_first(request, section, filter_fields, service, selected_org, period, is_superadmin):
    """Köhnə sıra: fənn → qrup (açılış). Davranış dəyişməyib."""
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
    offerings = service.offerings_for_subject(organization=selected_org, period=period, subject_id=selected_subject_id)
    if not is_superadmin:
        # Unit-scoped aktor (dekan/kafedra müdiri `exam.*` ilə) yalnız öz
        # alt-ağacının qruplarını görür — yazı qapısı ilə eyni əhatə.
        offerings = service.offerings_in_actor_scope(request.user, selected_org, offerings)
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


def _groups_in_actor_scope(user, organization, groups, service):
    """Qrup siyahısını aktorun struktur əhatəsinə görə süz (org-wide → hamısı)."""
    if not groups:
        return []
    from apps.registrar.public import journal_scope

    scope = journal_scope.permission_scope_for(user, organization, service.ENTRY_PERMISSION)
    if not scope.has_structure_access:
        return []
    if scope.is_org_wide:
        return groups
    from apps.organizations.models import OrgUnit

    allowed = {
        str(pk)
        for pk in OrgUnit.objects.filter(organization=organization, pk__in=[g["id"] for g in groups])
        .filter(scope.unit_subtree_q())
        .values_list("pk", flat=True)
    }
    return [g for g in groups if g["id"] in allowed]


def _fill_offering(section, offering, period, service, sheets_service, selected_org, is_superadmin):
    """Seçilmiş açılış: metadata (müəllim, qrup, fənn), siyahı, KPI, partiyalar, idxal URL-ləri."""
    from apps.registrar.public import exam_score_import as importer

    roster = service.roster_for_offering(offering=offering)
    section["rows"] = roster["rows"]
    section["exam_score_max"] = roster["exam_score_max"]
    section["journal_locked"] = _journal_locked(offering)
    section.update(_roster_kpis(roster["rows"]))
    section["kpi_tiles"] = _kpi_tiles(section)
    section["tabs"] = [
        {"key": "manual", "label": pgettext(_CTX, "Əl ilə daxil et"), "current": True},
        {"key": "import", "label": pgettext(_CTX, "Fayldan yüklə (XLSX / CSV)"), "current": False},
    ]
    section["offering_meta"] = {
        "subject_code": offering.subject.code,
        "subject_name": offering.subject.name,
        "group_label": service.offering_label(offering),
        "instructor": sheets_service.instructor_label(offering) or "—",
        "period_label": f"{period.season_label} — {period.name}",
    }
    sheets = sheets_service.sheets_for_offering(offering=offering)
    section["sheets"] = sheets
    section["sheet_defaults"] = sheets_service.latest_sheet_defaults(sheets)
    section["sheet_defaults"]["examiner_name"] = section["sheet_defaults"][
        "examiner_name"
    ] or sheets_service.instructor_label(offering)
    section["steps"] = _steps(offering=offering, saved=section["saved_flag"])
    section["import_columns"] = importer.template_columns(roster["exam_score_max"])
    section["import_max_rows"] = importer.MAX_ROWS
    section["import_max_upload_mb"] = importer.MAX_UPLOAD_BYTES // (1024 * 1024)
    org_param = {"ese_org": str(selected_org.pk)} if is_superadmin else {}
    section["import_template_url"] = _append_query_params(
        reverse("accounts:exam_score_import_template"), offering=str(offering.pk), **org_param
    )
    section["import_template_csv_url"] = _append_query_params(
        reverse("accounts:exam_score_import_template"), offering=str(offering.pk), format="csv", **org_param
    )
    section["import_preview_url"] = reverse("accounts:exam_score_import_preview")
    section["import_apply_url"] = reverse("accounts:exam_score_import_apply")


def _steps(*, offering, saved) -> list:
    """«Seç → Yoxla → Yaz» lenti (ems_ui/_stepper). JS yalnız 2↔3 arasını canlı dəyişir."""
    if offering is None:
        return [
            {"label": pgettext(_CTX, "Seç"), "state": "current", "note": pgettext(_CTX, "qrup və fənni seçin")},
            {"label": pgettext(_CTX, "Yoxla"), "state": "todo", "note": ""},
            {"label": pgettext(_CTX, "Yaz"), "state": "todo", "note": ""},
        ]
    return [
        {"label": pgettext(_CTX, "Seç"), "state": "done", "note": ""},
        {
            "label": pgettext(_CTX, "Yoxla"),
            "state": "done" if saved else "current",
            "note": pgettext(_CTX, "balları yazın və ya faylı yoxlayın"),
        },
        {
            "label": pgettext(_CTX, "Yaz"),
            "state": "done" if saved else "todo",
            "note": pgettext(_CTX, "yadda saxlanıldı") if saved else "",
        },
    ]


def _kpi_tiles(section) -> list:
    """ems_ui/_kpi_row kartları — «dəyişdirilib» kartını JS canlı yeniləyir (key=dirty)."""
    avg = section["kpi_avg"]
    return [
        {
            "label": pgettext(_CTX, "Tələbə"),
            "value": section["kpi_students"],
            "note": pgettext(_CTX, "qeydiyyatlı"),
            "key": "students",
        },
        {
            "label": pgettext(_CTX, "Bal yazılıb"),
            "value": section["kpi_recorded"],
            "note": pgettext(_CTX, "sistemə köçürülüb"),
            "tone": "accent-success" if section["kpi_recorded"] else "",
            "key": "recorded",
        },
        {
            "label": pgettext(_CTX, "Gözləyir"),
            "value": section["kpi_pending"],
            "note": pgettext(_CTX, "bal yazılmayıb"),
            "tone": "accent-warning" if section["kpi_pending"] else "",
            "key": "pending",
        },
        {
            "label": pgettext(_CTX, "Orta imtahan balı"),
            "value": avg if avg is not None else "—",
            "note": "%s %s" % (pgettext(_CTX, "maksimum"), section["exam_score_max"]),
            "key": "avg",
        },
        {
            "label": pgettext(_CTX, "Dəyişdirilib"),
            "value": 0,
            "note": pgettext(_CTX, "yadda saxlanmayıb"),
            "key": "dirty",
        },
    ]


def _roster_kpis(rows) -> dict:
    """Bölmə başındakı KPI rəqəmləri — siyahı ARTIQ yaddaşdadır, əlavə sorğu yoxdur."""
    recorded = [row for row in rows if row.get("has_score")]
    scores = [row["exam_score"] for row in recorded if row.get("exam_score") is not None]
    return {
        "kpi_students": len(rows),
        "kpi_recorded": len(recorded),
        "kpi_pending": len(rows) - len(recorded),
        "kpi_avg": round(sum(scores) / len(scores), 1) if scores else None,
    }


def _journal_locked(offering) -> bool:
    """Jurnal bağlıdırmı — səthdə «bal yenə yazılır» izahını göstərmək üçün."""
    from apps.registrar.public import gradebook

    return gradebook.journal_is_locked(offering)
