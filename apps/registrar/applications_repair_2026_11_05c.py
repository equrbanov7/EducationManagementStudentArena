"""RİM müraciətləri 2026-11-05 (axşam) — sabit id-li düzəlişlər (sahib: «müraciətləri 100% həll et»).

* **MR-209** (Səkinə Həsənova, 236 İ «İnformasiya təhlükəsizliyinin əsasları»): 11.10-da səhvən 236 İ ing jurnalına
  yazılmış 7 tələbənin 15.10 seminar qeydləri az jurnalına düşməmişdi (köhnə sistem 15203 ilə tutuşdurulub), ing
  müəlliminin onlara qoyduğu 14 qayıb isə köhnə (dropped) ing sətirlərində qalıb «Əvvəlki jurnaldan (236 İ ing)» kimi
  görünürdü. 7 xana YARADILIR (yalnız boşdursa), 14 qayıb SİLİNİR (yalnız gözlənilən sətir + qayıb), qayıb saatı
  yenidən hesablanır.
* **MR-218** (Esmira Əhmədova): 533 Bİ / 533 MRK «İnformasiya texnologiyaları» datalı jurnalları rəsmi axın sətrinin
  «İnformasiya texnologiyaları (ixtisas üzrə)» jurnallarına birləşir (``Merger``, keep) — mühazirə 233 K / 233 İT ilə
  eyni fənndə axın olur. Müəllimin xahişi ilə 29.10 seminarları (233 K, 233 İT — həmin gün aralıq imtahanı) silinir;
  hər silinən dərsin xanaları auditdə saxlanır.
* **MR-225** (Kəmalə Dadaşova): köhnə 14721 / 14261 jurnallarının dərsləri köçürmədə eyni qrup + dövrün, amma başqa adlı
  (yükdə olmayan) fənn jurnallarına düşüb; ``Merger`` (keep) ilə yükdəki cari jurnallara birləşir.

İdempotentdir: ikinci qaçışda heç nə yazılmır (``*_already``/``*_missing`` sayılır). Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .twin_merge import Merger
from .twin_relocate import recompute_absences

MR209_LESSON = "3ccd42ac-ab03-4c2f-b476-d55a49e5c17c"
MR209_OFFERING = "cd28c966-3150-45e7-9c98-b5d1f74752f6"
#: (az jurnal qeydiyyatı, status, bal) — köhnə sistem 15203, 15.10 10:10 seminar.
MR209_ADD = (
    ("60a7c88d-fc53-409c-9064-1a271e8e954e", "present", 7),
    ("da369420-a4a4-4873-a0c1-a7c99c3e3d8e", "present", 8),
    ("63e5eea1-fa94-4864-817a-9a2c7e106cf5", "present", 8),
    ("8cb5bbc1-7d1b-40d3-99d0-e1a3f1788688", "present", 9),
    ("7cdc8cda-f43f-46f6-a75c-64e8d52fe8cc", "absent", None),
    ("43fe85bc-de15-4b00-95a0-839576f15fe8", "present", 10),
    ("f6c752b3-8dbc-4181-9eb6-d30e298cffc9", "present", 7),
)
MR209_ING_OFFERING = "d8e0398f-4a84-49e5-bc93-07f5f5ece0e2"
#: (köhnə ing qeydiyyatı, səhv qayıb xanaları)
MR209_DROP = (
    (
        "22f9de3d-f354-425c-a97c-1999ac5b9a1f",
        ("a410d404-2a9e-4f84-9d06-b402e3bbef33", "2feaccb0-4d28-4339-b463-704a9da3502c"),
    ),
    (
        "70fd4b11-6ffd-473b-856a-8e7bbf6d3ed5",
        ("1a5d0914-0349-442e-80a6-46af450967dd", "3ff8b584-c1a3-4fef-a2d7-580584e70de5"),
    ),
    (
        "764d4092-ff68-4659-8e16-ef498970d0cd",
        ("d5939998-dfc2-47c2-a1eb-5b30b7e1bc0c", "7ffa7043-02ed-46dd-b722-dcb829cd2188"),
    ),
    (
        "97a4f598-a1b1-4100-ab8a-cf7c6c2e6664",
        ("a74c27e3-d186-44fd-90f2-7804b6c6ad9b", "cfce6db4-a016-4198-ab07-32fa33ec799f"),
    ),
    (
        "50a36a7f-b74d-4139-b8f7-6d61e1e61cfd",
        ("73ab72fe-4f4c-499a-b638-3f75953e4732", "b6cf684e-d2a9-48ac-ba88-15b97cc0e57c"),
    ),
    (
        "70fb0053-cf8f-49d6-a390-4c76c2d22ba6",
        ("a3bcf4f0-3dba-41da-b376-beb134ae3090", "3f12240f-c7d9-4f1f-b909-0c41681ce479"),
    ),
    (
        "a5b07a93-7062-43ab-ae2b-bc6fee8824df",
        ("43ee359d-b851-4458-9b27-244caa80927a", "d2e0fcb8-784e-441c-88d5-676e78305eb6"),
    ),
)
MR209_REASON = "MR-000209: köhnə sistem 15203 ilə tutuşdurma — 15.10 qeydləri az jurnalına, səhv ing qayıbları silinir"

MR218_PAIRS = (
    # 533 Bİ «İnformasiya texnologiyaları» (datalı) → «… (ixtisas üzrə)» (rəsmi axın sətri, boş).
    {
        "source": "9aa8baec-2e45-4aa8-b453-38981b1f0a1d",
        "target": "77c72001-183b-4874-b6d4-333cbb4b3230",
        "target_marks": "keep",
    },
    # 533 MRK — eyni.
    {
        "source": "f4380572-e795-46c2-b6d9-3af6a1160999",
        "target": "61eca9fe-1a06-47f9-b8a1-f3f1d1494720",
        "target_marks": "keep",
    },
)
#: (dərs, jurnal) — 29.10.2026 seminarları; müəllim: «aralıq imtahanı keçirilən dərs yazılmamalı idi».
MR218_DELETE_LESSONS = (
    ("c1379b70-f4c3-4687-84d5-f53716c0f9e3", "ef74c868-a293-40db-a346-ceba7f3813e0"),
    ("4a94df3a-72ac-49f1-9517-7c256beb8676", "6b1419bd-c247-4137-98e0-13f2c653bc61"),
)
MR218_LESSON_DATE = "2026-10-29"

MR225_PAIRS = (
    # «Qarabağ regionunda kənd turizmi …» (köhnə 14721-in dərsləri) → «Qarabağ regionunda turizminin inkişaf perspektivləri».
    {
        "source": "3faed019-e67c-4efb-9552-25b8eb5788be",
        "target": "3757d42a-165d-4301-996c-53f8c5cdb543",
        "target_marks": "keep",
    },
    # «Beynəlxalq turizm sferasında risklər və sığortalanma» (köhnə 14261) → «Beynəlxalq turizm sferasında risklər».
    {
        "source": "8683b730-002b-4d4a-99c9-be6aa0770924",
        "target": "4dbac766-8f26-455e-b8c3-646eca67b002",
        "target_marks": "keep",
    },
)
MR218_REASON = "MR-000218: müəllimin xahişi — 29.10 aralıq imtahanı günü, seminar dərsi yazılmamalı idi"


def _model(name):
    return django_apps.get_model("registrar", name)


def _audit(*, organization, actor, obj, old, new, reason, resource_type):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=obj,
        old_values=old,
        new_values=new,
        reason=reason,
        resource_type=resource_type,
        resource_id=str(obj.pk),
    )


def fix_mr209(*, organization, actor, counts) -> None:
    from core.rls import journal_unlock

    Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
    lesson = Lesson.objects.filter(organization=organization, pk=MR209_LESSON, offering_id=MR209_OFFERING).first()
    if lesson is None:
        counts["mr_marks_lesson_missing"] += 1
        return
    touched = []
    for enrollment_id, status, score in MR209_ADD:
        enrollment = Enrollment.objects.filter(pk=enrollment_id, offering_id=MR209_OFFERING).first()
        if enrollment is None:
            counts["mr_marks_enrollment_missing"] += 1
            continue
        if LessonMark.objects.filter(lesson=lesson, enrollment=enrollment).exists():
            counts["mr_marks_already"] += 1
            continue
        mark = LessonMark.objects.create(
            organization=organization,
            lesson=lesson,
            enrollment=enrollment,
            status=status,
            score=Decimal(score) if score is not None else None,
            entered_by=actor,
        )
        _audit(
            organization=organization,
            actor=actor,
            obj=mark,
            old={},
            new={"status": status, "score": score},
            reason=MR209_REASON,
            resource_type="registrar.LessonMark",
        )
        touched.append(enrollment)
        counts["mr_marks_added"] += 1
    for enrollment_id, mark_ids in MR209_DROP:
        enrollment = Enrollment.objects.filter(pk=enrollment_id, offering_id=MR209_ING_OFFERING).first()
        if enrollment is None:
            counts["wrong_absences_enrollment_missing"] += 1
            continue
        marks = list(
            LessonMark.objects.filter(pk__in=mark_ids, enrollment=enrollment, status="absent", score__isnull=True)
        )
        counts["wrong_absences_already"] += len(mark_ids) - len(marks)
        for mark in marks:
            _audit(
                organization=organization,
                actor=actor,
                obj=mark,
                old={"status": mark.status, "lesson": str(mark.lesson_id), "enrollment": str(enrollment.pk)},
                new={"deleted": True},
                reason=MR209_REASON,
                resource_type="registrar.LessonMark",
            )
        if marks:
            with journal_unlock():
                LessonMark.objects.filter(pk__in=[mark.pk for mark in marks]).delete()
            counts["wrong_absences_deleted"] += len(marks)
            touched.append(enrollment)
    recompute_absences(touched)


def fix_mr218(*, organization, actor, counts) -> None:
    Merger(organization=organization, actor=actor, counts=counts).run([dict(pair) for pair in MR218_PAIRS])
    Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
    for lesson_id, offering_id in MR218_DELETE_LESSONS:
        lesson = Lesson.objects.filter(
            organization=organization, pk=lesson_id, offering_id=offering_id, date=MR218_LESSON_DATE, kind="seminar"
        ).first()
        if lesson is None:
            counts["lessons_already_deleted"] += 1
            continue
        snapshot = [
            {"enrollment": str(row["enrollment_id"]), "status": row["status"], "score": str(row["score"] or "")}
            for row in LessonMark.objects.filter(lesson=lesson).values("enrollment_id", "status", "score")
        ]
        _audit(
            organization=organization,
            actor=actor,
            obj=lesson,
            old={"date": MR218_LESSON_DATE, "kind": lesson.kind, "offering": offering_id, "marks": snapshot},
            new={"deleted": True},
            reason=MR218_REASON,
            resource_type="registrar.Lesson",
        )
        lesson.delete()
        counts["lessons_deleted"] += 1
        recompute_absences(list(Enrollment.objects.filter(offering_id=offering_id)))


def run(*, organization, actor, counts) -> None:
    fix_mr209(organization=organization, actor=actor, counts=counts)
    fix_mr218(organization=organization, actor=actor, counts=counts)
    Merger(organization=organization, actor=actor, counts=counts).run([dict(pair) for pair in MR225_PAIRS])
