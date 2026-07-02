"""
Labs Views - Block Management
Blok CRUD və idarəetmə
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from ...models import LabBlock
from ..shared._helpers import _get_tenant_block_or_404, _get_tenant_lab_or_404

logger = logging.getLogger(__name__)


@login_required
def manage_blocks(request, pk):
    """Blokları idarə et"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    blocks = lab.blocks.all().order_by("order")

    context = {
        "lab": lab,
        "blocks": blocks,
    }

    return render(request, "labs/manage_blocks.html", context)


@login_required
@require_POST
def create_block(request, pk):
    """Blok yarat"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        questions_to_pick = int(request.POST.get("questions_to_pick", 0) or 0)
        if questions_to_pick < 0:
            questions_to_pick = 0

        block = LabBlock.objects.create(
            lab=lab,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            order=lab.blocks.count() + 1,
            questions_to_pick=questions_to_pick,
        )
        messages.success(request, pgettext("labs.view.message", "block_created"))
        return JsonResponse({"success": True, "block_id": block.id})

    except Exception:
        logger.exception("Unexpected error in create_block")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def edit_block(request, pk):
    """Blok redaktə et"""
    block = _get_tenant_block_or_404(request, pk)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if request.method == "GET":
        data = {
            "id": block.id,
            "title": block.title,
            "description": block.description,
            "order": block.order,
            "questions_to_pick": block.questions_to_pick,
        }
        return JsonResponse({"success": True, "data": data})

    try:
        questions_to_pick = int(request.POST.get("questions_to_pick", 0) or 0)
        if questions_to_pick < 0:
            questions_to_pick = 0

        block.title = request.POST.get("title")
        block.description = request.POST.get("description", "")
        block.questions_to_pick = questions_to_pick
        block.save()
        return JsonResponse({"success": True})

    except Exception:
        logger.exception("Unexpected error in edit_block")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@login_required
@require_POST
def delete_block(request, pk):
    """Blok sil"""
    block = _get_tenant_block_or_404(request, pk)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    block.delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def update_questions_per_student(request, pk):
    """Lab üçün tələbə başına sual sayını yenilə"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    try:
        value = int(request.POST.get("questions_per_student", 0) or 0)
        if value < 0:
            value = 0
    except (TypeError, ValueError):
        value = 0

    lab.questions_per_student = value
    lab.save(update_fields=["questions_per_student", "updated_at"])

    # Mövcud assignment-ları yeni ayara görə yenilə.
    for assignment in lab.assignments.all():
        assignment.assign_questions()

    messages.success(request, "Tələbə başına sual sayı yeniləndi.")
    return redirect("labs:manage_blocks", pk=lab.id)
