"""Sillabus state maşını — README §4-ün YEGANƏ kod qarşılığı.

```
DRAFT ──(təsdiqə göndər)──> SUBMITTED ──(müdir açır)──> REVIEW
  ^                              │                        │
  │                              │(geri çağır, səbəb)     ├─(təsdiqlə)──> APPROVED [kilidli]
  └──────────────────────────────┘                        ├─(düzəliş, səbəb)──> REVISION ──> DRAFT
                                                          └─(rədd et, səbəb)──> REJECTED
APPROVED ──(yeni versiya)──> minor (cari semestr) | major (növbəti semestr) → DRAFT
Köhnə APPROVED ──(yeni versiya təsdiqlənəndə)──> ARCHIVED
```

Bu modul YALNIZ qaydaları saxlayır — DB yazısı yoxdur. Keçidin icrası
:mod:`apps.syllabus.services.workflow`-dadır; view qatı state maşınını BİRBAŞA
çağırmır, servis funksiyasını çağırır.

FAIL-CLOSED: naməlum keçid, icazəsi olmayan aktor, səbəbsiz düzəliş/rədd —
hamısı ``TransitionDenied`` ilə dayandırılır; «icazə tapılmadı → keç» davranışı
YOXDUR.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    PERM_APPROVE,
    PERM_MANAGE,
    PERM_REJECT,
    PERM_REVIEW,
    PERM_REVISE,
    PERM_SUBMIT,
    REASON_REQUIRED_STATUSES,
    SyllabusStatus,
)


class TransitionDenied(Exception):
    """Keçid qadağandır. ``code`` maşın-oxunaqlı səbəbdir (UI mətni üçün açar)."""

    # Bütün arqumentlər ``super()``-ə ötürülür ki, istisna pickle/copy edilə
    # bilsin (flake8-bugbear B042); oxunaqlı mətn ``__str__``-dan gəlir.
    def __init__(self, code: str, message: str = "", params: dict | None = None):
        super().__init__(code, message, params)
        self.code = code
        self.params = params or {}

    def __str__(self) -> str:
        return self.args[1] or self.code


class Transition:
    """Keçid adları — servis API-si və audit qeydi eyni sətirləri işlədir."""

    SUBMIT = "submit"
    WITHDRAW = "withdraw"
    START_REVIEW = "start_review"
    APPROVE = "approve"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    RESUME_EDITING = "resume_editing"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class TransitionRule:
    """Bir keçidin qaydası."""

    name: str
    sources: frozenset
    target: str
    permission: str
    reason_required: bool = False
    #: Keçid üçün sillabus 100% tamamlanmalıdırmı.
    requires_complete: bool = False
    #: Keçidi yalnız müəllif/təqdim edən edə bilərmi (kafedra tərəfi deyil).
    author_only: bool = False


TRANSITIONS = {
    Transition.SUBMIT: TransitionRule(
        name=Transition.SUBMIT,
        sources=frozenset({SyllabusStatus.DRAFT.value, SyllabusStatus.REVISION.value}),
        target=SyllabusStatus.SUBMITTED.value,
        permission=PERM_SUBMIT,
        requires_complete=True,
        author_only=True,
    ),
    Transition.WITHDRAW: TransitionRule(
        name=Transition.WITHDRAW,
        sources=frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value}),
        target=SyllabusStatus.DRAFT.value,
        permission=PERM_SUBMIT,
        reason_required=True,
        author_only=True,
    ),
    Transition.START_REVIEW: TransitionRule(
        name=Transition.START_REVIEW,
        sources=frozenset({SyllabusStatus.SUBMITTED.value}),
        target=SyllabusStatus.REVIEW.value,
        permission=PERM_REVIEW,
    ),
    Transition.APPROVE: TransitionRule(
        name=Transition.APPROVE,
        sources=frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value}),
        target=SyllabusStatus.APPROVED.value,
        permission=PERM_APPROVE,
    ),
    Transition.REQUEST_REVISION: TransitionRule(
        name=Transition.REQUEST_REVISION,
        sources=frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value}),
        target=SyllabusStatus.REVISION.value,
        permission=PERM_REVISE,
        reason_required=True,
    ),
    Transition.REJECT: TransitionRule(
        name=Transition.REJECT,
        sources=frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value}),
        target=SyllabusStatus.REJECTED.value,
        permission=PERM_REJECT,
        reason_required=True,
    ),
    Transition.RESUME_EDITING: TransitionRule(
        name=Transition.RESUME_EDITING,
        sources=frozenset({SyllabusStatus.REVISION.value}),
        target=SyllabusStatus.DRAFT.value,
        permission=PERM_SUBMIT,
        author_only=True,
    ),
    Transition.ARCHIVE: TransitionRule(
        name=Transition.ARCHIVE,
        sources=frozenset({SyllabusStatus.APPROVED.value}),
        target=SyllabusStatus.ARCHIVED.value,
        permission=PERM_MANAGE,
    ),
}

#: ``APPROVED``-dan çıxan YEGANƏ keçid arxivləmədir — və o da yalnız yeni versiya
#: təsdiqlənəndə sistem tərəfindən icra olunur. Redaktə/geri çağırma/yenidən
#: təsdiq YOXDUR: təsdiqlənmiş versiya jurnalın mənbəyidir.
APPROVED_LOCK_MESSAGE_CODE = "version.approved_locked"


def allowed_transitions(status: str) -> tuple:
    """Verilmiş statusdan mümkün keçidlərin adları."""
    return tuple(name for name, rule in TRANSITIONS.items() if status in rule.sources)


def get_rule(name: str) -> TransitionRule:
    rule = TRANSITIONS.get(name)
    if rule is None:
        raise TransitionDenied("transition.unknown", params={"transition": name})
    return rule


def check(
    *,
    name: str,
    status: str,
    permissions,
    reason: str = "",
    is_author: bool = False,
    completion_percent: int | None = None,
    in_scope: bool = True,
) -> TransitionRule:
    """Keçidin BÜTÜN şərtlərini yoxlayır; pozuntuda ``TransitionDenied`` atır.

    ``permissions`` — aktorun icazə sətirləri (rolun ``permissions`` siyahısı);
    wildcard uyğunluğu üçün ``core.permissions.has_permission`` işlədilir.
    ``in_scope`` — kafedra müdirinin öz kafedrası şərtinin nəticəsi; çağıran
    tərəf onu :mod:`apps.syllabus.services.scoping` ilə hesablayır və BURAYA
    hazır bool kimi verir (fail-closed: şübhə varsa ``False``).
    """
    from core.permissions import has_permission

    rule = get_rule(name)

    if status not in rule.sources:
        if status == SyllabusStatus.APPROVED.value and name != Transition.ARCHIVE:
            raise TransitionDenied(APPROVED_LOCK_MESSAGE_CODE, params={"status": status})
        raise TransitionDenied("transition.invalid_source", params={"transition": name, "status": status})

    if not has_permission(list(permissions or []), rule.permission):
        raise TransitionDenied("transition.permission_denied", params={"permission": rule.permission})

    if not in_scope:
        raise TransitionDenied("transition.out_of_scope", params={"transition": name})

    if rule.author_only and not is_author:
        raise TransitionDenied("transition.author_only", params={"transition": name})

    if rule.reason_required and not (reason or "").strip():
        raise TransitionDenied("transition.reason_required", params={"transition": name})

    if rule.requires_complete and (completion_percent or 0) < 100:
        raise TransitionDenied(
            "transition.incomplete",
            params={"transition": name, "percent": completion_percent or 0},
        )

    return rule


def target_requires_reason(status: str) -> bool:
    """Hədəf statusun səbəb tələb edib-etmədiyi (DB check ilə eyni qayda)."""
    return status in REASON_REQUIRED_STATUSES


__all__ = [
    "APPROVED_LOCK_MESSAGE_CODE",
    "TRANSITIONS",
    "Transition",
    "TransitionDenied",
    "TransitionRule",
    "allowed_transitions",
    "check",
    "get_rule",
    "target_requires_reason",
]
