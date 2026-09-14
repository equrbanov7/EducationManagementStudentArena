"""«Statistika» — SUPERADMİN profili: platforma-genişliyi + təşkilat seçici.

Təşkilat müqayisə cədvəli köhnə selector-dakı kimi qruplaşmış aqreqatlarla
qurulur (təşkilat başına sorğu YOX); səhifələmə view-dadır.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.utils import timezone

from ._shared import (
    FINISHED_ATTEMPT_STATUSES,
    STUDENT_ROLE_NAMES,
    TEACHER_ROLE_NAMES,
    Window,
    attempt_outcome,
    distribution,
    exam_lifecycle_aggregate,
)

#: Müqayisə cədvəlinə düşən maksimum təşkilat (köhnə selector ilə eyni).
ORG_COMPARISON_LIMIT = 60


def superadmin_metrics(*, window: Window, organization_id=None) -> dict:
    """Platforma metrik modeli — sabit sayda sorğu (~11)."""
    from django.contrib.auth import get_user_model

    from apps.courses.models import Course
    from apps.exams.models import Exam, ExamAttempt
    from apps.organizations.models import Membership, Organization

    User = get_user_model()
    now = timezone.now()

    orgs = Organization.objects.filter(is_active=True, status="active")
    if organization_id:
        orgs = orgs.filter(id=organization_id)
    org_agg = orgs.aggregate(total=Count("id"), universities=Count("id", filter=Q(org_type="university")))
    org_types = distribution(orgs.values("org_type").annotate(n=Count("id")).order_by("-n"), label_key="org_type")

    memberships = Membership.objects.filter(is_active=True, organization__in=orgs)
    member_agg = memberships.aggregate(
        memberships=Count("id"),
        members=Count("user", distinct=True),
        students=Count("user", distinct=True, filter=Q(role__name__in=STUDENT_ROLE_NAMES)),
        teachers=Count("user", distinct=True, filter=Q(role__name__in=TEACHER_ROLE_NAMES)),
    )
    active_users = int(member_agg["members"] or 0) if organization_id else User.objects.filter(is_active=True).count()

    exams = Exam.objects.filter(is_deleted=False, organization__in=orgs)
    lifecycle = exam_lifecycle_aggregate(window.apply(exams, "start_datetime") if window.is_bounded else exams, now=now)
    attempts = window.apply(ExamAttempt.objects.filter(exam__in=exams), "started_at")
    outcome = attempt_outcome(attempts)
    course_agg = Course.objects.filter(organization__in=orgs).aggregate(
        total=Count("id"), published=Count("id", filter=Q(status="published"))
    )

    org_rows = list(orgs.order_by("name").values("id", "name", "org_type")[:ORG_COMPARISON_LIMIT])
    org_ids = [row["id"] for row in org_rows]
    by_org_members = {
        row["organization_id"]: row
        for row in Membership.objects.filter(organization_id__in=org_ids, is_active=True)
        .values("organization_id")
        .annotate(
            members=Count("user", distinct=True),
            students=Count("user", distinct=True, filter=Q(role__name__in=STUDENT_ROLE_NAMES)),
            teachers=Count("user", distinct=True, filter=Q(role__name__in=TEACHER_ROLE_NAMES)),
        )
    }
    by_org_exams = dict(
        Exam.objects.filter(organization_id__in=org_ids, is_deleted=False)
        .values("organization_id")
        .annotate(c=Count("id"))
        .values_list("organization_id", "c")
    )
    by_org_attempts = dict(
        window.apply(
            ExamAttempt.objects.filter(
                exam__organization_id__in=org_ids,
                exam__is_deleted=False,
                status__in=FINISHED_ATTEMPT_STATUSES,
                is_trial=False,
            ),
            "started_at",
        )
        .values("exam__organization_id")
        .annotate(c=Count("id"))
        .values_list("exam__organization_id", "c")
    )
    comparison = []
    for row in org_rows:
        m = by_org_members.get(row["id"]) or {}
        comparison.append(
            {
                "id": str(row["id"]),
                "name": row["name"],
                "org_type": row["org_type"],
                "members": int(m.get("members") or 0),
                "students": int(m.get("students") or 0),
                "teachers": int(m.get("teachers") or 0),
                "exams": int(by_org_exams.get(row["id"]) or 0),
                "attempts": int(by_org_attempts.get(row["id"]) or 0),
            }
        )
    comparison.sort(key=lambda item: (-item["attempts"], -item["members"], item["name"].lower()))

    return {
        "profile": "superadmin",
        "window": window.as_dict(),
        "organizations": {
            "total": int(org_agg["total"] or 0),
            "universities": int(org_agg["universities"] or 0),
            "by_type": org_types,
        },
        "users": {
            "active": active_users,
            "memberships": int(member_agg["memberships"] or 0),
            "students": int(member_agg["students"] or 0),
            "teachers": int(member_agg["teachers"] or 0),
        },
        "exams": lifecycle,
        "outcome": outcome,
        "courses": {
            "total": int(course_agg["total"] or 0),
            "published": int(course_agg["published"] or 0),
        },
        "org_comparison": comparison,
    }
