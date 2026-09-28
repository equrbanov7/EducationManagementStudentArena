#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 audit remediasiyası, iş paketi C (sillabus / dərs yükü / cədvəl generatoru).

Əlavə olunan mətnlər:
  * `syllabus.notify`   — SYL-1: kafedra müdirinin öz sillabusu dekanlığa yönləndirilir;
  * `accounts.syllabus` — SYL-1: müəllif öz sillabusuna qərar verə bilmir;
  * `workload`          — W2: bölünmüş saatdan az cəm; W4: müəllim dəyişikliyində cədvəl toqquşması;
  * `timetable.policy`  — TT-1: pillə defoltu yalnız org-wide aktora;
  * `timetable.api`     — TT-2/TT-3/TT-5: işləmə dəyişmə hüququ, pozuq id, tezlik həddi;
  * `timetable.run`     — TT-4: brauzerə gedən ümumi xəta mətni.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_c_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _az(text):
    """AZ mənbə mətni msgid-dir — az kataloqunda eyni mətn yazılır."""
    return text


SYL_SELF = (
    "Bu sillabusun müəllifi kafedra müdirinin özüdür, ona görə öz sillabusunu təsdiqləyə bilməz. "
    "Qərar dekanlıq və ya universitet səviyyəsində verilməlidir."
)
SYL_FORBIDDEN = "Öz sillabusunuz üzrə qərar verə bilməzsiniz — qərar dekanlıq və ya universitet səviyyəsindədir."
WL_FLOOR = (
    "Bu fəaliyyət üzrə artıq %(assigned)s saat bölünüb — cəmi %(total)s saata endirmək olmaz. "
    "Əvvəlcə bölgünü azaldın."
)
WL_CONFLICT = (
    "Diqqət: yeni müəllimin cədvəldə eyni saatda başqa dərsi var (%(count)s toqquşma). " "Dərs cədvəlini yoxlayın."
)
TT_LEVEL = "Pillə defoltunu yalnız universitet səviyyəli cədvəl idarəçisi dəyişə bilər."
TT_LEVEL_NOTE = (
    "Pillə defoltunu yalnız universitet səviyyəli cədvəl idarəçisi dəyişə bilər. "
    "Öz qruplarınız üçün aşağıda istisna yaza bilərsiniz."
)
TT_BAD_GROUP = "Qrup identifikatoru düzgün deyil."
TT_RATE = "Çox tez-tez sorğu göndərilir — bir az sonra yenidən cəhd edin."
TT_MUTATE = "Bu işləməni yalnız onu yaradan və ya universitet səviyyəli idarəçi dəyişə bilər."
TT_PUBLIC_ERROR = (
    "İşləmə texniki xəta ilə dayandı. Parametrləri yoxlayıb yenidən cəhd edin; təkrarlansa inzibatçıya bildirin."
)

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    "syllabus.notify": {
        SYL_SELF: {
            "az": _az(SYL_SELF),
            "en": "The author of this syllabus is the head of department, who cannot approve their own syllabus. "
            "The decision must be made at the dean's office or university level.",
            "ru": "Автор этого силлабуса — сам заведующий кафедрой, поэтому он не может утвердить собственный "
            "силлабус. Решение должно приниматься на уровне деканата или университета.",
            "tr": "Bu izlencenin yazarı bölüm başkanının kendisidir, bu nedenle kendi izlencesini onaylayamaz. "
            "Karar dekanlık veya üniversite düzeyinde verilmelidir.",
        },
    },
    "accounts.syllabus": {
        SYL_FORBIDDEN: {
            "az": _az(SYL_FORBIDDEN),
            "en": "You cannot decide on your own syllabus — the decision is made at the dean's office or "
            "university level.",
            "ru": "Вы не можете принимать решение по собственному силлабусу — решение принимается на уровне "
            "деканата или университета.",
            "tr": "Kendi izlenceniz hakkında karar veremezsiniz — karar dekanlık veya üniversite düzeyinde verilir.",
        },
    },
    "workload": {
        WL_FLOOR: {
            "az": _az(WL_FLOOR),
            "en": "%(assigned)s hours of this activity are already assigned — the total cannot be reduced to "
            "%(total)s hours. Reduce the assignments first.",
            "ru": "По этому виду занятий уже распределено %(assigned)s ч — нельзя уменьшить итог до %(total)s ч. "
            "Сначала уменьшите распределение.",
            "tr": "Bu etkinlik için zaten %(assigned)s saat dağıtılmış — toplam %(total)s saate düşürülemez. "
            "Önce dağıtımı azaltın.",
        },
        WL_CONFLICT: {
            "az": _az(WL_CONFLICT),
            "en": "Warning: the new teacher already has another class at the same time in the timetable "
            "(%(count)s conflict(s)). Check the class schedule.",
            "ru": "Внимание: у нового преподавателя в расписании в это же время есть другое занятие "
            "(конфликтов: %(count)s). Проверьте расписание.",
            "tr": "Dikkat: yeni öğretmenin ders programında aynı saatte başka bir dersi var (%(count)s çakışma). "
            "Ders programını kontrol edin.",
        },
    },
    "timetable.policy": {
        TT_LEVEL: {
            "az": _az(TT_LEVEL),
            "en": "Only a university-level timetable manager can change the level defaults.",
            "ru": "Изменять настройки уровня по умолчанию может только управляющий расписанием на уровне "
            "университета.",
            "tr": "Düzey varsayılanlarını yalnızca üniversite düzeyindeki ders programı yöneticisi değiştirebilir.",
        },
        TT_LEVEL_NOTE: {
            "az": _az(TT_LEVEL_NOTE),
            "en": "Only a university-level timetable manager can change the level defaults. You can add "
            "exceptions for your own groups below.",
            "ru": "Изменять настройки уровня по умолчанию может только управляющий расписанием на уровне "
            "университета. Для своих групп вы можете задать исключения ниже.",
            "tr": "Düzey varsayılanlarını yalnızca üniversite düzeyindeki ders programı yöneticisi "
            "değiştirebilir. Kendi gruplarınız için aşağıda istisna tanımlayabilirsiniz.",
        },
    },
    "timetable.api": {
        TT_BAD_GROUP: {
            "az": _az(TT_BAD_GROUP),
            "en": "The group identifier is invalid.",
            "ru": "Неверный идентификатор группы.",
            "tr": "Grup kimliği geçersiz.",
        },
        TT_RATE: {
            "az": _az(TT_RATE),
            "en": "Too many requests — please try again in a moment.",
            "ru": "Слишком частые запросы — повторите попытку немного позже.",
            "tr": "Çok sık istek gönderiliyor — biraz sonra tekrar deneyin.",
        },
        TT_MUTATE: {
            "az": _az(TT_MUTATE),
            "en": "Only the creator of this run or a university-level manager can change it.",
            "ru": "Изменять этот запуск может только его создатель или управляющий на уровне университета.",
            "tr": "Bu çalıştırmayı yalnızca onu oluşturan kişi veya üniversite düzeyindeki yönetici değiştirebilir.",
        },
    },
    "timetable.run": {
        TT_PUBLIC_ERROR: {
            "az": _az(TT_PUBLIC_ERROR),
            "en": "The run stopped because of a technical error. Check the parameters and try again; if it "
            "happens again, notify the administrator.",
            "ru": "Запуск остановлен из-за технической ошибки. Проверьте параметры и повторите попытку; если "
            "ошибка повторится, сообщите администратору.",
            "tr": "Çalıştırma teknik bir hata nedeniyle durdu. Parametreleri kontrol edip tekrar deneyin; "
            "tekrarlanırsa yöneticiye bildirin.",
        },
    },
}

# Mövcud, amma yanlış tərcümələr — bu paketdə yoxdur.
FORCE = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
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
