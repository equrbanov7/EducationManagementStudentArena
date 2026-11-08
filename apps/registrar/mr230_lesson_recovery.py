"""RİM MR-000230 — 236 İT «İnformasiya texnologiyalarının əsasları» (Payız 2026/2027): köhnə sistemin dərsləri və xanaları.

Müəllim (EMS 7721, köhnə sistemdə ``workers.id`` 19) 19.10-dan əvvəlki dərslərin EMS jurnalında olmadığını yazıb. Mənbə:
köhnə jurnal **15209** (``uniqid`` TIR8euN56J, qrup 974 = 236 İT, 39 tələbə). Spesifikasiya lokal qurulub və koda
yazılıb (plan faylı yoxdur, YALNIZ id-lər, şəxsi məlumat yoxdur):

* **Dərslər** — ``journals_dates`` (09: 16,16,17,23,23,24,30,30; 10: 01,07,07,08,14,14,19,21,21) + saatları (``times``).
  Növü dərs sətrinin ``sem_muh``-u DEYİL (orada hər yerdə defolt 0-dır), xanalardır — delta-nın öz qaydası
  (``rehearsal_journal_lesson_kinds.cell_kind``): xana ``sem_muh=1`` → mühazirə, ``0`` → seminar; ``lab`` heç yerdə 1
  deyil. 17 slotun hər biri homogendir (bir slotda bir kod). Bitmə saatı açılışın cədvəl slotlarındandır
  (10:10–11:40, 11:50–13:20).
* **Xanalar** — ``journals_dates_points`` (arxivdə bu jurnal üçün sətir yoxdur), (tələbə, slot) üzrə dublikat yoxdur:
  ``ie`` → iştirak, ``qb`` → qayıb (``excusable``/``allowed_qb`` heç birində yoxdur), rəqəm → iştirak + bal (≤ 10).
* **Tələbələr** — köhnə ``students.id`` → EMS hesabı FİN ilə (39/39), ad-soyadla çarpaz yoxlanılıb; açılışın
  (11-03 prod nüsxəsi) qeydiyyatları. Qeydiyyat id ilə tapılmasa (yenidən yaradılıbsa) eyni tələbənin bu açılışdakı
  ``enrolled`` sətri götürülür.

Yazı qaydası («yalnız boşluğu doldur»):

* (tarix, növ) üzrə dərs varsa — ona toxunulmur (saat/mövzu dəyişmir); yoxdursa yaradılır (``hours=2``, saat + bitmə
  saatı, ``created_by`` boş — köçürmə dərsləri kimi). Eyni (tarix, növ) üzrə iki dərs — qeyri-müəyyən, atlanır;
* xana yalnız (dərs, qeydiyyat) üçün heç bir xana YOXDURSA yazılır. Mövcud xana dəyişdirilmir (fərqlidirsə
  ``marks_differ_kept`` sayılır) — ``trg_journal_mark_guard`` yalnız UPDATE-dədir, INSERT-ə kilid lazım deyil;
* bağlı / passiv jurnal, dəyişmiş açılış (qrup, fənn, müəllim) — heç nə yazılmır;
* hər yazılan dərs üçün audit sətri (yaradılıbmı + yazılan hər xananın id / qeydiyyat / status / bal) — tam iz;
  ``--undo`` həmin audit sətirlərinə görə YALNIZ bu əmrin yazdığı, dəyişməmiş xanaları və boş qalan yaradılmış
  dərsləri silir (``core.rls.journal_unlock`` altında), geri qaytarmanın özü də audit olunur;
* qayıb saatı toxunulan qeydiyyatlar üçün yenidən hesablanır. İdempotentdir: ikinci qaçışda 0 yazı.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .twin_relocate import closed, corrected_lesson_ids, recompute_absences

OFFERING = "a412f547-42bd-4105-82dc-1d12050bff2d"
GROUP = "55062763-8c0c-4640-99ec-bb37f4889668"  # 236 İT
SUBJECT = "78c47b4e-3272-41c7-98c2-867aa86a3af7"  # İnformasiya texnologiyalarının əsasları
TEACHER = 7721
RESOURCE = "registrar.mr230_lesson_recovery"
REASON = "MR-000230: köhnə sistem 15209 (236 İT) — çatışmayan dərslər və xanalar bərpa olundu"
UNDO_REASON = "MR-000230: bərpanın geri qaytarılması"

#: (qeydiyyat, tələbə hesabı) — köhnə ``students.id`` 11440 … 11479 (11456 jurnalda yoxdur) sırası ilə.
ENROLLMENTS = (
    ("aaa7c6d8-c1af-4f18-9454-b3a557023e89", 8495),
    ("1355ed18-9e62-4a48-8c66-985c024782e9", 8521),
    ("2b913230-74d7-4560-8263-d90fe12ad10f", 8622),
    ("7931ad7a-0f94-4ba5-9ef7-81934b6cc55b", 8681),
    ("d31b787f-b3c1-4758-8d2f-e6df19a7a8fe", 8808),
    ("b97847d9-0cd2-42f3-ab01-67426f8f16a8", 8826),
    ("1b7a7705-05d6-4a92-ab41-066c7f956ca7", 8847),
    ("808b0b87-b0af-4f6e-85df-b405abd0c749", 8900),
    ("ba44dd25-1be2-425f-8a90-ede144212462", 8904),
    ("02df972a-c8b6-4a05-ba94-5abae5c70dbc", 8971),
    ("b272bcb0-d45b-43a2-98a7-380782467e7b", 8987),
    ("5ad5a9e7-5db0-4e10-801c-00af9c0a4e2b", 8990),
    ("03528aec-9f7b-4be4-8fc4-0ba5240d2f6f", 8998),
    ("efcfb7cf-6582-4e5e-a694-ae25b5489d73", 9096),
    ("c6557a6d-8eef-4613-a5a1-bd749e2bd6d4", 9099),
    ("b33c6af9-7a9a-4c1c-9315-3e346a808a32", 9107),
    ("8161eac6-a9da-404e-b6e7-ddfc14defe75", 9121),
    ("6f3a7754-f170-47b2-9d68-4ae0699620db", 9174),
    ("88a0e8e4-1bc5-43bc-b144-3b33fc006503", 9180),
    ("a6bc1d72-fdd7-43c1-8096-731828461f48", 9186),
    ("576aeae1-2459-4bfb-8f94-b1ec10435130", 9226),
    ("c261c99d-f110-49e5-a92f-f0db8cb58feb", 9231),
    ("694903d9-3e0b-4a02-acd2-95a17e2e377e", 9237),
    ("b1a3e175-c9ed-42d7-8389-8782ad830756", 9246),
    ("8f7df94a-6553-4f02-b498-2c2cb06ff377", 9258),
    ("5f8bcc60-63ff-46d8-8a64-a67247f81196", 9315),
    ("0b6d04e4-055a-4504-8561-fbf5af37853e", 9322),
    ("c961601f-ad5f-48ae-b2a3-3393bd47a52e", 9335),
    ("28d3d5de-4f3e-4f22-a397-ad8c37a8cd63", 9338),
    ("9b232043-a7a7-4fac-a914-bec97df5c8d6", 9342),
    ("376cca55-0058-466b-8e32-09a08aeadd2e", 9356),
    ("bfd85fcf-9b17-4bfe-918c-5efa6916b6e5", 9366),
    ("df2e9be0-0801-4429-8e1b-86c45c527827", 9376),
    ("88ec6eeb-d425-4be7-85c7-92c289a82003", 9400),
    ("c5499026-4ea3-42bb-bc38-b84314876903", 9411),
    ("20111e11-151e-4d91-bd2c-25beda96a5a3", 9417),
    ("9adf27eb-76dd-49c5-9e12-187ac4eeab14", 9420),
    ("01605b62-20f5-4738-b183-4092d98348db", 9433),
    ("23362a53-a969-499a-824a-1da6d988b2d9", 9434),
)

#: (tarix, növ, başlama, bitmə, xanalar). Xana sətri ``ENROLLMENTS`` sırası ilə, hər simvol bir tələbə:
#: ``i`` iştirak, ``q`` qayıb, ``0``–``9`` iştirak + bal, ``X`` iştirak + 10, ``.`` köhnə sistemdə xana yoxdur.
LESSONS = (
    ("2026-09-16", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-09-16", "seminar", "11:50", "13:20", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-09-17", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-09-23", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-09-23", "seminar", "11:50", "13:20", "iiiii877iiiiii79iiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-09-24", "seminar", "10:10", "11:40", "iiiii877iiiiiii9iiX8iiiiX8i9i8ii6iii99i"),
    ("2026-09-30", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-09-30", "seminar", "11:50", "13:20", "i8i8iiiii9i97ii9qi9iiiii99i8i88iiii8ii8"),
    ("2026-10-01", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-10-07", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-10-07", "seminar", "11:50", "13:20", "7i9i9iii7i8ii89X97ii68979i9i7ii7987ii9i"),
    ("2026-10-08", "lecture", "10:10", "11:40", "iiiiiiiiqiiqiqiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-10-14", "lecture", "10:10", "11:40", "iiiiiiiiiiiqiiiiqiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-10-14", "seminar", "11:50", "13:20", "i9i8i786iiiiiii9ii8iiii88iiiiiiiiiii8ii"),
    ("2026-10-19", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-10-21", "lecture", "10:10", "11:40", "iiiiiiiiiiiiiiiiqiiiiiiiiiiiiiiiiiiiiii"),
    ("2026-10-21", "seminar", "11:50", "13:20", "8.7...7.....6...58.8.887...8...89.9.878"),
)


def _model(name):
    return django_apps.get_model("registrar", name)


def decode(code: str):
    """Xana simvolu → ``(status, score)``; ``.`` → ``None`` (köhnə sistemdə xana yoxdur)."""

    if code == ".":
        return None
    if code == "i":
        return "present", None
    if code == "q":
        return "absent", None
    return "present", Decimal(10 if code == "X" else int(code))


def _time(text: str) -> datetime.time:
    return datetime.time.fromisoformat(text)


def _enrollments(offering, counts) -> list:
    """``ENROLLMENTS`` sırası ilə canlı ``enrolled`` qeydiyyatlar (tapılmayan → ``None``)."""

    Enrollment = _model("Enrollment")
    rows = {str(row.pk): row for row in Enrollment.objects.filter(offering=offering, status="enrolled")}
    by_student = {row.student_id: row for row in rows.values()}
    found = []
    for enrollment_id, student_id in ENROLLMENTS:
        row = rows.get(enrollment_id)
        if row is not None and row.student_id != student_id:
            row = None
        if row is None:
            row = by_student.get(student_id)
            counts["enrollments_by_student" if row is not None else "enrollments_missing"] += 1
        found.append(row)
    return found


def _offering(organization, counts):
    Offering = _model("CourseOffering")
    offering = Offering.objects.select_for_update(of=("self",)).filter(organization=organization, pk=OFFERING).first()
    if offering is None:
        counts["offering_missing"] += 1
        return None
    if (str(offering.group_id), str(offering.subject_id), offering.instructor_id) != (GROUP, SUBJECT, TEACHER):
        counts["offering_scope_changed"] += 1
        return None
    if not offering.is_active or closed([offering.pk]):
        counts["offering_closed"] += 1
        return None
    return offering


def _lesson(organization, offering, date, kind, start, end, counts):
    """``(dərs, yaradıldımı)``; qeyri-müəyyəndirsə ``(None, False)``."""

    Lesson = _model("Lesson")
    lessons = list(Lesson.objects.filter(offering=offering, date=date, kind=kind))
    if len(lessons) > 1:
        counts["lessons_ambiguous"] += 1
        return None, False
    if lessons:
        counts["lessons_found"] += 1
        return lessons[0], False
    if Lesson.objects.filter(offering=offering, date=date).exists():
        counts["lessons_created_beside_other_kind"] += 1
    counts["lessons_created"] += 1
    lesson = Lesson.objects.create(
        organization=organization,
        offering=offering,
        date=date,
        kind=kind,
        hours=2,
        start_time=_time(start),
        end_time=_time(end),
    )
    return lesson, True


def recover(*, organization, actor, counts) -> None:
    LessonMark = _model("LessonMark")
    offering = _offering(organization, counts)
    if offering is None:
        return
    enrollments = _enrollments(offering, counts)
    touched = {}
    for date, kind, start, end, cells in LESSONS:
        lesson, created = _lesson(organization, offering, date, kind, start, end, counts)
        if lesson is None:
            continue
        existing = {row.enrollment_id: row for row in LessonMark.objects.filter(lesson=lesson)}
        written = []
        for enrollment, code in zip(enrollments, cells):
            value = decode(code)
            if value is None:
                continue
            if enrollment is None:
                counts["marks_enrollment_missing"] += 1
                continue
            status, score = value
            mark = existing.get(enrollment.pk)
            if mark is not None:
                counts["marks_already" if (mark.status, mark.score) == (status, score) else "marks_differ_kept"] += 1
                continue
            mark = LessonMark.objects.create(
                organization=organization, lesson=lesson, enrollment=enrollment, status=status, score=score
            )
            written.append(
                {
                    "id": str(mark.pk),
                    "enrollment": str(enrollment.pk),
                    "status": status,
                    "score": None if score is None else int(score),
                }
            )
            touched[enrollment.pk] = enrollment
        if written:
            counts["marks_added"] += len(written)
        if created or written:
            log_action(
                AuditAction.CREATE if created else AuditAction.UPDATE,
                user=actor,
                organization=organization,
                obj=lesson,
                new_values={"created": created, "date": date, "kind": kind, "start_time": start, "marks": written},
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(lesson.pk),
            )
    recompute_absences(list(touched.values()))


def undo(*, organization, actor, counts) -> None:
    """Bu əmrin audit sətirlərinə görə YALNIZ onun yazdığı, dəyişməmiş xanaları + boş qalan yaradılmış dərsləri sil."""

    from core.rls import journal_unlock

    AuditLog = django_apps.get_model("audit", "AuditLog")
    Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
    logs = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE)
    undone = {
        str((row or {}).get("undoes")) for row in logs.filter(reason=UNDO_REASON).values_list("new_values", flat=True)
    }
    touched = set()
    for entry in logs.filter(reason=REASON).order_by("-created_at"):
        if str(entry.pk) in undone:
            counts["undo_already"] += 1
            continue
        values = entry.new_values or {}
        doomed = []
        for item in values.get("marks") or []:
            score = item.get("score")
            mark = LessonMark.objects.filter(
                pk=item.get("id"),
                lesson_id=entry.resource_id,
                enrollment_id=item.get("enrollment"),
                status=item.get("status"),
                score=None if score is None else Decimal(score),
            ).first()
            if mark is None:
                counts["undo_marks_gone_or_changed"] += 1
                continue
            doomed.append(mark.pk)
            touched.add(item.get("enrollment"))
        if doomed:
            with journal_unlock():
                LessonMark.objects.filter(pk__in=doomed).delete()
            counts["undo_marks_deleted"] += len(doomed)
        lesson_deleted = False
        if values.get("created"):
            lesson = Lesson.objects.filter(pk=entry.resource_id, offering_id=OFFERING, created_by__isnull=True).first()
            if lesson is None:
                counts["undo_lessons_gone"] += 1
            elif lesson.marks.exists() or corrected_lesson_ids([lesson.pk]):
                counts["undo_lessons_kept"] += 1
            else:
                lesson.delete()
                lesson_deleted = True
                counts["undo_lessons_deleted"] += 1
        log_action(
            AuditAction.DELETE,
            user=actor,
            organization=organization,
            new_values={"undoes": str(entry.pk), "marks_deleted": len(doomed), "lesson_deleted": lesson_deleted},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=entry.resource_id,
        )
    recompute_absences(list(Enrollment.objects.filter(pk__in=touched)))
