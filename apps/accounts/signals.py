"""
Signals for accounts app.
Handles automatic profile creation.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(sender, instance, created, update_fields=None, **kwargs):
    """
    Ensure every User has a UserProfile.

    Performance: this fires on *every* ``User.save()`` — including the
    ``user.save(update_fields=["last_login"])`` that Django runs on each login.
    Previously a second receiver also called ``profile.save()`` on every user
    save, issuing a full-row UPDATE (and a SELECT) per login for no reason. We
    now:

    * skip all profile work when the save only touched ``last_login`` (the hot
      login path), and
    * only ``get_or_create`` the profile otherwise, never re-saving it blindly.

    The profile is created on user creation; the ``else`` branch is purely a
    defensive backfill for legacy users that predate this signal.
    """
    # Hot path: login updates only last_login — no profile change is implied.
    if update_fields is not None and set(update_fields) <= {"last_login"}:
        return

    from apps.accounts.models import UserProfile

    UserProfile.objects.get_or_create(user=instance)
