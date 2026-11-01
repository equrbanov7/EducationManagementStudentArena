"""MR-000034 explicitly approved duplicate identity; exact existing IDs only."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"

YEAR = "2026/2027"

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"

CHAIR = "ce2798eb-18fd-47c1-9920-f3fd9af5e436"

OLD = 11588

CANONICAL = 9510

APPROVAL_SHA = "fbdce9adf89e3b0af72afbc64e7f5face1743edce7cf225cbfa4f649b7bcf934"

IDENTITY_HASHES = {
    9510: "d0798ed85ebd51fa329f8bf46957121291f3d834e71b6efc839223937e77fb69",
    11588: "9717ae2c5841dd2305e10a15a476832fdd322b4d7de7cdf4d9420351aeb5a1a8",
}

ASSIGNMENTS = {
    "0579bc34-c3a7-4759-bbb0-3cc385e2f446": {
        "activity": "lecture",
        "hours": 30,
        "is_hourly_paid": False,
        "row_id": "40305d22-dac5-4ee8-91b8-7c7f6ed826b9",
    },
    "075b447a-dd09-41b6-bd51-f1f932673595": {
        "activity": "seminar",
        "hours": 15,
        "is_hourly_paid": False,
        "row_id": "40305d22-dac5-4ee8-91b8-7c7f6ed826b9",
    },
    "6b3b1af7-044c-4d9c-9315-64fe4173baf7": {
        "activity": "lecture",
        "hours": 30,
        "is_hourly_paid": False,
        "row_id": "0e8f5f38-1660-4b2c-a07a-6b72d4bd06f4",
    },
    "cb43d906-02ab-4d9a-b2df-a666f35e87f5": {
        "activity": "seminar",
        "hours": 30,
        "is_hourly_paid": False,
        "row_id": "8e4be310-9400-4402-8bd0-9725a1d4c3c9",
    },
    "fbb053de-6330-4ca0-a483-6dc2b2987918": {
        "activity": "seminar",
        "hours": 30,
        "is_hourly_paid": False,
        "row_id": "0e8f5f38-1660-4b2c-a07a-6b72d4bd06f4",
    },
}

ROWS = {
    "0e8f5f38-1660-4b2c-a07a-6b72d4bd06f4": {
        "groups": ["c895b91a-d8c2-48ac-a971-10b8812a2692"],
        "lab_plan": 0,
        "lab_total": 0,
        "lecture_plan": 30,
        "lecture_total": 30,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "seminar_plan": 30,
        "seminar_total": 30,
        "subgroup_count": 1,
        "subject_id": "d363639c-ae01-4da1-b9be-a22057ad6278",
        "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
        "union_count": 1,
    },
    "40305d22-dac5-4ee8-91b8-7c7f6ed826b9": {
        "groups": ["de6fb053-b9e1-4488-80d2-0c4f76f5c933"],
        "lab_plan": 0,
        "lab_total": 0,
        "lecture_plan": 30,
        "lecture_total": 30,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "seminar_plan": 15,
        "seminar_total": 15,
        "subgroup_count": 1,
        "subject_id": "7408265d-34f7-4fe0-bcf8-03a282de33dc",
        "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
        "union_count": 1,
    },
    "8e4be310-9400-4402-8bd0-9725a1d4c3c9": {
        "groups": ["96aa5842-71f8-43a1-88d2-b3a0fd1dce79"],
        "lab_plan": 0,
        "lab_total": 0,
        "lecture_plan": 30,
        "lecture_total": 0,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "seminar_plan": 30,
        "seminar_total": 30,
        "subgroup_count": 1,
        "subject_id": "d363639c-ae01-4da1-b9be-a22057ad6278",
        "task_id": "45b29907-4290-4028-bea7-943599cb0b48",
        "union_count": 0,
    },
}

OFFERINGS = {
    "7222c4a3-c29f-45f8-b652-6cad2249a7ba": {
        "group_id": "de6fb053-b9e1-4488-80d2-0c4f76f5c933",
        "is_active": True,
        "lesson_hours": 45,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "7408265d-34f7-4fe0-bcf8-03a282de33dc",
    },
    "7746c9d2-0062-46c1-bc3b-66c9896f1d36": {
        "group_id": "709c17ae-f469-4144-aebd-ae5bc8e3cbef",
        "is_active": True,
        "lesson_hours": 45,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "ecbbb5ec-91d3-4be8-b9a2-18986850ebe2",
    },
    "ab4d288a-52fb-4ccf-a91d-86202ea9fb06": {
        "group_id": "c895b91a-d8c2-48ac-a971-10b8812a2692",
        "is_active": True,
        "lesson_hours": 60,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "d363639c-ae01-4da1-b9be-a22057ad6278",
    },
    "ae284828-21cd-4a7b-9b6c-d99dd557e772": {
        "group_id": "96aa5842-71f8-43a1-88d2-b3a0fd1dce79",
        "is_active": True,
        "lesson_hours": 60,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "d363639c-ae01-4da1-b9be-a22057ad6278",
    },
    "cde93699-da10-4015-b18e-758370d79a3d": {
        "group_id": "0adbcc62-2431-44a7-b65b-42b785de1325",
        "is_active": True,
        "lesson_hours": 45,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "3885c98c-5b88-4b8c-a5f5-563c5ad638e1",
    },
}
