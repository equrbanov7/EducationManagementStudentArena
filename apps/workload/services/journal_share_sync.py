"""Mövcud jurnal paylarının bütün-kafedra bərpası; yük, owner və akademik məzmun yazılmır."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects

from apps.registrar.public import sync_workload_journal_shares

from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow
from .offering_rules import plan_reached_chair
from .offering_shares import plan_for_rows
from .offering_sync import group_targets
from .repair_fingerprints import academic_database_fingerprint
from .sbio235_state import RepairError, digest, records


def _model(label):
    return apps.get_model(label)


def _state(organization, tasks, rows, offerings, *, lock):
    """Baseline yalnız tenant/current-year giriş mənbələrini və mövcud scope-u bağlayır."""
    org_id = organization.pk
    row_ids, offering_ids = [row.pk for row in rows], [o.pk for o in offerings]
    shares = _model("registrar.JournalShare").objects.filter(organization=organization, offering_id__in=offering_ids)
    assignments = TeacherAssignment.objects.filter(organization=organization, row_id__in=row_ids)
    teacher_ids = {a.teacher_id for row in rows for a in row.assignments.all() if a.teacher_id}
    teacher_ids |= {o.instructor_id for o in offerings if o.instructor_id}
    teacher_ids |= set(shares.values_list("teacher_id", flat=True))
    memberships = _model("organizations.Membership").objects.filter(organization=organization, user_id__in=teacher_ids)
    users = get_user_model().objects.filter(pk__in=teacher_ids).order_by("pk")
    if lock:
        users = users.select_for_update()
    row_groups = TeachingTaskRow.groups.through.objects.filter(teachingtaskrow_id__in=row_ids)
    share_students = _model("registrar.JournalShare").enrollments.through.objects.filter(
        journalshare__organization_id=org_id, journalshare__offering_id__in=offering_ids
    )
    data = {
        "organization": records(_model("organizations.Organization").objects.filter(pk=org_id), lock=lock),
        "tasks": records(
            TeachingTask.objects.filter(organization=organization, pk__in=[t.pk for t in tasks]), lock=lock
        ),
        "rows": records(TeachingTaskRow.objects.filter(organization=organization, pk__in=row_ids), lock=lock),
        "row_groups": records(row_groups, lock=lock),
        "assignments": records(assignments, lock=lock),
        "offerings": records(
            _model("registrar.CourseOffering").objects.filter(organization=organization, pk__in=offering_ids), lock=lock
        ),
        "groups": records(
            _model("organizations.OrgUnit").objects.filter(
                organization=organization, pk__in={o.group_id for o in offerings if o.group_id}
            ),
            lock=lock,
        ),
        "periods": records(
            _model("organizations.AcademicPeriod").objects.filter(
                organization=organization, pk__in={o.period_id for o in offerings}
            ),
            lock=lock,
        ),
        "roles": records(
            _model("organizations.Role").objects.filter(
                organization=organization, pk__in=memberships.values("role_id")
            ),
            lock=lock,
        ),
        "memberships": records(memberships, lock=lock),
        "teachers": list(users.values("id", "is_active")),
        "shares": records(shares, lock=lock),
        "share_students": records(share_students, lock=lock),
    }
    return data


def _protected(state):
    protected = dict(state)
    protected["shares"] = [share for share in state["shares"] if share["source"] != "workload"]
    return digest(protected)


@transaction.atomic
def run(*, organization, year, user, apply=False, expected_baseline=""):
    if not getattr(user, "is_active", False) or not getattr(user, "is_superuser", False):
        raise RepairError("active_superadmin_required")
    tasks = list(
        TeachingTask.objects.select_for_update().filter(organization=organization, academic_year=year).order_by("pk")
    )
    tasks = [task for task in tasks if plan_reached_chair(task)]
    rows = list(
        TeachingTaskRow.objects.filter(organization=organization, task_id__in=[task.pk for task in tasks])
        .select_for_update(of=("self",))
        .select_related("period", "task")
        .order_by("task_id", "order", "created_at", "pk")
    )
    # Parent/through/assignment kilidləri prefetch-dən ƏVVƏL: baseline təzə olduğu
    # halda köhnə yaddaşdakı qrup/təyinatdan giriş yaranmasın.
    list(
        TeachingTaskRow.groups.through.objects.select_for_update()
        .filter(teachingtaskrow_id__in=[row.pk for row in rows])
        .values_list("pk", flat=True)
    )
    prefetch_related_objects(
        rows,
        "groups",
        Prefetch(
            "assignments",
            queryset=TeacherAssignment.objects.select_for_update(of=("self",))
            .select_related("teacher")
            .order_by("activity", "created_at"),
        ),
    )
    targets = group_targets(rows)
    offerings = list(
        _model("registrar.CourseOffering")
        .objects.filter(
            organization=organization,
            period__academic_year=year,
            is_active=True,
        )
        .select_for_update(of=("self",))
        .select_related("organization", "period")
        .order_by("pk")
    )
    before = _state(organization, tasks, rows, offerings, lock=True)
    academic = academic_database_fingerprint(
        organization_id=organization.pk, offerings=offerings, exclude=("journal_share",)
    )
    baseline = digest({"year": year, "state": before, "academic": academic})
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("baseline_changed")
    if apply and not expected_baseline:
        raise RepairError("expected_baseline_required")
    plans = {}
    for key, entry in targets.items():
        plans[key] = plan_for_rows(entry["rows"], group=entry["group"])
    counts = sync_workload_journal_shares(
        organization_id=organization.pk,
        offering_ids=[o.pk for o in offerings],
        plans=plans,
        by_user=user,
        retire_orphans=True,
    )
    after = _state(organization, tasks, rows, offerings, lock=False)
    if _protected(before) != _protected(after):
        raise RepairError("protected_workload_or_access_changed")
    if (
        academic_database_fingerprint(organization_id=organization.pk, offerings=offerings, exclude=("journal_share",))
        != academic
    ):
        raise RepairError("academic_content_changed")
    result = {"baseline": baseline, "tasks": len(tasks), "rows": len(rows), "offerings": len(offerings), **counts}
    if not apply:
        transaction.set_rollback(True)
    return result
