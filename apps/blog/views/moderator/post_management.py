"""Post management views for superadmin and organization owner/admin.

M2 (2026-07-02): apps/accounts/views/post_management.py-dən köçürülüb —
accounts→blog import kənarını kəsir. accounts tərəfdəki eyniadlı shim modul
bu view-ları profile_hooks registry-si üzərindən çağırır (URL-lər və
`accounts.views` fasad səthi DƏYİŞMƏYİB)."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.accounts.models import UserProfile
from apps.audit.public import log_action
from apps.blog.models import Post, PostApprovalLog
from apps.notifications.models import NotificationType
from apps.notifications.public import create_notification
from apps.organizations.models import Membership, Organization
from core.constants import AuditAction
from core.rate_limit import is_rate_limited, record_rate_limit_hit
from core.rls import bypass_rls
from core.roles import ProfileRole, get_user_role_level, is_superadmin_user
from core.utils import get_client_ip

logger = logging.getLogger(__name__)
User = get_user_model()

POSTS_PER_PAGE = 20

# Role names that grant org-level post moderation access.
# Uses the canonical set from ProfileRole rather than a numeric level threshold,
# so new high-level roles without moderation intent are excluded by default.
_ORG_MODERATOR_ROLE_NAMES = frozenset(ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES)


def _check_post_delete_rate_limit(request):
    """Return a 429 JsonResponse if the user exceeds POST_DELETE_RATE_LIMIT, else None."""
    rate = getattr(settings, "POST_DELETE_RATE_LIMIT", None)
    if not rate:
        return None
    ip = get_client_ip(request)
    user_id = request.user.pk
    limited, retry_after = is_rate_limited("post_delete", rate, user_id, ip)
    if limited:
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        msg = pgettext(
            "post_management.rate_limit",
            "too_many_delete_requests",
        )
        if is_ajax:
            resp = JsonResponse({"success": False, "error": msg}, status=429)
            if retry_after:
                resp["Retry-After"] = str(retry_after)
            return resp
        messages.error(request, msg)
        return None  # non-ajax path continues to redirect anyway
    return None


def _record_post_delete_hit(request):
    """Record a successful delete hit for rate limiting."""
    rate = getattr(settings, "POST_DELETE_RATE_LIMIT", None)
    if rate:
        ip = get_client_ip(request)
        record_rate_limit_hit("post_delete", rate, request.user.pk, ip)


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
    return render(request, "blog/superadmin_post_management.html", context)


@login_required
@require_POST
def superadmin_delete_post(request, post_id):
    """Superadmin deletes a post with required reason, notifies user, audit logs."""
    if not is_superadmin_user(request.user):
        raise PermissionDenied

    rate_resp = _check_post_delete_rate_limit(request)
    if rate_resp:
        return rate_resp

    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        msg = pgettext("post_management.error", "delete_reason_required")
        if is_ajax:
            return JsonResponse(
                {"success": False, "error": msg},
                status=400,
            )
        messages.error(request, msg)
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
            title=pgettext(
                "post_management.notification",
                "superadmin_deleted_post_title",
            ).format(title=post_title),
            message=pgettext(
                "post_management.notification",
                "superadmin_deleted_post_body",
            ).format(title=post_title, reason=reason),
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
                        role__name__in=_ORG_MODERATOR_ROLE_NAMES,
                    )
                    .exclude(user=request.user)
                    .select_related("user")
                )
                for admin_m in admin_memberships:
                    create_notification(
                        recipient=admin_m.user,
                        title=pgettext(
                            "post_management.notification",
                            "superadmin_deleted_org_post_title",
                        ).format(title=post_title),
                        message=pgettext(
                            "post_management.notification",
                            "superadmin_deleted_org_post_body",
                        ).format(org_name=org.name, title=post_title, reason=reason),
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
    _record_post_delete_hit(request)

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    msg = pgettext("post_management.success", "post_deleted").format(title=post_title)
    if is_ajax:
        return JsonResponse({"success": True, "message": msg})

    messages.success(request, msg)
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
            Membership.objects.filter(
                user=user,
                is_active=True,
                role__name__in=_ORG_MODERATOR_ROLE_NAMES,
            )
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
    return render(request, "blog/org_post_management.html", context)


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
            Membership.objects.filter(
                user=user,
                is_active=True,
                role__name__in=_ORG_MODERATOR_ROLE_NAMES,
            )
            .select_related("organization")
            .first()
        )

    if not admin_membership:
        raise PermissionDenied

    org = admin_membership.organization

    with bypass_rls():
        author_in_org = Membership.objects.filter(user=post.author, organization=org, is_active=True).exists()

    if not author_in_org and not is_superadmin_user(user):
        raise PermissionDenied(
            pgettext("post_management.error", "post_not_in_your_org"),
        )

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if action == "delete":
        rate_resp = _check_post_delete_rate_limit(request)
        if rate_resp:
            return rate_resp

        if not feedback:
            msg = pgettext("post_management.error", "delete_reason_required")
            if is_ajax:
                return JsonResponse(
                    {"success": False, "error": msg},
                    status=400,
                )
            messages.error(request, msg)
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
                title=pgettext(
                    "post_management.notification",
                    "org_admin_deleted_post_title",
                ).format(title=post_title),
                message=pgettext(
                    "post_management.notification",
                    "org_admin_deleted_post_body",
                ).format(title=post_title, reason=feedback),
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
        _record_post_delete_hit(request)

        msg = pgettext("post_management.success", "post_deleted").format(title=post_title)
        if is_ajax:
            return JsonResponse({"success": True, "message": msg})
        messages.success(request, msg)
        return redirect("accounts:org_post_management")

    elif action == "request_changes":
        if not feedback:
            msg = pgettext("post_management.error", "feedback_required")
            if is_ajax:
                return JsonResponse(
                    {"success": False, "error": msg},
                    status=400,
                )
            messages.error(request, msg)
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
                title=pgettext(
                    "post_management.notification",
                    "changes_requested_title",
                ).format(title=post.title),
                message=pgettext(
                    "post_management.notification",
                    "changes_requested_body",
                ).format(title=post.title, feedback=feedback),
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

        msg = pgettext("post_management.success", "feedback_sent")
        if is_ajax:
            return JsonResponse({"success": True, "message": msg})
        messages.success(request, msg)
        return redirect("accounts:org_post_management")

    msg = pgettext("post_management.error", "invalid_action")
    if is_ajax:
        return JsonResponse({"success": False, "error": msg}, status=400)
    messages.error(request, msg)
    return redirect("accounts:org_post_management")
