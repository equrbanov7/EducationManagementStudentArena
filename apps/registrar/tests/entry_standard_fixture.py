"""Giriş balı STANDARTI (Midterm rejimi, 2026/2027-dən) — parite/büdcə testlərinin ORTAQ fiksturası.

``test_entry_standard_parity`` (rəqəm pariteti + sorğu büdcəsi) və ``test_entry_standard_ui``
EYNİ datanı işlədir.  Fikstura QƏSDƏN yalnız keçiddən ƏVVƏL mövcud olan API-lərlə qurulur —
yəni köhnə kod üzərində də işləyir və «əvvəl ↔ sonra» snapshot-u həmin qaçışdan götürülüb.

Dövrlər / açılışlar (4 tələbə, hər biri tək akademik qeydli; ``esd_s3`` rəsmi idmançıdır):

* **OLD** — 2024/2025 Payız (KOLLOKVIUM rejimi, köhnə qayda bayt-bayt qalmalıdır):

  - ``K1`` (ESD101) — dərs cəmi yolu: 2 seminar + 1 lab + 1 mühazirə, K1–K3 (hər biri 10),
    10 mövzulu çeklist; tavan (50) iki tələbədə işə düşür, idmançı 8 saat qayıbla buraxılır.
  - ``K2`` (ESD102) — GENERIC komponent yolu (dərs balları nəzərə alınmır) + K1 + çeklist;
    bir tələbə imtahan minimumunu (17) keçmir.

* **NEW** — 2026/2027 Payız (MIDTERM rejimi, cari dövr, yeni standart):

  - ``M1`` (ESD201) — 3 seminar + 1 lab + 2 mühazirə (plan 30 saat), Midterm (0–20) + balı olan
    köhnə «Kollokvium 1» qalığı (20 ilə kəsilir), 2 × 5 sərbəst iş; buraxılmayan tələbə
    (10 saat > 7.5) təkrar imtahanla keçir, idmançı istisnası, 17.50 → 18 yuvarlaqlaşdırma sərhədi.
  - ``M2`` (ESD202) — dərs YOXDUR, plan saatı 0 (davamiyyət məxrəci naməlum → kanonik 10.00),
    ``entry_score_max=35`` (tavan), GENERIC komponent (Midterm rejimində giriş balına DAXİL DEYİL),
    1 × 10 sərbəst iş.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, journal_extras, selfwork_structure, services
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Curriculum,
    Enrollment,
    LessonKind,
    Program,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.models.selfwork import SELFWORK_TOTAL_POINTS
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

STUDENTS = ("esd_s0", "esd_s1", "esd_s2", "esd_s3")
#: Açılış açarı → (fənn şifri, dövr açarı).
OFFERINGS = {"K1": ("ESD101", "old"), "K2": ("ESD102", "old"), "M1": ("ESD201", "new"), "M2": ("ESD202", "new")}


def _score(value):
    return None if value is None else Decimal(str(value))


class EntryStandardFixture:
    """Mixin: iki dövr (kollokvium / midterm), dörd açılış, dörd tələbə — bax modul docstring-i."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("esd_owner", "esd_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ESD Univ",
                slug="esd-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="ESD Fakültə", slug="esd-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="ESD-101", slug="esd-g1", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            cls.periods = {
                "old": AcademicPeriod.objects.create(
                    organization=cls.org,
                    name="Payız",
                    period_type=AcademicPeriodType.SEMESTER,
                    academic_year="2024/2025",
                    start_date=datetime.date(2024, 9, 1),
                    end_date=datetime.date(2025, 1, 31),
                ),
                "new": AcademicPeriod.objects.create(
                    organization=cls.org,
                    name="Payız",
                    period_type=AcademicPeriodType.SEMESTER,
                    academic_year="2026/2027",
                    start_date=datetime.date(2026, 9, 15),
                    end_date=datetime.date(2027, 1, 31),
                    is_current=True,
                ),
            }
            cls.program = Program.objects.create(
                organization=cls.org, code="ESD", name="ESD proqramı", absence_limit_percent=25
            )
            curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.teacher = User.objects.create_user("esd_teacher", "esd_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.records = {}
            for index, username in enumerate(STUDENTS):
                student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                cls.records[username] = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=student,
                    program=cls.program,
                    curriculum=curriculum,
                    group=cls.group,
                    admission_year=2024,
                    national_athlete_exemption=(index == 3),
                )
            cls.offerings = {}
            cls.enrollments = {}
            for key, (code, period_key) in OFFERINGS.items():
                subject = Subject.objects.create(organization=cls.org, code=code, name=f"Fənn {code}", ects=5)
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.periods[period_key], group=cls.group
                )
                offering.instructor = cls.teacher
                offering.lesson_hours = 0 if key == "M2" else 30
                offering.save(update_fields=["instructor", "lesson_hours"])
                cls.offerings[key] = offering
                cls.enrollments[key] = {
                    username: Enrollment.objects.create(
                        organization=cls.org, student=cls.records[username].student, offering=offering
                    )
                    for username in STUDENTS
                }
            cls._build_k1()
            cls._build_k2()
            cls._build_m1()
            cls._build_m2()
            # ``save_marks`` qayıb saatını DB sətrində yeniləyir — yaddaşdakı nümunələr də təzələnsin.
            for by_user in cls.enrollments.values():
                for enrollment in by_user.values():
                    enrollment.refresh_from_db()

    # ── köməkçilər (setUpTestData) ─────────────────────────────────────────
    @classmethod
    def _lessons(cls, key, plan):
        """``plan`` = [(tarix, növ, {tələbə: (status, bal)})] → dərslər + işarələr."""
        offering = cls.offerings[key]
        for day, kind, cells in plan:
            lesson = gradebook.create_lesson(allow_past=True, offering=offering, date=day, kind=kind)
            entries = [
                {
                    "lesson_id": lesson.id,
                    "enrollment_id": cls.enrollments[key][username].id,
                    "status": status,
                    "score": score,
                }
                for username, (status, score) in cells.items()
            ]
            gradebook.save_marks(enforce_day=False, offering=offering, entries=entries, by_user=cls.teacher)

    @classmethod
    def _component_scores(cls, key, component, scores):
        for username, value in scores.items():
            ComponentScore.objects.create(
                organization=cls.org,
                component=component,
                enrollment=cls.enrollments[key][username],
                score=_score(value),
            )

    @classmethod
    def _checklist(cls, key, *, topics, done):
        offering = cls.offerings[key]
        created = [journal_extras.add_selfwork_topic(offering=offering, title=f"Mövzu {n}") for n in range(topics)]
        for username, count in done.items():
            for topic in created[:count]:
                assert journal_extras.set_selfwork_mark(
                    offering=offering,
                    topic_id=topic.id,
                    enrollment_id=cls.enrollments[key][username].id,
                    done=True,
                    by_user=cls.teacher,
                )

    @classmethod
    def _slots(cls, key, *, max_points, points):
        """Strukturlu sərbəst iş (``slot_index`` + ``max_points``) + real bal işarələri."""
        offering = cls.offerings[key]
        selfwork_structure.ensure_selfwork_component(offering)
        topics = [
            SelfWorkTopic.objects.create(
                organization=cls.org,
                offering=offering,
                title=f"Sərbəst iş {slot}",
                slot_index=slot,
                max_points=max_points,
                order=slot,
            )
            for slot in range(1, SELFWORK_TOTAL_POINTS // max_points + 1)
        ]
        for username, values in points.items():
            for topic, value in zip(topics, values):
                if value is not None:
                    SelfWorkMark.objects.create(
                        organization=cls.org,
                        topic=topic,
                        enrollment=cls.enrollments[key][username],
                        done=True,
                        points=_score(value),
                    )

    @classmethod
    def _exam(cls, key, scores):
        for username, value in scores.items():
            finals.set_exam_score(enrollment=cls.enrollments[key][username], score=value, by_user=cls.teacher)

    # ── OLD / K1: dərs cəmi + K1–K3 + çeklist ─────────────────────────────
    @classmethod
    def _build_k1(cls):
        p, a = "present", "absent"
        cls._lessons(
            "K1",
            [
                (
                    datetime.date(2024, 10, 1),
                    LessonKind.SEMINAR,
                    {"esd_s0": (p, 8), "esd_s1": (p, 10), "esd_s2": (p, 5)},
                ),
                (
                    datetime.date(2024, 10, 8),
                    LessonKind.SEMINAR,
                    {"esd_s0": (p, 9), "esd_s1": (p, 10), "esd_s2": (a, None)},
                ),
                (
                    datetime.date(2024, 10, 15),
                    LessonKind.LAB,
                    {"esd_s0": (p, 7), "esd_s1": (a, None), "esd_s2": (a, None)},
                ),
                (
                    datetime.date(2024, 10, 22),
                    LessonKind.LECTURE,
                    {"esd_s0": (p, None), "esd_s1": (a, None), "esd_s2": (a, None)},
                ),
            ],
        )
        # İdmançı (s3) bütün dərslərdə qayıbdır: 8 saat > 7.5 — istisna ilə buraxılır.
        cls._lessons(
            "K1",
            [
                (datetime.date(2024, 10, 29), LessonKind.LECTURE, {"esd_s3": (a, None)}),
                (datetime.date(2024, 11, 5), LessonKind.LECTURE, {"esd_s3": (a, None)}),
                (datetime.date(2024, 11, 12), LessonKind.LECTURE, {"esd_s3": (a, None)}),
                (datetime.date(2024, 11, 19), LessonKind.LECTURE, {"esd_s3": (a, None)}),
            ],
        )
        kolls = journal_extras.ensure_kollokviums(cls.offerings["K1"])
        assert [c.max_score for c in kolls] == [10, 10, 10]
        cls._component_scores("K1", kolls[0], {"esd_s0": 8, "esd_s1": 10, "esd_s3": 5})
        cls._component_scores("K1", kolls[1], {"esd_s0": 9, "esd_s1": 10})
        cls._component_scores("K1", kolls[2], {"esd_s0": 7, "esd_s1": 10})
        cls._checklist("K1", topics=10, done={"esd_s0": 3, "esd_s1": 10, "esd_s3": 1})
        cls._exam("K1", {"esd_s0": 40, "esd_s1": 30, "esd_s3": 20})

    # ── OLD / K2: GENERIC + K1 + çeklist ──────────────────────────────────
    @classmethod
    def _build_k2(cls):
        offering = cls.offerings["K2"]
        cls._lessons(
            "K2",
            [(datetime.date(2024, 10, 2), LessonKind.SEMINAR, {"esd_s0": ("present", 6), "esd_s1": ("present", 7)})],
        )
        generic = AssessmentComponent.objects.create(
            organization=cls.org, offering=offering, name="Giriş", kind=ComponentKind.GENERIC, max_score=30, order=0
        )
        koll = AssessmentComponent.objects.create(
            organization=cls.org,
            offering=offering,
            name="Kollokvium 1",
            kind=ComponentKind.KOLLOKVIUM,
            max_score=10,
            order=1,
        )
        cls._component_scores("K2", generic, {"esd_s0": 25, "esd_s1": 30, "esd_s2": 12, "esd_s3": 5})
        cls._component_scores("K2", koll, {"esd_s0": 8, "esd_s1": 10, "esd_s3": 3})
        cls._checklist("K2", topics=3, done={"esd_s0": 2, "esd_s1": 3})
        cls._exam("K2", {"esd_s0": 45, "esd_s1": 10})

    # ── NEW / M1: Midterm + qalıq K1 + 2 × 5 sərbəst iş ───────────────────
    @classmethod
    def _build_m1(cls):
        p, a = "present", "absent"
        cls._lessons(
            "M1",
            [
                (
                    datetime.date(2026, 9, 16),
                    LessonKind.SEMINAR,
                    {"esd_s0": (p, 7), "esd_s1": (a, None), "esd_s2": (p, 7), "esd_s3": (p, 6)},
                ),
                (
                    datetime.date(2026, 9, 17),
                    LessonKind.SEMINAR,
                    {"esd_s0": (p, 8), "esd_s1": (a, None), "esd_s2": (p, 8), "esd_s3": (p, 7)},
                ),
                (
                    datetime.date(2026, 9, 18),
                    LessonKind.SEMINAR,
                    {"esd_s0": (p, 10), "esd_s1": (a, None), "esd_s2": (p, None), "esd_s3": (a, None)},
                ),
                (
                    datetime.date(2026, 9, 21),
                    LessonKind.LAB,
                    {"esd_s0": (p, 9), "esd_s1": (p, 10), "esd_s2": (p, None), "esd_s3": (a, None)},
                ),
                (
                    datetime.date(2026, 9, 22),
                    LessonKind.LECTURE,
                    {"esd_s0": (a, None), "esd_s1": (a, None), "esd_s2": (p, None), "esd_s3": (a, None)},
                ),
                (
                    datetime.date(2026, 9, 23),
                    LessonKind.LECTURE,
                    {"esd_s0": (p, None), "esd_s1": (a, None), "esd_s2": (p, None), "esd_s3": (a, None)},
                ),
            ],
        )
        offering = cls.offerings["M1"]
        midterm = journal_extras.ensure_kollokviums(offering)[0]
        assert (midterm.name, midterm.max_score) == ("Midterm", 20)
        cls._component_scores("M1", midterm, {"esd_s0": 17, "esd_s1": 20, "esd_s3": 18})
        leftover = AssessmentComponent.objects.create(
            organization=cls.org,
            offering=offering,
            name="Kollokvium 1",
            kind=ComponentKind.KOLLOKVIUM,
            max_score=10,
            order=9,
        )
        cls._component_scores("M1", leftover, {"esd_s3": 3})
        cls._slots("M1", max_points=5, points={"esd_s0": (4, 5), "esd_s1": (5, 5), "esd_s3": ("2.5", None)})
        cls._exam("M1", {"esd_s0": 30, "esd_s3": 18})
        # Buraxılmayan s1: təkrar imtahan hüququ → 25 bal (buraxılış qadağası qalxır).
        barred = cls.enrollments["M1"]["esd_s1"]
        barred.refresh_from_db()  # qayıb saatı (10) DB-dədir
        assert finals.evaluate_resit(enrollment=barred) is not None
        assert finals.set_resit_score(enrollment=barred, score=25, by_user=cls.teacher) is not None

    # ── NEW / M2: dərssiz, tavan 35, GENERIC (nəzərə alınmır), 1 × 10 ─────
    @classmethod
    def _build_m2(cls):
        offering = cls.offerings["M2"]
        scheme = gradebook.ensure_assessment_scheme(offering=offering)
        scheme.entry_score_max = 35
        scheme.save(update_fields=["entry_score_max"])
        midterm = journal_extras.ensure_kollokviums(offering)[0]
        cls._component_scores("M2", midterm, {"esd_s0": 20, "esd_s2": 12})
        generic = AssessmentComponent.objects.create(
            organization=cls.org, offering=offering, name="Köhnə komponent", kind=ComponentKind.GENERIC, max_score=10
        )
        cls._component_scores("M2", generic, {"esd_s2": 5})
        cls._slots("M2", max_points=10, points={"esd_s0": (10,)})

    # ── test köməkçiləri ──────────────────────────────────────────────────
    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def fresh_offering(self, key):
        """DB-dən TƏZƏ oxunmuş açılış (keşlənmiş FK-sız) — sorğu ölçmələri üçün."""
        from apps.registrar.models import CourseOffering

        return CourseOffering.objects.get(pk=self.offerings[key].pk)

    def row_key(self, enrollment):
        for key, by_user in self.enrollments.items():
            for username, candidate in by_user.items():
                if candidate.pk == enrollment.pk:
                    return f"{key}/{username}"
        raise KeyError(enrollment.pk)
