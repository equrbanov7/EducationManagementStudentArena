"""Tələbəyə cavab açarının açılma siyasəti.

Nəticə və apellyasiya səthləri eyni qərarı verməlidir. Audit 2026-09-28 EX28-03:
çox-cəhdli imtahanda açar cəhd haqqı qurtarana (və ya ``end_datetime``-a) qədər
gizlənir — bax ``attempt_answer_key_hidden``.

MƏHSUL QƏRARI (2026-07-13, platforma sahibi): tələbə imtahanı təhvil verən
KİMİ öz nəticəsini və cavab analizini dərhal görməlidir — pəncərə
bağlanmasını gözləmək tələb olunmur. Nəticə səhifəsi onsuz da yalnız təhvil
verilmiş cəhdin sahibinə açılır; zal (final) rejimində isə giriş nəzarətli
və eyni vaxtlı olduğu üçün erkən-bitirmə sızma riski qəbul edilib.

Əvvəlki davranış (EXAM-P0-05: end_datetime keçənədək kilid) bilərəkdən
geri alınıb; funksiya imzası sabit qalır ki, bütün çağıranlar (results,
appeals) eyni qərarı bölüşsün.
"""


def exam_answers_release_locked(exam) -> bool:
    """Cavab açarı kilidlidirmi — hazırkı siyasətdə HEÇ VAXT.

    Tələbə öz təhvil verdiyi cəhdin nəticəsini dərhal görür.
    """
    return False


def attempt_answer_key_hidden(attempt, *, user=None, now=None) -> bool:
    """Bu cəhdin nəticə səhifəsində CAVAB AÇARI (düzgün variant, ideal cavab) gizlidirmi.

    Audit 2026-09-28 EX28-03 (sahib siyasəti): çox-cəhdli imtahanda (limitsiz,
    ``max_attempts_per_user > 1`` və ya «ikinci şans» qrantı) N-ci cəhdin açarı
    dərhal göstərilirdi → tələbə bir cəhdi «qurban verib» N+1-də tam bal alırdı.
    İndi tələbənin hələ cəhd haqqı varsa (``attempts_left_for(user) != 0`` —
    qrantlar daxil, limitsiz = ``None``) açar gizlənir; verdikt və bal QALIR.
    Açar son icazəli cəhddən sonra və ya imtahanın ``end_datetime``-ı keçəndə açılır.
    Müəllimin sınaq cəhdi (``is_trial``) istisnadır."""
    from django.utils import timezone

    if getattr(attempt, "is_trial", False):
        return False
    exam = attempt.exam
    end = getattr(exam, "end_datetime", None)
    if end and (now or timezone.now()) > end:
        return False
    return exam.attempts_left_for(user or attempt.user) != 0


__all__ = ["attempt_answer_key_hidden", "exam_answers_release_locked"]
