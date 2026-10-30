"""24Oktyabr rəsmi Maliyyə sənədinin35/36-cı sətirləri, iki fərqli ata adı."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
SOURCE_SHA = "3c87f7f625b57360522c0f3eb31a29dc464dea52edba0e0dc8b9137c5019f32f"
RESOURCE = "workload.cavid_source_35_36"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TEACHER = 11586
PREVIOUS = 8258
FINANCE = "9375b388-7945-464b-949c-aa5134e4eca4"
NATURE = "99856a60-d755-497c-a475-eb5f79fb26eb"
TASK_A = "0bcee890-62ff-46cf-bd05-f589218dbe67"
TASK_B = "bbfc4e1a-91f2-4cff-acd0-c813a6f0e01f"
ROW_B = "3c4de001-b2d7-4b87-a6f1-a4660e27f628"
LECTURE_B = "2a257776-dd51-4ed1-aa04-756bb963f3ff"
OFFERING_A = "8390e6fd-e457-479b-ac27-bd519116be76"
OFFERING_B = "f0555a39-ac5e-4c0c-89d8-a272bbcda281"
SUBJECT_A = "8fb278ca-23b8-4971-a2b2-a103db124a0a"
SUBJECT_B = "9f036b0b-86a4-4346-a6cd-657825d76944"
GROUP_A = "95cd66eb-3be1-410f-a231-8d28cc7223e8"
GROUP_B = "72cde476-07d1-4917-aed9-6b5c29afe2e2"
SPECIALTY_A = "4e9aa113-32f3-41e0-8989-42ded47812e4"
PLAN = {
    "source_sha256": SOURCE_SHA,
    "organization": ORG,
    "academic_year": YEAR,
    "period": PERIOD,
    "teacher": {"id": TEACHER, "username": "cavid.xelilov2", "patronymic": "Murad"},
    "previous": {"id": PREVIOUS, "username": "cavid.xelilov", "patronymic": "Bəxtiyar"},
    "source35": {
        "task": TASK_A,
        "chair": FINANCE,
        "subject": SUBJECT_A,
        "group": GROUP_A,
        "offering": OFFERING_A,
        "hours": {"lecture": 30, "seminar": 30},
        "student_count": 6,
        "credits": "5",
    },
    "source36": {
        "task": TASK_B,
        "chair": NATURE,
        "row": ROW_B,
        "lecture_assignment": LECTURE_B,
        "subject": SUBJECT_B,
        "group": GROUP_B,
        "offering": OFFERING_B,
        "hours": {"lecture": 30, "seminar": 15},
    },
}
