"""Ortaq fixture-lər: təşkilat + müəllim + açılış + 3 tələbə + təsdiqlənmiş sillabus (2x5)."""

from __future__ import annotations

from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

from apps.subject_folder import public

from . import factories as f


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.SUBJECT_FOLDER_SIMILARITY_SYNC = True


@pytest.fixture(autouse=True)
def _no_real_journal_hook(monkeypatch):
    """Registrar-ın REAL hook-u (paralel inkişafda ola/olmaya bilər) bu testlərə qarışmasın:
    default «hook yoxdur»; müqavilə testləri hook-u açıq ötürür və ya modul siyahısını qaytarır."""
    from apps.subject_folder.services import journal

    monkeypatch.setattr(journal, "HOOK_MODULES", ())


@pytest.fixture
def world(db):
    org = f.make_org()
    teacher = f.make_teacher(org)
    period = f.make_period(org)
    subject = f.make_subject(org)
    offering = f.make_offering(org, subject=subject, period=period, instructor=teacher)
    students = [f.make_student(org) for _ in range(3)]
    enrollments = [f.enroll(offering, student) for student in students]
    syllabus, version = f.approve_syllabus(offering, teacher, option="2x5")
    return SimpleNamespace(
        org=org,
        teacher=teacher,
        period=period,
        subject=subject,
        offering=offering,
        students=students,
        enrollments=enrollments,
        syllabus=syllabus,
        version=version,
    )


@pytest.fixture
def folder(world):
    folder, created, _summary = public.create_folder(
        organization=world.org, subject=world.subject, owner=world.teacher, by_user=world.teacher, period=world.period
    )
    assert created
    return folder


@pytest.fixture
def ready(world, folder, django_capture_on_commit_callbacks):
    """Qovluq qrupa təyin olunub, sərbəst iş slotları + bir ev tapşırığı DƏRC olunub."""
    with django_capture_on_commit_callbacks(execute=True):
        result = public.assign_folder(folder, [world.offering], by_user=world.teacher)
    assignment = result[0]["assignment"]
    slots = list(folder.tasks.filter(kind="selfwork").order_by("slot_index"))
    for task in slots:
        public.set_task_published(task, by_user=world.teacher, published=True)
    homework = public.create_homework(folder, by_user=world.teacher, title="Ev tapşırığı 1", is_published=True)
    folder.refresh_from_db()
    return SimpleNamespace(
        **vars(world), folder=folder, assignment=assignment, slots=slots, slot1=slots[0], homework=homework
    )


def upload(name="work.txt", content=b"salam dunya", content_type="text/plain"):
    return SimpleUploadedFile(name, content, content_type=content_type)
