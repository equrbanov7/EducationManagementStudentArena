#!/usr/bin/env python3
"""EMSArena i18n — Paket C: sual göndərişi səhifələri (müəllim detalı · kafedra · İmtahan Mərkəzi), 2026-10-17.

«Növbəti addım» lentinin yeni mətnləri (apps/exams/views/teacher/submission_page_ui.py).
msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

QS = "exams.template.question_submission"

ENTRIES = {
    QS: {
        "Kafedra müdirinin təsdiqi gözlənilir": {
            "en": "Awaiting the head of department's approval",
            "ru": "Ожидается утверждение заведующего кафедрой",
            "tr": "Bölüm başkanının onayı bekleniyor",
            "de": "Freigabe durch die Lehrstuhlleitung ausstehend",
        },
        "Dekanlığın təsdiqi gözlənilir": {
            "en": "Awaiting the dean's office approval",
            "ru": "Ожидается утверждение деканата",
            "tr": "Dekanlığın onayı bekleniyor",
            "de": "Freigabe durch das Dekanat ausstehend",
        },
        "Təsdiqdən sonra dəst İmtahan Mərkəzinə gedəcək. Bu mərhələdə sualları hələ düzəldə bilərsiniz.": {
            "en": "Once approved, the set goes to the Exam Centre. You can still edit the questions at this stage.",
            "ru": "После утверждения набор будет отправлен в Экзаменационный центр. На этом этапе вопросы ещё можно исправить.",
            "tr": "Onaylandıktan sonra set Sınav Merkezine gönderilecek. Bu aşamada soruları hâlâ düzeltebilirsiniz.",
            "de": "Nach der Freigabe geht der Satz an das Prüfungszentrum. In dieser Phase können Sie die Fragen noch bearbeiten.",
        },
        "Kafedra təsdiqindən sonra dəst dondurulur — İmtahan Mərkəzinin qərarını gözləyin.": {
            "en": "After the department's approval the set is locked — wait for the Exam Centre's decision.",
            "ru": "После утверждения кафедрой набор заморожен — дождитесь решения Экзаменационного центра.",
            "tr": "Bölüm onayından sonra set kilitlenir — Sınav Merkezinin kararını bekleyin.",
            "de": "Nach der Freigabe durch den Lehrstuhl ist der Satz gesperrt — warten Sie auf die Entscheidung des Prüfungszentrums.",
        },
        "Kafedra düzəliş istədi — düzəldib yenidən göndərin": {
            "en": "The department requested changes — revise and resubmit",
            "ru": "Кафедра запросила исправления — исправьте и отправьте снова",
            "tr": "Bölüm düzeltme istedi — düzeltip yeniden gönderin",
            "de": "Der Lehrstuhl hat Änderungen angefordert — überarbeiten und erneut einreichen",
        },
        "İmtahan Mərkəzi düzəliş istədi — düzəldib yenidən göndərin": {
            "en": "The Exam Centre requested changes — revise and resubmit",
            "ru": "Экзаменационный центр запросил исправления — исправьте и отправьте снова",
            "tr": "Sınav Merkezi düzeltme istedi — düzeltip yeniden gönderin",
            "de": "Das Prüfungszentrum hat Änderungen angefordert — überarbeiten und erneut einreichen",
        },
        "Qərarınız gözlənilir": {
            "en": "Your decision is required",
            "ru": "Требуется ваше решение",
            "tr": "Kararınız bekleniyor",
            "de": "Ihre Entscheidung ist erforderlich",
        },
        "Sualları və xəbərdarlıqları yoxlayın, sonra təsdiqləyin, düzəliş istəyin və ya rədd edin.": {
            "en": "Check the questions and warnings, then approve, request changes or reject.",
            "ru": "Проверьте вопросы и предупреждения, затем утвердите, запросите исправления или отклоните.",
            "tr": "Soruları ve uyarıları kontrol edin, ardından onaylayın, düzeltme isteyin veya reddedin.",
            "de": "Prüfen Sie die Fragen und Warnungen, dann freigeben, Änderungen anfordern oder ablehnen.",
        },
        "Qəbul etsəniz suallar seçdiyiniz banka yazılır; düzəliş və rədd üçün müəllimə qeyd məcburidir.": {
            "en": "If you accept, the questions are written to the bank you choose; a note to the teacher is required for changes or rejection.",
            "ru": "При принятии вопросы записываются в выбранный банк; для исправления или отклонения комментарий преподавателю обязателен.",
            "tr": "Kabul ederseniz sorular seçtiğiniz bankaya yazılır; düzeltme ve ret için öğretmene not zorunludur.",
            "de": "Bei Annahme werden die Fragen in die gewählte Fragenbank geschrieben; für Änderungen oder Ablehnung ist eine Notiz an die Lehrkraft Pflicht.",
        },
        "Qərar ver": {
            "en": "Decide",
            "ru": "Принять решение",
            "tr": "Karar ver",
            "de": "Entscheiden",
        },
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
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
