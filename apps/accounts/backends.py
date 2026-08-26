"""
Authentication backends for accounts app.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .identity import canonical_identity, canonical_identity_queryset, user_access_is_login_blocked


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

        user_model = get_user_model()
        key = canonical_identity(username)
        manager = user_model._default_manager
        username_candidates = canonical_identity_queryset(
            manager.all(),
            "username",
            key,
            alias="_login_username_key",
        ).order_by("pk")[:2]
        email_candidates = canonical_identity_queryset(
            manager.all(),
            "email",
            key,
            alias="_login_email_key",
        ).order_by(
            "pk"
        )[:2]
        candidates_by_id = {candidate.pk: candidate for candidate in (*username_candidates, *email_candidates)}
        candidates = [candidates_by_id[pk] for pk in sorted(candidates_by_id)[:2]]

        # Keep the absent/ambiguous-user path close to the password-hash cost of
        # an existing account and never pick an arbitrary canonical collision.
        if len(candidates) != 1:
            user_model().set_password(password)
            return None
        user = candidates[0]
        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None
        return user

    def user_can_authenticate(self, user):
        # staged (import) VƏ archived (məzun/xaric) — hər ikisi girişi bağlayır.
        return super().user_can_authenticate(user) and not user_access_is_login_blocked(user)

    def get_user(self, user_id):
        user = super().get_user(user_id)
        if user is None or not self.user_can_authenticate(user):
            return None
        return user
