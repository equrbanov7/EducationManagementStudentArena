"""Bölgünün qeydi saat/müəllim redaktəsində itməməlidir (2026-11-19).

«Yük bölgüsü» ekranının formaları (``bolgu/``) ``note`` sahəsi göndərmir — əvvəl hər redaktə mövcud qeydi boş
sətirlə əvəz edirdi (2026-11-15 auditində qeyd olunmuş səhv). İndi ``note`` açarı sorğuda YOXDURSA mövcud bölgünün
qeydi saxlanılır; açıq göndərilən (boş daxil) dəyər əvvəlki kimi yazılır; yeni bölgüdə qeyd boşdur.
"""

from __future__ import annotations

import json

from django.urls import reverse

from apps.workload.models import TeacherAssignment

from .test_subject_cards_2026_11_09 import CardsBase


class AssignKeepsNoteTests(CardsBase):
    code = "AN"

    def setUp(self):
        super().setUp()
        TeacherAssignment.objects.filter(row=self.row_i_ml).delete()
        self.client.force_login(self.head)
        self.saved = TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row_i_ml,
            teacher=self.habibov,
            activity="seminar",
            hours=37,
            note="Əmr № 14 — əvəzetmə",
        )

    def _post(self, **extra):
        payload = {
            "row_id": str(self.row_i_ml.pk),
            "assignment_id": str(self.saved.pk),
            "activity": "seminar",
            "teacher_id": str(self.habibov.pk),
            "hours": 30,
            "amend_reason": "correction",
            "amend_note": "saat düzəlişi",
            **extra,
        }
        return self.client.post(reverse("workload:assign"), data=json.dumps(payload), content_type="application/json")

    def test_edit_without_note_key_keeps_the_note(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content)
        self.saved.refresh_from_db()
        self.assertEqual((self.saved.hours, self.saved.note), (30, "Əmr № 14 — əvəzetmə"))

    def test_explicit_note_still_overwrites(self):
        self.assertEqual(self._post(note="").status_code, 200)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.note, "")
        self.assertEqual(self._post(note="yeni qeyd").status_code, 200)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.note, "yeni qeyd")

    def test_new_assignment_has_no_note(self):
        response = self.client.post(
            reverse("workload:assign"),
            data=json.dumps(
                {
                    "row_id": str(self.row_i_ml.pk),
                    "activity": "seminar",
                    "teacher_id": str(self.orucova.pk),
                    "hours": 8,
                    "amend_reason": "correction",
                    "amend_note": "əlavə müəllim",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(TeacherAssignment.objects.get(pk=response.json()["assignment_id"]).note, "")
