"""
Authentication backends for accounts app.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """
    Authenticate users using either username or email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get("username")
        if username is None or password is None:
            return None

        user_model = get_user_model()
        lookup = Q(username__iexact=username) | Q(email__iexact=username)
        user = user_model._default_manager.filter(lookup).first()

        if user is None:
            return None
        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None
        return user
