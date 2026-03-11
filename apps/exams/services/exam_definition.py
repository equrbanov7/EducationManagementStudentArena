def effective_random_question_count(exam) -> int:
    """
    0 -> hamısı
    1 -> 1
    10 -> 10
    boş/None -> 10 (default)
    """
    total = exam.questions.filter(is_active=True).count()

    val = getattr(exam, "random_question_count", None)
    if val is None:
        return min(10, total)

    try:
        val = int(val)
    except (TypeError, ValueError):
        return min(10, total)

    if val <= 0:
        return total

    return min(val, total)


__all__ = [
    "effective_random_question_count",
]
