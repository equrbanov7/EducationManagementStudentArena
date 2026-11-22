"""Öz qrupunun BAŞQA bölmədəki jurnalları — yalnız OXU (sahib 2026-11-22, ``registrar.journal_group_reach``).

Struktur (default rollar, real açarlar): A məktəbi → X kafedrası → ixtisas → A1 qrupu; B məktəbi → Y kafedrası
(Xarici dillər) → səviyyə kohortu L; B məktəbi → ixtisas → B1; Kollec → ixtisas → K1. A1 tələbəsi L kohortunun
jurnalında (Y kafedrası) və K1-in jurnalında qeydiyyatdadır.

* A dekanlığı / A tyutoru (``journal.roster``) və X kafedra müdiri / laborantı (``journal.view``) L jurnalını
  siyahıda görür və YALNIZ-OXU açır (yazı POST-ları keçmir);
* X kafedra müdiri A1-in Y kafedrasının tədris etdiyi jurnalını da görür (qrup X-in alt-ağacındadır);
* A tələbəsi olmayan B1 jurnalı, keçmiş dövrün kohortu, Kollec jurnalı, başqa təşkilat — görünmür;
* tələbə / müəllim davranışı dəyişmir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import journal_access, journal_group_reach, lessons_log
from apps.registrar.journal_list_scope import journal_list_base
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

PERIOD_QS = {"year": "2026/2027", "season": "Payız semestri"}


def _org(slug, owner):
    return Organization.objects.create(
        name=slug.upper(),
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


class JournalGroupReachTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gr_owner", "gr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = _org("gr-univ", cls.owner)

            def unit(name, unit_type, parent=None, **extra):
                return OrgUnit.objects.create(
                    organization=cls.org,
                    name=name,
                    slug=f"gr-{OrgUnit.objects.count()}",
                    unit_type=unit_type,
                    parent=parent,
                    **extra,
                )

            cls.school_a = unit("Biznes məktəbi", OrgUnitType.FACULTY)
            cls.chair_x = unit("Marketinq kafedrası", OrgUnitType.CHAIR, cls.school_a)
            cls.group_a1 = unit("134 P", OrgUnitType.GROUP, unit("Marketinq", OrgUnitType.SPECIALTY, cls.chair_x))
            cls.school_b = unit("Filologiya məktəbi", OrgUnitType.FACULTY)
            cls.chair_y = unit("Xarici dillər kafedrası", OrgUnitType.CHAIR, cls.school_b)
            cls.cohort = unit("İngilis dili B1-1", OrgUnitType.GROUP, cls.chair_y)
            cls.group_b1 = unit("201 F", OrgUnitType.GROUP, unit("Filologiya", OrgUnitType.SPECIALTY, cls.school_b))
            kollec = unit("Kollec", OrgUnitType.FACULTY)
            cls.group_k1 = unit("1226 A", OrgUnitType.GROUP, unit("Kollec ixtisası", OrgUnitType.SPECIALTY, kollec))

            cls.period = cls._period(cls.org, "2026/2027", "2026-09-15", "2027-01-31", current=True)
            cls.past = cls._period(cls.org, "2025/2026", "2025-09-15", "2026-01-31", current=False)

            cls.teacher_x = cls._member("gr_tx", "teacher", cls.chair_x)
            cls.teacher_y = cls._member("gr_ty", "teacher", cls.chair_y)
            cls.teacher_free = cls._member("gr_tf", "teacher", None)
            cls.dean = cls._member("gr_dean", "dean", cls.school_a)
            cls.tutor = cls._member("gr_tutor", "tutor", cls.school_a)
            cls.chair_head = cls._member("gr_head", "chair_head", cls.chair_x)
            cls.laborant = cls._member("gr_lab", "lab_assistant", cls.chair_x)
            cls.dean_b = cls._member("gr_dean_b", "dean", cls.school_b)

            def offering(code, group, teacher, chair, period=None):
                subject = Subject.objects.create(organization=cls.org, code=code, name=code, chair_unit=chair)
                return CourseOffering.objects.create(
                    organization=cls.org,
                    subject=subject,
                    period=period or cls.period,
                    group=group,
                    instructor=teacher,
                )

            cls.own_chair = offering("GR-MK", cls.group_a1, cls.teacher_x, cls.chair_x)
            cls.other_chair = offering("GR-IQ", cls.group_a1, cls.teacher_y, cls.chair_y)
            cls.level = offering("GR-EN", cls.cohort, cls.teacher_y, cls.chair_y)
            cls.b_only = offering("GR-FL", cls.group_b1, cls.teacher_y, cls.chair_y)
            cls.past_level = offering("GR-EN-OLD", cls.cohort, cls.teacher_y, cls.chair_y, period=cls.past)
            cls.college = offering("GR-KL", cls.group_k1, cls.teacher_free, None)

            cls.student_a = cls._student("gr_sa", cls.group_a1)
            cls.student_b = cls._student("gr_sb", cls.group_b1)
            for offering_row in (cls.own_chair, cls.other_chair, cls.level, cls.past_level, cls.college):
                cls._enroll(cls.student_a, offering_row)
            cls._enroll(cls.student_b, cls.b_only)
            cls._enroll(cls.student_b, cls.level)

            cls.lesson = Lesson.objects.create(
                organization=cls.org, offering=cls.level, date="2026-10-01", instructor=cls.teacher_y
            )

            cls.org2 = _org("gr-other", User.objects.create_user("gr_owner2", "gr_owner2@qku.edu.az", "pw"))
            group2 = OrgUnit.objects.create(
                organization=cls.org2, name="134 P", slug="gr2-g", unit_type=OrgUnitType.GROUP
            )
            period2 = cls._period(cls.org2, "2026/2027", "2026-09-15", "2027-01-31", current=True)
            subject2 = Subject.objects.create(organization=cls.org2, code="GR2-EN", name="GR2-EN")
            cls.foreign = CourseOffering.objects.create(
                organization=cls.org2, subject=subject2, period=period2, group=group2
            )

    @classmethod
    def _period(cls, org, year, start, end, *, current):
        return AcademicPeriod.objects.create(
            organization=org,
            name=f"{year} Payız semestri",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=year,
            start_date=start,
            end_date=end,
            is_current=current,
        )

    @classmethod
    def _member(cls, username, role_name, scope_unit):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            organization=cls.org,
            user=user,
            role=cls.org.roles.get(name=role_name),
            scope_unit=scope_unit,
            is_primary=True,
            is_active=True,
        )
        return user

    @classmethod
    def _student(cls, username, group):
        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            organization=cls.org,
            user=student,
            role=cls.org.roles.get(name="student"),
            scope_unit=group,
            is_primary=True,
            is_active=True,
        )
        program = Program.objects.create(organization=cls.org, code=f"P-{username}", name=f"Proqram {username}")
        curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=2026,
        )
        return student

    @classmethod
    def _enroll(cls, student, offering):
        Enrollment.objects.create(organization=cls.org, student=student, offering=offering)

    # ── köməkçilər ───────────────────────────────────────────────────────────

    def _fresh(self, user):
        return User.objects.get(pk=user.pk)  # hər yoxlamada təzə instans (üzvlük/öz-qrup keşi istifadəçidədir)

    def _client(self, user, org=None):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = (org or self.org).slug
        session.save()
        return client

    def _listed(self, user) -> set:
        request = RequestFactory().get("/jurnal/")
        request.user, request.organization = self._fresh(user), self.org
        with bypass_rls():
            base, _broad = journal_list_base(request.user, request)
            return set(base.values_list("subject__code", flat=True))

    def _page_codes(self, user) -> dict:
        response = self._client(user).get(reverse("registrar:journal_list"), PERIOD_QS)
        self.assertEqual(response.status_code, 200)
        return {row.subject.code: row.group_reach for row in response.context["offerings"]}

    def _observes(self, user, offering) -> bool:
        with bypass_rls():
            return journal_access.can_observe_journal(self._fresh(user), offering)

    def _detail(self, user, offering, method="get", data=None):
        url = reverse("registrar:journal_detail", args=[offering.pk])
        return getattr(self._client(user), method)(url, data or {})

    # ── Dekanlıq (fakültə əhatəsi, ``journal.roster``) ─────────────────────────

    def test_dean_lists_own_group_level_journal_of_other_school(self):
        self.assertEqual(self._listed(self.dean), {"GR-MK", "GR-IQ", "GR-EN"})

    def test_dean_list_marks_only_the_cross_unit_row_with_owning_chair(self):
        rows = self._page_codes(self.dean)
        self.assertEqual(set(rows), {"GR-MK", "GR-IQ", "GR-EN"})
        self.assertEqual(rows["GR-EN"], {"chair": "Xarici dillər kafedrası"})
        self.assertIsNone(rows["GR-MK"])
        self.assertIsNone(rows["GR-IQ"])  # fakültənin öz qrupu — əvvəldən görünürdü, etiket yoxdur
        response = self._client(self.dean).get(reverse("registrar:journal_list"), PERIOD_QS)
        self.assertContains(response, "jl-badge--reach", count=1)

    def test_dean_opens_cross_unit_journal_read_only(self):
        self.assertTrue(self._observes(self.dean, self.level))
        self.assertEqual(self._detail(self.dean, self.level).status_code, 200)
        with bypass_rls():
            dean = self._fresh(self.dean)
            self.assertFalse(journal_access.can_edit_journal(dean, self.level))
            self.assertFalse(journal_access.is_direct_editor(dean, self.level))
        export = self._client(self.dean).get(reverse("registrar:journal_xlsx", args=[self.level.pk]))
        self.assertEqual(export.status_code, 200)

    def test_dean_write_endpoints_are_refused_on_cross_unit_journal(self):
        with bypass_rls():
            before = Lesson.objects.filter(offering=self.level).count()
        response = self._detail(self.dean, self.level, "post", {"action": "add_lesson", "lesson_date": "2026-10-02"})
        self.assertIn(response.status_code, (403, 404))
        lesson_url = reverse("registrar:journal_lesson_action", args=[self.level.pk, self.lesson.pk])
        response = self._client(self.dean).post(lesson_url, {"action": "delete_lesson"})
        self.assertIn(response.status_code, (302, 403, 404))
        guest = self._client(self.dean).post(
            reverse("registrar:journal_guest_add", args=[self.level.pk]), {"student": self.student_b.pk}
        )
        self.assertIn(guest.status_code, (403, 404))
        with bypass_rls():
            self.assertEqual(Lesson.objects.filter(offering=self.level).count(), before)
            self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())

    def test_school_b_only_journal_past_period_and_college_stay_hidden(self):
        for offering in (self.b_only, self.past_level, self.college):
            with self.subTest(offering=offering.subject.code):
                self.assertFalse(self._observes(self.dean, offering))
                self.assertEqual(self._detail(self.dean, offering).status_code, 404)

    def test_other_school_dean_does_not_see_school_a_journals(self):
        self.assertEqual(self._listed(self.dean_b), {"GR-FL", "GR-EN"})
        self.assertFalse(self._observes(self.dean_b, self.own_chair))

    def test_other_org_journal_never_reachable(self):
        with bypass_rls():
            self.assertFalse(journal_group_reach.offering_in_reach(self._fresh(self.dean), self.foreign))
        self.assertEqual(self._detail(self.dean, self.foreign).status_code, 404)

    # ── Kafedra müdiri / laborant (kafedra əhatəsi, ``journal.view``) ──────────

    def test_chair_head_sees_own_group_journals_taught_by_other_chair(self):
        self.assertEqual(self._listed(self.chair_head), {"GR-MK", "GR-IQ", "GR-EN"})
        rows = self._page_codes(self.chair_head)
        self.assertIsNone(rows["GR-MK"])  # öz kafedrasının fənni — əvvəldən görünürdü
        self.assertEqual(rows["GR-IQ"], {"chair": "Xarici dillər kafedrası"})
        self.assertEqual(rows["GR-EN"], {"chair": "Xarici dillər kafedrası"})
        self.assertEqual(self._detail(self.chair_head, self.other_chair).status_code, 200)
        self.assertFalse(self._observes(self.chair_head, self.b_only))

    def test_laborant_same_reach_read_only(self):
        self.assertEqual(self._listed(self.laborant), {"GR-MK", "GR-IQ", "GR-EN"})
        self.assertTrue(self._observes(self.laborant, self.level))
        with bypass_rls():
            self.assertFalse(journal_access.is_direct_editor(self._fresh(self.laborant), self.level))
        self.assertIn(self._detail(self.laborant, self.level, "post", {"action": "add_lesson"}).status_code, (403, 404))
        self.assertFalse(self._observes(self.laborant, self.b_only))

    # ── Tyutor (fakültə əhatəsi, ``journal.roster``) ───────────────────────────

    def test_tutor_same_reach(self):
        self.assertEqual(self._listed(self.tutor), {"GR-MK", "GR-IQ", "GR-EN"})
        self.assertEqual(self._detail(self.tutor, self.level).status_code, 200)
        self.assertFalse(self._observes(self.tutor, self.b_only))
        self.assertFalse(self._observes(self.tutor, self.college))

    # ── «Keçilmiş dərslər» nəzarət əhatəsi ────────────────────────────────────

    def test_lessons_log_supervision_includes_cross_unit_lessons(self):
        with bypass_rls():
            scope_q = lessons_log.supervision_q(self._fresh(self.dean), self.org)
            self.assertTrue(Lesson.objects.filter(scope_q).filter(pk=self.lesson.pk).exists())
            other = lessons_log.supervision_q(self._fresh(self.dean_b), self.org)
            self.assertTrue(Lesson.objects.filter(other).filter(pk=self.lesson.pk).exists())

    # ── Tələbə / müəllim dəyişmir ───────────────────────────────────────────

    def test_students_and_teachers_unaffected(self):
        self.assertFalse(self._observes(self.student_a, self.level))
        self.assertEqual(self._detail(self.student_a, self.level).status_code, 404)
        self.assertFalse(self._listed(self.teacher_x) & {"GR-EN", "GR-IQ", "GR-FL"})
        self.assertFalse(self._observes(self.teacher_x, self.level))
        self.assertEqual(self._detail(self.teacher_x, self.level).status_code, 404)
        with bypass_rls():
            self.assertTrue(journal_access.can_edit_journal(self._fresh(self.teacher_y), self.level))
        self.assertEqual(journal_group_reach.own_group_ids(self._fresh(self.teacher_x), self.org), frozenset())
