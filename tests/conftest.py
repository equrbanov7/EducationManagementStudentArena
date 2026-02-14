"""
Pytest configuration and fixtures for EMS Arena project.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

import pytest

User = get_user_model()


@pytest.fixture
def create_user():
    """
    Fixture to create a user.
    """

    def _create_user(username="testuser", email="test@example.com", password="testpass123", **kwargs):
        return User.objects.create_user(username=username, email=email, password=password, **kwargs)

    return _create_user


@pytest.fixture
def teacher_user(create_user, db):
    """
    Fixture to create a teacher user.
    """
    user = create_user(username="teacher", email="teacher@example.com")
    teacher_group, _ = Group.objects.get_or_create(name="teacher")
    user.groups.add(teacher_group)
    return user


@pytest.fixture
def student_user(create_user, db):
    """
    Fixture to create a student user.
    """
    user = create_user(username="student", email="student@example.com")
    student_group, _ = Group.objects.get_or_create(name="student")
    user.groups.add(student_group)
    return user
