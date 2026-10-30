"""Frozen, reviewed MyEdu home-group identities; no name-based student discovery."""

from collections import Counter
from dataclasses import dataclass

from .legacy_roster_contracts import SI135, TSPX, Family
from .reviewed_batch_manifest import read_manifest
from .sbio235_state import RepairError

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
PARENT = "a163b409-dc4f-4454-91fb-9f09309e50df"
TARGETS = {
    927: "14afed62-6d55-4cdc-b58d-c1407a909859",
    929: "cc3dc2da-f694-4674-965f-2857c3fa7ac3",
}
SOURCE_SHA = "c64affd5268a60e987b23749770db5d841002e5645c02b1461d6098a833db888"
MANIFEST_SHA = "c6eb79792406c3ddc51d842cae767f88a9035a26a3c29eb3696870f560af23bb"
SI135_MANIFEST_SHA = SI135.manifest_sha
RESOURCE = "workload.tspx_legacy_roster"


@dataclass
class Plan:
    sha256: str
    candidates: list
    retain: list
    family: Family = TSPX

    @property
    def people(self):
        return self.candidates + self.retain

    @property
    def user_ids(self):
        return {p["target_user_id"] for p in self.people}

    @property
    def record_ids(self):
        return {p["expected_record_id"] for p in self.people}


def read_plan(path, sha256):
    return _read_family(path, sha256, TSPX, MANIFEST_SHA)


def read_si135_plan(path, sha256):
    return _read_family(path, sha256, SI135, SI135_MANIFEST_SHA)


def _read_family(path, sha256, family, expected_sha):
    if family not in (TSPX, SI135) or sha256 != expected_sha:
        raise RepairError("fixed_reviewed_tspx_manifest_sha_required")
    value = read_manifest(path, sha256)
    if (
        value.get("format") != "reviewed-canonical-student-subgroup-transfer-plan/1"
        or value.get("organization_id") != ORG
        or value.get("academic_year") != "2026/2027"
        or value.get("period_id") != PERIOD
        or value.get("source_sql_sha256") != SOURCE_SHA
        or value.get("source_parent_current_group_id") != family.parent
        or value.get("source_parent_legacy_group_id") != family.legacy_parent
        or value.get("source_target_groups") != {str(k): v for k, v in family.targets.items()}
    ):
        raise RepairError("fixed_tspx_source_scope_required")
    candidates, retain = value["candidates"], value["retain_parent"]
    plan = Plan(sha256, candidates, retain, family)
    if (
        len(candidates) != family.moves
        or len(retain) != 1
        or len(plan.user_ids) != family.moves + 1
        or len(plan.record_ids) != family.moves + 1
        or len({p["legacy_student_id"] for p in plan.people}) != family.moves + 1
        or Counter(p["source_home_group_id"] for p in candidates) != family.counts
    ):
        raise RepairError("fixed_tspx_source_partition_required")
    for person in plan.people:
        if (
            person["source_system"] != "myedu_mariadb"
            or person["clone_record_source_group_id"] != family.parent
            or person["keep_admission_year"] != 2025
            or not isinstance(person["target_user_id"], int)
            or isinstance(person["target_user_id"], bool)
            or person["target_user_id"] <= 0
        ):
            raise RepairError("fixed_tspx_student_identity_required")
    if retain[0]["source_home_group_id"] != family.legacy_parent or any(
        p["target_group_id"] != family.targets.get(p["source_home_group_id"]) for p in candidates
    ):
        raise RepairError("fixed_tspx_child_membership_required")
    return plan
