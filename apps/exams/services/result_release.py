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

Təhlükəsiz kateqoriyalar (final/midterm) üçün ayrıca qayda — ``secure_answer_key_hidden``.
"""

from datetime import timedelta

#: Final imtahan mərkəzinin təhvildən sonrakı nəticə baxışı (sonra sessiya bağlanır).
FINAL_CENTER_REVIEW_SECONDS = 5 * 60


def final_center_review_seconds_left(attempt, *, now=None) -> int:
    """Mərkəzin 5 dəqiqəlik nəticə baxışından qalan saniyə (``finished_at``-dan sayılır)."""
    from django.utils import timezone

    finished_at = getattr(attempt, "finished_at", None)
    if not finished_at:
        return FINAL_CENTER_REVIEW_SECONDS
    expires_at = finished_at + timedelta(seconds=FINAL_CENTER_REVIEW_SECONDS)
    return max(0, int((expires_at - (now or timezone.now())).total_seconds()))


def secure_answer_key_hidden(attempt, *, is_profile_results, now=None) -> bool:
    """Final/midterm cəhdinin CAVAB AÇARI (düzgün variant, yazılı «ideal cavab») tələbəyə gizlidirmi.

    Qərar SERVERDƏ, imtahan kateqoriyasından verilir — tələbənin idarə etdiyi
    ``from_section`` / ``return_to`` yalnız final-in kabinet rejimini seçir:

    * midterm (və digər təhlükəsiz kateqoriyalar) — HƏR halda gizli (2026-10-05);
    * final, kabinet rejimi — gizli;
    * final, mərkəz rejimi — yalnız təhvildən sonrakı 5 dəqiqəlik baxışda görünür
      (qəbul edilmiş dizayn; nəticə səhifəsi sonra sessiyanı bağlayır, apellyasiya
      səhifəsində isə bu vaxt sərhədi elə buradan tətbiq olunur — təhlükəsizlik
      auditi 2026-10-07: apellyasiya URL-i 3 günlük pəncərə boyu açarı açırdı);
    * müəllimin sınaq cəhdi (``is_trial``) mərkəz axınına aid deyil — vaxtla kəsilmir.
    """
    from apps.exams.services.access_policy import SECURE_EXAM_CATEGORIES

    category = getattr(attempt.exam, "exam_type_extended", "") or ""
    if category not in SECURE_EXAM_CATEGORIES:
        return False
    if category == "final" and not is_profile_results:
        if getattr(attempt, "is_trial", False):
            return False
        return final_center_review_seconds_left(attempt, now=now) <= 0
    return True


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


__all__ = [
    "FINAL_CENTER_REVIEW_SECONDS",
    "attempt_answer_key_hidden",
    "exam_answers_release_locked",
    "final_center_review_seconds_left",
    "secure_answer_key_hidden",
]
