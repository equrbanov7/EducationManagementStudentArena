"""``journal.view`` əhatəsinin kökü KAFEDRA olanda — /jurnal/ siyahısı + detal müşahidəsi (2026-10-24).

Köçürülmüş strukturda qrup fakültə → ixtisas → qrup altındadır, kafedra fakültənin AYRICA uşağıdır.
Əvvəl ``journal_scope.journal_view_q`` və ``journal_access.can_observe_journal`` yalnız qrupun
alt-ağacına baxırdı — kafedra əhatəli daşıyıcı (``Membership.scope_unit`` = kafedra) heç bir jurnal
görmürdü. İndi kökü kafedra olan əhatə ƏLAVƏ olaraq kafedraya aid açılışları görür
(``lessons_log_units.kafedra_offering_q`` — müəllimin kafedra üzvlüyü / fənnin aparıcı kafedrası),
başqa kafedranınkını yox. Fakültə əhatəsi dəyişmir. Yalnız OXU — yazma hüququ verilmir.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import journal_access, journal_scope
from apps.registrar.models import CourseOffering, Subject
from apps.syllabus.tests.factories import activate_member, make_org
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PERIOD_QS = {"year": "2026/2027", "season": "Payız semestri"}


class JournalViewKafedraScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("jvks-univ")

            def unit(name, unit_type, parent=None):
                return OrgUnit.objects.create(
                    organization=cls.org,
                    name=name,
                    slug=f"jvks-{OrgUnit.objects.count()}",
                    unit_type=unit_type,
                    parent=parent,
                )

            cls.school = unit("Rəqəmsal texnologiyalar məktəbi", OrgUnitType.FACULTY)
            cls.kafedra = unit("Proqramlaşdırma kafedrası", OrgUnitType.CHAIR, cls.school)
            cls.other_chair = unit("Kompüter elmləri kafedrası", OrgUnitType.CHAIR, cls.school)
            specialty = unit("Kompüter mühəndisliyi", OrgUnitType.SPECIALTY, cls.school)
            cls.group = unit("234 K az", OrgUnitType.GROUP, specialty)
            cls.econ = unit("İqtisadiyyat məktəbi", OrgUnitType.FACULTY)
            cls.econ_chair = unit("Maliyyə kafedrası", OrgUnitType.CHAIR, cls.econ)
            cls.econ_group = unit("301 M az", OrgUnitType.GROUP, unit("Maliyyə", OrgUnitType.SPECIALTY, cls.econ))

            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız semestri",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )

            cls.t_prog = User.objects.create_user("jvks_t1", "jvks_t1@qku.edu.az", "pw")
            cls.t_cs = User.objects.create_user("jvks_t2", "jvks_t2@qku.edu.az", "pw")
            cls.t_econ = User.objects.create_user("jvks_t3", "jvks_t3@qku.edu.az", "pw")
            cls.t_free = User.objects.create_user("jvks_t4", "jvks_t4@qku.edu.az", "pw")
            for teacher, chair in (
                (cls.t_prog, cls.kafedra),
                (cls.t_cs, cls.other_chair),
                (cls.t_econ, cls.econ_chair),
                (cls.t_free, None),
            ):
                activate_member(
                    cls.org, teacher, "teacher", permissions=["course.view", "grade.input"], scope_unit=chair
                )

            def offering(code, group, teacher, chair=None):
                subject = Subject.objects.create(organization=cls.org, code=code, name=code, chair_unit=chair)
                return CourseOffering.objects.create(
                    organization=cls.org, subject=subject, period=cls.period, group=group, instructor=teacher
                )

            # Kafedraya aid: müəllim üzvlüyü ilə / fənnin aparıcı kafedrası ilə (müəllim kafedrasız).
            cls.by_teacher = offering("JVKS-MP", cls.group, cls.t_prog)
            cls.by_subject = offering("JVKS-IT", cls.econ_group, cls.t_free, cls.kafedra)
            # Başqa kafedralar (eyni fakültə + başqa fakültə) və heç bir kafedraya aid olmayan.
            cls.other = offering("JVKS-AL", cls.group, cls.t_cs)
            cls.finance = offering("JVKS-FN", cls.econ_group, cls.t_econ, cls.econ_chair)
            cls.unattributed = offering("JVKS-XX", cls.group, cls.t_free)

            cls.chair_head = cls._scoped_viewer("jvks_head", "chair_head", cls.kafedra)
            cls.dean = cls._scoped_viewer("jvks_dean", "dean", cls.school)

    @classmethod
    def _scoped_viewer(cls, username, role_name, scope_unit):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        activate_member(
            cls.org,
            user,
            role_name,
            permissions=["course.view", "journal.view"],
            level=70,
            scope_type=RoleScopeType.UNIT,
            scope_unit=scope_unit,
        )
        return user

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _codes(self, user, **params) -> set[str]:
        response = self._client(user).get(reverse("registrar:journal_list"), {**PERIOD_QS, **params})
        self.assertEqual(response.status_code, 200)
        return {offering.subject.code for offering in response.context["offerings"]}

    def _detail_status(self, user, offering, method="get", **data) -> int:
        client = self._client(user)
        url = reverse("registrar:journal_detail", args=[offering.pk])
        return getattr(client, method)(url, data).status_code

    # ── Siyahı ───────────────────────────────────────────────────────────────

    def test_kafedra_scoped_viewer_lists_own_kafedra_offerings_only(self):
        self.assertEqual(self._codes(self.chair_head), {"JVKS-MP", "JVKS-IT"})

    def test_kafedra_scoped_viewer_kafedra_filter_matches_scope(self):
        self.assertEqual(self._codes(self.chair_head, department=self.kafedra.pk), {"JVKS-MP", "JVKS-IT"})
        self.assertEqual(self._codes(self.chair_head, department=self.other_chair.pk), set())

    def test_faculty_scoped_viewer_unchanged_group_subtree(self):
        # Fakültə əhatəsi qrup alt-ağacıdır: JVKS-IT (qrupu İqtisadiyyatda) DÜŞMÜR, fakültə qruplarının hamısı düşür.
        self.assertEqual(self._codes(self.dean), {"JVKS-MP", "JVKS-AL", "JVKS-XX"})

    # ── Detal (müşahidə) ─────────────────────────────────────────────────────

    def test_kafedra_scoped_viewer_observes_own_kafedra_journal(self):
        self.assertEqual(self._detail_status(self.chair_head, self.by_teacher), 200)
        self.assertEqual(self._detail_status(self.chair_head, self.by_subject), 200)

    def test_kafedra_scoped_viewer_cannot_open_other_kafedra_journal(self):
        # Detal səhifəsi icazəsizə (mövcud davranış) 404 verir — obyektin varlığı açılmır.
        self.assertEqual(self._detail_status(self.chair_head, self.other), 404)
        self.assertEqual(self._detail_status(self.chair_head, self.finance), 404)
        self.assertEqual(self._detail_status(self.chair_head, self.unattributed), 404)

    def test_kafedra_observation_is_read_only(self):
        status = self._detail_status(self.chair_head, self.by_teacher, method="post", action="add_lesson")
        self.assertEqual(status, 404)
        self.assertFalse(journal_access.is_direct_editor(self.chair_head, self.by_teacher))
        self.assertFalse(journal_access.can_edit_journal(self.chair_head, self.by_teacher))

    def test_faculty_scoped_observation_unchanged(self):
        self.assertTrue(journal_access.can_observe_journal(self.dean, self.other))
        self.assertTrue(journal_access.can_observe_journal(self.dean, self.unattributed))
        self.assertFalse(journal_access.can_observe_journal(self.dean, self.by_subject))
        self.assertFalse(journal_access.can_observe_journal(self.dean, self.finance))

    # ── Siyahı ↔ detal eyni əhatə + sorğu büdcəsi ────────────────────────────

    def test_list_and_detail_scope_agree(self):
        for user in (self.chair_head, self.dean):
            view_q = journal_scope.journal_view_q(user, self.org)
            listed = set(
                CourseOffering.objects.filter(organization=self.org).filter(view_q).values_list("pk", flat=True)
            )
            for offering in CourseOffering.objects.filter(organization=self.org).select_related("organization"):
                self.assertEqual(
                    journal_access.can_observe_journal(user, offering), offering.pk in listed, offering.subject_id
                )

    def test_scope_checks_add_no_queries(self):
        user = User.objects.get(pk=self.chair_head.pk)
        journal_scope.journal_view_q(user, self.org)  # üzvlük + bölmə yolları memoizasiya olunur
        offering = CourseOffering.objects.select_related("organization").get(pk=self.by_teacher.pk)
        with CaptureQueriesContext(connection) as ctx:
            journal_scope.journal_view_q(user, self.org)
        self.assertEqual(len(ctx.captured_queries), 0)  # Q alt-sorğulardan qurulur
        with CaptureQueriesContext(connection) as ctx:
            self.assertTrue(journal_scope.offering_in_journal_view_scope(user, self.org, offering))
        self.assertEqual(len(ctx.captured_queries), 1)  # tək EXISTS
