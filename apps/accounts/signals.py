"""
Signals for accounts app.
Handles automatic profile creation and group setup.
"""

from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

DEFAULT_GROUPS = ["student", "teacher", "assistant_teacher", "moderator"]


@receiver(post_migrate)
def create_default_groups(sender, **kwargs):
    """
    Create default groups after migration.
    """
    # yalnız "accounts" migrate olanda işlə (boşuna hər migrate-da qaçmasın)
    if sender.name != "apps.accounts":
        return

    Group = apps.get_model("auth", "Group")

    for name in DEFAULT_GROUPS:
        Group.objects.get_or_create(name=name)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a UserProfile when a new User is created.
    """
    if created:
        # Import here to avoid circular imports
        from apps.accounts.models import UserProfile

        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """
    Automatically save the UserProfile when the User is saved.
    Ensures profile exists even if it wasn't created initially.
    """
    from apps.accounts.models import UserProfile

    if hasattr(instance, "profile"):
        instance.profile.save()
    else:
        # Profile doesn't exist, create it now
        UserProfile.objects.get_or_create(user=instance)

