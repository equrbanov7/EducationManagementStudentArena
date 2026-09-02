"""P0-1 reqressiya: jurnal/düzəliş/sübut media prefiksləri QORUNUR.

2026-09-02 auditi (``docs/audits/2026-09-02/PHASE23_SECURITY.md``) autentifikasiyasız
``curl`` ilə ``/media/journal_lesson_corrections/<org>/doc.pdf`` üçün **200 + əsl PDF**
aldı.  Yalnız ``journal_corrections/`` qorunurdu; qalan altı prefiks (dərs/sərbəst
iş/kurs işi/komponent düzəlişləri, imtahan bal sübutu, köhnə üzrlü qayıb aktları)
statik media kimi verilirdi — 2 087 tibbi arayış və düzəliş sənədi.

Bu modul hər prefiks üçün dörd halı bağlayır:
  anonim → 302 login · yad istifadəçi → 404 · aid tələbə → 200 · müəllim → 200.
"""

from __future__ import annotations

import datetime
import os
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, override_settings

from apps.organizations.models import Membership
from apps.registrar.models import (
    AssessmentComponent,
    AttendanceStatus,
    ComponentScoreCorrection,
    CorrectionField,
    CorrectionReason,
    CourseWorkCorrection,
    ExamScoreEntry,
    JournalCorrection,
    LegacyExcuseDocument,
    LessonCorrection,
    LessonKind,
    SelfWorkCorrection,
    SelfWorkTopic,
)
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from core.media_views import _is_private, protected_media
from core.rls import bypass_rls

User = get_user_model()


def _activate_media_root(test_case, media_root: str) -> None:
    """MEDIA ayarlarını bir dəfə aktivləşdir (hər sorğuda deyil).

    ``override_settings``-in dəfələrlə enter/exit edilməsi test bazasının
    bağlantısını qopardır (``InterfaceError: connection already closed``).
    """
    override = override_settings(
        MEDIA_ROOT=media_root,
        MEDIA_URL="/media/",
        SERVE_MEDIA=True,
        DEBUG=False,
        MEDIA_ACCEL_REDIRECT_URL="",
        OBJECT_STORAGE_ENABLED=False,
    )
    override.enable()
    test_case.addCleanup(override.disable)


