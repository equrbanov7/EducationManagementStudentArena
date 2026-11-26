import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import IntegrityError, connections, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from apps.labs.models import LabBlock, LabQuestion

from .test_views import LabDetailFixtureMixin, _login_with_org


class QuestionNumberingTests(LabDetailFixtureMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.block = LabBlock.objects.create(lab=self.lab, title="Nömrələmə")
        self.create = reverse("labs:create_question", args=[self.block.pk])
        self.import_url = reverse("labs:import_questions", args=[self.block.pk])
        self._login_as(self.teacher)

    def assert_display_numbers(self, expected):
        response = self.client.get(reverse("labs:manage_blocks", args=[self.lab.pk]))
        self.assertEqual(response.status_code, 200)
        numbers = re.findall(r'<span class="lab-qno">(\d+)</span>', response.content.decode())
        self.assertEqual([int(n) for n in numbers], expected)
        self.assertEqual(list(self.block.questions.values_list("question_number", flat=True)), expected)

    def test_delete_middle_then_append_and_import(self):
        for n in range(3):
            self.assertTrue(self.client.post(self.create, {"question_text": f"Sual {n}"}).json()["success"])
        middle = self.block.questions.get(question_number=2)
        self.assertTrue(self.client.post(reverse("labs:delete_question", args=[middle.pk])).json()["success"])
        self.assertTrue(self.client.post(self.create, {"question_text": "Yeni sual"}).json()["success"])
        self.assert_display_numbers([1, 3, 4])
        self.assertEqual(self.client.post(self.import_url, {"questions_text": "1. Beş\n2. Altı"}).json()["count"], 2)
        self.assert_display_numbers([1, 3, 4, 5, 6])
        with self.assertRaises(IntegrityError), transaction.atomic():
            LabQuestion.objects.create(block=self.block, question_number=3, question_text="Təkrar")

    def test_simultaneous_single_additions_and_import(self):
        requests = [
            (self.create, {"question_text": "Tək A"}),
            (self.create, {"question_text": "Tək B"}),
            (self.import_url, {"questions_text": "1. Toplu A\n2. Toplu B"}),
        ]
        clients = [Client() for _ in requests]
        for client in clients:
            _login_with_org(client, self.teacher, self.organization)
        barrier = Barrier(len(requests))

        def post(item):
            client, (url, payload) = item
            try:
                barrier.wait(timeout=10)
                return client.post(url, payload).json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            results = list(pool.map(post, zip(clients, requests)))
        self.assertTrue(all(result["success"] for result in results), results)
        self.assert_display_numbers([1, 2, 3, 4])
        batch = list(
            self.block.questions.filter(question_text__startswith="Toplu").values_list("question_number", flat=True)
        )
        self.assertEqual(batch[1], batch[0] + 1)
