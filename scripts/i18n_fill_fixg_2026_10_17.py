#!/usr/bin/env python3
"""EMSArena i18n — FIX-G (QA-1 P3 tapıntıları) 2026-10-17.

Əlavə olunan / düzəldilən mətnlər:
  * `registrar.syllabus` — dərs hələ olmayanda sillabus bannerinin mətni («Dərslər başlayıb» demir) — F14;
  * `registrar.journal` — təqvim planında gələcək tarixli dərs üçün «planlaşdırılıb» (F13) və jurnal
    altlığında düzəliş ünvanı «RİM-ə (sənədli düzəliş)» (F14, bağlı jurnaldakı mətnlə eyni);
  * `accounts.lessons_log` — «Keçirilmiş dərslər» günlük cəmi: «1 lesson / 3 lessons», «2 hours» (F8, cəm formaları);
  * context-siz — «Şifrəni dəyiş»: yeni şifrə cari şifrə ilə eyni ola bilməz (F12);
  * `registrar.lessons_log`, `registrar.records` — ingilis «Payız»: «Autumn» → «Fall» (F8, başqa yerlərlə eyni);
  * `registrar.journal_timing` — türk dilində müddət etiketləri vahid: «2 sa.», «2 sa. 30 dk.», «45 dk.» (F18).

msgid AZ cümlədir → az msgstr = msgid. Skript idempotentdir: çatışmayanı əlavə edir, `OVERRIDES` isə mövcud
msgstr-i dəyişir. `.mo` fayllarını QURMUR — sonra: `compilemessages -i .claude -i venv`.

⚠️ `makemessages` İŞLƏDİLMİR.

İstifadə:  python scripts/i18n_fill_fixg_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

SYL = "registrar.syllabus"
JR = "registrar.journal"
LL = "accounts.lessons_log"
NOCTX = ""

SYL_BEFORE_LESSONS = (
    "Fənnin sillabusu hələ yaradılmayıb. Dərslər başlamazdan əvvəl sillabusunuzu yazıb kafedra müdirinin "
    "təsdiqinə göndərin — tələbələr yalnız təsdiqlənmiş sillabusu görür."
)
FOOT_LATE = (
    "Davamiyyət dərs günü və ondan sonra ən çox %(d)s gün ərzində qeyd edilə bilər · yazılmış qeyd %(w)s sonra "
    "kilidlənir — düzəliş üçün RİM-ə (sənədli düzəliş) müraciət edilir."
)
FOOT_SAME_DAY = (
    "Davamiyyət yalnız dərs günü qeyd edilə bilər · yazılmış qeyd %(w)s sonra kilidlənir — düzəliş üçün RİM-ə "
    "(sənədli düzəliş) müraciət edilir."
)

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid.
ENTRIES = {
    SYL: {
        SYL_BEFORE_LESSONS: {
            "en": "The subject's syllabus has not been created yet. Before the classes start, write your syllabus and "
            "send it to the head of department for approval — students only see an approved syllabus.",
            "ru": "Силлабус предмета ещё не создан. До начала занятий напишите силлабус и отправьте его на "
            "утверждение заведующему кафедрой — студенты видят только утверждённый силлабус.",
            "tr": "Dersin izlencesi henüz oluşturulmamış. Dersler başlamadan önce izlencenizi yazıp bölüm "
            "başkanının onayına gönderin — öğrenciler yalnızca onaylı izlenceyi görür.",
            "de": "Der Syllabus des Fachs wurde noch nicht erstellt. Verfassen Sie Ihren Syllabus vor Unterrichtsbeginn "
            "und senden Sie ihn der Lehrstuhlleitung zur Genehmigung — Studierende sehen nur einen genehmigten "
            "Syllabus.",
        },
    },
    JR: {
        "planlaşdırılıb": {"en": "planned", "ru": "запланировано", "tr": "planlandı", "de": "geplant"},
        FOOT_LATE: {
            "en": "Attendance can be recorded on the lesson day and up to %(d)s day(s) after it · a recorded mark "
            "locks after %(w)s — for a correction, apply to the Digital Development Centre (RİM) for a documented "
            "correction.",
            "ru": "Посещаемость отмечается в день занятия и не позднее %(d)s дн. после него · запись блокируется "
            "через %(w)s — для исправления обратитесь в Центр цифрового развития (RİM) за документальным "
            "исправлением.",
            "tr": "Devam, ders günü ve sonrasında en fazla %(d)s gün içinde kaydedilebilir · girilen kayıt %(w)s "
            "sonra kilitlenir — düzeltme için RİM'e (belgeli düzeltme) başvurulur.",
            "de": "Die Anwesenheit kann am Unterrichtstag und bis zu %(d)s Tag(e) danach erfasst werden · ein Eintrag "
            "wird nach %(w)s gesperrt — für eine Korrektur wenden Sie sich an das RİM (dokumentierte Korrektur).",
        },
        FOOT_SAME_DAY: {
            "en": "Attendance can be recorded only on the lesson day · a recorded mark locks after %(w)s — for a "
            "correction, apply to the Digital Development Centre (RİM) for a documented correction.",
            "ru": "Посещаемость отмечается только в день занятия · запись блокируется через %(w)s — для "
            "исправления обратитесь в Центр цифрового развития (RİM) за документальным исправлением.",
            "tr": "Devam yalnızca ders günü kaydedilebilir · girilen kayıt %(w)s sonra kilitlenir — düzeltme için "
            "RİM'e (belgeli düzeltme) başvurulur.",
            "de": "Die Anwesenheit kann nur am Unterrichtstag erfasst werden · ein Eintrag wird nach %(w)s gesperrt — "
            "für eine Korrektur wenden Sie sich an das RİM (dokumentierte Korrektur).",
        },
    },
    NOCTX: {
        "Yeni şifrə cari şifrədən fərqli olmalıdır.": {
            "en": "The new password must be different from the current password.",
            "ru": "Новый пароль должен отличаться от текущего.",
            "tr": "Yeni şifre mevcut şifreden farklı olmalıdır.",
            "de": "Das neue Passwort muss sich vom aktuellen Passwort unterscheiden.",
        },
    },
}

# (ctx, singular, plural) → {lang: [forms]}. ru 4 forma, qalanları 2.
PLURALS = {
    (LL, "%(n)s dərs", "%(n)s dərs"): {
        "az": ["%(n)s dərs", "%(n)s dərs"],
        "en": ["%(n)s lesson", "%(n)s lessons"],
        "ru": ["%(n)s занятие", "%(n)s занятия", "%(n)s занятий", "%(n)s занятия"],
        "tr": ["%(n)s ders", "%(n)s ders"],
        "de": ["%(n)s Unterrichtseinheit", "%(n)s Unterrichtseinheiten"],
    },
    (LL, "%(n)s saat", "%(n)s saat"): {
        "az": ["%(n)s saat", "%(n)s saat"],
        "en": ["%(n)s hour", "%(n)s hours"],
        "ru": ["%(n)s час", "%(n)s часа", "%(n)s часов", "%(n)s часа"],
        "tr": ["%(n)s saat", "%(n)s saat"],
        "de": ["%(n)s Stunde", "%(n)s Stunden"],
    },
}

# Mövcud msgstr-i DƏYİŞƏNLƏR: (ctx, msgid) → {lang: msgstr}.
OVERRIDES = {
    ("registrar.lessons_log", "Payız"): {"en": "Fall"},
    ("registrar.records", "Payız"): {"en": "Fall"},
    ("registrar.journal_timing", "%(n)s saat"): {"tr": "%(n)s sa."},
    ("registrar.journal_timing", "%(h)s saat %(m)s dəqiqə"): {"tr": "%(h)s sa. %(m)s dk."},
    ("registrar.journal_timing", "%(n)s dəqiqə"): {"tr": "%(n)s dk."},
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(entry.msgctxt or "", entry.msgid): entry for entry in po}
    added = changed = 0

    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr))
                added += 1
            elif entry.obsolete:
                entry.obsolete = False
                entry.msgstr = msgstr
                changed += 1

    nplurals = 4 if lang == "ru" else 2
    for (ctx, singular, plural), forms in PLURALS.items():
        values = {i: form for i, form in enumerate(forms[lang][:nplurals])}
        entry = index.get((ctx, singular))
        if entry is None:
            po.append(polib.POEntry(msgctxt=ctx or None, msgid=singular, msgid_plural=plural, msgstr_plural=values))
            added += 1
        elif entry.msgstr_plural != values:
            entry.msgstr_plural = values
            changed += 1

    for (ctx, msgid), translations in OVERRIDES.items():
        want = translations.get(lang)
        entry = index.get((ctx, msgid))
        if want and entry is not None and entry.msgstr != want:
            entry.msgstr = want
            if "fuzzy" in entry.flags:
                entry.flags.remove("fuzzy")
            changed += 1

    if added or changed:
        po.save(path)
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
