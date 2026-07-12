"""Tələbəyə cavab açarının açılma siyasəti.

Nəticə və apellyasiya səthləri eyni qərarı verməlidir.

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


__all__ = ["exam_answers_release_locked"]
