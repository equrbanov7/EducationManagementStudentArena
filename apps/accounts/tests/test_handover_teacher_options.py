"""Təhvil menyusu sıralamanın sonundakı uyğun müəllimləri də göstərir."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.views.profile._sections import handover_ui


class HandoverTeacherOptionsTests(SimpleTestCase):
    def test_eligible_teacher_after_filter_cap_remains_selectable(self):
        organization = object()
        rows = [(index, "Ad", f"Soyad {index:04}", f"teacher{index}") for index in range(1, 301)]
        rows.append((8446, "Gülnar", "Əlizadə", "gulnar.elizade"))
        with patch.object(handover_ui.handover_read, "target_queryset") as targets:
            targets.return_value.values_list.return_value = rows
            options = handover_ui.target_teacher_options(organization, blank_label="Seçin")

        targets.assert_called_once_with(organization)
        self.assertEqual(options[0], {"value": "", "label": "Seçin"})
        self.assertIn({"value": "8446", "label": "Gülnar Əlizadə"}, options)
