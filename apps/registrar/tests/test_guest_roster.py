"""«Alt qrupdan tələbə əlavə et» — jurnal siyahısının idarəsi (guest roster).

Sahibin tələbi (2026-08): bir fənnin jurnalına BAŞQA (alt) qrupdan tələbə əlavə
etmək mümkün olsun; həmin tələbə YALNIZ orada görünsün, jurnalda «alt qrupdan
əlavə olunub» işarəsi olsun; geri götürmə mümkün olsun; əməl koordinator/
dekanlıq səviyyəsindədir və audit olunur.

Burada yoxlanılan invariantlar:

* model qərarı — əlavə qeydiyyat (Enrollment) + `source_group` provenansı;
* təcrid — tələbə yalnız HƏMİN açılışın jurnalında görünür;
* təkrar əlavə mümkün deyil (unikal məhdudiyyət + servis yoxlaması);
* icazə/əhatə fail-closed (`journal.roster` + unit alt-ağacı);
* audit — kim, nə vaxt, kimi, hansı qrupdan;
* geri götürmə soft-dur (bal tarixçəsi qalır) və adi tələbəyə tətbiq olunmur.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, guest_roster, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _GuestRosterBase(TestCase):
    """Bir fakültə · bir kafedra · İKİ qrup (G1 hədəf, G2 alt qrup) + kənar fakültə."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gr_owner", "gr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GR Univ",
                slug="gr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="gr-f", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="gr-k", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
            )
            cls.group1 = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="gr-g1", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.group2 = OrgUnit.objects.create(
                organization=cls.org, name="G2", slug="gr-g2", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.far_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Uzaq fakültə", slug="gr-ff", unit_type=OrgUnitType.FACULTY
            )
            cls.far_group = OrgUnit.objects.create(
                organization=cls.org, name="GX", slug="gr-gx", unit_type=OrgUnitType.GROUP, parent=cls.far_faculty
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            cls.teacher = User.objects.create_user("gr_teacher", "gr_teacher@qku.edu.az", "pw")
            cls.coordinator = User.objects.create_user("gr_coord", "gr_coord@qku.edu.az", "pw")
            cls.outsider = User.objects.create_user("gr_out", "gr_out@qku.edu.az", "pw")
            for user, role, unit in (
                (cls.teacher, "teacher", None),
                (cls.coordinator, "program_coordinator", cls.chair),
                (cls.outsider, "program_coordinator", cls.far_faculty),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )

            cls.program = Program.objects.create(organization=cls.org, code="TAR", name="Tarix")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.history = Subject.objects.create(organization=cls.org, code="TAR101", name="Tarix")
            cls.math = Subject.objects.create(organization=cls.org, code="RIY101", name="Riyaziyyat")
            for subject in (cls.history, cls.math):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=cls.curriculum, subject=subject, semester_number=1
                )

            cls.host = cls._make_student("gr_host", cls.group1)
            cls.guest = cls._make_student("gr_guest", cls.group2)
            cls.far_student = cls._make_student("gr_far", cls.far_group)

            cls.offering = cls.host.enrollments.get(offering__subject=cls.history).offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            # Alt qrupun ÖZ Tarix jurnalı (təcrid yoxlaması üçün).
            cls.other_offering = cls.guest.enrollments.get(offering__subject=cls.history).offering

    @classmethod
    def _make_student(cls, username, group):
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
            curriculum=cls.curriculum,
            group=group,
            admission_year=2025,
        )
        services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        return student

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _drop_own_history(self, student):
        """Tələbəni öz qrupunun Tarix jurnalından çıxar (alt qrup ssenarisi)."""
        with bypass_rls():
            enrollment = student.enrollments.get(offering__subject=self.history)
            enrollment.status = Enrollment.Status.DROPPED
            enrollment.save(update_fields=["status"])


