"""Sahib 2026-11-28: «Fənlərim» kartından «Dərs materialları» keçidi — tələbənin görə bildiyi qovluqlar."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.registrar.student_subjects_context import attach_material_links
from apps.subject_folder import public

from . import factories as f
from .test_cabinet_ui import _get

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
    assert f"sf_offering={ready.offering.pk}" in rows[0]["materials_url"]
    assert rows[1]["materials_url"] == ""


def _extra_folder(ready, offering, title):
    teacher = f.make_teacher(ready.org)
    f.add_lesson(offering, teacher)
    folder, _, _ = public.create_folder(
        organization=ready.org,
        subject=offering.subject,
        period=offering.period,
        owner=teacher,
        by_user=teacher,
        title=title,
        auto_assign=False,
    )
    public.assign_folder(folder, [offering], by_user=teacher)
    return folder


def test_card_filters_multiple_folders_and_regular_menu_shows_all(ready, settings, django_assert_num_queries):
    settings.UNIVERSITY_MODE = True
    student = ready.students[0]
    extra = _extra_folder(ready, ready.offering, "Əlavə dərs vəsaiti")
    other = f.make_offering(ready.org, subject=f.make_subject(ready.org), period=ready.period, instructor=ready.teacher)
    other_enrollment = f.enroll(other, student)
    other_folder = _extra_folder(ready, other, "Başqa fənnin vəsaiti")
    rows = [{"enrollment": enrollment} for enrollment in (ready.enrollments[0], other_enrollment)]
    with django_assert_num_queries(1):
        attach_material_links(organization=ready.org, record=SimpleNamespace(student=student), rows=rows)
    assert parse_qs(urlsplit(rows[0]["materials_url"]).query) == {
        "section": [public.SECTION_STUDENT],
        "sf_offering": [str(ready.offering.pk)],
    }
    _, filtered = _get(student, ready.org, public.SECTION_STUDENT, offering=ready.offering.pk)
    assert extra.title in filtered and ready.folder.title in filtered and other_folder.title not in filtered
    _, all_materials = _get(student, ready.org, public.SECTION_STUDENT)
    assert extra.title in all_materials and other_folder.title in all_materials
    assert "sf_offering=" not in all_materials


def test_shared_folder_uses_chosen_offerings_assignment_and_keeps_legacy_link(ready, settings):
    settings.UNIVERSITY_MODE = True
    student = ready.students[0]
    other = f.make_offering(ready.org, subject=ready.subject, period=ready.period, instructor=ready.teacher)
    f.enroll(other, student)
    other_assignment = public.assign_folder(ready.folder, [other], by_user=ready.teacher)[0]["assignment"]
    _, listing = _get(student, ready.org, public.SECTION_STUDENT)
    _, legacy = _get(student, ready.org, public.SECTION_STUDENT, folder=ready.folder.pk)
    assert ready.homework.title in legacy
    for offering, assignment in ((ready.offering, ready.assignment), (other, other_assignment)):
        assert f"sf_offering={offering.pk}" in listing
        _, folder = _get(student, ready.org, public.SECTION_STUDENT, folder=ready.folder.pk, offering=offering.pk)
        assert f"sf_offering={offering.pk}" in folder and ready.homework.title in folder
        _, task = _get(
            student,
            ready.org,
            public.SECTION_STUDENT,
            folder=ready.folder.pk,
            task=ready.homework.pk,
            offering=offering.pk,
        )
        assert f'name="assignment" value="{assignment.pk}"' in task


def test_invalid_or_unassigned_offering_cannot_fall_back_to_other_materials(ready, settings):
    settings.UNIVERSITY_MODE = True
    student = ready.students[0]
    outside = f.make_org()
    assert public.student_folders(organization=outside, student=student, offering_id=ready.offering.pk) == []
    other = f.make_offering(ready.org, subject=ready.subject, period=ready.period, instructor=ready.teacher)
    for offering in (other.pk, "not-a-uuid"):
        _, panel = _get(student, ready.org, public.SECTION_STUDENT, offering=offering, folder=ready.folder.pk)
        assert "Dərs materiallarıma qayıt" in panel
        assert ready.homework.title not in panel and ready.folder.title not in panel
    _, empty = _get(student, ready.org, public.SECTION_STUDENT, offering=other.pk)
    assert "Hələ dərs materialı yoxdur" in empty and ready.folder.title not in empty
