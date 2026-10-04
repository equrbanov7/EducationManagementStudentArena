"""Tutum testi üçün seed — `manage.py shell -c "exec(open(PATH).read())"` ilə işləyir.

Yalnız İZOLƏ test bazasında (stress-test-university) işləyir; canlı bazaya
heç vaxt qoşulmur (orkestrator onu yalnız test stack-in DB URL-i ilə çağırır).

Yaradır (idempotent):
  * hər run üçün TƏZƏ MCQ imtahanı (`cap-<run>`) — bütün stress qruplarına açıq,
    cəhd limiti yoxdur → əvvəlki run-ların cəhdləri nəticəyə qarışmır;
  * `CAP_TEACHERS` müəllim (`cap_teacher_NNN`) — hər birinə öz elektron jurnalı
    (CourseOffering), qrupda `CAP_GROUP_SIZE` tələbə və BU GÜNƏ tarixli seminar
    dərsi (yeni qeyd yalnız dərs günü yazılır — gradebook.save_marks qaydası).

Nəticə: `CAP_OUT` (JSON) — imtahan slug-ı və müəllim → jurnal xəritəsi.
"""

import datetime
import json
import math
import os
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
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Lesson,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
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
OUT = os.environ.get("CAP_OUT", "/capacity/cap-seed.json")
ORG_SLUG = os.environ.get("CAP_ORG_SLUG", "stress-test-university")


def log(*parts):
    print("CAP_SEED", *parts, flush=True)


def seed_exam(org, author, groups):
    slug = slugify(f"cap-{RUN_ID}")
    exam = Exam.objects.filter(organization=org, slug=slug).first()
    if exam is None:
        exam = Exam.objects.create(
            organization=org,
            author=author,
            title=f"Tutum testi {RUN_ID}",
            description="Yük testi üçün MCQ imtahanı (capacity run).",
            exam_type="test",
            is_active=True,
            is_public=False,
            max_attempts_per_user=0,
            default_question_points=1,
            slug=slug,
        )
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


def ensure_teachers(org, role, owner, password_hash):
    existing = {u.username: u for u in User.objects.filter(username__startswith="cap_teacher_")}
    missing = [
        User(
            username=f"cap_teacher_{k:03d}",
            email=f"cap_teacher_{k:03d}@stress.emsarena.local",
            first_name="Tutum",
            last_name=f"Müəllim {k:03d}",
            password=password_hash,
            is_active=True,
        )
        for k in range(1, TEACHERS + 1)
        if f"cap_teacher_{k:03d}" not in existing
    ]
    if missing:
        User.objects.bulk_create(missing, batch_size=500)
    teachers = list(
        User.objects.filter(username__startswith="cap_teacher_").order_by("username")[:TEACHERS]
    )
    have_profile = set(UserProfile.objects.filter(user__in=teachers).values_list("user_id", flat=True))
    UserProfile.objects.bulk_create(
        [
            UserProfile(
                user=t,
                organization=org,
                organization_type=OrganizationType.UNIVERSITY,
                student_university_name=org.name,
                role=ProfileRole.TEACHER,
                email_verified=True,
                password_change_required=False,
            )
            for t in teachers
            if t.pk not in have_profile
        ],
        batch_size=500,
    )
    have_member = set(Membership.objects.filter(organization=org, user__in=teachers).values_list("user_id", flat=True))
    Membership.objects.bulk_create(
        [
            Membership(user=t, organization=org, role=role, is_active=True, is_primary=True, assigned_by=owner)
            for t in teachers
            if t.pk not in have_member
        ],
        batch_size=500,
    )
    return teachers


def seed_journals(org, owner):
    if TEACHERS <= 0:
        return []
    today = timezone.localdate()
    period = current_period(org, today)
    teacher_role = Role.objects.get(organization=org, name="teacher")
    student_hash = User.objects.get(username=f"stress_student_{1:0{PAD}d}").password
    teachers = ensure_teachers(org, teacher_role, owner, student_hash)

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
        Lesson.objects.get_or_create(
            organization=org,
            offering=offering,
            date=today,
            defaults={"kind": LessonKind.SEMINAR, "hours": 2},
        )
        mapping.append([teacher.username, str(offering.pk)])
    return mapping


started = time.monotonic()
with rls_worker_atomic(), bypass_rls():
    org = Organization.objects.get(slug=ORG_SLUG)
    owner = org.owner
    author = User.objects.get(username="stress_teacher")
    exam_groups = list(StudentGroup.objects.filter(organization=org))
    with transaction.atomic():
        exam = seed_exam(org, author, exam_groups)
    log("exam", exam.slug, "questions", exam.questions.count())
    with transaction.atomic():
        journals = seed_journals(org, owner)
    log("journals", len(journals))
    result = {
        "run_id": RUN_ID,
        "exam_slug": exam.slug,
        "exam_id": exam.pk,
        "questions": exam.questions.count(),
        "journals": journals,
        "student_count": User.objects.filter(username__startswith="stress_student_").count(),
        "seconds": round(time.monotonic() - started, 1),
    }
with open(OUT, "w") as fh:
    json.dump(result, fh)
log("done", json.dumps({k: v for k, v in result.items() if k != "journals"}))
