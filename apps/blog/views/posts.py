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
from ..selectors import get_post_category_tree
from ..services import author_requires_post_approval, can_user_review_post, resolve_post_category_selection

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

    if request.method == "POST":
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
            "post_category_tree": get_post_category_tree(),
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


# 3. MÜƏLLIM MODERASIYA: sil, deaktiv et, və ya yenidən aktiv et
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

    if not can_user_review_post(request.user, post):
        raise PermissionDenied("Bu postu idarə etmək üçün icazəniz yoxdur.")

    action = (request.POST.get("action") or "").strip().lower()
    feedback = (request.POST.get("feedback") or "").strip()

    if action not in {"delete", "deactivate", "reactivate"}:
        messages.error(request, "Yanlış əməliyyat seçildi.")
        return redirect(f"{reverse('accounts:profile')}?section=pending-post-approvals")

    # Feedback is mandatory for delete and deactivate so the student knows the reason.
    if action in {"delete", "deactivate"} and not feedback:
        messages.error(request, "Zəhmət olmasa əməliyyatın səbəbini yazın.")
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse({"success": False, "error": "Zəhmət olmasa əməliyyatın səbəbini yazın."}, status=400)
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
            from apps.notifications.services import create_notification

            create_notification(
                recipient=post_author,
                title=f"Postunuz silindi: {post_title}",
                message=(
                    f'"{post_title}" başlıqlı postunuz müəllim tərəfindən silindi. '
                    f"Səbəb: {feedback}"
                ),
                link=f"{reverse('accounts:profile')}?section=posts",
                notification_type=NotificationType.APPROVAL,
                metadata={"post_title": post_title, "feedback": feedback},
            )
        except Exception:
            logger.exception("Failed to notify author about post deletion title=%s", post_title)

        post.delete()
        messages.success(request, f'"{post_title}" postu silindi.')

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse({"success": True, "message": f'"{post_title}" postu silindi.'})

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
            from apps.notifications.services import create_notification

            create_notification(
                recipient=post.author,
                title=f"Postunuz yenidən aktiv edildi: {post.title}",
                message=f'"{post.title}" başlıqlı postunuz müəllim tərəfindən yenidən paylaşıldı.',
                link=f"/articles/{post.slug}/",
                notification_type=NotificationType.APPROVAL,
                metadata={"post_id": post.pk},
            )
        except Exception:
            logger.exception("Failed to notify author about post reactivation pk=%s", post.pk)

        messages.success(request, f'"{post.title}" postu yenidən aktiv edildi və paylaşıldı.')

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "message": f'"{post.title}" postu aktiv edildi.',
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
        from apps.notifications.services import create_notification

        create_notification(
            recipient=post.author,
            title=f"Postunuz deaktiv edildi: {post.title}",
            message=(
                f'"{post.title}" başlıqlı postunuz müəllim tərəfindən gizlədildi. '
                f"Post silinməyib — düzəlişlər edib yenidən göndərə bilərsiniz. "
                f"Müəllim rəyi: {feedback}"
            ),
            link=f"{reverse('accounts:profile')}?section=posts",
            notification_type=NotificationType.APPROVAL,
            metadata={"post_id": post.pk, "feedback": feedback},
        )
    except Exception:
        logger.exception("Failed to notify author about post deactivation pk=%s", post.pk)

    messages.info(
        request,
        f'"{post.title}" postu deaktiv edildi. Post gizlədilib, lakin silinməyib — '
        f"tələbə düzəliş edib yenidən göndərə bilər.",
    )

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return JsonResponse(
            {
                "success": True,
                "message": f'"{post.title}" postu deaktiv edildi.',
                "is_published": post.is_published,
            }
        )

    return _redirect_next()


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
