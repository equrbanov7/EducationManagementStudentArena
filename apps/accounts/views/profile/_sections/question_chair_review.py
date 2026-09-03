"""Profil «question-chair-review» («Sual təsdiqi») bölməsinin konteksti.

Kafedra müdiri (kafedra müdiri təyin edilməyibsə dekanlıq) öz kafedrasının
müəllimlərindən gələn sual dəstlərini burada görür və qərar səhifəsinə keçir.

Əhatə SERVİS QATINDAN gəlir (``apps.exams.services.question_chair_review
.chair_queue_queryset``) — bölmə heç vaxt «bütün təşkilat» sorğusu qurmur;
əhatəsi olmayan aktor BOŞ növbə görür (fail-closed).

GET parametrləri ``qchair_`` prefikslidir ki, digər bölmələrlə toqquşmasın.
Stat kartlar həm də status filtri linkləridir (mövcud «Sual göndərişləri»
bölməsi ilə eyni naxış).
"""

from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import pgettext

PAGE_SIZE = 10

_CTX = "accounts.profile.question_chair_review"

#: Növbənin status filtrləri (kafedra baxımından mənalı olanlar).
_STATUS_VALUES = (
    "submitted_to_chair",
    "chair_revision",
    "chair_approved",
    "center_review",
    "accepted",
    "rejected",
)


def _inactive_defaults() -> dict:
    return {
        "question_chair_review_items": [],
        "question_chair_review_page": None,
        "question_chair_review_has_access": False,
        "question_chair_review_pending_count": 0,
        "question_chair_review_approved_count": 0,
        "question_chair_review_revision_count": 0,
        "question_chair_review_total_count": 0,
        "question_chair_review_status_cards": [],
        "question_chair_review_filters": {},
        "question_chair_review_teachers": [],
        "question_chair_review_subjects": [],
        "question_chair_review_exam_kinds": [],
        "question_chair_review_clear_url": "",
        "question_chair_review_pagination_query": "",
        "question_chair_review_has_filters": False,
    }


def _profile_query(params: dict) -> str:
    pairs = [("section", "question-chair-review")]
    pairs.extend((key, value) for key, value in params.items() if value)
    return urlencode(pairs)


def _status_cards(counts, active_status, active_params) -> list:
    cards = [
        ("submitted_to_chair", pgettext(_CTX, "Təsdiq gözləyir"), counts["pending"], "fa-hourglass-half", "amber"),
        ("chair_approved", pgettext(_CTX, "Təsdiqlədiyim"), counts["approved"], "fa-check", "green"),
        ("chair_revision", pgettext(_CTX, "Düzəliş istənilən"), counts["revision"], "fa-rotate-left", "blue"),
        ("", pgettext(_CTX, "Ümumi"), counts["total"], "fa-layer-group", "slate"),
    ]
    result = []
    for status, label, value, icon, tone in cards:
        is_active = active_status == status
        params = dict(active_params)
        params["qchair_status"] = "" if is_active else status
        result.append(
            {
                "status": status,
                "label": label,
                "value": value or 0,
                "icon": icon,
                "tone": tone,
                "is_active": is_active,
                "query": _profile_query(params),
            }
        )
    return result


def build_question_chair_review_context(request, *, allowed_sections, active_section) -> dict:
    if not (active_section == "question-chair-review" and "question-chair-review" in allowed_sections):
        return _inactive_defaults()

    from django.contrib.auth import get_user_model
    from django.core.paginator import Paginator
    from django.db.models import Count, Q

    from apps.exams.constants import QUESTION_EXAM_KIND_CHOICES, QUESTION_EXAM_KIND_VALUES
    from apps.exams.models import QuestionSubmission
    from apps.exams.services.question_chair_review import chair_queue_queryset
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    if organization is None:
        return _inactive_defaults()

    scoped = chair_queue_queryset(request.user, organization)

    counts = scoped.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)),
        approved=Count("id", filter=Q(chair_decision=QuestionSubmission.CHAIR_DECISION_APPROVED)),
        revision=Count("id", filter=Q(status=QuestionSubmission.STATUS_CHAIR_REVISION)),
    )

    filters = {
        "q": (request.GET.get("qchair_q") or "").strip()[:120],
        "status": (request.GET.get("qchair_status") or "").strip().lower(),
        "kind": (request.GET.get("qchair_kind") or "").strip().lower(),
        "teacher": (request.GET.get("qchair_teacher") or "").strip()[:20],
    }
    if filters["status"] not in _STATUS_VALUES:
        filters["status"] = ""
    if filters["kind"] not in QUESTION_EXAM_KIND_VALUES:
        filters["kind"] = ""

    User = get_user_model()
    teacher_ids = list(scoped.values_list("teacher_id", flat=True).distinct())
    teachers = list(User.objects.filter(id__in=teacher_ids).order_by("first_name", "last_name", "username"))
    subjects = sorted({name for name in scoped.values_list("subject", flat=True) if name})

    filtered = scoped
    if filters["status"]:
        filtered = filtered.filter(status=filters["status"])
    if filters["kind"]:
        filtered = filtered.filter(exam_kind=filters["kind"])
    if filters["teacher"].isdigit():
        filtered = filtered.filter(teacher_id=int(filters["teacher"]))
    if filters["q"]:
        filtered = filtered.filter(
            Q(title__icontains=filters["q"])
            | Q(subject__icontains=filters["q"])
            | Q(group_label__icontains=filters["q"])
            | Q(teacher__first_name__icontains=filters["q"])
            | Q(teacher__last_name__icontains=filters["q"])
            | Q(teacher__username__icontains=filters["q"])
        )

    filtered = (
        filtered.select_related("teacher", "chair_unit", "chair_reviewer").distinct().order_by("-created_at", "-id")
    )
    page = Paginator(filtered, PAGE_SIZE).get_page(request.GET.get("qchair_page"))

    active_params = {
        "qchair_q": filters["q"],
        "qchair_status": filters["status"],
        "qchair_kind": filters["kind"],
        "qchair_teacher": filters["teacher"],
    }

    return {
        "question_chair_review_items": list(page.object_list),
        "question_chair_review_page": page,
        "question_chair_review_has_access": True,
        "question_chair_review_pending_count": counts["pending"] or 0,
        "question_chair_review_approved_count": counts["approved"] or 0,
        "question_chair_review_revision_count": counts["revision"] or 0,
        "question_chair_review_total_count": counts["total"] or 0,
        "question_chair_review_status_cards": _status_cards(counts, filters["status"], active_params),
        "question_chair_review_filters": filters,
        "question_chair_review_teachers": teachers,
        "question_chair_review_subjects": subjects,
        "question_chair_review_exam_kinds": QUESTION_EXAM_KIND_CHOICES,
        "question_chair_review_clear_url": f"{reverse('accounts:profile')}?section=question-chair-review",
        "question_chair_review_pagination_query": _profile_query(active_params),
        "question_chair_review_has_filters": any(active_params.values()),
    }


__all__ = ["build_question_chair_review_context"]
