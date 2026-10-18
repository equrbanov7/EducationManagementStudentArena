#!/usr/bin/env python3
"""EMSArena i18n — «İmtahan şansı ver» → «Yenidən imtahan cəhdi» akademik adlandırması (sahib 2026-10-19).

Sahib: «Şans deyil bu, yenidən imtahan cəhdi kimi daha çox akademik dilə uyğun bir formada qoy.»
Terminologiya: bölmə «Yenidən imtahan cəhdi», əməl «Cəhd hüququ ver», səbəb növü «Cəhdin əsası».
İmtahan mərkəzinin pozuntu panelindəki «Şans ver» də «Bərpa et» oldu.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. Şablon `{% trans %}`-dakı literal «%» kataloqda «%%»-dir.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

EXCH = "accounts.exam_chance"
SECTION = "profile.section"
RETAKE = "registrar.retake"
NOTIFY = "exams.second_chance.notification"
PERM = "organizations.permission.label"
RESULTS = "exams.template.teacher_exam_results"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


#: (domain, msgctxt) → {msgid: translations}; msgctxt=None — kontekstsiz gettext.
ENTRIES = {
    ("django", SECTION): {
        "Yenidən imtahan cəhdi": t(
            "Re-examination attempt",
            "Повторная попытка экзамена",
            "Yeniden sınav hakkı",
            "Erneuter Prüfungsversuch",
        ),
    },
    ("django", EXCH): {
        "Cəhd hüququ vermək üçün əvvəlcə aktiv təşkilat seçilməlidir.": t(
            "Select an active organization before granting an attempt.",
            "Чтобы предоставить право на попытку, сначала выберите активную организацию.",
            "Sınav hakkı vermek için önce aktif bir kurum seçilmelidir.",
            "Wählen Sie zuerst eine aktive Organisation, um einen Prüfungsversuch zu gewähren.",
        ),
        "Verilən cəhd hüququ": t(
            "Attempts granted", "Предоставлено попыток", "Verilen sınav hakkı", "Gewährte Versuche"
        ),
        "Cəhdin əsası": t("Grounds for the attempt", "Основание попытки", "Hakkın gerekçesi", "Grundlage des Versuchs"),
        "Əsas seçin…": t("Select grounds…", "Выберите основание…", "Gerekçe seçin…", "Grundlage wählen…"),
        "Əsas": t("Grounds", "Основание", "Gerekçe", "Grundlage"),
        "Yalnız baxış: cəhd hüququnu «İmtahan mərkəzinin qərarları» səlahiyyəti olan istifadəçi "
        "(imtahan mərkəzi rəhbəri) verir.": t(
            "View only: attempts are granted by a user with the “Exam centre decisions” permission "
            "(head of the exam centre).",
            "Только просмотр: право на попытку предоставляет пользователь с полномочием "
            "«Решения экзаменационного центра» (руководитель экзаменационного центра).",
            "Yalnızca görüntüleme: sınav hakkını «Sınav merkezi kararları» yetkisine sahip kullanıcı "
            "(sınav merkezi başkanı) verir.",
            "Nur Ansicht: Versuche gewährt ein Benutzer mit der Berechtigung „Entscheidungen des "
            "Prüfungszentrums“ (Leitung des Prüfungszentrums).",
        ),
        "Son verilən cəhd hüquqları": t(
            "Recently granted attempts",
            "Недавно предоставленные попытки",
            "Son verilen sınav hakları",
            "Zuletzt gewährte Versuche",
        ),
        "Rəsmi qeyd: kim, kimə, hansı imtahan, hansı əsasla və sənədlə. Qeydlər silinmir və dəyişdirilmir.": t(
            "Official record: who, to whom, which exam, on what grounds and with which document. "
            "Records cannot be deleted or changed.",
            "Официальная запись: кто, кому, какой экзамен, на каком основании и по какому документу. "
            "Записи не удаляются и не изменяются.",
            "Resmî kayıt: kim, kime, hangi sınav, hangi gerekçe ve belgeyle. Kayıtlar silinmez ve değiştirilmez.",
            "Offizieller Eintrag: wer, wem, welche Prüfung, auf welcher Grundlage und mit welchem Dokument. "
            "Einträge werden weder gelöscht noch geändert.",
        ),
        "Hələ cəhd hüququ verilməyib.": t(
            "No attempts have been granted yet.",
            "Право на попытку ещё не предоставлялось.",
            "Henüz sınav hakkı verilmedi.",
            "Noch keine Versuche gewährt.",
        ),
        "Cəhd hüququ ver": t("Grant attempt", "Предоставить попытку", "Sınav hakkı ver", "Versuch gewähren"),
        "Əsası seçin, tələbəni axtarıb işarələyin, imtahanı seçin, sənədi və qeydi yazın.": t(
            "Select the grounds, find and tick the student, choose the exam, then enter the document and note.",
            "Выберите основание, найдите и отметьте студента, выберите экзамен, укажите документ и примечание.",
            "Gerekçeyi seçin, öğrenciyi bulup işaretleyin, sınavı seçin, belgeyi ve notu yazın.",
            "Wählen Sie die Grundlage, suchen und markieren Sie die Studierenden, wählen Sie die Prüfung "
            "und tragen Sie Dokument und Notiz ein.",
        ),
        "1-ci addım: yuxarıdakı süzgəcdə «Cəhdin əsası»nı seçin — əsassız cəhd hüququ verilmir.": t(
            "Step 1: choose “Grounds for the attempt” in the filter above — no attempt is granted without grounds.",
            "Шаг 1: выберите «Основание попытки» в фильтре выше — без основания право на попытку не предоставляется.",
            "1. adım: yukarıdaki filtrede «Hakkın gerekçesi»ni seçin — gerekçesiz sınav hakkı verilmez.",
            "Schritt 1: Wählen Sie oben im Filter „Grundlage des Versuchs“ — ohne Grundlage wird kein Versuch "
            "gewährt.",
        ),
        "Sənəd və qeyd": t("Document and note", "Документ и примечание", "Belge ve not", "Dokument und Notiz"),
        "Cəhd hüququ veriləndə: cəhd limiti artır, final/midterm üçün YENİ fərdi PIN yaradılır, finalın köhnə "
        "giriş bileti sıfırlanır və imtahan «Təyin olunmuş tapşırıqlar»da yenidən görünür. Qərar əsası və "
        "sənədi ilə silinməyən qeydə yazılır və tələbənin 25%% izində görünür.": t(
            "When an attempt is granted: the attempt limit increases, a NEW personal PIN is generated for the "
            "final/midterm, the old final entry ticket is reset and the exam reappears under “Assigned tasks”. "
            "The decision is stored with its grounds and document in a permanent record and appears in the "
            "student's 25%% trail.",
            "При предоставлении попытки: лимит попыток увеличивается, для финала/промежуточного экзамена "
            "создаётся НОВЫЙ личный PIN, старый входной билет финала сбрасывается, и экзамен снова появляется "
            "в «Назначенных заданиях». Решение с основанием и документом записывается в неудаляемый журнал "
            "и отображается в истории 25%% студента.",
            "Sınav hakkı verildiğinde: deneme sınırı artar, final/ara sınav için YENİ kişisel PIN oluşturulur, "
            "finalin eski giriş bileti sıfırlanır ve sınav «Atanan görevler»de yeniden görünür. Karar, "
            "gerekçesi ve belgesiyle silinmeyen kayda yazılır ve öğrencinin %%25 geçmişinde görünür.",
            "Bei Gewährung eines Versuchs: Das Versuchslimit steigt, für Final/Midterm wird eine NEUE persönliche "
            "PIN erzeugt, das alte Final-Zugangsticket wird zurückgesetzt und die Prüfung erscheint wieder unter "
            "„Zugewiesene Aufgaben“. Die Entscheidung wird mit Grundlage und Dokument unlöschbar protokolliert "
            "und erscheint im 25-%%-Verlauf der Studierenden.",
        ),
        "Cəhd hüququ vermək üçün qərar səlahiyyətiniz yoxdur.": t(
            "You do not have the decision permission to grant attempts.",
            "У вас нет полномочия принимать решение о предоставлении попытки.",
            "Sınav hakkı vermek için karar yetkiniz yok.",
            "Sie haben keine Entscheidungsberechtigung, um Versuche zu gewähren.",
        ),
        "Köhnə qeyd (əsas yazılmayıb)": t(
            "Legacy record (no grounds recorded)",
            "Старая запись (основание не указано)",
            "Eski kayıt (gerekçe yazılmamış)",
            "Alter Eintrag (keine Grundlage erfasst)",
        ),
    },
    ("django", RETAKE): {
        "Cəhdin əsasını seçin.": t(
            "Select the grounds for the attempt.",
            "Выберите основание попытки.",
            "Hakkın gerekçesini seçin.",
            "Wählen Sie die Grundlage des Versuchs.",
        ),
        # Python pgettext — «%» literal qalır (python-format deyil).
        "25% müraciəti yalnız yekun (final) imtahan üçün cəhd hüququ verir.": t(
            "A 25% application grants an attempt only for the final exam.",
            "Заявка 25% даёт право на попытку только на итоговом (финальном) экзамене.",
            "%25 başvurusu yalnızca final sınavı için sınav hakkı verir.",
            "Ein 25-%-Antrag gewährt einen Versuch nur für die Abschlussprüfung (Final).",
        ),
        "Bütün müraciətlər, addımlar, qəbzlər, yenidən imtahan cəhdləri və nəticələr.": t(
            "All applications, steps, receipts, re-examination attempts and results.",
            "Все заявки, шаги, квитанции, повторные попытки экзамена и результаты.",
            "Tüm başvurular, adımlar, makbuzlar, yeniden sınav hakları ve sonuçlar.",
            "Alle Anträge, Schritte, Belege, erneuten Prüfungsversuche und Ergebnisse.",
        ),
        "Buraxılışdan sonra İmtahan mərkəzi «Yenidən imtahan cəhdi» bölməsində «25%% müraciəti» əsası ilə "
        "cəhd hüququ verir və ya kağız imtahanın balı yazılır.": t(
            "After admission, the exam centre grants an attempt in the “Re-examination attempt” section on the "
            "grounds of a “25%% application”, or the paper exam score is recorded.",
            "После допуска экзаменационный центр в разделе «Повторная попытка экзамена» предоставляет попытку "
            "по основанию «Заявка 25%%», либо вносится балл бумажного экзамена.",
            "Kabulden sonra Sınav merkezi «Yeniden sınav hakkı» bölümünde «%%25 başvurusu» gerekçesiyle sınav "
            "hakkı verir ya da kâğıt sınavın puanı girilir.",
            "Nach der Zulassung gewährt das Prüfungszentrum im Bereich „Erneuter Prüfungsversuch“ auf Grundlage "
            "eines „25-%%-Antrags“ einen Versuch, oder die Punktzahl der Papierprüfung wird eingetragen.",
        ),
        "Yenidən imtahan cəhdi: «%(title)s» · +%(n)s · %(reason)s · %(when)s": t(
            "Re-examination attempt: “%(title)s” · +%(n)s · %(reason)s · %(when)s",
            "Повторная попытка экзамена: «%(title)s» · +%(n)s · %(reason)s · %(when)s",
            "Yeniden sınav hakkı: «%(title)s» · +%(n)s · %(reason)s · %(when)s",
            "Erneuter Prüfungsversuch: „%(title)s“ · +%(n)s · %(reason)s · %(when)s",
        ),
    },
    ("django", NOTIFY): {
        "Yenidən imtahan cəhdi hüququ verildi": t(
            "Re-examination attempt granted",
            "Предоставлена повторная попытка экзамена",
            "Yeniden sınav hakkı verildi",
            "Erneuter Prüfungsversuch gewährt",
        ),
    },
    ("django", PERM): {
        "İmtahan mərkəzinin qərarları (yenidən imtahan cəhdi, kollokvium pəncərəsi, sual göndərişi)": t(
            "Exam centre decisions (re-examination attempt, colloquium window, question dispatch)",
            "Решения экзаменационного центра (повторная попытка экзамена, окно коллоквиума, отправка вопросов)",
            "Sınav merkezi kararları (yeniden sınav hakkı, kolokyum penceresi, soru gönderimi)",
            "Entscheidungen des Prüfungszentrums (erneuter Prüfungsversuch, Kolloquiumsfenster, Fragenversand)",
        ),
    },
    ("django", RESULTS): {
        "Qrupa yenidən imtahan cəhdi": t(
            "Re-examination attempt for a group",
            "Повторная попытка экзамена для группы",
            "Gruba yeniden sınav hakkı",
            "Erneuter Prüfungsversuch für eine Gruppe",
        ),
    },
    # İmtahan mərkəzi zal monitoru — pozuntu panelindəki «Şans ver» (room_monitor.py + room_aggregate.js).
    ("django", None): {
        "Bərpa et": t("Restore", "Восстановить", "Devam ettir", "Wiederherstellen"),
        "Tələbənin imtahanı bərpa edilsin? Pozuntu sayğacı bir vahid azalacaq.": t(
            "Restore the student's exam? The violation counter will decrease by one.",
            "Восстановить экзамен студента? Счётчик нарушений уменьшится на единицу.",
            "Öğrencinin sınavı devam ettirilsin mi? İhlal sayacı bir azalacak.",
            "Prüfung der/des Studierenden wiederherstellen? Der Verstoßzähler sinkt um eins.",
        ),
    },
    ("djangojs", None): {
        "Bərpa et": t("Restore", "Восстановить", "Devam ettir", "Wiederherstellen"),
        "Tələbənin imtahanı bərpa edilsin? Pozuntu sayğacı bir vahid azalacaq.": t(
            "Restore the student's exam? The violation counter will decrease by one.",
            "Восстановить экзамен студента? Счётчик нарушений уменьшится на единицу.",
            "Öğrencinin sınavı devam ettirilsin mi? İhlal sayacı bir azalacak.",
            "Prüfung der/des Studierenden wiederherstellen? Der Verstoßzähler sinkt um eins.",
        ),
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        print(f"{lang}/{domain}: kataloq yoxdur — keçildi")
        return
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for (entry_domain, ctx), messages in ENTRIES.items():
        if entry_domain != domain:
            continue
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if ("%(" in msgid or "%%" in msgid) else ""
            ctx_line = f'msgctxt "{esc(ctx)}"\n' if ctx is not None else ""
            blocks.append(f'{flags}{ctx_line}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for catalog in ("django", "djangojs"):
            fill(locale, catalog)
