"""
"View as" (istifadəçi profilinə baxış) servisi.

Dünya təcrübəsindəki "impersonation" (məs. django-hijack, GitHub staff view,
Stripe "view as customer") nümunəsinə uyğun:

- Səlahiyyətli rol filterdən istifadəçi seçir → request.user müvəqqəti olaraq
  həmin istifadəçi ilə əvəzlənir (``ViewAsMiddleware``), beləcə bütün mövcud
  view-lar (profil, imtahanlar, nəticələr, kurslar...) heç bir dəyişiklik
  olmadan hədəf istifadəçinin datasını göstərir.
- Rejimlər:
    * FULL      — hədəfin edə bildiyi hər şeyi etmək olar (audit-ə yazılır).
    * READONLY  — yalnız baxış; bütün unsafe (POST/PUT/...) sorğular bloklanır.

Təhlükəsizlik prinsipləri:
- Tenant izolyasiyası pozulmur: swap-dan sonra RLS/org konteksti HƏDƏF
  istifadəçinin üzvlüyü üzərində qurulur — aktor öz icazəsindən artıq heç nə
  görə bilməz (superadmin istisna, o, onsuz da qlobal səlahiyyətlidir).
- Hər sorğuda hədəf yenidən yüklənir; icazə ``PERMISSION_RECHECK_SECONDS``
  intervalı ilə tam yenidən yoxlanılır (rol/üzvlük dəyişsə sessiya dərhal bitir).
- Heç vaxt: superuser hədəf ola bilməz, nested view-as yoxdur, hədəfin
  şifrə dəyişmə / hesab silmə əməliyyatları hər iki rejimdə bloklanır.
- Start/stop və FULL rejimdəki bütün unsafe əməliyyatlar audit jurnalına yazılır.
"""

import logging
from datetime import datetime
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db.models import Max, Q

from core.rls import bypass_rls

from ..models import ProfileRole

logger = logging.getLogger(__name__)

User = get_user_model()

VIEW_AS_SESSION_KEY = "view_as_state"

MODE_FULL = "full"
MODE_READONLY = "readonly"

#: FULL rejim — hədəfin adından hər şeyi etmək olar (audit ilə).
FULL_ACCESS_ROLE_NAMES = {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}
#: READONLY rejim — yalnız baxış (tyutor/dekan/kafedra müdürü/HR).
READONLY_ROLE_NAMES = {"tutor", "dean", "vice_dean", "department_head", ProfileRole.HR}
#: Bu rollar üçün hədəflər öz unit alt-ağacı ilə məhdudlaşır.
UNIT_SCOPED_ROLE_NAMES = {"tutor", "dean", "vice_dean", "department_head"}

#: İcazənin tam yenidən yoxlanma intervalı (saniyə). Aralıq sorğularda yalnız
#: hədəf istifadəçi yüklənir — performans üçün hər sorğuda 3-4 əlavə sorğu yoxdur.
PERMISSION_RECHECK_SECONDS = 60

ROLE_FILTER_MAP = {
    "teacher": {
        ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER,
        "instructor",
        "professor",
        "associate_professor",
        "assistant",
        "lab_assistant",
    },
    "student": {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT},
    "admin": {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN, "rector", "vice_rector"},
    "staff": {
        ProfileRole.HR,
        ProfileRole.MEMBER,
        "exam_center",
        "tutor",
        "dean",
        "vice_dean",
        "department_head",
    },
}

SEARCH_PAGE_SIZE = 20


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def _active_memberships(user, organization):
    """Aktorun org daxilindəki aktiv üzvlükləri (role ilə birgə)."""
    from apps.organizations.models import Membership

    return list(
        Membership.objects.filter(user=user, organization=organization, is_active=True).select_related(
            "role", "scope_unit"
        )
    )


def _normalized_role_names(memberships):
    names = set()
    for membership in memberships:
        raw = getattr(membership.role, "name", "") or ""
        names.add(ProfileRole.normalize_membership_role_name(raw))
    return names


def resolve_actor_access(user, organization, *, memberships=None):
    """
    Aktorun bu org üçün view-as səlahiyyətini qaytarır:
    ``(mode, actor_level, memberships)`` və ya icazə yoxdursa ``(None, 0, [])``.
    """
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return None, 0, []

    if _is_superadmin(user):
        return MODE_FULL, 999, []

    if memberships is None:
        memberships = _active_memberships(user, organization)

    is_owner = getattr(organization, "owner_id", None) == user.pk
    role_names = _normalized_role_names(memberships)
    levels = [getattr(m.role, "level", 0) or 0 for m in memberships]
    actor_level = max(levels or [0])
    if is_owner:
        actor_level = max(actor_level, ProfileRole.LEVELS[ProfileRole.ORG_OWNER])

    if is_owner or (role_names & FULL_ACCESS_ROLE_NAMES) or actor_level >= ProfileRole.LEVELS[ProfileRole.ORG_ADMIN]:
        return MODE_FULL, actor_level, memberships

    if role_names & READONLY_ROLE_NAMES:
        return MODE_READONLY, actor_level, memberships

    return None, 0, []


