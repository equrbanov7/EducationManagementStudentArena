# blog/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required

from .models import Post, Category, Comment
from .forms import (
    SubscriptionForm,
    RegisterForm,
    PostForm,
    CommentForm,
)


# ------------------- ƏSAS SƏHİFƏLƏR ------------------- #

def home(request):
    """
    Ana səhifə – ən son postları göstərir
    """
    posts = (
        Post.objects
        .select_related("category", "author")
        .order_by("-created_at")
    )
    return render(request, "blog/home.html", {"posts": posts})


def about(request):
    return render(request, "blog/about.html")


def technology(request):
    """
    Texnologiya kateqoriyasına aid postlar.
    Category modelində 'technology' slug-u varsa ona görə filter edirik.
    Yoxdursa, sadəcə hamını qaytaracaq.
    """
    tech_posts = (
        Post.objects
        .filter(category__slug="technology")  # əgər slug yoxdur, bunu dəyişə bilərik
        .select_related("category", "author")
        .order_by("-created_at")
    )
    return render(request, "blog/technology.html", {"posts": tech_posts})


def contact(request):
    return HttpResponse("Contact Us Page (demo)")


# ------------------- POST DETAY + COMMENT ------------------- #

def post_detail(request, slug):
    """
    Bir postun detal səhifəsi + şərhlər və rating forması.
    Rating yalnız ilk şərhdə nəzərə alınır.
    """
    post = get_object_or_404(Post, slug=slug, is_published=True)

    comments = (
        post.comments
        .select_related("user")
        .order_by("-created_at")
    )

    # Bu user bu post üçün əvvəldən hər hansı şərh yazıb?
    user_first_comment = None
    if request.user.is_authenticated:
        user_first_comment = Comment.objects.filter(
            post=post,
            user=request.user
        ).order_by("created_at").first()

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Şərh yazmaq üçün əvvəlcə daxil olun.")
            return redirect("login")

        form = CommentForm(request.POST)

        if form.is_valid():
            if user_first_comment is None:
                # ✅ İlk dəfə şərh yazır → həm text, həm rating götürürük
                comment = form.save(commit=False)
                comment.post = post
                comment.user = request.user
                comment.save()
                messages.success(request, "Şərhiniz və qiymətləndirməniz əlavə olundu. ⭐")
            else:
                # ✅ Artıq bu posta şərhi var → YENİ şərh yazsın, amma rating DƏYİŞMƏSİN
                comment = Comment(
                    post=post,
                    user=request.user,
                    text=form.cleaned_data["text"],
                    rating=user_first_comment.rating  # rating-i köhnədən götürürük
                )
                comment.save()
                messages.success(request, "Yeni şərhiniz əlavə olundu, rating dəyişdirilmədi. 🙂")

            return redirect("post_detail", slug=post.slug)
    else:
        form = CommentForm()

    context = {
        "post": post,
        "comments": comments,
        "comment_form": form,
        "user_first_comment": user_first_comment,  # template-də istifadə edərsən
    }
    return render(request, "blog/postDetail.html", context)


# ------------------- SUBSCRIBE ------------------- #

def subscribe_page(request):
    """
    Email ilə abunə formu.
    Hələlik yalnız mesaj göstəririk, real DB/API hissəsini sonra əlavə edərik.
    """
    if request.method == "POST":
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            # Burada real DB yazmaq və ya Mailchimp API çağırmaq olar:
            # Subscriber.objects.create(email=email)

            messages.success(
                request,
                f"{email} ünvanı uğurla abunə oldu! Təşəkkürlər."
            )
            return redirect("subscribe")
        else:
            messages.error(request, "Zəhmət olmasa düzgün email ünvanı daxil edin.")
    else:
        form = SubscriptionForm()

    return render(request, "blog/subscribe.html", {"form": form})


# ------------------- POST CRUD ------------------- #

from django.utils.text import slugify
from .models import Post

@login_required
def create_post(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user

            base_slug = slugify(post.title)
            slug = base_slug
            counter = 1 

            while Post.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            post.slug = slug

            post.save()
            messages.success(request, "Post uğurla yaradıldı.")
            return redirect("post_detail", slug=post.slug)
    else:
        form = PostForm()

    return render(request, "post_form.html", {"form": form})





@login_required
def edit_post(request, post_id):
    """
    Postu redaktə etmək.
    Yalnız həmin postun müəllifi redaktə edə bilər.
    """
    post = get_object_or_404(Post, pk=post_id, author=request.user)

    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Post yeniləndi.")
            return redirect("post_detail", post_id=post.id)
    else:
        form = PostForm(instance=post)

    context = {
        "form": form,
        "post": post,
        "is_edit": True,
    }
    return render(request, "blog/post_form.html", context)


@login_required
def delete_post(request, post_id):
    """
    Postu silmək – sadə variant.
    Confirmation üçün ayrıca template istifadə edə bilərik.
    """
    post = get_object_or_404(Post, pk=post_id, author=request.user)

    if request.method == "POST":
        post.delete()
        messages.success(request, "Post silindi.")
        return redirect("home")

    return render(request, "blog/post_confirm_delete.html", {"post": post})


def list_posts(request):
    """
    Bütün postların siyahısı (əgər ayrıca page istəyirsənsə).
    """
    posts = (
        Post.objects
        .select_related("category", "author")
        .order_by("-created_at")
    )
    return render(request, "blog/post_list.html", {"posts": posts})


def search_posts(request):
    """
    Sadə search: ?q=... ilə title və excerpt-də axtarır.
    """
    query = request.GET.get("q", "").strip()
    posts = Post.objects.all()

    if query:
        posts = posts.filter(
            title__icontains=query
        ) | posts.filter(
            excerpt__icontains=query
        )

    posts = posts.order_by("-created_at")

    return render(request, "blog/search_results.html", {
        "posts": posts,
        "query": query,
    })


# ------------------- USER REGISTER / PROFILE / LOGOUT ------------------- #

def register_view(request):
    """
    Yeni istifadəçi qeydiyyatı.
    Qeydiyyat uğurlu olduqda user-i login edib onun profil səhifəsinə yönləndiririk.
    """
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data["password"]
            user.set_password(password)  # şifrəni hash-lə saxla
            user.save()
            login(request, user)        # qeydiyyatdan sonra avtomatik login
            return redirect("user_profile", username=user.username)
    else:
        form = RegisterForm()

    return render(request, "blog/register.html", {"form": form})


def user_profile(request, username):
    """
    İstifadəçi profili – həmin user-in yazdığı postlar.
    Məsələn: /blog/users/elvin/
    """
    profile_user = get_object_or_404(User, username=username)
    user_posts = (
        Post.objects
        .filter(author=profile_user)
        .select_related("category")
        .order_by("-created_at")
    )

    context = {
        "profile_user": profile_user,
        "posts": user_posts,
    }
    return render(request, "blog/user_profile.html", context)


def logout_view(request):
    """
    İstifadəçini çıxış etdirib ana səhifəyə yönləndirir.
    """
    logout(request)
    return redirect("home")
