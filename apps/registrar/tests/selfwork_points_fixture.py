"""Sərbəst iş parite/büdcə testlərinin ORTAQ fiksturası (köhnə çeklist datası).

``test_selfwork_points_parity`` (rəqəm pariteti) və ``test_selfwork_points_budget``
(sorğu büdcəsi) eyni datanı işlədir — fikstura keçiddən ƏVVƏLKİ sahələrlə qurulur
(``max_points``/``points`` yoxdur), yəni köhnə kod üzərində də işləyir.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, journal_extras, services
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    LessonKind,
    Program,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

STUDENTS = ("swp_s0", "swp_s1", "swp_s2", "swp_s3")


class SelfWorkLegacyFixture:
    """Mixin: iki açılış (O1 dərs cəmi, O2 generic + qeyri-standart SELF_WORK), dörd tələbə."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("swp_owner", "swp_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SWP Univ",
                slug="swp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="SWP Fakültə", slug="swp-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="SWP-101", slug="swp-g1", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="SWP", name="SWP proqramı")
            curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subjects = [
                Subject.objects.create(organization=cls.org, code="SWP101", name="Fənn A", ects=6),
                Subject.objects.create(organization=cls.org, code="SWP102", name="Fənn B", ects=5),
            ]
            for subject in cls.subjects:
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
                )
            cls.teacher = User.objects.create_user("swp_teacher", "swp_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.records = {}
            for username in STUDENTS:
                student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                record = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=student,
                    program=cls.program,
                    curriculum=curriculum,
                    group=cls.group,
                    admission_year=2024,
                )
                services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
                cls.records[username] = record
            cls.o1 = Enrollment.objects.get(student__username="swp_s0", offering__subject=cls.subjects[0]).offering
            cls.o2 = Enrollment.objects.get(student__username="swp_s0", offering__subject=cls.subjects[1]).offering
            for offering in (cls.o1, cls.o2):
                offering.instructor = cls.teacher
                offering.save(update_fields=["instructor"])
            cls.e1 = {e.student.username: e for e in cls.o1.enrollments.select_related("student")}
            cls.e2 = {e.student.username: e for e in cls.o2.enrollments.select_related("student")}
            cls._build_o1()
            cls._build_o2()

    # ── O1: dərs cəmi + kollokvium + standart çeklist ──────────────────────
    @classmethod
    def _build_o1(cls):
        o1, e1 = cls.o1, cls.e1
        scores = {"swp_s0": (10, 8), "swp_s1": (5, None), "swp_s2": (9, None), "swp_s3": (10, 10)}
        for day in (1, 2):
            lesson = gradebook.create_lesson(
                allow_past=True, offering=o1, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
            )
            entries = [
                {"lesson_id": lesson.id, "enrollment_id": e1[u].id, "status": "present", "score": s[day - 1]}
                for u, s in scores.items()
                if s[day - 1] is not None
            ]
            gradebook.save_marks(enforce_day=False, offering=o1, entries=entries, by_user=cls.teacher)
        kollokvium = AssessmentComponent.objects.create(
            organization=cls.org, offering=o1, name="Kollokvium 1", kind=ComponentKind.KOLLOKVIUM, max_score=10
        )
        for username, score in (("swp_s0", 8), ("swp_s1", 4), ("swp_s3", 10)):
            ComponentScore.objects.create(
                organization=cls.org, component=kollokvium, enrollment=e1[username], score=Decimal(score)
            )
        topics = [journal_extras.add_selfwork_topic(offering=o1, title=f"Mövzu {n}") for n in range(1, 11)]
        done = {"swp_s0": 7, "swp_s1": 4, "swp_s2": 0, "swp_s3": 10}
        for username, count in done.items():
            for topic in topics[:count]:
                assert journal_extras.set_selfwork_mark(
                    offering=o1, topic_id=topic.id, enrollment_id=e1[username].id, done=True, by_user=cls.teacher
                )
        # s1: 4-cü işarə geri alınır (2 saat pəncərəsində) → `done=False` sətri qalır.
        assert journal_extras.set_selfwork_mark(
            offering=o1, topic_id=topics[3].id, enrollment_id=e1["swp_s1"].id, done=False, by_user=cls.teacher
        )
        for username, score in (("swp_s0", 40), ("swp_s1", 20), ("swp_s3", 45)):
            finals.set_exam_score(enrollment=e1[username], score=score, by_user=cls.teacher)

    # ── O2: generic + qeyri-standart SELF_WORK (max 5) + 12 mövzu + arxiv ─
    @classmethod
    def _build_o2(cls):
        o2, e2 = cls.o2, cls.e2
        generic = AssessmentComponent.objects.create(
            organization=cls.org, offering=o2, name="Giriş", kind=ComponentKind.GENERIC, max_score=30, order=0
        )
        selfwork = AssessmentComponent.objects.create(
            organization=cls.org, offering=o2, name="Sərbəst iş", kind=ComponentKind.SELF_WORK, max_score=5, order=1
        )
        for username, score in (("swp_s0", 25), ("swp_s1", 12), ("swp_s2", 5), ("swp_s3", 20)):
            ComponentScore.objects.create(
                organization=cls.org, component=generic, enrollment=e2[username], score=Decimal(score)
            )
        topics = [
            SelfWorkTopic.objects.create(organization=cls.org, offering=o2, title=f"SDF {n}", order=n)
            for n in range(1, 13)
        ]
        plan = {"swp_s0": topics[:11], "swp_s1": topics[:4], "swp_s2": topics[10:12], "swp_s3": []}
        for username, chosen in plan.items():
            for topic in chosen:
                SelfWorkMark.objects.create(organization=cls.org, topic=topic, enrollment=e2[username], done=True)
        # Köçürülmüş «si» — lövhədə görünür, giriş balına ƏLAVƏ OLUNMUR.
        ComponentScore.objects.create(
            organization=cls.org, component=selfwork, enrollment=e2["swp_s3"], score=Decimal("7.00")
        )
        for username, score in (("swp_s0", 30), ("swp_s1", 35)):
            finals.set_exam_score(enrollment=e2[username], score=score, by_user=cls.teacher)

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _pairs(self):
        for username in STUDENTS:
            yield username, self.e1[username], self.e2[username]

    def _all_enrollments(self):
        return [e for _u, e1, e2 in self._pairs() for e in (e1, e2)]

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _fresh_offering(self, *, code="SWP103", option="2x5"):
        """Mövzusuz yeni açılış (eyni qrup, dörd tələbə) + (``option`` verilibsə) təsdiqlənmiş sillabus.

        Qaytarır ``(offering, {username: enrollment})``."""
        from apps.registrar import services as registrar_services

        with bypass_rls():
            subject = Subject.objects.create(organization=self.org, code=code, name=f"Fənn {code}", ects=4)
            offering = registrar_services.get_or_create_offering(
                organization=self.org, subject=subject, period=self.period, group=self.group
            )
            offering.instructor = self.teacher
            offering.save(update_fields=["instructor"])
            enrollments = {
                username: Enrollment.objects.create(
                    organization=self.org, student=self.records[username].student, offering=offering
                )
                for username in STUDENTS
            }
            if option:
                approve_syllabus(offering, self.teacher, option=option)
        return offering, enrollments


