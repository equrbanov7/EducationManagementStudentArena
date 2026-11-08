"""Tələbə + heyət rolu — «özünə / öz qrupuna toxunma» qapısı (sahib qaydası 2026-11-08).

Ssenari (sahibin konkret halı): magistrant «632/6 İ» qrupunda oxuyur və öz dekanlığına (qrupu da orada) «tyutor»
rolu alır. Heyət rolu ilə özünü, qrup yoldaşlarını, öz qrupunu (alt qrupu ilə) və öz jurnallarını görə / dəyişə
bilməməlidir; eyni əhatədəki BAŞQA qruplar isə əvvəlki kimi açıqdır. Adi tyutor və adi tələbə dəyişmir.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.services import people
from apps.accounts.services.people.movements import registry_records_qs
from apps.accounts.services.rim.policy import RimAccessError
from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.organizations.public import (
    SelfConflictDenied,
    get_permission_scope,
    is_self_conflict,
    own_scope,
    scope_org_units,
)
from apps.registrar import gradebook, guest_roster, journal_access, journal_scope, services
from apps.registrar.models import (
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

_EXTRA_TUTOR_PERMISSIONS = [
    "student.registry_view",
    "student.movement",
    "unit.group_manage",
    "journal.view",
    "final_score.entry",
]


class _SelfConflictBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sc_owner", "sc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SC Univ",
                slug="sc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            tutor_role = cls.org.roles.get(name="tutor")
            tutor_role.permissions = sorted(set(tutor_role.permissions or []) | set(_EXTRA_TUTOR_PERMISSIONS))
            tutor_role.save(update_fields=["permissions"])
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Rəqəmsal Texnologiya", slug="sc-f", unit_type=OrgUnitType.FACULTY
            )
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org,
                name="İnformatika",
                slug="sc-s",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.faculty,
            )
            cls.own_group = OrgUnit.objects.create(
                organization=cls.org, name="632/6 İ", slug="sc-g-own", unit_type=OrgUnitType.GROUP, parent=cls.specialty
            )
            cls.sub_group = OrgUnit.objects.create(
                organization=cls.org,
                name="632/6 İ-1",
                slug="sc-g-sub",
                unit_type=OrgUnitType.GROUP,
                parent=cls.specialty,
                settings={"parent_group": str(cls.own_group.pk)},
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, name="633 İ", slug="sc-g-other", unit_type=OrgUnitType.GROUP, parent=cls.specialty
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="INF", name="İnformatika")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)
            cls.subject = Subject.objects.create(organization=cls.org, code="INF601", name="Alqoritmlər")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )

            # Magistrant + tyutor (+ müəllim — öz qrupunun jurnalına təyin olunsa belə qiymət yaza bilməməlidir).
            cls.maryam, cls.maryam_record = cls._student("sc_maryam", cls.own_group)
            cls._member(cls.maryam, "tutor", cls.faculty, primary=False)
            cls._member(cls.maryam, "teacher", None, primary=False)
            cls.mate, cls.mate_record = cls._student("sc_mate", cls.own_group)
            cls.sub_mate, cls.sub_mate_record = cls._student("sc_sub", cls.sub_group)
            cls.other, cls.other_record = cls._student("sc_other", cls.other_group)

            cls.plain_tutor = User.objects.create_user("sc_tutor", "sc_tutor@qku.edu.az", "pw")
            cls._member(cls.plain_tutor, "tutor", cls.faculty)

            cls.own_offering = cls.mate.enrollments.get(offering__subject=cls.subject).offering
            cls.other_offering = cls.other.enrollments.get(offering__subject=cls.subject).offering

    @classmethod
    def _member(cls, user, role, unit, *, primary=True):
        return Membership.objects.create(
            user=user,
            organization=cls.org,
            role=cls.org.roles.get(name=role),
            scope_unit=unit,
            is_primary=primary,
            is_active=True,
        )

    @classmethod
    def _student(cls, username, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        cls._member(user, "student", group)
        record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2026,
        )
        services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        return user, record

    def _fresh(self, user):
        """Hər testdə təzə user instansı — request-ömürlü yaddaşlar (üzvlük / öz əhatə) sıfırdan."""
        return User.objects.get(pk=user.pk)

    def _request(self, user):
        request = RequestFactory().get("/accounts/profile/")
        request.user = user
        request.organization = self.org
        return request

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class OwnScopeTest(_SelfConflictBase):
    def test_own_scope_covers_self_group_family_mates_and_journals(self):
        with bypass_rls():
            scope = own_scope(self._fresh(self.maryam), self.org)
        self.assertEqual(scope.user_ids, {str(self.maryam.pk)})
        self.assertEqual(scope.group_ids, {str(self.own_group.pk), str(self.sub_group.pk)})
        self.assertTrue({str(self.maryam.pk), str(self.mate.pk), str(self.sub_mate.pk)} <= scope.student_ids)
        self.assertNotIn(str(self.other.pk), scope.student_ids)
        self.assertIn(str(self.own_offering.pk), scope.offering_ids)
        self.assertNotIn(str(self.other_offering.pk), scope.offering_ids)
        self.assertIn(str(self.mate_record.pk), scope.record_ids)

    def test_plain_staff_and_plain_student_are_unaffected_without_queries(self):
        for user in (self.plain_tutor, self.mate):
            fresh = self._fresh(user)
            with bypass_rls():
                get_permission_scope(fresh, self.org, "unit.view")  # üzvlüklər yaddaşa düşür (adi axın)
                with CaptureQueriesContext(connection) as ctx:
                    scope = own_scope(fresh, self.org)
                    conflict = is_self_conflict(fresh, self.org, group_id=self.own_group.pk)
            self.assertFalse(scope)
            self.assertFalse(conflict)
            self.assertEqual(len(ctx.captured_queries), 0, user.username)

    def test_staff_scope_excludes_own_group_but_student_keys_do_not(self):
        maryam = self._fresh(self.maryam)
        with bypass_rls():
            staff = get_permission_scope(maryam, self.org, "unit.view")
            student_key = get_permission_scope(maryam, self.org, "course.view")
            plain = get_permission_scope(self._fresh(self.plain_tutor), self.org, "unit.view")
        self.assertEqual(staff.excluded_unit_ids, {str(self.own_group.pk), str(self.sub_group.pk)})
        self.assertEqual(student_key.excluded_unit_ids, frozenset())
        self.assertEqual(plain.excluded_unit_ids, frozenset())


class VisibilityTest(_SelfConflictBase):
    def test_groups_registry_hides_own_group_family_only(self):
        with bypass_rls():
            scope = get_permission_scope(self._fresh(self.maryam), self.org, "unit.view")
            visible = set(
                scope_org_units(OrgUnit.objects.filter(organization=self.org, unit_type="group"), scope).values_list(
                    "pk", flat=True
                )
            )
            plain_scope = get_permission_scope(self._fresh(self.plain_tutor), self.org, "unit.view")
            plain_visible = set(
                scope_org_units(
                    OrgUnit.objects.filter(organization=self.org, unit_type="group"), plain_scope
                ).values_list("pk", flat=True)
            )
        self.assertEqual(visible, {self.other_group.pk})
        self.assertEqual(plain_visible, {self.own_group.pk, self.sub_group.pk, self.other_group.pk})

    def test_student_catalog_and_registry_hide_self_and_mates(self):
        with bypass_rls():
            actor = people.resolve_actor(self._request(self._fresh(self.maryam)))
            catalog = set(people.visible_students_qs(actor).values_list("pk", flat=True))
            registry = set(registry_records_qs(actor).values_list("student_id", flat=True))
        self.assertIn(self.other.pk, catalog)
        for hidden in (self.maryam.pk, self.mate.pk, self.sub_mate.pk):
            self.assertNotIn(hidden, catalog)
            self.assertNotIn(hidden, registry)

    def test_guest_roster_group_picker_and_journal_list_hide_own_group(self):
        maryam = self._fresh(self.maryam)
        with bypass_rls():
            groups = set(guest_roster.scoped_group_queryset(maryam, self.org).values_list("pk", flat=True))
            journal_q = journal_scope.journal_view_q(maryam, self.org)
            journals = set(
                type(self.own_offering).objects.filter(journal_q).values_list("pk", flat=True) if journal_q else []
            )
        self.assertEqual(groups, {self.other_group.pk})
        self.assertNotIn(self.own_offering.pk, journals)
        self.assertIn(self.other_offering.pk, journals)


class ActionsTest(_SelfConflictBase):
    def _deny_logs(self):
        return AuditLog.objects.filter(organization=self.org, reason__startswith="self_conflict")

    def test_transfer_of_self_or_mate_is_refused_with_403_and_audited(self):
        for record in (self.maryam_record, self.mate_record):
            with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
                people.transfer_group(
                    people.resolve_actor(self._request(self._fresh(self.maryam))),
                    record_id=str(record.pk),
                    new_group_id=str(self.other_group.pk),
                    reason="Dekanlıq sərəncamı №1",
                )
            self.assertEqual(ctx.exception.status, 403)
            self.assertEqual(ctx.exception.reason_code, "self_conflict")
        with bypass_rls():
            self.assertEqual(self._deny_logs().count(), 2)

    def test_transfer_of_other_group_student_is_not_a_self_conflict(self):
        with bypass_rls():
            actor = people.resolve_actor(self._request(self._fresh(self.maryam)))
            try:
                people.transfer_group(
                    actor,
                    record_id=str(self.other_record.pk),
                    new_group_id=str(self.other_group.pk),
                    reason="Dekanlıq sərəncamı №2",
                )
            except RimAccessError as exc:  # məs. «onsuz da bu qrupdadır» — amma self_conflict DEYİL
                self.assertNotEqual(exc.reason_code, "self_conflict")

    def test_guest_roster_in_own_group_journal_is_refused(self):
        maryam = self._fresh(self.maryam)
        with bypass_rls():
            self.assertFalse(guest_roster.can_manage_offering_roster(maryam, self.own_offering))
            self.assertTrue(guest_roster.can_manage_offering_roster(maryam, self.other_offering))
            with self.assertRaises(SelfConflictDenied):
                guest_roster.add_guest_student(
                    offering=self.own_offering, student=self.other, by_user=maryam, reason="x"
                )
        response = self._client(self.maryam).post(
            reverse("registrar:journal_guest_add", args=[self.own_offering.pk]),
            {"student": self.other.pk, "group": str(self.other_group.pk)},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "self_conflict")
        self.assertIn("tələbəsiniz", response.json()["message"])

    def test_marks_in_enrolled_journal_are_refused_even_as_instructor(self):
        with bypass_rls():
            for offering in (self.own_offering, self.other_offering):
                offering.instructor = self.maryam
                offering.save(update_fields=["instructor"])
            maryam = self._fresh(self.maryam)
            self.assertFalse(journal_access.can_edit_journal(maryam, self.own_offering))
            self.assertFalse(journal_access.is_direct_editor(maryam, self.own_offering))
            self.assertTrue(journal_access.can_edit_journal(maryam, self.other_offering))
            with self.assertRaises(SelfConflictDenied):
                gradebook.save_marks(offering=self.own_offering, entries=[], by_user=maryam)
            gradebook.save_marks(offering=self.other_offering, entries=[], by_user=maryam)

    def test_journal_detail_of_own_group_is_403(self):
        response = self._client(self.maryam).get(reverse("registrar:journal_detail", args=[self.own_offering.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "tələbəsiniz", status_code=403)

    def test_plain_tutor_keeps_roster_access_to_every_group(self):
        tutor = self._fresh(self.plain_tutor)
        with bypass_rls():
            self.assertTrue(guest_roster.can_manage_offering_roster(tutor, self.own_offering))
            self.assertTrue(guest_roster.can_manage_offering_roster(tutor, self.other_offering))


class MoreActionsTest(_SelfConflictBase):
    def test_groups_registry_action_on_own_group_is_403(self):
        response = self._client(self.maryam).post(
            reverse("organizations:group_action", args=[self.org.slug]),
            {"action": "add_students", "id": str(self.own_group.pk), "record_ids": str(self.other_record.pk)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "self_conflict")

    def test_rim_manage_of_groupmate_is_refused(self):
        from apps.accounts.services.rim import policy as rim_policy

        with bypass_rls():
            actor = rim_policy.RimActor(
                user=self._fresh(self.maryam), organization=self.org, level=40, is_superadmin=False
            )
            with self.assertRaises(RimAccessError) as ctx:
                rim_policy.assert_can_manage(actor, self.mate)
            hidden = set(rim_policy.manageable_users_queryset(actor).values_list("pk", flat=True))
        self.assertEqual(ctx.exception.reason_code, "self_conflict")
        self.assertNotIn(self.mate.pk, hidden)
        self.assertNotIn(self.sub_mate.pk, hidden)

    def test_exam_score_entry_on_own_offering_is_refused(self):
        from apps.registrar import exam_score_entry

        maryam = self._fresh(self.maryam)
        with bypass_rls():
            with self.assertRaises(SelfConflictDenied):
                exam_score_entry.assert_offering_in_actor_scope(maryam, self.org, self.own_offering)
            exam_score_entry.assert_offering_in_actor_scope(maryam, self.org, self.other_offering)

    def test_schedule_management_of_own_group_is_refused(self):
        from apps.registrar import schedule_manage

        maryam = self._fresh(self.maryam)
        with bypass_rls():
            self.assertFalse(schedule_manage.can_manage_offering(maryam, self.org, self.own_offering))
            self.assertTrue(schedule_manage.can_manage_offering(maryam, self.org, self.other_offering))
            self.assertFalse(schedule_manage.can_manage_group_subject(maryam, self.org, self.own_group, self.subject))


class DatabaseGuardTest(_SelfConflictBase):
    def test_db_rejects_mark_authored_by_a_student_of_the_offering(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.own_offering,
                date=datetime.date(2026, 9, 15),
                kind=LessonKind.SEMINAR,
            )
            enrollment = Enrollment.objects.get(offering=self.own_offering, student=self.mate)
            with self.assertRaises(IntegrityError), transaction.atomic():
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=enrollment, entered_by=self.maryam
                )
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, entered_by=self.plain_tutor
            )

    def test_update_keeping_the_author_passes_and_count_command_reports_legacy_rows(self):
        """Köhnə pozuntu: müəllif eyni qalan UPDATE keçir, müəllifi tələbəyə dəyişmək keçmir; say əmri onu tapır."""
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        from io import StringIO

        from django.core.management import call_command

        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.other_offering,
                date=datetime.date(2026, 9, 16),
                kind=LessonKind.SEMINAR,
            )
            enrollment = Enrollment.objects.get(offering=self.other_offering, student=self.other)
            mark = LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, entered_by=self.maryam
            )
            # Sonradan həmin açılışa yazılır → köhnə sətir artıq «pozuntu»dur.
            own = Enrollment.objects.create(organization=self.org, student=self.maryam, offering=self.other_offering)
            mark.score = 5
            mark.save(update_fields=["score", "entered_by", "enrollment", "updated_at"])  # eyni müəllif → keçir
            out = StringIO()
            call_command("count_self_conflict_marks", stdout=out)
            other = LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=own, entered_by=self.plain_tutor
            )
            other.entered_by = self.maryam
            with self.assertRaises(IntegrityError), transaction.atomic():
                other.save(update_fields=["entered_by"])
        self.assertIn("registrar_lessonmark: 1", out.getvalue())
        self.assertIn("TOTAL: 1", out.getvalue())


class ReviewFixesTest(_SelfConflictBase):
    def test_cache_key_separates_excluded_scope(self):
        from apps.accounts import academic_records_cache
        from apps.organizations.public import UnitScope

        plain = UnitScope(scope_type="unit", unit_ids=frozenset({self.faculty.pk}), unit_paths=(self.faculty.path,))
        mixed = UnitScope(
            scope_type="unit",
            unit_ids=frozenset({self.faculty.pk}),
            unit_paths=(self.faculty.path,),
            excluded_unit_ids=frozenset({str(self.own_group.pk)}),
        )
        self.assertNotEqual(
            academic_records_cache.scope_key(self.org, plain, {}),
            academic_records_cache.scope_key(self.org, mixed, {}),
        )

    def test_student_in_subgroup_covers_parent_and_sibling_subgroups(self):
        with bypass_rls():
            sub2 = OrgUnit.objects.create(
                organization=self.org,
                name="632/6 İ-2",
                slug="sc-g-sub2",
                unit_type=OrgUnitType.GROUP,
                parent=self.specialty,
                settings={"parent_group": str(self.own_group.pk)},
            )
            sub2_mate, _record = self._student("sc_sub2", sub2)
            tutor, _record = self._student("sc_subtutor", self.sub_group)
            self._member(tutor, "tutor", self.faculty, primary=False)
            scope = own_scope(self._fresh(tutor), self.org)
        self.assertEqual(scope.group_ids, {str(self.own_group.pk), str(self.sub_group.pk), str(sub2.pk)})
        self.assertIn(str(sub2_mate.pk), scope.student_ids)
        self.assertIn(str(self.mate.pk), scope.student_ids)

    def test_corrector_paths_skip_own_journals(self):
        from unittest import mock

        from apps.registrar.journal_list_scope import journal_list_base

        maryam = self._fresh(self.maryam)
        request = self._request(maryam)
        with bypass_rls(), mock.patch("apps.registrar.corrections.can_correct_journal", return_value=True):
            self.assertFalse(journal_access.can_correct_offering(request, self.own_offering))
            self.assertTrue(journal_access.can_correct_offering(request, self.other_offering))
            queryset, broad = journal_list_base(maryam, request)
            visible = set(queryset.values_list("pk", flat=True))
        self.assertTrue(broad)
        self.assertNotIn(self.own_offering.pk, visible)
        self.assertIn(self.other_offering.pk, visible)

    def test_absence_credit_on_own_journal_is_refused(self):
        from unittest import mock

        with mock.patch("apps.registrar.corrections.can_correct_journal", return_value=True):
            response = self._client(self.maryam).post(
                reverse("registrar:absence_credit_apply", args=[self.own_offering.pk]),
                {"enrollment": "x", "hours": "2", "reason": "x" * 12, "request_token": "x"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "self_conflict")

    def test_denial_audit_survives_atomic_request_rollback(self):
        """Prod ATOMIC_REQUESTS: 403 rollback-indən sonra da audit qalır; qrup yoldaşı BAŞQA jurnala əlavə olunmur."""
        settings_dict = connection.settings_dict
        previous = settings_dict.get("ATOMIC_REQUESTS", False)
        settings_dict["ATOMIC_REQUESTS"] = True
        try:
            response = self._client(self.maryam).post(
                reverse("registrar:journal_guest_add", args=[self.other_offering.pk]),
                {"student": self.sub_mate.pk, "group": str(self.sub_group.pk)},
                HTTP_ACCEPT="application/json",
            )
        finally:
            settings_dict["ATOMIC_REQUESTS"] = previous
        self.assertEqual(response.status_code, 403)
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__startswith="self_conflict").exists())

    def test_plain_form_post_gets_html_403_not_json(self):
        response = self._client(self.maryam).post(
            reverse("registrar:journal_detail", args=[self.own_offering.pk]), {"action": "x"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, "tələbəsiniz", status_code=403)
