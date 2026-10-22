#!/usr/bin/env python3
"""EMSArena i18n — profil aktivləşdirəndə RİM-ə bildiriş + RİM mərkəzinin aktivləşdirmə sayı (2026-10-23).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
RA = "accounts.rim_activation"
PR = "profile.rim"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    RS: {
        "Profil aktivləşdiriləndə RİM-ə bildiriş": t(
            "Notify the Digital Development Centre when a profile is activated",
            "Уведомлять ЦЦР об активации профиля",
            "Profil etkinleştirildiğinde RİM'e bildirim",
            "Digitalzentrum bei Profilaktivierung benachrichtigen",
        ),
        "Yandırılanda istifadəçi e-poçtunu təsdiqləyib öz parolunu quranda (ilk giriş və ya parol bərpası) "
        "RİM mərkəzinin bütün üzvlərinə bildiriş gedir: kim aktivləşdirdi və cəmi neçə nəfər aktivləşdirib. "
        "Toplu aktivləşdirmə günlərində bildiriş çox olarsa söndürün — say RİM mərkəzində görünməyə davam edir.": t(
            "When turned on, every member of the Digital Development Centre is notified when a user confirms "
            "their email and sets their own password (first login or password recovery): who activated and how "
            "many people have activated in total. Turn it off if there are too many notifications on mass "
            "activation days — the count stays visible in the centre's panel.",
            "Если включено, все сотрудники ЦЦР получают уведомление, когда пользователь подтверждает e-mail и "
            "задаёт свой пароль (первый вход или восстановление пароля): кто активировал и сколько человек "
            "активировали всего. Выключите, если в дни массовой активации уведомлений слишком много — счётчик "
            "по-прежнему виден в панели ЦЦР.",
            "Açıldığında kullanıcı e-postasını doğrulayıp kendi parolasını belirlediğinde (ilk giriş veya parola "
            "kurtarma) RİM merkezinin tüm üyelerine bildirim gider: kimin etkinleştirdiği ve toplam kaç kişinin "
            "etkinleştirdiği. Toplu etkinleştirme günlerinde bildirim çok olursa kapatın — sayı RİM merkezinde "
            "görünmeye devam eder.",
            "Wenn eingeschaltet, werden alle Mitglieder des Digitalzentrums benachrichtigt, sobald jemand seine "
            "E-Mail bestätigt und ein eigenes Passwort festlegt (erste Anmeldung oder Passwortwiederherstellung): "
            "wer aktiviert hat und wie viele insgesamt aktiviert haben. Bei zu vielen Meldungen an Tagen mit "
            "Massenaktivierung ausschalten — die Zahl bleibt im Zentrum sichtbar.",
        ),
    },
    RA: {
        "Tələbə": t("Student", "Студент", "Öğrenci", "Studierende(r)"),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretim elemanı", "Lehrkraft"),
        "Əməkdaş": t("Staff", "Сотрудник", "Personel", "Mitarbeiter(in)"),
        "Cəmi aktivləşdirən: %(done)d / %(total)d (%(pct)s%%)": t(
            "Activated in total: %(done)d / %(total)d (%(pct)s%%)",
            "Всего активировали: %(done)d / %(total)d (%(pct)s%%)",
            "Toplam etkinleştiren: %(done)d / %(total)d (%%%(pct)s)",
            "Insgesamt aktiviert: %(done)d / %(total)d (%(pct)s%%)",
        ),
        "tələbə %(s)d / %(st)d, müəllim %(t)d / %(tt)d, əməkdaş %(e)d / %(et)d": t(
            "students %(s)d / %(st)d, teachers %(t)d / %(tt)d, staff %(e)d / %(et)d",
            "студенты %(s)d / %(st)d, преподаватели %(t)d / %(tt)d, сотрудники %(e)d / %(et)d",
            "öğrenci %(s)d / %(st)d, öğretim elemanı %(t)d / %(tt)d, personel %(e)d / %(et)d",
            "Studierende %(s)d / %(st)d, Lehrkräfte %(t)d / %(tt)d, Mitarbeitende %(e)d / %(et)d",
        ),
        "Profilini aktivləşdirdi: %(name)s": t(
            "Profile activated: %(name)s",
            "Профиль активирован: %(name)s",
            "Profilini etkinleştirdi: %(name)s",
            "Profil aktiviert: %(name)s",
        ),
        "RİM mərkəzində aç": t(
            "Open in the Digital Development Centre",
            "Открыть в ЦЦР",
            "RİM merkezinde aç",
            "Im Digitalzentrum öffnen",
        ),
    },
    PR: {
        "PROFİLİNİ AKTİVLƏŞDİRİB": t(
            "PROFILE ACTIVATED", "АКТИВИРОВАЛИ ПРОФИЛЬ", "PROFİLİNİ ETKİNLEŞTİRDİ", "PROFIL AKTIVIERT"
        ),
        "%(total)d nəfərdən · %(pct)s%%": t(
            "of %(total)d people · %(pct)s%%",
            "из %(total)d человек · %(pct)s%%",
            "%(total)d kişiden · %%%(pct)s",
            "von %(total)d Personen · %(pct)s%%",
        ),
        "TƏLƏBƏ": t("STUDENTS", "СТУДЕНТЫ", "ÖĞRENCİ", "STUDIERENDE"),
        "MÜƏLLİM": t("TEACHERS", "ПРЕПОДАВАТЕЛИ", "ÖĞRETİM ELEMANI", "LEHRKRÄFTE"),
        "ƏMƏKDAŞ": t("STAFF", "СОТРУДНИКИ", "PERSONEL", "MITARBEITENDE"),
        "aktivləşdirib · %(pct)s%%": t(
            "activated · %(pct)s%%",
            "активировали · %(pct)s%%",
            "etkinleştirdi · %%%(pct)s",
            "aktiviert · %(pct)s%%",
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
