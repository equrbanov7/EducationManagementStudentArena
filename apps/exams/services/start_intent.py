"""İmtahan başlatma niyyəti tokeni — kənar linklə vaxtlı cəhdin başladılmasının qarşısı (EXAMQA R1, 2026-10-01).

Əvvəl ``GET /exams/<slug>/start/`` yeni cəhdi DƏRHAL yaradırdı: tələbəyə göndərilən zərərli link
(çat, e-poçt, başqa sayt) onun vaxtlı cəhdini başladıb bir haqqını yeyə bilərdi. İndi yeni cəhd yalnız:

* ``POST`` (CSRF qorunur) — təsdiq səhifəsinin «İmtahana başla» düyməsi; və ya
* ``GET`` + etibarlı ``si`` tokeni — platformanın öz «Başla» düymələrinin linkinə əlavə olunur
  (istifadəçi + imtahan üçün imzalı, ``_MAX_AGE`` ömürlü; kənar şəxs onu əldə edə bilmir).

Tokensiz GET cəhd yaratmır — təsdiq səhifəsi göstərilir. Davam edən cəhdə qayıtmaq (resume) isə
tokensiz də işləyir (yan təsiri yoxdur).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core import signing
from django.urls import reverse

START_INTENT_PARAM = "si"
_SALT = "exams.start_intent.v1"
_MAX_AGE = 6 * 60 * 60  # açıq qalmış siyahı səhifəsi üçün kifayət; köhnəlibsə təsdiq səhifəsi çıxır


def start_intent_token(user_id, exam_id) -> str:
    return signing.dumps([int(user_id), int(exam_id)], salt=_SALT)


def has_valid_start_intent(request, exam) -> bool:
    token = (request.GET.get(START_INTENT_PARAM) or "").strip()
    user_id = getattr(request.user, "pk", None)
    if not token or user_id is None:
        return False
    try:
        payload = signing.loads(token, salt=_SALT, max_age=_MAX_AGE)
    except signing.BadSignature:
        return False
    return payload == [int(user_id), int(exam.pk)]


def exam_start_url(exam, user, **params) -> str:
    """``exams:start_exam`` + niyyət tokeni (+ əlavə query parametrləri)."""
    query = {k: v for k, v in params.items() if v not in (None, "")}
    if getattr(user, "pk", None) is not None:
        query[START_INTENT_PARAM] = start_intent_token(user.pk, exam.pk)
    url = reverse("exams:start_exam", kwargs={"slug": exam.slug})
    return f"{url}?{urlencode(query)}" if query else url


__all__ = ["START_INTENT_PARAM", "exam_start_url", "has_valid_start_intent", "start_intent_token"]
