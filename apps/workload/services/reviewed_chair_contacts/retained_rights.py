"""Preserve ten reviewed LEGACY shares, including exact selected cohorts; never widen."""

from django.apps import apps

from ..sbio235_state import RepairError
from ..scoped_snapshot.repair_contact_rights import sha
from .retained_rights_pins import PINS

ENROLLMENT_FIELDS = (
    "id",
    "organization_id",
    "offering_id",
    "student_id",
    "status",
    "superseded_by_id",
    "source_group_id",
)


def validate(organization, offering_ids):
    selected = set(map(str, offering_ids)) & set(PINS)
    if not selected:
        return {}
    Share = apps.get_model("registrar.JournalShare")
    Enrollment = apps.get_model("registrar.Enrollment")
    result = {}
    for oid in sorted(selected):
        pin = PINS[oid]
        shares = list(Share.objects.select_for_update().filter(offering_id=oid).order_by("pk").values())
        if {str(s["id"]) for s in shares} != set(pin["shares"]):
            raise RepairError("reviewed_legacy_share_set_changed")
        for share in shares:
            if (
                share["organization_id"] != organization.pk
                or share["source"] != "legacy"
                or not share["is_active"]
                or sha(share) != pin["shares"][str(share["id"])]
            ):
                raise RepairError("reviewed_legacy_share_record_changed")
        links = list(
            Share.enrollments.through.objects.select_for_update()
            .filter(journalshare_id__in=[s["id"] for s in shares])
            .order_by("pk")
            .values()
        )
        if sha(links) != pin["through_sha256"]:
            raise RepairError("reviewed_legacy_selected_scope_changed")
        enrollments = list(
            Enrollment.objects.select_for_update()
            .filter(pk__in=[r["enrollment_id"] for r in links])
            .order_by("pk")
            .values(*ENROLLMENT_FIELDS)
        )
        if any(str(e["offering_id"]) != oid or e["organization_id"] != organization.pk for e in enrollments):
            raise RepairError("reviewed_legacy_foreign_enrollment")
        if sha(enrollments) != pin["selected_enrollments_sha256"]:
            raise RepairError("reviewed_legacy_selected_enrollment_changed")
        result[oid] = {s["teacher_id"]: set(s["kinds"]) for s in shares}
    return result


def accepts(cases, current, offering_id, expected):
    """Only fixed pins may satisfy source-kind ownership with retained restricted scopes."""
    if offering_id not in PINS:
        return False
    shares = [s for s in current["shares"] if s["offering_id"] == offering_id]
    actual = {s["teacher_id"]: set(s["kinds"]) for s in shares if s["is_active"] and s["source"] == "legacy"}
    return actual == expected and {s["id"] for s in shares} == set(PINS[offering_id]["shares"])
