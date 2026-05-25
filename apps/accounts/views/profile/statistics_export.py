"""
Statistics CSV export view.

Exports the same statistics shown in the profile "statistics" section as a CSV
download. Reuses the short-lived statistics cache so an identical
(role, scope, filters) request hits the same cache entry as the dashboard.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils.translation import pgettext_lazy

from ...models import UserProfile
from .._helpers import _get_active_organization, _role_capabilities


@login_required
def statistics_export_csv(request):
    """Export current statistics data as CSV."""
    import csv
    import io

    from apps.accounts.services.statistics_selectors import (
        get_org_admin_statistics,
        get_student_statistics,
        get_superadmin_statistics,
        get_teacher_statistics,
    )

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    if "statistics" not in capabilities["allowed_sections"]:
        raise Http404

    org = _get_active_organization(request)
    filters = {
        "date_from": (request.GET.get("stat_date_from") or "").strip(),
        "date_to": (request.GET.get("stat_date_to") or "").strip(),
        "course": (request.GET.get("stat_course") or "").strip() or None,
        "group": (request.GET.get("stat_group") or "").strip() or None,
        "content_type": (
            (request.GET.get("stat_content_type") or "all").strip().lower()
            if (request.GET.get("stat_content_type") or "all").strip().lower()
            in {"all", "exam", "assignment", "lab", "project"}
            else "all"
        ),
        "organization": (request.GET.get("stat_organization") or "").strip() or None,
    }

    # Reuse the same short-lived statistics cache as the dashboard view
    # (FAZA 12) — identical (role, scope, filters) hits the same cache entry.
    from core.cache import get_or_set_cached_statistics

    if capabilities["is_superadmin"]:
        stats = get_or_set_cached_statistics(
            role="superadmin",
            scope_id="global",
            filters=filters,
            compute=lambda: get_superadmin_statistics(filters=filters),
        )
    elif capabilities["is_org_admin"] and org:
        stats = get_or_set_cached_statistics(
            role="org_admin",
            scope_id=org.pk,
            filters=filters,
            compute=lambda: get_org_admin_statistics(organization=org, filters=filters),
        )
    elif capabilities["is_teacher"]:
        stats = get_or_set_cached_statistics(
            role="teacher",
            scope_id=request.user.pk,
            filters={**filters, "_org": getattr(org, "pk", None)},
            compute=lambda: get_teacher_statistics(request.user, organization=org, filters=filters),
        )
    else:
        stats = get_or_set_cached_statistics(
            role="student",
            scope_id=request.user.pk,
            filters={**filters, "_org": getattr(org, "pk", None)},
            compute=lambda: get_student_statistics(request.user, organization=org, filters=filters),
        )

    output = io.StringIO()
    writer = csv.writer(output)
    summary = stats.get("summary", {})
    writer.writerow(
        [
            str(pgettext_lazy("profile.statistics", "csv_header_metric")),
            str(pgettext_lazy("profile.statistics", "csv_header_value")),
        ]
    )
    for key, value in summary.items():
        writer.writerow([key.replace("_", " ").title(), value])

    from django.http import HttpResponse as _HR

    response = _HR(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="statistics.csv"'
    return response
