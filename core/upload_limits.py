"""Sorğu-səviyyəli ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (təhlükəsizlik auditi 2026-10-05).

Django FAYL olmayan form sahələrini (multipart mətn sahələri, urlencoded/JSON gövdə)
yaddaşa oxuyur və ``settings.DATA_UPLOAD_MAX_MEMORY_SIZE`` ilə yoxlayır; fayl
yükləmələri diskə axır və bu limitə DÜŞMÜR. Qlobal limit 5 MB-dır.

Yeganə legit böyük mətn gövdəsi yazılı imtahanın tam təhvilidir (``exams:take_exam``
POST): rəsm cavabları base64 MƏTN sahəsi kimi gedir (``paint_data_<qid>``, hər biri
≤ ``EXAM_PAINT_MAX_BASE64_CHARS``). Django limiti hər view üçün ayrıca vermir və
``override_settings`` proses-qlobaldır (ASGI thread-lərində təhlükəli), ona görə:

* ``RequestScopedLimit`` — ``int`` alt sinfi; müqayisə/toplama/çıxma əməliyyatlarında
  cari sorğunun ``ContextVar`` dəyərini (varsa) işlədir, əks halda öz (qlobal) dəyərini.
  Django-nun yoxlamaları (``length > LIMIT``, ``LIMIT - n``, ``LIMIT + 1``) bu
  operatorlardan keçir (sağ operand alt sinif olduğu üçün əks metod üstündür).
* ``ExamAnswerUploadLimitMiddleware`` — yalnız ``exams:take_exam`` POST-u üçün
  ``ContextVar``-ı ``DATA_UPLOAD_MAX_MEMORY_SIZE_EXAM``-a qaldırır; zəncirdə POST-u
  oxuyan hər şeydən (CSRF) ƏVVƏL durur və sorğu bitəndə dəyəri sıfırlayır.
"""

from __future__ import annotations

import contextvars

_REQUEST_LIMIT: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "ems_data_upload_max_memory_size", default=None
)

#: Böyük gövdəyə icazəli marşrutlar (``namespace:name``).
LARGE_BODY_ROUTES = frozenset({"exams:take_exam"})


class RequestScopedLimit(int):
    """Qlobal dəyəri olan, cari sorğu üçün ``ContextVar`` ilə qaldırıla bilən limit."""

    def effective(self) -> int:
        override = _REQUEST_LIMIT.get()
        return int.__int__(self) if override is None else override

    def __int__(self):
        return self.effective()

    __index__ = __int__

    def __add__(self, other):
        return self.effective() + other

    __radd__ = __add__

    def __sub__(self, other):
        return self.effective() - other

    def __rsub__(self, other):
        return other - self.effective()

    def __lt__(self, other):
        return self.effective() < other

    def __le__(self, other):
        return self.effective() <= other

    def __gt__(self, other):
        return self.effective() > other

    def __ge__(self, other):
        return self.effective() >= other

    def __eq__(self, other):
        return self.effective() == other

    def __ne__(self, other):
        return self.effective() != other

    def __hash__(self):
        return int.__hash__(self)

    def __repr__(self):
        return f"RequestScopedLimit({int.__int__(self)})"


def _wants_large_body(request) -> bool:
    # Gec idxal: modul settings yüklənərkən (``components/exam.py``) idxal olunur.
    from django.urls import Resolver404, resolve

    if request.method != "POST":
        return False
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return False
    return match.view_name in LARGE_BODY_ROUTES


class ExamAnswerUploadLimitMiddleware:
    """İmtahan cavabı POST-u üçün böyük mətn gövdəsi limiti; qalan hər şey qlobal 5 MB."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        if not _wants_large_body(request):
            return self.get_response(request)
        token = _REQUEST_LIMIT.set(int(getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE_EXAM", 0)) or None)
        try:
            return self.get_response(request)
        finally:
            _REQUEST_LIMIT.reset(token)
