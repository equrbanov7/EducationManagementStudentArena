from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        # ✅ accounts/signals.py yüklənsin
        # ✅ Import models to register UserProfile signals
        from apps.accounts import models  # noqa
        from apps.accounts import roles  # noqa - Attach role properties to User model
        from apps.accounts import signals  # noqa

        # M3 (2026-07-02): admin 2FA OTP hook-larını core.auth_otp-a qoş
        # (core→accounts kənarını kəsən fail-closed registry).
        from core import auth_otp

        from .services import issue_email_otp, verify_otp_code

        auth_otp.register("issue_email_otp", lambda user, *, purpose: issue_email_otp(user, purpose=purpose))
        auth_otp.register(
            "verify_otp_code", lambda user, *, code, purpose: verify_otp_code(user, code, purpose=purpose)
        )

        # 2026-10-01: «Akademik fəaliyyət» qoşmaları — məxfi media prefiksinin
        # icazə siyasəti (core deny-by-default-dur) + qeyd silinəndə faylların
        # təmizlənməsi (istifadəçi kaskadı da daxil).
        from django.db.models.signals import post_delete

        from core.media_policies import register_media_policy

        from .academic_models import ACADEMIC_ATTACHMENT_PREFIX, AcademicProfileItem
        from .services.academic_attachments import check_attachment_media_access, cleanup_files_on_item_delete

        register_media_policy(ACADEMIC_ATTACHMENT_PREFIX, check_attachment_media_access)
        post_delete.connect(
            cleanup_files_on_item_delete,
            sender=AcademicProfileItem,
            dispatch_uid="accounts.academic_item_attachment_cleanup",
        )
