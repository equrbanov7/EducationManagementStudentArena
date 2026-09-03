"""State maşınının qaydaları — DB-siz vahid testlər (README §4)."""

from __future__ import annotations

import pytest

from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.state_machine import (
    APPROVED_LOCK_MESSAGE_CODE,
    Transition,
    TransitionDenied,
    allowed_transitions,
    check,
)

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]


def _submit(**overrides):
    kwargs = {
        "name": Transition.SUBMIT,
        "status": SyllabusStatus.DRAFT.value,
        "permissions": TEACHER_PERMS,
        "is_author": True,
        "completion_percent": 100,
    }
    kwargs.update(overrides)
    return check(**kwargs)


def test_submit_from_draft_is_allowed():
    assert _submit().target == SyllabusStatus.SUBMITTED.value


def test_submit_requires_full_completion():
    with pytest.raises(TransitionDenied) as excinfo:
        _submit(completion_percent=88)
    assert excinfo.value.code == "transition.incomplete"


def test_submit_requires_the_submit_permission():
    with pytest.raises(TransitionDenied) as excinfo:
        _submit(permissions=["syllabus.view", "syllabus.edit"])
    assert excinfo.value.code == "transition.permission_denied"


def test_submit_is_author_only():
    with pytest.raises(TransitionDenied) as excinfo:
        _submit(is_author=False)
    assert excinfo.value.code == "transition.author_only"


def test_approved_version_is_locked_against_every_transition_but_archive():
    for name in (Transition.SUBMIT, Transition.WITHDRAW, Transition.REQUEST_REVISION, Transition.REJECT):
        with pytest.raises(TransitionDenied) as excinfo:
            check(
                name=name,
                status=SyllabusStatus.APPROVED.value,
                permissions=["*"],
                reason="səbəb",
                is_author=True,
                completion_percent=100,
            )
        assert excinfo.value.code == APPROVED_LOCK_MESSAGE_CODE
    assert allowed_transitions(SyllabusStatus.APPROVED.value) == (Transition.ARCHIVE,)


@pytest.mark.parametrize(
    "name,permission",
    [
        (Transition.REQUEST_REVISION, "syllabus.revise"),
        (Transition.REJECT, "syllabus.reject"),
        (Transition.WITHDRAW, "syllabus.submit"),
    ],
)
def test_reason_is_mandatory(name, permission):
    with pytest.raises(TransitionDenied) as excinfo:
        check(
            name=name,
            status=SyllabusStatus.REVIEW.value,
            permissions=[permission],
            reason="   ",
            is_author=True,
        )
    assert excinfo.value.code == "transition.reason_required"


def test_reason_bearing_decision_passes():
    rule = check(
        name=Transition.REQUEST_REVISION,
        status=SyllabusStatus.REVIEW.value,
        permissions=CHAIR_PERMS,
        reason="Həftəlik saatlar tədris planı ilə uyğun deyil.",
    )
    assert rule.target == SyllabusStatus.REVISION.value


def test_out_of_scope_chair_is_denied_even_with_permission():
    with pytest.raises(TransitionDenied) as excinfo:
        check(
            name=Transition.APPROVE,
            status=SyllabusStatus.SUBMITTED.value,
            permissions=CHAIR_PERMS,
            in_scope=False,
        )
    assert excinfo.value.code == "transition.out_of_scope"


def test_unknown_transition_is_denied():
    with pytest.raises(TransitionDenied) as excinfo:
        check(name="teleport", status=SyllabusStatus.DRAFT.value, permissions=["*"])
    assert excinfo.value.code == "transition.unknown"


def test_revision_can_go_back_to_draft_or_straight_to_submitted():
    assert set(allowed_transitions(SyllabusStatus.REVISION.value)) == {
        Transition.SUBMIT,
        Transition.RESUME_EDITING,
    }


def test_rejected_and_archived_are_terminal():
    assert allowed_transitions(SyllabusStatus.REJECTED.value) == ()
    assert allowed_transitions(SyllabusStatus.ARCHIVED.value) == ()


def test_teacher_cannot_approve_own_syllabus():
    with pytest.raises(TransitionDenied) as excinfo:
        check(
            name=Transition.APPROVE,
            status=SyllabusStatus.SUBMITTED.value,
            permissions=TEACHER_PERMS,
            is_author=True,
        )
    assert excinfo.value.code == "transition.permission_denied"
