"""E-poçt OTP modeli — signup/login/bərpa axınlarının birdəfəlik kodları.

Ölçü büdcəsi (``scripts/check_module_size.py``): ``accounts/models.py`` sərt
SOFT_CAP-a dayandığı üçün bu model ``academic_models`` / ``identity_models``
presedenti ilə ayrıca modula çıxarıldı və ``models.py``-dan yenidən ixrac
olunur — ``from apps.accounts.models import EmailOTP`` import səthi qorunur.
Model eyni ``accounts`` app-ındadır, ona görə miqrasiya tələb olunmur.
"""

import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import check_password, identify_hasher
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from core.utils import get_auth_otp_expiry_seconds, get_auth_otp_max_attempts


class EmailOTP(models.Model):
    """Secure one-time password record for signup, login, and recovery flows."""

    _HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup verification"
        LOGIN = "login", "Login verification"
        PASSWORD_RESET = "password_reset", "Password reset"
        ADMIN_LOGIN = "admin_login", "Admin login"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otps",
        null=True,
        blank=True,
    )
    email = models.EmailField(db_index=True, blank=True, default="")
    # Legacy storage kept temporarily so pre-migration OTP rows remain verifiable.
    code = models.CharField(max_length=128, blank=True, default="")
    otp_hash = models.CharField(max_length=64, blank=True, default="")
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.SIGNUP,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    attempts_count = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTPs"
        indexes = [
            models.Index(fields=["email", "purpose", "created_at"]),
            models.Index(fields=["user", "purpose", "created_at"]),
        ]

    @staticmethod
    def normalize_email(email):
        return BaseUserManager.normalize_email(str(email or "").strip()).lower()

    @classmethod
    def build_otp_hash(cls, *, email, otp, purpose):
        normalized_email = cls.normalize_email(email)
        payload = f"{purpose}:{normalized_email}:{str(otp or '').strip()}"
        return salted_hmac(
            "apps.accounts.email_otp",
            payload,
            secret=settings.SECRET_KEY,
            algorithm="sha256",
        ).hexdigest()

    @staticmethod
    def _code_is_hashed(value):
        try:
            identify_hasher(value)
            return True
        except Exception:
            return False

    @classmethod
    def _is_sha256_digest(cls, value):
        return bool(value and cls._HEX_DIGEST_RE.fullmatch(str(value).strip().lower()))

    def save(self, *args, **kwargs):
        if self.user_id and not self.email:
            self.email = self.normalize_email(getattr(self.user, "email", ""))
        else:
            self.email = self.normalize_email(self.email)

        if self.code and not self.otp_hash and not self._code_is_hashed(self.code):
            self.otp_hash = self.build_otp_hash(
                email=self.email or getattr(self.user, "email", ""),
                otp=self.code,
                purpose=self.purpose,
            )
            self.code = ""
        elif self.otp_hash and not self._is_sha256_digest(self.otp_hash):
            self.otp_hash = self.build_otp_hash(
                email=self.email or getattr(self.user, "email", ""),
                otp=self.otp_hash,
                purpose=self.purpose,
            )

        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(seconds=get_auth_otp_expiry_seconds())
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def matches_code(self, raw_code):
        candidate = str(raw_code or "").strip()
        if not candidate:
            return False

        if self.otp_hash:
            candidate_hash = self.build_otp_hash(
                email=self.email or getattr(self.user, "email", ""),
                otp=candidate,
                purpose=self.purpose,
            )
            if constant_time_compare(candidate_hash, self.otp_hash):
                return True

        if self.code:
            if self._code_is_hashed(self.code):
                return check_password(candidate, self.code)
            return constant_time_compare(candidate, self.code)

        return False

    @property
    def remaining_attempts(self):
        return max(0, get_auth_otp_max_attempts() - int(self.attempts_count or 0))

    def mark_verified(self):
        self.is_verified = True
        self.is_used = True
        self.save(update_fields=["is_verified", "is_used"])

    def invalidate(self):
        if self.is_used:
            return
        self.is_used = True
        self.save(update_fields=["is_used"])

    def register_failed_attempt(self):
        self.attempts_count = int(self.attempts_count or 0) + 1
        if self.attempts_count >= get_auth_otp_max_attempts():
            self.is_used = True
            self.save(update_fields=["attempts_count", "is_used"])
            return
        self.save(update_fields=["attempts_count"])

    @classmethod
    def pending_queryset(cls, *, user=None, email=None, purpose=None):
        if not user and not email:
            return cls.objects.none()

        filters = {
            "is_used": False,
        }
        if user is not None:
            filters["user"] = user
        if email:
            filters["email"] = cls.normalize_email(email)
        if purpose:
            filters["purpose"] = purpose
        return cls.objects.filter(**filters).order_by("-created_at")

    @classmethod
    def get_matching_otp(cls, *, user=None, email=None, code="", purpose=None):
        candidate = str(code or "").strip()
        if not candidate:
            return None

        queryset = cls.pending_queryset(user=user, email=email, purpose=purpose).filter(
            expires_at__gte=timezone.now(),
        )

        for otp in queryset[:10]:
            if otp.matches_code(candidate):
                return otp

        return None
