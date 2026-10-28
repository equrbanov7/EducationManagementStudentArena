"""Görünüş və əməl icazələri — fail-closed.

İki ayrı sual var və onları qarışdırmaq təhlükəlidir:

``can_view``  — «bu müraciəti OXUYA bilərmi?» Sahib, cari şöbənin əhatəli
                emalçısı, İZLƏYƏN şöbənin əhatəli emalçısı, təşkilat üzrə nəzarətçi
                (``can_oversee``: ``application.view_all`` / ``application.manage`` —
                RİM/rektor/prorektor), superuser və təşkilat sahibi. Konkret ünvanlanan
                müraciətin tarixçəsini ümumi manage/view_all açarı genişləndirmir.
``can_act``   — «bu müraciətə QƏRAR verə bilərmi?» CARİ şöbənin əhatəli emalçısı
                və ya «hər müraciəti cavablandıran» RİM şöbəsinin emalçısı
                (``is_universal_responder``, sahib 2026-10-26), müraciət AÇIQ olduqda.
                İzləyən şöbə OXUYUR, ƏMƏL ETMİR.

«Əhatə» ölçüsü: şöbənin ``resolve_by``-ı ``organization``-dursa rol adı
kifayətdir; əks halda üzvlüyün ``scope_unit``-i müraciətin
``current_scope_unit``-ini path prefiksi ilə örtməlidir.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q

from apps.organizations.public import ancestor_unit_ids, request_active_memberships
from core.constants import RoleScopeType
from core.permissions import has_permission

from ..constants import PERM_MANAGE, PERM_VIEW_ALL, RESPONDER_UNIT_CODE, ResolveBy
from ..models import ApplicationUnit, ApplicationWatch


def _is_privileged(user, organization) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    return organization is not None and getattr(organization, "owner_id", None) == user.pk


def active_memberships(user, organization):
    from apps.organizations.models import Membership

    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return []
    cached = getattr(user, "_applications_memberships", None)
    if cached is not None and cached[0] == organization.pk:
        return cached[1]
    # Perf 2026-10-07: middleware-in eyni request-də oxuduğu sətirlər (eyni süzgəc);
    # sıra canlı sorğunun `Membership.Meta.ordering`-i ilə eynidir (`handler_role_for`).
    snapshot = request_active_memberships(user, organization)
    if snapshot is not None:
        memberships = sorted(
            (membership for membership in snapshot if membership.role.is_active),
            key=lambda membership: (not membership.is_primary, membership.role.level),
        )
    else:
        memberships = list(
            Membership.objects.filter(
                user=user,
                organization=organization,
                is_active=True,
                role__organization=organization,
                role__is_active=True,
            ).select_related("role", "scope_unit")
        )
    try:
        user._applications_memberships = (organization.pk, memberships)
    except Exception:  # noqa: BLE001 — AnonymousUser kimi obyektlər immutable ola bilər
        pass
    return memberships


def active_units(organization) -> list:
    """Təşkilatın aktiv ``ApplicationUnit`` kataloqu — request daxilində keşlənir.

    ``handled_unit_ids`` (bir kontekst qurulmasında 7-8 dəfə: ``is_handler_anywhere``,
    tab sayğacları, KPI-lar, ``handled_unit_names``) və marşrutlaşdırma
    (``routing.unit_by_code``) eyni kataloqu dəfələrlə sorğulayırdı — keş olmadan
    hər çağırış ayrı SELECT idi (QA P2-26/P2-6: bölmə açılışında 80+ sorğu, 37-42
    dublikat). ``active_memberships``-dəki eyni keş naxışı (obyekt-atributu).
    """
    if organization is None:
        return []
    cached = getattr(organization, "_applications_units_cache", None)
    if cached is not None:
        return cached
    units = list(ApplicationUnit.objects.filter(organization=organization, is_active=True).order_by("order", "name"))
    try:
        organization._applications_units_cache = units
    except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
        pass
    return units


def user_permissions(user, organization) -> list:
    permissions = set()
    for membership in active_memberships(user, organization):
        permissions.update(membership.role.permissions or [])
    return list(permissions)


def has_app_permission(user, organization, permission: str) -> bool:
    if _is_privileged(user, organization):
        return True
    return has_permission(user_permissions(user, organization), permission)


def can_oversee(user, organization) -> bool:
    """«Bütün müraciətlər» — təşkilatın HƏR müraciətini OXUMAQ (nəzarət, RİM).

    ``application.view_all`` (RİM əməkdaşı, qəyyum) və ya onu ehtiva edən ``application.manage``
    (RİM rəhbəri / rektorat), superuser, təşkilat sahibi. Bu YALNIZ OXUDUR: qərar
    hüququ (``can_act``) və daxili qeydlər (``can_see_internal`` — yalnız ``manage``) vermir.
    """
    if organization is None:
        return False
    if _is_privileged(user, organization):
        return True
    permissions = user_permissions(user, organization)
    if has_permission(permissions, PERM_VIEW_ALL) or has_permission(permissions, PERM_MANAGE):
        return True
    # Hər müraciətə cavab verən (RİM) onları tapmaq üçün «Bütün müraciətlər» tabını da görməlidir.
    return is_universal_responder(user, organization)


def _covers(membership, scope_unit_id, scope_unit_path) -> bool:
    """Üzvlük verilmiş aidiyyət bölməsini örtürmü."""
    if membership.role.scope_type == RoleScopeType.ORGANIZATION:
        return True
    if scope_unit_id is None:
        # Aidiyyət təyin olunmayıb (mərkəzi şöbə və ya əcdad tapılmadı) →
        # rol adı kifayətdir; daraltmaq üçün struktur məlumat yoxdur.
        return True
    if not membership.scope_unit_id:
        return False
    ancestors = set(scope_unit_path or [])
    return str(membership.scope_unit_id) in ancestors


def handles_unit(user, organization, unit: ApplicationUnit, scope_unit) -> bool:
    """İstifadəçi verilmiş şöbəni (verilmiş aidiyyətlə) emal edirmi."""
    if unit is None:
        return False
    if unit.requires_scope and scope_unit is None:
        return False
    role_names = set(unit.role_names)
    if not role_names:
        return False
    scope_unit_id = getattr(scope_unit, "pk", None) if scope_unit is not None else None
    scope_path = ancestor_unit_ids(scope_unit) if scope_unit is not None else []
    if unit.resolve_by == ResolveBy.ORGANIZATION.value:
        scope_unit_id = None
    for membership in active_memberships(user, organization):
        if membership.role.name in role_names and _covers(membership, scope_unit_id, scope_path):
            return True
    return False


def handler_role_for(user, organization, unit: ApplicationUnit) -> str:
    """Aktorun bu şöbədəki rol adı (audit/hadisə snapshot-u üçün)."""
    if unit is None:
        return ""
    role_names = set(unit.role_names)
    for membership in active_memberships(user, organization):
        if membership.role.name in role_names:
            return membership.role.name
    memberships = active_memberships(user, organization)
    return memberships[0].role.name if memberships else ""


def handled_unit_ids(user, organization) -> set:
    """İstifadəçinin rol adına görə emal edə biləcəyi bütün şöbələr."""
    role_names = {membership.role.name for membership in active_memberships(user, organization)}
    if not role_names:
        return set()
    return {unit.pk for unit in active_units(organization) if role_names & set(unit.role_names)}


def responder_unit(organization):
    """«Hər müraciəti cavablandıran» şöbə (``RESPONDER_UNIT_CODE``) — aktiv deyilsə ``None``."""
    return next((unit for unit in active_units(organization) if unit.code == RESPONDER_UNIT_CODE), None)


def is_universal_responder(user, organization) -> bool:
    """RİM şöbəsinin emalçısı — təşkilatın HƏR açıq müraciətinə cavab verə bilər (sahib 2026-10-26).

    Rol adı ŞÖBƏNİN kataloq sətrindən gəlir (``handler_role_names``), sərt kodlaşdırılmır:
    rektorun ``*`` açarı bu hüququ VERMİR — o, «Bütün müraciətlər»i oxuyur, amma RİM deyil.
    Request daxilində istifadəçi obyektində keşlənir (siyahı/detal bir neçə dəfə soruşur).
    """
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return False
    cached = getattr(user, "_applications_responder", None)
    if cached is not None and cached[0] == organization.pk:
        return cached[1]
    unit = responder_unit(organization)
    result = bool(unit is not None and handles_unit(user, organization, unit, None))
    try:
        user._applications_responder = (organization.pk, result)
    except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
        pass
    return result


def is_current_handler(user, application) -> bool:
    """CARİ şöbənin öz emalçısı (RİM-in ümumi cavab hüququ DAXİL DEYİL).

    «Yeni → Baxılır» avtomatik keçidi və şöbəyə «RİM cavab verdi» bildirişi bu fərqə söykənir:
    RİM başqa şöbənin müraciətini sadəcə AÇANDA şöbənin «Yeni» nişanı itməməlidir.
    """
    return (not application.current_unit.requires_recipient or application.assigned_to_id == user.pk) and handles_unit(
        user, application.organization, application.current_unit, application.current_scope_unit
    )


def is_handler_anywhere(user, organization) -> bool:
    return bool(handled_unit_ids(user, organization))


def recipient_restricted(application) -> bool:
    return application.recipient_restricted or application.current_unit.requires_recipient


def watch_is_visible(user, application, watch) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if (watch.unit.requires_recipient or watch.recipient_ids) and user.pk not in (watch.recipient_ids or []):
        return False
    return handles_unit(user, application.organization, watch.unit, watch.scope_unit)


def _can_view_application(user, application) -> bool:
    organization = application.organization
    if _is_privileged(user, organization):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if application.created_by_id == user.pk:
        return True
    if is_universal_responder(user, organization):
        return True
    if not recipient_restricted(application) and can_oversee(user, organization):
        return True
    if is_current_handler(user, application):
        return True
    for watch in application.watches.select_related("unit", "scope_unit"):
        if watch_is_visible(user, application, watch):
            return True
    return False


def can_manage_application(user, application) -> bool:
    """Bütün müraciəti yalnız göndərən, universal RİM və sahib silib bərpa edir."""
    if not _can_view_application(user, application):
        return False
    return bool(
        is_sender(user, application)
        or _is_privileged(user, application.organization)
        or is_universal_responder(user, application.organization)
    )


def can_view(user, application) -> bool:
    if application.deleted_at is not None:
        return can_manage_application(user, application)
    return _can_view_application(user, application)


def can_act(user, application) -> bool:
    """QƏRAR hüququ — yalnız CARİ şöbənin emalçısı, müraciət açıq ikən.

    İzləyən şöbə DAXİL DEYİL (dizayn §6: «only if request.current_unit ==
    user.unit»). Superuser istisna olaraq daxildir — platforma səviyyəli
    dəstək/bərpa əməlləri üçün. RİM şöbəsinin emalçısı da daxildir
    (``is_universal_responder`` — sahib 2026-10-26: «RİM hər müraciəti cavablandıra bilsin»).
    """
    if application.deleted_at is not None or not application.is_open:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if is_current_handler(user, application):
        return True
    return is_universal_responder(user, application.organization)


def can_see_internal(user, application) -> bool:
    """Daxili qeydləri GÖRMƏ hüququ — statusdan ASILI DEYİL (QA 2026-09-05 APPLICATIONS-08).

    ``can_act`` (qərar hüququ) müraciət bağlananda/yönləndiriləndə False olur və
    emalçı ÖZ yazdığı daxili qeydi də görmürdü. Görmə: superuser, `application.manage`
    daşıyıcısı, cari şöbənin emalçısı və ya izləyən (watch) şöbənin emalçısı.
    """
    if application.deleted_at is not None and not can_manage_application(user, application):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    organization = application.organization
    if _is_privileged(user, organization):
        return True
    if not recipient_restricted(application) and has_app_permission(user, organization, PERM_MANAGE):
        return True
    if is_current_handler(user, application):
        return True
    # RİM cavab verəndə yazışmanın daxili qeydlərini də görməlidir (özü də daxili qeyd yaza bilir).
    if is_universal_responder(user, organization):
        return True
    for watch in application.watches.select_related("unit", "scope_unit"):
        if watch_is_visible(user, application, watch):
            return True
    return False


def can_view_attachment(user, attachment) -> bool:
    """Sənəd: müraciətin görünüşü + daxili qeydə bağlıdırsa daxili qeydləri görmə hüququ.

    Təhlükəsizlik auditi 2026-10-07 SEC-04: endirmə ucu və ``/media/applications/``
    siyasəti yalnız ``can_view``-a baxırdı — daxili (emalçı) qeydin sənədi müraciət
    sahibinə açıq idi. Endirmə, media siyasəti və detal siyahısı EYNİ qaydanı işlədir.
    """
    application = attachment.application
    if application.deleted_at is not None:
        return False
    if attachment.event_id and attachment.event.hidden_at:
        return False
    if not can_view(user, application):
        return False
    if attachment.event_id is not None and attachment.event.is_internal:
        return can_see_internal(user, application)
    return True


def is_sender(user, application) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and application.created_by_id == user.pk)


def _unit_scope_q(user, organization, *, unit_field, scope_field) -> Q:
    """``handles_unit`` ilə eyni rol + struktur əhatəsi, list/count üçün.

    Hər rol yalnız öz şöbəsi və öz scope-u ilə cütləşdirilir; başqa rolun
    organization əhatəsi dar ixtisas üzvlüyünü genişləndirə bilməz.
    """
    memberships = active_memberships(user, organization)
    permitted = Q(pk__in=[])
    for unit in active_units(organization):
        for membership in memberships:
            if membership.role.name not in unit.role_names:
                continue
            scope = Q()
            if (
                unit.resolve_by != ResolveBy.ORGANIZATION.value
                and membership.role.scope_type != RoleScopeType.ORGANIZATION
            ):
                scope = Q(pk__in=[]) if unit.requires_scope else Q(**{f"{scope_field}__isnull": True})
                if membership.scope_unit_id:
                    scope |= Q(**{f"{scope_field}_id": membership.scope_unit_id}) | Q(
                        **{f"{scope_field}__path__startswith": f"{membership.scope_unit.path}/"}
                    )
            if unit.requires_scope:
                scope &= Q(**{f"{scope_field}__isnull": False})
            permitted |= Q(**{f"{unit_field}_id": unit.pk}) & scope
    return permitted


def inbox_q(user, organization) -> Q:
    """«Mənə gələnlər» — eyni şöbənin roluna aid əhatə + konkret ünvan."""
    if not handled_unit_ids(user, organization):
        return Q(pk__in=[])
    recipient_q = Q(current_unit__requires_recipient=False) | Q(assigned_to=user)
    return _unit_scope_q(user, organization, unit_field="current_unit", scope_field="current_scope_unit") & recipient_q


def watching_q(user, organization) -> Q:
    if not handled_unit_ids(user, organization):
        return Q(pk__in=[])
    audience = Q(unit__requires_recipient=False, recipient_ids=[]) | Q(recipient_ids__contains=[user.pk])
    watches = ApplicationWatch.objects.filter(application_id=OuterRef("pk"), organization=organization).filter(
        _unit_scope_q(user, organization, unit_field="unit", scope_field="scope_unit") & audience
    )
    # EXISTS bütün şərtləri eyni watch sətrinə bağlayır; başqa şöbənin scope-u
    # və ya recipient siyahısı ilə yanlış JOIN uyğunluğu yarana bilməz.
    return Q(Exists(watches)) & ~inbox_q(user, organization)


def visible_q(user, organization) -> Q:
    """İstifadəçinin ÜMUMİYYƏTLƏ görə bildiyi müraciətlər (bütün tablar)."""
    own_access = Q(created_by=user) | inbox_q(user, organization) | watching_q(user, organization)
    if _is_privileged(user, organization) or is_universal_responder(user, organization):
        return Q()
    if can_oversee(user, organization):
        public = Q(recipient_restricted=False, current_unit__requires_recipient=False)
        return public | own_access
    return own_access


__all__ = [
    "active_memberships",
    "active_units",
    "can_act",
    "can_manage_application",
    "can_oversee",
    "can_view",
    "can_view_attachment",
    "handled_unit_ids",
    "handler_role_for",
    "handles_unit",
    "has_app_permission",
    "inbox_q",
    "is_current_handler",
    "is_handler_anywhere",
    "is_sender",
    "is_universal_responder",
    "responder_unit",
    "user_permissions",
    "visible_q",
    "watching_q",
]