class GuestModelDecisionTest(_GuestRosterBase):
    """Model qərarı: yeni model YOX — mövcud Enrollment + provenans sahələri."""

    def test_add_creates_enrollment_with_source_group(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator, reason="alt qrup birləşməsi"
            )
        self.assertEqual(enrollment.offering_id, self.offering.id)
        self.assertEqual(enrollment.source_group_id, self.group2.id)
        self.assertEqual(enrollment.added_by_id, self.coordinator.id)
        self.assertIsNotNone(enrollment.added_at)
        self.assertTrue(enrollment.is_guest)

    def test_guest_appears_only_in_that_journal(self):
        """Tələbə YALNIZ həmin açılışın jurnalında görünür — başqasında yox."""
        self._drop_own_history(self.guest)
        with bypass_rls():
            guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
            target = gradebook.get_offering_journal(offering=self.offering)
            other = gradebook.get_offering_journal(offering=self.other_offering)
            math_offering = self.host.enrollments.get(offering__subject=self.math).offering
            math = gradebook.get_offering_journal(offering=math_offering)

        self.assertIn(self.guest.id, [row["student"].id for row in target["rows"]])
        self.assertNotIn(self.guest.id, [row["student"].id for row in other["rows"]])
        self.assertNotIn(self.guest.id, [row["student"].id for row in math["rows"]])

    def test_journal_row_carries_guest_flag_and_source(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
            journal = gradebook.get_offering_journal(offering=self.offering)
        rows = {row["student"].id: row for row in journal["rows"]}
        self.assertTrue(rows[self.guest.id]["is_guest"])
        self.assertEqual(rows[self.guest.id]["source_group"].id, self.group2.id)
        self.assertFalse(rows[self.host.id]["is_guest"])
        self.assertEqual([row["student"].id for row in journal["guest_rows"]], [self.guest.id])

    def test_own_group_student_is_rejected(self):
        with bypass_rls(), self.assertRaises(ValidationError):
            guest_roster.add_guest_student(offering=self.offering, student=self.host, by_user=self.coordinator)

    def test_duplicate_add_is_rejected(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
            self.assertEqual(Enrollment.objects.filter(offering=self.offering, student=self.guest).count(), 1)

    def test_source_group_is_pinned_to_the_validated_group(self):
        """Provenans HTTP qatının yoxladığı qrupa bağlanır — «ən yeni qeyd» seçilmir."""
        self._drop_own_history(self.guest)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(
                    offering=self.offering,
                    student=self.guest,
                    by_user=self.coordinator,
                    source_group=self.far_group,  # tələbə bu qrupda deyil
                )
            enrollment = guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
            )
        self.assertEqual(enrollment.source_group_id, self.group2.id)

    def test_student_active_in_another_journal_of_same_subject_is_rejected(self):
        """Öz qrupunun Tarix jurnalında AKTİV olan tələbə ikiqat yazıla bilməz."""
        with bypass_rls(), self.assertRaises(ValidationError):
            guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)


class GuestRemovalTest(_GuestRosterBase):
    def test_remove_is_soft_and_keeps_marks(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator
            )
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2025, 10, 1),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, status=AttendanceStatus.ABSENT
            )
            guest_roster.remove_guest_student(offering=self.offering, enrollment=enrollment, by_user=self.coordinator)
            enrollment.refresh_from_db()
            journal = gradebook.get_offering_journal(offering=self.offering)

        self.assertEqual(enrollment.status, Enrollment.Status.DROPPED)
        self.assertEqual(enrollment.source_group_id, self.group2.id)  # provenans qalır
        self.assertEqual(LessonMark.objects.filter(enrollment=enrollment).count(), 1)
        self.assertNotIn(self.guest.id, [row["student"].id for row in journal["rows"]])

    def test_regular_student_cannot_be_removed_this_way(self):
        with bypass_rls():
            enrollment = self.host.enrollments.get(offering=self.offering)
            with self.assertRaises(ValidationError):
                guest_roster.remove_guest_student(
                    offering=self.offering, enrollment=enrollment, by_user=self.coordinator
                )
            enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)

    def test_readd_after_removal_reuses_the_row(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator
            )
            guest_roster.remove_guest_student(offering=self.offering, enrollment=enrollment, by_user=self.coordinator)
            again = guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
        self.assertEqual(again.pk, enrollment.pk)
        self.assertEqual(again.status, Enrollment.Status.ENROLLED)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering, student=self.guest).count(), 1)


