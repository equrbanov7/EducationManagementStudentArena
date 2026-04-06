"""
Signals for accounts app.
Handles automatic profile creation.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    profile, _created = UserProfile.objects.get_or_create(user=instance)
    profile.save()
