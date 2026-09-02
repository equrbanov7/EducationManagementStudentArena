"""State maşını — hər QANUNİ və QANUNSUZ keçid ayrıca yoxlanır (DB-siz)."""

from __future__ import annotations

import pytest

from apps.applications.constants import CLOSED_STATUSES, OPEN_STATUSES, ApplicationStatus
from apps.applications.state_machine import (
    ACTOR_HANDLER,
    ACTOR_SENDER,
    RULES,
    Action,
    TransitionDenied,
    available_actions,
    ensure_allowed,
    rule_for,
)

S = ApplicationStatus

#: (əməl, mənbə status) → icazəli keçidlərin TAM siyahısı.
LEGAL = [
    (Action.MARK_SEEN, S.SUBMITTED),
    (Action.ASSIGN, S.IN_REVIEW),
    (Action.ASSIGN, S.ASSIGNED),
    (Action.ASSIGN, S.FORWARDED),
    (Action.ASSIGN, S.WAITING_INFO),
    (Action.FORWARD, S.IN_REVIEW),
    (Action.FORWARD, S.FORWARDED),
    (Action.REQUEST_INFO, S.IN_REVIEW),
    (Action.PROVIDE_INFO, S.WAITING_INFO),
    (Action.RETURN_FOR_CORRECTION, S.IN_REVIEW),
    (Action.RESUBMIT, S.RETURNED),
    (Action.RESOLVE, S.IN_REVIEW),
    (Action.RESOLVE, S.ASSIGNED),
    (Action.REJECT, S.IN_REVIEW),
    (Action.CLOSE, S.RESOLVED),
    (Action.CANCEL, S.SUBMITTED),
    (Action.CANCEL, S.IN_REVIEW),
    (Action.CANCEL, S.WAITING_INFO),
]

ILLEGAL = [
    (Action.MARK_SEEN, S.IN_REVIEW),
    (Action.MARK_SEEN, S.RESOLVED),
    (Action.RESOLVE, S.SUBMITTED),
    (Action.RESOLVE, S.RESOLVED),
    (Action.RESOLVE, S.CLOSED),
    (Action.REJECT, S.SUBMITTED),
    (Action.REJECT, S.REJECTED),
    (Action.FORWARD, S.SUBMITTED),
    (Action.FORWARD, S.CLOSED),
    (Action.PROVIDE_INFO, S.IN_REVIEW),
    (Action.RESUBMIT, S.SUBMITTED),
    (Action.CLOSE, S.IN_REVIEW),
    (Action.CLOSE, S.CLOSED),
    (Action.CANCEL, S.RESOLVED),
    (Action.CANCEL, S.CLOSED),
    (Action.CANCEL, S.REJECTED),
    (Action.REQUEST_INFO, S.SUBMITTED),
    (Action.ASSIGN, S.SUBMITTED),
    (Action.RETURN_FOR_CORRECTION, S.RETURNED),
]


@pytest.mark.parametrize("action,status", LEGAL)
def test_legal_transitions_are_allowed(action, status):
    rule = ensure_allowed(action=action, status=status.value, text="Kifayət qədər uzun izah mətni")
    assert rule.name == action


@pytest.mark.parametrize("action,status", ILLEGAL)
def test_illegal_transitions_are_denied(action, status):
    with pytest.raises(TransitionDenied) as excinfo:
        ensure_allowed(action=action, status=status.value, text="Kifayət qədər uzun izah mətni")
    assert excinfo.value.code == "transition.invalid_source"


def test_unknown_action_is_denied():
    with pytest.raises(TransitionDenied) as excinfo:
        rule_for("teleport")
    assert excinfo.value.code == "transition.unknown"


@pytest.mark.parametrize(
    "action", [Action.RESOLVE, Action.REJECT, Action.FORWARD, Action.REQUEST_INFO, Action.RETURN_FOR_CORRECTION]
)
def test_decisions_require_a_reason(action):
    with pytest.raises(TransitionDenied) as excinfo:
        ensure_allowed(action=action, status=S.IN_REVIEW.value, text="   ")
    assert excinfo.value.code == "transition.reason_required"


@pytest.mark.parametrize(
    "action", [Action.RESOLVE, Action.REJECT, Action.FORWARD, Action.REQUEST_INFO, Action.RETURN_FOR_CORRECTION]
)
def test_decisions_require_ten_characters(action):
    with pytest.raises(TransitionDenied) as excinfo:
        ensure_allowed(action=action, status=S.IN_REVIEW.value, text="qısa")
    assert excinfo.value.code == "transition.text_too_short"
    assert excinfo.value.params["min_length"] == 10


def test_open_and_closed_partition_every_status():
    assert OPEN_STATUSES | CLOSED_STATUSES == {status.value for status in S}
    assert not (OPEN_STATUSES & CLOSED_STATUSES)


def test_terminal_statuses_admit_no_action_except_sender_close():
    for status in (S.REJECTED, S.CLOSED, S.CANCELLED):
        assert available_actions(status=status.value, is_handler=True, is_sender=True) == ()
    assert Action.CLOSE in available_actions(status=S.RESOLVED.value, is_handler=True, is_sender=True)


def test_available_actions_respect_the_actor():
    handler_only = available_actions(status=S.IN_REVIEW.value, is_handler=True, is_sender=False)
    assert Action.RESOLVE in handler_only and Action.CANCEL not in handler_only

    sender_only = available_actions(status=S.WAITING_INFO.value, is_handler=False, is_sender=True)
    assert Action.PROVIDE_INFO in sender_only and Action.RESOLVE not in sender_only

    assert available_actions(status=S.IN_REVIEW.value, is_handler=False, is_sender=False) == ()


def test_every_rule_names_a_known_actor_and_target():
    statuses = {status.value for status in S}
    for name, rule in RULES.items():
        assert rule.actor in {ACTOR_HANDLER, ACTOR_SENDER}, name
        assert rule.sources <= statuses, name
        assert rule.target is None or rule.target in statuses, name
