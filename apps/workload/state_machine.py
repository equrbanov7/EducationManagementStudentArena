"""Tapşırıq sənədinin keçid cədvəli — SAF modul (spec §4.1).

Niyə ayrı fayl? ``apps/syllabus/state_machine.py`` naxışı: keçid qaydası nə
Django modelini, nə də servis qatını import etmir, ona görə onu testdə birbaşa
(baza olmadan) yoxlamaq olur və qayda İKİ yerdə yazılmır.

```
draft ──submit──> submitted ──dean qaytardı──> returned ──resubmit(revision++)──> submitted
                     │                                                              │
                     ├──bütün dilimlər təsdiqləndi──> approved <─ pending_final_approval
                     │
approved ──ilk bölgü──> distributing ──müdir təsdiqi──> distributed ──düzəliş──> amended
                                                              ^                    │
                                                              └────────────────────┘
draft / submitted ──> cancelled
```

⚠️ ``approved`` HEÇ VAXT birbaşa əl ilə qoyulmur — o, fakültə dilimlərinin
(``TaskFacultySlice``) yekunundan TÖRƏYİR (``services.workflow.recompute_task_status``).
"""

from __future__ import annotations

DRAFT = "draft"
SUBMITTED = "submitted"
RETURNED = "returned"
PENDING_FINAL_APPROVAL = "pending_final_approval"
APPROVED = "approved"
DISTRIBUTING = "distributing"
DISTRIBUTED = "distributed"
AMENDED = "amended"
CANCELLED = "cancelled"

#: status → icazəli növbəti statuslar (BÜTÜN qanuni keçidlər).
TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({SUBMITTED, DISTRIBUTING, CANCELLED}),
    SUBMITTED: frozenset({RETURNED, PENDING_FINAL_APPROVAL, APPROVED, CANCELLED}),
    RETURNED: frozenset({SUBMITTED, CANCELLED}),
    PENDING_FINAL_APPROVAL: frozenset({APPROVED, RETURNED}),
    APPROVED: frozenset({DISTRIBUTING, RETURNED}),
    DISTRIBUTING: frozenset({DISTRIBUTED, APPROVED}),
    DISTRIBUTED: frozenset({AMENDED}),
    AMENDED: frozenset({DISTRIBUTED}),
    CANCELLED: frozenset(),
}

#: Tədris şöbəsi sətirləri redaktə edə bilir (F1 redaktoru).
OFFICE_EDITABLE = frozenset({DRAFT, RETURNED})

#: Koordinator vizası / dekan qərarı yalnız bu statusda mümkündür.
REVIEWABLE = frozenset({SUBMITTED, PENDING_FINAL_APPROVAL})

#: Kafedra müdiri bölgüyə başlaya bilər (zəncir keçildikdən SONRA).
#: ``draft`` ona görə buradadır ki, F1-dən ƏVVƏL yaradılmış (heç vaxt
#: göndərilməmiş) kafedra sənədləri işləməyə davam etsin — göndərilmiş sənəd
#: üçün ``services.workflow.ensure_distribution_stage`` əlavə şərt qoyur.
DISTRIBUTABLE = frozenset({DRAFT, APPROVED, DISTRIBUTING, AMENDED})


class IllegalTransition(Exception):
    """Qanunsuz status keçidi — servis qatı bunu 409-a çevirir."""

    def __init__(self, current: str, target: str):
        super().__init__(current, target)
        self.current = current
        self.target = target
        self.code = "workload.illegal_transition"
        self.message = f"«{current}» statusundan «{target}» statusuna keçmək olmaz."


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def ensure_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise IllegalTransition(current, target)


__all__ = [
    "AMENDED",
    "APPROVED",
    "CANCELLED",
    "DISTRIBUTABLE",
    "DISTRIBUTED",
    "DISTRIBUTING",
    "DRAFT",
    "IllegalTransition",
    "OFFICE_EDITABLE",
    "PENDING_FINAL_APPROVAL",
    "RETURNED",
    "REVIEWABLE",
    "SUBMITTED",
    "TRANSITIONS",
    "can_transition",
    "ensure_transition",
]
