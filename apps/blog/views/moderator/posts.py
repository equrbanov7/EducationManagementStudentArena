"""Blog — moderator səthi: baxış/qərar/silmə (F7 rol-skeleti, 2026-07-02)."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from ...models import Post, PostApprovalLog
from ...services import can_user_moderate_post, can_user_review_post
from ..shared._helpers import _can_manage_blog_content
from ..shared.module_gate import posts_module_required

logger = logging.getLogger(__name__)


@posts_module_required
@login_required
@require_POST
def review_post(request, post_id):
    post = get_object_or_404(Post.objects.select_related("author"), pk=post_id, requires_approval=True)

    if not can_user_review_post(request.user, post):
        raise PermissionDenied(pgettext("blog.moderation.message", "Bu postu təsdiqləmək üçün icazəniz yoxdur."))

    action = (request.POST.get("action") or "").strip().lower()
    feedback = (request.POST.get("feedback") or "").strip()

    if action not in {"approve", "needs_changes"}:
        messages.error(request, pgettext("blog.moderation.message", "Yanlış əməliyyat seçildi."))
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    if action == "needs_changes" and not feedback:
        messages.error(request, pgettext("blog.moderation.message", "Düzəliş istəyi üçün feedback yazın."))
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    if action == "approve":
        post.approval_status = Post.ApprovalStatus.APPROVED
        post.is_published = True
        post.approved_by = request.user
        post.approved_at = timezone.now()
        post.approval_feedback = feedback
        post.save(
            update_fields=[
                "approval_status",
                "is_published",
                "approved_by",
                "approved_at",
                "approval_feedback",
                "updated_at",
            ]
        )
        PostApprovalLog.objects.create(
            post=post,
            reviewer=request.user,
            action=PostApprovalLog.Action.APPROVED,
            feedback=feedback,
        )
        messages.success(request, pgettext("blog.moderation.message", "Post təsdiqləndi və paylaşıldı."))
    else:
        post.approval_status = Post.ApprovalStatus.NEEDS_CHANGES
        post.is_published = False
        post.approval_feedback = feedback
        post.save(
            update_fields=[
                "approval_status",
                "is_published",
                "approved_by",
                "approved_at",
                "approval_feedback",
                "updated_at",
            ]
        )
        PostApprovalLog.objects.create(
            post=post,
            reviewer=request.user,
            action=PostApprovalLog.Action.NEEDS_CHANGES,
            feedback=feedback,
        )
        messages.info(request, pgettext("blog.moderation.message", "Feedback göndərildi. Post düzəliş gözləyir."))

    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")


# 2. POSTU SİLMƏ (Təsdiqdən sonra)


@posts_module_required
@login_required
@require_POST
def delete_post(request, post_id):
    if not _can_manage_blog_content(request.user):
        raise PermissionDenied(pgettext("blog.permission", "no_permission"))

    post = get_object_or_404(Post, pk=post_id, author=request.user)
    post_title = post.title
    post.delete()

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JsonResponse(
            {
                "success": True,
                "message": pgettext("blog.post.message", "deleted").format(title=post_title),
            }
        )

    return redirect(f"{reverse('accounts:profile')}?section=posts")


# 3. MÜƏLLIM MODERASIYA: sil, deaktiv et, və ya yenidən aktiv et


@posts_module_required
@login_required
@require_POST
def teacher_moderate_post(request, post_id):
    """
    Müəllim tərəfindən post moderasiyası.

    POST parametrləri:
      action   – "delete" | "deactivate" | "reactivate"
      feedback – "delete" və "deactivate" üçün məcburi; "reactivate" üçün opsional.

    Yalnız postu nəzərdən keçirə bilən müəllimlər, orq adminlər/sahiblər
    və superadminlər bu əməliyyatı icra edə bilər.
    """
    post = get_object_or_404(Post.objects.select_related("author"), pk=post_id)

    if not can_user_moderate_post(request.user, post):
        raise PermissionDenied(pgettext("blog.moderation.message", "Bu postu idarə etmək üçün icazəniz yoxdur."))

    action = (request.POST.get("action") or "").strip().lower()
    feedback = (request.POST.get("feedback") or "").strip()

    if action not in {"delete", "deactivate", "reactivate"}:
        messages.error(request, pgettext("blog.moderation.message", "Yanlış əməliyyat seçildi."))
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    # Feedback is mandatory for delete and deactivate so the student knows the reason.
    if action in {"delete", "deactivate"} and not feedback:
        reason_required_msg = pgettext("blog.moderation.message", "Zəhmət olmasa əməliyyatın səbəbini yazın.")
        messages.error(request, reason_required_msg)
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse({"success": False, "error": reason_required_msg}, status=400)
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    def _redirect_next():
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    if action == "delete":
        post_title = post.title
        post_author = post.author

        # Notify the author about the deletion before removing the record.
        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.public import create_notification

            create_notification(
                recipient=post_author,
                title=pgettext("blog.notification", "Postunuz silindi: {title}").format(title=post_title),
                message=pgettext(
                    "blog.notification", '"{title}" başlıqlı postunuz idarəçi tərəfindən silindi. Səbəb: {reason}'
                ).format(title=post_title, reason=feedback),
                link=f"{reverse('accounts:profile')}?section=posts",
                notification_type=NotificationType.APPROVAL,
                metadata={"post_title": post_title, "feedback": feedback},
            )
        except Exception:
            logger.exception("Failed to notify author about post deletion title=%s", post_title)

        post.delete()
        deleted_msg = pgettext("blog.post.message", "deleted").format(title=post_title)
        messages.success(request, deleted_msg)

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse({"success": True, "message": deleted_msg})

        return _redirect_next()

    if action == "reactivate":
        post.is_published = True
        post.save(update_fields=["is_published", "updated_at"])

        PostApprovalLog.objects.create(
            post=post,
            reviewer=request.user,
            action=PostApprovalLog.Action.APPROVED,
            feedback=feedback or "Post yenidən aktiv edildi.",
        )

        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.public import create_notification

            create_notification(
                recipient=post.author,
                title=pgettext("blog.notification", "Postunuz yenidən aktiv edildi: {title}").format(title=post.title),
                message=pgettext(
                    "blog.notification", '"{title}" başlıqlı postunuz idarəçi tərəfindən yenidən paylaşıldı.'
                ).format(title=post.title),
                link=reverse("article_detail", kwargs={"slug": post.slug}),
                notification_type=NotificationType.APPROVAL,
                metadata={"post_id": post.pk},
            )
        except Exception:
            logger.exception("Failed to notify author about post reactivation pk=%s", post.pk)

        messages.success(
            request,
            pgettext("blog.post.message", '"{title}" postu yenidən aktiv edildi və paylaşıldı.').format(
                title=post.title
            ),
        )

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "message": pgettext("blog.post.message", '"{title}" postu aktiv edildi.').format(title=post.title),
                    "is_published": post.is_published,
                }
            )

        return _redirect_next()

    # action == "deactivate": postu gizlət, tələbəyə rəy göndər
    post.is_published = False
    post.approval_feedback = feedback
    post.save(update_fields=["is_published", "approval_feedback", "updated_at"])

    PostApprovalLog.objects.create(
        post=post,
        reviewer=request.user,
        action=PostApprovalLog.Action.FEEDBACK,
        feedback=feedback,
    )

    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.public import create_notification

        create_notification(
            recipient=post.author,
            title=pgettext("blog.notification", "Postunuz deaktiv edildi: {title}").format(title=post.title),
            message=pgettext(
                "blog.notification",
                '"{title}" başlıqlı postunuz idarəçi tərəfindən gizlədildi. '
                "Post silinməyib — düzəlişlər edib yenidən göndərə bilərsiniz. "
                "Rəy: {reason}",
            ).format(title=post.title, reason=feedback),
            link=f"{reverse('accounts:profile')}?section=posts",
            notification_type=NotificationType.APPROVAL,
            metadata={"post_id": post.pk, "feedback": feedback},
        )
    except Exception:
        logger.exception("Failed to notify author about post deactivation pk=%s", post.pk)

    messages.info(
        request,
        pgettext(
            "blog.moderation.message",
            '"{title}" postu deaktiv edildi. Post gizlədilib, lakin silinməyib — '
            "tələbə düzəliş edib yenidən göndərə bilər.",
        ).format(title=post.title),
    )

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JsonResponse(
            {
                "success": True,
                "message": pgettext("blog.post.message", '"{title}" postu deaktiv edildi.').format(title=post.title),
                "is_published": post.is_published,
            }
        )

    return _redirect_next()
