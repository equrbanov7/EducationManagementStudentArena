"""
Labs Views - Question Management
Sual CRUD və import
"""

import re

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from ..models import LabQuestion
from ._helpers import (
    _get_tenant_block_or_404,
    _get_tenant_question_or_404,
    _normalize_extensions,
    _validate_and_prepare_lab_upload,
)


@login_required
@require_POST
def create_question(request, block_id):
    """Sual yarat"""
    block = _get_tenant_block_or_404(request, block_id)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        attachment = request.FILES.get("attachment")
        if attachment is not None:
            allowed_extensions = _normalize_extensions(block.lab.allowed_extensions)
            _validate_and_prepare_lab_upload(
                attachment,
                allowed_extensions=allowed_extensions,
                max_size_mb=block.lab.max_file_size_mb or 25,
            )

        question = LabQuestion.objects.create(
            block=block,
            question_number=block.questions.count() + 1,
            question_text=request.POST.get("question_text"),
            points=request.POST.get("points", 0),
        )

        if attachment is not None:
            question.attachment = attachment
            question.save()

        return JsonResponse({"success": True, "question_id": question.id})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_question(request, pk):
    """Sual redaktə et"""
    question = _get_tenant_question_or_404(request, pk)

    if question.block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if request.method == "GET":
        data = {
            "id": question.id,
            "question_text": question.question_text,
            "points": question.points,
            "question_number": question.question_number,
        }
        return JsonResponse({"success": True, "data": data})

    try:
        question.question_text = request.POST.get("question_text")
        question.points = request.POST.get("points", 0)
        question.save()
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def delete_question(request, pk):
    """Sual sil"""
    question = _get_tenant_question_or_404(request, pk)

    if question.block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    question.delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def import_questions(request, block_id):
    """
    Sualları toplu import et.

    Format dəstəyi:
    - 1. Sual metni
    - 1) Sual metni
    - 2. Başqa sual
    - Nömrəsiz sətir = əvvəlki sualın davamı
    """

    block = _get_tenant_block_or_404(request, block_id)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        questions_text = request.POST.get("questions_text", "")

        if not questions_text.strip():
            return JsonResponse(
                {"success": False, "error": pgettext("labs.view.error", "empty_text_submitted")}, status=400
            )

        # Regex pattern: başda rəqəm + nöqtə və ya mötərizə
        # Məs: "1. " və ya "2) " və ya "10. "
        pattern = re.compile(r"^\s*(\d+)[\.\)]\s+(.+)", re.MULTILINE)

        lines = questions_text.split("\n")
        questions = []
        current_question = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = pattern.match(line)
            if match:
                # Yeni sual başlayır
                if current_question:
                    questions.append(current_question)

                num, text = match.groups()
                current_question = text.strip()
            else:
                # Əvvəlki sualın davamı
                if current_question:
                    current_question += " " + line

        # Sonuncu sualı əlavə et
        if current_question:
            questions.append(current_question)

        if not questions:
            return JsonResponse(
                {
                    "success": False,
                    "error": pgettext("labs.view.error", "import_no_questions_found_format"),
                },
                status=400,
            )

        # Sualları DB-yə əlavə et
        count = block.questions.count()
        created_count = 0

        for i, text in enumerate(questions, start=1):
            LabQuestion.objects.create(
                block=block,
                question_number=count + i,
                question_text=text,
            )
            created_count += 1

        return JsonResponse(
            {
                "success": True,
                "count": created_count,
                "message": pgettext("labs.view.message", "import_success_with_count") % {"count": created_count},
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
