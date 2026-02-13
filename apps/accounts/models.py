"""
User profile models for EMS Arena.
Extends Django's User model with additional profile information.
"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.constants import OrganizationType


class UserProfile(models.Model):
    """
    Extended user profile with organization type and additional information.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )

    organization_type = models.CharField(
        max_length=20,
        choices=OrganizationType.CHOICES,
        default=OrganizationType.INDIVIDUAL,
        verbose_name="Təşkilat tipi",
        help_text="Hansı təşkilat tipində qeydiyyatdan keçdiniz",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Avatar",
        help_text="Profil şəkli",
    )

    phone = models.CharField(
        max_length=20, blank=True, verbose_name="Telefon", help_text="Əlaqə nömrəsi"
    )

    bio = models.TextField(
        blank=True, verbose_name="Haqqında", help_text="Qısa məlumat"
    )

    supervisor_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Nəzarətçi kodu",
        help_text="Admin/supervisor tərəfindən təyin edilir. User dəyişə bilməz.",
    )

    location = models.CharField(
        max_length=100, blank=True, verbose_name="Yer", help_text="Şəhər və ya ünvan"
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Yaradılma tarixi"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yenilənmə tarixi")

    class Meta:
        verbose_name = "İstifadəçi profili"
        verbose_name_plural = "İstifadəçi profilləri"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.get_organization_type_display()}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a UserProfile when a new User is created.
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """
    Automatically save the UserProfile when the User is saved.
    """
    if hasattr(instance, "profile"):
        instance.profile.save()
