# your_app/signals.py
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Post  # Post və Subscriber modellərini import et
from .models import Subscriber
from .selectors import invalidate_blog_listing_cache

logger = logging.getLogger(__name__)


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
    invalidate_blog_listing_cache()


@receiver(post_delete, sender=Post)
def invalidate_blog_cache_on_post_delete(sender, instance, **kwargs):
    """Invalidate cached blog listing data whenever a post is deleted."""
    invalidate_blog_listing_cache()


# signals.py faylını app konfiqurasiyasında aktivləşdir:

# # your_app/apps.py
# from django.apps import AppConfig


# class YourAppConfig(AppConfig):
#     default_auto_field = "django.db.models.BigAutoField"
#     name = "your_app"

#     def ready(self):
#         import your_app.signals  # Sinyalları burada import edirik
