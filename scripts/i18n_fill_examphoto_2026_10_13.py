#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-13 (gecə, examphoto): imtahan ekranında tələbənin kimlik kartı.

Sahib: «test imtahanı zamanı solda ya da sağda tələbənin öz şəklinin görünməsi». Kart
`exams/student/partials/_proctor_id_card.html`-dədir (kontekst `exams.proctoring.identity`;
«Qrup» və «Tələbə №» bu kontekstdə artıq var).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_examphoto_2026_10_13.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = tuple(lang for lang in ("az", "en", "ru", "tr", "de") if os.path.isdir(os.path.join(BASE, "locale", lang)))
CTX = "exams.proctoring.identity"


def _t(az, en, ru, tr, de=None):
    return {"az": az, "en": en, "ru": ru, "tr": tr, "de": de or en}


# (ctx, msgid) → {az, en, ru, tr, de}
ENTRIES = {
    (CTX, "Tələbənin kimliyi"): _t(
        "Tələbənin kimliyi", "Student identity", "Личность студента", "Öğrenci kimliği", "Identität des Studierenden"
    ),
    (CTX, "Kimlik yoxlaması"): _t(
        "Kimlik yoxlaması", "Identity check", "Проверка личности", "Kimlik kontrolü", "Identitätsprüfung"
    ),
    (CTX, "İstifadəçi adı"): _t("İstifadəçi adı", "Username", "Имя пользователя", "Kullanıcı adı", "Benutzername"),
    (CTX, "Şəkil yüklənməyib — nəzarətçiyə şəxsiyyət vəsiqənizi göstərin."): _t(
        "Şəkil yüklənməyib — nəzarətçiyə şəxsiyyət vəsiqənizi göstərin.",
        "No photo uploaded — show your ID card to the invigilator.",
        "Фото не загружено — покажите удостоверение личности наблюдателю.",
        "Fotoğraf yüklenmemiş — gözetmene kimlik kartınızı gösterin.",
        "Kein Foto hochgeladen — zeigen Sie der Aufsicht Ihren Ausweis.",
    ),
}


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for (ctx, msgid), values in ENTRIES.items():
        want = values[lang]
        entry = index.get((ctx, msgid))
        if entry is None:
            po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
            added += 1
            continue
        if entry.msgstr != want or "fuzzy" in entry.flags or entry.obsolete:
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
