"""Post management views for superadmin and organization owner/admin."""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import ProfileRole, UserProfile
from apps.accounts.policies import get_user_role_level, is_superadmin_user
from apps.audit.utils import log_action
from apps.blog.models import Post, PostApprovalLog
from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification
from apps.organizations.models import Membership, Organization
from core.constants import AuditAction
from core.rls import bypass_rls

logger = logging.getLogger(__name__)
User = get_user_model()

POSTS_PER_PAGE = 20


@login_required
def superadmin_post_management(request):
    """Superadmin page to view, filter, and manage all posts."""
    if not is_superadmin_user(request.user):
        raise PermissionDenied

    search = (request.GET.get("q") or "").strip()
    org_filter = (request.GET.get("org") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    with bypass_rls():
        posts_qs = Post.objects.select_related(
            "author",
            "author__profile",
            "category",
        ).order_by("-created_at")

        if search:
            posts_qs = posts_qs.filter(
                Q(title__icontains=search)
                | Q(content__icontains=search)
                | Q(author__username__icontains=search)
                | Q(author__first_name__icontains=search)
                | Q(author__last_name__icontains=search)
            )

        if org_filter:
            member_user_ids = Membership.objects.filter(organization_id=org_filter, is_active=True).values_list(
                "user_id", flat=True
            )
            posts_qs = posts_qs.filter(author_id__in=member_user_ids)

        if role_filter:
            profile_user_ids = UserProfile.objects.filter(role=role_filter).values_list("user_id", flat=True)
            posts_qs = posts_qs.filter(author_id__in=profile_user_ids)

        if status_filter == "published":
            posts_qs = posts_qs.filter(is_published=True)
        elif status_filter == "draft":
            posts_qs = posts_qs.filter(is_published=False, requires_approval=False)
        elif status_filter == "pending":
            posts_qs = posts_qs.filter(requires_approval=True, approval_status="pending")
        elif status_filter == "needs_changes":
            posts_qs = posts_qs.filter(requires_approval=True, approval_status="needs_changes")

        if date_from:
            posts_qs = posts_qs.filter(created_at__date__gte=date_from)
        if date_to:
            posts_qs = posts_qs.filter(created_at__date__lte=date_to)

        organizations = list(Organization.objects.filter(is_active=True).order_by("name").values("id", "name"))

    paginator = Paginator(posts_qs, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "posts": page_obj,
        "search_query": search,
        "org_filter": org_filter,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "date_from": date_from,
        "date_to": date_to,
        "organizations": organizations,
        "role_choices": ProfileRole.CHOICES,
        "total_count": paginator.count,
    }
    return render(request, "accounts/superadmin_post_management.html", context)


@login_required
@require_POST
def superadmin_delete_post(request, post_id):
    """Superadmin deletes a post with required reason, notifies user, audit logs."""
    if not is_superadmin_user(request.user):
        raise PermissionDenied

    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse(
                {"success": False, "error": "Silinmə səbəbi yazılmalıdır."},
                status=400,
            )
        messages.error(request, "Silinmə səbəbi yazılmalıdır.")
        return redirect("accounts:superadmin_post_management")

    with bypass_rls():
        post = get_object_or_404(Post.objects.select_related("author"), pk=post_id)

    post_title = post.title
    post_author = post.author

    log_action(
        action=AuditAction.DELETE,
        user=request.user,
        obj=post,
        reason=f"Superadmin post deletion: {reason}",
        request=request,
        resource_type="Post",
        resource_id=str(post.pk),
        resource_repr=post_title,
    )

    try:
        create_notification(
            recipient=post_author,
            title=f"Postunuz superadmin tərəfindən silindi: {post_title}",
            message=(f'"{post_title}" başlıqlı postunuz superadmin tərəfindən' f" silindi.\nSəbəb: {reason}"),
            link=f"{reverse('accounts:profile')}?section=posts",
            notification_type=NotificationType.SYSTEM,
            metadata={
                "post_title": post_title,
                "reason": reason,
                "deleted_by": "superadmin",
            },
        )
    except Exception:
        logger.exception(
            "Failed to notify author about superadmin post deletion pk=%s",
            post_id,
        )

    try:
        with bypass_rls():
            org_memberships = Membership.objects.filter(user=post_author, is_active=True).select_related("organization")
            for membership in org_memberships:
                org = membership.organization
                admin_memberships = (
                    Membership.objects.filter(
                        organization=org,
                        is_active=True,
                        role__level__gte=80,
                    )
                    .exclude(user=request.user)
                    .select_related("user")
                )
                for admin_m in admin_memberships:
                    create_notification(
                        recipient=admin_m.user,
                        title=("Superadmin tərəfindən post silindi:" f" {post_title}"),
                        message=(
                            f'Təşkilatınızdakı ({org.name}) "{post_title}"'
                            " postu superadmin tərəfindən silindi.\n"
                            f"Səbəb: {reason}"
                        ),
                        link=f"{reverse('accounts:profile')}?section=posts",
                        notification_type=NotificationType.SYSTEM,
                        metadata={
                            "post_title": post_title,
                            "reason": reason,
                            "organization": org.name,
                        },
                    )
    except Exception:
        logger.exception("Failed to notify org admins about post deletion pk=%s", post_id)

    post.delete()

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JsonResponse({"success": True, "message": f'"{post_title}" postu silindi.'})

    messages.success(request, f'"{post_title}" postu superadmin tərəfindən silindi.')
    return redirect("accounts:superadmin_post_management")


@login_required
def org_post_management(request):
    """Org owner/admin page to view and moderate all posts within their org."""
    user = request.user
    user_level = get_user_role_level(user)
    if user_level < ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80) and not is_superadmin_user(user):
        raise PermissionDenied

    with bypass_rls():
        membership = (
            Membership.objects.filter(user=user, is_active=True, role__level__gte=80)
            .select_related("organization")
            .first()
        )

    if not membership:
        raise PermissionDenied

    org = membership.organization

    search = (request.GET.get("q") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    with bypass_rls():
        org_user_ids = Membership.objects.filter(organization=org, is_active=True).values_list("user_id", flat=True)

        posts_qs = (
            Post.objects.filter(author_id__in=org_user_ids)
            .select_related(
                "author",
                "author__profile",
                "category",
            )
            .order_by("-created_at")
        )

        if search:
            posts_qs = posts_qs.filter(
                Q(title__icontains=search)
                | Q(content__icontains=search)
                | Q(author__username__icontains=search)
                | Q(author__first_name__icontains=search)
                | Q(author__last_name__icontains=search)
            )

        if role_filter:
            role_user_ids = UserProfile.objects.filter(role=role_filter).values_list("user_id", flat=True)
            posts_qs = posts_qs.filter(author_id__in=role_user_ids)

        if status_filter == "published":
            posts_qs = posts_qs.filter(is_published=True)
        elif status_filter == "draft":
            posts_qs = posts_qs.filter(is_published=False, requires_approval=False)
        elif status_filter == "pending":
            posts_qs = posts_qs.filter(requires_approval=True, approval_status="pending")
        elif status_filter == "needs_changes":
            posts_qs = posts_qs.filter(requires_approval=True, approval_status="needs_changes")

        if date_from:
            posts_qs = posts_qs.filter(created_at__date__gte=date_from)
        if date_to:
            posts_qs = posts_qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(posts_qs, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "posts": page_obj,
        "organization": org,
        "search_query": search,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "date_from": date_from,
        "date_to": date_to,
        "role_choices": ProfileRole.CHOICES,
        "total_count": paginator.count,
    }
    return render(request, "accounts/org_post_management.html", context)


@login_required
@require_POST
def org_moderate_post(request, post_id):
    """Org admin/owner moderates a post: delete with reason, or request changes."""
    user = request.user
    user_level = get_user_role_level(user)
    if user_level < ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80) and not is_superadmin_user(user):
        raise PermissionDenied

    action = (request.POST.get("action") or "").strip().lower()
    feedback = (request.POST.get("feedback") or "").strip()

    with bypass_rls():
        post = get_object_or_404(Post.objects.select_related("author"), pk=post_id)

        admin_membership = (
            Membership.objects.filter(user=user, is_active=True, role__level__gte=80)
            .select_related("organization")
            .first()
        )

    if not admin_membership:
        raise PermissionDenied

    org = admin_membership.organization

    with bypass_rls():
        author_in_org = Membership.objects.filter(user=post.author, organization=org, is_active=True).exists()

    if not author_in_org and not is_superadmin_user(user):
        raise PermissionDenied("Bu post sizin təşkilatınıza aid deyil.")

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if action == "delete":
        if not feedback:
            if is_ajax:
                return JsonResponse(
                    {"success": False, "error": "Silinmə səbəbi yazılmalıdır."},
                    status=400,
                )
            messages.error(request, "Silinmə səbəbi yazılmalıdır.")
            return redirect("accounts:org_post_management")

        post_title = post.title

        log_action(
            action=AuditAction.DELETE,
            user=user,
            organization=org,
            obj=post,
            reason=f"Org admin post deletion: {feedback}",
            request=request,
            resource_type="Post",
            resource_id=str(post.pk),
            resource_repr=post_title,
        )

        try:
            create_notification(
                recipient=post.author,
                title=f"Postunuz silindi: {post_title}",
                message=(
                    f'"{post_title}" başlıqlı postunuz təşkilat admini' f" tərəfindən silindi.\nSəbəb: {feedback}"
                ),
                link=f"{reverse('accounts:profile')}?section=posts",
                notification_type=NotificationType.APPROVAL,
                metadata={
                    "post_title": post_title,
                    "reason": feedback,
                    "organization": org.name,
                },
            )
        except Exception:
            logger.exception(
                "Failed to notify author about org admin post deletion pk=%s",
                post_id,
            )

        post.delete()

        if is_ajax:
            return JsonResponse({"success": True, "message": f'"{post_title}" postu silindi.'})
        messages.success(request, f'"{post_title}" postu silindi.')
        return redirect("accounts:org_post_management")

    elif action == "request_changes":
        if not feedback:
            if is_ajax:
                return JsonResponse(
                    {"success": False, "error": "Feedback yazılmalıdır."},
                    status=400,
                )
            messages.error(request, "Feedback yazılmalıdır.")
            return redirect("accounts:org_post_management")

        post.approval_status = Post.ApprovalStatus.NEEDS_CHANGES
        post.requires_approval = True
        post.is_published = False
        post.save(
            update_fields=[
                "approval_status",
                "requires_approval",
                "is_published",
                "updated_at",
            ]
        )

        PostApprovalLog.objects.create(
            post=post,
            reviewer=user,
            action=PostApprovalLog.Action.NEEDS_CHANGES,
            feedback=feedback,
        )

        try:
            create_notification(
                recipient=post.author,
                title=f"Postunuzda düzəliş tələb olunur: {post.title}",
                message=(f'"{post.title}" başlıqlı postunuzda düzəliş tələb' f" olunur.\nFeedback: {feedback}"),
                link=f"{reverse('accounts:profile')}?section=posts",
                notification_type=NotificationType.APPROVAL,
                metadata={
                    "post_id": post.pk,
                    "feedback": feedback,
                    "organization": org.name,
                },
            )
        except Exception:
            logger.exception("Failed to notify author about feedback pk=%s", post_id)

        if is_ajax:
            return JsonResponse({"success": True, "message": "Feedback göndərildi."})
        messages.success(request, "Feedback göndərildi.")
        return redirect("accounts:org_post_management")

    if is_ajax:
        return JsonResponse({"success": False, "error": "Yanlış əməliyyat."}, status=400)
    messages.error(request, "Yanlış əməliyyat.")
    return redirect("accounts:org_post_management")
