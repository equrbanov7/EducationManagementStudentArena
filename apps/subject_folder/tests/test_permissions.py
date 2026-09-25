"""İcazələr: sahib/inzibatçı idarə edir; yalnız qrupun müəllimi yoxlayır; tələbə yalnız öz işini görür; əhatəli əməkdaş oxuyur."""

from __future__ import annotations

import pytest

from apps.subject_folder import public
from core.constants import RoleScopeType

from . import factories as f

pytestmark = pytest.mark.django_db


def _submission(ready, index=0):
    return public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[index], text="iş")


def test_only_owner_or_admin_manage_folder(ready):
    colleague = f.make_teacher(ready.org)
    assert public.can_manage_folder(ready.teacher, ready.folder)
    assert public.can_manage_folder(ready.org.owner, ready.folder)
    assert not public.can_manage_folder(colleague, ready.folder)
    assert not public.can_manage_folder(ready.students[0], ready.folder)
    with pytest.raises(public.FolderError) as exc:
        public.create_homework(ready.folder, by_user=colleague, title="x")
    assert exc.value.code == "permission.not_owner" and exc.value.is_permission


def test_owner_losing_instructor_role_loses_management(ready):
    from apps.organizations.models import Membership

    Membership.objects.filter(user=ready.teacher).update(is_active=False)
    assert not public.can_manage_folder(ready.teacher, ready.folder)


def test_only_the_groups_teacher_reviews(ready):
    row = _submission(ready)
    colleague = f.make_teacher(ready.org)
    with pytest.raises(public.FolderError) as exc:
        public.accept(row, by_user=colleague, points="3")
    assert exc.value.code == "permission.not_reviewer"
    with pytest.raises(public.FolderError):
        public.return_for_revision(row, by_user=ready.students[1], feedback="başqasının işi")
    # İnzibatçı (təşkilat sahibi) yoxlaya bilər.
    assert (
        public.check_homework(
            public.submit(task=ready.homework, assignment=ready.assignment, student=ready.students[1], text="ev"),
            by_user=ready.org.owner,
        ).status
        == "checked"
    )


def test_handover_moves_review_rights(ready):
    row = _submission(ready)
    successor = f.make_teacher(ready.org)
    ready.offering.instructor = successor
    ready.offering.save(update_fields=["instructor"])
    assert not public.can_review_assignment(ready.teacher, ready.assignment)
    assert public.can_review_assignment(successor, ready.assignment)
    assert public.accept(row, by_user=successor, points="4").status == "accepted"


def test_students_see_only_their_own_submissions(ready):
    mine = _submission(ready, 0)
    theirs = _submission(ready, 1)
    student = ready.students[0]
    assert public.can_view_submission(student, mine)
    assert not public.can_view_submission(student, theirs)
    listed = set(public.list_submissions(organization=ready.org, actor=student).values_list("pk", flat=True))
    assert listed == {mine.pk}
    teacher_view = set(
        public.list_submissions(organization=ready.org, actor=ready.teacher).values_list("pk", flat=True)
    )
    assert teacher_view == {mine.pk, theirs.pk}
    stranger = f.make_teacher(ready.org)
    assert not public.list_submissions(organization=ready.org, actor=stranger).exists()


def test_staff_scope_reads_only_groups_in_scope(ready):
    faculty = f.make_group(ready.org, name="Fakulte")
    inside = f.make_offering(
        ready.org,
        subject=ready.subject,
        period=ready.period,
        instructor=ready.teacher,
        group=f.make_group(ready.org, parent=faculty),
    )
    student = f.make_student(ready.org)
    f.enroll(inside, student)
    assignment = public.assign_folder(ready.folder, [inside], by_user=ready.teacher)[0]["assignment"]
    row = public.submit(task=ready.homework, assignment=assignment, student=student, text="iş")
    _submission(ready)  # əhatədən KƏNAR qrupun işi
    dean = f.make_user("dean")
    f.activate_member(
        ready.org,
        dean,
        "dean_scoped",
        permissions=["journal.view"],
        level=70,
        scope_unit=faculty,
        scope_type=RoleScopeType.UNIT,
    )
    outsider_dean = f.make_user("dean")
    f.activate_member(
        ready.org,
        outsider_dean,
        "dean_other",
        permissions=["journal.view"],
        level=70,
        scope_unit=f.make_group(ready.org, name="Basqa"),
        scope_type=RoleScopeType.UNIT,
    )
    rim = f.make_user("rim")
    f.activate_member(ready.org, rim, "rim_head", permissions=["journal.correct"], level=80)
    assert public.can_view_submission(dean, row) and public.can_view_folder(dean, ready.folder)
    assert not public.can_view_submission(outsider_dean, row)
    assert public.can_view_submission(rim, row)
    assert set(public.list_submissions(organization=ready.org, actor=dean).values_list("pk", flat=True)) == {row.pk}
    assert not public.list_submissions(organization=ready.org, actor=outsider_dean).exists()
    assert public.list_submissions(organization=ready.org, actor=rim).count() == 2
    with pytest.raises(public.FolderError):
        public.accept(row, by_user=dean, points="2")  # əhatə YALNIZ OXUDUR


