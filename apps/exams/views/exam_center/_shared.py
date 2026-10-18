"""exam_center view paketi — ortaq guard-lar və context helper-ləri."""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext

from apps.exams.models import ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import (
    can_manage_final_center,
    can_supervise_session,
    ensure_can_enter_supervision_surface,
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
    """Nəzarətçi səviyyəsi: mərkəz VƏ YA bu tenantda təyinatı olan nəzarətçi.

    2026-09-02 audit, P2-1: əvvəl «aktiv təşkilat varmı» yeganə şərt idi, ona
    görə tələbə də ``/exams/center/rooms/`` səthini 200 ilə açırdı.  Obyekt
    səviyyəli yoxlama (``can_supervise_session``) öz yerində qalır — bu, səthin
    ÖZÜNƏ giriş qapısıdır.
    """
    ensure_teacher_exam_tenant_context(request)
    organization = get_active_organization(request)
    if organization is None:
        raise PermissionDenied(pgettext("exams.final_center.permission", "Aktiv təşkilat konteksti tapılmadı."))
    ensure_can_enter_supervision_surface(request.user, organization)
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


#: Nəzarətçi ola BİLMƏYƏN rollar — tələbə ailəsi və neytral doldurucu (``member``).
_NON_STAFF_ROLE_NAMES = ("student", "lead_student", "alumni", "member")


def center_staff_queryset(organization):
    """Nəzarətçi namizədləri — YALNIZ heyət (müəllim / əməkdaş).

    2026-10-18 (sahib: «burda tələbələri göstərmə, kimləri nəzarətçi seçə bilərəmsə elə göstər»): əvvəl yalnız
    ``profile.role == "student"`` çıxarılırdı — starosta, məzun, profili fərqli tələbə, deaktiv / silinmiş hesab və
    rolsuz «üzv» siyahıya düşürdü. İndi müsbət qayda: aktiv hesab, girişi bağlı olmayan profil və bu təşkilatda heyət
    rolu ilə AKTİV üzvlük (aktiv rol). ``eligible_invigilators`` də bu sorğu üzərində qurulur — axtarış və yazı eynidir.
    """
    from django.apps import apps as django_apps
    from django.contrib.auth import get_user_model
    from django.db.models import Exists, OuterRef

    from apps.organizations.models import Membership

    # Model `get_model` ilə — exams → accounts statik importu modul dövrü yaradır (accounts ↔ exams).
    access = django_apps.get_model("accounts", "UserProfile").AccessState
    blocked_states = (access.STAGED, access.ARCHIVED)  # = accounts.identity.login_blocked_access_states()

    User = get_user_model()
    staff_membership = Membership.objects.filter(
        user_id=OuterRef("pk"), organization=organization, is_active=True, role__is_active=True
    ).exclude(role__name__in=_NON_STAFF_ROLE_NAMES)
    return (
        User.objects.filter(is_active=True)
        .filter(Exists(staff_membership))
        .exclude(profile__is_deleted=True)
        .exclude(profile__access_state__in=blocked_states)
        .exclude(profile__role__in=("student", "lead_student"))
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
