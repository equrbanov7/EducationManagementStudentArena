from django.apps import AppConfig


class AppealsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.appeals"

    def attempt_history_provider(self):
        """Registrar cəhd tarixçəsinin provayderi (Audit 2026-09-28 EXA-03).

        ``apps.registrar.exam_attempt_history`` bunu app registry üzərindən
        (``django_apps.get_app_config("appeals")``) çağırır — registrar → appeals
        STATİK importu yoxdur (dövri modul asılılığı yaranmasın). Qaytarır:
        ``attempt_percents(attempts)`` və ``appeal_rows_by_attempt(attempt_ids)``
        funksiyaları olan modul."""
        from .services import history

        return history

    def ready(self):
        # M2 (2026-07-02): exams-ın score-adjustment genişlənmə nöqtəsinə
        # apellyasiya implementasiyalarını qoş (dependency inversion —
        # exams artıq appeals-i import etmir; bax apps/exams/score_adjustments.py).
        from apps.exams.public import score_adjustments

        from .services import (
            appeal_applicable,
            appeal_bonus_map,
            appeal_score_state,
            apply_bonus_to_test_result,
            can_create_appeal,
            effective_test_score,
            remaining_window_seconds,
            student_visible_appeal_bonus_map,
            student_visible_appeal_score_state,
            student_visible_appeal_status_by_qid,
            student_visible_effective_test_score,
        )

        score_adjustments.register("bonus_map", appeal_bonus_map)
        score_adjustments.register("apply_bonus", apply_bonus_to_test_result)
        score_adjustments.register("effective_test_score", effective_test_score)
        score_adjustments.register("score_state", appeal_score_state)
        score_adjustments.register("student_visible_bonus_map", student_visible_appeal_bonus_map)
        score_adjustments.register("student_visible_effective_test_score", student_visible_effective_test_score)
        score_adjustments.register("student_visible_score_state", student_visible_appeal_score_state)
        score_adjustments.register("student_visible_status_by_qid", student_visible_appeal_status_by_qid)
        score_adjustments.register("can_create", can_create_appeal)
        score_adjustments.register("remaining_window_seconds", remaining_window_seconds)
        score_adjustments.register("is_applicable", appeal_applicable)
