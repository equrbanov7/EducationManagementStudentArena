"""Açılışın kafedrası = fənnin TƏDRİS YÜKÜNÜN kafedrası (sahib, 2026-10-25) — «Keçilmiş dərslər» və /jurnal/.

Sahibin şikayəti: kafedra seçiləndə başqa kafedranın dərsləri çıxırdı («Mülki müdafiə» Proqramlaşdırma
süzgəcində). Kök səbəb: «kafedra» müəllimin İSTƏNİLƏN kafedra üzvlüyündən götürülürdü; ştatca bir
kafedrada olan müəllim yük faylı ilə başqa kafedraya (saat hesabı) da üzv yazılanda onun bütün fənləri
o kafedraya düşürdü. İndi tərif ``apps.registrar.offering_chairs``-dədir: dərs yükü sətri → tapşırığın
kafedrası, yoxdursa ``Subject.chair_unit``, köçürülmüşdə fənnin yükü / müəllimin ştat kafedrası.
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, OrgUnit, Role
from apps.registrar import offering_chairs
from apps.registrar.models import CourseOffering, Lesson, LessonKind, Subject
from apps.syllabus.tests.factories import activate_member, make_org
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

TEACHER_PERMS = ["course.view", "grade.input"]
WINDOW = {"ll_range": "custom", "ll_from": "2025-02-01", "ll_to": "2027-01-31"}


@override_settings(UNIVERSITY_MODE=True)
class OfferingChairsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("ofc-univ")

            def unit(name, unit_type, parent=None):
                return OrgUnit.objects.create(
                    organization=cls.org,
                    name=name,
                    slug=f"ofc-{OrgUnit.objects.count()}",
                    unit_type=unit_type,
                    parent=parent,
                )

            def period(name, year, start, end, current):
                return AcademicPeriod.objects.create(
                    organization=cls.org,
                    name=name,
                    period_type=AcademicPeriodType.SEMESTER,
                    academic_year=year,
                    start_date=start,
                    end_date=end,
                    is_current=current,
                )

            # Real (köçürülmüş) ağac: kafedra fakültənin uşağı, qrup isə İXTİSAS altında.
            cls.school = unit("Rəqəmsal texnologiyalar məktəbi", OrgUnitType.FACULTY)
            cls.prog = unit("Proqramlaşdırma kafedrası", OrgUnitType.CHAIR, cls.school)
            cls.it = unit("İnformasiya texnologiyaları kafedrası", OrgUnitType.CHAIR, cls.school)
            cls.eco = unit("Ekologiya məktəbi", OrgUnitType.FACULTY)
            cls.land = unit("Yer kadastrı kafedrası", OrgUnitType.CHAIR, cls.eco)
            cls.g_it = unit("236 İT", OrgUnitType.GROUP, unit("İT ixtisası", OrgUnitType.SPECIALTY, cls.school))
            cls.g_eco = unit("236 EK", OrgUnitType.GROUP, unit("Ekologiya", OrgUnitType.SPECIALTY, cls.eco))

            cls.fall = period("2026/2027 Payız", "2026/2027", dt.date(2026, 9, 15), dt.date(2027, 1, 31), True)
            cls.old = period("2025/2026 Yaz", "2025/2026", dt.date(2025, 2, 1), dt.date(2025, 6, 30), False)

            # Ştatca Proqramlaşdırmada, İT-nin fənnini saat hesabı ilə aparır.
            cls.cross = User.objects.create_user("ofc_cross", "ofc_cross@qku.edu.az", "pw")
            activate_member(cls.org, cls.cross, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.prog)
            # Ştatca (əsas) Yer kadastrında + yük faylından ƏLAVƏ Proqramlaşdırma üzvlüyü (prod halı).
            cls.multi = User.objects.create_user("ofc_multi", "ofc_multi@qku.edu.az", "pw")
            teacher_role = activate_member(
                cls.org, cls.multi, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.land
            )
            Membership.objects.filter(user=cls.multi).update(is_primary=True)
            Membership.objects.create(
                organization=cls.org, user=cls.multi, role=teacher_role, scope_unit=cls.prog, is_active=True
            )
            # Kafedrada yalnız inzibati («member») üzvlüyü olan müəllim — ştat sayılmır.
            cls.admin_member = User.objects.create_user("ofc_member", "ofc_member@qku.edu.az", "pw")
            activate_member(cls.org, cls.admin_member, "teacher", permissions=TEACHER_PERMS)
            member_role, _ = Role.objects.get_or_create(
                organization=cls.org,
                name="member",
                defaults={"display_name": "Member", "scope_type": RoleScopeType.UNIT},
            )
            Membership.objects.create(
                organization=cls.org, user=cls.admin_member, role=member_role, scope_unit=cls.it, is_active=True
            )

            def subject(code, name, chair=None):
                return Subject.objects.create(organization=cls.org, code=code, name=name, chair_unit=chair)

            cls.s_it = subject("OFC-IT", "Tədqiqat metodları")
            cls.s_prog = subject("OFC-PR", "Veb proqramlaşdırma")
            cls.s_civil = subject("OFC-MM", "Mülki müdafiə")
            cls.s_legacy = subject("OFC-OLD", "Köhnə fənn")
            cls.s_owned = subject("OFC-OWN", "Kafedralı fənn", chair=cls.it)

            def load(chair, subj, groups, status="distributed"):
                task, _ = TeachingTask.objects.get_or_create(
                    organization=cls.org, chair=chair, academic_year="2026/2027", defaults={"status": status}
                )
                row = TeachingTaskRow.objects.create(
                    organization=cls.org, task=task, period=cls.fall, subject=subj, total_hours=30
                )
                row.groups.set(groups)
                return row

            load(cls.it, cls.s_it, [cls.g_it])
            load(cls.prog, cls.s_prog, [cls.g_it])
            load(cls.land, cls.s_civil, [cls.g_it, cls.g_eco])

            def offering(code, subj, group, teacher, per=None):
                item = CourseOffering.objects.create(
                    organization=cls.org, subject=subj, period=per or cls.fall, group=group, instructor=teacher
                )
                Lesson.objects.create(
                    organization=cls.org,
                    offering=item,
                    date=(per or cls.fall).start_date + dt.timedelta(days=7),
                    kind=LessonKind.LECTURE,
                    hours=2,
                    topic=code,
                )
                return item

            cls.o_cross = offering("cross", cls.s_it, cls.g_it, cls.cross)  # ştat Proq → fənn İT
            cls.o_prog = offering("prog", cls.s_prog, cls.g_it, cls.multi)  # Proq yükü
            cls.o_civil_it = offering("civil-it", cls.s_civil, cls.g_it, cls.multi)  # Yer kadastrı yükü
            cls.o_civil_eco = offering("civil-eco", cls.s_civil, cls.g_eco, cls.multi)
            cls.o_owned = offering("owned", cls.s_owned, cls.g_eco, cls.cross)  # Subject.chair_unit = İT
            # Köçürülmüş: keçən il; İT fənninin yükü yalnız bu il var → fənnin yükü (İT).
            cls.o_old_it = offering("old-it", cls.s_it, cls.g_it, cls.cross, per=cls.old)
            # Yükdə izi olmayan köhnə fənn → müəllimin ŞTAT (əsas) kafedrası, əlavə üzvlük yox.
            cls.o_old_multi = offering("old-multi", cls.s_legacy, cls.g_eco, cls.multi, per=cls.old)
            # İnzibati üzvlük ştat deyil → heç bir kafedraya düşmür.
            cls.o_old_member = offering("old-member", cls.s_legacy, cls.g_it, cls.admin_member, per=cls.old)

            cls.admin = User.objects.create_user("ofc_admin", "ofc_admin@qku.edu.az", "pw", is_superuser=True)
            cls.rim = User.objects.create_user("ofc_rim", "ofc_rim@qku.edu.az", "pw")
            activate_member(
                cls.org,
                cls.rim,
                "rim_head",
                permissions=["course.view", "journal.roster", "unit.view"],
                level=90,
                scope_type=RoleScopeType.ORGANIZATION,
            )
            profile = cls.rim.profile
            profile.role = "rim_head"
            profile.save(update_fields=["role"])

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _chairs(self, offering):
        with bypass_rls():
            found = offering_chairs.offering_chairs(CourseOffering.objects.filter(pk=offering.pk), self.org.pk)
        return found[offering.pk]

    def _lessons_log(self, **params) -> set[str]:
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "lessons-log"})
        response = self._client(self.rim).get(url, dict(WINDOW, **params))
        self.assertEqual(response.status_code, 200)
        return {row["topic"] for row in response.context["lessons_log_section"]["rows"]}

    def _journal(self, **params) -> set[str]:
        query = {"year": "2026/2027", "season": "Payız semestri", **params}
        response = self._client(self.admin).get(reverse("registrar:journal_list"), query)
        self.assertEqual(response.status_code, 200)
        return {(o.subject.code, o.group.name) for o in response.context["offerings"]}

    # ── Tərif ────────────────────────────────────────────────────────────────

    def test_load_row_decides_not_the_teachers_staff_chair(self):
        self.assertEqual(self._chairs(self.o_cross), {str(self.it.pk)})
        self.assertEqual(self._chairs(self.o_civil_it), {str(self.land.pk)})
        self.assertEqual(self._chairs(self.o_prog), {str(self.prog.pk)})

    def test_subject_chair_when_no_load_row(self):
        self.assertEqual(self._chairs(self.o_owned), {str(self.it.pk)})

    def test_legacy_offering_follows_the_subjects_load(self):
        self.assertEqual(self._chairs(self.o_old_it), {str(self.it.pk)})

    def test_legacy_fallback_prefers_the_primary_teaching_membership(self):
        self.assertEqual(self._chairs(self.o_old_multi), {str(self.land.pk)})
        self.assertEqual(self._chairs(self.o_old_member), frozenset())

    def test_cancelled_task_is_ignored(self):
        with bypass_rls():
            TeachingTask.objects.filter(chair=self.land).update(status="cancelled")
        # Yük ləğv olunub → fənnin aparıcı kafedrası yox, yükü yox → müəllimin ştatı (Yer kadastrı, əsas).
        self.assertEqual(self._chairs(self.o_civil_it), {str(self.land.pk)})
        with bypass_rls():
            Membership.objects.filter(user=self.multi, scope_unit=self.land).update(is_active=False)
        self.assertEqual(self._chairs(self.o_civil_it), {str(self.prog.pk)})

    # ── «Keçilmiş dərslər» ───────────────────────────────────────────────────

    def test_lessons_log_cross_chair_teacher_shows_under_the_subjects_chair(self):
        self.assertEqual(self._lessons_log(ll_kafedra=str(self.it.pk)), {"cross", "owned", "old-it"})
        self.assertEqual(self._lessons_log(ll_kafedra=str(self.prog.pk)), {"prog"})

    def test_lessons_log_multi_membership_does_not_leak_civil_defence(self):
        self.assertEqual(self._lessons_log(ll_kafedra=str(self.land.pk)), {"civil-it", "civil-eco", "old-multi"})
        self.assertNotIn("civil-it", self._lessons_log(ll_kafedra=str(self.prog.pk)))

    def test_lessons_log_faculty_and_kafedra(self):
        self.assertEqual(
            self._lessons_log(ll_faculty=str(self.school.pk), ll_kafedra=str(self.it.pk)), {"cross", "old-it"}
        )
        # Fakültə + başqa fakültənin kafedrası → kaskad kafedranı atır, nəticə fakültənindir.
        self.assertEqual(
            self._lessons_log(ll_faculty=str(self.school.pk), ll_kafedra=str(self.land.pk)),
            {"cross", "prog", "civil-it", "old-it", "old-member"},
        )

    def test_lessons_log_kafedra_options_are_the_resolved_chairs(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "lessons-log"})
        section = self._client(self.rim).get(url, WINDOW).context["lessons_log_section"]
        field = next(f for f in section["filters"]["fields"] if f["name"] == "ll_kafedra")
        self.assertEqual(
            {o["value"] for o in field["options"]} - {""}, {str(self.prog.pk), str(self.it.pk), str(self.land.pk)}
        )

    # ── /jurnal/ ─────────────────────────────────────────────────────────────

    def test_journal_kafedra_without_faculty(self):
        self.assertEqual(self._journal(department=self.it.pk), {("OFC-IT", "236 İT"), ("OFC-OWN", "236 EK")})
        self.assertEqual(self._journal(department=self.prog.pk), {("OFC-PR", "236 İT")})
        self.assertEqual(self._journal(department=self.land.pk), {("OFC-MM", "236 İT"), ("OFC-MM", "236 EK")})

    def test_journal_faculty_and_kafedra(self):
        self.assertEqual(self._journal(faculty=self.school.pk, department=self.prog.pk), {("OFC-PR", "236 İT")})
        # Fakültəyə aid olmayan kafedra atılır (UI kaskadı) — boş yox, fakültənin nəticəsi.
        self.assertEqual(
            self._journal(faculty=self.school.pk, department=self.land.pk),
            {("OFC-IT", "236 İT"), ("OFC-PR", "236 İT"), ("OFC-MM", "236 İT")},
        )
        self.assertEqual(self._journal(faculty=self.eco.pk, department=self.land.pk), {("OFC-MM", "236 EK")})
