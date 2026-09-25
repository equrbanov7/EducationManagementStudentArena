"""Təyinat: yalnız öz açılışları; auditoriya = enrolled (guest daxil, köçürülmüş xaric); tək qiymətləndirici."""

from __future__ import annotations

import pytest

from apps.registrar.models import Enrollment
from apps.subject_folder import public

from . import factories as f

pytestmark = pytest.mark.django_db


def _texts(ready, student):
    return public.submit(task=ready.slot1, assignment=ready.assignment, student=student, text="cavab mətni")


def test_teacher_can_assign_only_own_offerings(world, folder):
    stranger = f.make_teacher(world.org)
    foreign = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=stranger)
    with pytest.raises(public.FolderError) as exc:
        public.assign_folder(folder, [foreign], by_user=world.teacher)
    assert exc.value.code == "permission.not_teaching"
    offered = {row["offering"].pk for row in public.assignable_offerings(folder, world.teacher)}
    assert offered == {world.offering.pk}


def test_lesson_instructor_counts_as_teacher(world, folder):
    colleague = f.make_teacher(world.org)
    shared = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=colleague)
    f.add_lesson(shared, world.teacher)  # fənn iki müəllim arasında bölünüb
    result = public.assign_folder(folder, [shared], by_user=world.teacher)
    assert result[0]["created"] and result[0]["assignment"].is_active


def test_wrong_subject_or_period_is_refused(world, folder):
    other_subject = f.make_offering(
        world.org, subject=f.make_subject(world.org), period=world.period, instructor=world.teacher
    )
    with pytest.raises(public.FolderError) as exc:
        public.assign_folder(folder, [other_subject], by_user=world.teacher)
    assert exc.value.code == "folder.subject_mismatch"
    other_period = f.make_offering(
        world.org, subject=world.subject, period=f.make_period(world.org, current=False), instructor=world.teacher
    )
    with pytest.raises(public.FolderError) as exc:
        public.assign_folder(folder, [other_period], by_user=world.teacher)
    assert exc.value.code == "folder.period_mismatch"


def test_first_assignment_activates_folder_and_snapshots_syllabus(world, folder):
    assert folder.status == "draft"
    result = public.assign_folder(folder, [world.offering], by_user=world.teacher)
    folder.refresh_from_db()
    assignment = result[0]["assignment"]
    assert folder.status == "active"
    assert assignment.syllabus_version_ref == world.version.pk and assignment.selfwork_option == "2x5"
    assert assignment.grades_selfwork and result[0]["warnings"] == []
    again = public.assign_folder(folder, [world.offering], by_user=world.teacher)
    assert again[0]["created"] is False and again[0]["reactivated"] is False


def test_audience_enrolled_and_guest_yes_transferred_and_completed_no(ready):
    guest_student = f.make_student(ready.org)
    f.enroll(ready.offering, guest_student, source_group=f.make_group(ready.org))
    transferred = f.make_student(ready.org)
    old = f.enroll(ready.offering, transferred)
    new_offering = f.make_offering(ready.org, subject=ready.subject, period=ready.period, instructor=ready.teacher)
    successor = f.enroll(new_offering, transferred)
    Enrollment.objects.filter(pk=old.pk).update(status="dropped", superseded_by=successor)
    finished = f.make_student(ready.org)
    f.enroll(ready.offering, finished, status="completed")

    assert _texts(ready, guest_student).status == "submitted"
    for outsider in (transferred, finished, f.make_student(ready.org)):
        with pytest.raises(public.FolderError) as exc:
            _texts(ready, outsider)
        assert exc.value.code == "audience.not_enrolled"
    visible = {row["folder"].pk for row in public.student_folders(organization=ready.org, student=guest_student)}
    assert visible == {ready.folder.pk}
    assert public.student_folders(organization=ready.org, student=transferred) == []


def test_second_folder_on_same_offering_does_not_grade_selfwork(ready):
    colleague = f.make_teacher(ready.org)
    f.add_lesson(ready.offering, colleague)
    other, _c, _s = public.create_folder(
        organization=ready.org, subject=ready.subject, owner=colleague, by_user=colleague, period=ready.period
    )
    result = public.assign_folder(other, [ready.offering], by_user=colleague)
    assignment = result[0]["assignment"]
    assert not assignment.grades_selfwork
    slot = other.tasks.filter(kind="selfwork").first()
    public.set_task_published(slot, by_user=colleague, published=True)
    with pytest.raises(public.FolderError) as exc:
        public.submit(task=slot, assignment=assignment, student=ready.students[0], text="cavab")
    assert exc.value.code == "assignment.selfwork_elsewhere"
    homework = public.create_homework(other, by_user=colleague, title="Seminar tapşırığı", is_published=True)
    assert (
        public.submit(task=homework, assignment=assignment, student=ready.students[0], text="ok").status == "submitted"
    )
    feed = public.student_folders(organization=ready.org, student=ready.students[0])
    other_row = next(row for row in feed if row["folder"].pk == other.pk)
    assert [row["task"].kind for row in other_row["tasks"]] == ["homework"]


def test_option_mismatch_warns_and_disables_selfwork(world, folder):
    other_group = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=world.teacher)
    f.approve_syllabus(other_group, world.teacher, option="10x1")
    result = public.assign_folder(folder, [other_group], by_user=world.teacher)
    assert not result[0]["assignment"].grades_selfwork
    assert result[0]["warnings"][0]["code"] == "assignment.selfwork_option_mismatch"


def test_unassign_keeps_history_and_blocks_new_work(ready):
    row = _texts(ready, ready.students[0])
    public.unassign(ready.assignment, by_user=ready.teacher)
    ready.assignment.refresh_from_db()
    assert not ready.assignment.is_active and ready.assignment.unassigned_at is not None
    with pytest.raises(public.FolderError) as exc:
        _texts(ready, ready.students[1])
    assert exc.value.code == "assignment.inactive"
    assert public.can_view_submission(ready.students[0], row)  # öz işi görünməyə davam edir
    assert public.student_folders(organization=ready.org, student=ready.students[0]) == []
    result = public.assign_folder(ready.folder, [ready.offering], by_user=ready.teacher)
    assert result[0]["reactivated"] and result[0]["assignment"].grades_selfwork


def test_student_feed_states(ready):
    student = ready.students[0]
    feed = public.student_folders(organization=ready.org, student=student)
    assert len(feed) == 1
    row = feed[0]
    assert row["counts"]["selfwork"] == 2 and row["counts"]["homework"] == 1
    submitted = _texts(ready, student)
    public.return_for_revision(submitted, by_user=ready.teacher, feedback="Yenidən işləyin")
    view = public.student_task_view(ready.slot1, ready.assignment, student)
    assert view["status"] == "returned" and view["can_submit"] and len(view["attempts"]) == 1
    public.submit(task=ready.slot1, assignment=ready.assignment, student=student, text="ikinci cəhd")
    view = public.student_task_view(ready.slot1, ready.assignment, student)
    assert view["blocked_reason"] == "submission.pending" and [a.attempt_no for a in view["attempts"]] == [1, 2]
    with pytest.raises(public.FolderError):
        public.student_task_view(ready.slot1, ready.assignment, f.make_student(ready.org))
