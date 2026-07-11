"""Tələbəyə cavab açarının açılma siyasəti.

Nəticə və apellyasiya səthləri eyni qərarı verməlidir; əks halda
imtahanı erkən bitirən tələbə alternativ URL-dən düzgün cavabı
görə bilər.
"""


def exam_answers_release_locked(exam) -> bool:
    """Planlaşdırılmış imtahan bitənədək correctness-i gizlət.

    ``end_datetime`` olmayan məşq/legacy imtahanlarında əvvəlki davranış
    qorunur. Vaxtlı imtahanlarda isə bütün tələbələrin pəncərəsi
    bağlanmayana qədər variant düzgünlüyü, ideal cavab və per-sual
    verdikt açılmır.
    """
    if not getattr(exam, "end_datetime", None):
        return False
    return not exam.is_after_end()


__all__ = ["exam_answers_release_locked"]
