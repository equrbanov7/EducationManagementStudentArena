#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 (WP8, URL auditi A7): bildiriş mətnləri «Təşkilata qoşul» bölməsinə yönləndirmir.

`student-organization-request/` bölməsi silindi; dəvətlər «Bildirişlər» bölməsində qəbul / rədd olunur.
Yeni mətnlər (`notifications.event`, mənbə dili ingiliscədir — apps/notifications/services/events.py):
  * «You were removed from {organization}.»
  * «{organization} sent you an invitation as {role_label}. You can accept or decline it in the
    "Notifications" section of your profile.»

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp8urls.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

NE = "notifications.event"


def _t(msgid, az, en, ru, tr):
    return msgid, {"az": az, "en": en, "ru": ru, "tr": tr}


_NOTIFICATIONS = [
    _t(
        "You were removed from {organization}.",
        "{organization} təşkilatından uzaqlaşdırıldınız.",
        "You were removed from {organization}.",
        "Вы были удалены из организации {organization}.",
        "{organization} kuruluşundan çıkarıldınız.",
    ),
    _t(
        "{organization} sent you an invitation as {role_label}. You can accept or decline it in the "
        '"Notifications" section of your profile.',
        "{organization} təşkilatından sizə {role_label} kimi dəvət göndərildi. "
        'Dəvəti profildəki "Bildirişlər" bölməsində qəbul və ya rədd edə bilərsiniz.',
        "{organization} sent you an invitation as {role_label}. You can accept or decline it in the "
        '"Notifications" section of your profile.',
        "{organization} отправила вам приглашение в роли {role_label}. "
        "Принять или отклонить его можно в разделе «Уведомления» вашего профиля.",
        "{organization} size {role_label} olarak bir davet gönderdi. "
        'Daveti profilinizdeki "Bildirimler" bölümünde kabul edebilir veya reddedebilirsiniz.',
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    NE: dict(_NOTIFICATIONS),
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
