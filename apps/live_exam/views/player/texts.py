"""live_exam player paketi — istifadəçiyə görünən mətnlər (gettext + pgettext kontekstləri).

2026-10-08: əvvəl PIN girişi, «əvvəlki qoşulma» bildirişi və «ad məşğuldur» mətnləri dil lüğətlərində
(``{"az": …, "en": …}``) sərt kodlanmışdı, sürət-həddi mesajı isə HƏR dildə Azərbaycanca idi — qoşulma
və oyun səhifələrində Azərbaycan və ingilis dili qarışırdı. İndi hamısı kataloqdan gəlir (aktiv dil:
LocaleMiddleware və ya aparıcının sessiya dili — ``apps.live_exam.i18n``); tərcümələr:
``scripts/i18n_fill_2026_10_08_live_exam_ux.py``.
"""

from __future__ import annotations

from django.utils.translation import pgettext

PIN_CTX = "live_exam.pin_entry"
JOIN_CTX = "live_exam.join"


def pin_entry_copy() -> dict[str, str]:
    return {
        "title": pgettext(PIN_CTX, "Canlı imtahana qoşul"),
        "eyebrow": pgettext(PIN_CTX, "Canlı"),
        "subtitle": pgettext(PIN_CTX, "Müəllimin göstərdiyi PIN-i yaz, sonra adını seçib oyuna daxil ol."),
        "pin_label": pgettext(PIN_CTX, "Oyun PIN-i"),
        "pin_placeholder": pgettext(PIN_CTX, "Məsələn: 3A8K2B94F1"),
        "button": pgettext(PIN_CTX, "Davam et"),
        "hint": pgettext(PIN_CTX, "PIN-i ekranda gördüyün kimi daxil et. Növbəti addımda ad və avatar seçəcəksən."),
        "feature_fast": pgettext(PIN_CTX, "Saniyələr içində qoşul"),
        "feature_device": pgettext(PIN_CTX, "Telefon, planşet və kompüterdən işləyir"),
        "feature_live": pgettext(PIN_CTX, "Canlı nəticə və liderlik cədvəli"),
        "card_title": pgettext(PIN_CTX, "Hazırsan?"),
        "card_subtitle": pgettext(PIN_CTX, "Bir URL, bir PIN, hamısı eyni oyunda."),
        "footer_left": pgettext(PIN_CTX, "Müəllim ekranında PIN və QR kod görünür."),
        "footer_right": pgettext(PIN_CTX, "Daxil olduqdan sonra avatar və ad seçimi gəlir."),
        "loading": pgettext(PIN_CTX, "Yoxlanılır..."),
        "invalid_pin": pgettext(PIN_CTX, "Düzgün PIN daxil et."),
        "session_not_found": pgettext(PIN_CTX, "Bu PIN tapılmadı və ya oyun bağlanıb."),
    }


def join_resume_copy(nickname: str) -> dict[str, str]:
    """«Əvvəlki qoşulma tapıldı» bildirişi və modalı (``{nickname}`` artıq yerinə qoyulub)."""
    copy = {
        "notice_title": pgettext(JOIN_CTX, "Əvvəlki qoşulma tapıldı"),
        "notice_body": pgettext(JOIN_CTX, "{nickname} adı ilə bu oyuna artıq daxil olmusan."),
        "notice_hint": pgettext(
            JOIN_CTX, "İstəsən həmin oyunçu ilə davam et, istəsən yeni ad və avatarla yenidən qoşul."
        ),
        "continue_button": pgettext(JOIN_CTX, "{nickname} kimi davam et"),
        "modal_title": pgettext(JOIN_CTX, "Əvvəlki adla davam etmək istəyirsən?"),
        "modal_body": pgettext(
            JOIN_CTX,
            "Bu PIN üçün aktiv oyunçu profilin var. Həmin profil ilə gözləmə otağına qayıda və ya yeni "
            "ad/avatar seçib yenidən daxil ola bilərsən.",
        ),
        "restart_button": pgettext(JOIN_CTX, "Yenidən daxil ol"),
        "close_button": pgettext(JOIN_CTX, "Bağla"),
    }
    return {key: value.format(nickname=nickname) for key, value in copy.items()}


def nickname_conflict_message() -> str:
    return pgettext(JOIN_CTX, "Bu ad artıq istifadə olunur. Başqa ad seç.")


def rate_limit_message() -> str:
    return pgettext("live_exam.view.message", "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin.")


def state_rate_limit_message() -> str:
    return pgettext(
        "live_exam.view.message", "Çox sayda sorğu göndərildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."
    )
