"""Siyahı API-lərinin sorğu büdcəsi — sorğu sayı sətir sayı ilə ARTMIR (N+1 yoxdur)."""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from apps.subject_folder import public

from . import factories as f

pytestmark = pytest.mark.django_db


def _grow(ready, extra_students: int):
    for _ in range(extra_students):
        student = f.make_student(ready.org)
        f.enroll(ready.offering, student)
        public.submit(task=ready.slot1, assignment=ready.assignment, student=student, text="iş mətni")
        public.submit(task=ready.homework, assignment=ready.assignment, student=student, text="ev işi")


def _count(callable_):
    with CaptureQueriesContext(connection) as ctx:
        callable_()
    return len(ctx.captured_queries)


def test_list_submissions_is_constant(ready):
    def run():
        rows = list(public.list_submissions(organization=ready.org, actor=ready.teacher, student_query="student"))
        for row in rows:
            _ = (row.task.title, row.student.username, row.assignment.offering.group, row.file_count)
        return rows

    _grow(ready, 2)
    run()  # isinmə: bir dəfəlik keşlər (ContentType və s.) ölçüyə düşməsin
    small = _count(run)
    _grow(ready, 6)
    assert _count(run) == small <= 6


def test_student_feed_is_constant(ready):
    student = ready.students[0]
    for _ in range(3):
        public.create_homework(ready.folder, by_user=ready.teacher, title="əlavə", is_published=True)
    public.student_folders(organization=ready.org, student=student)  # isinmə
    small = _count(lambda: public.student_folders(organization=ready.org, student=student))
    for _ in range(6):
        public.create_homework(ready.folder, by_user=ready.teacher, title="daha", is_published=True)
    assert _count(lambda: public.student_folders(organization=ready.org, student=student)) == small <= 6


def test_task_progress_and_counts_are_constant(ready):
    _grow(ready, 2)
    public.task_progress(ready.assignment)  # isinmə
    small = _count(lambda: public.task_progress(ready.assignment))
    _grow(ready, 5)
    assert _count(lambda: public.task_progress(ready.assignment)) == small <= 4
    queryset = public.list_submissions(organization=ready.org, actor=ready.teacher)
    counts = public.status_counts(queryset)
    assert counts["submitted"] == 14 and counts["total"] == 14


def test_folder_list_and_contents_are_constant(ready):
    list(public.list_folders(organization=ready.org, actor=ready.teacher))  # isinmə
    listing = _count(lambda: list(public.list_folders(organization=ready.org, actor=ready.teacher)))
    rows = list(public.list_folders(organization=ready.org, actor=ready.teacher))
    assert rows[0].selfwork_count == 2 and rows[0].homework_count == 1 and rows[0].topic_count == 4
    for index in range(8):
        public.create_material(
            ready.folder, by_user=ready.teacher, kind="note", title=f"Q{index}", description="x", is_published=True
        )
    assert _count(lambda: list(public.list_folders(organization=ready.org, actor=ready.teacher))) == listing
    public.folder_contents(ready.folder, actor=ready.students[0])  # isinmə
    contents = _count(lambda: public.folder_contents(ready.folder, actor=ready.students[0]))
    for index in range(8):
        public.create_material(
            ready.folder, by_user=ready.teacher, kind="note", title=f"R{index}", description="y", is_published=True
        )
    assert _count(lambda: public.folder_contents(ready.folder, actor=ready.students[0])) == contents
