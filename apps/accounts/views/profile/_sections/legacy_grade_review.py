"""Profil «legacy-grade-review» bölməsi — köçürülmüş nəticələrin dəqiqləşdirilməsi.

Bölmə SPA panelidir (``teaching-handover`` naxışı): server yalnız ÇƏRÇİVƏNİ verir
— icazə bayraqları, endpoint URL-ləri və sabitlər. Cədvəl, seçicilər, sayğaclar
və irəliləyiş JSON-la gəlir, ona görə burada AĞIR SORĞU YOXDUR. Bu vacibdir:
növbə 170 min sətirlik sübut qatının üstündə oturur; onu profil kontekstində
hesablasaydıq bölməyə heç girməyən istifadəçi də bədəlini ödəyərdi.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (UI buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``legacy_grade_review_section`` (dict):

    has_access             bool  — bölmə açılırmı (qərar VƏ YA oxu səlahiyyəti)
    can_review             bool  — qərar/düzəliş yaza bilirmi (`final_score.entry`)
    access_denied_message  str
    observer_notice        str   — yalnız oxu rejimində göstərilən qeyd
    queue_url              str   — GET cədvəl + irəliləyiş + kateqoriya sayları
    options_url            str   — GET dövr/status/şiddət açılışları
    faculty_url            str   — GET fakültə seçicisi (kaskadın 1-ci pilləsi)
    kafedra_url/…          str   — kaskadın qalan pillələri
    action_url             str   — POST təsdiq/mübahisə/düzəliş
    reasons                list  — düzəliş səbəbləri (`CorrectionReason`)
    default_page_size      int
    min_note_length        int
    max_note_length        int
"""

from django.urls import reverse
from django.utils.translation import pgettext

SECTION = "legacy-grade-review"

# Tərcümə konteksti hər çağırışda HƏRFİ sətirdir, dəyişən DEYİL: ``xgettext``
# ``pgettext``-in kontekst arqumentini yalnız hərfi sətir olanda oxuya bilir —
# dəyişən verilsə sətri SƏSSİZCƏ atır və mətn heç bir dilə çıxmır.


def build_legacy_grade_review_section(request, section, *, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir (journal-close/handover naxışı)."""
    if SECTION not in allowed_sections or active_section != SECTION:
        return

    from apps.registrar import legacy_grade_review_actions as review_write
    from apps.registrar.models import CorrectionReason

    from ...legacy_review.api import DEFAULT_PAGE_SIZE
    from ...legacy_review.policy import resolve_actor

    actor = resolve_actor(request)
    section["has_access"] = actor.has_access
    section["can_review"] = actor.can_review
    section["access_denied_message"] = pgettext(
        "accounts.legacy_review",
        "Bu bölmə köhnə sistemdən köçürülmüş imtahan nəticələrini dəqiqləşdirən " "səlahiyyətli şəxslər üçündür.",
    )
    section["observer_notice"] = pgettext(
        "accounts.legacy_review",
        "Siz növbəni oxu rejimində görürsünüz: təsdiq və düzəliş səlahiyyəti "
        "İmtahan Mərkəzinin bal daxiletmə açarına bağlıdır.",
    )
    section["queue_url"] = reverse("accounts:legacy_review_queue")
    section["options_url"] = reverse("accounts:legacy_review_options")
    section["faculty_url"] = reverse("accounts:legacy_review_units", kwargs={"kind": "faculty"})
    section["kafedra_url"] = reverse("accounts:legacy_review_units", kwargs={"kind": "kafedra"})
    section["specialty_url"] = reverse("accounts:legacy_review_units", kwargs={"kind": "specialty"})
    section["group_url"] = reverse("accounts:legacy_review_groups")
    section["subject_url"] = reverse("accounts:legacy_review_subjects")
    section["teacher_url"] = reverse("accounts:legacy_review_teachers")
    section["action_url"] = reverse("accounts:legacy_review_action")
    section["default_page_size"] = DEFAULT_PAGE_SIZE
    section["min_note_length"] = review_write.MIN_NOTE_LENGTH
    section["max_note_length"] = review_write.MAX_NOTE_LENGTH
    section["reasons"] = [{"value": value, "label": str(label)} for value, label in CorrectionReason.choices]


__all__ = ["SECTION", "build_legacy_grade_review_section"]
