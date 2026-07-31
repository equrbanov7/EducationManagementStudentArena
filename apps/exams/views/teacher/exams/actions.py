"""teacher exams paketi — actions."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST

from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.retention import AcademicHistoryProtected, permanently_delete_exam_without_history
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._shared import (
    _ensure_exam_permission,
    _get_deleted_exam_or_404,
    _get_editable_exam_or_404,
    _organization_selection_redirect,
    _resolve_required_organization,
    _safe_same_origin_redirect_path,
    _teacher_profile_my_exams_url,
)

logger = logging.getLogger(__name__)


@login_required
def toggle_exam_active(request, slug):
    """
    Müəllim imtahanı istənilən vaxt dərc/deaktiv edə bilsin.

    Seq3 (EXAM-P1-01): keçid atomikdir (şərti UPDATE) — paralel tab/müəllim
    double-flip edə bilməz; publish qapısı (aktiv sual + dil parity) keçilməsə
    imtahan qaralama qalır. Forma müəllimin GÖRDÜYÜ niyyəti ``desired_state``
    ilə göndərir; köhnə (parametrsiz) formalar cari vəziyyətdən flip edir.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, "exam.edit")
    exam = get_teacher_exam_or_404(request, slug=slug)

    if request.method == "POST":
        from apps.exams.services.lifecycle import publish_exam, unpublish_exam

        desired_raw = request.POST.get("desired_state")
        want_active = desired_raw == "1" if desired_raw in {"0", "1"} else not exam.is_active
        if want_active:
            changed, error = publish_exam(exam, by_user=request.user, request=request)
            if error:
                messages.error(request, error)
                return redirect("exams:teacher_exam_detail", slug=exam.slug)
            if changed:
                from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup
                from apps.notifications.public import get_exam_assigned_user_ids, notify_task_assignment

                schedule_ai_question_difficulty_warmup(exam)
                notify_task_assignment(
                    task=exam,
                    user_ids=get_exam_assigned_user_ids(exam),
                    task_kind="exam",
                )
        else:
            unpublish_exam(exam, by_user=request.user, request=request)
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

    # Seq3: nəticə görünürlüyü də atomik keçiddir (paralel tab double-flip etməsin).
    from apps.exams.services.lifecycle import set_results_hidden

    desired_raw = request.POST.get("desired_state")
    want_hidden = desired_raw == "1" if desired_raw in {"0", "1"} else not exam.results_hidden_from_students
    changed = set_results_hidden(
        exam,
        want_hidden,
        by_user=request.user,
        request=request,
    )

    # EXAM-P1-20: nəticə görünürlük dəyişikliyini SLI kimi qeyd et.
    if changed:
        from apps.exams.metrics import record_result_published

        record_result_published("hidden" if exam.results_hidden_from_students else "published")

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
    İmtahanı sil — YUMŞAQ silmə (soft delete).

    İmtahan sətri və bütün cəhdlər/nəticələr bazada saxlanır: yalnız
    ``is_deleted`` işarələnir və imtahan bütün siyahılardan çıxarılır
    ("Zibil qutusu"na keçir). Nəticələr itmir; müəllim istəsə imtahanı
    bərpa edə və ya "Zibil qutusu"ndan birdəfəlik (CASCADE) silə bilər.
    """
    from django.utils import timezone

    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = _get_editable_exam_or_404(request, slug)
    if exam.author_id != request.user.id:
        _ensure_exam_permission(request, "exam.delete")

    if request.method == "POST":
        from apps.audit.public import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.DELETE,
            user=request.user,
            organization=exam.organization,
            obj=exam,
            old_values={"title": exam.title, "slug": exam.slug},
            reason="exam_soft_deleted",
            request=request,
        )
        # Soft delete — nəticələr qorunur. İmtahanı tələbələr üçün də bağlayırıq
        # (is_active=False) ki, silinmiş imtahan heç bir yerdə aktiv görünməsin.
        exam.is_deleted = True
        exam.deleted_at = timezone.now()
        exam.is_active = False
        exam.save(update_fields=["is_deleted", "deleted_at", "is_active"])
        try:
            from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache

            invalidate_exam_metadata_cache(exam.pk)
            invalidate_exam_question_ids_cache(exam.pk)
        except Exception:
            # Best-effort cache cleanup after delete: entries expire on their
            # own TTL, so failure must not block the delete — but log it.
            logger.warning(
                "Exam cache invalidation failed after soft-delete of exam %s",
                exam.pk,
                exc_info=True,
            )
        messages.success(
            request,
            pgettext_lazy("exams.view.exams.message", "exam_soft_deleted"),
        )
        return redirect(_teacher_profile_my_exams_url())

    # JS-siz geri düşmə: silmə düymələri `<a href>` olduğu üçün GET gələ bilər
    # (yeni tabda aç / orta klik / JS sınıb). Ümumi təsdiq səhifəsi göstərilir.
    return render(
        request,
        "exams/teacher/confirm_delete.html",
        {
            "confirm_title": pgettext("exams.view.exams.confirm", "delete_exam_title"),
            "confirm_message": pgettext("exams.view.exams.confirm", "delete_exam_message"),
            "confirm_target": exam.title,
            "confirm_action": reverse("exams:delete_exam", kwargs={"slug": exam.slug}),
            "cancel_url": reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
        },
    )


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

    from apps.audit.public import log_action
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
        # Best-effort: stale metadata self-heals on its next TTL, so an
        # archive toggle must not fail on cache errors — but log for visibility.
        logger.warning(
            "Exam metadata cache invalidation failed for exam %s",
            exam.pk,
            exc_info=True,
        )

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

    from apps.audit.public import log_action
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


@login_required
def deleted_exams_list(request):
    """ "Zibil qutusu" — müəllimin yumşaq silinmiş imtahanları.

    Silinmiş imtahanların sətri və nəticələri qorunur; buradan onlara baxıla,
    imtahan bərpa oluna və ya birdəfəlik (CASCADE) silinə bilər. Hər imtahan
    üçün saxlanan cəhd (nəticə) sayı göstərilir.
    """
    from django.db.models import Count

    from apps.exams.models import Exam
    from apps.exams.views.shared.tenant import tenant_scoped_exams

    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)

    deleted_exams = (
        tenant_scoped_exams(
            request,
            Exam.objects.filter(author=request.user, is_deleted=True),
            include_deleted=True,
        )
        .annotate(attempts_total=Count("attempts", distinct=True))
        .order_by("-deleted_at", "-created_at")
    )
    return render(
        request,
        "exams/teacher/deleted_exams.html",
        {"deleted_exams": list(deleted_exams)},
    )


@login_required
@require_POST
def restore_exam(request, slug):
    """Yumşaq silinmiş imtahanı "Zibil qutusu"ndan bərpa et.

    ``is_deleted`` təmizlənir və imtahan siyahılara qayıdır. ``is_active`` toxunulmur
    — bərpa olunan imtahan qaralama kimi qalır; müəllim onu ayrıca yenidən dərc edir.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = _get_deleted_exam_or_404(request, slug)
    if exam.author_id != request.user.id:
        _ensure_exam_permission(request, "exam.delete")

    exam.is_deleted = False
    exam.deleted_at = None
    exam.save(update_fields=["is_deleted", "deleted_at"])

    from apps.audit.public import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=exam.organization,
        obj=exam,
        new_values={"is_deleted": "False"},
        reason="exam_restored",
        request=request,
    )
    try:
        from core.cache import invalidate_exam_metadata_cache

        invalidate_exam_metadata_cache(exam.pk)
    except Exception:
        logger.warning(
            "Exam metadata cache invalidation failed after restore of exam %s",
            exam.pk,
            exc_info=True,
        )

    messages.success(request, pgettext_lazy("exams.view.exams.message", "exam_restored"))
    return redirect("exams:deleted_exams_list")


