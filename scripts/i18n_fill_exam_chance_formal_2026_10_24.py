#!/usr/bin/env python3
"""EMSArena i18n — midterm/final üçün rəsmi «Yenidən imtahan cəhdi» + məcburi sənəd + ata adı (2026-10-24).

* Nəticələr səhifəsi: midterm/final-da birbaşa «Yenidən şans ver» / «Qrupa yenidən imtahan cəhdi» əvəzinə rəsmi
  səhifəyə keçid (və ya kilid qeydi); birbaşa endpoint-in imtina mesajı.
* «Yenidən imtahan cəhdi»: məcburi əsas sənəd, çiplərdə / cədvəldə ata adı, «Son verilən» sətrindən ön-doldurma.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

EC = "accounts.exam_chance"
TR = "exams.template.teacher_exam_results"
EM = "exams.view.exams.message"
RT = "registrar.retake"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    EM: {
        "Midterm və final imtahanları üçün yenidən cəhd hüququ yalnız «Yenidən imtahan cəhdi» səhifəsində "
        "rəsmi əsasla (əmr, sənəd, qeyd) verilir.": t(
            "For midterm and final exams a re-attempt can only be granted on the “Exam re-attempt” page with an "
            "official basis (order, document, note).",
            "Для промежуточных и итоговых экзаменов повторная попытка предоставляется только на странице "
            "«Повторная попытка экзамена» на официальном основании (приказ, документ, примечание).",
            "Ara sınav ve final sınavları için yeniden deneme hakkı yalnızca “Sınav yeniden denemesi” sayfasında "
            "resmî gerekçeyle (karar, belge, not) verilir.",
            "Für Zwischen- und Abschlussprüfungen wird ein weiterer Versuch nur auf der Seite „Prüfungswiederholung“ "
            "mit offizieller Grundlage (Anordnung, Dokument, Vermerk) gewährt.",
        ),
    },
    RT: {
        "Əsas sənədi (əmr / sərəncam / ərizə) yükləyin — sənədsiz cəhd hüququ verilmir.": t(
            "Upload the supporting document (order / decree / application) — no re-attempt is granted without it.",
            "Загрузите документ-основание (приказ / распоряжение / заявление) — без документа попытка не "
            "предоставляется.",
            "Dayanak belgesini (karar / yönerge / dilekçe) yükleyin — belge olmadan deneme hakkı verilmez.",
            "Laden Sie das Grundlagendokument hoch (Anordnung / Verfügung / Antrag) — ohne Dokument wird kein "
            "weiterer Versuch gewährt.",
        ),
    },
    TR: {
        "Midterm/final: cəhd hüququ rəsmi əsasla (əmr, sənəd, qeyd) «Yenidən imtahan cəhdi» səhifəsində verilir.": t(
            "Midterm/final: a re-attempt is granted with an official basis (order, document, note) on the “Exam "
            "re-attempt” page.",
            "Промежуточный/итоговый: попытка предоставляется на официальном основании (приказ, документ, "
            "примечание) на странице «Повторная попытка экзамена».",
            "Ara sınav/final: deneme hakkı resmî gerekçeyle (karar, belge, not) “Sınav yeniden denemesi” sayfasında "
            "verilir.",
            "Zwischen-/Abschlussprüfung: Ein weiterer Versuch wird mit offizieller Grundlage (Anordnung, Dokument, "
            "Vermerk) auf der Seite „Prüfungswiederholung“ gewährt.",
        ),
        "Midterm/final üçün yenidən cəhd hüququnu yalnız İmtahan Mərkəzi rəsmi əsasla verir.": t(
            "For midterm/final exams only the Exam Centre grants a re-attempt, with an official basis.",
            "Для промежуточных/итоговых экзаменов повторную попытку предоставляет только Экзаменационный центр на "
            "официальном основании.",
            "Ara sınav/final için yeniden deneme hakkını yalnızca Sınav Merkezi resmî gerekçeyle verir.",
            "Für Zwischen-/Abschlussprüfungen gewährt nur das Prüfungszentrum einen weiteren Versuch mit offizieller "
            "Grundlage.",
        ),
        "Midterm/final üçün cəhd hüququ birbaşa verilmir: «Yenidən imtahan cəhdi» səhifəsində əsas, əmr / sərəncam №, "
        "tarix, sənəd və qeyd ilə rəsmi qeyd yazılır.": t(
            "Midterm/final re-attempts are not granted directly: on the “Exam re-attempt” page an official record is "
            "written with the basis, order / decree No., date, document and note.",
            "Для промежуточных/итоговых экзаменов попытка не предоставляется напрямую: на странице «Повторная "
            "попытка экзамена» составляется официальная запись с основанием, № приказа / распоряжения, датой, "
            "документом и примечанием.",
            "Ara sınav/final için deneme hakkı doğrudan verilmez: “Sınav yeniden denemesi” sayfasında gerekçe, karar "
            "/ yönerge no., tarih, belge ve not ile resmî kayıt yazılır.",
            "Bei Zwischen-/Abschlussprüfungen wird kein Versuch direkt gewährt: Auf der Seite „Prüfungswiederholung“ "
            "wird ein offizieller Eintrag mit Grundlage, Anordnungs-/Verfügungs-Nr., Datum, Dokument und Vermerk "
            "angelegt.",
        ),
        "Rəsmi cəhd səhifəsinə keç": t(
            "Go to the official re-attempt page",
            "Перейти на страницу официальной попытки",
            "Resmî deneme sayfasına git",
            "Zur offiziellen Wiederholungsseite",
        ),
        "Midterm/final üçün yenidən cəhd hüququnu yalnız İmtahan Mərkəzi «Yenidən imtahan cəhdi» səhifəsində rəsmi "
        "əsasla (əmr, sənəd, qeyd) verir.": t(
            "For midterm/final exams only the Exam Centre grants a re-attempt, on the “Exam re-attempt” page with an "
            "official basis (order, document, note).",
            "Для промежуточных/итоговых экзаменов повторную попытку предоставляет только Экзаменационный центр на "
            "странице «Повторная попытка экзамена» на официальном основании (приказ, документ, примечание).",
            "Ara sınav/final için yeniden deneme hakkını yalnızca Sınav Merkezi “Sınav yeniden denemesi” sayfasında "
            "resmî gerekçeyle (karar, belge, not) verir.",
            "Für Zwischen-/Abschlussprüfungen gewährt nur das Prüfungszentrum auf der Seite „Prüfungswiederholung“ "
            "einen weiteren Versuch mit offizieller Grundlage (Anordnung, Dokument, Vermerk).",
        ),
    },
    EC: {
        "Sənəd": t("Document", "Документ", "Belge", "Dokument"),
        "Ata adı": t("Patronymic", "Отчество", "Baba adı", "Vatersname"),
        "Bu tələbə və imtahan üçün «Cəhd hüququ ver» formasını doldur": t(
            "Fill in the “Grant a re-attempt” form for this student and exam",
            "Заполнить форму «Предоставить попытку» для этого студента и экзамена",
            "Bu öğrenci ve sınav için “Deneme hakkı ver” formunu doldur",
            "Formular „Versuch gewähren“ für diese:n Studierende:n und Prüfung ausfüllen",
        ),
        "Sətrə klikləyin — həmin tələbə və imtahan üçün «Cəhd hüququ ver» forması doldurulur.": t(
            "Click a row to fill in the “Grant a re-attempt” form for that student and exam.",
            "Нажмите на строку — форма «Предоставить попытку» заполнится для этого студента и экзамена.",
            "Satıra tıklayın — o öğrenci ve sınav için “Deneme hakkı ver” formu doldurulur.",
            "Klicken Sie auf eine Zeile — das Formular „Versuch gewähren“ wird für diese:n Studierende:n und Prüfung "
            "ausgefüllt.",
        ),
        "Əmr / sərəncam, ərizə və ya qərarın surəti — PDF, JPG və ya PNG, ən çox 10 MB. Sənədsiz cəhd hüququ "
        "verilmir.": t(
            "A copy of the order / decree, application or decision — PDF, JPG or PNG, up to 10 MB. No re-attempt is "
            "granted without a document.",
            "Копия приказа / распоряжения, заявления или решения — PDF, JPG или PNG, не более 10 МБ. Без документа "
            "попытка не предоставляется.",
            "Karar / yönerge, dilekçe veya kararın kopyası — PDF, JPG ya da PNG, en fazla 10 MB. Belge olmadan "
            "deneme hakkı verilmez.",
            "Kopie der Anordnung / Verfügung, des Antrags oder der Entscheidung — PDF, JPG oder PNG, höchstens "
            "10 MB. Ohne Dokument wird kein weiterer Versuch gewährt.",
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
