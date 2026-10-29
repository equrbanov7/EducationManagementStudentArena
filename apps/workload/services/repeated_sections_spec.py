"""İki təsdiqli mənbə sətri: vahid saat dəyişmir, təkrar seminar sayı düzəlir."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
RESOURCE = "workload.repeated_sections_repair"
SPECS = (
    {
        "id": "52debb1c-189f-4e93-b34c-56e313c3d457",
        "task_id": "663dbec7-6043-4b12-9f69-9d1278a1b7cb",
        "chair_id": "723f5382-82c4-4627-9e69-739b8b3d8325",
        "subject_id": "0d46e234-3280-4ec1-893d-ae9c1c8caaff",
        "period_id": "4c81ff31-e755-4c30-a836-e0bb2599577b",
        "season": "spring",
        "teacher_id": 7726,
        "group_ids": ["4bbfa907-90ec-4439-81c7-29df5c7656c9", "9ea0c8df-cbcc-4dd3-8105-5efe0a10c89f"],
        "offering_ids": ["12545099-be58-4a62-8977-bb95f8024dcb", "5ae9b27e-f851-472a-9894-b55397a1cb3a"],
        "assignment_ids": {
            "lecture": "d72b481c-40db-406b-b457-cf57285a3fcf",
            "seminar": "ecca642e-4880-40ea-ae48-e584e0073dce",
        },
        "before_count": 1,
        "after_count": 2,
        "unit_hours": 15,
        "source": {
            "sha256": "7630be3cbe9bfe7050e2f308fae8c4959c35bd298967f5e3f2b77a0ab4a9cb09",
            "line": 23,
            "line_zero_based": True,
            "seminar_raw": "15*2",
        },
        "offering_groups": {
            "5ae9b27e-f851-472a-9894-b55397a1cb3a": "9ea0c8df-cbcc-4dd3-8105-5efe0a10c89f",
            "12545099-be58-4a62-8977-bb95f8024dcb": "4bbfa907-90ec-4439-81c7-29df5c7656c9",
        },
    },
    {
        "id": "be8e8251-977c-468d-b7d8-23a5e2196bf5",
        "task_id": "f9e57565-648f-4365-b533-db04007796d2",
        "chair_id": "6cb37f21-4d0f-4858-8c53-1f09d4d0efda",
        "subject_id": "6d3ff61d-d2f8-4757-a1e6-28a09009b86f",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "season": "fall",
        "teacher_id": 7769,
        "group_ids": [
            "17d2aa91-959e-45d2-9a57-f989753a3175",
            "681e46cb-8737-4073-8653-216f5f3ed4cc",
            "d826bb98-20ac-4783-b452-a2cd8f107611",
        ],
        "offering_ids": [
            "3d81f109-bcfb-4e0c-a6d2-4476e026e1ff",
            "8180f33d-e4e4-490d-ae42-d8df9fc43d39",
            "bcbdb2b5-243e-43bf-a054-26a212f0e2a1",
        ],
        "assignment_ids": {
            "lecture": "2a1a90fa-5341-4018-ac00-3419ee02249b",
            "seminar": "1c842a10-a948-4ecb-99d3-b43de6ddc014",
        },
        "before_count": 2,
        "after_count": 3,
        "unit_hours": 15,
        "source": {
            "sha256": "5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d",
            "line": 66,
            "line_zero_based": False,
            "seminar_raw": "15*3",
        },
        "offering_groups": {
            "3d81f109-bcfb-4e0c-a6d2-4476e026e1ff": "681e46cb-8737-4073-8653-216f5f3ed4cc",
            "8180f33d-e4e4-490d-ae42-d8df9fc43d39": "17d2aa91-959e-45d2-9a57-f989753a3175",
            "bcbdb2b5-243e-43bf-a054-26a212f0e2a1": "d826bb98-20ac-4783-b452-a2cd8f107611",
        },
    },
)
