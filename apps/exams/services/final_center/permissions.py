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


def can_supervise_session(user, session, *, scope=None) -> bool:
    """Oturumun canlı idarəsi: mərkəz + İNDİ aktiv növbəsi olan nəzarətçi.

    2026-10-13 (gecə): nəzarətçi çıxışı artıq DAİMİ deyil — ``duties.supervision_scope``
    sorğu anında hesablayır (``InvigilatorDuty`` pəncərəsi; köhnə zal M2M və
    oturum-səviyyəli ``invigilator``/``staff`` yalnız oturum canlı olanda). Növbə
    bitən kimi bu funksiya False qaytarır — monitor, snapshot, WS, şəkil hamısı bağlanır.
    ``scope`` — eyni sorğuda çoxlu oturum yoxlanırsa bir dəfə hesablanmış əhatə.
    """
    if can_manage_final_center(user):
        return True
    if scope is None:
        from .duties import supervision_scope

        scope = supervision_scope(user, organization_id=session.organization_id)
    return scope.allows_session(session)


def ensure_can_supervise_session(user, session) -> None:
    if can_supervise_session(user, session):
        return
    raise PermissionDenied(pgettext("exams.final_center.permission", "Bu otağa təyin olunmamısınız."))


def supervised_sessions_q(user) -> Q:
    """İstifadəçinin nəzarətçi kimi İNDİ göründüyü oturumlar üçün Q filtri (vaxtla məhdud)."""
    from .duties import supervision_scope

    return supervision_scope(user).sessions_q()


def sessions_visible_to(user, base_queryset):
    """
    İstifadəçinin görə biləcəyi oturumlar: mərkəz → hamısı (tenant daxilində),
    nəzarətçi → yalnız İNDİ aktiv növbəsinin zalları/oturumları. Queryset artıq
    org-scoped gəlməlidir.
    """
    if can_manage_final_center(user):
        return base_queryset
    return base_queryset.filter(supervised_sessions_q(user)).distinct()


def can_enter_supervision_surface(user, organization) -> bool:
    """Nəzarət səthinə (otaqlar/monitor/statistika) GİRİŞ hüququ.

    2026-09-02 audit, P2-1: ``supervisor_org_or_403`` yalnız «aktiv təşkilat
    varmı» deyə soruşurdu, rol/təyinat yoxlamırdı — nəticədə İSTƏNİLƏN
    autentifikasiya olunmuş üzv, hətta TƏLƏBƏ, ``GET /exams/center/rooms/``
    səhifəsini 200 ilə alırdı.

    İcazə: imtahan mərkəzi VƏ YA bu tenantda İNDİ aktiv nəzarət növbəsi olan istifadəçi
    (2026-10-13: köhnə «ən azı bir dəfə təyin olunub» qaydası daimi çıxış verirdi).
    """
    if organization is None:
        return False
    if can_manage_final_center(user):
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    from .duties import supervision_scope

    return not supervision_scope(user, organization_id=organization.pk).is_empty


def ensure_can_enter_supervision_surface(user, organization) -> None:
    if can_enter_supervision_surface(user, organization):
        return
    raise PermissionDenied(
        pgettext("exams.final_center.permission", "Bu bölmə yalnız imtahan mərkəzi və nəzarətçilər üçündür.")
    )


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


def can_view_final_history(user, organization) -> bool:
    """
    Final imtahan TARİXÇƏSİNƏ kim baxa bilər — yuxarı səviyyələr:

    * imtahan mərkəzi rəhbəri (``exam_center``),
    * superadmin,
    * təşkilat sahibi / admini (rektor / prorektor səviyyəsi).

    Nəzarətçi/müəllim tarixçəni GÖRMÜR (yalnız canlı monitor).
    """
    if can_manage_final_center(user):
        return True
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if organization is not None and getattr(organization, "owner_id", None) == getattr(user, "id", None):
        return True
    from core.roles import ProfileRole

    profile = getattr(user, "profile", None)
    return profile is not None and getattr(profile, "role", None) in (ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER)


def ensure_can_view_final_history(user, organization) -> None:
    if can_view_final_history(user, organization):
        return
    raise PermissionDenied(pgettext("exams.final_center.permission", "Tarixçəyə baxış üçün icazəniz yoxdur."))


def user_supervises_final_sessions(user) -> bool:
    """
    Bu istifadəçinin İNDİ aktiv nəzarət növbəsi varmı? Kabinet naviqasiyasının
    («İmtahan Nəzarət Sistemi» bəndi) görünürlüyü üçün — növbə bitəndə bənd özü itir
    (2026-10-13; əvvəl istənilən ləğv olunmamış keçmiş oturum bəndi daimi saxlayırdı).
    İmtahan mərkəzi rolu ayrıca yoxlanır.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    from .duties import supervision_scope

    return not supervision_scope(user).is_empty


__all__ = [
    "can_manage_final_center",
    "can_supervise_session",
    "can_supervise_session_ws",
    "can_view_final_history",
    "ensure_can_manage_final_center",
    "ensure_can_supervise_session",
    "ensure_can_view_final_history",
    "ensure_ticket_owner",
    "sessions_visible_to",
    "supervised_sessions_q",
    "user_is_org_member",
    "user_supervises_final_sessions",
]
