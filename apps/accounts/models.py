"""
User profile models for EMS Arena.
Extends Django's User model with additional profile information.
"""

from django.conf import settings
from django.db import models

from core.constants import OrganizationType


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
