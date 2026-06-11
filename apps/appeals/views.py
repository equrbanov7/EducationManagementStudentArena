"""
Apellyasiya view-ları.

Faza 4 — student tərəfi: apellyasiya yaratma, izləmə (siyahı) və detal.
Teacher idarəetmə view-ları sonrakı slice-da əlavə olunacaq.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import pgettext

from apps.exams.models import ExamAttempt
from apps.exams.views.shared.tenant import tenant_scoped_exams
from apps.exams.views.student._helpers import ensure_student_exam_tenant_context
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_MIN_COMMENT_LENGTH,
    APPEAL_STATUS_CHOICES,
    APPEAL_STATUS_VALUES,
    APPEAL_TYPE_CHOICES,
    APPEAL_TYPE_VALUES,
    PERM_APPEAL_DECIDE,
    PERM_APPEAL_RESPOND,
)
from .models import Appeal
from .selectors import (
    filter_student_appeals,
    paginate_student_appeals,
    student_appeals_queryset,
)
from .services import (
    accept_appeal_item,
    can_create_appeal,
    can_review_appeal,
    create_appeal,
    effective_test_score,
    is_within_appeal_window,
    reject_appeal_item,
    remaining_window_seconds,
    revert_item_adjustment,
)


def _result_url(exam, attempt):
    return reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id})


def _marked_question_map(attempt):
    marked_ids = {}
    for raw_question_id in getattr(attempt, "marked_question_ids", None) or []:
        try:
            marked_ids[int(raw_question_id)] = True
        except (TypeError, ValueError):
            continue
    return marked_ids


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


def _appeal_item_stats(items):
    """Detal səhifəsi üçün item statuslarının xülasəsi."""
    stats = {"total": len(items), "accepted": 0, "rejected": 0, "pending": 0}
    for item in items:
        if item.status == APPEAL_ITEM_STATUS_ACCEPTED:
            stats["accepted"] += 1
        elif item.status == APPEAL_ITEM_STATUS_REJECTED:
            stats["rejected"] += 1
        else:
            stats["pending"] += 1
    return stats


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

    items = list(appeal.items.all())
    score_info = effective_test_score(appeal.attempt) if appeal.exam.exam_type == "test" else None

    context = {
        "appeal": appeal,
        "items": items,
        "is_owner": is_owner,
        "score_info": score_info,
        "item_stats": _appeal_item_stats(items),
        "is_within_window": is_within_appeal_window(appeal.attempt),
        "marked_question_by_qid": _marked_question_map(appeal.attempt),
        "back_url": reverse("accounts:profile") + "?section=my-appeals",
    }

    # Dashboard daxili AJAX swap üçün yalnız gövdə fraqmenti qaytarılır.
    is_fragment = request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest"
    if is_fragment:
        return render(request, "appeals/partials/_appeal_detail_body.html", context)
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


def build_manage_appeals_context(request, *, list_action, section=""):
    """
    Müəllim/reviewer apellyasiya siyahısı konteksti (DRY) — həm standalone
    ``manage_appeals``, həm profil dashboard bölməsi eyni məntiqi paylaşır.

    Açar adları ``appeal_``-prefiksli saxlanılır ki, profil dashboard
    kontekstindəki digər dəyişənlərlə (total_count, search_query, page_obj…)
    toqquşmasın. Tenant/sahiblik scope-u burada qorunur; ÇAĞIRAN tərəf access
    yoxlamasını (``_can_open_appeal_management``) ayrıca etməlidir.
    """
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

    # ── Filtrlər (status istisna — status sayğacları üçün) ──
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

    # Status sayğacları — status filtrindən ƏVVƏL (stat plitələri = sürətli filtr).
    status_counts = {row["status"]: row["c"] for row in appeals.values("status").annotate(c=Count("id", distinct=True))}
    total_count = sum(status_counts.values())

    # Filtr dropdown-u üçün apellyasiyası olan imtahanlar (status filtrindən asılı deyil).
    exam_options = list(appeals.values_list("exam__slug", "exam__title").distinct().order_by("exam__title")[:200])

    # ── Status filtri (siyahı üçün) ──
    status_filter = (request.GET.get("status") or "").strip()
    if status_filter in APPEAL_STATUS_VALUES:
        appeals = appeals.filter(status=status_filter)

    appeals = appeals.order_by("-created_at")

    paginator = Paginator(appeals, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return {
        "appeal_page_obj": page_obj,
        "appeal_list": page_obj.object_list,
        "appeal_status_choices": APPEAL_STATUS_CHOICES,
        "appeal_type_choices": APPEAL_TYPE_CHOICES,
        "appeal_exam_options": exam_options,
        "appeal_status_filter": status_filter if status_filter in APPEAL_STATUS_VALUES else "",
        "appeal_exam_slug": exam_slug,
        "appeal_type_filter": type_filter,
        "appeal_search_query": search_query,
        "appeal_date_from": request.GET.get("date_from", ""),
        "appeal_date_to": request.GET.get("date_to", ""),
        "appeal_can_decide": can_decide,
        "appeal_status_counts": status_counts,
        "appeal_total_count": total_count,
        "appeal_list_action": list_action,
        "appeal_section": section,
    }


@login_required
def manage_appeals(request):
    """Müəllim/reviewer üçün apellyasiya idarəetmə siyahısı (filtr + axtarış)."""
    if not _can_open_appeal_management(request):
        raise PermissionDenied

    is_fragment = request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest"
    # `embedded=1` → dashboard bölməsi kontekstində render (link/form profil
    # URL-inə yönəlir, sidebar sabit qalır). Əks halda standalone səhifə.
    if request.GET.get("embedded") == "1":
        context = build_manage_appeals_context(
            request, list_action=reverse("accounts:profile"), section="manage-appeals"
        )
    else:
        context = build_manage_appeals_context(request, list_action=reverse("appeals:manage_appeals"))

    if is_fragment:
        return render(request, "appeals/partials/_manage_appeals_body.html", context)
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

    items = list(
        appeal.items.select_related("question", "answer", "score_adjustment")
        .prefetch_related("question__options", "answer__selected_options")
        .all()
    )

    is_test = appeal.exam.exam_type == "test"

    # Dashboard daxili AJAX (manage-appeals bölməsi) → fraqment/JSON rejimi.
    is_fragment = request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest"

    final_item_statuses = {APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED}
    now = timezone.now()

    def _edit_locked(item):
        # Qərar verildikdən sonra yalnız REVIEW_EDIT_LOCK_WINDOW (5 dəq) ərzində
        # dəyişmək olar; sonra item DAİMİ kilidlənir (yazılı imtahan məntiqi ilə eyni).
        return bool(item.resolved_at and now >= item.resolved_at + REVIEW_EDIT_LOCK_WINDOW)

    if request.method == "POST":
        # Validasiya: qərar verilən hər item üçün cavab mətni məcburidir.
        decisions = []
        error_message = ""
        for item in items:
            if _edit_locked(item):
                continue  # 5 dəq keçib — kilidli, dəyişdirilə bilməz
            decision = (request.POST.get(f"decision_{item.id}") or "").strip()
            response_text = (request.POST.get(f"response_{item.id}") or "").strip()
            if decision in ("accept", "reject"):
                if not response_text:
                    error_message = pgettext("appeals.view.message", "Hər qərar üçün izah/cavab mətni yazmalısınız.")
                    break
                awarded = request.POST.get(f"points_{item.id}") if decision == "accept" else None
                was_decided = item.status in final_item_statuses
                decisions.append((item, decision, response_text, awarded, was_decided))

        if not error_message:
            for item, decision, response_text, awarded, was_decided in decisions:
                # Window içində yenidən redaktə → əvvəlki bal düzəlişini təmizlə ki,
                # yeni qərar/bal təmiz tətbiq olunsun (bal ikiqat sayılmasın).
                if was_decided:
                    revert_item_adjustment(item)
                if decision == "accept":
                    accept_appeal_item(
                        item,
                        reviewer=request.user,
                        response_text=response_text,
                        request=request,
                        awarded_points=awarded,
                    )
                else:
                    reject_appeal_item(item, reviewer=request.user, response_text=response_text, request=request)

            note = (request.POST.get("reviewer_note") or "").strip()
            if note:
                appeal.reviewer_note = note
                appeal.save(update_fields=["reviewer_note", "updated_at"])

            success_text = pgettext("appeals.view.message", "Qərarlar yadda saxlanıldı.")
            if is_fragment:
                return JsonResponse({"ok": True, "message": str(success_text)})
            messages.success(request, success_text)
            return redirect("appeals:review_appeal", appeal_id=appeal.id)

        # Validasiya səhvi
        if is_fragment:
            return JsonResponse({"ok": False, "error": str(error_message)}, status=200)
        messages.error(request, error_message)

    # ── Bal konteksti (əvvəlki → yeni bal göstərmək üçün) ──
    score_info = effective_test_score(appeal.attempt) if is_test else None
    if is_test and score_info:
        review_current_score = score_info["effective_score"]
        review_max_score = score_info["max_score"]
    else:
        from apps.exams.services.grading import calculate_attempt_score

        review_current_score = calculate_attempt_score(appeal.attempt)
        review_max_score = None

    # ── Hər item üçün şablon məlumatı: kilid/window, cari qərar, seçilmiş variant ──
    for item in items:
        item.is_decided = item.status in final_item_statuses
        item.is_locked = _edit_locked(item)
        item.max_points = item.question.points or 1
        item.current_decision = (
            "accept"
            if item.status == APPEAL_ITEM_STATUS_ACCEPTED
            else "reject" if item.status == APPEAL_ITEM_STATUS_REJECTED else ""
        )
        if item.is_decided and not item.is_locked and item.resolved_at:
            secs = max(0, int((item.resolved_at + REVIEW_EDIT_LOCK_WINDOW - now).total_seconds()))
            item.edit_minutes_left = max(1, (secs + 59) // 60)
            item.edit_seconds_left = secs
        else:
            item.edit_minutes_left = 0
            item.edit_seconds_left = 0
        # Qəbul olunmuş item üçün verilmiş bal (input default-u).
        # DİQQƏT: delta_points FƏRQDİR (verilən bal − əvvəlki töhfə), input isə
        # "bu suala verilən bal"ı gözləyir — birbaşa delta göstərmək yanlış idi.
        try:
            adjustment = item.score_adjustment
        except ObjectDoesNotExist:
            adjustment = None
        if item.current_decision == "accept" and adjustment and not adjustment.reverted:
            if is_test:
                base_contribution = item.max_points if adjustment.previous_is_correct else 0
                item.awarded_value = (adjustment.delta_points or 0) + base_contribution
            elif item.answer_id and item.answer and item.answer.teacher_score is not None:
                # Yazılı/praktiki: cari verilmiş bal birbaşa cavabda saxlanılır.
                item.awarded_value = item.answer.teacher_score
            else:
                item.awarded_value = item.max_points
        else:
            item.awarded_value = item.max_points
        # Test: tələbənin seçdiyi variant id-ləri (variant analizi üçün).
        if is_test and item.answer_id:
            item.selected_option_ids = {opt.id for opt in item.answer.selected_options.all()}
        else:
            item.selected_option_ids = set()

    context = {
        "appeal": appeal,
        "items": items,
        "is_test": is_test,
        "score_info": score_info,
        "review_current_score": review_current_score,
        "review_max_score": review_max_score,
        "marked_question_by_qid": _marked_question_map(appeal.attempt),
    }
    if is_fragment:
        return render(request, "appeals/partials/_review_appeal_body.html", context)
    return render(request, "appeals/teacher/review_appeal.html", context)
