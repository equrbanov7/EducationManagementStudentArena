#!/usr/bin/env python3
"""Final gözləmə otağının JS mətnləri (djangojs, 4 dil).

`apps/exams/static/exams/js/final_center/waiting_room.js` TƏLƏBƏYƏ final imtahanı
gözləmə otağında göstərilən mesajları sabit azərbaycanca literal kimi saxlayırdı
— yəni EN/RU/TR tələbə imtahanın ən kritik anında (bağlantı kəsilməsi, imtahandan
çıxarılma, oturumun ləğvi) azərbaycanca mətn görürdü. Fayl `gettext()`-ə keçirildi;
bu skript msgid-ləri **djangojs** kataloquna əlavə edir.

İstifadə::

    python scripts/i18n_add_waiting_room_strings.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
DOMAIN = "djangojs"

ENTRIES: dict[str, dict[str, str]] = {
    "Bağlantı quruldu": {
        "az": "Bağlantı quruldu",
        "en": "Connected",
        "ru": "Соединение установлено",
        "tr": "Bağlantı kuruldu",
    },
    "Yenidən qoşulur…": {
        "az": "Yenidən qoşulur…",
        "en": "Reconnecting…",
        "ru": "Переподключение…",
        "tr": "Yeniden bağlanıyor…",
    },
    "Bağlantı yoxdur — fallback rejimi": {
        "az": "Bağlantı yoxdur — fallback rejimi",
        "en": "No connection — fallback mode",
        "ru": "Нет соединения — резервный режим",
        "tr": "Bağlantı yok — yedek mod",
    },
    "İmtahan başlayır — yönləndirilirsiniz…": {
        "az": "İmtahan başlayır — yönləndirilirsiniz…",
        "en": "The exam is starting — you are being redirected…",
        "ru": "Экзамен начинается — вас перенаправляют…",
        "tr": "Sınav başlıyor — yönlendiriliyorsunuz…",
    },
    "Oturum bitdi. Nəzarətçiyə müraciət edin.": {
        "az": "Oturum bitdi. Nəzarətçiyə müraciət edin.",
        "en": "The session has ended. Please contact the invigilator.",
        "ru": "Сессия завершена. Обратитесь к наблюдателю.",
        "tr": "Oturum sona erdi. Lütfen gözetmene başvurun.",
    },
    "İmtahandan çıxarıldınız. Nəzarətçiyə müraciət edin.": {
        "az": "İmtahandan çıxarıldınız. Nəzarətçiyə müraciət edin.",
        "en": "You have been removed from the exam. Please contact the invigilator.",
        "ru": "Вы удалены с экзамена. Обратитесь к наблюдателю.",
        "tr": "Sınavdan çıkarıldınız. Lütfen gözetmene başvurun.",
    },
    "Oturum ləğv edildi.": {
        "az": "Oturum ləğv edildi.",
        "en": "The session has been cancelled.",
        "ru": "Сессия отменена.",
        "tr": "Oturum iptal edildi.",
    },
    "İmtahanınız müvəqqəti dayandırıldı.": {
        "az": "İmtahanınız müvəqqəti dayandırıldı.",
        "en": "Your exam has been paused.",
        "ru": "Ваш экзамен временно приостановлен.",
        "tr": "Sınavınız geçici olarak durduruldu.",
    },
    "%(message)s Səbəb: %(reason)s": {
        "az": "%(message)s Səbəb: %(reason)s",
        "en": "%(message)s Reason: %(reason)s",
        "ru": "%(message)s Причина: %(reason)s",
        "tr": "%(message)s Neden: %(reason)s",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gözləmə otağı JS mətnlərini əlavə et")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        import polib
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{DOMAIN}.po")
        catalog = polib.pofile(path)
        index = {(e.msgctxt or "", e.msgid): e for e in catalog if not e.obsolete}

        added = updated = 0
        for msgid, texts in ENTRIES.items():
            entry = index.get(("", msgid))
            if entry is None:
                catalog.append(polib.POEntry(msgid=msgid, msgstr=texts[lang]))
                added += 1
            elif entry.msgstr != texts[lang]:
                entry.msgstr = texts[lang]
                updated += 1

        if (added or updated) and not args.dry_run:
            catalog.save(path)
        print(f"  {lang}: {added} yeni, {updated} yeniləndi")

    print("\n✅ Bitdi. İndi: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
