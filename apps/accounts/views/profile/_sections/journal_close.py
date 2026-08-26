"""Profil «journal-close» bölməsi — RİM semestr-sonu jurnal bağlaması.

``section`` dict-ini YERİNDƏ mutasiya edir (``kollokvium_windows`` pattern-i).
Superadmin cross-org (təşkilat seçici); RİM istifadəçisi yalnız aktiv təşkilatı.
Tədris ili + semestr AYRICA seçilir (jurnaldakı kimi); əhatə (bütün universitet /
fakültə / kafedra) seçilir və neçə jurnalın təsirlənəcəyi ÖNİZLƏNİR.

Bölmə həm də RİM-in «jurnallar bu tarixdən sonra bağlanacaq» xəbərdarlıqlarını
idarə edir — jurnalda kollokvium lenti ilə eyni sürüşən zolaqda görünür.
"""

from django.urls import reverse
from django.utils import timezone

from apps.accounts.views._helpers.formatting import _append_query_params

from .kollokvium_windows import _current_semester, _season_label


def _selected_org(request, *, is_superadmin, active_organization):
    from apps.organizations.models import Organization

    if not is_superadmin:
        return [], active_organization
    org_options = list(Organization.objects.filter(is_active=True).order_by("name").values("id", "name"))
    requested = (request.GET.get("jc_org") or "").strip()
    selected = Organization.objects.filter(pk=requested).first() if requested else None
    if selected is None and org_options:
        selected = Organization.objects.filter(pk=org_options[0]["id"]).first()
    return org_options, selected


def _resolve_period(request, all_periods, today):
    """Tədris ili + semestr seçimi — kollokvium bölməsi ilə eyni heuristika."""
    years, seen = [], set()
    for period in all_periods:
        label = period.year_display
        if label and label not in seen:
            seen.add(label)
            years.append(label)

    default_period = _current_semester(all_periods, today)
    requested_year = (request.GET.get("jc_year") or "").strip()
    selected_year = requested_year if requested_year in seen else None
    if selected_year is None and default_period is not None:
        selected_year = default_period.year_display
    if selected_year is None and years:
        selected_year = years[0]

    periods_in_year = [p for p in all_periods if p.year_display == selected_year]
    requested_period = (request.GET.get("period") or "").strip()
    period = next((p for p in periods_in_year if str(p.id) == requested_period), None)
    if period is None and default_period is not None and default_period.year_display == selected_year:
        period = default_period
    if period is None and periods_in_year:
        period = periods_in_year[0]
    return years, selected_year, periods_in_year, period


def build_journal_close_section(
    request, section, *, is_superadmin, active_organization, allowed_sections, active_section
):
    if "journal-close" not in allowed_sections or active_section != "journal-close":
        return

    from apps.organizations.models import AcademicPeriod, OrgUnit
    from apps.registrar import journal_close as journal_close_service
    from apps.registrar.models import JournalCloseNotice
    from core.constants import OrgUnitType

    org_options, selected_org = _selected_org(
        request, is_superadmin=is_superadmin, active_organization=active_organization
    )
    section["is_superadmin"] = is_superadmin
    section["org_options"] = org_options
    section["selected_org"] = selected_org
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section="journal-close")

    if selected_org is None:
        return

    today = timezone.localdate()
    all_periods = list(AcademicPeriod.objects.filter(organization=selected_org).order_by("-start_date"))
    for period in all_periods:
        period.season_label = _season_label(period)
    years, selected_year, periods_in_year, period = _resolve_period(request, all_periods, today)

    section["years"] = years
    section["selected_year"] = selected_year
    section["periods"] = periods_in_year
    section["period"] = period
    section["today"] = today
    section["post_next_url"] = _append_query_params(
        reverse("accounts:profile"),
        section="journal-close",
        **({"jc_org": str(selected_org.pk)} if (is_superadmin and selected_org) else {}),
        **({"jc_year": selected_year} if selected_year else {}),
        **({"period": str(period.id)} if period else {}),
    )

    # ── Əhatə seçimi (fakültə / kafedra ağacı) ─────────────────────────────
    faculties = list(
        OrgUnit.objects.filter(organization=selected_org, is_active=True, unit_type=OrgUnitType.FACULTY)
        .order_by("name")
        .values("id", "name")
    )
    departments = list(
        OrgUnit.objects.filter(
            organization=selected_org,
            is_active=True,
            unit_type__in=[OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT],
        )
        .order_by("name")
        .values("id", "name", "parent_id")
    )
    section["faculties"] = faculties
    section["departments"] = [{**row, "parent_id": str(row["parent_id"] or "")} for row in departments]

    # ── Önizləmə: seçilmiş əhatədə neçə jurnal təsirlənəcək ────────────────
    scope = (request.GET.get("jc_scope") or "organization").strip()
    unit_id = (request.GET.get("jc_unit") or "").strip()
    unit = None
    if scope in ("faculty", "department") and unit_id:
        unit = OrgUnit.objects.filter(organization=selected_org, pk=unit_id).first()
    section["selected_scope"] = scope
    section["selected_unit_id"] = str(unit.pk) if unit is not None else ""
    section["preview"] = (
        journal_close_service.preview(organization=selected_org, period=period, unit=unit)
        if period is not None
        else None
    )

    # ── Mövcud xəbərdarlıqlar (bu dövr üzrə) ──────────────────────────────
    section["notices"] = (
        list(
            JournalCloseNotice.objects.filter(organization=selected_org, period=period)
            .select_related("org_unit")
            .order_by("scope", "closes_on")
        )
        if period is not None
        else []
    )
