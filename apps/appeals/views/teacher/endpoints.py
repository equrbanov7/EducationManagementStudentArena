"""Appeals — müəllim/reviewer səthi: idarəetmə + qərar (F4, 2026-07-02)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import pgettext

from apps.exams.public import is_exam_center_user
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization

from ...constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_STATUS_CHOICES,
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_VALUES,
    APPEAL_TYPE_CHOICES,
    APPEAL_TYPE_VALUES,
)
from ...models import Appeal
from ...services import (
    accept_appeal_item,
    can_review_appeal,
    can_view_appeal_managed,
    effective_test_score,
    reject_appeal_item,
    revert_item_adjustment,
)
from ..shared._helpers import _marked_question_map


def _format_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _format_decimal(value):
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".")


def _can_open_appeal_management(request):
    return is_exam_center_user(getattr(request, "user", None))


def count_pending_manage_appeals(request):
    """Reviewer sidebar badge üçün tenant-scoped gözləyən apellyasiya sayı."""
    if not _can_open_appeal_management(request):
        return 0

    user = request.user
    organization = get_request_organization(request)
    appeals = Appeal.objects.filter(status=APPEAL_STATUS_PENDING)

    if organization is not None:
        appeals = appeals.filter(organization=organization)
    elif not is_superadmin_user(user):
        return 0

    return appeals.count()


def _appeal_edit_seconds_left(appeal, now):
    seconds_left = []
    for item in appeal.items.all():
        if item.status not in {APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED}:
            continue
        if not item.resolved_at:
            continue
        seconds = int((item.resolved_at + REVIEW_EDIT_LOCK_WINDOW - now).total_seconds())
        if seconds > 0:
            seconds_left.append(seconds)
    return max(seconds_left, default=0)


def _current_review_score(appeal, is_test):
    if is_test:
        score_info = effective_test_score(appeal.attempt)
        return score_info["effective_score"], score_info["max_score"], score_info

    from apps.exams.public import calculate_attempt_score

    return calculate_attempt_score(appeal.attempt), None, None


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
    can_decide = is_exam_center_user(user)

    appeals = Appeal.objects.select_related("exam", "attempt", "student", "reviewed_by").prefetch_related("items")

    if organization is not None:
        appeals = appeals.filter(organization=organization)
    elif not is_superadmin_user(user):
        appeals = appeals.none()

    # Scope: imtahan mərkəzi/superadmin → təşkilatın bütün apellyasiyaları.

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
    now = timezone.now()
    for appeal in page_obj.object_list:
        appeal.edit_seconds_left = _appeal_edit_seconds_left(appeal, now)
        appeal.edit_time_label = _format_seconds(appeal.edit_seconds_left)

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
    """Müəllim/reviewer apellyasiya siyahısı — yalnız dashboard bölməsi.

    Standalone səhifə yoxdur: birbaşa URL (köhnə link/bookmark) sidebar-lı
    profil bölməsinə yönləndirilir; filtr parametrləri qorunur. Fragment
    rejimi dashboard-un AJAX siyahı yeniləməsi üçün qalır.
    """
    if not _can_open_appeal_management(request):
        raise PermissionDenied

    is_fragment = request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest"
    if not is_fragment:
        query = request.GET.urlencode()
        target = reverse("accounts:profile") + "?section=manage-appeals"
        if query:
            target += "&" + query
        return redirect(target)

    context = build_manage_appeals_context(request, list_action=reverse("accounts:profile"), section="manage-appeals")
    return render(request, "appeals/partials/_manage_appeals_body.html", context)


@login_required
def review_appeal(request, appeal_id):
    """Müəllim/reviewer apellyasiya detalı + qərar (per-sual accept/reject)."""
    appeal = get_object_or_404(
        Appeal.objects.select_related("exam", "attempt", "student", "reviewed_by").prefetch_related(
            "items__question", "items__score_adjustment"
        ),
        id=appeal_id,
    )
    review_can_decide = can_review_appeal(request, appeal)
    if not review_can_decide:
        # Reviewer-independence: imtahan müəllifi/qiymətləndirən qərar verə
        # bilməz, amma READ-ONLY baxa bilər. Heç bir baxış haqqı yoxdursa —
        # fraqment sorğusuna generik "Loading failed" əvəzinə mənalı mesaj.
        if not can_view_appeal_managed(request, appeal):
            if request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "ok": False,
                        "error": str(
                            pgettext(
                                "appeals.view.message",
                                "Bu apellyasiyaya baxmaq icazəniz yoxdur.",
                            )
                        ),
                    },
                    status=403,
                )
            raise PermissionDenied
        if request.method == "POST":
            return JsonResponse(
                {
                    "ok": False,
                    "error": str(
                        pgettext(
                            "appeals.view.message",
                            "Qərarı yalnız müstəqil imtahan mərkəzi istifadəçisi verə bilər — "
                            "imtahanın müəllifi/qiymətləndirəni öz işinə qərar verə bilməz.",
                        )
                    ),
                },
                status=403,
            )

    items = list(
        appeal.items.select_related("question", "answer", "score_adjustment")
        .prefetch_related("question__options", "answer__selected_options")
        .all()
    )

    is_test = appeal.exam.exam_type == "test"

    # Dashboard daxili AJAX (manage-appeals bölməsi) → fraqment/JSON rejimi.
    is_fragment = request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest"
    # Standalone qərar səhifəsi yoxdur — qərar yalnız dashboard modalında
    # verilir; birbaşa URL sidebar-lı siyahı bölməsinə yönləndirilir.
    dashboard_url = reverse("accounts:profile") + "?section=manage-appeals"
    if not is_fragment and request.method != "POST":
        return redirect(dashboard_url)

    final_item_statuses = {APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED}
    now = timezone.now()

    def _edit_locked(item):
        # Qərar verildikdən sonra yalnız REVIEW_EDIT_LOCK_WINDOW (5 dəq) ərzində
        # dəyişmək olar; sonra item DAİMİ kilidlənir (yazılı imtahan məntiqi ilə eyni).
        return bool(item.resolved_at and now >= item.resolved_at + REVIEW_EDIT_LOCK_WINDOW)

    if request.method == "POST":
        score_before, _, _ = _current_review_score(appeal, is_test)
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
                was_decided = item.status in final_item_statuses
                decisions.append((item, decision, response_text, was_decided))

        if not error_message:
            for item, decision, response_text, was_decided in decisions:
                # Window içində yenidən redaktə → əvvəlki bal düzəlişini təmizlə ki,
                # yeni qərar təmiz tətbiq olunsun (bal ikiqat sayılmasın).
                if was_decided:
                    revert_item_adjustment(item)
                if decision == "accept":
                    # Qəbul → sabit +1 bal (bax scoring.accept_appeal_item).
                    accept_appeal_item(
                        item,
                        reviewer=request.user,
                        response_text=response_text,
                        request=request,
                    )
                else:
                    reject_appeal_item(item, reviewer=request.user, response_text=response_text, request=request)

            score_after, _, _ = _current_review_score(appeal, is_test)
            score_delta = score_after - score_before
            note = (request.POST.get("reviewer_note") or "").strip()
            if note:
                appeal.reviewer_note = note
                appeal.save(update_fields=["reviewer_note", "updated_at"])

            success_text = pgettext("appeals.view.message", "Qərarlar yadda saxlanıldı.")
            if is_fragment:
                toast_text = str(success_text)
                if score_delta > 0:
                    toast_text = pgettext(
                        "appeals.view.message",
                        "+{points} bal əlavə olundu. Tələbə nəticəni 5 dəqiqədən sonra görəcək; bu 5 dəqiqə ərzində qərarı dəyişə bilərsiniz.",
                    ).format(points=_format_decimal(score_delta))
                elif decisions:
                    toast_text = pgettext(
                        "appeals.view.message",
                        "Qərarlar yadda saxlanıldı. Tələbə nəticəni 5 dəqiqədən sonra görəcək; bu 5 dəqiqə ərzində qərarı dəyişə bilərsiniz.",
                    )
                return JsonResponse(
                    {
                        "ok": True,
                        "message": str(success_text),
                        "toast": str(toast_text),
                        "score_delta": _format_decimal(score_delta),
                    }
                )
            messages.success(request, success_text)
            return redirect(dashboard_url)

        # Validasiya səhvi
        if is_fragment:
            return JsonResponse({"ok": False, "error": str(error_message)}, status=200)
        messages.error(request, error_message)
        return redirect(dashboard_url)

    # ── Bal konteksti (əvvəlki → yeni bal göstərmək üçün) ──
    review_current_score, review_max_score, score_info = _current_review_score(appeal, is_test)

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
        item.existing_delta = adjustment.delta_points if adjustment and not adjustment.reverted else 0
        item.existing_delta_value = _format_decimal(item.existing_delta)
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

    # Redaktə oluna bilən (kilidlənməmiş) item qalmayıbsa → qərar formu artıq
    # final-dır: "yadda saxla" düyməsi və ümumi qeyd sahəsi gizlədilir.
    review_has_editable = review_can_decide and any(not item.is_locked for item in items)

    context = {
        "appeal": appeal,
        "items": items,
        "is_test": is_test,
        "score_info": score_info,
        "review_current_score": review_current_score,
        "review_max_score": review_max_score,
        "review_has_editable": review_has_editable,
        "review_can_decide": review_can_decide,
        "marked_question_by_qid": _marked_question_map(appeal.attempt),
    }
    return render(request, "appeals/partials/_review_appeal_body.html", context)
