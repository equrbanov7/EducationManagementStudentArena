#!/usr/bin/env python3
"""i18n — canlı oyunun təqdimat üslubu «Rəsmi» / «Qeyri-rəsmi» (sahib 2026-10-19).

Yeni mətnlər: sessiya yaratma təsdiqindəki üslub seçimi, aparıcının idarə paneli və tənzimləmə
çekməcəsi, server xətaları (yararsız dəyər / oyun başlayandan sonra dəyişiklik), model seçimləri,
rəsmi üslubun səhnə / telefon mətnləri (JSON i18n bloklarından — ``_host_i18n.html``,
``player_screen.html``; canlı oyunun JS mətnləri ``django`` kataloqundan gəlir), qoşulma səhifəsi.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. ⚠️ `makemessages` İŞLƏDİLMİR.
İstifadə:  python scripts/i18n_fill_live_style_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

STYLE = "live_exam.presentation_style"
SETTINGS = "live_exam.host_settings"
MODEL = "live_exam.model.session.presentation_style"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


FORMAL = t("Formal", "Официальный", "Resmî", "Formell")
INFORMAL = t("Informal", "Неофициальный", "Gayriresmî", "Locker")

ENTRIES = {
    STYLE: {
        "Görünüş üslubu": t("Presentation style", "Стиль оформления", "Sunum stili", "Darstellungsstil"),
        "Rəsmi": FORMAL,
        "Qeyri-rəsmi": INFORMAL,
        "A/B/C/D variantları, sakit ikonlar, baş hərflər və sıralama cədvəli. Konfetti, səs effektləri və emoji yoxdur.": t(
            "A/B/C/D options, calm icons, initials and a ranking table. No confetti, sound effects or emoji.",
            "Варианты A/B/C/D, спокойные значки, инициалы и рейтинговая таблица. Без конфетти, звуковых эффектов "
            "и эмодзи.",
            "A/B/C/D seçenekleri, sade simgeler, baş harfler ve sıralama tablosu. Konfeti, ses efekti ve emoji yok.",
            "Antworten A/B/C/D, ruhige Symbole, Initialen und eine Ranglistentabelle. Kein Konfetti, keine "
            "Soundeffekte, keine Emojis.",
        ),
        "Rəngli fiqurlar, avatarlar, reaksiyalar, musiqi və final səhnəsində konfetti.": t(
            "Colourful shapes, avatars, reactions, music and confetti on the final stage.",
            "Цветные фигуры, аватары, реакции, музыка и конфетти в финальной сцене.",
            "Renkli şekiller, avatarlar, tepkiler, müzik ve final sahnesinde konfeti.",
            "Bunte Formen, Avatare, Reaktionen, Musik und Konfetti auf der Finalbühne.",
        ),
        "«Rəsmi»: A/B/C/D variantları, sakit ikonlar, baş hərflər, sıralama cədvəli — konfetti, səs effekti və emoji "
        "olmadan. «Qeyri-rəsmi»: fiqurlar, avatarlar, musiqi və final şousu. Yalnız oyun başlamazdan əvvəl dəyişir.": t(
            "«Formal»: A/B/C/D options, calm icons, initials, a ranking table — without confetti, sound effects or "
            "emoji. «Informal»: shapes, avatars, music and the final show. Can only be changed before the game starts.",
            "«Официальный»: варианты A/B/C/D, спокойные значки, инициалы, рейтинговая таблица — без конфетти, "
            "звуковых эффектов и эмодзи. «Неофициальный»: фигуры, аватары, музыка и финальное шоу. Меняется только "
            "до начала игры.",
            "«Resmî»: A/B/C/D seçenekleri, sade simgeler, baş harfler, sıralama tablosu — konfeti, ses efekti ve emoji "
            "olmadan. «Gayriresmî»: şekiller, avatarlar, müzik ve final şovu. Yalnızca oyun başlamadan önce "
            "değiştirilebilir.",
            "«Formell»: Antworten A/B/C/D, ruhige Symbole, Initialen, Ranglistentabelle — ohne Konfetti, Soundeffekte "
            "und Emojis. «Locker»: Formen, Avatare, Musik und Finalshow. Nur vor Spielbeginn änderbar.",
        ),
        "Variant {letter}": t("Option {letter}", "Вариант {letter}", "Seçenek {letter}", "Antwort {letter}"),
        "Yekun nəticələr hazırlanır": t(
            "Preparing the final results",
            "Готовятся итоговые результаты",
            "Nihai sonuçlar hazırlanıyor",
            "Endergebnisse werden vorbereitet",
        ),
        "Yekun nəticələr": t("Final results", "Итоговые результаты", "Nihai sonuçlar", "Endergebnisse"),
        "Yer": t("Rank", "Место", "Sıra", "Platz"),
        "İştirakçı": t("Participant", "Участник", "Katılımcı", "Teilnehmer/in"),
        "Düzgün cavablar": t("Correct answers", "Правильные ответы", "Doğru cevaplar", "Richtige Antworten"),
        "Xal": t("Points", "Баллы", "Puan", "Punkte"),
        "Oyun başa çatdı": t("The game has ended", "Игра окончена", "Oyun sona erdi", "Das Spiel ist beendet"),
        "Adınızı və soyadınızı yazın — oyun müəllim başladanda açılacaq.": t(
            "Enter your first and last name — the game opens when the teacher starts it.",
            "Введите имя и фамилию — игра откроется, когда преподаватель её начнёт.",
            "Adınızı ve soyadınızı yazın — oyun öğretmen başlattığında açılacak.",
            "Geben Sie Vor- und Nachnamen ein — das Spiel öffnet sich, sobald die Lehrkraft es startet.",
        ),
        "Ad və soyad": t("First and last name", "Имя и фамилия", "Ad ve soyad", "Vor- und Nachname"),
    },
    SETTINGS: {
        "Görünüş üslubu yalnız «Rəsmi» və ya «Qeyri-rəsmi» ola bilər.": t(
            "The presentation style can only be «Formal» or «Informal».",
            "Стиль оформления может быть только «Официальный» или «Неофициальный».",
            "Sunum stili yalnızca «Resmî» veya «Gayriresmî» olabilir.",
            "Der Darstellungsstil kann nur «Formell» oder «Locker» sein.",
        ),
        "Görünüş üslubu yalnız oyun başlamazdan əvvəl dəyişdirilə bilər.": t(
            "The presentation style can only be changed before the game starts.",
            "Стиль оформления можно изменить только до начала игры.",
            "Sunum stili yalnızca oyun başlamadan önce değiştirilebilir.",
            "Der Darstellungsstil kann nur vor Spielbeginn geändert werden.",
        ),
    },
    MODEL: {
        "Rəsmi": FORMAL,
        "Qeyri-rəsmi": INFORMAL,
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
