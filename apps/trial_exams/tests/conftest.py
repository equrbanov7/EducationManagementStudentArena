"""Shared fixtures for trial_exams tests."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

_MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def create_user(django_user_model):
    """Create a user for trial-exam app tests."""

    def _create_user(username="testuser", email="test@example.com", password="testpass123", **kwargs):
        return django_user_model.objects.create_user(username=username, email=email, password=password, **kwargs)

    return _create_user


@pytest.fixture
def pdf_upload():
    """Return a factory producing a valid in-memory PDF upload."""

    def _make(name="questions.pdf", content=_MINIMAL_PDF, content_type="application/pdf"):
        return SimpleUploadedFile(name, content, content_type=content_type)

    return _make


@pytest.fixture
def valid_post_data():
    return {
        "full_name": "Tələbə Test",
        "email": "student@example.com",
        "subject_name": "Riyaziyyat",
        "note": "",
        "website": "",  # honeypot stays empty
    }
