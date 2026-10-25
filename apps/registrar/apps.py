from django.apps import AppConfig


class RegistrarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registrar"
    verbose_name = "Registrar (curriculum)"

    def ready(self):
        from apps.organizations.public import register_student_transfer

        register_student_transfer(_transfer_student_group)
        _register_retake_media()


def _register_retake_media():
    """25% qəbzləri və alt qrup sənədləri — qorunan media (default DENY, ``retake_media`` checker-ləri)."""
    from core.media_policies import register_media_policy

    from .models.retake import RETAKE_DOCUMENT_PREFIX, RETAKE_RECEIPT_PREFIX
    from .models.retake_log import EXAM_CHANCE_DOCUMENT_PREFIX
    from .retake_media import check_chance_document_access, check_document_access, check_receipt_access

    register_media_policy(RETAKE_RECEIPT_PREFIX, check_receipt_access)
    register_media_policy(RETAKE_DOCUMENT_PREFIX, check_document_access)
    register_media_policy(EXAM_CHANCE_DOCUMENT_PREFIX, check_chance_document_access)

    # «Xarici nəticənin tanınması» sənədi (2026-10-25) — tələbə + açarlı heyət (struktur əhatəsi).
    from .credit_recognition import check_document_access as check_recognition_document_access
    from .models.external_recognition import RECOGNITION_DOCUMENT_PREFIX

    register_media_policy(RECOGNITION_DOCUMENT_PREFIX, check_recognition_document_access)


def _transfer_student_group(**kwargs):
    # Resolve the owning service at call time; tests and overrides keep working.
    from .transfer import transfer_student_group

    return transfer_student_group(**kwargs)
