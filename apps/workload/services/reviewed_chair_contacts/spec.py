"""Four exact source-backed courses; no arbitrary identities or source payloads accepted."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
TEACHER_IDENTITIES = {
    7824: "a6d07debe0ef893fc44705db1ee17cfab537be3cddf07740531febed20efbd9b",
    7885: "c9ef5e52aad853479e7d2b37791dec4df240ce03caf1a8249675fbbd37836af3",
    7958: "e18f3a07a066f88ea37ab720954d2547309e6209119f6aeea4cf735bddbb1596",
    9524: "107c564367377a7378e64ce7a927fccce7d76cdd39a120ad72eeb3d2f8d4c44f",
    9526: "7a44c58c6ccfd4febf017727194f16f14f5662f9d05d36feae0506a168e7bf15",
}
GROUP_IDENTITIES = {
    "3e4c8e6c-4049-44cd-a0fe-7d79c02a1a97": "cf4c905ef909152f9f9a89c012b5f621877e10a248a89a4c23331441538d5f6e",
    "4e5ad122-f2a9-4685-9fcb-45f4f9e05d4c": "ed36b66e0d6dffcec6f2164e079e53aa6b8b24cda69494be3996ce58a8659eee",
    "646c17d7-9b3b-4ac2-8d19-bb262842f5c4": "7ac6b4d2f8b9eb34857016996bd2b6d16187c0dca95386573479c3bdc4e976d0",
    "aba7f830-e116-4d2f-b0c6-e165da2bd495": "13c945085147e5f1e69659ccc9e2ea16626431b8b01faea20a100d40592642a6",
    "be2992ad-529a-46b6-be1a-8a469f708265": "cf806fe2063f3524e8d41dab56d33df22468b25cabfd4dca3a1767b60f222a18",
    "bf9986dc-1366-4a42-8ba0-f9e7636ec78c": "8db9123cd7a1f7676c3fdf01a23ee479c2eb56db851dddc95c015966f556ab24",
}
TASK_CHAIRS = {
    "2e350e27-745c-42bd-9ca8-128041007ca3": "14a08ffe-b0e5-4433-a1af-e787e057a4be",
    "45b29907-4290-4028-bea7-943599cb0b48": "ce2798eb-18fd-47c1-9920-f3fd9af5e436",
}
CASES = {
    "az_morphology": {
        "offerings": {
            "4fee5132-a7ff-4f9f-b4d9-93c22f54bdfc": {
                "group_id": "646c17d7-9b3b-4ac2-8d19-bb262842f5c4",
                "new_hours": 105,
                "new_owner": 7824,
                "old_hours": 210,
                "old_owner": 7824,
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "65ba3bf6-7875-460f-aafb-1776c24baf3c",
            },
            "dfb06cc3-4b48-47ea-a90d-d15ef5e840ca": {
                "group_id": "3e4c8e6c-4049-44cd-a0fe-7d79c02a1a97",
                "new_hours": 105,
                "new_owner": 7824,
                "old_hours": 210,
                "old_owner": 7824,
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "65ba3bf6-7875-460f-aafb-1776c24baf3c",
            },
        },
        "plan_hours": {"lecture": 45, "seminar": 60},
        "rows": [
            {
                "assignments": [
                    {
                        "id": "fb8985db-5cef-4b25-992b-27a23fb1d2d8",
                        "new": {"activity": "lecture", "hours": 45, "is_hourly_paid": False, "teacher_id": 7824},
                        "old": {"activity": "lecture", "hours": 105, "is_hourly_paid": False, "teacher_id": 7824},
                    }
                ],
                "groups": ["3e4c8e6c-4049-44cd-a0fe-7d79c02a1a97", "646c17d7-9b3b-4ac2-8d19-bb262842f5c4"],
                "id": "8281b25e-4b35-42a7-8073-bf5f06f8cf19",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 45,
                    "lecture_total": 45,
                    "seminar_plan": 0,
                    "seminar_total": 0,
                    "subgroup_count": 1,
                    "total_hours": 45,
                    "union_count": 2,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 105,
                    "lecture_total": 105,
                    "seminar_plan": 0,
                    "seminar_total": 0,
                    "subgroup_count": 1,
                    "total_hours": 105,
                    "union_count": 2,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "65ba3bf6-7875-460f-aafb-1776c24baf3c",
                "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
            },
            {
                "assignments": [
                    {
                        "id": "66bfe5d5-ba0a-4208-af39-2820481222ff",
                        "new": {"activity": "seminar", "hours": 60, "is_hourly_paid": False, "teacher_id": 7958},
                        "old": {"activity": "seminar", "hours": 105, "is_hourly_paid": False, "teacher_id": 7824},
                    }
                ],
                "groups": ["3e4c8e6c-4049-44cd-a0fe-7d79c02a1a97"],
                "id": "265c729b-a707-4915-99b7-d96228d43727",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 60,
                    "seminar_total": 60,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 1,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 105,
                    "seminar_total": 105,
                    "subgroup_count": 1,
                    "total_hours": 105,
                    "union_count": 1,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "65ba3bf6-7875-460f-aafb-1776c24baf3c",
                "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
            },
            {
                "assignments": [
                    {
                        "id": "864a1fe1-4db1-4786-845a-9c72ec056728",
                        "new": {"activity": "seminar", "hours": 60, "is_hourly_paid": False, "teacher_id": 7958},
                        "old": {"activity": "seminar", "hours": 105, "is_hourly_paid": False, "teacher_id": 7824},
                    }
                ],
                "groups": ["646c17d7-9b3b-4ac2-8d19-bb262842f5c4"],
                "id": "027319eb-b525-4ea0-b284-0f884c664876",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 60,
                    "seminar_total": 60,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 1,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 105,
                    "seminar_total": 105,
                    "subgroup_count": 1,
                    "total_hours": 105,
                    "union_count": 1,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "65ba3bf6-7875-460f-aafb-1776c24baf3c",
                "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
            },
        ],
        "source": {"lines": [2, 19], "sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff"},
    },
    "az_onomastics": {
        "offerings": {
            "0ad85d3e-a9a3-480e-926a-68a384cb2435": {
                "group_id": "bf9986dc-1366-4a42-8ba0-f9e7636ec78c",
                "new_hours": 60,
                "new_owner": 7824,
                "old_hours": 90,
                "old_owner": 9526,
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "4b9f247f-a2db-4c8a-b42a-125c8418f614",
            },
            "e3071d54-4e9a-48fb-8243-5fcd293f590e": {
                "group_id": "aba7f830-e116-4d2f-b0c6-e165da2bd495",
                "new_hours": 60,
                "new_owner": 7824,
                "old_hours": 90,
                "old_owner": 9526,
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "4b9f247f-a2db-4c8a-b42a-125c8418f614",
            },
        },
        "plan_hours": {"lecture": 30, "seminar": 30},
        "rows": [
            {
                "assignments": [
                    {
                        "id": "959eb800-5749-4e1c-a694-e10d0f344739",
                        "new": {"activity": "lecture", "hours": 30, "is_hourly_paid": False, "teacher_id": 7824},
                        "old": {"activity": "lecture", "hours": 30, "is_hourly_paid": False, "teacher_id": 9526},
                    },
                    {
                        "id": "b638c1c5-6472-4990-af7b-3377880f05fc",
                        "new": None,
                        "old": {"activity": "seminar", "hours": 30, "is_hourly_paid": False, "teacher_id": 9526},
                    },
                ],
                "groups": ["aba7f830-e116-4d2f-b0c6-e165da2bd495", "bf9986dc-1366-4a42-8ba0-f9e7636ec78c"],
                "id": "58ec1394-7d32-4c2d-ab60-771da1a6d313",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 30,
                    "lecture_total": 30,
                    "seminar_plan": 0,
                    "seminar_total": 0,
                    "subgroup_count": 1,
                    "total_hours": 30,
                    "union_count": 2,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 30,
                    "lecture_total": 30,
                    "seminar_plan": 30,
                    "seminar_total": 30,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 2,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "4b9f247f-a2db-4c8a-b42a-125c8418f614",
                "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
            },
            {
                "assignments": [
                    {
                        "id": "fe8f455b-7a3c-4863-a38f-1dc7859df41e",
                        "new": {"activity": "seminar", "hours": 30, "is_hourly_paid": False, "teacher_id": 9526},
                        "old": {"activity": "seminar", "hours": 60, "is_hourly_paid": False, "teacher_id": 9526},
                    }
                ],
                "groups": ["bf9986dc-1366-4a42-8ba0-f9e7636ec78c"],
                "id": "21a4f570-69e4-4dc3-ad8c-f79e2626ed57",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 30,
                    "seminar_total": 30,
                    "subgroup_count": 1,
                    "total_hours": 30,
                    "union_count": 1,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 60,
                    "seminar_total": 60,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 1,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "4b9f247f-a2db-4c8a-b42a-125c8418f614",
                "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
            },
            {
                "assignments": [
                    {
                        "id": "41b3ef4a-62ce-4d36-9bc1-da9e23697de9",
                        "new": {"activity": "seminar", "hours": 30, "is_hourly_paid": False, "teacher_id": 9526},
                        "old": {"activity": "seminar", "hours": 60, "is_hourly_paid": False, "teacher_id": 9526},
                    }
                ],
                "groups": ["aba7f830-e116-4d2f-b0c6-e165da2bd495"],
                "id": "5ceb6d74-c634-46c3-bf09-ec9abfdc3824",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 30,
                    "seminar_total": 30,
                    "subgroup_count": 1,
                    "total_hours": 30,
                    "union_count": 1,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 0,
                    "lecture_total": 0,
                    "seminar_plan": 60,
                    "seminar_total": 60,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 1,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "4b9f247f-a2db-4c8a-b42a-125c8418f614",
                "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
            },
        ],
        "source": {"lines": [3, 60], "sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff"},
    },
    "tarix_europe": {
        "offerings": {
            "7effa191-f9c6-420c-9a6d-bd2b75f872a7": {
                "group_id": "be2992ad-529a-46b6-be1a-8a469f708265",
                "new_hours": 60,
                "new_owner": 7885,
                "old_hours": 90,
                "old_owner": 7885,
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "ebd209c7-398f-4260-85fe-28a2d088315a",
            }
        },
        "plan_hours": {"lecture": 30, "seminar": 30},
        "rows": [
            {
                "assignments": [
                    {
                        "id": "411607ee-d99e-46df-abf8-fb8f62d60f2c",
                        "new": {"activity": "seminar", "hours": 30, "is_hourly_paid": False, "teacher_id": 7885},
                        "old": {"activity": "seminar", "hours": 30, "is_hourly_paid": False, "teacher_id": 7885},
                    },
                    {
                        "id": "a46c43a6-50f9-43fd-8dec-5ad828650a9b",
                        "new": {"activity": "lecture", "hours": 30, "is_hourly_paid": False, "teacher_id": 7885},
                        "old": {"activity": "lecture", "hours": 30, "is_hourly_paid": False, "teacher_id": 7885},
                    },
                ],
                "groups": ["be2992ad-529a-46b6-be1a-8a469f708265"],
                "id": "10e7fb5e-7967-4fd3-916f-49aaecf1b826",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 30,
                    "lecture_total": 30,
                    "seminar_plan": 30,
                    "seminar_total": 30,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 1,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 30,
                    "lecture_total": 30,
                    "seminar_plan": 60,
                    "seminar_total": 30,
                    "subgroup_count": 1,
                    "total_hours": 60,
                    "union_count": 1,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "ebd209c7-398f-4260-85fe-28a2d088315a",
                "task_id": "2e350e27-745c-42bd-9ca8-128041007ca3",
            }
        ],
        "source": {"lines": [45], "sha256": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d"},
    },
    "tarix_region": {
        "offerings": {
            "86236c69-0011-46e3-88a4-0e5124290d0f": {
                "group_id": "4e5ad122-f2a9-4685-9fcb-45f4f9e05d4c",
                "new_hours": 90,
                "new_owner": 7885,
                "old_hours": 150,
                "old_owner": 7885,
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "f5411cd5-510d-43bd-9093-5199ebc31ccc",
            }
        },
        "plan_hours": {"lecture": 60, "seminar": 30},
        "rows": [
            {
                "assignments": [
                    {
                        "id": "25df60cc-76c9-4ef7-8fc6-6c0b43fa6e62",
                        "new": {"activity": "lecture", "hours": 60, "is_hourly_paid": False, "teacher_id": 7885},
                        "old": {"activity": "lecture", "hours": 60, "is_hourly_paid": False, "teacher_id": 7885},
                    },
                    {
                        "id": "a7a419dc-36fc-4521-93fd-d1bc3417353b",
                        "new": {"activity": "seminar", "hours": 30, "is_hourly_paid": True, "teacher_id": 9524},
                        "old": {"activity": "seminar", "hours": 90, "is_hourly_paid": False, "teacher_id": 7885},
                    },
                ],
                "groups": ["4e5ad122-f2a9-4685-9fcb-45f4f9e05d4c"],
                "id": "8207e13d-d046-4bd4-bfc2-6889ba4637e1",
                "new": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 60,
                    "lecture_total": 60,
                    "seminar_plan": 30,
                    "seminar_total": 30,
                    "subgroup_count": 1,
                    "total_hours": 90,
                    "union_count": 1,
                },
                "old": {
                    "lab_plan": 0,
                    "lab_total": 0,
                    "lecture_plan": 60,
                    "lecture_total": 60,
                    "seminar_plan": 90,
                    "seminar_total": 90,
                    "subgroup_count": 1,
                    "total_hours": 150,
                    "union_count": 1,
                },
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "subject_id": "f5411cd5-510d-43bd-9093-5199ebc31ccc",
                "task_id": "2e350e27-745c-42bd-9ca8-128041007ca3",
            }
        ],
        "source": {"lines": [47, 90], "sha256": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d"},
    },
}
