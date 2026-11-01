"""Live-session-only bomb rules; persisted answer ledger makes retries harmless."""

MAX_BOMB_QUESTIONS = 200


def normalize_bomb_questions(value, *, session=None):
    if not isinstance(value, list) or len(value) > MAX_BOMB_QUESTIONS:
        if session is not None:
            raise ValueError("Bomba sualları siyahısı yararsızdır.")
        return []
    try:
        if any(isinstance(item, bool) or str(int(item)) != str(item) or int(item) <= 0 for item in value):
            raise ValueError
        result = sorted(set(map(int, value)))
    except (ValueError, TypeError, OverflowError):
        if session is not None:
            raise ValueError("Bomba sualının identifikatoru yararsızdır.") from None
        return []
    if session is not None:
        previous = normalize_bomb_questions((session.host_settings or {}).get("bomb_questions", []))
        if previous != result and (session.state != session.STATE_LOBBY or session.answers.exists()):
            raise ValueError("Bomba sualları yalnız oyun başlamazdan əvvəl seçilir.")
        from django.apps import apps

        questions = list(
            apps.get_model("exams", "ExamQuestion")
            .objects.filter(exam_id=session.exam_id, pk__in=result)
            .prefetch_related("options")
        )
        if len(questions) != len(result):
            raise ValueError("Bomba sualı bu canlı oyuna aid deyil.")
        from apps.live_exam.typed_answers import typed_eligibility

        if any(
            not any(option.is_correct for option in question.options.all()) and not typed_eligibility(question)[0]
            for question in questions
        ):
            raise ValueError("Düzgün cavabı olmayan sual bomba ola bilməz.")
    return result


def bomb_score_effect(config, score, current_score):
    """Only accepted wrong answers reset this player's current live-session score.

    Missing/late/invalid submissions do not pass the normal answer pipeline;
    neutral questions never penalize. A partial answer is not fully correct.
    No official exam/attempt/result models are read or written here.
    """
    triggered = bool(config.is_bomb and not config.is_neutral and not score["is_correct"])
    reset = max(0, int(current_score or 0)) if triggered else 0
    return triggered, reset, 0 if triggered else int(score["awarded_points"])


def result_fields(answer):
    read = answer.get if isinstance(answer, dict) else lambda key, default: getattr(answer, key, default)
    return {
        "bomb_triggered": bool(read("bomb_triggered", False)),
        "score_reset_amount": int(read("score_reset_amount", 0) or 0),
    }