def actor_can_use_view_as(user, organization) -> bool:
    """Panelin görünürlüyü üçün ucuz yoxlama (superadmin org-suz da görür)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if organization is None:
        return False
    mode, _level, _m = resolve_actor_access(user, organization)
    return mode is not None


def _unit_scope_user_ids(user, organization, memberships):
    """Unit-scoped rollar üçün icazəli hədəf user id-ləri (yoxdursa None)."""
    role_names = _normalized_role_names(memberships)
    if not (role_names & UNIT_SCOPED_ROLE_NAMES):
        return None

    from apps.organizations.models import Membership
    from apps.organizations.scoping import get_unit_scope, scope_memberships_by_unit

    scope = get_unit_scope(user, organization)
    if scope.is_org_wide:
        return None
    scoped = scope_memberships_by_unit(
        Membership.objects.filter(organization=organization, is_active=True),
        scope,
        organization,
    )
    return scoped.values("user_id")


def build_target_queryset(actor, organization, *, mode, actor_level, memberships, q="", role_filter=""):
    """
    Aktorun baxa biləcəyi hədəf istifadəçilərin queryset-i.

    Qaydalar:
    - yalnız org-un aktiv üzvləri, aktiv hesablar;
    - superuser hədəf OLA BİLMƏZ, aktor özü siyahıda yoxdur;
    - qeyri-superadmin üçün ciddi iyerarxiya: hədəfin maksimum rol səviyyəsi
      aktorunkundan AŞAĞI olmalıdır;
    - unit-scoped rollar (tyutor/dekan/kafedra müdürü) yalnız öz alt-ağacını görür.
    """
    is_superadmin = actor_level >= 999

    users = (
        User.objects.filter(
            is_active=True,
            memberships__organization=organization,
            memberships__is_active=True,
        )
        .exclude(is_superuser=True)
        .exclude(pk=getattr(actor, "pk", None))
        .annotate(_max_org_level=Max("memberships__role__level", filter=Q(memberships__organization=organization)))
        .distinct()
    )

    if not is_superadmin:
        users = users.filter(_max_org_level__lt=actor_level)
        # Org sahibi hədəf ola bilməz (yalnız sahibin özü/superadmin idarə edir).
        owner_id = getattr(organization, "owner_id", None)
        if owner_id:
            users = users.exclude(pk=owner_id)

        scoped_ids = _unit_scope_user_ids(actor, organization, memberships)
        if scoped_ids is not None:
            users = users.filter(pk__in=scoped_ids)

    q = (q or "").strip()[:120]
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
            | Q(profile__student_group_number__icontains=q)
        )

    role_filter = (role_filter or "").strip()
    role_names = ROLE_FILTER_MAP.get(role_filter)
    if role_names:
        users = users.filter(
            memberships__organization=organization,
            memberships__is_active=True,
            memberships__role__name__in=_expand_role_aliases(role_names),
        )

    return users.order_by("first_name", "last_name", "username", "id")


def _expand_role_aliases(normalized_names):
    """Normalizasiya xəritəsinin tərsi: DB-dəki xam rol adlarını da əhatə et."""
    expanded = set(normalized_names)
    for raw, normalized in ProfileRole.ROLE_NAME_NORMALIZATION.items():
        if normalized in normalized_names:
            expanded.add(raw)
    return expanded


def validate_target(actor, organization, target_user_id):
    """
    Hədəfi yoxlayıb ``(target_user, mode)`` qaytarır, icazə yoxdursa ``(None, None)``.
    """
    mode, actor_level, memberships = resolve_actor_access(actor, organization)
    if mode is None:
        return None, None

    if target_user_id in (None, "") or str(target_user_id) == str(getattr(actor, "pk", None)):
        return None, None

    try:
        qs = build_target_queryset(
            actor,
            organization,
            mode=mode,
            actor_level=actor_level,
            memberships=memberships,
        ).filter(pk=target_user_id)

        if actor_level >= 999:
            with bypass_rls():
                target = qs.first()
        else:
            target = qs.first()
    except (TypeError, ValueError):
        # Yanlış formatlı pk (məs. int pk üçün qeyri-rəqəm) → icazə yoxdur.
        return None, None

    if target is None:
        return None, None
    return target, mode


# ---------------------------------------------------------------------------
# Sessiya idarəetməsi
# ---------------------------------------------------------------------------


def get_view_as_state(request):
    state = request.session.get(VIEW_AS_SESSION_KEY)
    return state if isinstance(state, dict) else None


def start_view_as(request, target_user, organization, mode):
    """View-as sessiyasını başladır; aktiv org-u hədəfin org-una keçirir."""
    from apps.audit.utils import log_action
    from core.constants import AuditAction

    # QEYD: pk-lar str kimi saxlanılır — Organization UUID pk istifadə edir və
    # sessiya JSON serializer-i UUID obyektini qəbul etmir.
    now_iso = datetime.now(dt_timezone.utc).isoformat()
    request.session[VIEW_AS_SESSION_KEY] = {
        "target_id": str(target_user.pk),
        "org_id": str(organization.pk),
        "org_slug": organization.slug,
        "mode": mode,
        "real_id": str(request.user.pk),
        "prev_org_slug": request.session.get("active_organization") or "",
        "started_at": now_iso,
        "checked_at": now_iso,
    }
    request.session["active_organization"] = organization.slug

    log_action(
        action=AuditAction.VIEW,
        user=request.user,
        organization=organization,
        obj=target_user,
        reason="view_as_start",
        changes={"mode": mode, "target_username": target_user.username},
        request=request,
    )
    logger.info(
        "view_as start: actor=%s target=%s org=%s mode=%s",
        request.user.pk,
        target_user.pk,
        organization.pk,
        mode,
    )


def stop_view_as(request, *, reason="view_as_stop"):
    """View-as sessiyasını bitirir və əvvəlki org kontekstini bərpa edir."""
    state = request.session.pop(VIEW_AS_SESSION_KEY, None)
    if not isinstance(state, dict):
        return None

    prev_org_slug = state.get("prev_org_slug") or ""
    if prev_org_slug:
        request.session["active_organization"] = prev_org_slug
    else:
        request.session.pop("active_organization", None)

    try:
        from apps.audit.utils import log_action
        from apps.organizations.models import Organization
        from core.constants import AuditAction

        with bypass_rls():
            organization = Organization.objects.filter(pk=state.get("org_id")).first()
        real_user = getattr(request, "real_user", None) or request.user
        log_action(
            action=AuditAction.VIEW,
            user=real_user if getattr(real_user, "is_authenticated", False) else None,
            organization=organization,
            reason=reason,
            changes={"mode": state.get("mode"), "target_id": state.get("target_id")},
            request=request,
        )
    except Exception:  # noqa: BLE001 — audit xətası çıxışı bloklamamalıdır
        logger.exception("view_as stop audit log failed")
    return state


def resolve_view_as_request(request):
    """
    Middleware üçün: aktiv view-as sessiyasını yoxlayıb
    ``(target_user, mode)`` qaytarır; etibarsızdırsa sessiyanı bitirib
    ``(None, None)`` qaytarır.
    """
    state = get_view_as_state(request)
    if not state:
        return None, None

    real_user = request.user
    # Sessiya başqa istifadəçiyə keçibsə (qorunma) və ya org konteksti dəyişibsə → bitir.
    if str(state.get("real_id")) != str(getattr(real_user, "pk", None)):
        stop_view_as(request, reason="view_as_invalid_real_user")
        return None, None
    if (request.session.get("active_organization") or "") != (state.get("org_slug") or ""):
        stop_view_as(request, reason="view_as_org_context_changed")
        return None, None

    mode = state.get("mode")
    if mode not in {MODE_FULL, MODE_READONLY}:
        stop_view_as(request, reason="view_as_invalid_mode")
        return None, None

    needs_full_check = True
    checked_at = state.get("checked_at")
    if checked_at:
        try:
            parsed = datetime.fromisoformat(checked_at)
            needs_full_check = (datetime.now(dt_timezone.utc) - parsed).total_seconds() >= PERMISSION_RECHECK_SECONDS
        except ValueError:
            needs_full_check = True

    from apps.organizations.models import Organization

    with bypass_rls():
        organization = Organization.objects.filter(pk=state.get("org_id"), is_active=True, status="active").first()
    if organization is None:
        stop_view_as(request, reason="view_as_org_unavailable")
        return None, None

    if needs_full_check:
        target, fresh_mode = validate_target(real_user, organization, state.get("target_id"))
        if target is None or fresh_mode != mode:
            stop_view_as(request, reason="view_as_permission_revoked")
            return None, None
        state["checked_at"] = datetime.now(dt_timezone.utc).isoformat()
        request.session[VIEW_AS_SESSION_KEY] = state
    else:
        with bypass_rls():
            target = User.objects.filter(pk=state.get("target_id"), is_active=True).exclude(is_superuser=True).first()
        if target is None:
            stop_view_as(request, reason="view_as_target_unavailable")
            return None, None

    return target, mode
