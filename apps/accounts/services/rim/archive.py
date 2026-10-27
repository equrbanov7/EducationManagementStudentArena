"""RİM — «Arxivdən çıxar» kartı (sahib 2026-10-27: «Mən özüm də arxivdən çıxara bilim»).

Arxiv statuslu hesabın detal kartında (və «Parol sıfırlama» nəticəsində) göstərilən blok: hesab SƏHVƏN
arxivdədirmi (tələbə hələ oxuyur) və bu operator onu arxivdən çıxara bilərmi. Qayda və keçid
``services/archive_restore.py``-dədir — burada yalnız görünüş məlumatı qurulur (düymə UI rahatlığıdır,
faktiki qapı endpoint + servisdədir).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from ..archive_restore import (
    MAX_ADMISSION_YEAR,
    MIN_ADMISSION_YEAR,
    SENTINEL_ADMISSION_YEAR,
    actor_can_restore,
    error_message,
    restore_eligibility,
)
from .policy import RimActor

_CTX = "accounts.archive_restore"


def restore_organization(actor: RimActor, user):
    """Əməliyyatın təşkilatı — aktorun aktiv təşkilatı; təşkilatsız superadmin üçün hədəfin öz təşkilatı."""
    if actor.organization is not None:
        return actor.organization
    if actor.is_superadmin:
        return getattr(getattr(user, "profile", None), "organization", None)
    return None


def archive_restore_card(user, actor: RimActor) -> dict:
    """Arxiv hesab üçün «Arxivdən çıxar» bloku: uyğunluq, səbəb mətni, qəbul ili sahəsi lazımdırmı."""
    organization = restore_organization(actor, user)
    eligibility = restore_eligibility(user, organization)
    allowed = eligibility.eligible and actor_can_restore(actor.user, organization)
    if eligibility.eligible:
        note = pgettext(
            _CTX,
            "Tələbə hələ oxuyur (aktiv akademik qeyd, qrup: %(group)s), amma hesab arxivdədir — giriş və parol "
            "bərpası bağlıdır. Səhv arxivdirsə «Arxivdən çıxar».",
        ) % {"group": eligibility.group_name or "—"}
        if not allowed:
            note = f"{note} " + pgettext(
                _CTX, "Bunun üçün «member.edit» icazəsi lazımdır — RİM rəhbərinə müraciət edin."
            )
    else:
        note = error_message(eligibility.code)
    return {
        "eligible": eligibility.eligible,
        "can_restore": allowed,
        "code": eligibility.code,
        "note": note,
        "needs_admission_year": eligibility.eligible and eligibility.needs_admission_year,
        "sentinel_year": SENTINEL_ADMISSION_YEAR,
        "min_year": MIN_ADMISSION_YEAR,
        "max_year": MAX_ADMISSION_YEAR,
        "url": reverse("accounts:rim_archive_restore"),
    }


def archive_restore_dialog_context(actor: RimActor) -> dict | None:
    """Panelə «Arxivdən çıxar» dialoqu lazımdırmı (``member.edit`` / superadmin) — və onun çərçivəsi."""
    if actor.user is None or not (actor.is_superadmin or actor_can_restore(actor.user, actor.organization)):
        return None
    return {
        "url": reverse("accounts:rim_archive_restore"),
        # `_reason_dialog.html`-in forma atributu — JS formanı məhz bununla tanıyır (ad serverdən).
        "form_data": {"data-archive-restore-form": "1"},
        "min_year": MIN_ADMISSION_YEAR,
        "max_year": MAX_ADMISSION_YEAR,
    }


__all__ = ["archive_restore_card", "archive_restore_dialog_context", "restore_organization"]
