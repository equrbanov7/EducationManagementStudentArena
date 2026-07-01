"""teacher exams paketi — actions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_POST

from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._shared import (
    _ensure_exam_permission,
    _get_editable_exam_or_404,
    _organization_selection_redirect,
    _resolve_required_organization,
    _safe_same_origin_redirect_path,
    _teacher_profile_my_exams_url,
)


@login_required
def toggle_exam_active(request, slug):
    """
    Müəllim imtahanı istənilən vaxt aktiv/deaktiv edə bilsin.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, "exam.edit")
    exam = get_teacher_exam_or_404(request, slug=slug)

    if request.method == "POST":
        exam.is_active = not exam.is_active
        exam.save()
        if exam.is_active:
            from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup
            from apps.notifications.services import get_exam_assigned_user_ids, notify_task_assignment

            schedule_ai_question_difficulty_warmup(exam)
            notify_task_assignment(
                task=exam,
                user_ids=get_exam_assigned_user_ids(exam),
                task_kind="exam",
            )
    return redirect("exams:teacher_exam_detail", slug=exam.slug)


@login_required
@require_POST
def toggle_exam_results_visibility(request, slug):
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, "exam.edit")
    exam = get_teacher_exam_or_404(request, slug=slug)

    exam.results_hidden_from_students = not exam.results_hidden_from_students
    exam.save(update_fields=["results_hidden_from_students"])

    if exam.results_hidden_from_students:
        messages.success(
            request,
            pgettext_lazy("exams.view.exams.message", "İmtahan nəticələri tələbələrdən gizlədildi."),
        )
    else:
        messages.success(
            request,
            pgettext_lazy("exams.view.exams.message", "İmtahan nəticələri tələbələrə açıldı."),
        )

    redirect_url = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
    query_string = request.GET.urlencode()
    if query_string:
        redirect_url = f"{redirect_url}?{query_string}"
    return redirect(redirect_url)


@login_required
def delete_exam(request, slug):
    """
    İmtahanı silmək – amma əvvəlcə təsdiq istəyəciyik.
    İmtahan üzrə cəhdlər varsa, onlar da CASCADE ilə birlikdə silinir.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = _get_editable_exam_or_404(request, slug)
    if exam.author_id != request.user.id:
        _ensure_exam_permission(request, "exam.delete")

    if request.method == "POST":
        from apps.audit.utils import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.DELETE,
            user=request.user,
            organization=exam.organization,
            obj=exam,
            old_values={"title": exam.title, "slug": exam.slug},
            reason="exam_deleted",
            request=request,
        )
        _exam_pk = exam.pk
        exam.delete()
        try:
            from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache

            invalidate_exam_metadata_cache(_exam_pk)
            invalidate_exam_question_ids_cache(_exam_pk)
        except Exception:
            pass
        return redirect(_teacher_profile_my_exams_url())

    return render(request, "exams/teacher/confirm_delete_exam.html", {"exam": exam})


@login_required
@require_POST
def toggle_exam_archive(request, slug):
    """
    İmtahanı arxivlə / arxivdən çıxar — soft state (silmə deyil).

    Nəticələr saxlanır; imtahan müəllim panelində "Arxiv" bölməsinə keçir.
    Yalnız POST — təsdiq UI tərəfində verilir.
    """
    from django.utils import timezone

    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = _get_editable_exam_or_404(request, slug)
    if exam.author_id != request.user.id:
        _ensure_exam_permission(request, "exam.edit")

    exam.is_archived = not exam.is_archived
    exam.archived_at = timezone.now() if exam.is_archived else None
    exam.save(update_fields=["is_archived", "archived_at"])

    from apps.audit.utils import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=exam.organization,
        obj=exam,
        new_values={"is_archived": str(exam.is_archived)},
        reason="exam_archived" if exam.is_archived else "exam_unarchived",
        request=request,
    )
    try:
        from core.cache import invalidate_exam_metadata_cache

        invalidate_exam_metadata_cache(exam.pk)
    except Exception:
        pass

    messages.success(
        request,
        (
            pgettext_lazy("exams.view.exams.message", "exam_archived")
            if exam.is_archived
            else pgettext_lazy("exams.view.exams.message", "exam_unarchived")
        ),
    )
    redirect_url = _safe_same_origin_redirect_path(request, request.POST.get("next") or request.GET.get("next"))
    return redirect(redirect_url or _teacher_profile_my_exams_url())


@login_required
@require_POST
def duplicate_exam(request, slug):
    """
    İmtahanı qaralama kimi dublikat et: parametrlər + giriş icazələri + nəzarət
    konfiqurasiyası kopyalanır (suallar yox). Yalnız POST.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, "exam.create")
    exam = _get_editable_exam_or_404(request, slug)

    from apps.exams.services.duplication import duplicate_exam as duplicate_exam_service

    copy = duplicate_exam_service(exam=exam, user=request.user)

    from apps.audit.utils import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=copy.organization,
        obj=copy,
        new_values={"title": copy.title, "duplicated_from": exam.slug},
        reason="exam_duplicated",
        request=request,
    )
    messages.success(request, pgettext_lazy("exams.view.exams.message", "exam_duplicated"))
    return redirect(_teacher_profile_my_exams_url())
