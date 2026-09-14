"""The academic transfer extension fails closed and preserves service results."""

from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.organizations import student_transfer
from apps.registrar.apps import _transfer_student_group


class StudentTransferHookTests(SimpleTestCase):
    def setUp(self):
        self.args = dict(
            record=object(), new_group=object(), period=object(), by_user=object(), reason="Transfer reason"
        )

    def test_missing_provider_rejects_transfer(self):
        with patch.object(student_transfer, "_handler", None):
            with self.assertRaises(ValidationError):
                student_transfer.transfer_student_group(**self.args)

    def test_provider_receives_identity_and_returns_own_result(self):
        handler = Mock(return_value={"moved": 2})
        with patch.object(student_transfer, "_handler", None):
            student_transfer.register_student_transfer(handler)
            result = student_transfer.transfer_student_group(**self.args)
        handler.assert_called_once_with(**self.args)
        self.assertIs(result, handler.return_value)

    def test_domain_rejection_is_not_swallowed(self):
        rejection = ValidationError("Blocked by journal policy")
        with patch.object(student_transfer, "_handler", Mock(side_effect=rejection)):
            with self.assertRaises(ValidationError) as raised:
                student_transfer.transfer_student_group(**self.args)
        self.assertIs(raised.exception, rejection)

    def test_registrar_adapter_resolves_own_service_at_call_time(self):
        with patch("apps.registrar.transfer.transfer_student_group", return_value={"moved": 1}) as service:
            self.assertEqual(_transfer_student_group(**self.args), {"moved": 1})
        service.assert_called_once_with(**self.args)

    def test_non_callable_registration_is_rejected(self):
        with self.assertRaises(TypeError):
            student_transfer.register_student_transfer(None)
