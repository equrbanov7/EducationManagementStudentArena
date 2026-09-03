"""Tədris planının TƏSDİQ ZƏNCİRİ — saf state maşını (dizayn handoff ekran 05).

Model qatında qərar YOXDUR; bütün keçidlər buradan keçir və hər keçid ÜÇ şeyi
tələb edir: mövcud status, icazə açarı, (bəzən) səbəb.

    qaralama ──göndər──> kafedra baxışı ──təsdiq──> fakültə şurası
                                              ──təsdiq──> tədris şöbəsi
                                                     ──təsdiq──> TƏSDİQLƏNİB
    hər baxış mərhələsi ──qaytar (səbəb ≥20)──> QAYTARILIB ──yenidən işlə──> qaralama

QAYDALAR (handoff §8)
---------------------
1. **Təsdiqlənmiş plan IMMUTABLE-dır** (qayda 1): sətir əlavəsi/redaktəsi/
   silinməsi və status keçidi QADAĞANDIR. Dəyişiklik yalnız YENİ VERSİYA —
   ``start_new_version`` köhnəni ``is_active=False`` edir (SİLMİR) və yeni
   qaralama yaradır. HTTP qatı bunu **409 Conflict** kimi qaytarır.
6. **Səbəb məcburidir** (≥20 simvol) «qaytar» əməlində; audit-ə aktor +
   timestamp ilə yazılır.
11. **Saat uzlaşması** pozulubsa təsdiqə GÖNDƏRMƏ bloklanır — bu modul yalnız
    keçidi rədd edir, hesablama ``curriculum_registry.plan_balance``-dədir.

Bu modul Django modelini İMPORT ETMİR (saf funksiyalar + istisnalar) — testdən
birbaşa çağırıla bilər və ``apps.syllabus.state_machine`` ilə eyni naxışdadır.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models.curriculum_meta import PLAN_REASON_MIN_LENGTH, PlanStatus


class PlanTransitionError(Exception):
    """Keçid rədd edildi. ``code`` HTTP qatının status kodunu seçir.

    ⚠️ Konstruktor QƏSDƏN POZİSİYALIDIR (kwarg yoxdur): flake8-bugbear B042
    istisna siniflərində kwarg-ı `pickle`/`copy` səbəbi ilə qadağan edir.
    """

    def __init__(self, code: str = "invalid", message: str = "", http_status: int = 400):
        super().__init__(code, message, http_status)
        self.code = code
        self.message = message
        self.http_status = http_status


class PlanImmutable(PlanTransitionError):
    """Təsdiqlənmiş plana yazma cəhdi — 409 (yeni versiya lazımdır)."""


@dataclass(frozen=True, slots=True)
class Transition:
    """Bir keçid: hansı statusdan hansına, hansı açarla, səbəb lazımdırmı."""

    action: str
    source: tuple[str, ...]
    target: str
    permission: str
    reason_required: bool = False


#: Zəncirin bütün keçidləri. Sıra UI-dakı düymə sırasıdır.
TRANSITIONS: tuple[Transition, ...] = (
    Transition("submit", (PlanStatus.DRAFT, PlanStatus.RETURNED), PlanStatus.CHAIR_REVIEW, "plan.submit"),
    Transition("approve_chair", (PlanStatus.CHAIR_REVIEW,), PlanStatus.FACULTY_COUNCIL, "plan.approve_chair"),
    Transition("approve_council", (PlanStatus.FACULTY_COUNCIL,), PlanStatus.TEACHING_OFFICE, "plan.approve_council"),
    Transition("approve_office", (PlanStatus.TEACHING_OFFICE,), PlanStatus.APPROVED, "plan.approve_office"),
    Transition(
        "return",
        (PlanStatus.CHAIR_REVIEW, PlanStatus.FACULTY_COUNCIL, PlanStatus.TEACHING_OFFICE),
        PlanStatus.RETURNED,
        # Qaytarmaq HƏMİŞƏ cari mərhələnin öz açarı ilə olur — `_return_permission`
        # onu statusa görə seçir; buradakı dəyər yalnız fallback-dır.
        "plan.approve_chair",
        reason_required=True,
    ),
    Transition("rework", (PlanStatus.RETURNED,), PlanStatus.DRAFT, "plan.edit"),
)

TRANSITIONS_BY_ACTION: dict[str, Transition] = {item.action: item for item in TRANSITIONS}

#: «Qaytar» əməli hansı mərhələdədirsə, ONUN təsdiq açarını tələb edir —
#: kafedra müdiri şuranın qərarını geri qaytara bilməz.
RETURN_PERMISSION_BY_STATUS: dict[str, str] = {
    PlanStatus.CHAIR_REVIEW: "plan.approve_chair",
    PlanStatus.FACULTY_COUNCIL: "plan.approve_council",
    PlanStatus.TEACHING_OFFICE: "plan.approve_office",
}

#: Sətir REDAKTƏSİNƏ icazə verən statuslar. Baxışdakı plan da kilidlidir:
#: qərar verən şəxs baxdığı sənədin altından dəyişməsini görməməlidir.
EDITABLE_STATUSES: frozenset[str] = frozenset({PlanStatus.DRAFT, PlanStatus.RETURNED})


def permission_for(action: str, current_status: str) -> str:
    """Keçid üçün TƏLƏB OLUNAN icazə açarı."""
    transition = TRANSITIONS_BY_ACTION.get(action)
    if transition is None:
        raise PlanTransitionError("unknown_action", "Naməlum əməl.")
    if action == "return":
        return RETURN_PERMISSION_BY_STATUS.get(current_status, transition.permission)
    return transition.permission


def is_editable(status: str) -> bool:
    return status in EDITABLE_STATUSES


def assert_editable(status: str) -> None:
    """Sətir yazmadan ƏVVƏL çağırılır. Təsdiqlənmiş plan → 409."""
    if status == PlanStatus.APPROVED:
        raise PlanImmutable(
            "plan_immutable",
            "Təsdiqlənmiş tədris planı dəyişdirilmir — dəyişiklik üçün yeni versiya yaradın.",
            409,
        )
    if not is_editable(status):
        raise PlanTransitionError(
            "plan_locked",
            "Plan təsdiq zəncirindədir — redaktə yalnız qaralama və ya qaytarılmış planda mümkündür.",
            409,
        )


def next_transition(status: str) -> Transition | None:
    """Cari statusdan İRƏLİ gedən keçid (UI-dakı əsas düymə)."""
    for transition in TRANSITIONS:
        if transition.action == "return":
            continue
        if status in transition.source:
            return transition
    return None


def resolve(action: str, *, current_status: str, permissions, reason: str = "", has_blocking_warnings=False):
    """Keçidi yoxlayır və HƏDƏF statusu qaytarır; uyğunsuzluqda istisna atır.

    ``permissions`` — aktorun effektiv icazə siyahısı; yoxlama
    ``core.permissions.has_permission`` ilə (wildcard-lar dəstəklənir).
    """
    from core.permissions import has_permission

    transition = TRANSITIONS_BY_ACTION.get(action)
    if transition is None:
        raise PlanTransitionError("unknown_action", "Naməlum əməl.")

    if current_status == PlanStatus.APPROVED:
        raise PlanImmutable(
            "plan_immutable",
            "Təsdiqlənmiş plan üzərində status dəyişikliyi mümkün deyil — yeni versiya yaradın.",
            409,
        )

    if current_status not in transition.source:
        raise PlanTransitionError(
            "illegal_transition",
            "Bu əməl planın cari vəziyyətində mümkün deyil.",
            409,
        )

    required = permission_for(action, current_status)
    if not has_permission(list(permissions or []), required):
        raise PlanTransitionError("forbidden", "Bu əməl üçün səlahiyyətiniz yoxdur.", 403)

    if transition.reason_required and len((reason or "").strip()) < PLAN_REASON_MIN_LENGTH:
        raise PlanTransitionError(
            "reason_too_short",
            "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.",
        )

    # Handoff §8 qayda 11 + ekran 05: «açıq xəbərdarlıq varsa təsdiqə göndərmə
    # BLOKLANIR». Yalnız GÖNDƏRMƏYƏ aiddir — təsdiq mərhələləri planı olduğu
    # kimi qəbul edir (xəbərdarlıq göndərişdə artıq bağlanmışdır).
    if action == "submit" and has_blocking_warnings:
        raise PlanTransitionError(
            "blocking_warnings",
            "Planda bağlanmamış xəbərdarlıq var (kredit/saat balansı) — təsdiqə göndərmək mümkün deyil.",
        )

    return transition.target


__all__ = [
    "EDITABLE_STATUSES",
    "PlanImmutable",
    "PlanTransitionError",
    "RETURN_PERMISSION_BY_STATUS",
    "TRANSITIONS",
    "TRANSITIONS_BY_ACTION",
    "Transition",
    "assert_editable",
    "is_editable",
    "next_transition",
    "permission_for",
    "resolve",
]
