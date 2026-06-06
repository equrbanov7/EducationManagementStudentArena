"""
Apellyasiya view-ları.

Faza 4 — student tərəfi: apellyasiya yaratma, izləmə (siyahı) və detal.
Teacher idarəetmə view-ları sonrakı slice-da əlavə olunacaq.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.translation import pgettext

from apps.exams.models import ExamAttempt
from apps.exams.views.shared.tenant import tenant_scoped_exams
from apps.exams.views.student._helpers import ensure_student_exam_tenant_context
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .constants import (
    APPEAL_MIN_COMMENT_LENGTH,
    APPEAL_STATUS_CHOICES,
    APPEAL_STATUS_VALUES,
    APPEAL_TYPE_CHOICES,
    APPEAL_TYPE_VALUES,
    PERM_APPEAL_DECIDE,
    PERM_APPEAL_RESPOND,
)
from .models import Appeal
from .services import (
    accept_appeal_item,
    can_create_appeal,
    can_review_appeal,
    create_appeal,
    effective_test_score,
    is_within_appeal_window,
    reject_appeal_item,
    remaining_window_seconds,
)


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
            return redirect(reverse("appeals:my_appeals"))

    context = {
        "exam": exam,
        "attempt": attempt,
        "answers": delivered_answers,
        "appeal_type_choices": APPEAL_TYPE_CHOICES,
        "min_comment_length": APPEAL_MIN_COMMENT_LENGTH,
        "remaining_seconds": remaining_window_seconds(attempt),
        "result_url": _result_url(exam, attempt),
    }
    return render(request, "appeals/student/appeal_create.html", context)


@login_required
def my_appeals(request):
    ensure_student_exam_tenant_context(request)

    appeals = (
        Appeal.objects.filter(student=request.user)
        .select_related("exam", "attempt", "reviewed_by")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    status_filter = (request.GET.get("status") or "").strip()
    if status_filter in APPEAL_STATUS_VALUES:
        appeals = appeals.filter(status=status_filter)

    exam_slug = (request.GET.get("exam") or "").strip()
    if exam_slug:
        appeals = appeals.filter(exam__slug=exam_slug)

    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        appeals = appeals.filter(exam__title__icontains=search_query)

    paginator = Paginator(appeals, 12)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "appeals": page_obj.object_list,
        "status_choices": APPEAL_STATUS_CHOICES,
        "status_filter": status_filter,
        "exam_slug": exam_slug,
        "search_query": search_query,
    }
    return render(request, "appeals/student/my_appeals.html", context)


@login_required
def appeal_detail(request, appeal_id):
    appeal = get_object_or_404(
        Appeal.objects.select_related("exam", "attempt", "reviewed_by", "student").prefetch_related(
            "items__question", "items__score_adjustment"
        ),
        id=appeal_id,
    )

    is_owner = appeal.student_id == request.user.id
    if not is_owner and not can_review_appeal(request, appeal):
        raise PermissionDenied

    score_info = effective_test_score(appeal.attempt) if appeal.exam.exam_type == "test" else None

    context = {
        "appeal": appeal,
        "items": list(appeal.items.all()),
        "is_owner": is_owner,
        "score_info": score_info,
        "is_within_window": is_within_appeal_window(appeal.attempt),
    }
    return render(request, "appeals/student/appeal_detail.html", context)


# ===========================================================================
# Teacher / reviewer
# ===========================================================================
def _can_open_appeal_management(request):
    user = getattr(request, "user", None)
    return bool(
        is_superadmin_user(user)
        or request_has_permission(request, PERM_APPEAL_DECIDE)
        or request_has_permission(request, PERM_APPEAL_RESPOND)
    )


@login_required
def manage_appeals(request):
    """Müəllim/reviewer üçün apellyasiya idarəetmə siyahısı (filtr + axtarış)."""
    if not _can_open_appeal_management(request):
        raise PermissionDenied

    user = request.user
    organization = get_request_organization(request)
    can_decide = is_superadmin_user(user) or request_has_permission(request, PERM_APPEAL_DECIDE)

    appeals = Appeal.objects.select_related("exam", "attempt", "student", "reviewed_by").prefetch_related("items")

    if organization is not None:
        appeals = appeals.filter(organization=organization)
    elif not is_superadmin_user(user):
        appeals = appeals.none()

    # Scope: decide/superadmin → təşkilatın bütün apellyasiyaları;
    # yalnız respond → yalnız öz imtahanlarının apellyasiyaları.
    if not can_decide:
        appeals = appeals.filter(exam__author=user)

    # ── Filtrlər ──
    status_filter = (request.GET.get("status") or "").strip()
    if status_filter in APPEAL_STATUS_VALUES:
        appeals = appeals.filter(status=status_filter)

    exam_slug = (request.GET.get("exam") or "").strip()
    if exam_slug:
        appeals = appeals.filter(exam__slug=exam_slug)

    type_filter = (request.GET.get("type") or "").strip()
    if type_filter in APPEAL_TYPE_VALUES:
        appeals = appeals.filter(items__appeal_type=type_filter).distinct()

    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        appeals = appeals.filter(
            Q(exam__title__icontains=search_query)
            | Q(student__username__icontains=search_query)
            | Q(student__email__icontains=search_query)
            | Q(student__first_name__icontains=search_query)
            | Q(student__last_name__icontains=search_query)
        )

    date_from = parse_date((request.GET.get("date_from") or "").strip())
    if date_from:
        appeals = appeals.filter(created_at__date__gte=date_from)
    date_to = parse_date((request.GET.get("date_to") or "").strip())
    if date_to:
        appeals = appeals.filter(created_at__date__lte=date_to)

    appeals = appeals.order_by("-created_at")

    # Filtr dropdown-u üçün apellyasiyası olan imtahanlar.
    exam_options = list(
        appeals.values_list("exam__slug", "exam__title").distinct().order_by("exam__title")[:200]
    )

    paginator = Paginator(appeals, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "appeals": page_obj.object_list,
        "status_choices": APPEAL_STATUS_CHOICES,
        "type_choices": APPEAL_TYPE_CHOICES,
        "exam_options": exam_options,
        "status_filter": status_filter,
        "exam_slug": exam_slug,
        "type_filter": type_filter,
        "search_query": search_query,
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "can_decide": can_decide,
    }
    return render(request, "appeals/teacher/manage_appeals.html", context)


@login_required
def review_appeal(request, appeal_id):
    """Müəllim/reviewer apellyasiya detalı + qərar (per-sual accept/reject)."""
    appeal = get_object_or_404(
        Appeal.objects.select_related("exam", "attempt", "student", "reviewed_by").prefetch_related(
            "items__question", "items__score_adjustment"
        ),
        id=appeal_id,
    )
    if not can_review_appeal(request, appeal):
        raise PermissionDenied

    items = list(appeal.items.select_related("question").all())

    if request.method == "POST":
        # Əvvəlcə validasiya: qərar verilən hər item üçün cavab mətni məcburidir
        # ("niyə artırıldı/artırılmadı" izahı).
        decisions = []
        invalid = False
        for item in items:
            decision = (request.POST.get(f"decision_{item.id}") or "").strip()
            response_text = (request.POST.get(f"response_{item.id}") or "").strip()
            if decision in ("accept", "reject"):
                if not response_text:
                    messages.error(
                        request,
                        pgettext("appeals.view.message", "Hər qərar üçün izah/cavab mətni yazmalısınız."),
                    )
                    invalid = True
                    break
                decisions.append((item, decision, response_text))

        if not invalid:
            for item, decision, response_text in decisions:
                if decision == "accept":
                    accept_appeal_item(item, reviewer=request.user, response_text=response_text, request=request)
                else:
                    reject_appeal_item(item, reviewer=request.user, response_text=response_text, request=request)

            note = (request.POST.get("reviewer_note") or "").strip()
            if note:
                appeal.reviewer_note = note
                appeal.save(update_fields=["reviewer_note", "updated_at"])

            messages.success(request, pgettext("appeals.view.message", "Qərarlar yadda saxlanıldı."))
            return redirect("appeals:review_appeal", appeal_id=appeal.id)

    score_info = effective_test_score(appeal.attempt) if appeal.exam.exam_type == "test" else None

    context = {
        "appeal": appeal,
        "items": items,
        "score_info": score_info,
    }
    return render(request, "appeals/teacher/review_appeal.html", context)
