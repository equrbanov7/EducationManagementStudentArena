"""İmtahan balı dəyişikliyinin TƏQDİMATI (səbəb + qeyd + sənəd) və superadmin istisnası.

``exam_score_entry`` 600 sətir limitindədir — təqdimat qaydası buraya köçürülüb (davranış eynidir).

Sahib 2026-10-27: superadmin miqrasiyadan sonra balı sənədsiz düzəldə bilməlidir. Sənəd (sətrin faylı və ya
vərəqin skanı) yoxdursa və aktor superadmindirsə:

* təqdimat / apellyasiya sənədi tələbi keçilir (``waived``);
* yazılan sətrə (``ExamScoreEntry``) səbəb «Digər» (apellyasiyada «Apellyasiya») və qeyd
  «Superadmin düzəlişi — sənədsiz (ad, tarix)» düşür — tarixçədə görünür (:func:`fill`).

Qeyri-superadmin üçün qayda dəyişmir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from core import superadmin_waiver

from .models import CorrectionReason, ExamScoreEntryKind

_CTX = "registrar.exam_score_entry"

#: Sənədli dəyişiklik növləri — superadmin sənədsiz yazanda qeyd bunlara düşür.
_DOCUMENTED_KINDS = (ExamScoreEntryKind.CORRECTION, ExamScoreEntryKind.APPEAL)


def waived(by_user, *, evidence=None, sheet=None) -> bool:
    """Superadmindir və nə sətirdə, nə vərəqdə sənəd yoxdur."""
    has_document = bool(evidence) or bool(sheet is not None and sheet.evidence)
    return not has_document and superadmin_waiver.waives(by_user)


def require_justification(*, reason, note, evidence, sheet=None, by_user=None):
    """Sonrakı dəyişiklik = TƏQDİMAT: səbəb + qeyd + sənəd (üçü də məcburi; superadmin sənədsiz keçir).

    2026-09-12: sənəd sətrin öz faylı VƏ YA partiyanın (vərəqin) skanı ola
    bilər — toplu köçürmədə bir protokol bütün dəyişiklikləri əsaslandırır,
    hər sətir üçün eyni faylı təkrar saxlamağa ehtiyac yoxdur.
    """
    if waived(by_user, evidence=evidence, sheet=sheet):
        return
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün səbəb seçilməlidir."))
    if not (note or "").strip():
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün izahat qeydi məcburidir."))
    if not evidence and not (sheet is not None and sheet.evidence):
        raise ValidationError(pgettext(_CTX, "Balı dəyişmək üçün təsdiqedici sənəd əlavə olunmalıdır."))


def fill(by_user, *, entry_kind, reason, note, evidence, sheet):
    """Superadmin sənədsiz düzəliş / apellyasiya yazırsa sətrin səbəbi + qeydi avtomatik dolur."""
    if entry_kind not in _DOCUMENTED_KINDS or not waived(by_user, evidence=evidence, sheet=sheet):
        return reason, note
    if reason not in CorrectionReason.values:
        reason = CorrectionReason.APPEAL if entry_kind == ExamScoreEntryKind.APPEAL else CorrectionReason.OTHER
    return reason, superadmin_waiver.stamp(note, by_user)


__all__ = ["fill", "require_justification", "waived"]
