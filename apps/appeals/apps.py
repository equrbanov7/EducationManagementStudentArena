from django.apps import AppConfig


class AppealsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.appeals"

    def ready(self):
        # M2 (2026-07-02): exams-ın score-adjustment genişlənmə nöqtəsinə
        # apellyasiya implementasiyalarını qoş (dependency inversion —
        # exams artıq appeals-i import etmir; bax apps/exams/score_adjustments.py).
        from apps.exams import score_adjustments

        from .services import (
            appeal_bonus_map,
            appeal_score_state,
            apply_bonus_to_test_result,
            can_create_appeal,
            effective_test_score,
            remaining_window_seconds,
        )

        score_adjustments.register("bonus_map", appeal_bonus_map)
        score_adjustments.register("apply_bonus", apply_bonus_to_test_result)
        score_adjustments.register("effective_test_score", effective_test_score)
        score_adjustments.register("score_state", appeal_score_state)
        score_adjustments.register("can_create", can_create_appeal)
        score_adjustments.register("remaining_window_seconds", remaining_window_seconds)