def test_student_sees_only_published_content(ready):
    folder = ready.folder
    public.create_material(
        folder, by_user=ready.teacher, kind="note", title="Açıq qeyd", description="a", is_published=True
    )
    public.create_material(folder, by_user=ready.teacher, kind="note", title="Gizli qeyd", description="b")
    hidden_topic = folder.topics.order_by("order").first()
    public.create_material(
        folder,
        by_user=ready.teacher,
        kind="note",
        title="Gizli mövzu",
        description="c",
        topic=hidden_topic,
        is_published=True,
    )
    public.set_topic_hidden(hidden_topic, by_user=ready.teacher, hidden=True)
    student_view = public.folder_contents(folder, actor=ready.students[0])
    titles = [m.title for m in student_view["general"]["materials"]]
    titles += [m.title for row in student_view["topics"] for m in row["materials"]]
    assert titles == ["Açıq qeyd"] and not student_view["is_staff_view"]
    teacher_view = public.folder_contents(folder, actor=ready.teacher)
    assert teacher_view["is_staff_view"] and teacher_view["can_manage"]
    all_titles = [m.title for m in teacher_view["general"]["materials"]]
    all_titles += [m.title for row in teacher_view["topics"] for m in row["materials"]]
    assert sorted(all_titles) == ["Açıq qeyd", "Gizli mövzu", "Gizli qeyd"]
    outsider = f.make_student(ready.org)
    assert not public.can_view_folder(outsider, folder)


def test_draft_folder_is_invisible_to_students(ready):
    public.set_folder_status(ready.folder, by_user=ready.teacher, status="draft")
    assert not public.is_folder_student(ready.students[0], ready.folder)
    with pytest.raises(public.FolderError) as exc:
        _submission(ready)
    assert exc.value.code == "folder.not_active"


def test_archived_folder_is_read_only(ready):
    public.set_folder_status(ready.folder, by_user=ready.teacher, status="archived")
    with pytest.raises(public.FolderError) as exc:
        public.create_homework(ready.folder, by_user=ready.teacher, title="x")
    assert exc.value.code == "folder.archived"
    public.set_folder_status(ready.folder, by_user=ready.teacher, status="active")
    assert public.create_homework(ready.folder, by_user=ready.teacher, title="x").pk


def test_read_helpers_enforce_visibility(ready):
    outsider = f.make_student(ready.org)
    with pytest.raises(public.FolderError) as exc:
        public.folder_contents(ready.folder, actor=outsider)
    assert exc.value.code == "permission.denied"
    with pytest.raises(public.FolderError):
        public.list_materials(ready.folder, actor=outsider)
    row = _submission(ready)
    with pytest.raises(public.FolderError):
        public.submission_detail(row, actor=ready.students[1])


def test_submission_detail_views(ready):
    from apps.subject_folder.models import SimilarityMatch

    row = _submission(ready)
    other = _submission(ready, 1)
    low, high = sorted([row, other], key=lambda item: item.pk)
    SimilarityMatch.objects.create(
        organization=ready.org, submission_a=low, submission_b=high, score="0.950", method="exact", is_flagged=True
    )
    teacher_view = public.submission_detail(row, actor=ready.teacher)
    assert teacher_view["can_review"] and teacher_view["actions"] == ["accept", "return", "reject"]
    assert len(teacher_view["matches"]) == 1 and not teacher_view["is_final"]
    student_view = public.submission_detail(row, actor=ready.students[0])
    assert student_view["matches"] == [] and student_view["actions"] == [] and not student_view["can_review"]
    assert [attempt.pk for attempt in student_view["attempts"]] == [row.pk]
    public.reject(row, by_user=ready.teacher, reason="plagiarism", feedback="Köçürülmüş iş")
    row.refresh_from_db()
    assert public.submission_detail(row, actor=ready.teacher)["actions"] == ["reopen"]
