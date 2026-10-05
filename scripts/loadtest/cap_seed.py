"""Tutum testi üçün seed — `manage.py shell -c "exec(open(PATH).read())"` ilə işləyir.

Yalnız İZOLƏ test bazasında (stress-test-university) işləyir; canlı bazaya
heç vaxt qoşulmur (orkestrator onu yalnız test stack-in DB URL-i ilə çağırır).

Yaradır (idempotent):
  * hər run üçün TƏZƏ MCQ imtahanı (`cap-<run>`) — bütün stress qruplarına açıq,
    cəhd limiti yoxdur → əvvəlki run-ların cəhdləri nəticəyə qarışmır;
  * `CAP_TEACHERS` müəllim (`cap_teacher_NNN`) — hər birinə öz elektron jurnalı
    (CourseOffering), qrupda `CAP_GROUP_SIZE` tələbə və BU RUN-a məxsus, BU GÜNƏ
    (Bakı) tarixli seminar dərsi (yeni qeyd yalnız dərs günü yazılır; mövcud qeyd
    2 saatdan sonra kilidlənir — gradebook.save_marks + DB trigger).

Nəticə: `CAP_OUT` (JSON) — imtahan slug-ı və müəllim → jurnal xəritəsi.
"""

import datetime
import json
import math
import os
import secrets
import time

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock, StudentGroup
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import (
    ComponentScore,
    CourseOffering,
    CourseWork,
    Curriculum,
    CurriculumSubject,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.models.exam_score_entry import ExamScoreEntry, ExamScoreSheet
from apps.registrar.models.grading import FinalGrade
from apps.registrar.models.kollokvium_window import KollokviumWindow
from apps.registrar.public import services as registrar_services
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()
UserProfile = django_apps.get_model("accounts", "UserProfile")

RUN_ID = os.environ["CAP_RUN_ID"]
TEACHERS = int(os.environ.get("CAP_TEACHERS", "0") or 0)
GROUP_SIZE = int(os.environ.get("CAP_GROUP_SIZE", "25") or 25)
SUBJECTS = int(os.environ.get("CAP_SUBJECTS", "5") or 5)
STUDENT_OFFSET = int(os.environ.get("CAP_JOURNAL_STUDENT_OFFSET", "40000") or 0)
QUESTIONS = int(os.environ.get("CAP_EXAM_QUESTIONS", "10") or 10)
# Real imtahan kimi: blokdan təsadüfi seçim (randomizer yolu da yük altında ölçülür).
BLOCKS = int(os.environ.get("CAP_EXAM_BLOCKS", "3") or 1)
POOL_PER_BLOCK = int(os.environ.get("CAP_EXAM_POOL_PER_BLOCK", "10") or 10)
PAD = int(os.environ.get("CAP_STUDENT_PAD", "3") or 3)
# Tələbə jurnal görünüşü üçün keçmiş tarixli dərslər + işarələr (bir dəfə, idempotent).
HISTORY = int(os.environ.get("CAP_HISTORY_LESSONS", "4") or 0)
# İmtahan Mərkəzi «imtahan balı» aktorları (exam_center_head rolu).
CLERKS = int(os.environ.get("CAP_CLERKS", "20") or 0)
OUT = os.environ.get("CAP_OUT", "/capacity/cap-seed.json")
ORG_SLUG = os.environ.get("CAP_ORG_SLUG", "stress-test-university")


def log(*parts):
    print("CAP_SEED", *parts, flush=True)


def seed_exam(org, author, groups, *, prefix="cap", extended=None):
    slug = slugify(f"{prefix}-{RUN_ID}")
    exam = Exam.objects.filter(organization=org, slug=slug).first()
    if exam is None:
        exam = Exam.objects.create(
            organization=org,
            author=author,
            title=f"Tutum testi {'final ' if extended else ''}{RUN_ID}",
            description="Yük testi üçün MCQ imtahanı (capacity run).",
            exam_type="test",
            exam_type_extended=extended,
            is_active=True,
            is_public=False,
            max_attempts_per_user=0,
            default_question_points=1,
            slug=slug,
        )
    if extended:
        # Final/midterm: `allowed_groups.add` m2m siqnalı BÜTÜN təyin olunmuş tələbələrə
        # sinxron PIN verir (hər birinə PBKDF2 make_password — 50k tələbədə ~1.5 saat).
        # Through cədvəlinə birbaşa yazılır; PIN-ləri yalnız pillənin tələbələrinə
        # cap_prep.py verir.
        through = Exam.allowed_groups.through
        have = set(through.objects.filter(exam_id=exam.pk).values_list("studentgroup_id", flat=True))
        through.objects.bulk_create(
            [through(exam_id=exam.pk, studentgroup_id=g.pk) for g in groups if g.pk not in have], batch_size=1000
        )
    else:
        exam.allowed_groups.add(*groups)
    total = BLOCKS * POOL_PER_BLOCK
    order = exam.questions.count()
    for b in range(1, BLOCKS + 1):
        block, _ = QuestionBlock.objects.get_or_create(exam=exam, order=b, defaults={"name": f"Blok {b}"})
        for _i in range(block.questions.count() if hasattr(block, "questions") else 0, POOL_PER_BLOCK):
            if order >= total:
                break
            order += 1
            question = ExamQuestion.objects.create(
                exam=exam,
                block=block,
                order=order,
                text=f"Tutum sualı {order}: düzgün variantı seçin.",
                answer_mode="single",
                points=1,
                difficulty="easy",
            )
            ExamQuestionOption.objects.bulk_create(
                [
                    ExamQuestionOption(question=question, label=label, text=f"Variant {label}", is_correct=label == "A")
                    for label in "ABCD"
                ]
            )
    if total > QUESTIONS and exam.random_question_count != QUESTIONS:
        exam.random_question_count = QUESTIONS
        exam.save(update_fields=["random_question_count"])
    return exam


def current_period(org, today):
    period = (
        AcademicPeriod.objects.filter(organization=org, is_current=True, start_date__lte=today, end_date__gte=today)
        .order_by("-start_date")
        .first()
    )
    if period is not None:
        return period
    period, _ = AcademicPeriod.objects.get_or_create(
        organization=org,
        name="Payız semestri (tutum)",
        academic_year="2026/2027",
        defaults={
            "period_type": AcademicPeriodType.SEMESTER,
            "start_date": datetime.date(2026, 9, 15),
            "end_date": datetime.date(2027, 1, 31),
            "is_current": True,
        },
    )
    if not period.is_current:
        period.is_current = True
        period.save(update_fields=["is_current"])
    return period


def ensure_staff(org, role, owner, password_hash, *, prefix="cap_teacher_", count=None, profile_role=ProfileRole.TEACHER):
    count = TEACHERS if count is None else count
    existing = {u.username: u for u in User.objects.filter(username__startswith=prefix)}
    missing = [
        User(
            username=f"{prefix}{k:03d}",
            email=f"{prefix}{k:03d}@stress.emsarena.local",
            first_name="Tutum",
            last_name=f"{'Müəllim' if prefix == 'cap_teacher_' else 'Mərkəz'} {k:03d}",
            password=password_hash,
            is_active=True,
        )
        for k in range(1, count + 1)
        if f"{prefix}{k:03d}" not in existing
    ]
    if missing:
        User.objects.bulk_create(missing, batch_size=500)
    staff = list(User.objects.filter(username__startswith=prefix).order_by("username")[:count])
    have_profile = set(UserProfile.objects.filter(user__in=staff).values_list("user_id", flat=True))
    UserProfile.objects.bulk_create(
        [
            UserProfile(
                user=t,
                organization=org,
                organization_type=OrganizationType.UNIVERSITY,
                student_university_name=org.name,
                role=profile_role,
                email_verified=True,
                password_change_required=False,
            )
            for t in staff
            if t.pk not in have_profile
        ],
        batch_size=500,
    )
    have_member = set(Membership.objects.filter(organization=org, user__in=staff).values_list("user_id", flat=True))
    Membership.objects.bulk_create(
        [
            Membership(user=t, organization=org, role=role, is_active=True, is_primary=True, assigned_by=owner)
            for t in staff
            if t.pk not in have_member
        ],
        batch_size=500,
    )
    return staff


def seed_journals(org, owner):
    if TEACHERS <= 0:
        return [], {}
    today = timezone.localdate()
    period = current_period(org, today)
    teacher_role = Role.objects.get(organization=org, name="teacher")
    student_hash = User.objects.get(username=f"stress_student_{1:0{PAD}d}").password
    teachers = ensure_staff(org, teacher_role, owner, student_hash)

    program, _ = Program.objects.get_or_create(
        organization=org, code="CAP", defaults={"name": "Tutum Proqramı", "absence_limit_percent": 25}
    )
    curriculum, _ = Curriculum.objects.get_or_create(organization=org, program=program, admission_year=2026)
    subjects = []
    for s in range(1, SUBJECTS + 1):
        subject, _ = Subject.objects.get_or_create(
            organization=org, code=f"CAP{s:03d}", defaults={"name": f"Tutum Fənni {s}"}
        )
        CurriculumSubject.objects.get_or_create(
            organization=org, curriculum=curriculum, subject=subject, semester_number=1
        )
        subjects.append(subject)

    groups = math.ceil(TEACHERS / SUBJECTS)
    offerings = []
    for g in range(1, groups + 1):
        unit, _ = OrgUnit.objects.get_or_create(
            organization=org,
            slug=f"cap-g{g:03d}",
            defaults={"name": f"CAP-{g:03d}", "unit_type": OrgUnitType.GROUP, "is_active": True},
        )
        first = STUDENT_OFFSET + (g - 1) * GROUP_SIZE + 1
        names = [f"stress_student_{i:0{PAD}d}" for i in range(first, first + GROUP_SIZE)]
        students = list(User.objects.filter(username__in=names).order_by("username"))
        for student in students:
            record, created = StudentAcademicRecord.objects.get_or_create(
                organization=org,
                student=student,
                defaults={"program": program, "curriculum": curriculum, "group": unit, "admission_year": 2026},
            )
            if created or not student.enrollments.filter(offering__period=period, offering__subject__in=subjects).exists():
                registrar_services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
        group_offerings = list(
            CourseOffering.objects.filter(organization=org, period=period, group=unit, subject__in=subjects).order_by(
                "subject__code"
            )
        )
        offerings.extend(group_offerings)
        if g % 10 == 0:
            log("groups", g, "/", groups, "offerings", len(offerings))

    # Hər run ÖZ dərsini alır. Əvvəl `get_or_create(date=today)` idi: eyni Bakı günündə
    # ikinci run (məs. 05:00 və 19:49) səhərki run-ın dərsini və İŞARƏLƏRİNİ təkrar
    # istifadə edirdi — 2 saatlıq pəncərə (MARK_EDIT_WINDOW + DB trigger) keçdiyi üçün
    # bütün xanalar kilidli idi, grid-də heç bir `att__` input render olunmurdu
    # («journal grid parse cells=0», 2026-10-05). Bu gün/sabah tarixli köhnə cap
    # dərsləri silinir (marks cascade; yalnız izolə test bazası).
    used = offerings[: len(teachers)]
    tag = f"cap-run {RUN_ID}"
    dates = [today]
    if timezone.localtime().hour >= 18:
        # Run Bakı gecə yarısını keçərsə jurnal pilləsi «sabahın» dərsini yazır.
        dates.append(today + datetime.timedelta(days=1))
    stale, _ = (
        Lesson.objects.filter(offering__in=used, date__in=dates).exclude(topic=tag).delete()
    )
    log("stale cap lessons deleted (incl. marks)", stale)
    have = set(
        Lesson.objects.filter(offering__in=used, topic=tag).values_list("offering_id", "date")
    )
    for o in used:  # .create (save/siqnallar işləsin), bulk_create yox
        for d in dates:
            if (o.pk, d) not in have:
                Lesson.objects.create(organization=org, offering=o, date=d, kind=LessonKind.SEMINAR, hours=2, topic=tag)

    mapping = []
    for teacher, offering in zip(teachers, offerings):
        changed = []
        if offering.instructor_id != teacher.pk:
            offering.instructor = teacher
            changed.append("instructor")
        if offering.lesson_hours != 60:
            offering.lesson_hours = 60
            changed.append("lesson_hours")
        if changed:
            offering.save(update_fields=changed)
        mapping.append([teacher.username, str(offering.pk)])
    seed_history(org, used, teachers, today, period)
    reset_scores(used)
    open_interim_windows(org, period, today, owner)
    enrollments = {
        str(o.pk): [str(e) for e in o.enrollments.order_by("id").values_list("id", flat=True)] for o in used
    }
    return mapping, enrollments


def seed_history(org, offerings, teachers, today, period):
    """Keçmiş həftələrin seminarları + işarələr — tələbə jurnalı/yekun real data göstərsin.

    Bir dəfə (topic=«cap-history»); `save_marks(enforce_day=False)` YALNIZ seed üçündür.
    """
    if HISTORY <= 0:
        return
    from apps.registrar import gradebook

    dates = [today - datetime.timedelta(days=7 * k) for k in range(1, HISTORY + 1)]
    dates = [d for d in dates if d >= period.start_date]
    have = set(
        Lesson.objects.filter(offering__in=offerings, topic="cap-history").values_list("offering_id", "date")
    )
    created = 0
    for offering, teacher in zip(offerings, teachers):
        new_lessons = [
            Lesson.objects.create(
                organization=org, offering=offering, date=d, kind=LessonKind.SEMINAR, hours=2, topic="cap-history"
            )
            for d in dates
            if (offering.pk, d) not in have
        ]
        if not new_lessons:
            continue
        enrollment_ids = list(offering.enrollments.values_list("id", flat=True))
        entries = [
            {
                "lesson_id": lesson.pk,
                "enrollment_id": eid,
                "status": "absent" if (i + j) % 11 == 0 else "present",
                "score": 4 + (i * 3 + j) % 7,
            }
            for i, lesson in enumerate(new_lessons)
            for j, eid in enumerate(enrollment_ids)
        ]
        gradebook.save_marks(offering=offering, entries=entries, by_user=teacher, enforce_day=False)
        # Keçmiş həftələrin qeydləri real kimi KİLİDLİ olsun (2 saat pəncərəsi bitib): əks
        # halda seed-dən sonrakı 2 saatda jurnal pilləsi bu xanaları da «yazıla bilən» görür.
        # (Təzə sətirlərdə UPDATE trigger-i keçir — OLD.created_at hələ 2 saat deyil.)
        for lesson in new_lessons:
            aged = timezone.make_aware(datetime.datetime.combine(lesson.date, datetime.time(12, 0)))
            LessonMark.objects.filter(lesson=lesson).update(created_at=aged)
            Lesson.objects.filter(pk=lesson.pk).update(created_at=aged)
        created += len(new_lessons)
    log("history lessons created", created)


def reset_scores(offerings):
    """journalfinal pilləsi hər run «ilk daxiletmə» ilə başlasın (izolə test bazası).

    Midterm/kollokvium balları, kurs işi və yekun imtahan balları (FinalGrade +
    ExamScoreEntry sübut sətirləri + partiyalar) silinir; əks halda 2 saat kilidi /
    «yazılmış balın dəyişdirilməsi sənəd tələb edir» qaydası saxlamanı rədd edərdi.
    """
    from apps.registrar import journal_extras

    for offering in offerings:
        journal_extras.ensure_kollokviums(offering)
    deleted = {
        "component_scores": ComponentScore.objects.filter(
            component__offering__in=offerings, component__kind="kollokvium"
        ).delete()[0],
        "course_work": CourseWork.objects.filter(enrollment__offering__in=offerings).delete()[0],
        "exam_score_entries": ExamScoreEntry.objects.filter(enrollment__offering__in=offerings).delete()[0],
        "exam_score_sheets": ExamScoreSheet.objects.filter(offering__in=offerings).delete()[0],
        "final_grades": FinalGrade.objects.filter(enrollment__offering__in=offerings).delete()[0],
    }
    log("reset", json.dumps(deleted))


def open_interim_windows(org, period, today, owner):
    """İmtahan Mərkəzi pəncərəsi: K1..K3 (midterm rejimində yalnız K1 istifadə olunur) açıq."""
    for k_index in range(3):
        KollokviumWindow.objects.update_or_create(
            organization=org,
            period=period,
            k_index=k_index,
            defaults={
                "opens_on": today - datetime.timedelta(days=1),
                "closes_on": today + datetime.timedelta(days=3),
                "is_active": True,
                "created_by": owner,
            },
        )


started = time.monotonic()
with rls_worker_atomic(), bypass_rls():
    org = Organization.objects.get(slug=ORG_SLUG)
    owner = org.owner
    author = User.objects.get(username="stress_teacher")
    exam_groups = list(StudentGroup.objects.filter(organization=org))
    with transaction.atomic():
        exam = seed_exam(org, author, exam_groups)
        final_exam = seed_exam(org, author, exam_groups, prefix="cap-final", extended="final")
    log("exam", exam.slug, "questions", exam.questions.count(), "final", final_exam.slug)
    with transaction.atomic():
        journals, enrollments = seed_journals(org, owner)
    log("journals", len(journals))
    clerks = []
    if CLERKS > 0:
        with transaction.atomic():
            clerk_role = Role.objects.get(organization=org, name="exam_center_head")
            clerk_hash = User.objects.get(username=f"stress_student_{1:0{PAD}d}").password
            clerks = [
                u.username
                for u in ensure_staff(
                    org,
                    clerk_role,
                    owner,
                    clerk_hash,
                    prefix="cap_examcenter_",
                    count=CLERKS,
                    profile_role=ProfileRole.EXAM_CENTER_HEAD,
                )
            ]
    result = {
        "run_id": RUN_ID,
        "exam_slug": exam.slug,
        "exam_id": exam.pk,
        "final_exam_slug": final_exam.slug,
        "final_exam_id": final_exam.pk,
        # finalcenter: hamı üçün eyni fərdi PIN (cap_prep.py PIN sətirlərini pillədən əvvəl yazır).
        "final_pin": "".join(secrets.choice("23456789") for _ in range(6)),
        "exam_author": author.username,
        "questions": exam.questions.count(),
        "journals": journals,
        "enrollments": enrollments,
        "clerks": clerks,
        "journal_student_offset": STUDENT_OFFSET,
        "journal_students": math.ceil(TEACHERS / SUBJECTS) * GROUP_SIZE if TEACHERS > 0 else 0,
        "student_count": User.objects.filter(username__startswith="stress_student_").count(),
        "seconds": round(time.monotonic() - started, 1),
    }
with open(OUT, "w") as fh:
    json.dump(result, fh)
log("done", json.dumps({k: v for k, v in result.items() if k not in ("journals", "enrollments")}))
