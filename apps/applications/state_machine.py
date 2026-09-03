"""Müraciət state maşını — README §3.4-ün genişləndirilmiş kod qarşılığı.

```
submitted ──baxış──▶ in_review ──┬── resolve ──▶ resolved ──(təsdiq / 5 iş günü)──▶ closed
     │                           ├── reject (səbəb) ──▶ rejected            [terminal]
     │                           ├── request_info ──▶ waiting_info ──provide_info──▶ in_review
     │                           ├── return_for_correction (səbəb) ──▶ returned ──resubmit──▶ submitted
     │                           ├── assign ──▶ assigned
     │                           └── forward (qeyd ≥10) ──▶ forwarded  (cari şöbə DƏYİŞİR)
     └── cancel (yalnız sahib, açıq ikən) ──▶ cancelled                     [terminal]
```

Bu modul YALNIZ qaydaları saxlayır — DB yazısı ``services.workflow``-dadır.
FAIL-CLOSED: naməlum əməl, yanlış mənbə status, səbəbsiz rədd/qaytarma,
səlahiyyətsiz aktor — hamısı ``TransitionDenied`` ilə dayanır.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import HANDLER_ACTION_SOURCES, OPEN_STATUSES, ApplicationStatus


class TransitionDenied(Exception):
    """Keçid qadağandır. ``code`` maşın-oxunaqlı səbəbdir (UI mətni üçün açar)."""

    def __init__(self, code: str, message: str = "", params: dict | None = None):
        super().__init__(code, message, params)
        self.code = code
        self.params = params or {}

    def __str__(self) -> str:
        return self.args[1] or self.code


class Action:
    """Əməl adları — servis API-si, hadisə növü və audit eyni sətirləri işlədir."""

    MARK_SEEN = "mark_seen"
    ADD_COMMENT = "add_comment"
    ASSIGN = "assign"
    FORWARD = "forward"
    REQUEST_INFO = "request_info"
    PROVIDE_INFO = "provide_info"
    RETURN_FOR_CORRECTION = "return_for_correction"
    RESUBMIT = "resubmit"
    RESOLVE = "resolve"
    REJECT = "reject"
    CLOSE = "close"
    CANCEL = "cancel"


#: Əməli kim edir: ``handler`` (cari şöbə) | ``sender`` (müraciət sahibi).
ACTOR_HANDLER = "handler"
ACTOR_SENDER = "sender"


@dataclass(frozen=True)
class ActionRule:
    name: str
    sources: frozenset
    #: ``None`` = status dəyişmir (yalnız qeyd yazılır).
    target: str | None
    actor: str
    reason_required: bool = False
    #: Əməl mətni (qeyd/səbəb) ən azı neçə simvol olmalıdır.
    min_text_length: int = 0


_HANDLER_SOURCES = frozenset(HANDLER_ACTION_SOURCES)
_COMMENT_SOURCES = frozenset(OPEN_STATUSES)

RULES = {
    Action.MARK_SEEN: ActionRule(
        name=Action.MARK_SEEN,
        sources=frozenset({ApplicationStatus.SUBMITTED.value}),
        target=ApplicationStatus.IN_REVIEW.value,
        actor=ACTOR_HANDLER,
    ),
    Action.ADD_COMMENT: ActionRule(
        name=Action.ADD_COMMENT,
        sources=_COMMENT_SOURCES,
        target=None,
        actor=ACTOR_HANDLER,
        min_text_length=1,
    ),
    Action.ASSIGN: ActionRule(
        name=Action.ASSIGN,
        sources=_HANDLER_SOURCES,
        target=ApplicationStatus.ASSIGNED.value,
        actor=ACTOR_HANDLER,
    ),
    Action.FORWARD: ActionRule(
        name=Action.FORWARD,
        sources=_HANDLER_SOURCES,
        target=ApplicationStatus.FORWARDED.value,
        actor=ACTOR_HANDLER,
        reason_required=True,
        min_text_length=10,
    ),
    Action.REQUEST_INFO: ActionRule(
        name=Action.REQUEST_INFO,
        sources=_HANDLER_SOURCES,
        target=ApplicationStatus.WAITING_INFO.value,
        actor=ACTOR_HANDLER,
        reason_required=True,
        min_text_length=10,
    ),
    Action.PROVIDE_INFO: ActionRule(
        name=Action.PROVIDE_INFO,
        sources=frozenset({ApplicationStatus.WAITING_INFO.value}),
        target=ApplicationStatus.IN_REVIEW.value,
        actor=ACTOR_SENDER,
        reason_required=True,
        min_text_length=10,
    ),
    Action.RETURN_FOR_CORRECTION: ActionRule(
        name=Action.RETURN_FOR_CORRECTION,
        sources=_HANDLER_SOURCES,
        target=ApplicationStatus.RETURNED.value,
        actor=ACTOR_HANDLER,
        reason_required=True,
        min_text_length=10,
    ),
    Action.RESUBMIT: ActionRule(
        name=Action.RESUBMIT,
        sources=frozenset({ApplicationStatus.RETURNED.value}),
        target=ApplicationStatus.SUBMITTED.value,
        actor=ACTOR_SENDER,
    ),
    Action.RESOLVE: ActionRule(
        name=Action.RESOLVE,
        sources=_HANDLER_SOURCES,
        target=ApplicationStatus.RESOLVED.value,
        actor=ACTOR_HANDLER,
        reason_required=True,
        min_text_length=10,
    ),
    Action.REJECT: ActionRule(
        name=Action.REJECT,
        sources=_HANDLER_SOURCES,
        target=ApplicationStatus.REJECTED.value,
        actor=ACTOR_HANDLER,
        reason_required=True,
        min_text_length=10,
    ),
    Action.CLOSE: ActionRule(
        name=Action.CLOSE,
        sources=frozenset({ApplicationStatus.RESOLVED.value}),
        target=ApplicationStatus.CLOSED.value,
        actor=ACTOR_SENDER,
    ),
    Action.CANCEL: ActionRule(
        name=Action.CANCEL,
        sources=frozenset(OPEN_STATUSES),
        target=ApplicationStatus.CANCELLED.value,
        actor=ACTOR_SENDER,
    ),
}

#: Emalçının cavab qutusundakı əməllər (UI düymələri) — sıralama dizayn §4.7.
HANDLER_ACTIONS = (
    Action.RESOLVE,
    Action.REQUEST_INFO,
    Action.FORWARD,
    Action.RETURN_FOR_CORRECTION,
    Action.REJECT,
    Action.ASSIGN,
    Action.ADD_COMMENT,
    Action.MARK_SEEN,
)
SENDER_ACTIONS = (Action.PROVIDE_INFO, Action.RESUBMIT, Action.CLOSE, Action.CANCEL)


def rule_for(action: str) -> ActionRule:
    rule = RULES.get(action)
    if rule is None:
        raise TransitionDenied("transition.unknown", f"Naməlum əməl: {action}", {"action": action})
    return rule


def ensure_allowed(*, action: str, status: str, text: str = "") -> ActionRule:
    """Qaydanı yoxlayır və qaytarır; pozuntuda ``TransitionDenied`` atır.

    İCAZƏ yoxlanışı burada DEYİL (servis qatındadır) — bu funksiya yalnız
    status maşınının strukturunu qoruyur.
    """
    rule = rule_for(action)
    if status not in rule.sources:
        raise TransitionDenied(
            "transition.invalid_source",
            f"«{action}» əməli «{status}» statusundan mümkün deyil.",
            {"action": action, "status": status},
        )
    cleaned = (text or "").strip()
    if rule.reason_required and not cleaned:
        raise TransitionDenied(
            "transition.reason_required",
            "Bu əməl üçün mətn məcburidir.",
            {"action": action},
        )
    if rule.min_text_length and len(cleaned) < rule.min_text_length:
        raise TransitionDenied(
            "transition.text_too_short",
            f"Mətn ən azı {rule.min_text_length} simvol olmalıdır.",
            {"action": action, "min_length": rule.min_text_length},
        )
    return rule


def available_actions(*, status: str, is_handler: bool, is_sender: bool) -> tuple:
    """Bu status + bu aktor üçün mümkün əməllər (UI ``allowed_actions``)."""
    actions = []
    for name in HANDLER_ACTIONS + SENDER_ACTIONS:
        rule = RULES[name]
        if status not in rule.sources:
            continue
        if rule.actor == ACTOR_HANDLER and not is_handler:
            continue
        if rule.actor == ACTOR_SENDER and not is_sender:
            continue
        actions.append(name)
    return tuple(actions)


__all__ = [
    "ACTOR_HANDLER",
    "ACTOR_SENDER",
    "Action",
    "ActionRule",
    "HANDLER_ACTIONS",
    "RULES",
    "SENDER_ACTIONS",
    "TransitionDenied",
    "available_actions",
    "ensure_allowed",
    "rule_for",
]
