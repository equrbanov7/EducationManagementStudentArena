"""Sahib 2026-11-28: «Fənlərim» kartından «Dərs materialları» keçidi — tələbənin görə bildiyi qovluqlar."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.registrar.student_subjects_context import attach_material_links
from apps.subject_folder import public

from . import factories as f

pytestmark = pytest.mark.django_db


def test_folder_ids_follow_student_visibility(ready, django_assert_num_queries):
    student = ready.students[0]
    stranger = f.make_student(ready.org)
    other = f.make_offering(ready.org, subject=ready.subject, period=ready.period, instructor=ready.teacher)
    with django_assert_num_queries(1):
        links = public.student_folder_ids_by_offering(
            organization=ready.org, student=student, offering_ids=[ready.offering.pk, other.pk]
        )
    assert links == {ready.offering.pk: [ready.folder.pk]}
    assert (
        public.student_folder_ids_by_offering(
            organization=ready.org, student=stranger, offering_ids=[ready.offering.pk]
        )
        == {}
    )


def test_card_link_opens_the_folder(ready):
    other = f.make_offering(ready.org, subject=ready.subject, period=ready.period, instructor=ready.teacher)
    rows = [
        {"enrollment": SimpleNamespace(offering_id=ready.offering.pk)},
        {"enrollment": SimpleNamespace(offering_id=other.pk)},
    ]
    attach_material_links(organization=ready.org, record=SimpleNamespace(student=ready.students[0]), rows=rows)
    assert "section=my-subject-folders" in rows[0]["materials_url"]
    assert f"sf_folder={ready.folder.pk}" in rows[0]["materials_url"]
    assert rows[1]["materials_url"] == ""
