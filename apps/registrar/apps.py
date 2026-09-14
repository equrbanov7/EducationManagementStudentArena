from django.apps import AppConfig


class RegistrarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registrar"
    verbose_name = "Registrar (curriculum)"

    def ready(self):
        from apps.organizations.public import register_student_transfer

        register_student_transfer(_transfer_student_group)


def _transfer_student_group(**kwargs):
    # Resolve the owning service at call time; tests and overrides keep working.
    from .transfer import transfer_student_group

    return transfer_student_group(**kwargs)
