"""Internal exact-operation capability; never a client-facing validation bypass."""

from dataclasses import dataclass

from django.db import connection

from . import mr34_teacher_spec as spec
from . import mr34_teacher_state as state
from .sbio235_state import RepairError, digest, model
from .scoping import WorkloadDenied

_ISSUER = object()


@dataclass(frozen=True)
class _ExistingOwnerAuthority:
    issuer: object
    actor_id: int
    organization_id: str
    approval_sha: str
    database_alias: str
    database_connection: object
    transaction_id: str


def _transaction_id():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_current_xact_id()::text")
        return cursor.fetchone()[0]


def issue(*, organization, user, expected_baseline):
    if (
        connection.vendor != "postgresql"
        or not connection.in_atomic_block
        or not user.is_active
        or not user.is_superuser
    ):
        raise RepairError("mr34_atomic_privileged_issuer_required")
    current = state.snapshot(organization)
    if current["phase"] != "before" or not expected_baseline or digest(current) != expected_baseline:
        raise RepairError("mr34_authority_baseline_changed")
    return _ExistingOwnerAuthority(
        _ISSUER,
        user.pk,
        str(organization.pk),
        spec.APPROVAL_SHA,
        connection.alias,
        connection.connection,
        _transaction_id(),
    )


def validate(authority, *, organization, actor, row, assignment, teacher, activity, hours, groups_note, hourly):
    pin = spec.ASSIGNMENTS.get(str(getattr(assignment, "pk", "")))
    valid = (
        isinstance(authority, _ExistingOwnerAuthority)
        and authority.issuer is _ISSUER
        and authority.actor_id == getattr(getattr(actor, "user", None), "pk", None)
        and authority.organization_id == str(organization.pk) == spec.ORG
        and authority.approval_sha == spec.APPROVAL_SHA
        and connection.in_atomic_block
        and connection.vendor == "postgresql"
        and authority.database_alias == connection.alias
        and authority.database_connection is connection.connection
        and teacher.pk == spec.CANONICAL
        and teacher.is_active
        and pin is not None
    )
    if valid:
        valid = authority.transaction_id == _transaction_id()
    if valid:
        actual = (
            model("workload.TeacherAssignment")
            .objects.filter(
                organization=organization,
                pk=assignment.pk,
                row=row,
                teacher_id=spec.OLD,
                activity=activity,
                hours=hours,
                groups_note=groups_note,
                is_hourly_paid=hourly,
            )
            .first()
        )
        valid = (
            actual is not None
            and str(row.pk) == pin["row_id"]
            and activity == pin["activity"]
            and hours == pin["hours"]
        )
    if valid:
        row_pin = spec.ROWS.get(str(row.pk), {})
        groups = sorted(str(pk) for pk in row.groups.filter(organization=organization).values_list("pk", flat=True))
        valid = groups == row_pin.get("groups") and all(
            str(getattr(row, key)) == str(value) for key, value in row_pin.items() if key != "groups"
        )
        valid = (
            valid
            and model("registrar.CourseOffering")
            .objects.filter(
                organization=organization,
                pk__in=spec.OFFERINGS,
                is_active=True,
                instructor=teacher,
                subject_id=row.subject_id,
                period_id=row.period_id,
                group_id__in=groups,
            )
            .count()
            == len(groups)
            and state.active_teacher(organization, teacher)
        )
    if not valid:
        raise WorkloadDenied("workload.reviewed_identity_invalid", "reviewed_existing_owner_authority_required")
