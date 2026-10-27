"""«Tapşırıq təyin olunmuşlar» səhifəsi — siyahı = giriş siyasəti, süzgəc/axtarış/sıra, qrup / tələbə əlavə et
(sehrbazın saxlama qapıları ilə), icazələr, sorğu büdcəsi (sahib 2026-10-27).

Bax ``apps/exams/services/exam_assignees.py`` və ``apps/exams/views/teacher/exams/assignee_edit.py``.
"""

from __future__ import annotations

import datetime
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamAttempt, ExamStudentPin
from apps.exams.services import exam_assignees, exam_subject_change, exam_unit_coverage
from apps.exams.services.student_pins import _assigned_student_ids
from apps.exams.tests.test_exam_unit_coverage_2026_10_27 import _REASON, _CoverageSetup
from apps.exams.tests.test_w4_wizard_units import _login, _UnitFixture
from apps.exams.views.teacher.exams.assignee_edit import AUDIT_REASON
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _Fixture(_UnitFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            User.objects.filter(pk=cls.student.pk).update(first_name="Əli", last_name="Məmmədov")
            User.objects.filter(pk=cls.student_other_group.pk).update(first_name="Zaur", last_name="Abbasov")
            cls.program = Program.objects.get(organization=cls.org, code="DZ")
            cls.curriculum = Curriculum.objects.get(organization=cls.org, program=cls.program)
        cls.student.refresh_from_db()
        cls.student_other_group.refresh_from_db()
        cls.student3 = cls._make_student("eas_student3", cls.group, first_name="Bəxtiyar", last_name="Cəfərov")

    @classmethod
    def _make_student(cls, username, unit, **names):
        from apps.accounts.models import ProfileRole
        from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org

        user = User.objects.create_user(username, f"{username}@test.az", PASSWORD, **names)
        _assign_user_to_org(user, cls.org, ProfileRole.STUDENT, "student")
        with bypass_rls():
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program,
                curriculum=cls.curriculum,
                group=unit,
                admission_year=2024,
            )
        return user

    def _page(self, exam, as_user=None, **params):
        return _login(as_user or self.teacher, self.org).get(
            reverse("exams:teacher_exam_assignees", kwargs={"slug": exam.slug}), params
        )

    def _post(self, exam, as_user=None, **data):
        return _login(as_user or self.teacher, self.org).post(
            reverse("exams:teacher_exam_assignees_update", kwargs={"slug": exam.slug}),
            data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @staticmethod
    def _ids(rows):
        return [row.user_id for row in rows]


class RosterMatchesAccessPolicyTests(_Fixture):
    def test_roster_is_group_plus_individual_minus_excluded(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        exam.allowed_users.add(self.student_other_group)
        exam.excluded_users.add(self.student3)
        rows = exam_assignees.build_roster(exam)
        by_id = {row.user_id: row for row in rows}

        eligible = {row.user_id for row in rows if not row.is_excluded}
        self.assertEqual(eligible, _assigned_student_ids(exam))
        self.assertEqual(eligible, {self.student.pk, self.student_other_group.pk})
        # İstisna edilən — siyahıda bayraqla; xaric olunmuş qeyd və başqa tenant — yoxdur.
        self.assertTrue(by_id[self.student3.pk].is_excluded)
        self.assertNotIn(self.student_expelled.pk, by_id)
        self.assertNotIn(self.student_b.pk, by_id)
        self.assertEqual(by_id[self.student.pk].sources, ("group",))
        self.assertEqual(by_id[self.student_other_group.pk].sources, ("individual",))
        self.assertEqual(by_id[self.student.pk].group_name, "634 ing")
        # Giriş siyasəti ilə üst-üstə düşür: siyahıdakı hər «verə bilən» imtahanı görür, istisna görmür.
        for row in rows:
            with self.subTest(user=row.user.username):
                self.assertEqual(exam.can_user_see(row.user), not row.is_excluded)
        self.assertEqual(exam_assignees.assignee_count(exam), 2)

    def test_attempt_status_and_score(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        with bypass_rls():
            ExamAttempt.objects.create(
                exam=exam, user=self.student, status="submitted", finished_at=timezone.now(), correct_count=3
            )
            ExamAttempt.objects.create(exam=exam, user=self.student3, status="in_progress")
            ExamAttempt.objects.create(
                exam=exam, user=self.student3, status="submitted", is_trial=True, attempt_number=2
            )
        rows = {row.user_id: row for row in exam_assignees.build_roster(exam)}
        self.assertEqual(rows[self.student.pk].status, exam_assignees.STATUS_FINISHED)
        self.assertEqual(rows[self.student3.pk].status, exam_assignees.STATUS_IN_PROGRESS)
        self.assertEqual(rows[self.student3.pk].attempts_count, 1)  # sınaq sayılmır
        exam_assignees.attach_scores(exam, list(rows.values()))
        self.assertEqual(rows[self.student.pk].score_text, "3 / 3")

    def test_final_exam_shows_pin_presence(self):
        exam = self._exam(exam_type_extended="midterm")
        exam.allowed_units.add(self.group)
        from apps.exams.services.student_pins import provision_exam_student_pins

        provision_exam_student_pins(exam)
        with bypass_rls():
            ExamStudentPin.objects.filter(exam=exam, student=self.student3).delete()
        rows = {row.user_id: row for row in exam_assignees.build_roster(exam)}
        self.assertTrue(rows[self.student.pk].has_pin)
        self.assertFalse(rows[self.student3.pk].has_pin)


class FilterSearchSortTests(_Fixture):
    def setUp(self):
        self.exam = self._exam()
        self.exam.allowed_units.add(self.group)
        self.exam.allowed_users.add(self.student_other_group)
        with bypass_rls():
            ExamAttempt.objects.create(
                exam=self.exam, user=self.student, status="submitted", finished_at=timezone.now()
            )

    def _rows(self, **params):
        response = self._page(self.exam, **params)
        self.assertEqual(response.status_code, 200)
        return self._ids(response.context["rows"])

    def test_default_sort_is_alphabetical_by_surname(self):
        self.assertEqual(self._rows(), [self.student_other_group.pk, self.student3.pk, self.student.pk])
        self.assertEqual(
            self._rows(order="name_desc"), [self.student.pk, self.student3.pk, self.student_other_group.pk]
        )
        self.assertEqual(
            self._rows(sort_by="name", sort_dir="desc"),
            [self.student.pk, self.student3.pk, self.student_other_group.pk],
        )

    def test_azerbaijani_alphabet_order(self):
        names = ["Zeynalov", "Şükürov", "Səfərov", "Əliyev", "Eyvazov", "İsmayılov", "Işıqlı"]
        self.assertEqual(
            sorted(names, key=exam_assignees.az_sort_key),
            ["Eyvazov", "Əliyev", "Işıqlı", "İsmayılov", "Səfərov", "Şükürov", "Zeynalov"],
        )

    def test_diacritic_tolerant_search(self):
        self.assertEqual(self._rows(q="memmed"), [self.student.pk])
        self.assertEqual(self._rows(q="CEFER"), [self.student3.pk])
        self.assertEqual(self._rows(q="w4u_student2"), [self.student_other_group.pk])

    def test_group_source_status_filters(self):
        self.assertEqual(self._rows(group="634 ing"), [self.student3.pk, self.student.pk])
        self.assertEqual(self._rows(source="individual"), [self.student_other_group.pk])
        self.assertEqual(self._rows(status="finished"), [self.student.pk])
        self.assertEqual(self._rows(status="not_started"), [self.student_other_group.pk, self.student3.pk])
        self.assertEqual(self._rows(status="excluded"), [])

    def test_group_chips_count_per_group(self):
        response = self._page(self.exam)
        self.assertEqual(dict(response.context["group_summary"]), {"634 ing": 2, "701 biz": 1})
        self.assertContains(response, "Tapşırıq təyin olunmuşlar")

    def test_detail_page_links_with_count(self):
        response = _login(self.teacher, self.org).get(
            reverse("exams:teacher_exam_detail", kwargs={"slug": self.exam.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["assignee_count"], 3)
        self.assertContains(response, reverse("exams:teacher_exam_assignees", kwargs={"slug": self.exam.slug}))


class PermissionTests(_Fixture):
    def test_author_can_edit(self):
        exam = self._exam()
        response = self._page(exam)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_edit"])
        self.assertContains(response, "js-eas-add-units")

    def test_other_teacher_and_student_are_denied(self):
        from apps.accounts.models import ProfileRole
        from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org

        exam = self._exam()
        stranger = User.objects.create_user("eas_stranger", "eas_stranger@test.az", PASSWORD)
        _assign_user_to_org(stranger, self.org, ProfileRole.TEACHER, "teacher")
        self.assertEqual(self._page(exam, as_user=stranger).status_code, 404)
        self.assertEqual(self._post(exam, as_user=stranger, action="add_users", users=self.student.pk).status_code, 403)
        self.assertEqual(self._page(exam, as_user=self.student).status_code, 403)
        self.assertEqual(
            self._post(exam, as_user=self.student, action="add_users", users=self.student.pk).status_code, 403
        )
        self.assertFalse(exam.allowed_users.exists())

    def test_without_exam_edit_permission_page_is_read_only(self):
        exam = self._exam()
        with bypass_rls():
            role = self.org.roles.get(name="teacher")
            role.permissions = [perm for perm in role.permissions if perm not in ("exam.edit", "exam.*", "*")]
            role.save(update_fields=["permissions"])
        response = self._page(exam)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_edit"])
        self.assertNotContains(response, "js-eas-add-units")
        self.assertEqual(self._post(exam, action="add_users", users=self.student.pk).status_code, 403)


class EditActionTests(_Fixture):
    def _audit(self, exam):
        with bypass_rls():
            return list(AuditLog.objects.filter(reason=AUDIT_REASON, object_id=str(exam.pk)).order_by("created_at"))

    def test_add_group_goes_through_scope_and_provisions_pins(self):
        exam = self._exam(exam_type_extended="midterm")
        response = self._post(exam, action="add_units", allowed_units=str(self.group.pk))
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(set(exam.allowed_units.values_list("pk", flat=True)), {self.group.pk})
        with bypass_rls():
            pins = set(ExamStudentPin.objects.filter(exam=exam).values_list("student_id", flat=True))
        self.assertEqual(pins, {self.student.pk, self.student3.pk})
        audit = self._audit(exam)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].changes["action"], "add_units")
        # Təkrar əlavə → 400, başqa tenantın qrupu → 400 (sehrbazın `allowed_units_invalid` qapısı).
        self.assertEqual(self._post(exam, action="add_units", allowed_units=str(self.group.pk)).status_code, 400)
        self.assertEqual(self._post(exam, action="add_units", allowed_units=str(self.group_b.pk)).status_code, 400)
        self.assertEqual(set(exam.allowed_units.values_list("pk", flat=True)), {self.group.pk})

    def test_remove_group(self):
        exam = self._exam()
        exam.allowed_units.add(self.group, self.group_other)
        response = self._post(exam, action="remove_unit", unit=str(self.group.pk))
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(set(exam.allowed_units.values_list("pk", flat=True)), {self.group_other.pk})
        self.assertEqual(self._post(exam, action="remove_unit", unit=str(self.group.pk)).status_code, 400)

    def test_add_and_remove_individual_student(self):
        exam = self._exam()
        exam.excluded_users.add(self.student_other_group)
        response = self._post(exam, action="add_users", users=[self.student_other_group.pk])
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertTrue(exam.allowed_users.filter(pk=self.student_other_group.pk).exists())
        self.assertFalse(exam.excluded_users.exists())  # fərdi əlavə istisnanı götürür
        self.assertIn(self.student_other_group.pk, _assigned_student_ids(exam))
        response = self._post(exam, action="remove_user", user=self.student_other_group.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(exam.allowed_users.exists())
        self.assertEqual([log.changes["action"] for log in self._audit(exam)], ["add_users", "remove_user"])

    def test_add_user_outside_tenant_is_rejected(self):
        exam = self._exam()
        response = self._post(exam, action="add_users", users=[self.student_b.pk])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(exam.allowed_users.exists())

    def test_exclude_and_restore_group_student(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        response = self._post(exam, action="exclude_user", user=self.student3.pk)
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertNotIn(self.student3.pk, _assigned_student_ids(exam))
        self.assertFalse(exam.can_user_see(self.student3))
        response = self._post(exam, action="include_user", user=self.student3.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.student3.pk, _assigned_student_ids(exam))

    def test_exclude_only_applies_to_group_assigned_students(self):
        exam = self._exam()
        exam.allowed_users.add(self.student_other_group)
        response = self._post(exam, action="exclude_user", user=self.student_other_group.pk)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(exam.excluded_users.exists())

    def test_unknown_action_is_rejected(self):
        self.assertEqual(self._post(self._exam(), action="drop_table").status_code, 400)


class QueryBudgetTests(_Fixture):
    def _bulk_students(self, unit, count, prefix):
        users = User.objects.bulk_create(
            [User(username=f"{prefix}{index}", email=f"{prefix}{index}@test.az") for index in range(count)]
        )
        with bypass_rls():
            role = self.org.roles.get(name="student")
            Membership.objects.bulk_create(
                [Membership(user=user, organization=self.org, role=role, is_active=True) for user in users]
            )
            for user in users:
                StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=user,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=unit,
                    admission_year=2024,
                )
        return users

    def _count(self, exam):
        client = _login(self.teacher, self.org)
        url = reverse("exams:teacher_exam_assignees", kwargs={"slug": exam.slug})
        client.get(url)  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx), response

    def test_300_student_list_has_constant_query_count(self):
        small = self._exam(title="Small", exam_type_extended="midterm")
        small.allowed_units.add(self.group_other)
        with bypass_rls():
            big_unit = OrgUnit.objects.create(
                organization=self.org, name="900 big", slug="eas-big", unit_type=OrgUnitType.GROUP
            )
        users = self._bulk_students(big_unit, 300, "eas_bulk_")
        big = self._exam(title="Big", exam_type_extended="midterm")
        big.allowed_units.add(big_unit)
        with bypass_rls():
            for user in users[:40]:
                ExamAttempt.objects.create(exam=big, user=user, status="submitted", finished_at=timezone.now())
        small_count, _ = self._count(small)
        big_count, response = self._count(big)
        self.assertEqual(response.context["stats"]["eligible"], 300)
        self.assertEqual(response.context["page_obj"].paginator.count, 300)
        self.assertLessEqual(big_count, small_count + 6, (small_count, big_count))
        self.assertLessEqual(big_count, 50)


class GuardTests(_CoverageSetup):
    """Sehrbazın qapıları: fənnin jurnalında olmayan qrup (məcburi əlavə + səbəb) və fənn/jurnal təsdiqi."""

    def _exam_obj(self, subject):
        now = timezone.now()
        with bypass_rls():
            return Exam.objects.create(
                title="EAS midterm",
                author=self.center,
                organization=self.org,
                exam_type="test",
                exam_type_extended="midterm",
                subject=subject,
                is_active=False,
                start_datetime=now,
                end_datetime=now + datetime.timedelta(days=1),
            )

    def _post(self, exam, **data):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=False):
            return client.post(
                reverse("exams:teacher_exam_assignees_update", kwargs={"slug": exam.slug}),
                {"action": "add_units", "allowed_units": str(self.group.pk), **data},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

    def _units(self, exam):
        with bypass_rls():
            return set(Exam.objects.get(pk=exam.pk).allowed_units.values_list("pk", flat=True))

    def test_uncovered_group_needs_forced_reason_and_is_audited(self):
        exam = self._exam_obj(self.history)
        response = self._post(exam)
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual([row["id"] for row in payload["unit_coverage_required"]], [str(self.group.pk)])
        self.assertEqual(self._units(exam), set())

        response = self._post(exam, forced_units=json.dumps({str(self.group.pk): "qısa"}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._units(exam), set())

        response = self._post(exam, forced_units=json.dumps({str(self.group.pk): _REASON}))
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._units(exam), {self.group.pk})
        with bypass_rls():
            forced = AuditLog.objects.filter(
                resource_type=exam_unit_coverage.AUDIT_RESOURCE, resource_id=str(exam.pk)
            ).get()
        self.assertEqual(forced.reason, _REASON)

    def test_covered_group_needs_no_reason(self):
        exam = self._exam_obj(self.subject)
        response = self._post(exam)
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._units(exam), {self.group.pk})

    def test_subject_journal_guard_requires_confirmation(self):
        exam = self._exam_obj(self.subject)
        decision = exam_subject_change.Decision(
            students=2,
            old_subject_id=self.subject.pk,
            old_subject_label="X",
            new_subject_id=self.subject.pk,
            new_subject_label="X",
            old_link_ids=frozenset(),
            new_link_ids=frozenset(),
        )
        with mock.patch.object(exam_subject_change, "decide", return_value=decision):
            response = self._post(exam)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["subject_change_required"]["students"], 2)
            self.assertEqual(self._units(exam), set())
            response = self._post(
                exam, subject_change_confirm="1", subject_change_reason="Qrup səhvən əlavə olunmamışdı"
            )
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._units(exam), {self.group.pk})
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type=exam_subject_change.AUDIT_RESOURCE, resource_id=str(exam.pk)
                ).exists()
            )
