"""exam_center view paketi — ortaq guard-lar və context helper-ləri."""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext

from apps.exams.models import ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import (
    can_manage_final_center,
    can_supervise_session,
    sessions_visible_to,
)
from apps.exams.views.shared.tenant import ensure_teacher_exam_tenant_context, get_active_organization


def center_org_or_403(request):
    """Tenant konteksti + imtahan mərkəzi icazəsi (idarəetmə səviyyəsi)."""
    ensure_teacher_exam_tenant_context(request)
    organization = get_active_organization(request)
    if organization is None:
        raise PermissionDenied(pgettext("exams.final_center.permission", "Aktiv təşkilat konteksti tapılmadı."))
    if not can_manage_final_center(request.user):
        raise PermissionDenied(
            pgettext("exams.final_center.permission", "Bu əməliyyat yalnız imtahan mərkəzi üçündür.")
        )
    return organization


def supervisor_org_or_403(request):
    """Nəzarətçi səviyyəsi: org konteksti kifayətdir, oturum icazəsi obyekt üzrə yoxlanır."""
    ensure_teacher_exam_tenant_context(request)
    organization = get_active_organization(request)
    if organization is None:
        raise PermissionDenied(pgettext("exams.final_center.permission", "Aktiv təşkilat konteksti tapılmadı."))
    return organization


def get_center_session_or_404(request, session_id, *, for_supervision=False):
    """
    Oturumu tenant daxilində tapır. ``for_supervision=True`` olduqda təyin
    olunmuş nəzarətçi/heyət də buraxılır; əks halda yalnız imtahan mərkəzi.
    """
    if for_supervision:
        organization = supervisor_org_or_403(request)
    else:
        organization = center_org_or_403(request)
    session = get_object_or_404(
        ExamRoomSession.objects.select_related("room", "invigilator", "organization"),
        pk=session_id,
        organization=organization,
    )
    if for_supervision and not can_supervise_session(request.user, session):
        raise PermissionDenied(pgettext("exams.final_center.permission", "Bu otağa təyin olunmamısınız."))
    return organization, session


def get_session_ticket_or_404(session, ticket_id):
    return get_object_or_404(
        FinalExamTicket.objects.select_related("student", "exam", "session", "attempt"),
        pk=ticket_id,
        session=session,
    )


def get_center_ticket_or_404(request, ticket_id):
    """İmtahan-scoped bileti tenant daxilində tapır (oturum sisteminin ləğvindən
    sonra bilet zala yox, imtahana bağlıdır — PIN idarəsi org üzrə)."""
    organization = center_org_or_403(request)
    ticket = get_object_or_404(
        FinalExamTicket.objects.select_related("student", "exam", "session", "attempt", "organization"),
        pk=ticket_id,
        organization=organization,
    )
    return organization, ticket


def visible_sessions_qs(request, organization):
    """İstifadəçiyə görünən oturumlar (mərkəz → hamısı; nəzarətçi → təyinatlıları)."""
    base = ExamRoomSession.objects.filter(organization=organization).select_related("room", "invigilator")
    return sessions_visible_to(request.user, base)


def center_staff_queryset(organization):
    """Nəzarətçi namizədləri: org-un tələbə olmayan aktiv üzvləri (müəllim/mərkəz)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return (
        User.objects.filter(memberships__organization=organization, memberships__is_active=True)
        .exclude(profile__role="student")
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


__all__ = [
    "center_org_or_403",
    "center_staff_queryset",
    "get_center_session_or_404",
    "get_session_ticket_or_404",
    "supervisor_org_or_403",
    "visible_sessions_qs",
]