class GuestAuditTest(_GuestRosterBase):
    def test_add_and_remove_are_audited(self):
        from django.apps import apps as django_apps

        audit_model = django_apps.get_model("audit", "AuditLog")
        self._drop_own_history(self.guest)
        with bypass_rls():
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator, reason="dekanlıq sərəncamı"
            )
            guest_roster.remove_guest_student(offering=self.offering, enrollment=enrollment, by_user=self.coordinator)
            rows = list(audit_model.objects.filter(resource_type="registrar.journal_guest").order_by("created_at"))
        self.assertEqual(len(rows), 2)
        added = rows[0]
        self.assertEqual(added.user_id, self.coordinator.id)
        self.assertEqual(added.changes["verb"], "add")
        self.assertEqual(added.changes["source_group"], "G2")
        self.assertEqual(added.changes["target_group"], "G1")
        self.assertEqual(added.changes["student_id"], str(self.guest.id))
        self.assertEqual(added.reason, "dekanlıq sərəncamı")
        self.assertEqual(rows[1].changes["verb"], "remove")


class GuestPermissionTest(_GuestRosterBase):
    """İcazə + struktur əhatəsi fail-closed-dur."""

    def test_teacher_has_no_roster_permission(self):
        self.assertFalse(guest_roster.can_manage_offering_roster(self.teacher, self.offering))

    def test_coordinator_in_scope_may_manage(self):
        self.assertTrue(guest_roster.can_manage_offering_roster(self.coordinator, self.offering))

    def test_coordinator_outside_scope_may_not(self):
        self.assertFalse(guest_roster.can_manage_offering_roster(self.outsider, self.offering))

    def test_group_lookup_is_scope_limited(self):
        client = self._client(self.coordinator)
        payload = client.get(reverse("registrar:journal_guest_group_search", args=[self.offering.id])).json()
        names = [row["text"] for row in payload["results"]]
        self.assertIn("G2", names)
        self.assertNotIn("G1", names)  # hədəf qrupun özü namizəd deyil
        self.assertNotIn("GX", names)  # kənar fakültə əhatədən kənardır

    def test_outsider_gets_404_on_every_surface(self):
        client = self._client(self.outsider)
        for name in (
            "registrar:journal_guest_group_search",
            "registrar:journal_guest_student_search",
        ):
            self.assertEqual(client.get(reverse(name, args=[self.offering.id])).status_code, 404)
        self.assertEqual(
            client.post(reverse("registrar:journal_guest_add", args=[self.offering.id]), {}).status_code, 404
        )

    def test_teacher_cannot_add_via_http(self):
        client = self._client(self.teacher)
        self.assertEqual(
            client.post(
                reverse("registrar:journal_guest_add", args=[self.offering.id]),
                {"group": str(self.group2.id), "student": str(self.guest.id)},
            ).status_code,
            404,
        )


