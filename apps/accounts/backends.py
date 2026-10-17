"""
Authentication backends for accounts app.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .identity import (
    REQUEST_USER_LOGIN_CHECKED_ATTR,
    canonical_identity,
    canonical_identity_queryset,
    login_blocked_access_states,
    user_access_is_login_blocked,
)


def single_login_candidate(username):
    """İstifadəçi adı VƏ YA e-poçta TƏK uyğun hesab (kanonik forma); yoxdursa / birmənalı deyilsə ``None``.

    Giriş backend-i və «hesab dayandırılıb» bildirişi (``account_block_notice``) EYNİ axtarışı işlədir.
    """
    key = canonical_identity(str(username or "").strip())
    if not key:
        return None
    manager = get_user_model()._default_manager
    username_candidates = canonical_identity_queryset(
        manager.all(), "username", key, alias="_login_username_key"
    ).order_by("pk")[:2]
    email_candidates = canonical_identity_queryset(manager.all(), "email", key, alias="_login_email_key").order_by(
        "pk"
    )[:2]
    candidates_by_id = {candidate.pk: candidate for candidate in (*username_candidates, *email_candidates)}
    candidates = [candidates_by_id[pk] for pk in sorted(candidates_by_id)[:2]]
    return candidates[0] if len(candidates) == 1 else None


class EmailOrUsernameBackend(ModelBackend):
    """
    Authenticate users using either username or email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get("username")
        if username is None or password is None:
            return None

        username = str(username).strip()
        if not username:
            return None

        user = single_login_candidate(username)
        # Keep the absent/ambiguous-user path close to the password-hash cost of
        # an existing account and never pick an arbitrary canonical collision.
        if user is None:
            get_user_model()().set_password(password)
            return None
        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None
        return user

    def user_can_authenticate(self, user):
        # staged (import) VƏ archived (məzun/xaric) — hər ikisi girişi bağlayır.
        return super().user_can_authenticate(user) and not user_access_is_login_blocked(user)

    def get_user(self, user_id):
        # PERF-1 F-12 (2026-10-17): istifadəçi profili ilə BİR sorğuda (LEFT JOIN) oxunur. Əvvəl hər
        # autentifikasiyalı sorğuda 3 ayrı SELECT gedirdi: `auth_user`, `access_state` EXISTS
        # (``user_can_authenticate``) və `OrganizationMiddleware`-də `user.profile`. Profil EYNİ sorğuda
        # bazadan gəlir — ``_access_state_in``-in «köhnə keşə güvənmə» qaydası pozulmur (keş təzədir).
        # Semantika ``ModelBackend.get_user`` + ``user_can_authenticate`` ilə eynidir.
        user_model = get_user_model()
        try:
            user = user_model._default_manager.select_related("profile").get(pk=user_id)
        except user_model.DoesNotExist:
            return None
        if not ModelBackend.user_can_authenticate(self, user):
            return None
        profile = user._state.fields_cache.get("profile")
        if profile is None:
            # Profil sətri yoxdur: keşdəki «yoxdur» işarəsi atılır ki, sorğuda sonradan yaradılan profil
            # əvvəlki kimi təzə oxunsun.
            user._state.fields_cache.pop("profile", None)
        elif profile.access_state in login_blocked_access_states():
            return None
        # 2026-09-14 (perf F-08): yoxlama keçilib — sorğu daxilində middleware və
        # view-as köməkçiləri (`request_user_login_blocked`) eyni SELECT-i təkrarlamır.
        setattr(user, REQUEST_USER_LOGIN_CHECKED_ATTR, True)
        return user
