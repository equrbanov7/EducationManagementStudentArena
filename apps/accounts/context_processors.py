"""
Accounts context processor-ları.

``view_as_context`` — "View as" banner/panel üçün qlobal şablon konteksti.
Performans: heç bir əlavə DB sorğusu ETMİR — middleware-in artıq request-ə
qoyduğu atributlardan və OrganizationMiddleware-in yüklədiyi üzvlüklərdən
istifadə edir.
"""


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def view_as_context(request):
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"view_as": {"active": False, "can_use": False, "is_superadmin": False}}

    is_active = bool(getattr(request, "is_view_as", False))
    real_user = getattr(request, "real_user", user)
    mode = getattr(request, "view_as_mode", None)

    can_use = False
    if not is_active:
        if _is_superadmin(user):
            can_use = True
        else:
            # OrganizationMiddleware-in artıq yüklədiyi üzvlüklərdən ucuz yoxlama
            # (əlavə sorğu yoxdur). Dəqiq icazə start zamanı serverdə yenidən yoxlanılır.
            from apps.accounts.services.view_as import resolve_actor_access

            organization = getattr(request, "organization", None)
            if organization is not None:
                actor_mode, _level, _m = resolve_actor_access(
                    user,
                    organization,
                    memberships=getattr(request, "org_memberships", None) or None,
                )
                can_use = actor_mode is not None

    target = user if is_active else None
    target_name = ""
    if target is not None:
        target_name = (f"{target.first_name} {target.last_name}").strip() or target.username

    return {
        "view_as": {
            "active": is_active,
            "mode": mode,
            "target": target,
            "target_name": target_name,
            "real_user": real_user,
            "can_use": can_use,
            "is_superadmin": _is_superadmin(real_user),
        }
    }
