"""Profil «exam-score-entry» bölməsi — İmtahan Mərkəzi bal daxiletməsi.

``section`` dict-ini YERİNDƏ mutasiya edir (``journal_close`` pattern-i).
Superadmin cross-org (təşkilat seçici); imtahan mərkəzi istifadəçisi yalnız
aktiv təşkilatı görür.

Axın (sahibin qərarı, spec E2): tədris ili → semestr → FƏNN → QRUP (açılış) →
tələbə siyahısı. Hər tələbə sətrində cari bal, yekun güzgüsü, daxiletmə
tarixçəsi və (varsa) rəqəmsal cəhdlərin tarixçəsi göstərilir.
"""

from django.urls import reverse
from django.utils import timezone

from apps.accounts.views._helpers.formatting import _append_query_params

from .kollokvium_windows import _current_semester, _season_label

SECTION = "exam-score-entry"


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
    requested_period = (request.GET.get("period") or "").strip()
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


def _resolve_offering(request, offerings):
    requested = (request.GET.get("ese_offering") or "").strip()
    match = next((o for o in offerings if str(o.id) == requested), None)
    if match is not None:
        return match
    return offerings[0] if offerings else None


def build_exam_score_entry_section(
    request, section, *, is_superadmin, active_organization, allowed_sections, active_section
):
    if SECTION not in allowed_sections or active_section != SECTION:
        return

    from apps.organizations.models import AcademicPeriod
    from apps.registrar import exam_score_entry as service
    from apps.registrar.models import CorrectionReason

    org_options, selected_org = _selected_org(
        request, is_superadmin=is_superadmin, active_organization=active_organization
    )
    section["is_superadmin"] = is_superadmin
    section["org_options"] = org_options
    section["selected_org"] = selected_org
    section["reasons"] = [{"value": value, "label": str(label)} for value, label in CorrectionReason.choices]
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section=SECTION)

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
    if period is None:
        return

    subjects = service.subjects_for_period(organization=selected_org, period=period)
    selected_subject_id = _resolve_subject(request, subjects)
    section["subjects"] = subjects
    section["selected_subject_id"] = selected_subject_id

    offerings = service.offerings_for_subject(organization=selected_org, period=period, subject_id=selected_subject_id)
    if not is_superadmin:
        # Unit-scoped aktor (dekan/kafedra müdiri `exam.*` ilə) yalnız öz
        # alt-ağacının qruplarını görür — yazı qapısı ilə eyni əhatə.
        offerings = [
            offering for offering in offerings if service.offering_in_actor_scope(request.user, selected_org, offering)
        ]
    for offering in offerings:
        offering.group_label = service.offering_label(offering)
    offering = _resolve_offering(request, offerings)
    section["offerings"] = offerings
    section["offering"] = offering

    section["post_next_url"] = _append_query_params(
        reverse("accounts:profile"),
        section=SECTION,
        **({"ese_org": str(selected_org.pk)} if (is_superadmin and selected_org) else {}),
        **({"ese_year": selected_year} if selected_year else {}),
        **({"period": str(period.id)} if period else {}),
        **({"ese_subject": selected_subject_id} if selected_subject_id else {}),
        **({"ese_offering": str(offering.id)} if offering is not None else {}),
    )

    if offering is None:
        return

    roster = service.roster_for_offering(offering=offering)
    section["rows"] = roster["rows"]
    section["exam_score_max"] = roster["exam_score_max"]
    section["journal_locked"] = _journal_locked(offering)


def _journal_locked(offering) -> bool:
    """Jurnal bağlıdırmı — səthdə «bal yenə yazılır» izahını göstərmək üçün."""
    from apps.registrar import gradebook

    return gradebook.journal_is_locked(offering)
