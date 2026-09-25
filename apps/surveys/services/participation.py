"""İştirak — gözlənilən hədəf sayı, qəbz sayı, iştirak faizi, günlük tempo.

* **Gözlənilən** — kampaniya dövrünün BAĞLI jurnallarında hər (DROPPED olmayan)
  qeydiyyat × açılışı tədris edən hər müəllim (``targets`` modulu ilə eyni qayda).
* **Qəbz** — ``SurveyReceipt`` (müəllim bölməsi). Faiz = qəbz / gözlənilən.

Sorğu sayı kampaniya başına sabitdir (~6), sətir sayından asılı deyil. Qəbzlərdən
yalnız SAY oxunur — heç bir şəxs siyahısı qaytarılmır.
"""

from __future__ import annotations

from django.db.models import Count

from .. import registrar_bridge as bridge
from ..constants import Section
from ..models import SurveyCampaign, SurveyReceipt
from .access import receipt_scope_q, unit_in_scope


def _enrollment_counts(organization, period_id, filters) -> dict:
    offerings = bridge.closed_offerings(organization, period_id)
    if filters.subject_id is not None:
        offerings = offerings.filter(subject_id=filters.subject_id)
    if filters.group_id is not None:
        offerings = offerings.filter(group_id=filters.group_id)
    rows = (
        bridge.closed_enrollments(organization, period_id)
        .filter(offering_id__in=offerings.values("pk"))
        .values("offering_id")
        .annotate(n=Count("id"))
    )
    return {row["offering_id"]: row["n"] for row in rows}


def expected_targets(campaign, scope, filters) -> int:
    """Kampaniyanın gözlənilən (tələbə × açılış × müəllim) hədəf sayı — əhatə + filtrlə."""
    counts = _enrollment_counts(campaign.organization_id, campaign.period_id, filters)
    if not counts:
        return 0
    teachers = bridge.offering_teachers(list(counts))
    pairs = [
        (offering_id, teacher_id)
        for offering_id, ids in teachers.items()
        for teacher_id in ids
        if filters.teacher_id is None or teacher_id == filters.teacher_id
    ]
    need_units = not scope.is_org_wide or filters.department_id is not None or filters.faculty_id is not None
    departments = bridge.resolve_departments(campaign.organization_id, pairs) if need_units else {}
    paths = bridge.unit_paths(departments.values()) if departments else {}
    faculties = bridge.faculties_for_units(departments.values()) if filters.faculty_id is not None else {}
    total = 0
    for pair in pairs:
        if need_units:
            department_id = departments.get(pair)
            if filters.department_id is not None and department_id != filters.department_id:
                continue
            if filters.faculty_id is not None and faculties.get(department_id) != filters.faculty_id:
                continue
            if not unit_in_scope(scope, department_id, paths.get(department_id)):
                continue
        total += counts.get(pair[0], 0)
    return total


def receipt_count(campaign_ids, scope, filters, *, section=Section.TEACHER) -> int:
    queryset = SurveyReceipt.objects.filter(campaign_id__in=campaign_ids, scope=section)
    if section == Section.TEACHER:
        queryset = queryset.filter(receipt_scope_q(scope))
        for field, value in (
            ("teacher_id", filters.teacher_id),
            ("teacher_department_id", filters.department_id),
            ("offering__subject_id", filters.subject_id),
            ("offering__group_id", filters.group_id),
        ):
            if value is not None:
                queryset = queryset.filter(**{field: value})
    return queryset.count()


def participation(organization, scope, filters, campaign_ids) -> dict:
    """``{"receipts", "expected", "rate", "general_receipts"}`` — bir və ya bir neçə kampaniya."""
    expected = 0
    for campaign in SurveyCampaign.objects.filter(organization=organization, pk__in=campaign_ids):
        expected += expected_targets(campaign, scope, filters)
    receipts = receipt_count(campaign_ids, scope, filters)
    general = receipt_count(campaign_ids, scope, filters, section=Section.GENERAL) if scope.is_org_wide else None
    return {
        "receipts": receipts,
        "expected": expected,
        "rate": round(receipts / expected, 4) if expected else None,
        "general_receipts": general,
    }


def daily_timeline(campaign_ids, scope) -> list:
    """Günlük tamamlanma sayı (müəllim bölməsi qəbzləri) — ``[{"day", "count"}]``."""
    rows = (
        SurveyReceipt.objects.filter(campaign_id__in=campaign_ids, scope=Section.TEACHER)
        .filter(receipt_scope_q(scope))
        .values("completed_on")
        .annotate(count=Count("id"))
        .order_by("completed_on")
    )
    return [{"day": row["completed_on"], "count": row["count"]} for row in rows]
