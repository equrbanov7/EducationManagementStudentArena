#!/usr/bin/env python3
"""EMSArena i18n — final/midterm apellyasiyası: «imtahan sonunda» / «sonradan» rejimləri (2026-10-20).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. `{% blocktrans %}` mətnləri `%(ad)s` yer tutucusu ilə yazılıb.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AT = "appeals.template"
RES = "exams.template.student_exam_result"
RS = "core.runtime_settings"
FIELD = "appeals.model.appeal.field"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


# az msgstr-i msgid-dən fərqli olan açar-tipli msgid-lər (model sahəsi adı).
AZ_OVERRIDES = {
    (FIELD, "filed_onsite"): "İmtahan sonunda verilib",
}

ENTRIES = {
    AT: {
        # ── Tələbə forması: rejim banneri ───────────────────────────────────
        "İmtahan sonunda apellyasiya": t(
            "Appeal at the end of the exam",
            "Апелляция сразу после экзамена",
            "Sınav sonunda itiraz",
            "Einspruch direkt nach der Prüfung",
        ),
        "İmtahan yenicə bitdiyi üçün hər sualın variantlarını, öz cavabınızı və düzgün cavabı görürsünüz.": t(
            "Because the exam has just ended, you can see each question's options, your answer and the correct "
            "answer.",
            "Поскольку экзамен только что завершился, вы видите варианты каждого вопроса, свой ответ и правильный "
            "ответ.",
            "Sınav yeni bittiği için her sorunun seçeneklerini, kendi cevabınızı ve doğru cevabı görüyorsunuz.",
            "Da die Prüfung gerade erst beendet wurde, sehen Sie die Antwortoptionen jeder Frage, Ihre Antwort und "
            "die richtige Antwort.",
        ),
        "Bu imkan %(until)s-dək davam edir; sonradan verilən apellyasiyada yalnız suallar göstərilir.": t(
            "This is available until %(until)s; an appeal filed later shows the questions only.",
            "Эта возможность действует до %(until)s; в апелляции, поданной позже, показываются только вопросы.",
            "Bu imkân %(until)s saatine kadar geçerlidir; daha sonra yapılan itirazda yalnızca sorular gösterilir.",
            "Dies ist bis %(until)s möglich; bei einem später eingereichten Einspruch werden nur die Fragen "
            "angezeigt.",
        ),
        "Sonradan verilən apellyasiya — yalnız suallar": t(
            "Appeal filed later — questions only",
            "Апелляция, поданная позже, — только вопросы",
            "Sonradan yapılan itiraz — yalnızca sorular",
            "Später eingereichter Einspruch — nur Fragen",
        ),
        "Bu rejimdə yalnız sualların mətni göstərilir: variantlar və düzgün cavab göstərilmir. Etiraz etdiyiniz "
        "sualı seçin və səbəbini yazın.": t(
            "In this mode only the question text is shown: options and the correct answer are not shown. Select the "
            "question you contest and write your reason.",
            "В этом режиме показывается только текст вопросов: варианты и правильный ответ не показываются. "
            "Выберите оспариваемый вопрос и напишите причину.",
            "Bu modda yalnızca soruların metni gösterilir: seçenekler ve doğru cevap gösterilmez. İtiraz ettiğiniz "
            "soruyu seçin ve gerekçenizi yazın.",
            "In diesem Modus wird nur der Fragetext angezeigt: Antwortoptionen und die richtige Antwort werden nicht "
            "angezeigt. Wählen Sie die angefochtene Frage und geben Sie Ihre Begründung an.",
        ),
        # ── «Yeni apellyasiya» modalı ────────────────────────────────────────
        "Sonradan verilən apellyasiyada yalnız sualların mətni göstərilir — variantlar və düzgün cavab "
        "göstərilmir.": t(
            "An appeal filed later shows only the question text — options and the correct answer are not shown.",
            "В апелляции, поданной позже, показывается только текст вопросов — варианты и правильный ответ не "
            "показываются.",
            "Sonradan yapılan itirazda yalnızca soruların metni gösterilir — seçenekler ve doğru cevap gösterilmez.",
            "Bei einem später eingereichten Einspruch wird nur der Fragetext angezeigt — Antwortoptionen und die "
            "richtige Antwort werden nicht angezeigt.",
        ),
        # ── Əməkdaş nişanı ───────────────────────────────────────────────────
        "İmtahan sonunda verilib": t(
            "Filed at the end of the exam",
            "Подана сразу после экзамена",
            "Sınav sonunda yapıldı",
            "Direkt nach der Prüfung eingereicht",
        ),
        "Sonradan verilib": t("Filed later", "Подана позже", "Sonradan yapıldı", "Später eingereicht"),
        "Tələbə müraciəti imtahan bitən kimi verib — formada variantları və düzgün cavabı görürdü.": t(
            "The student filed the appeal right after the exam — the form showed the options and the correct answer.",
            "Студент подал апелляцию сразу после экзамена — в форме были видны варианты и правильный ответ.",
            "Öğrenci itirazı sınav biter bitmez yaptı — formda seçenekleri ve doğru cevabı görüyordu.",
            "Die studierende Person hat den Einspruch direkt nach der Prüfung eingereicht — im Formular waren die "
            "Antwortoptionen und die richtige Antwort sichtbar.",
        ),
        "Tələbə müraciəti sonradan verib — formada yalnız sualları görürdü.": t(
            "The student filed the appeal later — the form showed the questions only.",
            "Студент подал апелляцию позже — в форме были видны только вопросы.",
            "Öğrenci itirazı sonradan yaptı — formda yalnızca soruları görüyordu.",
            "Die studierende Person hat den Einspruch später eingereicht — im Formular waren nur die Fragen "
            "sichtbar.",
        ),
    },
    RES: {
        "İmtahan bitəndən sonrakı %(minutes)s dəqiqə ərzində (universitet şəbəkəsində) verilən apellyasiyada "
        "suallarla yanaşı variantları və düzgün cavabı da görəcəksiniz. Sonradan verilən apellyasiyada yalnız "
        "suallar göstərilir.": t(
            "If you appeal within %(minutes)s minutes after the exam (on the university network), you will also see "
            "the options and the correct answer along with the questions. An appeal filed later shows the questions "
            "only.",
            "В апелляции, поданной в течение %(minutes)s минут после экзамена (в сети университета), вместе с "
            "вопросами вы увидите варианты и правильный ответ. В апелляции, поданной позже, показываются только "
            "вопросы.",
            "Sınavdan sonraki %(minutes)s dakika içinde (üniversite ağında) yapılan itirazda sorularla birlikte "
            "seçenekleri ve doğru cevabı da göreceksiniz. Sonradan yapılan itirazda yalnızca sorular gösterilir.",
            "Bei einem Einspruch innerhalb von %(minutes)s Minuten nach der Prüfung (im Hochschulnetz) sehen Sie "
            "neben den Fragen auch die Antwortoptionen und die richtige Antwort. Bei einem später eingereichten "
            "Einspruch werden nur die Fragen angezeigt.",
        ),
    },
    RS: {
        "İmtahan sonunda apellyasiya müddəti": t(
            "Appeal-at-exam-end period",
            "Срок апелляции сразу после экзамена",
            "Sınav sonunda itiraz süresi",
            "Einspruchsfrist direkt nach der Prüfung",
        ),
        "Final/midterm bitdikdən sonra neçə dəqiqə ərzində, universitet şəbəkəsindən və imtahanı verdiyi "
        "sessiyadan verilən apellyasiyada tələbə sualla yanaşı variantları, öz cavabını və düzgün cavabı "
        "görür. Bundan sonra (məsələn, evdən) verilən apellyasiyada yalnız suallar göstərilir. "
        "0 — bu rejim söndürülür (həmişə yalnız suallar).": t(
            "For how many minutes after a final/midterm ends an appeal filed from the university network and the "
            "session in which the exam was taken shows the student the options, their own answer and the correct "
            "answer along with the question. An appeal filed after that (for example, from home) shows the "
            "questions only. 0 — this mode is off (questions only, always).",
            "В течение скольких минут после окончания финала/промежуточного экзамена в апелляции, поданной из сети "
            "университета и из сессии, в которой сдавался экзамен, студент видит вместе с вопросом варианты, свой "
            "ответ и правильный ответ. В апелляции, поданной позже (например, из дома), показываются только "
            "вопросы. 0 — режим отключён (всегда только вопросы).",
            "Final/ara sınav bittikten sonra kaç dakika içinde, üniversite ağından ve sınavın verildiği oturumdan "
            "yapılan itirazda öğrenci soruyla birlikte seçenekleri, kendi cevabını ve doğru cevabı görür. Bundan "
            "sonra (örneğin evden) yapılan itirazda yalnızca sorular gösterilir. 0 — bu mod kapalıdır (her zaman "
            "yalnızca sorular).",
            "Wie viele Minuten nach Ende einer Final-/Zwischenprüfung ein aus dem Hochschulnetz und aus der "
            "Prüfungssitzung eingereichter Einspruch der studierenden Person neben der Frage auch die "
            "Antwortoptionen, die eigene Antwort und die richtige Antwort zeigt. Ein danach (z. B. von zu Hause) "
            "eingereichter Einspruch zeigt nur die Fragen. 0 — dieser Modus ist aus (immer nur Fragen).",
        ),
        "dəqiqə": t("minutes", "минут", "dakika", "Minuten"),
    },
    FIELD: {
        "filed_onsite": t(
            "Filed at the end of the exam",
            "Подана сразу после экзамена",
            "Sınav sonunda yapıldı",
            "Direkt nach der Prüfung eingereicht",
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
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
