#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-09: eyni FİN — tələbə + işçi hesabı bağ təsdiqi modalı (``apps/accounts/shared_fin.py``,
``accounts/profile_completion.html``). Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_shared_fin_2026_11_09.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_C = "accounts.profile_completion"

STRINGS = {
    (_C, "tələbə hesabınız"): (
        "your student account",
        "ваша учётная запись студента",
        "öğrenci hesabınız",
        "Ihr Studierendenkonto",
    ),
    (_C, "işçi hesabınız"): (
        "your staff account",
        "ваша учётная запись сотрудника",
        "personel hesabınız",
        "Ihr Mitarbeiterkonto",
    ),
    (_C, "başqa hesabınız"): (
        "your other account",
        "ваша другая учётная запись",
        "diğer hesabınız",
        "Ihr anderes Konto",
    ),
    (_C, "Təsdiq tələb olunur"): (
        "Confirmation required",
        "Требуется подтверждение",
        "Onay gerekiyor",
        "Bestätigung erforderlich",
    ),
    (_C, "Bu FİN ilə sistemdə başqa hesabınız da var"): (
        "You also have another account in the system with this FIN",
        "В системе есть ещё одна ваша учётная запись с этим FIN",
        "Bu FİN ile sistemde başka bir hesabınız daha var",
        "Mit dieser FIN existiert im System noch ein weiteres Konto von Ihnen",
    ),
    (
        _C,
        "Yazdığınız FİN artıq %(label)s ilə qeydə alınıb: <strong>%(name)s</strong>. Hər iki hesab sizindirsə "
        "təsdiqləyin — FİN hər iki hesabda görünəcək və bu sual bir daha verilməyəcək.",
    ): (
        "The FIN you entered is already registered with %(label)s: <strong>%(name)s</strong>. If both accounts are "
        "yours, confirm — the FIN will be shown on both accounts and you will not be asked again.",
        "Введённый FIN уже зарегистрирован: %(label)s — <strong>%(name)s</strong>. Если обе учётные записи ваши, "
        "подтвердите — FIN будет виден в обеих, и этот вопрос больше не появится.",
        "Girdiğiniz FİN zaten %(label)s ile kayıtlı: <strong>%(name)s</strong>. Her iki hesap da sizinse onaylayın — "
        "FİN her iki hesapta görünecek ve bu soru bir daha sorulmayacak.",
        "Die eingegebene FIN ist bereits mit %(label)s registriert: <strong>%(name)s</strong>. Wenn beide Konten Ihnen "
        "gehören, bestätigen Sie — die FIN wird in beiden Konten angezeigt und diese Frage wird nicht erneut gestellt.",
    ),
    (
        _C,
        "İşçi hesabı ilə öz qrupunuza və öz jurnallarınıza aid əməliyyatlar aparıla bilməz — bu, sistem tərəfindən "
        "avtomatik qorunur.",
    ): (
        "With the staff account you cannot perform operations on your own group or your own journals — the system "
        "enforces this automatically.",
        "С учётной записи сотрудника нельзя выполнять операции над своей группой и своими журналами — система "
        "контролирует это автоматически.",
        "Personel hesabıyla kendi grubunuza ve kendi günlüklerinize ilişkin işlemler yapılamaz — sistem bunu otomatik "
        "olarak korur.",
        "Mit dem Mitarbeiterkonto können keine Vorgänge an Ihrer eigenen Gruppe oder Ihren eigenen Journalen "
        "durchgeführt werden — das System stellt dies automatisch sicher.",
    ),
    (_C, "Bəli, hər iki hesab mənimdir"): (
        "Yes, both accounts are mine",
        "Да, обе учётные записи мои",
        "Evet, her iki hesap da benim",
        "Ja, beide Konten gehören mir",
    ),
    (_C, "Xeyr, bu mən deyiləm"): (
        "No, that is not me",
        "Нет, это не я",
        "Hayır, bu ben değilim",
        "Nein, das bin ich nicht",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
