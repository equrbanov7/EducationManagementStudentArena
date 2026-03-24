# your_app/signals.py
import logging

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Post  # Post və Subscriber modellərini import et
from .models import Subscriber
from .selectors import _CACHE_KEY_NAVBAR, _CACHE_KEY_POPULAR_TOPICS, _CACHE_KEY_SIDEBAR

logger = logging.getLogger(__name__)


def _invalidate_blog_listing_cache():
    """Remove cached blog listing data that changes when posts are added/removed."""
    try:
        cache.delete_many(
            [
                _CACHE_KEY_NAVBAR,
                _CACHE_KEY_SIDEBAR,
                # Popular topics uses a keyed pattern; delete the common key
                f"{_CACHE_KEY_POPULAR_TOPICS}:5",
            ]
        )
    except Exception:
        logger.warning("Redis unavailable; could not invalidate blog listing cache")


# Yeni post üçün email göndərmək
@receiver(post_save, sender=Post)
def send_new_post_notification(sender, instance, created, **kwargs):
    # Yalnız yeni yaradılan və yayımlanan postlar üçün işləsin
    if created and instance.is_published:

        # 1. Bütün aktiv abunəçiləri çək
        active_subscribers = list(
            Subscriber.objects.filter(is_active=True).values_list("email", flat=True)
        )

        if not active_subscribers:
            return  # Abunəçi yoxdursa dayandır

        # 2. Bildirişi Celery vasitəsilə arxa planda göndər
        from core.email_tasks import send_new_post_notification_email

        send_new_post_notification_email.delay(
            post_pk=instance.pk,
            subscriber_emails=active_subscribers,
        )


@receiver(post_save, sender=Post)
def invalidate_blog_cache_on_post_save(sender, instance, **kwargs):
    """Invalidate cached blog listing data whenever a post is saved."""
    _invalidate_blog_listing_cache()


@receiver(post_delete, sender=Post)
def invalidate_blog_cache_on_post_delete(sender, instance, **kwargs):
    """Invalidate cached blog listing data whenever a post is deleted."""
    _invalidate_blog_listing_cache()


# signals.py faylını app konfiqurasiyasında aktivləşdir:

# # your_app/apps.py
# from django.apps import AppConfig


# class YourAppConfig(AppConfig):
#     default_auto_field = "django.db.models.BigAutoField"
#     name = "your_app"

#     def ready(self):
#         import your_app.signals  # Sinyalları burada import edirik
