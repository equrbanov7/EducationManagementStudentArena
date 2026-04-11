"""
Account management views: account deletion and superadmin user management.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ..models import UserProfile
from ..services.account_deletion import (
    AccountDeletionError,
    hard_delete_account,
    restore_account,
    soft_delete_account,
)
from ._helpers import _is_superadmin_user

logger = logging.getLogger(__name__)
User = get_user_model()


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
    Superadmin-only view for managing users (active and deleted).
    Supports search, filtering, restore, and hard delete operations.
    """
    if not _is_superadmin_user(request.user):
        return HttpResponseForbidden("Bu bölməyə yalnız superadminlər daxil ola bilər.")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        user_id = request.POST.get("user_id")

        if not user_id:
            messages.error(request, "İstifadəçi tapılmadı.")
            return redirect(reverse("accounts:superadmin_user_management"))

        target_user = get_object_or_404(User, pk=user_id)

        if action == "restore":
            restore_account(target_user, request=request)
            messages.success(
                request,
                f'"{target_user.username}" istifadəçisi uğurla bərpa edildi.',
            )
        elif action == "hard_delete":
            if target_user == request.user:
                messages.error(request, "Öz hesabınızı silə bilməzsiniz.")
            elif target_user.is_superuser:
                messages.error(request, "Superadmin hesabını silmək olmaz.")
            else:
                username = target_user.username
                hard_delete_account(target_user, request=request)
                messages.success(
                    request,
                    f'"{username}" istifadəçisi həmişəlik silindi.',
                )
        else:
            messages.error(request, "Naməlum əməliyyat.")

        return redirect(reverse("accounts:superadmin_user_management"))

    # GET: List users with filtering
    search_query = (request.GET.get("search") or "").strip()
    status_filter = (request.GET.get("status") or "active").strip().lower()

    if status_filter == "deleted":
        users_qs = User.objects.filter(
            is_active=False,
            profile__is_deleted=True,
        ).select_related("profile", "profile__organization")
    else:
        users_qs = User.objects.filter(
            is_active=True,
        ).select_related("profile", "profile__organization")

    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    users_qs = users_qs.order_by("-date_joined")

    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get("page")
    users_page = paginator.get_page(page_number)

    # Counts for tab badges
    active_count = User.objects.filter(is_active=True).count()
    deleted_count = User.objects.filter(
        is_active=False,
        profile__is_deleted=True,
    ).count()

    context = {
        "users": users_page,
        "search_query": search_query,
        "status_filter": status_filter,
        "active_count": active_count,
        "deleted_count": deleted_count,
    }
    return render(request, "accounts/superadmin_user_management.html", context)