def approve_syllabus(offering, author, *, option="2x5", self_titles=None):
    """Açılış üçün TƏSDİQLƏNMİŞ sillabus (yalnız ``week`` + ``self`` bölmələri) — birbaşa model yazısı.

    ``apps/subject_folder/tests/factories.py::approve_syllabus`` naxışı; iş axını
    (göndər → bax → təsdiqlə) testin mövzusu deyil.
    """
    from django.utils import timezone

    from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion

    organization = offering.organization
    syllabus, _created = Syllabus.objects.get_or_create(
        organization=organization,
        offering=offering,
        defaults={"subject": offering.subject, "period": offering.period, "author": author},
    )
    latest = syllabus.versions.order_by("-major").first()
    if latest is not None and latest.status == "approved":
        SyllabusVersion.objects.filter(pk=latest.pk).update(status="archived")
    now = timezone.now()
    version = SyllabusVersion.objects.create(
        organization=organization,
        syllabus=syllabus,
        major=(latest.major + 1) if latest else 1,
        status="approved",
        locked_at=now,
        approved_at=now,
        approved_by=author,
    )
    count = {"1x10": 1, "2x5": 2, "10x1": 10}.get(option, 0)
    titles = self_titles or [f"Sillabus sərbəst işi {i}" for i in range(1, count + 1)]
    rows = [{"topic": f"Həftə mövzusu {i}", "lecture": 2, "seminar": 2, "lab": 0, "outcome": "TN1"} for i in (1, 2)]
    SyllabusSection.objects.create(organization=organization, version=version, section_id="week", data={"rows": rows})
    SyllabusSection.objects.create(
        organization=organization,
        version=version,
        section_id="self",
        data={"option": option, "topics": [{"title": t} for t in titles], "archived": []},
    )
    syllabus.approved_version = version
    syllabus.current_version = version
    syllabus.save(update_fields=["approved_version", "current_version", "updated_at"])
    return syllabus, version
