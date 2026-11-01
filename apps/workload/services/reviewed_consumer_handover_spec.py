"""One mutually reported current handover; never an inferred historical effective date."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
COURSE = "27b96834-6c7d-4747-8bf6-b739624340f1"
GROUP = "a5841412-893b-43db-8e65-47214bcd7f51"
SUBJECT = "ca51bef9-4364-448b-b1e4-aeb9d507d5c3"
ROW = "07b63e53-3193-44f3-880e-bd97b1f003e9"
TASK = "598db875-7e68-425b-bd02-9f06dfaa6904"
CHAIR = "813355a3-efac-4c51-a3ca-8b471d3b3a0e"
OLD = 8103
NEW = 8218
NAMES = {8103: ("Aydın", "Rəfiyev", "Ağaəli"), 8218: ("Ülviyyə", "Xudaverdili", "Ramiz")}
ASSIGNMENTS = {"c5b69d6d-42e7-4ced-b3ae-d9f8b1c69f0c": "seminar", "cc54dd1f-b7b6-4a73-b3c5-061040268ff8": "lecture"}
COUNTS = {"registrar.Lesson": 9, "registrar.LessonMark": 126, "registrar.Enrollment": 15}
CLAIMS = [
    {
        "book": 19,
        "row": 5,
        "sha256": "38f22d457e55f9c59c6330d1e5a8d1a9e1c4e73b0eae49d91deefcf4127d53de",
        "claim": "new_teacher_missing_534MRK_consumer_journal",
    },
    {
        "book": 22,
        "row": 5,
        "sha256": "18d66b5aba3d0ccd5c1880979d3384767ecb7a7907f07d7a048bf742afc9082e",
        "claim": "same_new_teacher_claim_duplicate",
    },
    {
        "book": 24,
        "row": 6,
        "sha256": "00c1cd05b607503c9c68899640ccc8499f0543d27bdcf75aab207eb2fea87a15",
        "claim": "old_teacher_does_not_teach_534MRK_consumer",
    },
]
SOURCE_PLAN_SHA = "82587a424581e664266387aeda75ab04a79adf343625705a7569e97d5e53870f"
RESOURCE = "workload.reviewed_consumer_handover_v1"
