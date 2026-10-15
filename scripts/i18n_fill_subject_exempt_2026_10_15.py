#!/usr/bin/env python3
"""EMSArena i18n — «Fəndən azad et» / «Bərpa et» 2026-10-15.

Sahib: «tələbə qrupda qalır, amma hansısa fəndən azaddır — onu ancaq jurnalda o fəndən çıxarda bilim».
Əlavə olunan mətnlər:
  * `registrar.journal_hygiene` — yeni qərar kateqoriyası «Fəndən azad» (model + «Jurnal təmizliyi» tarixçəsi);
  * `registrar.subject_exempt` — servis / HTTP mesajları (`subject_exempt.py`, `subject_exempt_views.py`),
    jurnal səhifəsinin sətir düyməsi, modal və «Azad edilənlər» siyahısı (`_jd_grid.html`,
    `_jd_subject_exempt.html`);
  * `profile.subjects` — tələbə kabinetində «Azad edildiyiniz fənlər» bloku (`_my_subjects.html`).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_subject_exempt_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

HYGIENE = "registrar.journal_hygiene"
EXEMPT = "registrar.subject_exempt"
SUBJECTS = "profile.subjects"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    HYGIENE: {
        "Fəndən azad": t("Exempt from subject", "Освобождён от предмета", "Dersten muaf", "Vom Fach befreit"),
    },
    EXEMPT: {
        "Sənəd tarixi düzgün deyil.": t(
            "The document date is invalid.",
            "Неверная дата документа.",
            "Belge tarihi geçersiz.",
            "Das Dokumentdatum ist ungültig.",
        ),
        "Fəndən azad edildi": t(
            "Exempted from the subject", "Освобождён от предмета", "Dersten muaf tutuldu", "Vom Fach befreit"
        ),
        "sənəd: %(doc)s": t("document: %(doc)s", "документ: %(doc)s", "belge: %(doc)s", "Dokument: %(doc)s"),
        "Qeydiyyat tapılmadı.": t(
            "Enrollment not found.", "Запись не найдена.", "Kayıt bulunamadı.", "Einschreibung nicht gefunden."
        ),
        "Bu tələbə artıq jurnalda deyil.": t(
            "This student is no longer in the journal.",
            "Этого студента уже нет в журнале.",
            "Bu öğrenci artık defterde değil.",
            "Diese Person steht nicht mehr im Journal.",
        ),
        "Fəndən azadlıq geri alındı": t(
            "Subject exemption withdrawn",
            "Освобождение от предмета отменено",
            "Ders muafiyeti geri alındı",
            "Befreiung vom Fach aufgehoben",
        ),
        "Qərar tapılmadı və ya artıq geri qaytarılıb.": t(
            "Decision not found or already reverted.",
            "Решение не найдено или уже отменено.",
            "Karar bulunamadı veya zaten geri alındı.",
            "Entscheidung nicht gefunden oder bereits zurückgenommen.",
        ),
        "Qeydiyyatın statusu o vaxtdan dəyişib — bərpa olunmur.": t(
            "The enrollment status has changed since then — it cannot be restored.",
            "Статус записи с тех пор изменился — восстановление невозможно.",
            "Kaydın durumu o zamandan beri değişti — geri yüklenemez.",
            "Der Status der Einschreibung hat sich seitdem geändert — keine Wiederherstellung möglich.",
        ),
        "Tələbə bu fənn üzrə başqa jurnalda aktivdir — əvvəlcə oradan çıxarın.": t(
            "The student is active in another journal for this subject — remove them there first.",
            "Студент активен в другом журнале по этому предмету — сначала уберите его оттуда.",
            "Öğrenci bu ders için başka bir defterde aktif — önce oradan çıkarın.",
            "Die Person ist in einem anderen Journal dieses Fachs aktiv — zuerst dort entfernen.",
        ),
        "Tələbəni fəndən azad etmək üçün səlahiyyətiniz yoxdur.": t(
            "You are not allowed to exempt students from a subject.",
            "У вас нет прав освобождать студентов от предмета.",
            "Öğrencileri dersten muaf tutma yetkiniz yok.",
            "Sie dürfen Studierende nicht von einem Fach befreien.",
        ),
        "Tələbə bu fəndən azad edildi — qrupda qalır, digər fənlərə toxunulmadı.": t(
            "The student was exempted from this subject — they stay in the group; other subjects are untouched.",
            "Студент освобождён от этого предмета — остаётся в группе, другие предметы не затронуты.",
            "Öğrenci bu dersten muaf tutuldu — grupta kalır, diğer derslere dokunulmadı.",
            "Die Person wurde von diesem Fach befreit — sie bleibt in der Gruppe, andere Fächer bleiben unberührt.",
        ),
        "Tələbə jurnala qaytarıldı.": t(
            "The student was returned to the journal.",
            "Студент возвращён в журнал.",
            "Öğrenci deftere geri döndürüldü.",
            "Die Person wurde ins Journal zurückgeholt.",
        ),
        "Azad edilənlər": t("Exempted", "Освобождённые", "Muaf tutulanlar", "Befreite"),
        "qrupda qalırlar — yalnız bu fənnin jurnalında görünmürlər": t(
            "they stay in the group — they are only hidden from this subject's journal",
            "остаются в группе — не отображаются только в журнале этого предмета",
            "grupta kalırlar — yalnızca bu dersin defterinde görünmezler",
            "sie bleiben in der Gruppe — nur im Journal dieses Fachs ausgeblendet",
        ),
        "Bərpa et": t("Restore", "Восстановить", "Geri al", "Wiederherstellen"),
        "Əməliyyat alınmadı — yenidən cəhd edin.": t(
            "The action failed — please try again.",
            "Операция не удалась — попробуйте снова.",
            "İşlem başarısız — tekrar deneyin.",
            "Die Aktion ist fehlgeschlagen — bitte erneut versuchen.",
        ),
        "Təsdiq üçün yenidən klikləyin": t(
            "Click again to confirm",
            "Нажмите ещё раз для подтверждения",
            "Onaylamak için tekrar tıklayın",
            "Zum Bestätigen erneut klicken",
        ),
        "Fəndən azad et": t("Exempt from subject", "Освободить от предмета", "Dersten muaf tut", "Vom Fach befreien"),
        "Tələbə qrupda qalır — yalnız bu fənnin jurnalından, imtahan siyahısından və hesablamalarından çıxır. "
        "Digər fənlərə toxunulmur; «Bərpa et» ilə geri qaytarılır.": t(
            "The student stays in the group — they are removed only from this subject's journal, exam list and "
            "calculations. Other subjects are untouched; «Restore» brings them back.",
            "Студент остаётся в группе — он убирается только из журнала, экзаменационного списка и расчётов этого "
            "предмета. Другие предметы не затрагиваются; «Восстановить» возвращает его.",
            "Öğrenci grupta kalır — yalnızca bu dersin defterinden, sınav listesinden ve hesaplamalarından çıkarılır. "
            "Diğer derslere dokunulmaz; «Geri al» ile geri döndürülür.",
            "Die Person bleibt in der Gruppe — sie wird nur aus Journal, Prüfungsliste und Berechnungen dieses Fachs "
            "entfernt. Andere Fächer bleiben unberührt; «Wiederherstellen» holt sie zurück.",
        ),
        "Bağla": t("Close", "Закрыть", "Kapat", "Schließen"),
        "Səbəb": t("Reason", "Причина", "Gerekçe", "Begründung"),
        "(istəyə bağlı)": t("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
        "Sənəd №": t("Document No.", "Документ №", "Belge No.", "Dokument Nr."),
        "Sənəd tarixi": t("Document date", "Дата документа", "Belge tarihi", "Dokumentdatum"),
        "Ləğv et": t("Cancel", "Отмена", "İptal", "Abbrechen"),
        "Fəndən azad et — tələbə qrupda qalır, yalnız bu jurnaldan çıxır": t(
            "Exempt from subject — the student stays in the group and leaves only this journal",
            "Освободить от предмета — студент остаётся в группе и убирается только из этого журнала",
            "Dersten muaf tut — öğrenci grupta kalır, yalnızca bu defterden çıkar",
            "Vom Fach befreien — die Person bleibt in der Gruppe und verlässt nur dieses Journal",
        ),
    },
    SUBJECTS: {
        "Azad edildiyiniz fənlər": t(
            "Subjects you are exempt from",
            "Предметы, от которых вы освобождены",
            "Muaf olduğunuz dersler",
            "Fächer, von denen Sie befreit sind",
        ),
        "Azad edilib": t("Exempt", "Освобождён", "Muaf", "Befreit"),
        "Bu fənlər üzrə jurnal, davamiyyət və imtahan tələbi sizə aid deyil; qrupunuz dəyişmir. Sual yaranarsa "
        "dekanlığa müraciət edin.": t(
            "Journal, attendance and exam requirements for these subjects do not apply to you; your group does not "
            "change. If you have questions, contact the dean's office.",
            "Требования журнала, посещаемости и экзамена по этим предметам к вам не относятся; ваша группа не "
            "меняется. По вопросам обращайтесь в деканат.",
            "Bu dersler için defter, devam ve sınav şartları size uygulanmaz; grubunuz değişmez. Sorularınız için "
            "dekanlığa başvurun.",
            "Journal-, Anwesenheits- und Prüfungsanforderungen dieser Fächer gelten nicht für Sie; Ihre Gruppe "
            "ändert sich nicht. Bei Fragen wenden Sie sich an das Dekanat.",
        ),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


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
            msgstr = translations.get("az", msgid) if lang == "az" else (translations.get(lang) or msgid)
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
