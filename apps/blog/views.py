# blog/views.py

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file

from .forms import CommentForm, PostForm, QuestionForm, RegisterForm, SubscriptionForm
from .models import Category, Comment, EmailOTP, Post, PostApprovalLog, Question, Subscriber
from .services import author_requires_post_approval, can_user_review_post
from .utils import generate_otp, send_verify_email

User = get_user_model()
signer = TimestampSigner()
logger = logging.getLogger(__name__)


def _can_manage_blog_content(user):
    """
    Any authenticated user can create and manage their own posts.
    """
    return getattr(user, "is_authenticated", False)


# ------------------- ƏSAS SƏHİFƏLƏR ------------------- #


def home(request):

    query = request.GET.get("q", "").strip()
    post_list = Post.objects.filter(is_published=True).select_related("category", "author").order_by("-created_at")

    if query:
        post_list = post_list.filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(content__icontains=query)
        ).distinct()

    paginator = Paginator(post_list, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    categories = (
        Category.objects.annotate(post_count=Count("posts", filter=Q(posts__is_published=True)))
        .filter(post_count__gt=0)
        .order_by("name")
    )

    context = {
        "page_obj": page_obj,
        "categories": categories,
        "search_query": query,
        "query": query,  # Also pass as 'query' for template compatibility
    }

    return render(request, "blog/home.html", context)


def about(request):
    return render(request, "blog/about.html")


def technology(request):

    TECH_CATEGORIES = [
        "proqramlasdirma",
        "suni-intellekt",
        "python",
        "django",
        "texnologiya",
        "backend",
    ]

    post_list = (
        Post.objects.filter(category__slug__in=TECH_CATEGORIES)
        .select_related("category", "author")
        .order_by("-created_at")
    )

    paginator = Paginator(post_list, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blog/technology.html", {"page_obj": page_obj})


def contact(request):
    return HttpResponse("Contact Us Page (demo)")


# ------------------- POST DETAY + COMMENT ------------------- #


def post_detail(request, slug):
    """
    Bir postun detal səhifəsi + şərhlər və rating forması.
    Rating yalnız ilk şərhdə nəzərə alınır.
    """
    # 1) Postu statusdan asılı olmayaraq tap
    post = get_object_or_404(Post, slug=slug)

    # 2) Əgər post nəşr olunmayıbsa, yalnız müəllif və ya uyğun reviewer görə bilsin.
    if not post.is_published and request.user != post.author and not can_user_review_post(request.user, post):
        raise Http404("No Post matches the given query.")

    comments = post.comments.select_related("user").order_by("-created_at")

    user_first_comment = None
    if request.user.is_authenticated:
        user_first_comment = Comment.objects.filter(post=post, user=request.user).order_by("created_at").first()

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, pgettext("blog.post_detail.message", "login_required"))
            return redirect("login")

        form = CommentForm(request.POST)

        if form.is_valid():
            if user_first_comment is None:
                # İlk dəfə şərh yazır → həm text, həm rating götürürük
                comment = form.save(commit=False)
                comment.post = post
                comment.user = request.user
                comment.save()
                messages.success(request, pgettext("blog.post_detail.message", "comment_added_with_rating"))
            else:
                # Artıq bu posta şərhi var → yeni şərh, eyni rating
                comment = Comment(
                    post=post,
                    user=request.user,
                    text=form.cleaned_data["text"],
                    rating=user_first_comment.rating,
                )
                comment.save()
                messages.success(request, pgettext("blog.post_detail.message", "comment_added_without_rating"))

            return redirect("post_detail", slug=post.slug)
    else:
        form = CommentForm()

    context = {
        "post": post,
        "comments": comments,
        "comment_form": form,
        "user_first_comment": user_first_comment,
    }
    return render(request, "blog/postDetail.html", context)


# ------------------- SUBSCRIBE ------------------- #


def subscribe_page(request):
    if request.method == "POST":
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            try:
                # 1. Abunəçini bazaya yaz
                subscriber, created = Subscriber.objects.get_or_create(email=email)

                if created or not subscriber.is_active:

                    # 2. Email şablonunu yarat
                    html_message = render_to_string("email_templates/welcome_email.html", {"email": email})

                    # 3. Email göndər
                    send_mail(
                        pgettext("blog.subscribe.email", "subject"),
                        pgettext("blog.subscribe.email", "plain_text_body").format(email=email),
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        html_message=html_message,
                        fail_silently=False,
                    )

                    messages.success(
                        request,
                        pgettext("blog.subscribe.message", "confirmation_email_sent").format(email=email),
                    )

                else:
                    messages.warning(
                        request, pgettext("blog.subscribe.message", "already_subscribed").format(email=email)
                    )

            except Exception:
                # Hər hansı bir xəta (məsələn, SMTP xətası) olarsa
                messages.error(
                    request,
                    pgettext("blog.subscribe.message", "send_error"),
                )
                logger.exception("Subscription email delivery failed")

            return redirect("subscribe")
        else:
            messages.error(request, pgettext("blog.subscribe.message", "invalid_email"))
    else:
        form = SubscriptionForm()

    return render(request, "blog/subscribe.html", {"form": form})


# ------------------- POST CRUD ------------------- #


@login_required
def create_post(request):
    if not _can_manage_blog_content(request.user):
        raise PermissionDenied(pgettext("blog.permission", "no_permission"))

    requires_approval = author_requires_post_approval(request.user)

    if request.method == "POST":
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        form = PostForm(request.POST, request.FILES)
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
            return redirect("post_detail", slug=post.slug)
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
        form = PostForm()

    return render(
        request,
        "post_form.html",
        {
            "form": form,
            "requires_approval": requires_approval,
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


# ------------------- USER REGISTER / PROFILE / LOGOUT ------------------- #


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # password set
            password = form.cleaned_data["password"]
            user.set_password(password)

            # email təsdiqlənənə qədər giriş qadağan
            user.is_active = False
            user.save()

            code = generate_otp()
            EmailOTP.objects.create(
                user=user,
                code=code,
                expires_at=timezone.now() + timezone.timedelta(minutes=10),
            )
            send_verify_email(user, code)

            request.session["pending_verify_email"] = user.email
            messages.success(request, pgettext("blog.verify.message", "code_sent"))
            return redirect("verify_code")
    else:
        form = RegisterForm()

    return render(request, "blog/register.html", {"form": form})


def verify_code_view(request):
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext("blog.verify.message", "pending_email_missing"))
        return redirect("register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, pgettext("blog.verify.message", "user_not_found"))
            return redirect("register")

        otp = EmailOTP.objects.filter(user=user, code=code, is_used=False).order_by("-created_at").first()
        if not otp or otp.is_expired():
            messages.error(request, pgettext("blog.verify.message", "invalid_or_expired_code"))
            return render(request, "blog/verify_code.html", {"email": email})

        otp.is_used = True
        otp.save()

        user.is_active = True
        user.save()

        messages.success(request, pgettext("blog.verify.message", "email_verified"))
        return redirect("login")

    return render(request, "blog/verify_code.html", {"email": email})


def verify_email_link_view(request):
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=60 * 10)  # 10 dəqiqə
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save()
        messages.success(request, pgettext("blog.verify.message", "email_verified"))
        return redirect("login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, pgettext("blog.verify.message", "invalid_or_expired_link"))
        return redirect("register")


def resend_code_view(request):
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext("blog.verify.message", "email_missing"))
        return redirect("register")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, pgettext("blog.verify.message", "user_not_found"))
        return redirect("register")

    code = generate_otp()
    EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timezone.timedelta(minutes=10))
    send_verify_email(user, code)

    messages.success(request, pgettext("blog.verify.message", "new_code_sent"))
    return redirect("verify_code")


