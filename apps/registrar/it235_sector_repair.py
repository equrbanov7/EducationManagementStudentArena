"""Two source-evidenced sector transfers; historical marks remain unchanged."""

import hashlib
import json

from django.apps import apps
from django.db import transaction

from .models import Enrollment, LessonMark, StudentAcademicRecord
from .transfer import transfer_student_group

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
SOURCE = "2b471dec-7783-49f1-b17e-cb9acae77f31"
TARGET = "eee00e67-ca42-48b9-8217-dd03027855aa"
PEOPLE = {6794: ("9049", "Ramin"), 6831: ("9086", "Anar")}


class RepairError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline=""):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise RepairError("fixed_scope_active_superadmin_required")
    Group = apps.get_model("organizations", "OrgUnit")
    Profile = apps.get_model("accounts", "UserProfile")
    target = Group.objects.get(pk=TARGET, organization=organization, is_active=True)
    if (target.settings or {}).get("sector") != "en":
        raise RepairError("target_sector_changed")
    period = organization.academic_periods.get(is_current=True, is_active=True)
    records = list(
        StudentAcademicRecord.objects.select_for_update()
        .filter(organization=organization, student_id__in=PEOPLE, is_active=True, status="enrolled")
        .order_by("student_id")
    )
    if len(records) != 2 or {r.student_id for r in records} != set(PEOPLE):
        raise RepairError("exact_active_student_records_required")
    for record in records:
        profile = Profile.objects.get(organization=organization, user_id=record.student_id)
        identifier, patronymic = PEOPLE[record.student_id]
        if str(profile.institutional_identifier) != identifier or profile.patronymic.strip() != patronymic:
            raise RepairError("source_student_identity_changed")
        if str(record.group_id) not in (SOURCE, TARGET):
            raise RepairError("unexpected_current_group")
    enrollments = Enrollment.objects.filter(organization=organization, student_id__in=PEOPLE)
    marks = LessonMark.objects.filter(organization=organization, enrollment__student_id__in=PEOPLE)
    before_marks = list(marks.order_by("pk").values())
    old_ids = set(enrollments.values_list("pk", flat=True))
    baseline = digest(
        {
            "records": [(r.pk, r.student_id, r.group_id) for r in records],
            "enrollments": list(enrollments.order_by("pk").values()),
            "marks": before_marks,
        }
    )
    if expected_baseline and expected_baseline != baseline:
        raise RepairError("live_baseline_changed")
    pending = sum(str(r.group_id) != TARGET for r in records)
    if not apply:
        return {"baseline": baseline, "pending": pending}
    if not expected_baseline:
        raise RepairError("fresh_baseline_required")
    for record in records:
        transfer_student_group(
            record=record,
            new_group=target,
            period=period,
            by_user=user,
            reason="235 İT az→ing: mənbə tələbə 9049/9086, oktyabr ingilis jurnalları ilə təsdiqlənib",
        )
    if list(marks.order_by("pk").values()) != before_marks or not old_ids.issubset(
        set(enrollments.values_list("pk", flat=True))
    ):
        raise RepairError("historical_academic_content_changed")
    return {"baseline": baseline, "applied": pending}
