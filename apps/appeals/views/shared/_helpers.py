"""Appeals — rollar-arası helper-lər (F4 rol-skeleti, 2026-07-02)."""


def _marked_question_map(attempt):
    marked_ids = {}
    for raw_question_id in getattr(attempt, "marked_question_ids", None) or []:
        try:
            marked_ids[int(raw_question_id)] = True
        except (TypeError, ValueError):
            continue
    return marked_ids
