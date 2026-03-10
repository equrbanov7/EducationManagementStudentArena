# blog/views/posts.py

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file

from ..forms import PostForm
from ..models import Category, Post, PostApprovalLog
from ..services import author_requires_post_approval, can_user_create_post_category, can_user_review_post

logger = logging.getLogger(__name__)


def _can_manage_blog_content(user):
    """
    Any authenticated user can create and manage their own posts.
    """
    return getattr(user, "is_authenticated", False)


@login_required
def create_post(request):
    if not _can_manage_blog_content(request.user):
        raise PermissionDenied(pgettext("blog.permission", "no_permission"))

    requires_approval = author_requires_post_approval(request.user)
    can_create_categories = can_user_create_post_category(request.user)

    if request.method == "POST":
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        form = PostForm(request.POST, request.FILES, author=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user

            new_cat_name = form.cleaned_data.get("new_category")
            selected_cat = form.cleaned_data.get("category")

            if new_cat_name:

                category, created = Category.objects.get_or_create(name=new_cat_name)
                post.category = category

                if created:
                    messages.info(request, pgettext("blog.post.message", "category_created").format(name=new_cat_name))

            elif selected_cat:
                # 2. Əgər yeni heç nə yazmayıb, sadəcə siyahıdan seçibsə:
                post.category = selected_cat

            else:
                # 3. Heç nə seçməyibsə (istəyə bağlı):
                # post.category = None # (Modeldə null=True olduğu üçün problem yoxdur)
                pass

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
                messages.success(request, "Post yaradıldı və müəllim təsdiqi gözləyir.")
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
            "can_create_categories": can_create_categories,
        },
    )


# 1. POSTU REDAKTƏ ET (AJAX Endpoint)


@login_required
@require_POST
def post_edit_ajax(request, pk):
    if not _can_manage_blog_content(request.user):
        raise PermissionDenied(pgettext("blog.permission", "no_permission"))

    # Yalnız öz postunu düzəldə bilsin
    post = get_object_or_404(Post, pk=pk, author=request.user)

    title = request.POST.get("title", "").strip()
    content = request.POST.get("content", "").strip()
    excerpt = request.POST.get("excerpt", "").strip()
    category_id = request.POST.get("category")  # select name="category"
    image_url = request.POST.get("image_url", "").strip()
    is_published = bool(request.POST.get("is_published"))  # "on" gəlir

    # Sadə validasiya (istəsən form ilə də edə bilərsən)
    if not title or not content:
        return JsonResponse(
            {"success": False, "message": pgettext("blog.post.message", "title_and_content_required")},
            status=400,
        )

    # Məlumatları post-a yaz
    post.title = title
    post.content = content
    post.excerpt = excerpt

    # Kateqoriya
    if category_id:
        try:
            post.category = Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            post.category = None
    else:
        post.category = None

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

    # Save
    post.save()

    return JsonResponse(
        {
            "success": True,
            "status": post.approval_status,
            "is_published": post.is_published,
        }
    )


@login_required
@require_POST
def review_post(request, post_id):
    post = get_object_or_404(Post.objects.select_related("author"), pk=post_id, requires_approval=True)

    if not can_user_review_post(request.user, post):
        raise PermissionDenied("Bu postu təsdiqləmək üçün icazəniz yoxdur.")

    action = (request.POST.get("action") or "").strip().lower()
    feedback = (request.POST.get("feedback") or "").strip()

    if action not in {"approve", "needs_changes"}:
        messages.error(request, "Yanlış əməliyyat seçildi.")
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    if action == "needs_changes" and not feedback:
        messages.error(request, "Düzəliş istəyi üçün feedback yazın.")
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
        messages.success(request, "Post təsdiqləndi və paylaşıldı.")
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
        messages.info(request, "Feedback göndərildi. Post düzəliş gözləyir.")

    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")


# 2. POSTU SİLMƏ (Təsdiqdən sonra)
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


def list_posts(request):
    """
    Bütün postların siyahısı (əgər ayrıca page istəyirsənsə).
    """
    posts = Post.objects.select_related("category", "author").order_by("-created_at")
    return render(request, "blog/post_list.html", {"posts": posts})


def search_posts(request):
    """
    Sadə search: ?q=... ilə title və excerpt-də axtarır.
    """
    query = request.GET.get("q", "").strip()
    posts = Post.objects.all()

    if query:
        posts = posts.filter(title__icontains=query) | posts.filter(excerpt__icontains=query)

    posts = posts.order_by("-created_at")

    return render(
        request,
        "blog/search_results.html",
        {
            "posts": posts,
            "query": query,
        },
    )
