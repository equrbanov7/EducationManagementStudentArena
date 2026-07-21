"""Jurnal redaktə/giriş hüquq köməkçiləri (paylaşılan — views + journal_actions).

İki fərqli səviyyə var:

* :func:`can_edit_journal` — GİRİŞ + korrektor səlahiyyəti. Müəllim / org sahibi /
  superuser / İKT Rəhbəri jurnalı aça bilər. İKT texniki super-operatordur.
* :func:`is_direct_editor` — BİRBAŞA (audit-siz) redaktə hüququ: YALNIZ müəllim,
  org sahibi, superuser. Korrektor (İKT) buraya DAXİL DEYİL — o, dəyişikliyi yalnız
  «Jurnal düzəlişi» rejimində sənədli (audited, PDF) yolla edir; normal görünüşdə
  hər şey read-only-dir. views.py + journal_actions.py hər ikisi buradan idxal edir
  (modul-ölçü limiti üçün ayrıca kiçik modul).
"""

from __future__ import annotations


def can_edit_journal(user, offering) -> bool:
    """Giriş + redaktə/korrektor səlahiyyəti: müəllim / sahib / superuser / İKT Rəhbəri."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_ikt_rehber", False):
        return True
    if offering.instructor_id and offering.instructor_id == user.id:
        return True
    return offering.organization.owner_id == user.id


def is_direct_editor(user, offering) -> bool:
    """Birbaşa (audit-siz) redaktə — YALNIZ müəllim / org sahibi / superuser.

    Korrektor (İKT Rəhbəri) buraya daxil deyil: jurnalı yalnız düzəliş rejimində
    sənədli dəyişir, normal görünüşdə read-only."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if offering.instructor_id and offering.instructor_id == user.id:
        return True
    return offering.organization.owner_id == user.id
