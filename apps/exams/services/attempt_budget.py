"""Cəhd limiti büdcəsi — bir səhifəlik tələbə dəsti üçün TOPLU hesab.

``Exam.attempts_left_for(user)`` hər çağırışda 3 sorğu edir (köhnəlmiş cəhd
yoxlaması, bitmiş cəhd COUNT-u, fərdi qrant). Müəllim nəticələri cədvəli onu
sətir-sətir çağırırdı — 12 cəhdlik səhifədə ~36 əlavə sorğu (audit P1-9,
2026-09-12). Bu modul eyni məntiqi səhifədəki bütün tələbələr üçün 3 sabit
sorğuya yığır. Filtrlər modeldəki ilə BİRƏBİR eynidir; parity testi
``apps/exams/tests/test_results_attempt_budget.py``-dədir.

Model faylı (``apps/exams/domain/exam_definition.py``) toxunulmaz qalır —
tək-tələbə yolu (imtahana giriş qapısı) orada işləməyə davam edir.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Count

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES

# ``ExamAccessPolicyMixin._expire_stale_attempts_for`` ilə eyni «hələ açıq» statuslar.
_OPEN_STATUSES = ("draft", "in_progress")


def attempts_left_map(exam, user_ids: Iterable[int | None]) -> dict[int, int | None]:
    """``{user_id: qalan cəhd}`` — hər dəyər ``exam.attempts_left_for(user)`` ilə eynidir.

    Limitsiz imtahanda (``max_attempts_per_user`` boş) model metodu kimi ``None``
    qaytarır və heç bir sorğu etmir. Təkrarlanan/boş id-lər süzülür.
    """
    ordered_ids = list(dict.fromkeys(uid for uid in user_ids if uid))
    if not exam.max_attempts_per_user or not ordered_ids:
        return {uid: None for uid in ordered_ids}

    # 1) Köhnəlmiş (vaxt limiti keçmiş) draft/in_progress cəhdləri bağla —
    #    ``_expire_stale_attempts_for``-un toplu ekvivalenti: tək SELECT, yalnız
    #    həqiqətən vaxtı keçənlərə yazı. ``exam.attempts`` üzərindən gedirik ki,
    #    ``attempt.exam`` əvvəlcədən dolu olsun (deadline hesabı əlavə sorğu etməsin).
    stale = exam.attempts.filter(user_id__in=ordered_ids, status__in=_OPEN_STATUSES).order_by("-started_at")
    for attempt in stale:
        attempt.expire_if_time_limit_reached()

    # 2) İstifadə olunmuş cəhdlər — modeldəki filtr: bitmiş statuslar, sınaq xaric.
    #    ``order_by()`` model Meta sırasını (-started_at) GROUP BY-a qarışdırmamaq üçündür.
    used_rows = (
        exam.attempts.filter(user_id__in=ordered_ids, status__in=ATTEMPT_FINISHED_STATUSES)
        .exclude(is_trial=True)
        .order_by()
        .values("user_id")
        .annotate(used=Count("id"))
    )
    used_by_user = {row["user_id"]: row["used"] for row in used_rows}

    # 3) Fərdi əlavə cəhd qrantları — (exam, student) unikaldır, tələbə başına ən çox bir sətir.
    extra_by_user = dict(
        exam.attempt_grants.filter(student_id__in=ordered_ids).values_list("student_id", "extra_attempts")
    )

    limit = exam.max_attempts_per_user
    return {uid: max(limit + (extra_by_user.get(uid) or 0) - used_by_user.get(uid, 0), 0) for uid in ordered_ids}
