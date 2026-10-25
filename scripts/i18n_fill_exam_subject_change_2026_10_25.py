#!/usr/bin/env python3
"""EMSArena i18n — nəticəli midtermin fənn dəyişikliyi: təsdiq + səbəb, tarixçə (sahib 2026-10-25).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CTX = "exams.subject_change"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "Bu imtahanda tələbə nəticələri var — fənn dəyişikliyini təsdiqləyin və səbəbini yazın.": t(
            "This exam already has student results — confirm the subject change and enter the reason.",
            "У этого экзамена уже есть результаты студентов — подтвердите смену предмета и укажите причину.",
            "Bu sınavda öğrenci sonuçları var — ders değişikliğini onaylayın ve nedenini yazın.",
            "Diese Prüfung hat bereits Ergebnisse von Studierenden — bestätigen Sie den Fachwechsel und geben "
            "Sie den Grund an.",
        ),
        "Fənn dəyişikliyini təsdiqləyin («Təsdiq edirəm»).": t(
            "Confirm the subject change («I confirm»).",
            "Подтвердите смену предмета («Подтверждаю»).",
            "Ders değişikliğini onaylayın («Onaylıyorum»).",
            "Bestätigen Sie den Fachwechsel («Ich bestätige»).",
        ),
        "Səbəb ən azı %(min)d simvol olmalıdır.": t(
            "The reason must be at least %(min)d characters long.",
            "Причина должна содержать не менее %(min)d символов.",
            "Neden en az %(min)d karakter olmalıdır.",
            "Der Grund muss mindestens %(min)d Zeichen lang sein.",
        ),
        "Fənn dəyişikliyi təsdiq tələb edir": t(
            "The subject change requires confirmation",
            "Смена предмета требует подтверждения",
            "Ders değişikliği onay gerektiriyor",
            "Der Fachwechsel erfordert eine Bestätigung",
        ),
        "Bu imtahanda %(students)s tələbənin nəticəsi var.": t(
            "Students with results in this exam: %(students)s.",
            "Студентов с результатами в этом экзамене: %(students)s.",
            "Bu sınavda sonucu olan öğrenci sayısı: %(students)s.",
            "Studierende mit Ergebnissen in dieser Prüfung: %(students)s.",
        ),
        "Saxladıqdan sonra nəticələr yeni fənnin jurnalına köçürüləcək, köhnə fənnin jurnalındakı bu imtahanın "
        "balları silinəcək.": t(
            "After saving, the results will be moved to the new subject's journal and this exam's scores in the "
            "old subject's journal will be removed.",
            "После сохранения результаты будут перенесены в журнал нового предмета, а баллы этого экзамена в "
            "журнале прежнего предмета будут удалены.",
            "Kaydettikten sonra sonuçlar yeni dersin defterine taşınacak, eski dersin defterindeki bu sınavın "
            "puanları silinecek.",
            "Nach dem Speichern werden die Ergebnisse in das Journal des neuen Fachs übertragen und die Punkte "
            "dieser Prüfung im Journal des bisherigen Fachs gelöscht.",
        ),
        "Təsdiq edirəm: nəticələr yeni fənnə köçürülsün": t(
            "I confirm: move the results to the new subject",
            "Подтверждаю: перенести результаты в новый предмет",
            "Onaylıyorum: sonuçlar yeni derse taşınsın",
            "Ich bestätige: Ergebnisse in das neue Fach übertragen",
        ),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "Məsələn: imtahan yaradılarkən fənn səhv seçilmişdi": t(
            "For example: the wrong subject was selected when the exam was created",
            "Например: при создании экзамена был выбран неверный предмет",
            "Örneğin: sınav oluşturulurken ders yanlış seçilmişti",
            "Zum Beispiel: Beim Anlegen der Prüfung wurde das falsche Fach gewählt",
        ),
        "Ən azı %(min)s simvol. Dəyişiklik, səbəb və köçürülən nəticələrin sayı imtahan tarixçəsinə yazılır.": t(
            "At least %(min)s characters. The change, the reason and the number of moved results are recorded "
            "in the exam history.",
            "Не менее %(min)s символов. Изменение, причина и число перенесённых результатов записываются в "
            "историю экзамена.",
            "En az %(min)s karakter. Değişiklik, neden ve taşınan sonuç sayısı sınav geçmişine yazılır.",
            "Mindestens %(min)s Zeichen. Die Änderung, der Grund und die Zahl der übertragenen Ergebnisse "
            "werden im Prüfungsverlauf festgehalten.",
        ),
        "Fənn dəyişikliyi tarixçəsi": t(
            "Subject change history", "История смены предмета", "Ders değişikliği geçmişi", "Verlauf der Fachwechsel"
        ),
        "Nəticəsi olan tələbə: %(students)s": t(
            "Students with results: %(students)s",
            "Студентов с результатами: %(students)s",
            "Sonucu olan öğrenci: %(students)s",
            "Studierende mit Ergebnissen: %(students)s",
        ),
        "Yeni jurnala köçürülən: %(moved)s · köhnə jurnaldan silinən: %(cleared)s": t(
            "Moved to the new journal: %(moved)s · removed from the old journal: %(cleared)s",
            "Перенесено в новый журнал: %(moved)s · удалено из прежнего журнала: %(cleared)s",
            "Yeni deftere taşınan: %(moved)s · eski defterden silinen: %(cleared)s",
            "Ins neue Journal übertragen: %(moved)s · aus dem alten Journal gelöscht: %(cleared)s",
        ),
        "yeni fənn üzrə jurnalda qeydiyyatı olmayan: %(n)s": t(
            "not enrolled in a journal of the new subject: %(n)s",
            "не записаны в журнал нового предмета: %(n)s",
            "yeni dersin defterinde kaydı olmayan: %(n)s",
            "nicht in einem Journal des neuen Fachs eingeschrieben: %(n)s",
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
