"""Two fixed existing journals; four absent source cells, never lesson synthesis."""

SOURCE_SHA = "00fd00569b1a1af9460c57db647313622a70b0026d06716cf3843311d490ba1f"
PAYLOAD_DIGEST = "4a5d8c646886f722b80729ac5f5794fd6912caf1a989a2273d7f1c3fecbbd95d"
SOURCE_REVIEW_SHA = "0427f147d86af86860c9524682aed0b7406f1af181fe331b4b633e8b8b26c34d"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TARGETS = {
    "b9add126-024d-4865-97b4-26abdfbd3193": {
        "group_id": "3e4c8e6c-4049-44cd-a0fe-7d79c02a1a97",
        "subject_id": "6d3ff61d-d2f8-4757-a1e6-28a09009b86f",
        "teacher_id": 7723,
        "journal_id": 14211,
        "journal_uniqid": "NcAA2ymEa8",
        "legacy_group_id": 812,
        "legacy_subject_id": 5,
        "legacy_teacher_id": 23,
        "period_id": PERIOD,
        "selection_id": 0,  # Existing exact lesson, not a new workload-row claim.
        "special": False,
    },
    "03ac22fc-5153-4e27-bec2-c804373c612f": {
        "group_id": "9ea0c8df-cbcc-4dd3-8105-5efe0a10c89f",
        "subject_id": "1b94fb52-7511-4ffd-a477-612b6d184a31",
        "teacher_id": 8163,
        "journal_id": 14302,
        "journal_uniqid": "knqwDXQuIs",
        "legacy_group_id": 765,
        "legacy_subject_id": 1493,
        "legacy_teacher_id": 713,
        "period_id": PERIOD,
        "selection_id": 0,
        "special": False,
    },
}
CASES = {
    5458056: (
        "b9add126-024d-4865-97b4-26abdfbd3193",
        "9e98944b-3260-4a7e-ad42-97e474265e80",
        "fdf331ec-a9c7-41bd-b610-b9dd6887d3d3",
        9354,
        7098,
        "2026-10-07",
        "13:35:00",
    ),
    5558632: (
        "03ac22fc-5153-4e27-bec2-c804373c612f",
        "e2eaa0ba-19a0-4acf-a068-60a66a58b578",
        "33f96d1b-b541-439d-aaae-28a6ef1d40c4",
        8220,
        5966,
        "2026-10-20",
        "15:15:00",
    ),
    5558637: (
        "03ac22fc-5153-4e27-bec2-c804373c612f",
        "e2eaa0ba-19a0-4acf-a068-60a66a58b578",
        "7c90c7f4-1243-41fc-a3a0-d0b3664892c9",
        8222,
        5968,
        "2026-10-20",
        "15:15:00",
    ),
    5558643: (
        "03ac22fc-5153-4e27-bec2-c804373c612f",
        "e2eaa0ba-19a0-4acf-a068-60a66a58b578",
        "744b05f8-d427-4ff3-820b-4c40103145ab",
        8247,
        5993,
        "2026-10-20",
        "15:15:00",
    ),
}
# Canonical16-field source projection, not a claim about physical DB immutability.
ROW_HASHES = {
    5458056: "f494d3470eee408603c53f3f03efea4cacd35ad232faf55bc7f6d5e32d8fd2a2",
    5558632: "ebc7b4a662e8ffde18184aa83d1d86cfdd65bfefc49e1245f2ba7e63c4b1ea4b",
    5558637: "c6863a9e3471ca87f0b257a20b48045245aeb3e0f7b43c06cd38db6a69a1612d",
    5558643: "fd6578092a1b2a83f9bcc68930fca6482dd0ad487c06471b19f9ae1f21ec1f58",
}
