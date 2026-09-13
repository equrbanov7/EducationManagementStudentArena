"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: `create_question`
(sual + `visible_users` M2M) ``transaction.atomic`` içindədir."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.blog.models import Question

User = get_user_model()


class CreateQuestionAtomicTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_superuser("w2bq_teacher", "w2bq_teacher@example.com", "pw")
        self.viewer = User.objects.create_user("w2bq_viewer", "w2bq_viewer@example.com", "pw")
        self.client.force_login(self.teacher)

    def _post(self):
        return self.client.post(
            reverse("create_question"),
            {"question_text": "Dalğa 2 sualı?", "answer_text": "Cavab", "visible_users": [str(self.viewer.pk)]},
        )

    def test_m2m_failure_rolls_back_the_question(self):
        # `save_m2m` instansiya atributudur; M2M yazısı `through` cədvəlinə `bulk_create` ilə gedir.
        with mock.patch("django.db.models.query.QuerySet.bulk_create", side_effect=RuntimeError("m2m boom")):
            with self.assertRaises(RuntimeError):
                self._post()
        self.assertFalse(Question.objects.filter(author=self.teacher).exists())

    def test_happy_path_writes_question_and_m2m(self):
        self.assertEqual(self._post().status_code, 302)
        question = Question.objects.get(author=self.teacher)
        self.assertEqual(list(question.visible_users.values_list("pk", flat=True)), [self.viewer.pk])
