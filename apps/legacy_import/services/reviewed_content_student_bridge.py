"""One reviewed institutional identity, never a general ledger fallback."""

from uuid import UUID

from django.apps import apps

from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG

SOURCE_STUDENT = 10928
USER = 11334
TARGET = "1206a0f5-1483-4b67-b820-9f976f335231"
GROUP = "12c1ba2a-b7ee-4e2f-a31c-64bccaeb71bf"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SUBJECT = "dd392764-9e62-5284-89e6-86169a2b510e"


def reviewed_student_bridge(data, mappings, *, lock=False):
    """Fill the sole proven missing map; immutable ledger conflicts remain fatal."""
    if not any(p["student_id"] == SOURCE_STUDENT for p in data["points"]):
        return
    key = str(SOURCE_STUDENT)
    if TARGET not in data["selected_target_ids"]:
        raise ContentError("reviewed_student_target_mismatch")
    students = [s for s in data["students"] if s["id"] == SOURCE_STUDENT]
    if len(students) != 1 or students[0]["group_id"] != 829:
        raise ContentError("reviewed_student_source_group_mismatch")
    if mappings.get(key) and mappings[key] != {str(USER)}:
        raise ContentError("reviewed_student_ledger_conflict")
    Profile = apps.get_model("accounts.UserProfile")
    profiles = Profile.objects.filter(institutional_identifier=key)
    if lock:
        profiles = profiles.select_for_update()
    profiles = list(profiles.select_related("user"))
    if len(profiles) != 1:
        raise ContentError("reviewed_student_identifier_not_unique")
    profile = profiles[0]
    if str(profile.organization_id) != ORG or profile.access_state != "active":
        raise ContentError("reviewed_student_account_scope_changed")
    user = profile.user
    if (user.pk, user.username, user.first_name, user.last_name, profile.patronymic, user.is_active) != (
        USER,
        "salman.zeynalov",
        "Salman",
        "Zeynalov",
        "Sarvan",
        True,
    ):
        raise ContentError("reviewed_student_exact_identity_changed")
    Academic = apps.get_model("registrar.StudentAcademicRecord")
    records = Academic.objects.filter(organization_id=ORG, student_id=USER, is_active=True, status="enrolled")
    if lock:
        records = records.select_for_update()
    if list(records.values_list("group_id", flat=True)) != [UUID(GROUP)]:
        raise ContentError("reviewed_student_current_group_changed")
    Offering = apps.get_model("registrar.CourseOffering")
    if not Offering.objects.filter(
        pk=TARGET, organization_id=ORG, group_id=GROUP, period_id=PERIOD, subject_id=SUBJECT, is_active=True
    ).exists():
        raise ContentError("reviewed_student_offering_changed")
    Enrollment = apps.get_model("registrar.Enrollment")
    if (
        Enrollment.objects.filter(
            organization_id=ORG, offering_id=TARGET, student_id=USER, status="enrolled", superseded_by__isnull=True
        ).count()
        != 1
    ):
        raise ContentError("reviewed_student_exact_enrollment_missing")
    mappings[key] = {str(USER)}
