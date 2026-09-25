"""Müraciət siyahısı dözümlü axtarış (sahib 2026-09-26): «Secme» → «Seçmə», nömrə ayırıcıya dözümlü."""

from __future__ import annotations

from django.urls import reverse

import pytest

from apps.applications.tests.test_endpoints import application, body, client_for, world  # noqa: F401

pytestmark = pytest.mark.django_db


def _total(world, query):  # noqa: F811
    student = client_for(world["student"], world["organization"])
    return body(student.get(reverse("applications:list"), {"tab": "mine", "q": query}))["total"]


def test_subject_is_found_with_an_english_keyboard(world, application):  # noqa: F811
    for query in ("Secme", "SEÇMƏ fenn", "secme bloku"):
        assert _total(world, query) == 1, query


def test_number_is_found_without_separators(world, application):  # noqa: F811
    compact = application.number.replace("-", "")
    assert _total(world, compact) == 1
    assert _total(world, "tapılmayan") == 0
