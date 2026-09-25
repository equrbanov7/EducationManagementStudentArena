"""Fənn qovluğu axtarışı kanonik ``core.search_text.tolerant_q``-dan gəlir (sahib 2026-09-26)."""

from __future__ import annotations

import pytest

from apps.subject_folder import public
from apps.subject_folder.services import queries
from core import search_text

pytestmark = pytest.mark.django_db


def test_local_helper_is_the_canonical_api():
    assert queries.tolerant_q is search_text.tolerant_q


def test_folder_list_folds_subject_name_and_compacts_code(world, folder):
    type(world.subject).objects.filter(pk=world.subject.pk).update(name="Verilənlər bazası", code="SF-77")

    def found(query):
        return set(
            public.list_folders(organization=world.org, actor=world.teacher, search=query).values_list("pk", flat=True)
        )

    for query in ("verilenler", "VERİLƏNLƏR bazasi", "sf77", "SF 77"):
        assert found(query) == {folder.pk}, query
    assert found("Kimya") == set()
