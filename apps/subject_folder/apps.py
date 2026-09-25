from django.apps import AppConfig


class SubjectFolderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subject_folder"
    label = "subject_folder"
    verbose_name = "Fənn qovluğu"

    def ready(self):
        """Qorunan media prefikslərinin icazə siyasətini ``core``-a qeyd edir.

        ``core.media_views`` deny-by-default-dur: qeydsiz prefiks superadmin-dən
        başqa hər kəsə 404 verir. Siyasət funksiyaları bu app-ın öz modulundadır,
        ``core`` app-ı idxal etmir (``register_media_policy`` runtime reyestri).
        """
        from core.media_policies import register_media_policy

        from .constants import MATERIALS_MEDIA_PREFIX, SUBMISSIONS_MEDIA_PREFIX
        from .services.media import check_material_media_access, check_submission_media_access

        register_media_policy(MATERIALS_MEDIA_PREFIX, check_material_media_access)
        register_media_policy(SUBMISSIONS_MEDIA_PREFIX, check_submission_media_access)
