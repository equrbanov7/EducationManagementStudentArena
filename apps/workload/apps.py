from django.apps import AppConfig


class WorkloadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workload"
    verbose_name = "Dərs yükü"

    def ready(self):
        from apps.registrar.public import (
            register_history_restore_actions,
            register_joint_journal_candidates,
            register_teacher_journal_assignments,
            register_teacher_journal_plan_hours,
        )
        from core.group_identity import register_alias_provider

        from .services.group_aliases import verified_aliases
        from .services.joint_journals import joint_journal_candidates
        from .services.journal_assignments import teacher_journal_assignments, teacher_journal_plan_hours

        register_alias_provider(verified_aliases)
        from .services.history_restore import attach_actions

        register_history_restore_actions(attach_actions)
        register_teacher_journal_assignments(teacher_journal_assignments)
        register_teacher_journal_plan_hours(teacher_journal_plan_hours)
        register_joint_journal_candidates(joint_journal_candidates)
