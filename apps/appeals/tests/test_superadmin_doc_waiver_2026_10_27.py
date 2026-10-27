"""Apellyasiya qərarı — «əsaslandırıcı sənəd məcburidir» tənzimləməsi superadmini saxlamır (sahib 2026-10-27).

``exam.appeal_document_required`` yandırılıbsa adi qərarverici sənədsiz qərar yaza bilmir (dəyişməyib); superadmin
sənədsiz keçir və modalda sənəd sahəsi məcburi göstərilmir.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from apps.appeals.views.teacher import _review_decision as decision

User = get_user_model()


class AppealDecisionDocumentWaiverTest(TestCase):
    def _request(self, user):
        request = RequestFactory().post("/", {decision.TEACHER_FIELD: "1"})
        request.user = user
        return request

    def _parse(self, user):
        teacher = SimpleNamespace(pk=1)
        with (
            mock.patch.object(decision, "resolve_decision_teacher", return_value=teacher),
            mock.patch("apps.appeals.services.documents.document_required", return_value=True),
        ):
            return decision.parse_decision_extras(self._request(user), appeal=None)

    def test_superadmin_decides_without_document(self):
        admin = User.objects.create_user("apw_admin", "apw_admin@qku.edu.az", "pw", is_superuser=True)
        teacher, document = self._parse(admin)
        self.assertEqual(teacher.pk, 1)
        self.assertIsNone(document)

    def test_regular_decider_still_needs_the_document(self):
        plain = User.objects.create_user("apw_plain", "apw_plain@qku.edu.az", "pw")
        with self.assertRaises(ValidationError):
            self._parse(plain)
