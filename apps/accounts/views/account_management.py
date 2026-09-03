"""
Account management views: account deletion and superadmin user management.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.staff_position import resolve_position_label

from ..models import ProfileRole
from ..services.account_deletion import (
    AccountDeletionError,
    block_account,
    hard_delete_account,
    restore_account,
    soft_delete_account,
    unblock_account,
)
from ._helpers import (
    PROFILE_ROLE_LABELS,
    _append_query_params,
    _is_superadmin_user,
    _query_string,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)
User = get_user_model()
USER_PAGE_SIZE = 15
USER_STATUS_ALL = "all"
USER_STATUS_ACTIVE = "active"
USER_STATUS_BLOCKED = "blocked"
USER_STATUS_DELETED = "deleted"
USER_ORG_FILTER_NONE = "__none__"
USER_SORT_NEWEST = "newest"
USER_SORT_OLDEST = "oldest"
USER_SORT_USERNAME = "username"
USER_SORT_NAME = "name"
USER_SORT_LAST_LOGIN = "last_login"


def _safe_user_profile(user):
    try:
        return user.profile
    except ObjectDoesNotExist:
        return None


def _superadmin_user_status_key(user, profile=None):
    user_profile = profile if profile is not None else _safe_user_profile(user)
    if user_profile and user_profile.is_deleted:
        return USER_STATUS_DELETED
    if user.is_active:
        return USER_STATUS_ACTIVE
    return USER_STATUS_BLOCKED


def _mask_email_address(email):
    normalized = str(email or "").strip()
    if not normalized:
        return "-"
    if len(normalized) <= 24:
        return normalized
    return f"{normalized[:10]}...{normalized[-10:]}"


def _build_superadmin_user_row(user, *, actor=None):
    profile = _safe_user_profile(user)
    status_key = _superadmin_user_status_key(user, profile)
    status_label = {
        USER_STATUS_ACTIVE: "Aktiv",
        USER_STATUS_BLOCKED: "Bloklanıb",
        USER_STATUS_DELETED: "Silinib",
    }.get(status_key, "Naməlum")
    status_badge_class = {
        USER_STATUS_ACTIVE: "status-badge status-badge--active",
        USER_STATUS_BLOCKED: "status-badge status-badge--blocked",
        USER_STATUS_DELETED: "status-badge status-badge--deleted",
    }.get(status_key, "status-badge")

    # ⚠️ Doldurucu «Üzv» rolu etiket kimi yazılmır — sütun «-» qalır; əvəzinə
    # profildə vəzifə varsa o göstərilir (bax core/staff_position.py).
    role_label = "-"
    if getattr(user, "is_superuser", False):
        role_label = PROFILE_ROLE_LABELS.get(ProfileRole.SUPERADMIN, "Super Admin")
    elif profile:
        resolved = resolve_position_label(
            staff_position=getattr(profile, "staff_position", "") or "",
            role_name=profile.role or "",
            role_label=str(PROFILE_ROLE_LABELS.get(profile.role, profile.get_role_display() if profile.role else "")),
        )
        role_label = resolved or "-"

    organization_name = "-"
    if profile:
        if profile.organization_id and profile.organization:
            organization_name = profile.organization.name
        elif not profile.is_deleted:
            organization_name = profile.organization_name

    is_self = bool(actor and actor.pk == user.pk)
    is_superadmin_account = _is_superadmin_user(user)
    can_moderate = not is_self and not is_superadmin_account

    return {
        "user": user,
        "profile": profile,
        "username": user.username,
        "email": user.email or "-",
        "email_display": _mask_email_address(user.email) if status_key == USER_STATUS_DELETED else (user.email or "-"),
        "full_name": user.get_full_name() or "-",
        "role_label": role_label,
        "organization_name": organization_name,
        "group_number": profile.student_group_number if profile and profile.student_group_number else "-",
        "department": profile.department if profile and profile.department else "-",
        "status_key": status_key,
        "status_label": status_label,
        "status_badge_class": status_badge_class,
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        "deleted_at": profile.deleted_at if profile else None,
        "is_self": is_self,
        "is_superadmin_account": is_superadmin_account,
        "can_block": can_moderate and status_key == USER_STATUS_ACTIVE,
        "can_unblock": can_moderate and status_key == USER_STATUS_BLOCKED,
        "can_soft_delete": can_moderate and status_key in {USER_STATUS_ACTIVE, USER_STATUS_BLOCKED},
        "can_restore": can_moderate and status_key == USER_STATUS_DELETED,
        "can_hard_delete": can_moderate and status_key == USER_STATUS_DELETED,
        "restriction_label": "Cari hesab" if is_self else ("Superadmin hesabı" if is_superadmin_account else ""),
    }


def build_superadmin_user_management_context(request, *, base_url=None, include_section=False):
    from apps.organizations.models import Organization

    search_query = (request.GET.get("user_search") or "").strip()[:120]
    status_filter = (request.GET.get("user_status") or USER_STATUS_ALL).strip().lower()
    role_filter = (request.GET.get("user_role") or "").strip().lower()
    organization_filter = (request.GET.get("user_org") or "").strip()
    group_filter = (request.GET.get("user_group") or "").strip()[:100]
    department_filter = (request.GET.get("user_department") or "").strip()[:100]
    sort_filter = (request.GET.get("user_sort") or USER_SORT_NEWEST).strip().lower()

    allowed_statuses = {
        USER_STATUS_ALL,
        USER_STATUS_ACTIVE,
        USER_STATUS_BLOCKED,
        USER_STATUS_DELETED,
    }
    if status_filter not in allowed_statuses:
        status_filter = USER_STATUS_ALL

    allowed_sorts = {
        USER_SORT_NEWEST,
        USER_SORT_OLDEST,
        USER_SORT_USERNAME,
        USER_SORT_NAME,
        USER_SORT_LAST_LOGIN,
    }
    if sort_filter not in allowed_sorts:
        sort_filter = USER_SORT_NEWEST

    users_qs = User.objects.select_related("profile", "profile__organization").all()

    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(profile__organization__name__icontains=search_query)
            | Q(profile__department__icontains=search_query)
            | Q(profile__student_group_number__icontains=search_query)
        )

    if status_filter == USER_STATUS_ACTIVE:
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == USER_STATUS_BLOCKED:
        users_qs = users_qs.filter(is_active=False).exclude(profile__is_deleted=True)
    elif status_filter == USER_STATUS_DELETED:
        users_qs = users_qs.filter(profile__is_deleted=True)

    if role_filter:
        if role_filter == ProfileRole.SUPERADMIN:
            users_qs = users_qs.filter(Q(is_superuser=True) | Q(profile__role=ProfileRole.SUPERADMIN))
        else:
            users_qs = users_qs.filter(profile__role=role_filter)

    if organization_filter == USER_ORG_FILTER_NONE:
        users_qs = users_qs.filter(profile__organization__isnull=True)
    elif organization_filter:
        users_qs = users_qs.filter(profile__organization_id=organization_filter)

    if group_filter:
        users_qs = users_qs.filter(profile__student_group_number__icontains=group_filter)

    if department_filter:
        users_qs = users_qs.filter(profile__department__icontains=department_filter)

    if sort_filter == USER_SORT_OLDEST:
        users_qs = users_qs.order_by("date_joined", "username")
    elif sort_filter == USER_SORT_USERNAME:
        users_qs = users_qs.order_by("username")
    elif sort_filter == USER_SORT_NAME:
        users_qs = users_qs.order_by("first_name", "last_name", "username")
    elif sort_filter == USER_SORT_LAST_LOGIN:
        users_qs = users_qs.order_by(F("last_login").desc(nulls_last=True), "-date_joined", "username")
    else:
        users_qs = users_qs.order_by("-date_joined", "username")

    users_page = Paginator(users_qs, USER_PAGE_SIZE).get_page(request.GET.get("user_page"))
    users_page.object_list = [_build_superadmin_user_row(user, actor=request.user) for user in users_page.object_list]

    base_url = base_url or reverse("accounts:superadmin_user_management")
    query_kwargs = {
        "section": "superadmin-users" if include_section else None,
        "user_search": search_query,
        "user_status": status_filter if status_filter != USER_STATUS_ALL else None,
        "user_role": role_filter,
        "user_org": organization_filter,
        "user_group": group_filter,
        "user_department": department_filter,
        "user_sort": sort_filter if sort_filter != USER_SORT_NEWEST else None,
    }

    current_page_number = users_page.number if users_page.number > 1 else None
    pagination_query = _query_string(**query_kwargs)
    post_next_url = _append_query_params(base_url, **query_kwargs, user_page=current_page_number)
    reset_url = _append_query_params(base_url, section="superadmin-users" if include_section else None)

    total_count = User.objects.count()
    active_count = User.objects.filter(is_active=True).count()
    blocked_count = User.objects.filter(is_active=False).exclude(profile__is_deleted=True).count()
    deleted_count = User.objects.filter(profile__is_deleted=True).count()

    role_options = [
        {
            "value": ProfileRole.SUPERADMIN,
            "label": PROFILE_ROLE_LABELS.get(ProfileRole.SUPERADMIN, "Super Admin"),
        }
    ] + [
        {"value": role_name, "label": role_label}
        for role_name, role_label in ProfileRole.CHOICES
        if role_name != ProfileRole.SUPERADMIN
    ]

    organization_options = [{"value": USER_ORG_FILTER_NONE, "label": "Təşkilatsız / fərdi"}] + [
        {"value": str(organization.id), "label": organization.name}
        for organization in Organization.objects.order_by("name")
    ]

    status_tabs = [
        {"value": USER_STATUS_ALL, "label": "Hamısı", "count": total_count},
        {"value": USER_STATUS_ACTIVE, "label": "Aktiv", "count": active_count},
        {"value": USER_STATUS_BLOCKED, "label": "Bloklanmış", "count": blocked_count},
        {"value": USER_STATUS_DELETED, "label": "Silinmiş", "count": deleted_count},
    ]

    sort_options = [
        {"value": USER_SORT_NEWEST, "label": "Ən yeni"},
        {"value": USER_SORT_OLDEST, "label": "Ən köhnə"},
        {"value": USER_SORT_USERNAME, "label": "İstifadəçi adına görə"},
        {"value": USER_SORT_NAME, "label": "Ada görə"},
        {"value": USER_SORT_LAST_LOGIN, "label": "Son girişə görə"},
    ]

    return {
        "users": users_page,
        "user_rows": users_page.object_list,
        "search_query": search_query,
        "status_filter": status_filter,
        "role_filter": role_filter,
        "organization_filter": organization_filter,
        "group_filter": group_filter,
        "department_filter": department_filter,
        "sort_filter": sort_filter,
        "status_tabs": status_tabs,
        "role_options": role_options,
        "organization_options": organization_options,
        "sort_options": sort_options,
        "pagination_query": pagination_query,
        "page_param": "user_page",
        "post_next_url": post_next_url,
        "reset_url": reset_url,
        "filtered_count": users_qs.count(),
        "total_count": total_count,
        "active_count": active_count,
        "blocked_count": blocked_count,
        "deleted_count": deleted_count,
        "embedded_in_profile": include_section,
    }


@login_required
@require_POST
def delete_account(request):
    """
    Handle account deletion request from the profile page.
    Requires password confirmation via POST data.
    """
    password = (request.POST.get("password") or "").strip()

    if not password:
        messages.error(request, _("delete_account_password_required"))
        return redirect(f"{reverse('accounts:profile')}?section=profile-info")

    try:
        soft_delete_account(request.user, request=request, password=password)
    except AccountDeletionError as exc:
        error_key = str(exc)
        if error_key == "password_incorrect":
            messages.error(request, _("delete_account_password_incorrect"))
        elif error_key == "last_org_admin":
            messages.error(request, _("delete_account_last_admin"))
        else:
            messages.error(request, _("delete_account_error"))
        return redirect(f"{reverse('accounts:profile')}?section=profile-info")

    # Log the user out after deletion
    logout(request)
    messages.success(request, _("delete_account_success"))
    return redirect(reverse("accounts:login"))


@login_required
def superadmin_user_management(request):
    """
    Superadmin-only view for managing active, blocked, and deleted users.
    """
    if not _is_superadmin_user(request.user):
        return HttpResponseForbidden(_("superadmin_access_only"))

    fallback_next_url = reverse("accounts:superadmin_user_management")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        user_id = request.POST.get("user_id")
        next_url = _resolve_next_url(request, fallback_next_url)

        if not user_id:
            messages.error(request, _("user_not_found"))
            return redirect(next_url)

        target_user = User.objects.filter(pk=user_id).first()
        if target_user is None:
            messages.error(request, _("user_not_found"))
            return redirect(next_url)

        target_profile = _safe_user_profile(target_user)
        target_status = _superadmin_user_status_key(target_user, target_profile)

        if action == "block":
            if target_user == request.user:
                messages.error(request, _("Öz hesabınızı bloklaya bilməzsiniz."))
            elif _is_superadmin_user(target_user):
                messages.error(request, _("Superadmin hesabını bloklamaq olmaz."))
            else:
                try:
                    block_account(target_user, request=request)
                except AccountDeletionError as exc:
                    if str(exc) == "last_org_admin":
                        messages.error(request, _("delete_account_last_admin"))
                    else:
                        messages.error(request, _("delete_account_error"))
                else:
                    messages.success(
                        request,
                        _('"{username}" hesabı müvəqqəti bloklandı.').format(username=target_user.username),
                    )
        elif action == "unblock":
            if target_status == USER_STATUS_DELETED:
                messages.error(request, _("Silinmiş hesabı blokdan çıxarmaq üçün əvvəlcə bərpa edin."))
            elif target_user == request.user:
                messages.error(request, _("Öz hesabınızın blokunu bu bölmədən aça bilməzsiniz."))
            elif _is_superadmin_user(target_user):
                messages.error(request, _("Superadmin hesabının blokunu açmaq olmaz."))
            else:
                unblock_account(target_user, request=request)
                messages.success(
                    request,
                    _('"{username}" hesabının bloku açıldı.').format(username=target_user.username),
                )
        elif action == "soft_delete":
            if target_user == request.user:
                messages.error(request, _("cannot_delete_self"))
            elif _is_superadmin_user(target_user):
                messages.error(request, _("cannot_delete_superadmin"))
            else:
                try:
                    soft_delete_account(target_user, request=request)
                except AccountDeletionError as exc:
                    if str(exc) == "last_org_admin":
                        messages.error(request, _("delete_account_last_admin"))
                    else:
                        messages.error(request, _("delete_account_error"))
                else:
                    messages.success(
                        request,
                        _('"{username}" hesabı silinmişlərə göndərildi.').format(username=target_user.username),
                    )
        elif action == "restore":
            restore_account(target_user, request=request)
            messages.success(
                request,
                _("user_restored_success") % {"username": target_user.username},
            )
        elif action == "hard_delete":
            if target_user == request.user:
                messages.error(request, _("cannot_delete_self"))
            elif _is_superadmin_user(target_user):
                messages.error(request, _("cannot_delete_superadmin"))
            else:
                username = target_user.username
                try:
                    hard_delete_account(target_user, request=request)
                except AccountDeletionError as exc:
                    if str(exc) == "last_org_admin":
                        messages.error(request, _("delete_account_last_admin"))
                    else:
                        messages.error(request, _("delete_account_error"))
                else:
                    messages.success(
                        request,
                        _("user_hard_deleted_success") % {"username": username},
                    )
        else:
            messages.error(request, _("unknown_action"))

        return redirect(next_url)

    return redirect(reverse("accounts:profile") + "?section=superadmin-users")
