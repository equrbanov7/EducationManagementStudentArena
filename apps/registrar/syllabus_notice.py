"""Jurnal ↔ sillabus KÖRPÜSÜ — müəllimə vəziyyət banneri + «Sillabusa bax» keçidi.

Sahibin tələbi (2026-08): «dərs başlayanda müəllim sillabusu yazmayıbsa
xəbərdarlıq çıxsın; gözləmədədirsə göstərsin ki sillabusunuz gözləmədədir;
düzəliş istəyirsə düzəlişdə qeyd etsin — hamısı useri rahat hiss etdirmək
üçün, keçid linki ilə».

⚠️ Bu mərhələdə jurnal KİLİDLƏNMİR. Sillabusu olmayan müəllim bal yazmağa
davam edir — banner yalnız XƏBƏRDARLIQ və KEÇİDdir. Kilidləmə ayrıca qərardır
(sahib deməyib), ona görə burada `can_edit`-ə toxunan heç nə yoxdur.

İş bölgüsü:
  * VƏZİYYƏT KODU — :func:`apps.syllabus.services.offering_syllabus_state`
    (domen; mətn saxlamır);
  * MƏTN, TON və KEÇİD — bu modul (UI qatı), mövcud ``journal_close_notices``
    banner nümunəsinin eyni forması.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.syllabus import services as syllabus_services
from apps.syllabus.services.offerings import (
    STATE_APPROVED,
    STATE_ARCHIVED,
    STATE_DRAFT,
    STATE_MISSING,
    STATE_PENDING,
    STATE_REJECTED,
    STATE_REVISION,
)

_CTX = "registrar.syllabus"

#: Vəziyyət → (ton, başlıq, izah). Ton adı CSS-də `--ems-*` tokenlərinə bağlanır
#: (dizayn təhvili §1: şablonda hardcode rəng yoxdur).
_NOTICE = {
    STATE_MISSING: (
        "danger",
        pgettext_lazy(_CTX, "Bu fənn üzrə sillabus yazılmayıb"),
        pgettext_lazy(
            _CTX,
            "Dərslər başlayıb, amma fənnin sillabusu hələ yaradılmayıb. Əvvəlcə sillabusunuzu yazıb kafedra "
            "müdirinin təsdiqinə göndərin — tələbələr yalnız təsdiqlənmiş sillabusu görür.",
        ),
    ),
    STATE_DRAFT: (
        "warning",
        pgettext_lazy(_CTX, "Sillabus hələ qaralamadır"),
        pgettext_lazy(
            _CTX,
            "Sillabus yaradılıb, amma təsdiqə göndərilməyib. Qaralama tələbələrə görünmür — bölmələri tamamlayıb "
            "kafedra müdirinin təsdiqinə göndərin.",
        ),
    ),
    STATE_PENDING: (
        "info",
        pgettext_lazy(_CTX, "Sillabusunuz kafedra müdirinin baxışındadır"),
        pgettext_lazy(
            _CTX,
            "Versiya təsdiq növbəsinə göndərilib və baxış müddətində kilidlidir. Cavab gələnə qədər əməl tələb "
            "olunmur.",
        ),
    ),
    STATE_REVISION: (
        "warning",
        pgettext_lazy(_CTX, "Sillabus üzrə düzəliş tələb olunur"),
        pgettext_lazy(
            _CTX,
            "Kafedra müdiri versiyanı düzəliş üçün geri qaytarıb. Qeydləri nəzərə alıb yenidən təsdiqə göndərin.",
        ),
    ),
    STATE_REJECTED: (
        "danger",
        pgettext_lazy(_CTX, "Sillabus versiyası rədd edilib"),
        pgettext_lazy(_CTX, "Kafedra müdiri versiyanı rədd edib. Səbəbi oxuyub yeni versiya yaradın."),
    ),
    STATE_ARCHIVED: (
        "warning",
        pgettext_lazy(_CTX, "Bu fənnin qüvvədə olan sillabusu yoxdur"),
        pgettext_lazy(
            _CTX, "Yalnız arxiv nüsxəsi qalıb — cari semestr üçün yeni versiya yaradıb təsdiqə göndərin."
        ),
    ),
}

#: Bannerin əməl düyməsinin mətni — vəziyyətə görə.
_ACTION_LABEL = {
    STATE_MISSING: pgettext_lazy(_CTX, "Sillabus yarat"),
    STATE_DRAFT: pgettext_lazy(_CTX, "Qaralamanı tamamla"),
    STATE_PENDING: pgettext_lazy(_CTX, "Sillabusa bax"),
    STATE_REVISION: pgettext_lazy(_CTX, "Qeydlərə bax və düzəlt"),
    STATE_REJECTED: pgettext_lazy(_CTX, "Səbəbi oxu"),
    STATE_ARCHIVED: pgettext_lazy(_CTX, "Yeni versiya yarat"),
}

#: «Səbəb» sətrinin etiketi (düzəliş/rədd bannerində).
REASON_LABEL = pgettext_lazy(_CTX, "Kafedra müdirinin qeydi")


def _profile_link(section: str, **params) -> str:
    """Profil shell-i içindəki bölməyə keçid — sol sidebar QALIR (ayrı səhifə yox)."""
    query = "".join(f"&{key}={value}" for key, value in params.items() if value)
    return f"{reverse('accounts:profile')}?section={section}{query}"


def journal_syllabus_notice(offering) -> dict:
    """Jurnal başlığındakı vəziyyət zolağı üçün kontekst.

    HƏMİŞƏ dict qaytarır (``None`` yox): təsdiqlənmiş halda da şablon
    «Sillabusa bax» keçidini bu dict-dən oxuyur, sadəcə ``show_banner`` False
    olur — dizayn tələbi «APPROVED → banner yox, yalnız keçid».
    """
    syllabus = syllabus_services.syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )
    state = syllabus_services.offering_syllabus_state(syllabus)
    key = state["state"]
    tone, title, message = _NOTICE.get(key, (None, None, None))

    if key == STATE_MISSING:
        # Dosye yoxdur — siyahı ekranı açılır (yaratma düyməsi oradadır).
        link = _profile_link("syllabus-list")
    else:
        link = _profile_link("syllabus-editor", syllabus=syllabus.pk)

    version = state["version"]
    return {
        "state": key,
        "tone": tone,
        "title": title,
        "message": message,
        "reason": state["reason"],
        "reason_label": REASON_LABEL,
        "action_label": _ACTION_LABEL.get(key),
        "action_url": link,
        "show_banner": key != STATE_APPROVED,
        # «Sillabusa bax» yalnız oxunacaq məzmun VARSA göstərilir.
        "can_open": state["syllabus"] is not None and version is not None,
        "syllabus_id": str(syllabus.pk) if syllabus is not None else "",
        "version_label": version.label if version is not None else "",
        "status_label": (
            str(version.get_status_display()) if version is not None and hasattr(version, "get_status_display") else ""
        ),
        "has_approved": state["has_approved"],
    }


__all__ = ["REASON_LABEL", "journal_syllabus_notice"]
