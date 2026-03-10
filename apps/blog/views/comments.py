# blog/views/comments.py

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from ..forms import CommentForm
from ..models import Comment, Post
from ..services import can_user_review_post


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
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

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

            return redirect("article_detail", slug=post.slug)
    else:
        form = CommentForm()

    context = {
        "post": post,
        "comments": comments,
        "comment_form": form,
        "user_first_comment": user_first_comment,
    }
    return render(request, "blog/postDetail.html", context)
