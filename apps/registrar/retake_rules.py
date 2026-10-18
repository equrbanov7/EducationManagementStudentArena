"""25% / alt qrup müraciətinin QAYDALARI — status maşını, icazə açarları, tənzimləmələr (sahib 2026-10-18).

Təsdiq zənciri (sahibin seçdiyi variant):

* ``retake_25``: tələbə müraciət edir və qəbzi yükləyir → **Mühasibatlıq** ödənişi yoxlayır
  (``retake.payment_verify``) → **dekanlıq / tədris şöbəsi** imtahana buraxır (``retake.manage``) →
  İmtahan mərkəzi «İmtahan şansı ver» ilə cəhd verir (``exam_granted``) və ya kağız imtahanın balı yazılır →
  nəticə gələndə ``completed``.
* ``subgroup``: ödənişsiz; dekanlıq sənədlə təsdiqləyir və tələbəni rəsmi yerləşdirmə servisi ilə alt
  qrupa salır (``registrar.public.place_in_subgroup``) → ``completed``.

Keçidlər YALNIZ :data:`TRANSITIONS`-dakılardır; hər keçid servis qatında append-only hadisə yazır.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext, pgettext_lazy

from .models import RetakeKind, RetakeStatus

_CTX = "registrar.retake"

#: İcazə açarları — kataloqa və rol şablonlarına «Mühasibatlıq» agenti əlavə edir (organizations 0067).
PERM_PAYMENT_VERIFY = "retake.payment_verify"
PERM_MANAGE = "retake.manage"
#: İz (trail) oxusu — koordinator / dekanlıq / rəhbərlik (sahibin 2026-09-07 memo-su).
PERM_RECORDS_VIEW = "student.records_view"
#: Nəticəni İmtahan mərkəzi də yaza bilər (kağız imtahanın balı).
PERM_SCORE_ENTRY = "final_score.entry"

#: Səbəb tələb edən qərarlar üçün minimum uzunluq (``_reason_dialog`` ilə eyni).
REASON_MIN = 20

S = RetakeStatus
TRANSITIONS: dict[str, frozenset] = {
    S.SUBMITTED: frozenset({S.PAYMENT_PENDING_REVIEW, S.ADMITTED, S.REJECTED, S.WITHDRAWN}),
    S.PAYMENT_PENDING_REVIEW: frozenset({S.PAYMENT_VERIFIED, S.PAYMENT_REJECTED, S.WITHDRAWN}),
    S.PAYMENT_REJECTED: frozenset({S.PAYMENT_PENDING_REVIEW, S.WITHDRAWN}),
    S.PAYMENT_VERIFIED: frozenset({S.ADMITTED, S.REJECTED, S.WITHDRAWN}),
    S.ADMITTED: frozenset({S.EXAM_GRANTED, S.COMPLETED}),
    S.EXAM_GRANTED: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
    S.REJECTED: frozenset(),
    S.WITHDRAWN: frozenset(),
}

#: Tələbənin geri götürə bildiyi statuslar — «qərar verilməyənə qədər».
WITHDRAWABLE = frozenset({S.SUBMITTED, S.PAYMENT_PENDING_REVIEW, S.PAYMENT_REJECTED, S.PAYMENT_VERIFIED})
#: Qəbz yükləmək (ilk dəfə və ya rəddən sonra) mümkün olan statuslar.
RECEIPT_UPLOADABLE = frozenset({S.SUBMITTED, S.PAYMENT_REJECTED})
#: Nəticə yazıla bilən statuslar.
RESULT_RECORDABLE = frozenset({S.ADMITTED, S.EXAM_GRANTED})

#: Status → badge tonu (``core.ui.status_catalog`` ``retake`` ailəsi ilə eyni).
TONES = {
    S.SUBMITTED: "info",
    S.PAYMENT_PENDING_REVIEW: "warning",
    S.PAYMENT_REJECTED: "danger",
    S.PAYMENT_VERIFIED: "primary",
    S.ADMITTED: "primary",
    S.EXAM_GRANTED: "primary",
    S.COMPLETED: "success",
    S.REJECTED: "danger",
    S.WITHDRAWN: "muted",
}

#: Tələbəyə «növbəti addım» mətni.
NEXT_STEP = {
    S.SUBMITTED: pgettext_lazy(_CTX, "Ödəniş qəbzini yükləyin — Mühasibatlıq yalnız qəbzdən sonra yoxlayır."),
    S.PAYMENT_PENDING_REVIEW: pgettext_lazy(_CTX, "Qəbziniz Mühasibatlıqda yoxlanılır."),
    S.PAYMENT_REJECTED: pgettext_lazy(_CTX, "Qəbz rədd edilib — səbəbi oxuyun və düzgün qəbzi yenidən yükləyin."),
    S.PAYMENT_VERIFIED: pgettext_lazy(_CTX, "Ödəniş təsdiqlənib — dekanlığın buraxılış qərarı gözlənilir."),
    S.ADMITTED: pgettext_lazy(_CTX, "İmtahana buraxılmısınız — imtahan vaxtı İmtahan mərkəzi tərəfindən bildiriləcək."),
    S.EXAM_GRANTED: pgettext_lazy(_CTX, "İmtahan cəhdi açılıb — imtahan «Təyin olunmuş tapşırıqlar»da görünür."),
}
SUBGROUP_NEXT_STEP = {
    S.SUBMITTED: pgettext_lazy(_CTX, "Müraciətiniz dekanlıqdadır — alt qrup qərarı gözlənilir."),
    S.ADMITTED: pgettext_lazy(_CTX, "Alt qrup təsdiqlənib — yerləşdirmə gözlənilir."),
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise ValidationError(
            pgettext(_CTX, "Bu addım müraciətin cari vəziyyətində mümkün deyil ({current} → {target}).").format(
                current=RetakeStatus(current).label, target=RetakeStatus(target).label
            )
        )


def tone_for(status: str) -> str:
    return TONES.get(status, "neutral")


def next_step_for(application) -> str:
    if application.kind == RetakeKind.SUBGROUP:
        return str(SUBGROUP_NEXT_STEP.get(application.status, ""))
    return str(NEXT_STEP.get(application.status, ""))


# ── Tənzimləmələr (RİM «Sistem tənzimləmələri») ────────────────────────────


def applications_open() -> bool:
    from core import runtime_settings

    return runtime_settings.get_bool("retake.applications_open")


def max_attempts() -> int:
    from core import runtime_settings

    return max(1, runtime_settings.get_int("retake.max_attempts"))


def clean_reason(raw, *, minimum: int = REASON_MIN) -> str:
    text = str(raw or "").strip()
    if len(text) < minimum:
        raise ValidationError(
            pgettext(_CTX, "Səbəb ən azı {n} simvol olmalıdır — qərar zəncirində görünəcək.").format(n=minimum)
        )
    return text[:2000]


__all__ = [
    "NEXT_STEP",
    "PERM_MANAGE",
    "PERM_PAYMENT_VERIFY",
    "PERM_RECORDS_VIEW",
    "PERM_SCORE_ENTRY",
    "REASON_MIN",
    "RECEIPT_UPLOADABLE",
    "RESULT_RECORDABLE",
    "TRANSITIONS",
    "WITHDRAWABLE",
    "applications_open",
    "assert_transition",
    "can_transition",
    "clean_reason",
    "max_attempts",
    "next_step_for",
    "tone_for",
]
