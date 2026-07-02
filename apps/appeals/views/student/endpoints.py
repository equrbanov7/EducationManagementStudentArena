"""Appeals — tələbə səthi: yaratma + siyahı (F4 rol-skeleti, 2026-07-02)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import ExamAttempt
from apps.exams.public import tenant_scoped_exams
from apps.exams.views.student._helpers import ensure_student_exam_tenant_context

from ...constants import APPEAL_MIN_COMMENT_LENGTH, APPEAL_STATUS_CHOICES, APPEAL_STATUS_VALUES, APPEAL_TYPE_CHOICES
from ...selectors import filter_student_appeals, paginate_student_appeals, student_appeals_queryset
from ...services import can_create_appeal, create_appeal, remaining_window_seconds
from ..shared._helpers import _marked_question_map


def _result_url(exam, attempt):
    return reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id})


def _parse_items_from_post(request, delivered_question_ids):
    """
    POST-dan apellyasiya item-lərini çıxarır.

    Hər təqdim olunmuş sual üçün `appeal_q_<id>` checkbox seçilibsə,
    `appeal_type_<id>` və `comment_<id>` toplanır.
    """
    items = []
    for question_id in delivered_question_ids:
        if not request.POST.get(f"appeal_q_{question_id}"):
            continue
        items.append(
            {
                "question_id": question_id,
                "appeal_type": (request.POST.get(f"appeal_type_{question_id}") or "").strip(),
                "comment": (request.POST.get(f"comment_{question_id}") or "").strip(),
            }
        )
    return items


@login_required
def appeal_create(request, attempt_id):
    ensure_student_exam_tenant_context(request)
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__organization"),
        id=attempt_id,
        user=request.user,
    )
    exam = attempt.exam
    if not tenant_scoped_exams(request).filter(id=exam.id).exists():
        raise Http404

    if not can_create_appeal(request, attempt):
        messages.error(
            request,
            pgettext("appeals.view.message", "Apellyasiya müddəti bitib və ya icazəniz yoxdur."),
        )
        return redirect(_result_url(exam, attempt))

    delivered_answers = list(
        attempt.answers.select_related("question")
        .prefetch_related("question__options", "selected_options")
        .order_by("id")
    )
    delivered_question_ids = {answer.question_id for answer in delivered_answers}

    if request.method == "POST":
        items = _parse_items_from_post(request, delivered_question_ids)
        try:
            create_appeal(attempt=attempt, student=request.user, items=items)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request,
                pgettext("appeals.view.message", "Apellyasiyanız qeydə alındı."),
            )
            # Tələbə apellyasiyalarını dashboard bölməsində izləyir.
            return redirect(reverse("accounts:profile") + "?section=my-appeals")

    marked_map = _marked_question_map(attempt)
    has_marked = any(marked_map.get(answer.question_id) for answer in delivered_answers)

    context = {
        "exam": exam,
        "attempt": attempt,
        "answers": delivered_answers,
        "appeal_type_choices": APPEAL_TYPE_CHOICES,
        "min_comment_length": APPEAL_MIN_COMMENT_LENGTH,
        "remaining_seconds": remaining_window_seconds(attempt),
        "result_url": _result_url(exam, attempt),
        "marked_question_by_qid": marked_map,
        "has_marked": has_marked,
    }
    return render(request, "appeals/student/appeal_create.html", context)


def build_my_appeals_context(request, *, list_action, section=""):
    """
    Ortaq apellyasiya siyahısı konteksti (DRY) — həm standalone ``my_appeals``,
    həm də profil dashboard bölməsi (``accounts...main``) eyni məntiqi paylaşır.
    """
    status_filter = (request.GET.get("status") or "").strip()
    exam_slug = (request.GET.get("exam") or "").strip()
    search_query = (request.GET.get("q") or "").strip()

    queryset = filter_student_appeals(
        student_appeals_queryset(request.user),
        status=status_filter,
        exam_slug=exam_slug,
        search=search_query,
    )
    page_obj = paginate_student_appeals(queryset, request.GET.get("page", 1))

    return {
        "appeal_page_obj": page_obj,
        "appeal_list": page_obj.object_list,
        "appeal_status_choices": APPEAL_STATUS_CHOICES,
        "appeal_status_filter": status_filter if status_filter in APPEAL_STATUS_VALUES else "",
        "appeal_search_query": search_query,
        "appeal_list_action": list_action,
        "appeal_section": section,
    }


@login_required
def my_appeals(request):
    # Apellyasiyalar ayrıca səhifə deyil — dashboard bölməsində açılır.
    # Birbaşa URL ilə gələnləri (köhnə link/bookmark) dashboard-a yönləndiririk;
    # filtr parametrləri (status/q) qorunur.
    query = request.GET.urlencode()
    target = reverse("accounts:profile") + "?section=my-appeals"
    if query:
        target += "&" + query
    return redirect(target)
