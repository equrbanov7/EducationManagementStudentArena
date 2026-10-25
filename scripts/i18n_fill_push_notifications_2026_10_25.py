#!/usr/bin/env python3
"""EMSArena i18n — telefona push bildirişləri + q/b bildirişinin tarixi (sahib 2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "registrar.notify": {
        "Qayıb (q/b) qeyd edildi: %(date)s": t(
            "Absence (q/b) recorded: %(date)s",
            "Пропуск (q/b) отмечен: %(date)s",
            "Devamsızlık (q/b) kaydedildi: %(date)s",
            "Fehlzeit (q/b) erfasst: %(date)s",
        ),
    },
    "core.runtime_settings": {
        "Bildirişlər": t("Notifications", "Уведомления", "Bildirimler", "Benachrichtigungen"),
        "Push bildirişləri aktivdir (telefona göndər)": t(
            "Push notifications enabled (send to phone)",
            "Push-уведомления включены (отправлять на телефон)",
            "Anlık bildirimler etkin (telefona gönder)",
            "Push-Benachrichtigungen aktiv (an das Telefon senden)",
        ),
        "Yandırılanda yeni bildiriş (q/b, bal, imtahan, elan və s.) mobil tətbiqi quraşdırıb hesabına daxil olmuş "
        "istifadəçinin telefonunda bildiriş kimi görünür. Söndürüləndə bildirişlər yalnız kabinetdə qalır. "
        "Firebase açarı serverdə qoşulmayıbsa bu açar heç nəyi dəyişmir.": t(
            "When enabled, every new notification (absence, score, exam, announcement, etc.) also appears as a "
            "notification on the phone of a user who installed the mobile app and signed in. When disabled, "
            "notifications stay in the cabinet only. If the Firebase key is not configured on the server, this "
            "switch has no effect.",
            "Если включено, каждое новое уведомление (пропуск, балл, экзамен, объявление и т. д.) появляется и на "
            "телефоне пользователя, который установил мобильное приложение и вошёл в аккаунт. Если выключено, "
            "уведомления остаются только в кабинете. Если ключ Firebase на сервере не подключён, переключатель "
            "ни на что не влияет.",
            "Açıkken her yeni bildirim (devamsızlık, puan, sınav, duyuru vb.) mobil uygulamayı kurup hesabına "
            "giriş yapmış kullanıcının telefonunda da bildirim olarak görünür. Kapalıyken bildirimler yalnızca "
            "kabinette kalır. Sunucuda Firebase anahtarı bağlı değilse bu anahtar hiçbir şeyi değiştirmez.",
            "Wenn aktiviert, erscheint jede neue Benachrichtigung (Fehlzeit, Punkte, Prüfung, Ankündigung usw.) "
            "auch als Mitteilung auf dem Telefon von Nutzern, die die mobile App installiert und sich angemeldet "
            "haben. Wenn deaktiviert, bleiben Benachrichtigungen nur im Kabinett. Ist der Firebase-Schlüssel auf "
            "dem Server nicht eingerichtet, hat dieser Schalter keine Wirkung.",
        ),
    },
    "notifications.push": {
        "Test bildirişi": t("Test notification", "Тестовое уведомление", "Test bildirimi", "Testbenachrichtigung"),
        "Push bildirişləri bu cihazda işləyir.": t(
            "Push notifications work on this device.",
            "Push-уведомления на этом устройстве работают.",
            "Anlık bildirimler bu cihazda çalışıyor.",
            "Push-Benachrichtigungen funktionieren auf diesem Gerät.",
        ),
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
