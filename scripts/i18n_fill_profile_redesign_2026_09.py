#!/usr/bin/env python3
"""EMSArena i18n — «Bildirişlər» + «Profil məlumatları» + açıq profil yenidən
dizaynının sətirləri (4 dil). İdempotent.

2026-09-07 redizaynı üç ekranı yenilədi; yeni mətnlər bunlardır:

* bildiriş axınının ZAMAN QRUPLARI («Bu gün / Dünən / …») — bunlar
  ``_sections/notifications_ui.py``-dan ``pgettext(_CTX, …)`` ilə gəlir və
  mənbə skaneri dəyişən konteksti oxuya bilmədiyi üçün qapı onları GÖRMÜR;
  tərcüməsiz qalmasınlar deyə burada AÇIQ əlavə olunurlar;
* seçim sayğacı, açıq profilin hero faktları və təşkilat kartının linkləri.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir. Yer tutucular (`%(joined)s`, `{n}`, …) tərcümədə də EYNİ qalmalıdır
(`scripts/check_i18n_catalogs.py` bunu yoxlayır).

İstifadə:  python scripts/i18n_fill_profile_redesign_2026_09.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ── Kontekstsiz (şablon `{% trans %}` / `{% blocktrans %}`) ─────────────────
_PLAIN = {
    "%(joined)s-dan bəri": {
        "en": "Member since %(joined)s",
        "ru": "С %(joined)s",
        "tr": "%(joined)s tarihinden beri",
    },
    "%(org_type)s · %(count)s üzv": {
        "en": "%(org_type)s · %(count)s members",
        "ru": "%(org_type)s · участников: %(count)s",
        "tr": "%(org_type)s · %(count)s üye",
    },
    "%(count)s qrup": {
        "en": "%(count)s groups",
        "ru": "групп: %(count)s",
        "tr": "%(count)s grup",
    },
    "Kateqoriyalar": {"en": "Categories", "ru": "Категории", "tr": "Kategoriler"},
    "Panel": {"en": "Dashboard", "ru": "Панель", "tr": "Kontrol paneli"},
    "Rollar": {"en": "Roles", "ru": "Роли", "tr": "Roller"},
}

# ── Açıq profil hero sayğacları ─────────────────────────────────────────────
_PUBLIC = {
    "açıq paylaşım": {"en": "public posts", "ru": "открытых публикаций", "tr": "açık paylaşım"},
    "kateqoriya": {"en": "categories", "ru": "категорий", "tr": "kategori"},
}

# ── Bildiriş inbox-u: zaman qrupları + seçim sayğacı ────────────────────────
_NOTIF = {
    "{n} seçilib": {"en": "{n} selected", "ru": "выбрано: {n}", "tr": "{n} seçildi"},
    "Bu gün": {"en": "Today", "ru": "Сегодня", "tr": "Bugün"},
    "Dünən": {"en": "Yesterday", "ru": "Вчера", "tr": "Dün"},
    "Bu həftə": {"en": "This week", "ru": "На этой неделе", "tr": "Bu hafta"},
    "Daha əvvəl": {"en": "Earlier", "ru": "Ранее", "tr": "Daha önce"},
    "indicə": {"en": "just now", "ru": "только что", "tr": "az önce"},
}

# ── «Universitet strukturu»: rəhbər seçicisi native `<select>`-dən axtarışlı
#    komponentə keçdi (native popup dialoqdan daşıb onu bağlayırdı).
_STRUCTURE = {
    "Ad və ya istifadəçi adı üzrə axtar": {
        "en": "Search by name or username",
        "ru": "Поиск по имени или логину",
        "tr": "Ad veya kullanıcı adına göre ara",
    },
    "Seçimi boş buraxsanız bölmənin rəhbəri götürülür.": {
        "en": "Leave the selection empty to remove the unit's head.",
        "ru": "Оставьте выбор пустым, чтобы снять руководителя подразделения.",
        "tr": "Seçimi boş bırakırsanız birimin yöneticisi kaldırılır.",
    },
    "Uyğun namizəd tapılmadı.": {
        "en": "No matching candidate found.",
        "ru": "Подходящий кандидат не найден.",
        "tr": "Uygun aday bulunamadı.",
    },
}

ENTRIES = {
    "": _PLAIN,
    "accounts.structure_tree": _STRUCTURE,
    "accounts.public_profile": _PUBLIC,
    "profile.notifications": _NOTIF,
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            # Kontekstsiz giriş `msgctxt` sətri OLMADAN yazılır. Prob SƏRTDİR:
            # eyni msgid BAŞQA kontekstdə mövcud ola bilər (məs. «Rollar»
            # `profile.rim` kontekstində var) — sadə alt-sətir axtarışı onu
            # səhvən «var» sayıb kontekstsiz girişi əlavə etmirdi.
            if ctx:
                exists = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text
            else:
                # Kontekstsiz giriş BLOK səviyyəsində axtarılır: eyni msgid
                # başqa kontekstdə ola bilər (məs. «Rollar» → `profile.rim`),
                # sadə alt-sətir axtarışı onu səhvən «var» sayırdı.
                exists = any(
                    block.lstrip("#\n").startswith(f'msgid "{esc(msgid)}"\n')
                    for block in text.split("\n\n")
                )
            if exists:
                continue
            header = "" if not ctx else f'msgctxt "{esc(ctx)}"\n'
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{header}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
