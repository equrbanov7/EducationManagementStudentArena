# blog/views/questions.py

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
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
        form = QuestionForm(request.POST, organization=getattr(request, "organization", None))
        if form.is_valid():
            # Audit 2026-09-13 backend F-07 (2026-09-14): sual + `visible_users` M2M birlikdə.
            with transaction.atomic():
                question = form.save(commit=False)
                question.author = request.user
                # Təhlükəsizlik auditi 2026-10-05: sual aktiv təşkilata bağlanır —
                # ``visible_to_all`` yalnız bu təşkilatın üzvlərinə şamil olur.
                question.organization = getattr(request, "organization", None)
                question.save()
                form.save_m2m()  # visible_users üçün lazımdır
            return redirect("my_questions")
    else:
        form = QuestionForm(organization=getattr(request, "organization", None))

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
    Bu view login olan user-in AKTİV TƏŞKİLATDA görə bildiyi sualları göstərir:
    həmin təşkilatın visible_to_all / öz / visible_users sualları + təşkilatsız
    köhnə sətirlər yalnız müəllifinə (və superadmin-ə).
    """

    questions = (
        Question.objects.filter(Question.visible_q(request.user, getattr(request, "organization", None)))
        .distinct()
        .select_related("author")
    )

    return render(request, "blog/questions_i_can_see.html", {"questions": questions})
