"""
2026-09-14 (audit 2026-09-13, `findings/tests.md` §1 · F-T11) — media giriş yoxlayıcıları.

Coverage cədvəlində 0 % olan checker-lər:
* `core/media_policies.py`: `register_media_policy` (+ `registered_prefixes`,
  `resolve_checker`), `check_guest_roster_document_access`,
  `check_workload_amendment_access`;
* `core/media_views.py`: `_check_exam_paint_access`, `_check_lab_file_access`
  (4 alt-yol), `_check_course_resource_access`, `_check_trial_exam_access`.

(`check_notification_file_access` / `check_assignment_submission_access` artıq
`test_audit_2026_09_13_media_export.py`-də örtülüb — burada təkrarlanmır.)

Hər checker üçün matris: sahib/aid aktor → 200; eyni təşkilatın aidiyyəti
olmayan üzvü → 404; yad tenant → 404; anonim → login-ə 302 (deny-by-default
qaydası: 403 deyil, 404 — faylın mövcudluğu sızmır). Naxış:
`core/tests/test_audit_2026_09_13_media_export.py::_MediaBase`.
"""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.courses.models import Course, CourseResource
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion
from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, GuestRosterDocument, Subject
from apps.trial_exams.models import TrialExamRequest
from apps.workload.constants import AmendmentReason, AmendmentTarget
from apps.workload.models import TeachingTask, WorkloadAmendment
from core import media_policies
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.media_views import protected_media
from core.rls import bypass_rls

User = get_user_model()

_MEDIA_SETTINGS = dict(
    MEDIA_URL="/media/",
    SERVE_MEDIA=True,
    DEBUG=False,
    MEDIA_ACCEL_REDIRECT_URL="",
    OBJECT_STORAGE_ENABLED=False,
)


