"""Two sealed families and 41 reviewed GUI/source identities, without ledger invention."""

import html
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .legacy_roster_contracts import Family
from .reviewed_batch_manifest import read_manifest
from .sbio235_state import RepairError

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
MANIFEST_SHA = "a7d0870a8da05cfc617e1756c03db9c46366cef8bc4ed6a4dd6e82bc4b64fd4f"
SOURCE_SQL_SHA = "c64affd5268a60e987b23749770db5d841002e5645c02b1461d6098a833db888"
SOURCE_ROWS_SHA = "f4a12bc0690350b617b86327700b8fc55b24d4ff3a7997c70f6981fb0abcb827"
GUI_SHA = "a2e865661f2106de990bb424c9d6f044fe53760955ff5fcfcef5ad245393a8b9"
RESOURCE = "workload.bi_mu536_legacy_roster"
PREFIX = "bimu536-roster"
EXCLUDED = {10655, 10066, 10067}
BI = Family(
    "bi536",
    "b7bc07b8-c91f-47fb-bd38-f712ae99c1db",
    918,
    ((965, "e49610ef-4b19-4baf-a8d7-63df36495908", 0), (966, "69eb55b0-c261-4dea-ad65-7bf04dc4e32e", 20)),
    MANIFEST_SHA,
    "536bi",
    PREFIX,
    RESOURCE,
    "536 Bİ",
)
MU = Family(
    "mu536",
    "34c8a15b-a491-4374-94e7-e71f1116b82c",
    0,
    ((900, "6a7657ff-ae69-4fb9-9435-2a4648b99fcf", 21), (898, "4cd7199f-ea7d-497c-a517-109eb7ce8448", 0)),
    MANIFEST_SHA,
    "536mu",
    PREFIX,
    RESOURCE,
    "536 MU",
)
FAMILIES = (BI, MU)
GEOMETRY = {
    BI.name: {
        "specialty": "0e7f196d-3f73-423b-a566-4386a5d43ab3",
        "names": ("536 Bİ", "536 Bi 1", "536 Bİ2"),
        "program": "6004002",
        "source_child": 966,
    },
    MU.name: {
        "specialty": "4e9aa113-32f3-41e0-8989-42ded47812e4",
        "names": ("536 MU", "536 MU1", "536 MU2"),
        "program": "6004008",
        "source_child": 900,
    },
}


def normalized(value):
    """Case/spacing only; retain accent and spelling differences."""
    if not isinstance(value, str):
        raise RepairError("bi_mu_identity_text_required")
    return " ".join(unicodedata.normalize("NFKC", html.unescape(value)).upper().replace("İ", "I").split())


def identity(value):
    if not isinstance(value, dict) or set(value) != {"first_name", "last_name", "patronymic"}:
        raise RepairError("bi_mu_full_three_identity_required")
    values = [normalized(value[key]) for key in ("first_name", "last_name", "patronymic")]
    values[2] = re.sub(r"\s+(OĞLU|QIZI)$", "", values[2])
    if not all(values):
        raise RepairError("bi_mu_full_three_identity_required")
    return tuple(values)


@dataclass(frozen=True)
class Plan:
    sha256: str
    candidates: tuple


def read_plan(path, sha256):
    if sha256 != MANIFEST_SHA:
        raise RepairError("fixed_bi_mu536_manifest_sha_required")
    value = read_manifest(path, sha256)
    return parse(value, sha256)


def parse(value, sha256):
    if (
        sha256 != MANIFEST_SHA
        or value.get("format") != "reviewed-bi-mu536-liveidentity-roster/1"
        or value.get("organization_id") != ORG
        or value.get("academic_year") != "2026/2027"
        or value.get("period_id") != PERIOD
        or value.get("source_sql_sha256") != SOURCE_SQL_SHA
        or value.get("source_rows_sha256") != SOURCE_ROWS_SHA
        or value.get("live_gui_evidence_sha256") != GUI_SHA
        or set(value.get("excluded_source_ids", [])) != EXCLUDED
    ):
        raise RepairError("fixed_bi_mu536_source_scope_required")
    people = value.get("candidates", [])
    if (
        len(people) != 41
        or Counter(p.get("source_home_group_id") for p in people) != {966: 20, 900: 21}
        or len({p.get("legacy_student_id") for p in people}) != 41
        or len({p.get("current_username") for p in people}) != 41
    ):
        raise RepairError("fixed_bi_mu536_source_partition_required")
    for person in people:
        family = BI if person["source_home_group_id"] == 966 else MU
        spec = GEOMETRY[family.name]
        if (
            type(person.get("legacy_student_id")) is not int
            or person["legacy_student_id"] <= 0
            or person["legacy_student_id"] in EXCLUDED
            or person.get("source_entry_year") != 2026
            or person.get("keep_admission_year") != 2026
            or person.get("program_official_code") != spec["program"]
            or person.get("current_parent_group_name") != spec["names"][0]
            or not isinstance(person.get("current_username"), str)
            or not re.fullmatch(r"[a-z0-9_.-]{1,150}", person["current_username"])
            or identity(person.get("source_identity")) != identity(person.get("current_identity"))
        ):
            raise RepairError("fixed_bi_mu536_reviewed_identity_required")
    return Plan(sha256, tuple(people))
