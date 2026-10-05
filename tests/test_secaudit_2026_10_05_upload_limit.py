"""Təhlükəsizlik auditi 2026-10-05 — qlobal ``DATA_UPLOAD_MAX_MEMORY_SIZE`` 50 MB → 5 MB.

Django FAYL olmayan form sahələrini (və JSON/urlencoded gövdəni) yaddaşa oxuyur və
bu limitlə yoxlayır; fayl yükləmələri diskə axır və SAYILMIR. 50 MB qlobal limit hər
anonim POST-un (login, sorğu, axtarış) 50 MB-a qədər yaddaş tutmasına imkan verirdi.
Yeganə legit böyük mətn gövdəsi yazılı imtahanın tam təhvilidir: rəsm cavabları
base64 MƏTN sahəsi kimi (``paint_data_<qid>``, hər biri ≤ 1.5M simvol) gedir — yalnız
``exams:take_exam`` POST-u üçün limit ``DATA_UPLOAD_MAX_MEMORY_SIZE_EXAM`` qalır.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.upload_limits import ExamAnswerUploadLimitMiddleware

MB = 1024 * 1024


def _big_post(path, size):
    return RequestFactory().post(path, {"paint_data_1": "A" * size, "q_1": "cavab"})


def _read_post(request):
    return HttpResponse(str(len(request.POST["paint_data_1"])))


class UploadLimitTest(TestCase):
    def test_global_limit_is_five_megabytes(self):
        self.assertEqual(int(settings.DATA_UPLOAD_MAX_MEMORY_SIZE), 5 * MB)
        self.assertGreaterEqual(int(settings.DATA_UPLOAD_MAX_MEMORY_SIZE_EXAM), 50 * MB)

    def test_ordinary_post_over_limit_is_rejected(self):
        request = _big_post("/accounts/login/", 6 * MB)
        middleware = ExamAnswerUploadLimitMiddleware(_read_post)
        with self.assertRaises(RequestDataTooBig):
            middleware(request)

    def test_exam_answer_post_keeps_the_large_limit(self):
        path = reverse("exams:take_exam", kwargs={"slug": "imtahan", "attempt_id": 7})
        response = ExamAnswerUploadLimitMiddleware(_read_post)(_big_post(path, 6 * MB))
        self.assertEqual(response.content, str(6 * MB).encode())

    def test_exam_limit_does_not_leak_to_the_next_request(self):
        path = reverse("exams:take_exam", kwargs={"slug": "imtahan", "attempt_id": 7})
        middleware = ExamAnswerUploadLimitMiddleware(_read_post)
        middleware(_big_post(path, 6 * MB))
        with self.assertRaises(RequestDataTooBig):
            middleware(_big_post("/sorgu/", 6 * MB))

    def test_middleware_runs_before_anything_reads_post(self):
        chain = list(settings.MIDDLEWARE)
        index = chain.index("core.upload_limits.ExamAnswerUploadLimitMiddleware")
        self.assertLess(index, chain.index("django.middleware.csrf.CsrfViewMiddleware"))
        self.assertLess(index, chain.index("core.middleware_concurrency.ConcurrencyLimitMiddleware"))