@login_required
@require_POST
def permanent_delete_exam(request, slug):
    """Boş imtahanı "Zibil qutusu"ndan birdəfəlik sil.

    Akademik cəhd/nəticə varsa retention qaydası fiziki silməni bloklayır;
    müəllim həmin imtahanı arxivdə saxlamalıdır. Yalnız artıq yumşaq silinmiş,
    heç bir cəhdi olmayan imtahan fiziki silinə bilər.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = _get_deleted_exam_or_404(request, slug)
    if exam.author_id != request.user.id:
        _ensure_exam_permission(request, "exam.delete")

    try:
        _exam_pk = permanently_delete_exam_without_history(
            exam,
            actor=request.user,
            request=request,
        )
    except AcademicHistoryProtected as exc:
        messages.error(request, exc.messages[0])
        return redirect("exams:deleted_exams_list")
    try:
        from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache

        invalidate_exam_metadata_cache(_exam_pk)
        invalidate_exam_question_ids_cache(_exam_pk)
    except Exception:
        logger.warning(
            "Exam cache invalidation failed after permanent delete of exam %s",
            _exam_pk,
            exc_info=True,
        )

    messages.success(request, pgettext_lazy("exams.view.exams.message", "exam_permanently_deleted"))
    return redirect("exams:deleted_exams_list")
