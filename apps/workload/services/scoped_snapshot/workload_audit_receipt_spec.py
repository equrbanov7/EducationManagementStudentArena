"""Only four immutable-byte reviewed workload receipts, never a resource-prefix exemption."""

PINS = {
    "005343b3-adcb-4774-a03e-792259cd89af": (
        "reviewed",
        "cf3d1f1ad0e5bb2a189bd4622a538f3750a245b419723a5fc6e0effd25ca6435",
    ),
    "528a2d9e-04d7-4638-9a45-4d519e30cdc8": (
        "reviewed",
        "f8be165ac662cf95fff77283db03c50adddda3effc1d9b7fc44a6674e3b52b8f",
    ),
    "9e7e623d-562a-4b06-b4e2-2cb0d1842292": (
        "owner",
        "3966f2e5c0aa8ea317aab0de1621c7fe6e6bd61ae684aac7bdeef11319fa5868",
    ),
    "ba4a6e4a-3c10-409a-9c51-f3f4ba9c3ba8": (
        "reviewed",
        "9f96efd4d3e410ea937b4d507dbd1bd4523d49a20285569323358b04822ff135",
    ),
}
FAMILIES = {
    "reviewed": ("workload.reviewed_source_batch", "workload.reviewed_source_batch"),
    "owner": ("workload.owner_activity_batch", "workload.fixed_owner_activity_source_batch"),
}
ACADEMIC = tuple(
    sorted(
        "offering lesson enrollment syllabus journal_share handover mark selfwork_topic selfwork componentscore criterionscore coursework finalgrade resitrecord assessmentscheme assessmentcomponent scheduleslot syllabus_share version section review".split()
    )
)
BEFORE = {
    "reviewed": tuple(
        sorted(
            "selection extensions electives tasks rows offerings groups periods programs subjects memberships roles teachers profiles history academic".split()
        )
    ),
    "owner": tuple(sorted("selection tasks rows groups periods history".split())),
}
TOP = {
    "reviewed": tuple(
        sorted(
            "selection_sha manifest_sha256 kind before_baseline after_baseline before details protected_academic".split()
        )
    ),
    "owner": tuple(
        sorted(
            "kind source_manifest_sha256 selection_sha256 selected_rows before_baseline after_baseline before created_assignment_ids academic_before_after".split()
        )
    ),
}
DETAILS = tuple(
    sorted(
        "created_row_ids changed_row_ids metadata_group_ids created_subject_ids created_membership_ids handover_ids detached_objection_provenance created_offering_ids created_share_ids".split()
    )
)
JSON_SQL_POLICY = "postgres-jsonb-text-utf8-sha256/1"
JSON_PYTHON_POLICY = "python-json-ascii-sorted-compact-sha256/1"
ROW_SQL_POLICY = "postgres-row_to_json-text-utf8-sha256/1"
MAX_THIN_BYTES = 16384

# Same authenticated server-side SQL field hashes; never substitute Python JSON hashes.
FIELD_PINS = {
    "005343b3-adcb-4774-a03e-792259cd89af": {
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "new_values_sha256": "34eb2434bf8f3bdd5605ef6427dadc7901fa46513dfd0066f5389c1aec67b381",
        "changes_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "resource_id_sha256": "7e95909d2ce4ff11ee5c029d2b0b0db21825049314a4b7dd7c801d3802533a66",
        "source_raw_bytes": 624693,
    },
    "528a2d9e-04d7-4638-9a45-4d519e30cdc8": {
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "new_values_sha256": "48c54b81cf19c6fd5127bb4dae97ac8f921c002aead1a1da16ab6ddb8a426260",
        "changes_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "resource_id_sha256": "2219defaab0a579292dba9848a93602b4de155a584219d7e24c20aa428df8bf8",
        "source_raw_bytes": 2023330,
    },
    "9e7e623d-562a-4b06-b4e2-2cb0d1842292": {
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "new_values_sha256": "06c68250a317309b3dda3a294031d3f89cdca61fdffccbf70aef9a9c9cb5ec7c",
        "changes_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "resource_id_sha256": "7d8edb5d3746d3ad629f177330e72879e1fa2e7bcc1056d775cc30625c3ffa03",
        "source_raw_bytes": 2047819,
    },
    "ba4a6e4a-3c10-409a-9c51-f3f4ba9c3ba8": {
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "new_values_sha256": "257e35890f563dfb85ba8e41a644bdb0193cb276bf79e3499501d1ab9632cdf3",
        "changes_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "resource_id_sha256": "860cc84a6a2713d1c1ebbaca8dea2ce3ddc83870b953e23a686f155a6b94609b",
        "source_raw_bytes": 2601318,
    },
}

# Authenticated diagnostic 41326871426 (8c06e8a527d8): closed historic schemas.
WITHOUT_ELECTIVES = ("ba4a6e4a-3c10-409a-9c51-f3f4ba9c3ba8",)
WITHOUT_PROVENANCE = (
    "005343b3-adcb-4774-a03e-792259cd89af",
    "528a2d9e-04d7-4638-9a45-4d519e30cdc8",
    "ba4a6e4a-3c10-409a-9c51-f3f4ba9c3ba8",
)
