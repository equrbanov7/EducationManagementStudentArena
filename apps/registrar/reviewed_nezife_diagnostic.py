"""Closed value-free refusal codes for the single reviewed Nəzifə label case."""

SAFE_GUARDS = frozenset(
    (
        "nezife_academic_graph_changed",
        "nezife_actor_scope",
        "nezife_actor_tenant",
        "nezife_course_changed",
        "nezife_exact_receipt",
        "nezife_exact_undo_failed",
        "nezife_exact_write_count",
        "nezife_explicit_mode",
        "nezife_fresh_baseline",
        "nezife_lesson_changed",
        "nezife_mark_inventory_changed",
        "nezife_prior_receipt_review",
        "nezife_room_changed",
        "nezife_schedule_changed",
        "nezife_scope_changed",
        "nezife_teacher_changed",
        "nezife_undo_changed",
        "nezife_unreceipted_clear",
    )
)


def native_failure(exc):
    """Only existing literal ValueError guards may leave the native process."""
    if type(exc) is ValueError and len(exc.args) == 1 and isinstance(exc.args[0], str):
        if exc.args[0] in SAFE_GUARDS:
            return exc.args[0]
    return "nezife_label_refused"
