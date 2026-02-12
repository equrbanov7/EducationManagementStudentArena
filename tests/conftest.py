"""
Pytest configuration and fixtures for EMS Arena project.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def create_user():
    """
    Fixture to create a user.
    """

    def _create_user(
        username="testuser", email="test@example.com", password="testpass123", **kwargs
    ):
        return User.objects.create_user(
            username=username, email=email, password=password, **kwargs
        )

    return _create_user


@pytest.fixture
def teacher_user(create_user):
    """
    Fixture to create a teacher user.
    """
    return create_user(username="teacher", email="teacher@example.com", role="teacher")


@pytest.fixture
def student_user(create_user):
    """
    Fixture to create a student user.
    """
    return create_user(username="student", email="student@example.com", role="student")