def _write_media_file(media_root: str, path: str) -> None:
    full = os.path.join(media_root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as handle:
        handle.write(b"%PDF-1.4 w2 media")


class _MediaBase(TestCase):
    """İki tenant: A (əsas) və B (yad). A-da müəllim, iki tələbə, dekan, rektor."""

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("w2m_teacher", "w2m_teacher@qku.edu.az", "pw")
        cls.student = User.objects.create_user("w2m_student", "w2m_student@qku.edu.az", "pw")
        cls.other_student = User.objects.create_user("w2m_other", "w2m_other@qku.edu.az", "pw")
        cls.dean = User.objects.create_user("w2m_dean", "w2m_dean@qku.edu.az", "pw")
        cls.rector = User.objects.create_user("w2m_rector", "w2m_rector@qku.edu.az", "pw")
        cls.foreign_teacher = User.objects.create_user("w2m_foreign", "w2m_foreign@other.edu.az", "pw")
        cls.foreign_student = User.objects.create_user("w2m_fstudent", "w2m_fstudent@other.edu.az", "pw")
        cls.superadmin = User.objects.create_superuser("w2m_root", "w2m_root@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="W2 Media Org",
                slug="w2-media-org",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.rector,
                status="active",
                is_active=True,
            )
            cls.other_org = Organization.objects.create(
                name="W2 Foreign Org",
                slug="w2-foreign-org",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.foreign_teacher,
                status="active",
                is_active=True,
            )
            for user, org, role in (
                (cls.teacher, cls.org, "teacher"),
                (cls.student, cls.org, "student"),
                (cls.other_student, cls.org, "student"),
                (cls.dean, cls.org, "dean"),
                (cls.rector, cls.org, "rector"),
                (cls.foreign_teacher, cls.other_org, "teacher"),
                (cls.foreign_student, cls.other_org, "student"),
            ):
                Membership.objects.create(
                    user=user, organization=org, role=org.roles.get(name=role), is_primary=True, is_active=True
                )
            cls.course = Course.objects.create(
                owner=cls.teacher, title="W2 Media Kursu", status="published", organization=cls.org
            )

    def setUp(self):
        self.media_tmp = tempfile.mkdtemp()
        self.factory = RequestFactory()
        override = override_settings(MEDIA_ROOT=self.media_tmp, **_MEDIA_SETTINGS)
        override.enable()
        self.addCleanup(override.disable)

    def _file(self, path: str) -> str:
        _write_media_file(self.media_tmp, path)
        return path

    def _status(self, user, path) -> int:
        request = self.factory.get(f"/media/{path}")
        request.user = user
        try:
            return protected_media(request, path=path).status_code
        except Http404:
            return 404

    def assert_matrix(self, path, *, allowed=(), denied=()):
        for user in allowed:
            with self.subTest(user=user.username, expected=200):
                self.assertEqual(self._status(user, path), 200)
        for user in denied:
            with self.subTest(user=user.username, expected=404):
                self.assertEqual(self._status(user, path), 404)
        with self.subTest(user="anonymous"):
            request = self.factory.get(f"/media/{path}")
            request.user = AnonymousUser()
            response = protected_media(request, path=path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"])
        # Superadmin həmişə keçir (qlobal səlahiyyət).
        self.assertEqual(self._status(self.superadmin, path), 200)


class GuestRosterDocumentMediaTest(_MediaBase):
    """`guest_roster_documents/` — tələbə, açılışın müəllimi, `journal.roster` (dekan), org-admin (rektor)."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız W2",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            group = OrgUnit.objects.create(
                organization=self.org, name="W2-101", slug="w2-media-101", unit_type=OrgUnitType.GROUP
            )
            subject = Subject.objects.create(organization=self.org, code="W2M101", name="Media fənni", ects=3)
            self.offering = CourseOffering.objects.create(
                organization=self.org, subject=subject, period=period, group=group, instructor=self.teacher
            )
            enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.offering, kind="mandatory"
            )
            self.path = self._file(f"guest_roster_documents/{self.org.pk}/serencam.pdf")
            GuestRosterDocument.objects.create(
                organization=self.org,
                enrollment=enrollment,
                document=self.path,
                note="sərəncam №7",
                uploaded_by=self.dean,
            )

    def test_matrix(self):
        self.assert_matrix(
            self.path,
            allowed=(self.student, self.teacher, self.dean, self.rector),
            denied=(self.other_student, self.foreign_teacher, self.foreign_student),
        )

    def test_unknown_file_under_prefix_is_denied_even_for_admin(self):
        ghost = self._file(f"guest_roster_documents/{self.org.pk}/olmayan.pdf")
        self.assertEqual(self._status(self.rector, ghost), 404)
        self.assertEqual(self._status(self.student, ghost), 404)


class WorkloadAmendmentMediaTest(_MediaBase):
    """`workload_amendments/` — sənədin təşkilatında `workload.view` daşıyan aktor."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            chair = OrgUnit.objects.create(
                organization=self.org, name="W2 kafedra", slug="w2-media-chair", unit_type=OrgUnitType.CHAIR
            )
            task = TeachingTask.objects.create(
                organization=self.org, chair=chair, academic_year="2026/2027", created_by=self.dean
            )
            # FileField(max_length=100) — UUID-li real yol sığmır, qısa test yolu.
            self.path = self._file(f"workload_amendments/{self.org.pk}/t1/emr.pdf")
            WorkloadAmendment.objects.create(
                organization=self.org,
                task=task,
                target_kind=AmendmentTarget.ROW,
                target_id=task.pk,
                reason=AmendmentReason.OTHER,
                note="W2 düzəliş əmri",
                document=self.path,
                made_by=self.dean,
            )

    def test_matrix(self):
        # Kataloq: teacher/dean/rector `workload.view` daşıyır; tələbə daşımır;
        # yad tenantın müəllimi eyni açarı daşısa da BAŞQA təşkilatdadır.
        self.assert_matrix(
            self.path,
            allowed=(self.teacher, self.dean, self.rector),
            denied=(self.student, self.other_student, self.foreign_teacher),
        )

    def test_unknown_file_is_denied(self):
        ghost = self._file(f"workload_amendments/{self.org.pk}/x/yox.pdf")
        self.assertEqual(self._status(self.rector, ghost), 404)


class ExamPaintMediaTest(_MediaBase):
    """`exam_paints/` — cavabın tələbəsi və ya imtahan təşkilatının müəllim səviyyəli üzvü."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            exam = Exam.objects.create(
                title="Paint imtahanı", author=self.teacher, organization=self.org, exam_type="written"
            )
            question = ExamQuestion.objects.create(exam=exam, order=1, text="Çək")
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted", attempt_number=1)
            self.path = self._file("exam_paints/2026/09/w2_paint.png")
            ExamAnswer.objects.create(attempt=attempt, question=question, has_paint=True, paint_image=self.path)

    def test_matrix(self):
        self.assert_matrix(
            self.path,
            allowed=(self.student, self.teacher, self.dean, self.rector),
            denied=(self.other_student, self.foreign_teacher, self.foreign_student),
        )

    def test_unknown_paint_is_denied(self):
        ghost = self._file("exam_paints/2026/09/yox.png")
        self.assertEqual(self._status(self.teacher, ghost), 404)


class LabFileMediaTest(_MediaBase):
    """`labs/` — dörd alt-yol, hər birinin öz qaydası; naməlum alt-yol rədd."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        with bypass_rls():
            self.teacher_path = self._file("labs/teacher_files/2026/09/w2_metodika.pdf")
            self.lab = Lab.objects.create(
                course=self.course,
                title="W2 Lab",
                start_datetime=now - timedelta(hours=1),
                end_datetime=now + timedelta(days=1),
                status="published",
                teacher_files=self.teacher_path,
                created_by=self.teacher,
            )
            block = LabBlock.objects.create(lab=self.lab, title="Blok", order=1)
            self.question_path = self._file("labs/questions/2026/09/w2_sual.pdf")
            self.question = LabQuestion.objects.create(
                block=block, question_number=1, question_text="Sual", attachment=self.question_path
            )
            assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
            self.submission_path = self._file("labs/submissions/2026/09/w2_tehvil.zip")
            LabSubmission.objects.create(assignment=assignment, submission_file=self.submission_path)
            self.answer_path = self._file("labs/answers/2026/09/w2_cavab.py")
            LabAnswer.objects.create(
                lab=self.lab, question=self.question, student=self.student, answer_file=self.answer_path
            )

    def test_teacher_files_only_teacher_level(self):
        self.assert_matrix(
            self.teacher_path,
            allowed=(self.teacher, self.dean, self.rector),
            denied=(self.student, self.other_student, self.foreign_teacher),
        )

    def test_question_attachment_any_org_member(self):
        self.assert_matrix(
            self.question_path,
            allowed=(self.student, self.other_student, self.teacher),
            denied=(self.foreign_teacher, self.foreign_student),
        )

    def test_submission_owner_or_teacher_level(self):
        self.assert_matrix(
            self.submission_path,
            allowed=(self.student, self.teacher, self.rector),
            denied=(self.other_student, self.foreign_teacher),
        )

    def test_answer_owner_or_teacher_level(self):
        self.assert_matrix(
            self.answer_path,
            allowed=(self.student, self.teacher, self.rector),
            denied=(self.other_student, self.foreign_teacher),
        )

    def test_unknown_sub_path_is_denied_for_everyone_but_superadmin(self):
        ghost = self._file("labs/other/2026/09/w2_x.pdf")
        for user in (self.teacher, self.rector, self.student):
            with self.subTest(user=user.username):
                self.assertEqual(self._status(user, ghost), 404)
        self.assertEqual(self._status(self.superadmin, ghost), 200)

    def test_unknown_file_under_known_sub_path_is_denied(self):
        ghost = self._file("labs/submissions/2026/09/yox.zip")
        self.assertEqual(self._status(self.teacher, ghost), 404)


class CourseResourceMediaTest(_MediaBase):
    """`course_resources/` — kursun təşkilatının istənilən aktiv üzvü."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.path = self._file("course_resources/2026/09/w2_muhazire.pdf")
            CourseResource.objects.create(course=self.course, title="Mühazirə 1", resource_type="file", file=self.path)

    def test_matrix(self):
        self.assert_matrix(
            self.path,
            allowed=(self.student, self.other_student, self.teacher, self.rector),
            denied=(self.foreign_teacher, self.foreign_student),
        )

    def test_inactive_membership_is_denied(self):
        Membership.objects.filter(user=self.other_student, organization=self.org).update(is_active=False)
        self.assertEqual(self._status(self.other_student, self.path), 404)

    def test_unknown_resource_is_denied(self):
        ghost = self._file("course_resources/2026/09/yox.pdf")
        self.assertEqual(self._status(self.teacher, ghost), 404)


class TrialExamMediaTest(_MediaBase):
    """`trial_exams/` — yalnız müraciəti göndərən istifadəçi (superadmin qlobal)."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.path = self._file("trial_exams/2026/09/w2_suallar.pdf")
            TrialExamRequest.objects.create(
                user=self.student,
                full_name="Tələbə W2",
                email="w2m_student@qku.edu.az",
                subject_name="Riyaziyyat",
                questions_file=self.path,
            )
            self.orphan_path = self._file("trial_exams/2026/09/w2_qonaq.pdf")
            TrialExamRequest.objects.create(
                user=None,
                full_name="Qonaq",
                email="qonaq@example.test",
                subject_name="Fizika",
                questions_file=self.orphan_path,
            )

    def test_matrix(self):
        # Müəllim/rektor belə görmür — müraciət şəxsi fayldır.
        self.assert_matrix(
            self.path,
            allowed=(self.student,),
            denied=(self.other_student, self.teacher, self.rector, self.foreign_teacher),
        )

    def test_request_without_user_is_denied_to_everyone_but_superadmin(self):
        for user in (self.student, self.teacher, self.rector):
            with self.subTest(user=user.username):
                self.assertEqual(self._status(user, self.orphan_path), 404)
        self.assertEqual(self._status(self.superadmin, self.orphan_path), 200)

    def test_staff_flag_alone_does_not_bypass(self):
        """`is_staff` Django admin bayrağıdır — tenant səlahiyyəti vermir (reqressiya)."""
        User.objects.filter(pk=self.teacher.pk).update(is_staff=True)
        self.teacher.refresh_from_db()
        self.assertEqual(self._status(self.teacher, self.path), 404)


class RuntimeMediaPolicyRegistryTest(_MediaBase):
    """`register_media_policy` — app-ın `ready()`-dən qoşduğu siyasət statik default-u əvəz edir."""

    def _register(self, prefix, checker):
        media_policies.register_media_policy(prefix, checker)
        self.addCleanup(media_policies._RUNTIME_POLICIES.pop, prefix, None)

    def test_prefix_must_end_with_slash(self):
        with self.assertRaises(ValueError):
            media_policies.register_media_policy("w2_bad_prefix", lambda user, path: True)
        self.assertNotIn("w2_bad_prefix", media_policies.registered_prefixes())

    def test_new_prefix_is_served_through_registered_checker(self):
        prefix = "w2_runtime_prefix/"
        path = self._file(f"{prefix}fayl.pdf")
        # Qeydsiz: naməlum private yol → hamıya 404 (deny-by-default).
        self.assertEqual(self._status(self.teacher, path), 404)

        self._register(prefix, lambda user, p: user.pk == self.student.pk and p == path)
        self.assertIn(prefix, media_policies.registered_prefixes())
        self.assertEqual(self._status(self.student, path), 200)
        self.assertEqual(self._status(self.teacher, path), 404)
        self.assertEqual(self._status(self.foreign_student, path), 404)

    def test_runtime_registration_overrides_static_checker(self):
        path = self._file("course_resources/2026/09/w2_override.pdf")
        with bypass_rls():
            CourseResource.objects.create(course=self.course, title="Override", resource_type="file", file=path)
        self.assertEqual(self._status(self.student, path), 200)

        self._register("course_resources/", lambda user, p: False)
        self.assertEqual(self._status(self.student, path), 404)
        self.assertEqual(self._status(self.teacher, path), 404)
        # Superadmin runtime siyasətindən də əvvəl keçir.
        self.assertEqual(self._status(self.superadmin, path), 200)

    def test_resolve_checker_precedence(self):
        static = media_policies.ACCESS_CHECKERS["applications/"]
        self.assertIs(media_policies.resolve_checker("applications/"), static)
        sentinel = object()
        self.assertIs(media_policies.resolve_checker("applications/", default=sentinel), sentinel)

        runtime = lambda user, path: False  # noqa: E731
        self._register("applications/", runtime)
        self.assertIs(media_policies.resolve_checker("applications/", default=sentinel), runtime)
        # Sonuncu qeyd qüvvədədir (idempotent).
        runtime2 = lambda user, path: True  # noqa: E731
        self._register("applications/", runtime2)
        self.assertIs(media_policies.resolve_checker("applications/"), runtime2)
        self.assertEqual(media_policies.registered_prefixes().count("applications/"), 1)