class GuestHttpFlowTest(_GuestRosterBase):
    def test_already_enrolled_student_is_listed_but_not_selectable(self):
        """Sahibin UX tələbi: jurnalda olan tələbə GÖRÜNÜR, amma seçilə bilmir.

        Əvvəllər belə tələbə siyahıdan tamamilə çıxarılırdı və istifadəçi
        «axtardığım tələbə niyə yoxdur?» sualı ilə qalırdı.
        """
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        url = reverse("registrar:journal_guest_student_search", args=[self.offering.id])
        before = client.get(url, {"group": str(self.group2.id)}).json()
        row = next(r for r in before["results"] if r["id"] == str(self.guest.id))
        self.assertFalse(row["disabled"])
        self.assertEqual(row["hint"], "")

        client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )

        after = client.get(url, {"group": str(self.group2.id)}).json()
        listed = next(r for r in after["results"] if r["id"] == str(self.guest.id))
        # Siyahıdan DÜŞMÜR...
        self.assertTrue(listed["disabled"])
        # ...və səbəb MƏTNLƏ yazılır (yalnız rəng/bayraq deyil — a11y).
        self.assertTrue(listed["hint"])

    def test_disabled_candidate_still_cannot_be_added(self):
        """Görünürlük icazə deyil: `disabled` sətri POST-la da keçməməlidir."""
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        payload = {"group": str(self.group2.id), "student": str(self.guest.id)}
        self.assertTrue(
            client.post(reverse("registrar:journal_guest_add", args=[self.offering.id]), payload).json()["ok"]
        )

        repeat = client.post(reverse("registrar:journal_guest_add", args=[self.offering.id]), payload)
        self.assertFalse(repeat.json()["ok"])
        with bypass_rls():
            self.assertEqual(
                Enrollment.objects.filter(
                    offering=self.offering, student=self.guest, status=Enrollment.Status.ENROLLED
                ).count(),
                1,
            )

    def test_add_then_remove_over_http(self):
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        added = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id), "reason": "alt qrup"},
        )
        self.assertEqual(added.status_code, 200)
        body = added.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["source_group"], "G2")

        removed = client.post(
            reverse("registrar:journal_guest_remove", args=[self.offering.id]),
            {"enrollment": body["enrollment_id"]},
        )
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["ok"])
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=body["enrollment_id"]).status, Enrollment.Status.DROPPED)

    def test_add_from_group_outside_scope_is_refused(self):
        client = self._client(self.coordinator)
        resp = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.far_group.id), "student": str(self.far_student.id)},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["ok"])

    def test_malformed_ids_do_not_500(self):
        client = self._client(self.coordinator)
        self.assertEqual(
            client.get(
                reverse("registrar:journal_guest_student_search", args=[self.offering.id]), {"group": "not-a-uuid"}
            ).status_code,
            200,
        )
        self.assertEqual(
            client.post(
                reverse("registrar:journal_guest_remove", args=[self.offering.id]), {"enrollment": "nope"}
            ).status_code,
            404,
        )

    def test_journal_page_shows_button_and_chip_for_coordinator(self):
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )
        page = client.get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn("data-jgs-open", page)
        self.assertIn("data-jgs-modal", page)
        self.assertIn("jgs-chip", page)
        # Təsdiqdən əvvəlki xülasə + qrup seçilməmiş vəziyyət izahı.
        self.assertIn("data-jgs-summary", page)
        self.assertIn("data-jgs-hintbox", page)

    def test_page_carries_in_place_refresh_hooks(self):
        """Yerində yenilənmə müqaviləsi: JS bu iki qarmağa arxalanır.

        Onlar şablondan itsə, əməldən sonra cədvəl səssizcə yenilənməzdi —
        ona görə qarmaqlar testlə bağlanır.
        """
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        added = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        ).json()
        page = client.get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn("data-jgs-tbody", page)
        # Vurğulanacaq sətir məhz enrollment id-si ilə tapılır.
        self.assertIn('data-jd-enrollment="%s"' % added["enrollment_id"], page)

    def test_teacher_page_has_no_roster_controls(self):
        page = (
            self._client(self.teacher)
            .get(reverse("registrar:journal_detail", args=[self.offering.id]))
            .content.decode()
        )
        self.assertNotIn("data-jgs-open", page)
        self.assertNotIn("data-jgs-modal", page)


@override_settings(UNIVERSITY_MODE=True)
class GuestRosterNavigationTest(_GuestRosterBase):
    """Sidebar keçidi: koordinator jurnal iş sahəsinə ÇATA bilməlidir.

    Sahibin (c) tələbi «sidebardan ora keçid». Sidebar bəndi mövcud
    `my-journal` bölməsidir və müəllim/admin üçün `/jurnal/` iş sahəsini açır.
    Amma siyahı ƏVVƏLLƏR yalnız `instructor=user` ilə süzülürdü — koordinator
    linkə basıb BOŞ siyahı görərdi. Bu testlər həmin zənciri bağlayır.
    """

    def test_coordinator_sees_subtree_offerings_in_journal_list(self):
        page = self._client(self.coordinator).get(reverse("registrar:journal_list"))
        self.assertEqual(page.status_code, 200)
        offering_ids = {str(o.id) for o in page.context["offerings"]}
        self.assertIn(str(self.offering.id), offering_ids)

    def test_outsider_coordinator_does_not_see_them(self):
        """Əhatə fail-closed: kənar fakültənin koordinatoru bu jurnalı görməməlidir."""
        page = self._client(self.outsider).get(reverse("registrar:journal_list"))
        offering_ids = {str(o.id) for o in page.context["offerings"]}
        self.assertNotIn(str(self.offering.id), offering_ids)

    def test_coordinator_gets_journal_sidebar_entry(self):
        """`my-journal` bəndi icazə sahibinə açıq, adi tələbə-olmayan kənara yox."""
        from apps.accounts.views._helpers.rbac import _role_capabilities

        client = self._client(self.coordinator)
        # `active_organization` middleware tərəfindən request-in user-inə qoyulur,
        # ona görə qabiliyyətlər MƏHZ o user obyektindən hesablanır.
        request = client.get(reverse("registrar:journal_list")).wsgi_request
        capabilities = _role_capabilities(request.user, getattr(request.user, "profile", None))
        self.assertTrue(capabilities["can_manage_journal_roster"])
        self.assertIn("my-journal", capabilities["allowed_sections"])
