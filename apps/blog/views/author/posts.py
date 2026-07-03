"""Blog — müəllif səthi: post yaratma/redaktə (F7 rol-skeleti, 2026-07-02)."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.audit.public import log_action
from core.constants import AuditAction
from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file

from ...forms import PostForm
from ...models import Category, Post
from ...selectors import get_post_category_tree
from ...services import (
    author_requires_post_approval,
    can_user_moderate_post,
    can_user_publish_post,
    resolve_post_category_selection,
)
from ..shared._helpers import _can_manage_blog_content

logger = logging.getLogger(__name__)


@login_required
def create_post(request):
    if not _can_manage_blog_content(request.user):
        raise PermissionDenied(pgettext("blog.permission", "no_permission"))

    can_publish, blocked_reason = can_user_publish_post(request.user)
    requires_approval = author_requires_post_approval(request.user)

    if request.method == "POST":
        if not can_publish:
            raise PermissionDenied(blocked_reason)

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        form = PostForm(request.POST, request.FILES, author=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user

            if requires_approval:
                post.requires_approval = True
                post.approval_status = Post.ApprovalStatus.PENDING
                post.approval_requested_at = timezone.now()
                post.approval_feedback = ""
                post.is_published = False
            else:
                post.requires_approval = False
                post.approval_status = Post.ApprovalStatus.APPROVED
                post.approval_requested_at = None
                if "is_published" in request.POST:
                    post.is_published = bool(request.POST.get("is_published"))

            # --- SLUG MƏNTİQİ SİLİNDİ ---
            # Sənin Post modelinin save() metodu slug-ı və unikallığı
            # avtomatik həll edir. Burda artıq kod yazmağa ehtiyac yoxdur.

            post.save()

            # Audit trail: record who created the post and whether it went
            # straight to PUBLISHED or into the approval queue. This makes
            # unapproved-content attempts reviewable.
            try:
                log_action(
                    action=AuditAction.CREATE,
                    user=request.user,
                    obj=post,
                    request=request,
                    resource_type="blog.Post",
                    resource_id=str(post.pk),
                    resource_repr=post.title[:200],
                    new_values={
                        "approval_status": post.approval_status,
                        "requires_approval": post.requires_approval,
                        "is_published": post.is_published,
                    },
                )
            except Exception:  # audit must never break the user flow
                logger.exception("Failed to write audit log for blog post creation")

            if is_ajax:
                return JsonResponse(
                    {
                        "success": True,
                        "post_id": post.id,
                        "slug": post.slug,
                        "status": post.approval_status,
                        "is_published": post.is_published,
                    }
                )
            if requires_approval:
                messages.success(request, pgettext("blog.author.message", "Post yaradıldı və təsdiq gözləyir."))
                return redirect(f"{reverse('accounts:profile')}?section=posts")

            messages.success(request, pgettext("blog.post.message", "created"))
            return redirect("article_detail", slug=post.slug)
        if is_ajax:
            errors = {field: [str(error) for error in error_list] for field, error_list in form.errors.items()}
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "message": pgettext("blog.post.message", "form_invalid"),
                },
                status=400,
            )
    else:
        form = PostForm(author=request.user)

    return render(
        request,
        "post_form.html",
        {
            "form": form,
            "requires_approval": requires_approval,
            "posting_blocked": not can_publish,
            "posting_blocked_reason": blocked_reason,
            "post_category_tree": get_post_category_tree(),
        },
    )


# 1. POSTU REDAKTƏ ET (AJAX Endpoint)


@login_required
@require_POST
def post_edit_ajax(request, pk):
    if not _can_manage_blog_content(request.user):
        raise PermissionDenied(pgettext("blog.permission", "no_permission"))

    post = get_object_or_404(Post.objects.select_related("author"), pk=pk)
    is_author_edit = post.author_id == request.user.id
    is_moderator_edit = not is_author_edit and can_user_moderate_post(request.user, post)

    if not is_author_edit and not is_moderator_edit:
        raise Http404

    if is_author_edit:
        can_publish, blocked_reason = can_user_publish_post(request.user)
        if not can_publish:
            return JsonResponse(
                {"success": False, "message": blocked_reason},
                status=403,
            )

    title = request.POST.get("title", "").strip()
    content = request.POST.get("content", "").strip()
    excerpt = request.POST.get("excerpt", "").strip()
    category_id = request.POST.get("category")
    subcategory_id = request.POST.get("subcategory")
    image_url = request.POST.get("image_url", "").strip()
    is_published = bool(request.POST.get("is_published"))  # "on" gəlir
    legacy_new_category = (request.POST.get("new_category") or "").strip()

    # Sadə validasiya (istəsən form ilə də edə bilərsən)
    if not title or not content:
        return JsonResponse(
            {"success": False, "message": pgettext("blog.post.message", "title_and_content_required")},
            status=400,
        )
    if legacy_new_category:
        return JsonResponse(
            {
                "success": False,
                "errors": {"category": ["Categories are managed by SuperAdmin only."]},
                "message": "Categories are managed by SuperAdmin only.",
            },
            status=400,
        )

    # Məlumatları post-a yaz
    post.title = title
    post.content = content
    post.excerpt = excerpt

    selected_root_category = (
        Category.objects.filter(pk=category_id, parent__isnull=True).first() if category_id else None
    )
    selected_subcategory = (
        Category.objects.select_related("parent").filter(pk=subcategory_id, parent__isnull=False).first()
        if subcategory_id
        else None
    )

    try:
        post.category = resolve_post_category_selection(
            category=selected_root_category,
            subcategory=selected_subcategory,
        )
    except ValidationError as exc:
        error_message = ""
        if hasattr(exc, "message_dict"):
            error_message = " ".join(error_list[0] for error_list in exc.message_dict.values() if error_list)
        elif getattr(exc, "messages", None):
            error_message = exc.messages[0]
        return JsonResponse(
            {
                "success": False,
                "errors": getattr(exc, "message_dict", {"category": [error_message or "Invalid category selection."]}),
                "message": error_message or "Invalid category selection.",
            },
            status=400,
        )

    # Şəkil faylı
    image_file = request.FILES.get("image")
    if image_file:
        try:
            validate_uploaded_file(
                image_file,
                allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
                max_size_mb=int(getattr(settings, "FILE_UPLOAD_SECURITY_MAX_SIZE_MB", 25)),
                allowed_mime_types=set(),
                allowed_mime_prefixes=("image/",),
            )
        except ValidationError as exc:
            return JsonResponse({"success": False, "message": exc.messages[0]}, status=400)
        randomize_uploaded_filename(image_file)
        post.image = image_file

    # Şəkil URL
    post.image_url = image_url or None

    if not is_moderator_edit:
        if post.requires_approval or author_requires_post_approval(post.author):
            post.requires_approval = True
            post.approval_status = Post.ApprovalStatus.PENDING
            post.approval_requested_at = timezone.now()
            post.is_published = False
        else:
            post.requires_approval = False
            post.approval_status = Post.ApprovalStatus.APPROVED
            post.approval_requested_at = None
            post.is_published = is_published

    post.save()

    return JsonResponse(
        {
            "success": True,
            "status": post.approval_status,
            "is_published": post.is_published,
        }
    )
