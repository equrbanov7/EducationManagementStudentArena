"""Bounded read-only evidence for historical duplicate and sector repairs."""

from django.apps import apps

from .data import ORG

COLLISIONS = (
    "038d9147-cbe4-4494-b664-c219419e38d5",
    "5c1f6e6d-44f1-4321-a28f-9fc87ed6070c",
    "8337fd0a-0515-445d-bf7d-a364eee43019",
    "d27f9a35-cfcf-4e51-a69f-ece59e346c4e",
)


def collect_repair_evidence():
    Slot = apps.get_model("registrar", "ScheduleSlot")
    Profile = apps.get_model("accounts", "UserProfile")
    Record = apps.get_model("registrar", "StudentAcademicRecord")
    profiles = Profile.objects.filter(organization_id=ORG, institutional_identifier__in=("9049", "9086"))
    return {
        "repair_ke233_slots": list(
            Slot.objects.filter(organization_id=ORG, offering_id__in=COLLISIONS).order_by("pk").values()
        ),
        "repair_sector_profiles": list(
            profiles.order_by("user_id").values("user_id", "institutional_identifier", "patronymic")
        ),
        "repair_sector_records": list(
            Record.objects.filter(organization_id=ORG, student_id__in=profiles.values("user_id"))
            .order_by("pk")
            .values("id", "student_id", "group_id", "program_id", "is_active", "status")
        ),
    }
