"""Jurnaldan çıxarılmanın SƏBƏBİ — doğrulama + yazı + jurnal tarixçəsi (sahib 2026-11-04).

Sahib: «Jurnalda hansısa tələbəni çıxardarkən səbəb seçmə olsun select option ilə … Daha sonra mən harada isə
onda baxa bilim o tip hadisələrə — nəyə görə olub.»

YENİ ÇIXARMA MEXANİZMİ YOXDUR. Mövcud iki əməl öz işini görür:

* «Fəndən azad et» — :func:`apps.registrar.subject_exempt.exempt_student` (qərar jurnalı + audit);
* alt qrupdan əlavənin «Çıxar»-ı — :func:`apps.registrar.guest_roster.remove_guest_student`.

Bu modul onlara «niyə» qatını əlavə edir, ÇAĞIRANIN tranzaksiyasında:

1. :func:`clean` — HTTP girişinin doğrulanması (səbəb seçilməlidir, «Digər» qeydsiz olmur) → istifadəçi xətası;
2. :func:`record` — :class:`~apps.registrar.models.JournalRemoval` sətri (append-only) + jurnalın «Dəyişiklik
   tarixçəsi»nə ``registrar.grade.roster-removal`` audit sətri (fail-closed: səbəbsiz çıxarılma commit olunmur).

Mərkəzi siyahı (RİM rəhbəri / superadmin) :mod:`apps.registrar.journal_removal_read`-dədir.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from . import grade_audit
from .models import REMOVAL_NOTE_MAX_LENGTH, JournalRemoval, RemovalAction, RemovalReason

_CTX = "registrar.journal_removal"

#: Jurnal tarixçəsindəki növ (``registrar.grade.<kind>`` — ``journal_history`` bir prefikslə oxuyur).
HISTORY_KIND = "roster-removal"
HISTORY_RESTORE_KIND = "roster-restore"

#: HTTP sahə adları (modal ``journal_subject_exempt.js`` / ``journal_guest.js`` bunları göndərir).
REASON_FIELD = "removal_reason"
NOTE_FIELD = "removal_note"


class RemovalReasonError(Exception):
    """İstifadəçiyə göstərilə bilən doğrulama xətası (HTTP 400)."""

    def __init__(self, code, message):
        super().__init__(code, message)
        self.code = code
        self.message = str(message)


def reason_choices() -> list:
    """Modalın seçim siyahısı — ``[(value, label), …]`` (aktiv dildə)."""
    return [(choice.value, str(choice.label)) for choice in RemovalReason]


def reason_label(value) -> str:
    try:
        return str(RemovalReason(value).label)
    except ValueError:
        return str(value or "")


def action_label(value) -> str:
    try:
        return str(RemovalAction(value).label)
    except ValueError:
        return str(value or "")


def clean_note(raw) -> str:
    return " ".join(str(raw or "").split())[:REMOVAL_NOTE_MAX_LENGTH]


def clean(reason, note) -> dict:
    """``{"reason", "note"}`` — səbəb siyahıdan seçilməlidir, «Digər» üçün qeyd məcburidir."""
    value = str(reason or "").strip()
    if not value:
        raise RemovalReasonError("reason_required", pgettext(_CTX, "Çıxarılma səbəbini seçin."))
    if value not in RemovalReason.values:
        raise RemovalReasonError("reason_invalid", pgettext(_CTX, "Çıxarılma səbəbi tanınmadı — siyahıdan seçin."))
    text = clean_note(note)
    if value == RemovalReason.OTHER and not text:
        raise RemovalReasonError("note_required", pgettext(_CTX, "«Digər» seçiləndə qeyd yazılmalıdır."))
    return {"reason": value, "note": text}


def clean_payload(data) -> dict:
    """HTTP gövdəsindən (JSON və ya form) :func:`clean`."""
    return clean(data.get(REASON_FIELD), data.get(NOTE_FIELD))


def _actor_name(actor) -> str:
    if actor is None or not getattr(actor, "pk", None):
        return pgettext(_CTX, "Sistem")
    return ((actor.get_full_name() or "").strip() or actor.get_username())[:200]


def _history(*, enrollment, offering, actor, kind, reason, note, action, request=None):
    """Jurnalın «Dəyişiklik tarixçəsi» sətri — kodlar saxlanılır, göstərmədə aktiv dilə çevrilir."""
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=actor,
        kind=kind,
        changes=[
            {
                "student": grade_audit.student_label(enrollment),
                "item": action,
                "old": "",
                "new": reason,
                "note": note,
            }
        ],
        fail_closed=True,
        request=request,
        reason=reason,
    )


def record(*, enrollment, action, cleaned, actor=None, hygiene_decision_id=None, request=None) -> JournalRemoval:
    """Çıxarılma səbəbi sətri + jurnal tarixçəsi — ÇAĞIRANIN tranzaksiyasında (əməlin özü artıq yazılıb)."""
    removal = JournalRemoval(
        organization_id=enrollment.organization_id,
        enrollment=enrollment,
        action=RemovalAction(action).value,
        reason=cleaned["reason"],
        note=cleaned.get("note") or "",
        hygiene_decision_id=hygiene_decision_id,
        actor=actor if getattr(actor, "pk", None) else None,
        actor_name=_actor_name(actor),
    )
    removal.full_clean(exclude=["enrollment", "organization", "hygiene_decision", "actor"])
    removal.save()
    _history(
        enrollment=enrollment,
        offering=enrollment.offering,
        actor=actor,
        kind=HISTORY_KIND,
        reason=removal.reason,
        note=removal.note,
        action=removal.action,
        request=request,
    )
    return removal


def record_restore(*, enrollment, actor=None, note="", request=None):
    """«Bərpa et» — jurnal tarixçəsində çıxarılmanın geri alınması da görünsün."""
    _history(
        enrollment=enrollment,
        offering=enrollment.offering,
        actor=actor,
        kind=HISTORY_RESTORE_KIND,
        reason="",
        note=clean_note(note),
        action=RemovalAction.SUBJECT_EXEMPT.value,
        request=request,
    )


def latest_by_decision(decision_ids) -> dict:
    """``{hygiene_decision_id: JournalRemoval}`` — «Azad edilənlər» siyahısının səbəb nişanı (TƏK sorğu)."""
    ids = [pk for pk in decision_ids if pk]
    if not ids:
        return {}
    rows = JournalRemoval.objects.filter(hygiene_decision_id__in=ids).order_by("hygiene_decision_id", "-created_at")
    found: dict = {}
    for row in rows:
        found.setdefault(row.hygiene_decision_id, row)
    return found


__all__ = [
    "HISTORY_KIND",
    "HISTORY_RESTORE_KIND",
    "NOTE_FIELD",
    "REASON_FIELD",
    "RemovalReasonError",
    "action_label",
    "clean",
    "clean_note",
    "clean_payload",
    "latest_by_decision",
    "reason_choices",
    "reason_label",
    "record",
    "record_restore",
]
