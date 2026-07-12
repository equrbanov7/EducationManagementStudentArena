"""Appeals — tələbə səthi: yaratma + siyahı (F4 rol-skeleti, 2026-07-02)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import ExamAttempt
from apps.exams.navigation import append_query_params, current_return_to
from apps.exams.public import exam_answers_release_locked, tenant_scoped_exams
from apps.exams.services.question_snapshot import delivered_question_render
from apps.exams.views.student._helpers import ensure_student_exam_tenant_context

from ...constants import (
    APPEAL_MIN_COMMENT_LENGTH,
    APPEAL_STATUS_CHOICES,
    APPEAL_STATUS_UNDER_REVIEW,
    APPEAL_STATUS_VALUES,
    APPEAL_TYPE_CHOICES,
    APPEAL_WINDOW_DAYS,
)
from ...models import AppealItem
from ...selectors import filter_student_appeals, paginate_student_appeals, student_appeals_queryset
from ...services import (
    appeal_deadline,
    appeal_item_result_visible_to_student,
    can_create_appeal,
    create_appeal,
    is_within_appeal_window,
    remaining_window_seconds,
)
from ..shared._helpers import _marked_question_map

APPEAL_STATUS_LABELS = dict(APPEAL_STATUS_CHOICES)


def _is_profile_results_request(request):
    source_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    if source_section == "my-results":
        return True
    return "section=my-results" in (current_return_to(request) or "")


def _result_url(exam, attempt, request=None):
    url = reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
    if request is not None and _is_profile_results_request(request):
        url = append_query_params(
            url,
            from_section="my-results",
            return_to=current_return_to(request) or f"{reverse('accounts:profile')}?section=my-results",
        )
    return url


def _is_final_exam(exam):
    return getattr(exam, "exam_type_extended", "") == "final"


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


def _attempt_appeals_for_student(attempt):
    """Bu attempt üzrə tələbənin apellyasiyaları (nəticə/status baxışı üçün)."""
    from ...models import Appeal

    appeals = list(
        Appeal.objects.filter(attempt=attempt, student=attempt.user).prefetch_related("items").order_by("-created_at")
    )
    for appeal in appeals:
        has_hidden_decision = any(not appeal_item_result_visible_to_student(item) for item in appeal.items.all())
        appeal.student_display_status = APPEAL_STATUS_UNDER_REVIEW if has_hidden_decision else appeal.status
        appeal.student_display_status_label = APPEAL_STATUS_LABELS.get(
            appeal.student_display_status,
            appeal.get_status_display(),
        )
    return appeals


def _render_appeal_window_closed(request, exam, attempt, *, window_closed):
    """Pəncərə bağlı (və ya icazə yox) — read-only appeal səhifəsi."""
    is_profile_results_request = _is_profile_results_request(request)
    context = {
        "exam": exam,
        "attempt": attempt,
        "appeal_window_closed": True,
        "appeal_window_days": APPEAL_WINDOW_DAYS,
        "appeal_deadline": appeal_deadline(attempt),
        "window_expired": window_closed,
        "attempt_appeals": _attempt_appeals_for_student(attempt),
        "result_url": _result_url(exam, attempt, request),
        "is_final_exam": _is_final_exam(exam) and not is_profile_results_request,
        # Read-only rejim üçün form dəyişənləri boş/deaktiv.
        "answers": [],
    }
    return render(request, "appeals/student/appeal_create.html", context)


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
        # UX: pəncərə (3 gün) bağlanıbsa çılpaq error/redirect əvəzinə oxu-rejimli
        # "müddət bitib" səhifəsi göstərilir — tələbə əvvəlki nəticəyə və öz
        # apellyasiyalarının nəticəsinə baxa bilir, yenidən vermək istəsə isə
        # 3-gün qaydası aydın UX formatında görünür.
        window_closed = not is_within_appeal_window(attempt)
        return _render_appeal_window_closed(request, exam, attempt, window_closed=window_closed)

    delivered_answers = list(
        attempt.answers.select_related("question")
        .prefetch_related("question__options", "selected_options")
        .order_by("id")
    )
    delivered_question_ids = {answer.question_id for answer in delivered_answers}
    appealed_question_ids = set(
        AppealItem.objects.filter(appeal__attempt=attempt, question_id__in=delivered_question_ids).values_list(
            "question_id", flat=True
        )
    )

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
            if _is_final_exam(exam) and not _is_profile_results_request(request):
                # Final imtahan: apellyasiyadan sonra imtahan giriş səhifəsinə çıxılır.
                return redirect(reverse("exams:final_exam_entry"))
            # Tələbə apellyasiyalarını dashboard bölməsində izləyir.
            return redirect(reverse("accounts:profile") + "?section=my-appeals")

    for answer in delivered_answers:
        answer.has_selection = bool(list(answer.selected_options.all()))
        # EXAM-P0-03: apellyasiya sübutu da çatdırılma anındakı dondurulmuş sual
        # görünüşündən render olunur (müəllif sonradan redaktə etsə də sabit
        # qalır); dondurulmuş seçim yoxdursa canlı seçimə düşülür.
        frozen_selection = getattr(answer, "selected_option_ids_snapshot", None)
        if frozen_selection is not None:
            selected_ids = {int(option_id) for option_id in frozen_selection}
        else:
            selected_ids = {opt.id for opt in answer.selected_options.all()}
        answer.delivered = delivered_question_render(answer, selected_ids)

    marked_map = _marked_question_map(attempt)
    has_marked = any(marked_map.get(answer.question_id) for answer in delivered_answers)

    is_profile_results_request = _is_profile_results_request(request)
    answers_release_locked = exam_answers_release_locked(exam)

    context = {
        "exam": exam,
        "attempt": attempt,
        "answers": delivered_answers,
        "appeal_type_choices": APPEAL_TYPE_CHOICES,
        "min_comment_length": APPEAL_MIN_COMMENT_LENGTH,
        "remaining_seconds": remaining_window_seconds(attempt),
        "result_url": _result_url(exam, attempt, request),
        "marked_question_by_qid": marked_map,
        "appealed_question_by_qid": {question_id: True for question_id in appealed_question_ids},
        "has_marked": has_marked,
        # EXAM-P0-05: nəticə səhifəsindəki release kilidi appeal
        # URL-indən yan keçilə bilməz. Eyni siyasət correctness variantlarını,
        # ideal cavabı və tələbə seçimini birlikdə gizlədir.
        "hide_answer_details": is_profile_results_request or answers_release_locked,
        "answers_release_locked": answers_release_locked,
        "is_final_exam": _is_final_exam(exam) and not is_profile_results_request,
    }
    return render(request, "appeals/student/appeal_create.html", context)


def _appeal_eligible_attempts(request):
    """ "Yeni apellyasiya" modal-ı üçün uyğun cəhdlər.

    Tələbənin 3-günlük pəncərəsi hələ açıq olan bitmiş final/midterm cəhdləri —
    hər biri üçün müraciət səhifəsinə keçid. Adi test/quiz cəhdləri apellyasiya
    axışına daxil deyil (yalnız final/midterm).
    """
    from apps.exams.constants import ATTEMPT_FINISHED_STATUSES

    attempts = (
        ExamAttempt.objects.filter(
            user=request.user,
            status__in=ATTEMPT_FINISHED_STATUSES,
            exam__exam_type_extended__in=("final", "midterm"),
        )
        .select_related("exam")
        .order_by("-finished_at")
    )
    eligible = []
    for attempt in attempts:
        if not can_create_appeal(request, attempt):
            continue
        attempt.appeal_deadline = appeal_deadline(attempt)
        attempt.appeal_remaining_seconds = remaining_window_seconds(attempt)
        attempt.appeal_create_url = append_query_params(
            reverse("appeals:appeal_create", kwargs={"attempt_id": attempt.id}),
            from_section="my-appeals",
        )
        eligible.append(attempt)
    return eligible


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
    for appeal in page_obj.object_list:
        has_hidden_decision = any(not appeal_item_result_visible_to_student(item) for item in appeal.items.all())
        appeal.student_display_status = APPEAL_STATUS_UNDER_REVIEW if has_hidden_decision else appeal.status
        appeal.student_display_status_label = APPEAL_STATUS_LABELS.get(
            appeal.student_display_status,
            appeal.get_status_display(),
        )

    eligible_attempts = _appeal_eligible_attempts(request)
    return {
        "appeal_page_obj": page_obj,
        "appeal_list": page_obj.object_list,
        "appeal_status_choices": APPEAL_STATUS_CHOICES,
        "appeal_status_filter": status_filter if status_filter in APPEAL_STATUS_VALUES else "",
        "appeal_search_query": search_query,
        "appeal_list_action": list_action,
        "appeal_section": section,
        "appeal_eligible_attempts": eligible_attempts,
        "appeal_window_days": APPEAL_WINDOW_DAYS,
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
