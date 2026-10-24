"""Elektron jurnal (/jurnal/, Addım 1 «Qrup seçimi») — «Fakültə» ↔ «Kafedra» süzgəci (2026-10-24).

Sahibin şikayəti (ekran görüntüləri): kafedra seçiləndə siyahı boş qalırdı —
«Bu filtrlərlə tədris fənni (offering) tapılmadı.»

  a) ``?year=2026%2F2027&season=Payız+semestri&faculty=&department=<kafedra>`` — fakültəsiz kafedra;
  b) ``?faculty=<Rəqəmsal texnologiyalar məktəbi>&department=<Proqramlaşdırma … kafedrası>``.

Kök səbəb: kafedra süzgəci açılışın QRUP yolunda kafedra id-sini axtarırdı. Real (köçürülmüş)
strukturda qrup kafedranın altında DEYİL — fakültə → ixtisas → qrup; kafedra fakültənin ayrıca
uşağıdır. Kafedra açılışa MÜƏLLİMİN kafedra üzvlüyü və fənnin aparıcı kafedrası
(``Subject.chair_unit``) ilə bağlıdır — «Keçilmiş dərslər»in ``lessons_log_units`` tərifi.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.syllabus.tests.factories import activate_member, make_org
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

#: Ekran görüntüsündəki URL-in xam sorğu sətri (``/`` kodlanmış, boşluq ``+``, «ı» UTF-8 %-kodlu).
RAW_PERIOD_QS = "year=2026%2F2027&season=Pay%C4%B1z+semestri"


class JournalListUnitFiltersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("jluf-univ")

            def unit(name, unit_type, parent=None, slug=None):
                return OrgUnit.objects.create(
                    organization=cls.org,
                    name=name,
                    slug=slug or f"jluf-{OrgUnit.objects.count()}",
                    unit_type=unit_type,
                    parent=parent,
                )

            # Real ağac: «məktəb» FACULTY tipidir; kafedra fakültənin uşağı, qrup isə İXTİSAS altında.
            cls.school = unit("Rəqəmsal texnologiyalar məktəbi", OrgUnitType.FACULTY)
            cls.kafedra = unit("Proqramlaşdırma və informasiya təhlükəsizliyi kafedrası", OrgUnitType.CHAIR, cls.school)
            cls.other_chair = unit("Kompüter elmləri kafedrası", OrgUnitType.CHAIR, cls.school)
            specialty = unit("Kompüter mühəndisliyi", OrgUnitType.SPECIALTY, cls.school)
            cls.group = unit("234 K az", OrgUnitType.GROUP, specialty)
            cls.group_b = unit("235 K az", OrgUnitType.GROUP, specialty)
            # Başqa fakültə (səs-küy): öz kafedrası və qrupu.
            cls.econ = unit("İqtisadiyyat məktəbi", OrgUnitType.FACULTY)
            cls.econ_chair = unit("Maliyyə kafedrası", OrgUnitType.CHAIR, cls.econ)
            cls.econ_group = unit("301 M az", OrgUnitType.GROUP, unit("Maliyyə", OrgUnitType.SPECIALTY, cls.econ))
            # Köhnə/seed quruluşu: kafedra → ixtisas → qrup (qrup yolunda kafedra var).
            cls.legacy_group = unit(
                "236 K az", OrgUnitType.GROUP, unit("Kibertəhlükəsizlik", OrgUnitType.SPECIALTY, cls.kafedra)
            )

            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız semestri",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )

            cls.t_prog = User.objects.create_user("jluf_t1", "jluf_t1@qku.edu.az", "pw")  # kafedranın müəllimi
            cls.t_cs = User.objects.create_user("jluf_t2", "jluf_t2@qku.edu.az", "pw")  # qonşu kafedra
            cls.t_econ = User.objects.create_user("jluf_t3", "jluf_t3@qku.edu.az", "pw")
            cls.t_free = User.objects.create_user("jluf_t4", "jluf_t4@qku.edu.az", "pw")  # kafedrasız
            for teacher, chair in (
                (cls.t_prog, cls.kafedra),
                (cls.t_cs, cls.other_chair),
                (cls.t_econ, cls.econ_chair),
                (cls.t_free, None),
            ):
                activate_member(
                    cls.org,
                    teacher,
                    "teacher",
                    permissions=["course.view", "grade.input", "syllabus.edit"],
                    scope_unit=chair,
                )

            def offering(code, name, group, teacher, chair=None):
                subject = Subject.objects.create(organization=cls.org, code=code, name=name, chair_unit=chair)
                return CourseOffering.objects.create(
                    organization=cls.org, subject=subject, period=cls.period, group=group, instructor=teacher
                )

            cls.mobile = offering("JLUF-MP", "Mobil proqramlaşdırma", cls.group, cls.t_prog)
            cls.by_subject = offering("JLUF-IT", "İnformasiya təhlükəsizliyi", cls.group_b, cls.t_free, cls.kafedra)
            cls.by_group = offering("JLUF-KT", "Kriptoqrafiya", cls.legacy_group, cls.t_free)
            cls.cs = offering("JLUF-AL", "Alqoritmlər", cls.group, cls.t_cs)
            cls.finance = offering("JLUF-FN", "Maliyyə", cls.econ_group, cls.t_econ)

            cls.admin = User.objects.create_user("jluf_admin", "jluf_admin@qku.edu.az", "pw", is_superuser=True)

    def _client(self, user=None):
        client = Client()
        client.force_login(user or self.admin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _codes(self, query: str, user=None) -> set[str]:
        response = self._client(user).get(f"{reverse('registrar:journal_list')}?{query}")
        self.assertEqual(response.status_code, 200)
        return {offering.subject.code for offering in response.context["offerings"]}

    # ── (a) kafedra fakültəsiz ─────────────────────────────────────────────────

    def test_department_without_faculty_lists_kafedra_offerings(self):
        codes = self._codes(f"{RAW_PERIOD_QS}&faculty=&department={self.kafedra.pk}&group=&teacher=&q=")
        # Müəllim üzvlüyü + fənnin aparıcı kafedrası + (seed) qrup yolu — üçü də kafedranındır.
        self.assertEqual(codes, {"JLUF-MP", "JLUF-IT", "JLUF-KT"})

    # ── (b) fakültə + kafedra ─────────────────────────────────────────────────

    def test_faculty_and_department_lists_kafedra_offerings_inside_faculty(self):
        codes = self._codes(
            f"year=2026/2027&season=Payız semestri&faculty={self.school.pk}&department={self.kafedra.pk}"
        )
        self.assertEqual(codes, {"JLUF-MP", "JLUF-IT", "JLUF-KT"})

    def test_faculty_alone_filters_by_group_subtree(self):
        codes = self._codes(f"{RAW_PERIOD_QS}&faculty={self.school.pk}&department=")
        self.assertEqual(codes, {"JLUF-MP", "JLUF-IT", "JLUF-KT", "JLUF-AL"})
        self.assertEqual(self._codes(f"{RAW_PERIOD_QS}&faculty={self.econ.pk}"), {"JLUF-FN"})

    def test_kafedra_outside_chosen_faculty_is_dropped_not_emptied(self):
        response = self._client().get(
            reverse("registrar:journal_list"),
            {"year": "2026/2027", "season": "Payız semestri", "faculty": self.econ.pk, "department": self.kafedra.pk},
        )
        self.assertEqual({o.subject.code for o in response.context["offerings"]}, {"JLUF-FN"})
        self.assertEqual(response.context["journal_selected_department"], "")
        self.assertEqual(response.context["journal_selected_faculty"], str(self.econ.pk))

    def test_unknown_department_id_stays_fail_closed(self):
        self.assertEqual(self._codes(f"{RAW_PERIOD_QS}&department=not-a-uuid"), set())

    # ── İl / fəsil parse + əhatə ────────────────────────────────────────────────

    def test_year_and_season_with_slash_space_and_azerbaijani_letters_are_parsed(self):
        response = self._client().get(
            f"{reverse('registrar:journal_list')}?{RAW_PERIOD_QS}&department={self.kafedra.pk}"
        )
        self.assertEqual(response.context["journal_selected_year"], "2026/2027")
        self.assertEqual(response.context["journal_selected_season"], "Payız semestri")
        self.assertEqual(
            response.context["journal_selected_department_label"],
            "Proqramlaşdırma və informasiya təhlükəsizliyi kafedrası",
        )
        self.assertNotContains(response, "Bu filtrlərlə tədris fənni (offering) tapılmadı.")

    def test_faculty_scoped_journal_viewer_sees_kafedra_offerings(self):
        """Fakültə əhatəli ``journal.view`` daşıyıcısı (dekan) — əhatə kafedra nəticəsini boşaltmır."""
        dean = User.objects.create_user("jluf_dean", "jluf_dean@qku.edu.az", "pw")
        with bypass_rls():
            activate_member(
                self.org,
                dean,
                "dean",
                permissions=["course.view", "journal.view"],
                level=70,
                scope_type=RoleScopeType.UNIT,
                scope_unit=self.school,
            )
            profile = dean.profile
            profile.role = "dean"
            profile.save(update_fields=["role"])
        codes = self._codes(f"{RAW_PERIOD_QS}&faculty=&department={self.kafedra.pk}", user=dean)
        self.assertEqual(codes, {"JLUF-MP", "JLUF-IT", "JLUF-KT"})
        # Əhatə hələ də işləyir: başqa fakültənin jurnalı görünmür.
        self.assertEqual(self._codes(f"{RAW_PERIOD_QS}&faculty={self.econ.pk}", user=dean), set())


class DepartmentSearchSubtreeTest(TestCase):
    """Kafedra seçicisi (``accounts:records_department_search``) fakültənin ALT-AĞACINI göstərir."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("jluf-dept")
            cls.school = OrgUnit.objects.create(
                organization=cls.org, name="Rəqəmsal texnologiyalar məktəbi", slug="d-s", unit_type=OrgUnitType.FACULTY
            )
            # Ara səviyyə: məktəb → departament (UNIT) → kafedra.
            middle = OrgUnit.objects.create(
                organization=cls.org,
                name="Tədris departamenti",
                slug="d-m",
                unit_type=OrgUnitType.UNIT,
                parent=cls.school,
            )
            cls.deep = OrgUnit.objects.create(
                organization=cls.org,
                name="Proqramlaşdırma və informasiya təhlükəsizliyi kafedrası",
                slug="d-k",
                unit_type=OrgUnitType.CHAIR,
                parent=middle,
            )
            cls.direct = OrgUnit.objects.create(
                organization=cls.org,
                name="Kompüter elmləri kafedrası",
                slug="d-c",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.school,
            )
            other = OrgUnit.objects.create(
                organization=cls.org, name="İqtisadiyyat məktəbi", slug="d-e", unit_type=OrgUnitType.FACULTY
            )
            OrgUnit.objects.create(
                organization=cls.org, name="Maliyyə kafedrası", slug="d-f", unit_type=OrgUnitType.CHAIR, parent=other
            )
            cls.admin = User.objects.create_user("jluf_dadmin", "jluf_dadmin@qku.edu.az", "pw", is_superuser=True)

    def _get(self, **params):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:records_department_search"), params)
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.json()["results"]}

    def test_faculty_param_lists_kafedras_of_whole_subtree(self):
        self.assertEqual(self._get(faculty=str(self.school.pk)), {str(self.deep.pk), str(self.direct.pk)})

    def test_malformed_faculty_param_returns_empty_not_500(self):
        self.assertEqual(self._get(faculty="not-a-uuid"), set())
