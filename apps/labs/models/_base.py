"""labs model paketi — paylaşılan (User, secure_random)."""

import secrets

from django.contrib.auth import get_user_model

User = get_user_model()


secure_random = secrets.SystemRandom()
