#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 şəbəkə zonası izah səhifəsi (sahib: «hamı developer deyil»).

Əlavə olunan mətnlər (`accounts.network_zone`, `templates/errors/network_zone.html`): kənardan
/jurnal/ və /manage/ açılanda sadə dildə səbəb və «Nə etməli?» addımları.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_netzone_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

NZ = "accounts.network_zone"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_ROWS = [
    _t(
        "İdarəetmə paneli yalnız universitet şəbəkəsində açılır",
        "The admin panel opens only on the university network",
        "Панель управления открывается только в сети университета",
        "Yönetim paneli yalnızca üniversite ağında açılır",
    ),
    _t(
        "Siz hazırda universitetdən kənar internetdən (mobil internet və ya ev Wi-Fi-ı) qoşulmusunuz.",
        "You are currently connected from outside the university (mobile data or home Wi-Fi).",
        "Сейчас вы подключены не из университета (мобильный интернет или домашний Wi-Fi).",
        "Şu anda üniversite dışından (mobil internet veya ev Wi-Fi'ı) bağlısınız.",
    ),
    _t(
        "Təhlükəsizlik üçün qiymət və davamiyyət yalnız universitet binasında, universitetin Wi-Fi və ya "
        "kompüter şəbəkəsindən yazılır.",
        "For security, grades and attendance can be entered only inside the university, over the university "
        "Wi-Fi or computer network.",
        "В целях безопасности оценки и посещаемость вносятся только в здании университета — через "
        "университетский Wi-Fi или компьютерную сеть.",
        "Güvenlik için not ve devam bilgisi yalnızca üniversite binasında, üniversitenin Wi-Fi veya bilgisayar "
        "ağından girilir.",
    ),
    _t(
        "Təhlükəsizlik üçün bu bölmə yalnız universitet binasında, universitetin Wi-Fi və ya kompüter "
        "şəbəkəsindən açılır.",
        "For security, this section opens only inside the university, over the university Wi-Fi or computer "
        "network.",
        "В целях безопасности этот раздел открывается только в здании университета — через университетский "
        "Wi-Fi или компьютерную сеть.",
        "Güvenlik için bu bölüm yalnızca üniversite binasında, üniversitenin Wi-Fi veya bilgisayar ağından açılır.",
    ),
    _t("Nə etməli?", "What to do?", "Что делать?", "Ne yapmalı?"),
    _t(
        "Universitetdəsinizsə: telefonda mobil interneti söndürün və universitetin Wi-Fi şəbəkəsinə qoşulun "
        "(kompüterdə — universitet şəbəkəsinə).",
        "If you are at the university: turn off mobile data on your phone and connect to the university Wi-Fi "
        "(on a computer — to the university network).",
        "Если вы в университете: отключите мобильный интернет на телефоне и подключитесь к университетскому "
        "Wi-Fi (на компьютере — к сети университета).",
        "Üniversitedeyseniz: telefonda mobil interneti kapatın ve üniversitenin Wi-Fi ağına bağlanın "
        "(bilgisayarda — üniversite ağına).",
    ),
    _t(
        "Sonra bu səhifəni yeniləyin.",
        "Then reload this page.",
        "Затем обновите эту страницу.",
        "Ardından bu sayfayı yenileyin.",
    ),
    _t(
        "Kabinetin digər bölmələri — dərs cədvəli, fənlər, imtahanlar, sillabus — evdən də işləyir.",
        "Other parts of your account — timetable, subjects, exams, syllabus — also work from home.",
        "Остальные разделы кабинета — расписание, предметы, экзамены, силлабус — работают и из дома.",
        "Hesabınızın diğer bölümleri — ders programı, dersler, sınavlar, müfredat — evden de çalışır.",
    ),
    _t(
        "Universitet Wi-Fi-ına qoşulduğunuz halda da bu səhifə çıxırsa, RİM mərkəzinə müraciət edin.",
        "If you still see this page while connected to the university Wi-Fi, contact the Digital Development "
        "Centre (RİM).",
        "Если эта страница появляется и при подключении к университетскому Wi-Fi, обратитесь в Центр "
        "цифрового развития (RİM).",
        "Üniversite Wi-Fi'ına bağlıyken de bu sayfa çıkıyorsa RİM merkezine başvurun.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {NZ: {row["az"]: row for row in _ROWS}}

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
