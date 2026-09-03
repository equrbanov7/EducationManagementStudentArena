"""Profil «teaching-handover» bölməsi — fənnin başqa müəllimə təhvili.

Bölmə SPA panelidir (``people`` naxışı): server yalnız ÇƏRÇİVƏNİ verir —
icazə bayraqları, endpoint URL-ləri və sabitlər; cədvəl, seçicilər və tarixçə
JSON-la gəlir. Ona görə burada AĞIR SORĞU YOXDUR.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (UI buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``handover_section`` (dict):

    has_access             bool  — bölmə ümumiyyətlə açılırmı (`journal.reassign`)
    access_denied_message  str
    scope_label            str   — «Bütün universitet» / «Öz bölmələriniz»
    teachers_url           str   — GET  müəllim seçicisi (?role=source|target&q=&page=)
    offerings_url          str   — GET  açılış cədvəli
    options_url            str   — GET  süzgəc açılışları
    history_url            str   — GET  təhvil tarixçəsi
    action_url             str   — POST təhvil / geri qaytarma
    default_page_size      int
    min_reason_length      int
    max_reason_length      int
    max_bulk_rows          int
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import handover as handover_read
from apps.registrar import handover_actions as handover_write

_CTX = "accounts.handover"


def build_handover_section(request, section, *, active_organization, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir (kollokvium/journal-close naxışı)."""
    if "teaching-handover" not in allowed_sections or active_section != "teaching-handover":
        return

    from ...handover.api import DEFAULT_PAGE_SIZE

    has_access = bool(active_organization is not None and handover_read.can_reassign(request.user, active_organization))
    section["has_access"] = has_access
    section["access_denied_message"] = pgettext(
        _CTX, "Fənn təhvili üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür."
    )
    section["teachers_url"] = reverse("accounts:handover_teachers")
    section["offerings_url"] = reverse("accounts:handover_offerings")
    section["options_url"] = reverse("accounts:handover_options")
    section["history_url"] = reverse("accounts:handover_history")
    section["action_url"] = reverse("accounts:handover_action")
    section["default_page_size"] = DEFAULT_PAGE_SIZE
    section["min_reason_length"] = handover_read.MIN_REASON_LENGTH
    section["max_reason_length"] = handover_read.MAX_REASON_LENGTH
    section["max_bulk_rows"] = handover_write.MAX_BULK_ROWS

    if not has_access:
        return

    scope = handover_read.actor_scope(request.user, active_organization)
    section["scope_label"] = (
        pgettext(_CTX, "Bütün universitet") if scope.is_org_wide else pgettext(_CTX, "Yalnız öz struktur bölmələriniz")
    )


__all__ = ["build_handover_section"]
