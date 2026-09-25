"""Tələbə göndərişi → müəllim baxışı: qaytar/yenidən göndər (0 yazılmır), qəbul (bal), yoxlandı, rədd."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

import pytest

from apps.subject_folder import public
from apps.subject_folder.models import Submission, SubmissionEvent

from .conftest import upload

pytestmark = pytest.mark.django_db


def _submit(ready, student=None, task=None, **kwargs):
    kwargs.setdefault("text", "Mənim cavabım burada yazılıb")
    return public.submit(
        task=task or ready.slot1, assignment=ready.assignment, student=student or ready.students[0], **kwargs
    )


def test_submit_creates_first_attempt_with_event_and_hash(ready):
    row = _submit(ready, files=[upload()])
    assert (row.status, row.attempt_no, row.is_current) == ("submitted", 1, True)
    assert row.submitted_at is not None and len(row.content_sha256) == 64
    assert row.files.count() == 1 and row.files.get().original_name == "work.txt"
    assert list(row.events.values_list("kind", flat=True)) == ["submitted"]


def test_pending_submission_blocks_second_send(ready):
    _submit(ready)
    with pytest.raises(public.FolderError) as exc:
        _submit(ready)
    assert exc.value.code == "submission.pending"


def test_return_requires_feedback_never_writes_points_and_resubmit_keeps_history(ready):
    first = _submit(ready)
    with pytest.raises(public.FolderError) as exc:
        public.return_for_revision(first, by_user=ready.teacher, feedback="  ")
    assert exc.value.code == "review.feedback_required"
    returned = public.return_for_revision(first, by_user=ready.teacher, feedback="Mənbələri əlavə edin")
    assert returned.status == "returned" and returned.points is None
    second = _submit(ready, text="Yenidən işlənmiş cavab")
    first.refresh_from_db()
    assert (second.attempt_no, second.is_current, first.is_current) == (2, True, False)
    assert first.feedback == "Mənbələri əlavə edin" and first.points is None
    history = Submission.objects.filter(task=ready.slot1, enrollment=ready.enrollments[0]).order_by("attempt_no")
    assert [row.status for row in history] == ["returned", "submitted"]
    assert list(second.events.values_list("kind", flat=True)) == ["resubmitted"]


def test_accept_writes_points_and_marks_journal_pending(ready, django_capture_on_commit_callbacks):
    row = _submit(ready)
    preview = public.journal_preview(row, points="4")
    assert preview["can_award"] and preview["text"] == "Bu bal jurnala düşəcək: Sərbəst iş 1 · 4/5 (cəmi 4/10)"
    with django_capture_on_commit_callbacks(execute=True):
        accepted = public.accept(row, by_user=ready.teacher, points="4", feedback="Yaxşı")
    accepted.refresh_from_db()
    assert (accepted.status, accepted.points, accepted.points_max) == ("accepted", Decimal("4.0"), Decimal("5.0"))
    assert accepted.journal_sync_status == "pending"  # registrar hook-u hələ yoxdur
    kinds = list(accepted.events.values_list("kind", flat=True))
    assert kinds == ["submitted", "accepted"]


@pytest.mark.parametrize("points", ["0", "-1", "5.5", "4.55", "abc"])
def test_invalid_points_are_rejected(ready, points):
    row = _submit(ready)
    with pytest.raises(public.FolderError) as exc:
        public.accept(row, by_user=ready.teacher, points=points)
    assert exc.value.code == "review.points_invalid"
    row.refresh_from_db()
    assert row.status == "submitted" and row.points is None


def test_half_points_are_allowed(ready):
    row = public.accept(_submit(ready), by_user=ready.teacher, points="4,5")
    assert row.points == Decimal("4.5")


def test_no_second_award_for_same_slot(ready, folder):
    public.accept(_submit(ready), by_user=ready.teacher, points="5")
    with pytest.raises(public.FolderError) as exc:
        _submit(ready)
    assert exc.value.code == "submission.closed"
    # Sillabus dəyişib slot üçün YENİ tapşırıq açılsa belə eyni slota ikinci bal yoxdur.
    from . import factories as f

    f.approve_syllabus(ready.offering, ready.teacher, option="1x10")
    public.resync_folder(folder, by_user=ready.teacher)
    replacement = folder.tasks.get(kind="selfwork", slot_index=1, is_archived=False)
    public.set_task_published(replacement, by_user=ready.teacher, published=True)
    second = _submit(ready, task=replacement)
    with pytest.raises(public.FolderError) as exc:
        public.accept(second, by_user=ready.teacher, points="3")
    assert exc.value.code == "review.already_awarded"


def test_two_slots_sum_to_ten_and_students_are_independent(ready):
    slot1, slot2 = ready.slots
    public.accept(_submit(ready, task=slot1), by_user=ready.teacher, points="5")
    row = _submit(ready, task=slot2)
    preview = public.journal_preview(row, points="5")
    assert (preview["total_before"], preview["total_after"], preview["can_award"]) == (5, 10, True)
    assert preview["text"].endswith("(cəmi 10/10)")
    public.accept(row, by_user=ready.teacher, points="5")
    other = _submit(ready, task=slot1, student=ready.students[1])
    assert public.journal_preview(other)["total_before"] == 0


def test_total_cap_error_names_remaining(ready, folder):
    from apps.subject_folder.models import FolderTask

    enrollment = ready.enrollments[0]
    legacy = FolderTask.objects.create(
        organization=ready.org,
        folder=folder,
        kind="selfwork",
        title="Köhnə slot",
        slot_index=9,
        max_points=Decimal("8"),
        is_archived=True,
    )
    Submission.objects.create(
        organization=ready.org,
        task=legacy,
        assignment=ready.assignment,
        enrollment=enrollment,
        student=ready.students[0],
        kind="selfwork",
        status="accepted",
        points=Decimal("8"),
        points_max=Decimal("8"),
    )
    row = _submit(ready)
    with pytest.raises(public.FolderError) as exc:
        public.accept(row, by_user=ready.teacher, points="3")
    assert exc.value.code == "review.points_total_exceeded"
    assert exc.value.params["remaining"] == Decimal("2")
    assert public.accept(row, by_user=ready.teacher, points="2").points == Decimal("2")


def test_homework_is_checked_not_graded(ready):
    row = _submit(ready, task=ready.homework)
    with pytest.raises(public.FolderError) as exc:
        public.accept(row, by_user=ready.teacher, points="3")
    assert exc.value.code == "review.homework_has_no_points"
    checked = public.check_homework(row, by_user=ready.teacher)
    assert (checked.status, checked.points, checked.journal_sync_status) == ("checked", None, "none")
    selfwork = _submit(ready)
    with pytest.raises(public.FolderError) as exc:
        public.check_homework(selfwork, by_user=ready.teacher)
    assert exc.value.code == "review.selfwork_needs_points"


def test_reject_requires_reason_and_reopen_allows_resubmission(ready):
    row = _submit(ready)
    with pytest.raises(public.FolderError) as exc:
        public.reject(row, by_user=ready.teacher, reason="nonsense", feedback="Köçürülmüş iş")
    assert exc.value.code == "review.reason_invalid"
    rejected = public.reject(row, by_user=ready.teacher, reason="plagiarism", feedback="Köçürülmüş iş")
    assert rejected.status == "rejected" and rejected.points is None
    with pytest.raises(public.FolderError):
        _submit(ready)
    reopened = public.reopen(rejected, by_user=ready.teacher, feedback="Yenidən yazın")
    assert reopened.status == "returned"
    assert _submit(ready).attempt_no == 2


def test_deadline_policies(ready):
    now = timezone.now()
    public.set_deadline(ready.assignment, ready.slot1, by_user=ready.teacher, due_at=now - timedelta(hours=1))
    with pytest.raises(public.FolderError) as exc:
        _submit(ready)
    assert exc.value.code == "deadline.passed"
    public.set_deadline(
        ready.assignment, ready.slot1, by_user=ready.teacher, due_at=now - timedelta(hours=1), late_policy="allow"
    )
    late = _submit(ready)
    assert late.is_late
    # Son tarixdən sonra QAYTARILAN iş yenidən göndərilə bilər (gecikmə siyasəti «none» olsa da).
    public.set_deadline(ready.assignment, ready.slot1, by_user=ready.teacher, due_at=now - timedelta(hours=1))
    public.return_for_revision(late, by_user=ready.teacher, feedback="Düzəldin zəhmət olmasa")
    assert _submit(ready).is_late
    public.set_deadline(ready.assignment, ready.slots[1], by_user=ready.teacher, opens_at=now + timedelta(days=1))
    with pytest.raises(public.FolderError) as exc:
        _submit(ready, task=ready.slots[1])
    assert exc.value.code == "deadline.not_open"
    with pytest.raises(public.FolderError) as exc:
        public.set_deadline(ready.assignment, ready.slot1, by_user=ready.teacher, opens_at=now, due_at=now)
    assert exc.value.code == "deadline.invalid_range"


def test_payload_validation(ready):
    with pytest.raises(public.FolderError) as exc:
        _submit(ready, text="   ")
    assert exc.value.code == "submission.empty"
    public.update_task(
        ready.homework, by_user=ready.teacher, allow_text_answer=False, max_files=1, allowed_extensions=["pdf"]
    )
    with pytest.raises(public.FolderError) as exc:
        _submit(ready, task=ready.homework, text="mətn")
    assert exc.value.code == "submission.text_not_allowed"
    with pytest.raises(public.FolderError) as exc:
        _submit(ready, task=ready.homework, text=None, files=[upload()])
    assert exc.value.code == "upload.invalid"  # .txt icazəli siyahıda deyil
    pdf = [upload("a.pdf", b"%PDF-1.4 a", "application/pdf"), upload("b.pdf", b"%PDF-1.4 b", "application/pdf")]
    with pytest.raises(public.FolderError) as exc:
        _submit(ready, task=ready.homework, text=None, files=pdf)
    assert exc.value.code == "submission.too_many_files"
    fake = upload("evil.pdf", b"<html><script>alert(1)</script>", "application/pdf")
    with pytest.raises(public.FolderError) as exc:
        _submit(ready, task=ready.homework, text=None, files=[fake])
    assert exc.value.code == "upload.invalid"
    assert not Submission.objects.filter(task=ready.homework).exists()


def test_draft_then_submit_merges_and_draft_file_can_be_removed(ready):
    draft = public.save_draft(
        task=ready.slot1, assignment=ready.assignment, student=ready.students[0], text="qaralama", files=[upload()]
    )
    assert draft.status == "draft"
    extra = public.save_draft(
        task=ready.slot1, assignment=ready.assignment, student=ready.students[0], files=[upload("b.txt", b"iki")]
    )
    assert extra.pk == draft.pk and extra.files.count() == 2
    public.remove_draft_file(extra.files.get(original_name="b.txt"), student=ready.students[0])
    sent = _submit(ready, text=None)
    assert sent.pk == draft.pk and sent.status == "submitted" and sent.text_answer == "qaralama"
    with pytest.raises(public.FolderError) as exc:
        public.remove_draft_file(sent.files.get(), student=ready.students[0])
    assert exc.value.code == "submission.not_draft"
    assert set(SubmissionEvent.objects.filter(submission=sent).values_list("kind", flat=True)) == {
        "draft_saved",
        "file_removed",
        "submitted",
    }


def test_bulk_review_isolates_failures(ready):
    rows = [_submit(ready, student=student) for student in ready.students]
    public.accept(rows[2], by_user=ready.teacher, points="1")
    result = public.bulk_review(
        rows, by_user=ready.teacher, action="accept", points={str(rows[0].pk): "5", str(rows[1].pk): "9"}
    )
    assert result["ok"] == [str(rows[0].pk)]
    assert result["failed"][str(rows[1].pk)]["code"] == "review.points_invalid"
    assert result["failed"][str(rows[2].pk)]["code"] == "submission.not_reviewable"
