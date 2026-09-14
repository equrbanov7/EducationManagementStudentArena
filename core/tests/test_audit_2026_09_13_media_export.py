"""2026-09-13 təhlükəsizlik auditi — F-02 (media prefiksləri) və F-07 (formula neytrallaşdırması).

F-02: ``assignments/submissions/``, ``notifications/files/``, ``notifications/images/``
``default_storage.save`` ilə yazılır, amma media checker reyestrində yox idi →
deny-by-default sayəsində sızma yox, amma superadmin-dən başqa hər kəsə 404
(auditorun reprosu ``scratchpad/audit/security/repro/test_media_unregistered_prefixes.py``
bunu «auth → 404» kimi sənədləşdirirdi). Burada həmin repro TƏRSİNƏ çevrilir:
aid aktor 200, yad aktor 404.

F-07: ``core.export_safety`` — ``=``/``+``/``-``/``@``/nəzarət simvolu ilə başlayan
mətn xanaları ``'`` prefiksi alır; ədədlər dəyişmir; CSV və openpyxl yolları.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course, CourseMembership
from apps.notifications.models import InAppNotification, NotificationType
from apps.organizations.models import Membership, Organization
from core import export_safety
from core.constants import OrganizationType
from core.media_policies import ACCESS_CHECKERS, PRIVATE_PREFIXES
from core.media_views import _ACCESS_CHECKERS, protected_media
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
        handle.write(b"%PDF-1.4 audit")


class _MediaBase(TestCase):
    """Ortaq: təşkilat, müəllim (kurs sahibi), tələbə, yad tələbə, media kökü."""

    def setUp(self):
        self.media_tmp = tempfile.mkdtemp()
        self.factory = RequestFactory()
        override = override_settings(MEDIA_ROOT=self.media_tmp, **_MEDIA_SETTINGS)
        override.enable()
        self.addCleanup(override.disable)

        self.teacher = User.objects.create_user("md_teacher", "md_teacher@qku.edu.az", "pw")
        self.student = User.objects.create_user("md_student", "md_student@qku.edu.az", "pw")
        self.outsider = User.objects.create_user("md_outsider", "md_outsider@qku.edu.az", "pw")
        self.assistant = User.objects.create_user("md_assistant", "md_assistant@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Media Audit Org",
                slug="media-audit-org",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.teacher,
                status="active",
                is_active=True,
            )
            for user, role in (
                (self.teacher, "teacher"),
                (self.student, "student"),
                (self.outsider, "student"),
                (self.assistant, "teacher"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )

    def _get(self, user, path):
        request = self.factory.get(f"/media/{path}")
        request.user = user
        return protected_media(request, path=path)

    def _status(self, user, path) -> int:
        from django.http import Http404

        try:
            return self._get(user, path).status_code
        except Http404:
            return 404


class RegistryCoverageTest(SimpleTestCase):
    """Üç prefiks həm PRIVATE_PREFIXES-də, həm də checker reyestrindədir."""

    def test_prefixes_registered(self):
        for prefix in ("assignments/submissions/", "notifications/files/", "notifications/images/"):
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, PRIVATE_PREFIXES)
                self.assertIn(prefix, ACCESS_CHECKERS)
                self.assertIn(prefix, _ACCESS_CHECKERS)


class AssignmentSubmissionMediaTest(_MediaBase):
    """``assignments/submissions/`` — göndərən tələbə, kurs sahibi, kurs asistanı: 200; yad: 404."""

    def setUp(self):
        super().setUp()
        self.path = "assignments/submissions/audit_f02_cavab.pdf"
        _write_media_file(self.media_tmp, self.path)
        with bypass_rls():
            self.course = Course.objects.create(
                owner=self.teacher, title="F-02 Kursu", status="published", organization=self.org
            )
            CourseMembership.objects.create(course=self.course, user=self.assistant, role="assistant")
            self.assignment = Assignment.objects.create(
                course=self.course,
                title="F-02 tapşırığı",
                start_date=timezone.now() - timedelta(days=1),
                due_date=timezone.now() + timedelta(days=2),
                status="published",
            )
            Submission.objects.create(
                assignment=self.assignment,
                user=self.student,
                content="cavab",
                status="submitted",
                files=[{"name": "cavab.pdf", "path": self.path, "size": 12}],
            )

    def test_submitting_student_can_open_own_file(self):
        self.assertEqual(self._status(self.student, self.path), 200)

    def test_course_owner_can_open_submission(self):
        self.assertEqual(self._status(self.teacher, self.path), 200)

    def test_course_assistant_can_open_submission(self):
        self.assertEqual(self._status(self.assistant, self.path), 200)

    def test_other_student_is_denied(self):
        self.assertEqual(self._status(self.outsider, self.path), 404)

    def test_unknown_file_under_prefix_is_denied_even_for_owner(self):
        ghost = "assignments/submissions/olmayan.pdf"
        _write_media_file(self.media_tmp, ghost)
        self.assertEqual(self._status(self.teacher, ghost), 404)


class NotificationAttachmentMediaTest(_MediaBase):
    """``notifications/files|images/`` — alıcı və təşkilatın müəllim səviyyəli üzvü: 200; yad: 404."""

    def setUp(self):
        super().setUp()
        self.file_path = "notifications/files/audit_f02_elave.pdf"
        self.image_path = "notifications/images/audit_f02_sekil.png"
        _write_media_file(self.media_tmp, self.file_path)
        _write_media_file(self.media_tmp, self.image_path)
        # Alıcı — ``student``; ``outsider`` eyni təşkilatın tələbəsidir, amma alıcı deyil.
        with bypass_rls():
            InAppNotification.objects.create(
                recipient=self.student,
                organization=self.org,
                title="F-02 bildirişi",
                notification_type=NotificationType.SYSTEM,
                metadata={
                    "image_url": f"/media/{self.image_path}",
                    "attachments": [{"name": "elave.pdf", "url": f"/media/{self.file_path}", "size": 12}],
                },
            )

    def test_recipient_can_open_attachment_and_image(self):
        self.assertEqual(self._status(self.student, self.file_path), 200)
        self.assertEqual(self._status(self.student, self.image_path), 200)

    def test_org_teacher_can_open_attachment(self):
        """Dərc edən şəxs ayrıca saxlanmır — müəllim səviyyəli üzv (dərc səlahiyyəti) görür."""
        self.assertEqual(self._status(self.teacher, self.file_path), 200)

    def test_non_recipient_student_is_denied(self):
        self.assertEqual(self._status(self.outsider, self.file_path), 404)
        self.assertEqual(self._status(self.outsider, self.image_path), 404)

    def test_unknown_file_under_prefix_is_denied(self):
        ghost = "notifications/files/olmayan.pdf"
        _write_media_file(self.media_tmp, ghost)
        self.assertEqual(self._status(self.teacher, ghost), 404)

    def test_global_notification_only_recipient(self):
        """Təşkilatsız bildirişdə müəllim qapısı işləmir — yalnız alıcı."""
        path = "notifications/files/audit_f02_qlobal.pdf"
        _write_media_file(self.media_tmp, path)
        with bypass_rls():
            InAppNotification.objects.create(
                recipient=self.outsider,
                organization=None,
                title="qlobal",
                notification_type=NotificationType.SYSTEM,
                metadata={"attachments": [{"name": "q.pdf", "url": f"/media/{path}", "size": 1}]},
            )
        self.assertEqual(self._status(self.outsider, path), 200)
        self.assertEqual(self._status(self.teacher, path), 404)


class ExportSafetyHelperTest(SimpleTestCase):
    """F-07: ``core.export_safety`` qaydaları."""

    def test_formula_like_strings_get_prefix(self):
        for raw in ("=1+1", "+cmd", "-5", "@SUM(A1)", "\t=x", "\r=x", "  =HYPERLINK()"):
            with self.subTest(raw=raw):
                self.assertEqual(export_safety.neutralise_cell(raw), "'" + raw)

    def test_plain_values_untouched(self):
        for raw in ("Əli Vəliyev", "", None, 5, 5.5, Decimal("-3.5"), -7, "2026-09-13", "—", "q/b"):
            with self.subTest(raw=raw):
                self.assertEqual(export_safety.neutralise_cell(raw), raw)

    def test_row_helper(self):
        self.assertEqual(export_safety.neutralise_row(["=a", 1, "b"]), ["'=a", 1, "b"])

    def test_safe_csv_writer_neutralises(self):
        buffer = io.StringIO()
        writer = export_safety.safe_csv_writer(buffer)
        writer.writerow(["ad", "=cmd|' /C calc'!A0", 3])
        writer.writerows([["+x", "-y"], ["@z", "ok"]])
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        self.assertEqual(rows, [["ad", "'=cmd|' /C calc'!A0", "3"], ["'+x", "'-y"], ["'@z", "ok"]])

    def test_openpyxl_helpers_write_strings_not_formulas(self):
        from openpyxl import Workbook

        sheet = Workbook().active
        export_safety.sheet_append(sheet, ["=1+1", 2])
        cell = export_safety.sheet_cell(sheet, row=2, column=1, value="=SUM(A1)")
        self.assertEqual(sheet["A1"].data_type, "s")
        self.assertEqual(sheet["A1"].value, "'=1+1")
        self.assertEqual(sheet["B1"].value, 2)
        self.assertEqual(cell.data_type, "s")
        # Prefikssiz nəzarət: openpyxl "=…" sətrini formula kimi yazır — məhz qorunan hal.
        sheet["C1"] = "=1+1"
        self.assertEqual(sheet["C1"].data_type, "f")

    def test_registrar_export_text_delegates(self):
        from apps.registrar.exam_score_import_safety import export_text

        self.assertEqual(export_text("=x"), "'=x")
        self.assertEqual(export_text(None), "")
        self.assertEqual(export_text(5), "5")
