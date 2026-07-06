"""final_center paketi — obyekt-səviyyəli icazələr.

Qayda (mövcud imtahan mərkəzi siyasəti ilə uyğun):

* **İdarəetmə** (zal/oturum yaratmaq, tələbə təyin etmək, PIN vermək) —
  yalnız imtahan mərkəzi (``exam_center`` rolu) və superadmin.
* **Nəzarət** (monitor, start/son, tələbə çıxarma) — imtahan mərkəzi VƏ
  oturuma təyin olunmuş nəzarətçi (invigilator) / dəstək heyəti.
* Tələbə yalnız öz biletinə çıxa bilər.

Bütün yoxlamalar backend-də (view + consumer) tətbiq olunur; frontend
düymələri yalnız görünüşdür.
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import pgettext

from apps.exams.services.access_policy import is_exam_center_user


def can_manage_final_center(user) -> bool:
    return is_exam_center_user(user)


def ensure_can_manage_final_center(user) -> None:
    if can_manage_final_center(user):
        return
    raise PermissionDenied(pgettext("exams.final_center.permission", "Bu əməliyyat yalnız imtahan mərkəzi üçündür."))


def can_supervise_session(user, session) -> bool:
    """Oturumun canlı idarəsi: mərkəz + təyin olunmuş nəzarətçi/heyət."""
    if can_manage_final_center(user):
        return True
    if session.invigilator_id == user.id:
        return True
    return session.staff.filter(id=user.id).exists()


def ensure_can_supervise_session(user, session) -> None:
    if can_supervise_session(user, session):
        return
    raise PermissionDenied(pgettext("exams.final_center.permission", "Bu otağa təyin olunmamısınız."))


def supervised_sessions_q(user) -> Q:
    """İstifadəçinin nəzarətçi/heyət kimi göründüyü oturumlar üçün Q filtri."""
    return Q(invigilator=user) | Q(staff=user)


def sessions_visible_to(user, base_queryset):
    """
    İstifadəçinin görə biləcəyi oturumlar: mərkəz → hamısı (tenant daxilində),
    nəzarətçi/heyət → yalnız təyin olunduqları. Queryset artıq org-scoped
    gəlməlidir.
    """
    if can_manage_final_center(user):
        return base_queryset
    return base_queryset.filter(supervised_sessions_q(user)).distinct()


def ensure_ticket_owner(user, ticket) -> None:
    if ticket.student_id == user.id:
        return
    raise PermissionDenied(pgettext("exams.final_center.permission", "Bu bilet sizə aid deyil."))


def user_is_org_member(user, organization_id) -> bool:
    """Tenant sərhədi: istifadəçinin həmin təşkilatda aktiv üzvlüyü varmı."""
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    from django.apps import apps as django_apps

    Membership = django_apps.get_model("organizations", "Membership")
    return Membership.objects.filter(user=user, organization_id=organization_id, is_active=True).exists()


def can_supervise_session_ws(user, session) -> bool:
    """
    WS bağlantısı üçün tam yoxlama: rol + oturum təyinatı + TENANT üzvlüyü.
    (``is_exam_center_user`` qlobal bayraqdır — org üzvlüyü ayrıca yoxlanır.)
    """
    if not user_is_org_member(user, session.organization_id):
        return False
    return can_supervise_session(user, session)


def user_supervises_final_sessions(user) -> bool:
    """
    Bu istifadəçi (nəzarətçi/heyət kimi) ən azı bir ləğv olunmamış final
    oturumuna təyin olunubmu? Naviqasiya görünürlüyü üçün yüngül .exists()
    yoxlaması (imtahan mərkəzi rolu ayrıca yoxlanır).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from apps.exams.models import ExamRoomSession

    return ExamRoomSession.objects.filter(supervised_sessions_q(user)).exclude(state="cancelled").exists()


__all__ = [
    "can_manage_final_center",
    "can_supervise_session",
    "can_supervise_session_ws",
    "ensure_can_manage_final_center",
    "ensure_can_supervise_session",
    "ensure_ticket_owner",
    "sessions_visible_to",
    "supervised_sessions_q",
    "user_is_org_member",
    "user_supervises_final_sessions",
]
