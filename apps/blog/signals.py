import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from .models import Category, Post, Subscriber
from .selectors import invalidate_blog_listing_cache

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Cache the previous approval_status so we can detect transitions.
# ────────────────────────────────────────────────────────────────────────────


@receiver(pre_save, sender=Post)
def _cache_post_approval_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_approval_status = None
        return
    try:
        instance._previous_approval_status = (
            Post.objects.filter(pk=instance.pk).values_list("approval_status", flat=True).first()
        )
    except Exception:
        instance._previous_approval_status = None


# ────────────────────────────────────────────────────────────────────────────
# Notify teachers when a post is submitted for approval (PENDING).
# ────────────────────────────────────────────────────────────────────────────


def _get_reviewers_for_post(post):
    """Return the set of User instances who can review this post."""
    from apps.exams.models import StudentGroup

    User = get_user_model()
    reviewer_user_ids = set()

    groups = StudentGroup.objects.filter(students=post.author).prefetch_related("teachers")
    for group in groups:
        if group.teacher_id:
            reviewer_user_ids.add(group.teacher_id)
        # Iterate over the prefetch cache to avoid per-group DB queries.
        for teacher in group.teachers.all():
            reviewer_user_ids.add(teacher.pk)

    if not reviewer_user_ids:
        return []

    return list(User.objects.filter(pk__in=reviewer_user_ids, is_active=True))


@receiver(post_save, sender=Post)
def notify_teachers_on_post_pending(sender, instance, created, **kwargs):
    """Notify the post's reviewer(s) when approval_status transitions to PENDING."""
    if not instance.requires_approval:
        return

    current_status = instance.approval_status
    previous_status = getattr(instance, "_previous_approval_status", None)

    # Trigger when: newly created as PENDING, or re-submitted (status changed to PENDING).
    if current_status != Post.ApprovalStatus.PENDING:
        return
    if not created and previous_status == Post.ApprovalStatus.PENDING:
        # No transition — already was PENDING; avoid duplicate notifications.
        return

    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.services import create_notification_for_users

        reviewers = _get_reviewers_for_post(instance)
        if not reviewers:
            return

        author_name = (instance.author.get_full_name() or "").strip() or instance.author.username
        create_notification_for_users(
            recipients=reviewers,
            title=f"Yeni post təsdiq gözləyir: {instance.title}",
            message=f'{author_name} tərəfindən "{instance.title}" başlıqlı post təsdiq üçün göndərildi.',
            link=reverse("accounts:profile") + "?section=pending-post-approvals",
            notification_type=NotificationType.APPROVAL,
            metadata={"post_id": instance.pk, "author_id": instance.author_id},
        )
    except Exception:
        logger.exception("Failed to notify teachers about pending post pk=%s", instance.pk)


# ────────────────────────────────────────────────────────────────────────────
# Notify the post author when the approval decision changes.
# ────────────────────────────────────────────────────────────────────────────


@receiver(post_save, sender=Post)
def notify_author_on_approval_decision(sender, instance, created, **kwargs):
    """Notify the post author when their post is approved or returned for changes."""
    if created or not instance.requires_approval:
        return

    current_status = instance.approval_status
    previous_status = getattr(instance, "_previous_approval_status", None)

    if current_status == previous_status:
        return

    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.services import create_notification

        if current_status == Post.ApprovalStatus.APPROVED:
            create_notification(
                recipient=instance.author,
                title=f"Postunuz təsdiqləndi: {instance.title}",
                message=f'"{instance.title}" başlıqlı postunuz müəllim tərəfindən təsdiqləndi və paylaşıldı.',
                link=reverse("article_detail", kwargs={"slug": instance.slug}),
                notification_type=NotificationType.APPROVAL,
                metadata={"post_id": instance.pk},
            )
        elif current_status == Post.ApprovalStatus.NEEDS_CHANGES:
            feedback = (instance.approval_feedback or "").strip()
            message = f'"{instance.title}" başlıqlı postunuzda düzəliş tələb olunur.'
            if feedback:
                message = f"{message} Müəllim rəyi: {feedback}"
            create_notification(
                recipient=instance.author,
                title=f"Post düzəliş tələb edir: {instance.title}",
                message=message,
                link=reverse("accounts:profile") + "?section=posts",
                notification_type=NotificationType.APPROVAL,
                metadata={"post_id": instance.pk, "feedback": feedback},
            )
    except Exception:
        logger.exception("Failed to notify post author about approval decision pk=%s", instance.pk)


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