class PrivateCorrectionMediaTests(_BaseJournalSetup):
    """Hər sənəd prefiksi üçün: anonim / yad / sahib / müəllim / nəzarətçi."""

    def setUp(self):
        super().setUp()
        self.media_tmp = tempfile.mkdtemp()
        self.factory = RequestFactory()
        _activate_media_root(self, self.media_tmp)
        with bypass_rls():
            self.outsider = User.objects.create_user("cx_outsider", "cx_out@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.outsider,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_active=True,
            )
            self.lesson, self.mark = self._absent_lesson(7)
            self.topic = SelfWorkTopic.objects.create(organization=self.org, offering=self.offering, title="SI-1")
            self.component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Kollokvium 1", max_score=10
            )

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def _write(self, relative_path: str) -> str:
        """Fayl sistemində real fayl yaradır ki, 200 halı gerçək olsun."""
        absolute = os.path.join(self.media_tmp, relative_path)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "wb") as handle:
            handle.write(b"%PDF-1.4\n%%EOF\n")
        return relative_path

    def _get(self, path: str, user):
        request = self.factory.get(f"/media/{path}")
        request.user = user
        return protected_media(request, path=path)

    def _assert_matrix(self, path: str, *, allowed, denied):
        self.assertTrue(_is_private(path), f"{path} private prefiks siyahısında deyil")

        # Anonim → login-ə yönləndirmə (əvvəllər: 200 + PDF baytları).
        anonymous = self._get(path, AnonymousUser())
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("login", anonymous["Location"].lower())

        for user in denied:
            # 403 deyil 404 — icazəsiz aktora faylın mövcudluğu da bildirilmir.
            with self.assertRaises(Http404, msg=f"{path} {user.username} üçün açıq qaldı"):
                self._get(path, user)

        for user in allowed:
            response = self._get(path, user)
            self.assertEqual(response.status_code, 200, f"{path} {user.username} üçün bağlandı")
            # DİQQƏT: ``response.close()`` ÇAĞIRMA — ``HttpResponseBase.close()``
            # ``request_finished`` siqnalını atır, o da ``close_old_connections``
            # vasitəsilə TestCase-in tranzaksiyalı bağlantısını qoparır.
            stream = getattr(response, "file_to_stream", None)
            if stream is not None:
                stream.close()

    # ── prefikslər ──────────────────────────────────────────────────────────
    def test_journal_correction_document_is_guarded(self):
        path = self._write(f"journal_corrections/{self.org.id}/doc.pdf")
        with bypass_rls():
            JournalCorrection.objects.create(
                organization=self.org,
                lesson_mark=self.mark,
                lesson_mark_ref=self.mark.pk,
                lesson_ref=self.lesson.pk,
                enrollment_ref=self.enrollment.pk,
                field=CorrectionField.ATTENDANCE,
                old_status=AttendanceStatus.ABSENT,
                new_status=AttendanceStatus.EXCUSED,
                reason=CorrectionReason.MEDICAL,
                note="arayış",
                document=path,
                corrected_by=self.admin,
            )
        self._assert_matrix(path, allowed=[self.student, self.teacher, self.owner], denied=[self.outsider])

    def test_lesson_correction_document_is_guarded(self):
        path = self._write(f"journal_lesson_corrections/{self.org.id}/doc.pdf")
        with bypass_rls():
            LessonCorrection.objects.create(
                organization=self.org,
                lesson=self.lesson,
                reason=CorrectionReason.TECHNICAL,
                note="tarix düzəlişi",
                document=path,
                corrected_by=self.admin,
            )
        # Dərs sətri qrupa aiddir → həmin açılışın tələbəsi görür, yad tələbə yox.
        self._assert_matrix(path, allowed=[self.student, self.teacher, self.owner], denied=[self.outsider])

    def test_selfwork_correction_document_is_guarded(self):
        path = self._write(f"journal_selfwork_corrections/{self.org.id}/doc.pdf")
        with bypass_rls():
            SelfWorkCorrection.objects.create(
                organization=self.org,
                topic=self.topic,
                enrollment=self.enrollment,
                old_done=False,
                new_done=True,
                reason=CorrectionReason.OFFICIAL,
                note="təhvil düzəlişi",
                document=path,
                corrected_by=self.admin,
            )
        self._assert_matrix(path, allowed=[self.student, self.teacher, self.owner], denied=[self.outsider])

    def test_coursework_correction_document_is_guarded(self):
        path = self._write(f"journal_coursework_corrections/{self.org.id}/doc.pdf")
        with bypass_rls():
            CourseWorkCorrection.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                old_score=Decimal("10.00"),
                new_score=Decimal("20.00"),
                reason=CorrectionReason.APPEAL,
                note="kurs işi düzəlişi",
                document=path,
                corrected_by=self.admin,
            )
        self._assert_matrix(path, allowed=[self.student, self.teacher, self.owner], denied=[self.outsider])

    def test_component_correction_document_is_guarded(self):
        path = self._write(f"journal_component_corrections/{self.org.id}/doc.pdf")
        with bypass_rls():
            ComponentScoreCorrection.objects.create(
                organization=self.org,
                component=self.component,
                enrollment=self.enrollment,
                old_score=Decimal("5.00"),
                new_score=Decimal("8.00"),
                reason=CorrectionReason.TECHNICAL,
                note="kollokvium balı",
                document=path,
                corrected_by=self.admin,
            )
        self._assert_matrix(path, allowed=[self.student, self.teacher, self.owner], denied=[self.outsider])

    def test_exam_score_evidence_is_guarded(self):
        path = self._write(f"exam_score_entries/{self.org.id}/sheet.pdf")
        with bypass_rls():
            ExamScoreEntry.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                old_score=None,
                new_score=Decimal("42.00"),
                note="kağız imtahan",
                evidence=path,
                entered_by=self.teacher,
            )
        self._assert_matrix(path, allowed=[self.student, self.teacher, self.owner], denied=[self.outsider])

    def test_legacy_excuse_document_is_guarded(self):
        path = self._write(f"legacy_excuse_documents/{self.org.id}/1697461819.pdf")
        with bypass_rls():
            LegacyExcuseDocument.objects.create(
                organization=self.org,
                student=self.student,
                source_system="myedu",
                source_table="allowed_qb",
                source_pk=1,
                source_snapshot_sha256="a" * 64,
                source_row_hash="b" * 64,
                materialization_digest="c" * 64,
                transform_version="v1",
                mapping_status="linked",
                starts_on=datetime.date(2024, 10, 1),
                ends_on=datetime.date(2024, 10, 5),
                document_name="1697461819.pdf",
                document=path,
            )
        # Açılış/fənn yoxdur → müəllim əhatəsi hesablanmır; yalnız tələbə + nəzarətçi.
        self._assert_matrix(path, allowed=[self.student, self.owner], denied=[self.outsider, self.teacher])


class ApplicationAttachmentMediaTests(_BaseJournalSetup):
    """Müraciət qoşmaları da MEDIA altında statik verilirdi."""

    def setUp(self):
        super().setUp()
        self.media_tmp = tempfile.mkdtemp()
        self.factory = RequestFactory()
        _activate_media_root(self, self.media_tmp)

    def _get(self, path: str, user):
        request = self.factory.get(f"/media/{path}")
        request.user = user
        return protected_media(request, path=path)

    def test_attachment_prefix_is_private_and_fails_closed(self):
        path = f"applications/{self.org.id}/00000000-0000-0000-0000-000000000000/x.pdf"
        absolute = os.path.join(self.media_tmp, path)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "wb") as handle:
            handle.write(b"%PDF-1.4\n%%EOF\n")

        self.assertTrue(_is_private(path))
        anonymous = self._get(path, AnonymousUser())
        self.assertEqual(anonymous.status_code, 302)
        # Qoşma sətri yoxdur → fail-closed (mövcud fayl belə verilmir).
        with self.assertRaises(Http404):
            self._get(path, self.student)


class LessonKindImportGuard(_BaseJournalSetup):
    """``LessonKind`` idxalının istifadə olunduğunu təsdiqləyən sanity."""

    def test_lesson_kind_available(self):
        self.assertTrue(hasattr(LessonKind, "LECTURE"))
