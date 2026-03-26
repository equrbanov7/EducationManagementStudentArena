import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Category, Post, Subscriber
from .selectors import invalidate_blog_listing_cache

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Post)
def send_new_post_notification(sender, instance, created, **kwargs):
    if created and instance.is_published:
        active_subscribers = list(Subscriber.objects.filter(is_active=True).values_list("email", flat=True))

        if not active_subscribers:
            return

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


@receiver(post_save, sender=Category)
def invalidate_blog_cache_on_category_save(sender, instance, **kwargs):
    invalidate_blog_listing_cache()


@receiver(post_delete, sender=Category)
def invalidate_blog_cache_on_category_delete(sender, instance, **kwargs):
    invalidate_blog_listing_cache()
