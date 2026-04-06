"""
User profile models for EMS Arena.
Extends Django's User model with additional profile information.
"""

import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import check_password, identify_hasher
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from core.constants import OrganizationType
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


class ProfileRole:
    """Role constants for UserProfile.role field."""

    SUPERADMIN = "superadmin"
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    MEMBER = "member"
    HR = "hr"
    TEACHER = "teacher"
    ASSISTANT_TEACHER = "assistant_teacher"
    LEAD_STUDENT = "lead_student"
    STUDENT = "student"

    CHOICES = [
        (SUPERADMIN, "Super Admin"),
        (ORG_OWNER, "Təşkilat Sahibi"),
        (ORG_ADMIN, "Təşkilat Admini"),
        (MEMBER, "Üzv"),
        (HR, "HR"),
        (TEACHER, "Müəllim"),
        (ASSISTANT_TEACHER, "Müəllim Köməkçisi"),
        (LEAD_STUDENT, "Baş Tələbə"),
        (STUDENT, "Tələbə"),
    ]

    # Level mapping for hierarchy checks
    LEVELS = {
        SUPERADMIN: 100,
        ORG_OWNER: 90,
        ORG_ADMIN: 80,
        MEMBER: 20,
        HR: 65,
        TEACHER: 60,
        ASSISTANT_TEACHER: 55,
        LEAD_STUDENT: 30,
        STUDENT: 10,
    }

    ROLE_NAME_NORMALIZATION = {
        "deputy_director": "vice_director",
        "chair_head": "department_head",
        "section_head": "department_head",
    }

    MEMBERSHIP_ROLE_ALIASES = {
        MEMBER: {MEMBER},
        STUDENT: {STUDENT},
        LEAD_STUDENT: {LEAD_STUDENT, STUDENT},
        HR: {HR},
        TEACHER: {TEACHER},
        "instructor": {TEACHER, "instructor"},
        "professor": {TEACHER, "professor"},
        "associate_professor": {TEACHER, "associate_professor"},
        ASSISTANT_TEACHER: {ASSISTANT_TEACHER},
        "assistant": {ASSISTANT_TEACHER, "assistant"},
        "lab_assistant": {ASSISTANT_TEACHER, "lab_assistant"},
    }

    ADMIN_EQUIVALENT_ROLE_NAMES = {
        ORG_ADMIN,
        ORG_OWNER,
        "rector",
        "vice_rector",
        "dean",
        "vice_dean",
        "department_head",
        "director",
        "vice_director",
        "manager",
        "senior_instructor",
    }

    @classmethod
    def normalize_membership_role_name(cls, role_name):
        normalized = (role_name or "").strip().lower()
        return cls.ROLE_NAME_NORMALIZATION.get(normalized, normalized)

    @classmethod
    def aliases_for_membership_role(cls, role_name, *, level=0, is_org_owner=False):
        normalized = cls.normalize_membership_role_name(role_name)
        aliases = set()

        if normalized:
            aliases.add(normalized)
            aliases.update(cls.MEMBERSHIP_ROLE_ALIASES.get(normalized, set()))

        if is_org_owner:
            aliases.update({cls.ORG_OWNER, cls.ORG_ADMIN})

        if normalized in cls.ADMIN_EQUIVALENT_ROLE_NAMES or level >= cls.LEVELS.get(cls.ORG_ADMIN, 80):
            aliases.add(cls.ORG_ADMIN)

        return aliases


class UserProfile(models.Model):
    """
    Extended user profile with organization type and additional information.
    Links user to an organization for multi-tenant support.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    # Organization linkage for multi-tenant support
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name="Təşkilat",
        help_text="İstifadəçinin aid olduğu təşkilat",
    )

    requested_organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_members",
        verbose_name="Müraciət edilən təşkilat",
        help_text="Signup zamanı seçilən, amma hələ qoşulmadığı təşkilat",
    )

    requested_organization_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Müraciət edilən təşkilat adı",
        help_text="Təşkilat DB-də yoxdursa signup zamanı daxil edilən ad",
    )

    requested_organization_message = models.CharField(
        max_length=280,
        blank=True,
        default="",
        verbose_name="Təşkilata müraciət mesajı",
        help_text="Tələbənin təşkilata qoşulma üçün yazdığı qısa mesaj",
    )

    organization_type = models.CharField(
        max_length=20,
        choices=OrganizationType.CHOICES,
        default=OrganizationType.INDIVIDUAL,
        verbose_name="Təşkilat tipi",
        help_text="Hansı təşkilat tipində qeydiyyatdan keçdiniz",
    )

    country = models.CharField(max_length=100, blank=True, default="", verbose_name="Ölkə")

    student_university_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Universitet adı",
        help_text="Tələbə üçün universitet adı (əgər varsa)",
    )

    student_school_identifier = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Məktəb nömrəsi/identifikatoru",
        help_text="Tələbə üçün məktəb nömrəsi və ya rəsmi identifikator",
    )

    student_specialization = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="İxtisas / Fakültə",
        help_text="Tələbənin ixtisası və ya fakültəsi",
    )

    student_group_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Qrup / Sinif",
        help_text="Tələbənin qrup nömrəsi və ya sinif qrupu",
    )

    department = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Departament / Kafedra",
        help_text="Müəllim və ya işçinin departamenti/kafedrası",
    )

    staff_position = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Vəzifə",
        help_text="İşçinin vəzifəsi (yalnız staff üçün)",
    )

    # RBAC role field – single source of truth for role checks
    role = models.CharField(
        max_length=30,
        choices=ProfileRole.CHOICES,
        default=ProfileRole.MEMBER,
        db_index=True,
        verbose_name="Rol",
        help_text="İstifadəçinin sistəmdəki rolu",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Avatar",
        help_text="Profil şəkli",
    )

    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon", help_text="Əlaqə nömrəsi")

    bio = models.TextField(blank=True, verbose_name="Haqqında", help_text="Qısa məlumat")

    supervisor_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Nəzarətçi kodu",
        help_text="Admin/supervisor tərəfindən təyin edilir. User dəyişə bilməz.",
    )

    location = models.CharField(max_length=100, blank=True, verbose_name="Yer", help_text="Şəhər və ya ünvan")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma tarixi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yenilənmə tarixi")

    class Meta:
        verbose_name = "İstifadəçi profili"
        verbose_name_plural = "İstifadəçi profilləri"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["role"]),
            models.Index(fields=["requested_organization"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def organization_name(self):
        """Get organization name or 'Fərdi' for individual users."""
        if self.organization:
            return self.organization.name
        return "Fərdi"

    @property
    def role_level(self):
        """Numeric level for the current role."""
        return ProfileRole.LEVELS.get(self.role, 0)
