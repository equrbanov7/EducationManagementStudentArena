"""Subject-owning chair appeal readers; one source for panel, detail and notification."""

from collections import defaultdict

from django.apps import apps as django_apps

from apps.organizations.public import get_permission_scope
from apps.registrar.public import offering_chairs

PERMISSION = "appeal.view_subject"


def scope_for(user, organization):
    if (
        organization is None
        or not organization.is_active
        or user is None
        or not user.is_authenticated
        or not user.is_active
    ):
        return None
    scope = get_permission_scope(user, organization, PERMISSION)
    return scope if scope.has_structure_access else None


def selected_offerings(queryset, organization):
    """Exact student/subject enrollment selection shared by scope and notifications."""
    rows = list(
        queryset.filter(organization=organization).values(
            "pk",
            "student_id",
            "exam_id",
            "exam__subject_id",
            "exam__subject__chair_unit_id",
            "attempt__finished_at",
            "created_at",
        )
    )
    if not rows:
        return [], {}
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    Exam = django_apps.get_model("exams", "Exam")
    pairs = defaultdict(list)
    for student_id, subject_id, offering_id, start, end in (
        Enrollment.objects.filter(
            organization=organization,
            student_id__in={r["student_id"] for r in rows},
            offering__organization=organization,
            offering__subject_id__in={r["exam__subject_id"] for r in rows},
        )
        .exclude(status="dropped")
        .values_list(
            "student_id",
            "offering__subject_id",
            "offering_id",
            "offering__period__start_date",
            "offering__period__end_date",
        )
    ):
        pairs[(student_id, subject_id)].append((offering_id, start, end))
    links = defaultdict(set)
    for exam_id, offering_id in Exam.journal_offerings.through.objects.filter(
        exam_id__in={r["exam_id"] for r in rows}, courseoffering__organization=organization
    ).values_list("exam_id", "courseoffering_id"):
        links[exam_id].add(offering_id)
    selected = {}
    for row in rows:
        candidates = pairs[(row["student_id"], row["exam__subject_id"])]
        linked = [pk for pk, _start, _end in candidates if pk in links[row["exam_id"]]]
        moment = row["attempt__finished_at"] or row["created_at"]
        day = moment.date() if moment else None
        covering = [pk for pk, start, end in candidates if day and start and end and start <= day <= end]
        latest = max((start for _pk, start, _end in candidates if start), default=None)
        picked = linked or covering or [pk for pk, start, _end in candidates if start == latest]
        selected[row["pk"]] = picked
    return rows, selected


def appeal_chair_map(queryset, organization):
    """Resolve official subject chairs for the same selected physical offerings."""
    rows, selected = selected_offerings(queryset, organization)
    if not rows:
        return {}
    Offering = django_apps.get_model("registrar", "CourseOffering")
    all_ids = set().union(*selected.values())
    official = offering_chairs.official_offering_chairs(Offering.objects.filter(pk__in=all_ids), organization.pk)
    result = {}
    for row in rows:
        chairs = set().union(*(official.get(pk, ()) for pk in selected[row["pk"]]))
        if not chairs and row["exam__subject__chair_unit_id"]:
            chairs.add(str(row["exam__subject__chair_unit_id"]))
        result[row["pk"]] = chairs
    return result


def _covers(scope, chair):
    return bool(
        scope
        and (
            scope.is_org_wide
            or str(chair.pk) in {str(pk) for pk in scope.unit_ids}
            or any(chair.path.startswith(path + "/") for path in scope.unit_paths if path)
        )
    )


def _chairs(organization, mapping):
    ids = set().union(*mapping.values()) if mapping else set()
    return list(
        django_apps.get_model("organizations", "OrgUnit").objects.filter(
            organization=organization, pk__in=ids, unit_type__in=("chair", "department")
        )
    )


def scoped_queryset(user, organization, *, within=None):
    Appeal = django_apps.get_model("appeals", "Appeal")
    scope = scope_for(user, organization)
    if scope is None:
        return Appeal.objects.none()
    base = Appeal.objects.filter(organization=organization)
    if within is not None:
        base = base.filter(pk__in=within.values("pk"))
    mapping = appeal_chair_map(base, organization)
    covered = {str(chair.pk) for chair in _chairs(organization, mapping) if _covers(scope, chair)}
    return base.filter(pk__in=[pk for pk, chairs in mapping.items() if chairs & covered])


def exam_teacher_queryset(user, organization):
    """Only the explicit exam journal teacher gets this additional read path."""
    from apps.registrar.public import eligible_instructor_user_ids

    Appeal = django_apps.get_model("appeals", "Appeal")
    if organization is None or not user.is_authenticated:
        return Appeal.objects.none()
    candidates = Appeal.objects.filter(organization=organization, exam__journal_teacher=user)
    if not candidates.exists() or user.pk not in eligible_instructor_user_ids(organization=organization):
        return Appeal.objects.none()
    return candidates


def notification_readers(appeal):
    """Only explicit subscribers; wildcard-only executives receive no new appeal spam."""
    organization = appeal.organization
    memberships = (
        django_apps.get_model("organizations", "Membership")
        .objects.filter(
            organization=organization,
            is_active=True,
            role__organization=organization,
            role__is_active=True,
            user__is_active=True,
        )
        .exclude(user_id=appeal.student_id)
        .select_related("role", "user")
    )
    candidates = {
        m.user_id: m.user
        for m in memberships
        if PERMISSION in (m.role.permissions or []) or "appeal.*" in (m.role.permissions or [])
    }
    if not candidates:
        return []
    Appeal = django_apps.get_model("appeals", "Appeal")
    mapping = appeal_chair_map(Appeal.objects.filter(pk=appeal.pk), organization)
    chairs = _chairs(organization, mapping)
    return [
        user for user in candidates.values() if any(_covers(scope_for(user, organization), chair) for chair in chairs)
    ]
