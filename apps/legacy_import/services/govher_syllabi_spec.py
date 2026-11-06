"""MR-000250 / MR-000251: Gövhər Aydəmirovanın iki cari jurnalı üçün öz köhnə sillabusları (yalnız id + hash).

Mənbə: köhnə sistemin cari semestr jurnalının BİRBAŞA ``sillabus_id`` göstəricisi (müəllim, qrup, saat eyni):

* MR-000250 — 234 EKO az «Ümumi coğrafi xəritələrin layihələndirilməsi və tərtibi» (60 s, 30 müh + 30 sem):
  köhnə jurnal 15331 → sillabus 8837 (az, 15 mövzu). Jurnal hazırda baza dosyedəki İNGİLİS mətnli v1.0-ı
  (köhnə 7427, «en» sektoru) göstərir; o versiya arxivə keçir (silinmir), dosyeyə Azərbaycan dilli v2.0 yazılır.
* MR-000251 — 235 QM «Sağlamlıq və əməyin mühafizəsi» (45 s, 30 müh + 15 sem): köhnə jurnal 14029 →
  sillabus 8802 (köhnə sistemdə səhvən «Azərbaycanın tarixi coğrafiyası» fənn kartında saxlanılıb, mövzular bu
  fənnindir). Jurnalın öz dosyesi yoxdursa yaradılır; varsa yalnız BOŞ qaralama ola bilər (arxivə keçir, silinmir).

Məzmun repoda deyil — şifrəli paketdədir (``PACKET_SHA256``). Paketdəki hər mənbə, jurnal və çevrilmiş bölmələr
burada sabitlənmiş hash-lərlə yoxlanılır.
"""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
AUTHOR = 7760
SOURCE_AUTHOR = 166
FORMAT = "govher-own-syllabi/1"
PACKET_SHA256 = "03ea2babecfd8d7d0ed1d93aec872e6437b916f43f36c252dc601b813cb0e62f"
COMMON_TABLES = (
    "sillabus_certificates",
    "sillabus_dersin_islenme_formasi",
    "sillabus_derslikler",
    "sillabus_eldeolunacaq_tecrubeler",
    "sillabus_elmi_maraq",
    "sillabus_qarsilama_mesaji",
    "sillabus_serbest_is",
    "sillabus_tesviri_ve_meqsedi",
    "sillabus_yoxlama_formasi",
)

CASES = (
    {
        "key": "mr250",
        "offering_id": "ce820e15-c14e-4cf8-97bf-7da94de50361",
        "group_id": "fdb60c85-bc02-49f7-a972-24d7df81bdda",
        # QKU-2436 / QKU-452 eyni adlı dublikat kartlardır (merge_subjects 2026-11-04) — hər ikisi qəbul olunur.
        "subject_ids": ("16f1431a-260a-4fd8-8c04-ebdb671f97f8", "1602eef4-2d64-4540-a435-ea49bbeff201"),
        "hours": 60,
        "plan": {"lecture": 30, "seminar": 30},
        "workload_row": "4c11e680-f84f-4d67-90dc-849861a36273",
        "journal": {"id": 15331, "lesson_id": 2436, "groups_id": '["647"]', "fenn_saati": 60, "semestr": 14},
        "source": {"id": 8837, "lesson_id": 452, "uniqid": "BKVBdJZDztjVdBPCkIo2", "ders_saati": 60, "language": "az"},
        "topics": 15,
        "selfwork_rows": 15,
        "selfwork_topics": 15,
        "source_digest": "5bc38bad67d673658d3262d811953bc134103daa2a63fc71d11e6e3802f0f24c",
        "journal_digest": "904ad64737fc4f629279ffc77c7762646e6261421e196b8157b41d8b3a0eec5d",
        "converted_digest": "e1d5b086287a9f0c5b4179fd5c2d2d97011e871e89198ac4f3d6527376c46ced",
        # Səhv (ingilis dilli) təsdiqli baza dosye: arxivə keçir, yeni versiya EYNİ dosyeyə yazılır.
        "replace": {
            "syllabus_id": "434573c6-65c7-4750-bcce-245b72ce7314",
            "version_id": "09176895-00fc-4249-9c0f-c4c12195ede9",
            "content_digest": "9921611a93793c315d633ee5b2820544b0414ccb548a78284e768c4b9bccbd5b",
        },
    },
    {
        "key": "mr251",
        "offering_id": "ceea77f8-48c9-4083-98a4-40c6099fcba2",
        "group_id": "bb710525-2453-4ca0-85bc-71da98736988",
        "subject_ids": ("f7ed2e30-6e45-40bd-881c-bc00474173c2",),
        "hours": 45,
        "plan": {"lecture": 30, "seminar": 15},
        "workload_row": "3117ca75-7ef4-4601-b7cc-4cb9f95d7e50",
        "journal": {"id": 14029, "lesson_id": 1153, "groups_id": '["814"]', "fenn_saati": 45, "semestr": 14},
        "source": {"id": 8802, "lesson_id": 337, "uniqid": "hIubXEWmzH932KVRMt9U", "ders_saati": 45, "language": "az"},
        "topics": 23,
        "selfwork_rows": 17,
        "selfwork_topics": 17,
        "source_digest": "949e1817696ec507ce46c3d8bf1cd730b66fa0763975dc13a6b6a4b02d4e6375",
        "journal_digest": "b882f4b3dc724fe53bebbb46d27a593bcea6a556f70cfe8dd49e1ffbfa08e363",
        "converted_digest": "4e8a7279dbe5f408e77ae58f70ba57855dc7f79de9e1e734572684fa9ab426ca",
        "replace": None,
    },
)