def user_profile(request, username):
    """
    Legacy route redirect:
    - Own profile -> accounts profile
    - Other users -> accounts public profile
    """
    if request.user.is_authenticated and request.user.username == username:
        target_url = reverse("accounts:profile")
    else:
        # Keep existing 404 behavior when username does not exist.
        profile_user = get_object_or_404(User, username=username)
        target_url = reverse("accounts:public_profile", kwargs={"username": profile_user.username})

    query_string = request.GET.urlencode()
    if query_string:
        target_url = f"{target_url}?{query_string}"

    return redirect(target_url)


def logout_view(request):
    """
    İstifadəçini çıxış etdirib ana səhifəyə yönləndirir.
    """
    logout(request)
    return redirect("home")


# ------------------- CATEGORY DETAIL ------------------- #


def category_detail(request, slug):
    # 1. Hazırkı seçilmiş kateqoriyanı tapırıq (yoxdursa 404 qaytarır)
    category = get_object_or_404(Category, slug=slug)

    # 2. YALNIZ bu kateqoriyaya aid olan və yayımlanmış postları tapırıq
    posts = Post.objects.filter(category=category, is_published=True).order_by("-created_at")

    # 3. Sidebar üçün bütün kateqoriyaları və post saylarını hesablayırıq (Home view-dakı kimi)
    categories = (
        Category.objects.annotate(post_count=Count("posts", filter=Q(posts__is_published=True)))
        .filter(post_count__gt=0)
        .order_by("name")
    )

    context = {
        "category": category,  # Başlıqda adını yazmaq üçün
        "posts": posts,  # Süzülmüş postlar
        "categories": categories,  # Sidebar üçün siyahı
    }

    return render(request, "blog/category_detail.html", context)


# ------------------- QUESTION SUBMISSION ------------------- #


@login_required
def create_question(request):
    # Yalnız teacher qrupu olanlar sual yarada bilsin
    if not request.user.is_teacher_or_above:
        raise PermissionDenied(pgettext("blog.permission", "teacher_only"))

    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.author = request.user
            question.save()
            form.save_m2m()  # visible_users üçün lazımdır
            return redirect("my_questions")
    else:
        form = QuestionForm()

    return render(request, "blog/create_question.html", {"form": form})


@login_required
def my_questions(request):
    """
    Bu view müəllimin öz yaratdığı sualları göstərir.
    """
    questions = Question.objects.filter(author=request.user).order_by("-created_at")
    return render(request, "blog/my_questions.html", {"questions": questions})


@login_required
def questions_i_can_see(request):
    """
    Bu view login olan user-in görə bildiyi bütün sualları göstərir.
    visible_to_all = True olanlar,
    + author = user olanlar,
    + visible_users siyahısında user olanlar.
    """

    questions = (
        Question.objects.filter(Q(visible_to_all=True) | Q(author=request.user) | Q(visible_users=request.user))
        .distinct()
        .select_related("author")
    )

    return render(request, "blog/questions_i_can_see.html", {"questions": questions})
