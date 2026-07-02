# blog/views/questions.py

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.translation import pgettext

from ...forms import QuestionForm
from ...models import Question


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
