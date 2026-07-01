"""teacher questions paketi — _shared."""

from urllib.parse import urlencode, urlsplit

from django.template.loader import render_to_string
from django.urls import Resolver404, resolve
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestion, QuestionBlock


def _is_question_modal_request(request):
    return request.GET.get("modal") == "1" or request.POST.get("modal") == "1"


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _is_internal_exam_management_path(candidate_path):
    raw_path = (candidate_path or "").strip()
    if not raw_path:
        return False

    try:
        match = resolve(urlsplit(raw_path).path)
    except Resolver404:
        return False

    return match.namespace == "exams" and match.url_name in {
        "teacher_questions_bank",
        "test_question_bank",
        "create_question_bank",
        "add_exam_question",
        "edit_exam_question",
        "delete_exam_question",
        "teacher_exam_results",
        "teacher_view_attempt",
        "teacher_check_attempt",
    }


def _resolve_question_bank_navigation(request):
    requested_profile_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    valid_profile_sections = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = ""

    return_to = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.POST.get("return_to"),
    )
    if _is_internal_exam_management_path(return_to):
        return_to = ""

    nav_params = {}
    if requested_profile_section:
        nav_params["from_section"] = requested_profile_section
    if return_to:
        nav_params["return_to"] = return_to

    return return_to, requested_profile_section, urlencode(nav_params)


def _append_navigation_query(path, navigation_query):
    if not navigation_query:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{navigation_query}"


def _resequence_exam_questions(exam):
    ordered_questions = list(exam.questions.order_by("order", "id").only("id", "order"))
    updated_questions = []

    for index, question in enumerate(ordered_questions, start=1):
        if question.order != index:
            question.order = index
            updated_questions.append(question)

    if updated_questions:
        ExamQuestion.objects.bulk_update(updated_questions, ["order"])


def _question_form_blocks(exam):
    created_default_block = None

    if exam.exam_type == "written" and not exam.question_blocks.exists():
        created_default_block = QuestionBlock.objects.create(
            exam=exam,
            name=f"{pgettext('exams.template.create_question_bank', 'block_default')} 1",
            order=1,
            enable_paint=exam.enable_paint,
        )

    return QuestionBlock.objects.filter(exam=exam).order_by("order", "id"), created_default_block


def _question_post_data_with_default_block(request, created_default_block):
    if not created_default_block or request.POST.get("block"):
        return request.POST

    post_data = request.POST.copy()
    post_data["block"] = str(created_default_block.id)
    return post_data


def _render_question_form_html(request, *, exam, form, editing=False, question=None, navigation_query=""):
    return render_to_string(
        "exams/teacher/partials/_question_form.html",
        {
            "exam": exam,
            "form": form,
            "editing": editing,
            "question": question,
            "is_modal": True,
            "question_navigation_query": navigation_query,
        },
        request=request,
    )
