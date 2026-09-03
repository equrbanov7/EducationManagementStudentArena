"""Düzəliş endpoint-inin xəta mətni İSTİFADƏÇİ-ÜZLÜDÜR, `str(exc)` deyil.

CodeQL `py/stack-trace-exposure` (2026-09-02 PR audit): `correction_save` /
`correction_delete` `ValidationError`-u `str(exc)` ilə klientə qaytara bilirdi —
o forma daxili quruluşu (siyahı/dict, sahə adları) sızdırır. İndi yalnız
`exc.messages` göstərilir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.registrar.correction_views import _user_facing_validation_message


class CorrectionErrorPayloadTests(SimpleTestCase):
    def test_plain_message_is_kept_verbatim(self):
        exc = ValidationError("Səbəb göstərilməlidir.")
        self.assertEqual(_user_facing_validation_message(exc), "Səbəb göstərilməlidir.")

    def test_field_errors_do_not_leak_dict_or_field_names_structure(self):
        exc = ValidationError({"document": ["Sənəd tələb olunur."]})
        message = _user_facing_validation_message(exc)
        self.assertEqual(message, "Sənəd tələb olunur.")
        # `str(exc)` bu halda "{'document': ['...']}" verərdi.
        self.assertNotIn("{", message)
        self.assertNotIn("document", message)

    def test_multiple_messages_are_joined(self):
        exc = ValidationError(["Birinci.", "İkinci."])
        self.assertEqual(_user_facing_validation_message(exc), "Birinci.; İkinci.")
