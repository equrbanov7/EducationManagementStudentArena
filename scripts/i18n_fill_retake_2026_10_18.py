#!/usr/bin/env python3
"""EMSArena i18n — «25% təkrar imtahan və alt qrup» müraciəti + «İmtahan şansı ver» rəsmi səbəbi (2026-10-18).

msgid AZ cümlədir → az msgstr = msgid (model meta adları ingiliscə msgid-dir — az ayrıca verilir).
Şablon sətirlərində faiz işarəsi ``%%`` kimi saxlanılır (Django ``trans`` / ``blocktrans`` müqaviləsi);
Python ``pgettext`` sətirlərində tək ``%``. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RT = "registrar.retake"
RN = "registrar.retake.notification"
EC = "accounts.exam_chance"
RS = "core.runtime_settings"
SB = "profile.sidebar"


def t(en, ru, tr, de, az=None):
    row = {"en": en, "ru": ru, "tr": tr, "de": de}
    if az is not None:
        row["az"] = az
    return row


ENTRIES = {
    "registrar.model.retake.meta": {
        "retake application": t(
            "retake application",
            "заявка на пересдачу",
            "bütünleme başvurusu",
            "Wiederholungsantrag",
            az="25% / alt qrup müraciəti",
        ),
        "retake applications": t(
            "retake applications",
            "заявки на пересдачу",
            "bütünleme başvuruları",
            "Wiederholungsanträge",
            az="25% / alt qrup müraciətləri",
        ),
    },
    "registrar.model.retake_event.meta": {
        "retake application event": t(
            "retake application event",
            "событие заявки на пересдачу",
            "bütünleme başvurusu olayı",
            "Ereignis des Wiederholungsantrags",
            az="müraciət addımı",
        ),
        "retake application events": t(
            "retake application events",
            "события заявок на пересдачу",
            "bütünleme başvurusu olayları",
            "Ereignisse der Wiederholungsanträge",
            az="müraciət addımları",
        ),
    },
    "registrar.model.retake_receipt.meta": {
        "retake payment receipt": t(
            "retake payment receipt",
            "квитанция об оплате пересдачи",
            "bütünleme ödeme makbuzu",
            "Zahlungsbeleg für die Wiederholung",
            az="25% ödəniş qəbzi",
        ),
        "retake payment receipts": t(
            "retake payment receipts",
            "квитанции об оплате пересдачи",
            "bütünleme ödeme makbuzları",
            "Zahlungsbelege für die Wiederholung",
            az="25% ödəniş qəbzləri",
        ),
    },
    "registrar.model.exam_chance_grant.meta": {
        "exam chance grant": t(
            "exam chance grant",
            "предоставление попытки экзамена",
            "sınav hakkı tanıma",
            "Gewährte Prüfungschance",
            az="imtahan şansı qeydi",
        ),
        "exam chance grants": t(
            "exam chance grants",
            "предоставления попыток экзамена",
            "sınav hakkı tanımaları",
            "Gewährte Prüfungschancen",
            az="imtahan şansı qeydləri",
        ),
    },
    SB: {
        "25% və alt qrup": t("25% and subgroup", "25% и подгруппа", "%25 ve alt grup", "25 % und Untergruppe"),
        "25% müraciətləri": t("25% applications", "Заявки на 25%", "%25 başvuruları", "25-%-Anträge"),
        "25%% və alt qrup": t("25%% and subgroup", "25%% и подгруппа", "%%25 ve alt grup", "25 %% und Untergruppe"),
        "25%% müraciətləri": t("25%% applications", "Заявки на 25%%", "%%25 başvuruları", "25-%%-Anträge"),
    },
    RS: {
        "25% təkrar imtahan və alt qrup": t(
            "25% re-exam and subgroup",
            "Пересдача 25% и подгруппа",
            "%25 bütünleme ve alt grup",
            "25-%-Wiederholungsprüfung und Untergruppe",
        ),
        "Müraciət pəncərəsi açıqdır": t(
            "Application window is open", "Приём заявок открыт", "Başvuru dönemi açık", "Antragsfenster ist geöffnet"
        ),
        "Açıq olanda tələbə kəsr fənlər üzrə 25% təkrar imtahan və ya alt qrup müraciəti göndərə bilir. Bağlananda yeni müraciət qəbul olunmur; artıq göndərilmiş müraciətlərə baxış və qərarlar davam edir.": t(
            "When open, students can apply for a 25% re-exam or a subgroup for failed subjects. When closed, no new applications are accepted; submitted applications are still reviewed and decided.",
            "Когда приём открыт, студент может подать заявку на пересдачу 25% или в подгруппу по несданным предметам. Когда закрыт, новые заявки не принимаются; поданные заявки по-прежнему рассматриваются.",
            "Açık olduğunda öğrenci başarısız dersler için %25 bütünleme veya alt grup başvurusu yapabilir. Kapalıyken yeni başvuru alınmaz; gönderilmiş başvuruların incelenmesi ve kararlar sürer.",
            "Wenn geöffnet, können Studierende für nicht bestandene Fächer eine 25-%-Wiederholungsprüfung oder eine Untergruppe beantragen. Wenn geschlossen, werden keine neuen Anträge angenommen; eingereichte Anträge werden weiter geprüft und entschieden.",
        ),
        "Bir fənn üzrə 25% cəhd sayı": t(
            "25% attempts per subject",
            "Число попыток 25% по предмету",
            "Ders başına %25 deneme sayısı",
            "25-%-Versuche pro Fach",
        ),
        "Bir fənn üzrə tələbəyə ən çox neçə dəfə 25% təkrar imtahan verilir (buraxılmış, cəhdi verilmiş və tamamlanmış müraciətlər sayılır). Limit dolanda yalnız alt qrup yolu qalır.": t(
            "The maximum number of 25% re-exams a student may take per subject (admitted, granted and completed applications count). Once the limit is reached only the subgroup route remains.",
            "Сколько раз максимум студент может сдавать пересдачу 25% по одному предмету (учитываются допущенные, с выданной попыткой и завершённые заявки). После исчерпания лимита остаётся только подгруппа.",
            "Bir ders için öğrenciye en fazla kaç kez %25 bütünleme verilir (kabul edilmiş, hakkı tanınmış ve tamamlanmış başvurular sayılır). Sınır dolunca yalnızca alt grup yolu kalır.",
            "Wie oft ein Studierender pro Fach höchstens die 25-%-Wiederholungsprüfung ablegen darf (zugelassene, gewährte und abgeschlossene Anträge zählen). Ist das Limit erreicht, bleibt nur der Weg über die Untergruppe.",
        ),
    },
    RN: {
        "Müraciətiniz qəbul edildi": t(
            "Your application has been received",
            "Ваша заявка принята",
            "Başvurunuz alındı",
            "Ihr Antrag ist eingegangen",
        ),
        "Qəbz yoxlamaya göndərildi": t(
            "Receipt sent for review",
            "Квитанция отправлена на проверку",
            "Makbuz incelemeye gönderildi",
            "Beleg zur Prüfung gesendet",
        ),
        "Ödəniş qəbzi rədd edildi": t(
            "Payment receipt rejected",
            "Квитанция об оплате отклонена",
            "Ödeme makbuzu reddedildi",
            "Zahlungsbeleg abgelehnt",
        ),
        "Ödənişiniz təsdiqləndi": t(
            "Your payment has been verified",
            "Ваша оплата подтверждена",
            "Ödemeniz onaylandı",
            "Ihre Zahlung wurde bestätigt",
        ),
        "Təkrar imtahan cəhdi açıldı": t(
            "Re-exam attempt opened",
            "Открыта попытка пересдачи",
            "Bütünleme sınav hakkı açıldı",
            "Wiederholungsversuch freigeschaltet",
        ),
        "Müraciətiniz rədd edildi": t(
            "Your application was rejected",
            "Ваша заявка отклонена",
            "Başvurunuz reddedildi",
            "Ihr Antrag wurde abgelehnt",
        ),
        "Müraciət geri götürüldü": t(
            "Application withdrawn", "Заявка отозвана", "Başvuru geri çekildi", "Antrag zurückgezogen"
        ),
        "Müraciətinizin vəziyyəti dəyişdi": t(
            "Your application status changed",
            "Статус вашей заявки изменился",
            "Başvurunuzun durumu değişti",
            "Der Status Ihres Antrags hat sich geändert",
        ),
        "Alt qrup müraciətiniz təsdiqləndi": t(
            "Your subgroup application was approved",
            "Ваша заявка в подгруппу одобрена",
            "Alt grup başvurunuz onaylandı",
            "Ihr Untergruppenantrag wurde genehmigt",
        ),
        "25% təkrar imtahana buraxıldınız": t(
            "You have been admitted to the 25% re-exam",
            "Вы допущены к пересдаче 25%",
            "%25 bütünleme sınavına kabul edildiniz",
            "Sie sind zur 25-%-Wiederholungsprüfung zugelassen",
        ),
        "Alt qrupa yerləşdirildiniz": t(
            "You have been placed in a subgroup",
            "Вы зачислены в подгруппу",
            "Alt gruba yerleştirildiniz",
            "Sie wurden einer Untergruppe zugewiesen",
        ),
        "25% təkrar imtahanın nəticəsi yazıldı": t(
            "Your 25% re-exam result has been recorded",
            "Результат пересдачи 25% внесён",
            "%25 bütünleme sınavının sonucu girildi",
            "Das Ergebnis der 25-%-Wiederholungsprüfung wurde erfasst",
        ),
        '"{subject}" — {kind}: {status}.': t(
            '"{subject}" — {kind}: {status}.',
            "«{subject}» — {kind}: {status}.",
            "«{subject}» — {kind}: {status}.",
            "„{subject}“ — {kind}: {status}.",
        ),
        "Bal: {score}.": t("Score: {score}.", "Балл: {score}.", "Puan: {score}.", "Punkte: {score}."),
        "Yeni 25% / alt qrup müraciəti növbədədir": t(
            "A new 25% / subgroup application is in the queue",
            "В очереди новая заявка на 25% / подгруппу",
            "Sırada yeni bir %25 / alt grup başvurusu var",
            "Ein neuer 25-%-/Untergruppenantrag wartet",
        ),
        '{student} — "{subject}": {status}.': t(
            '{student} — "{subject}": {status}.',
            "{student} — «{subject}»: {status}.",
            "{student} — «{subject}»: {status}.",
            "{student} — „{subject}“: {status}.",
        ),
    },
    EC: {
        "Köhnə qeyd (səbəb yazılmayıb)": t(
            "Legacy record (no reason recorded)",
            "Старая запись (причина не указана)",
            "Eski kayıt (gerekçe yazılmamış)",
            "Alter Eintrag (kein Grund erfasst)",
        ),
        "Səbəbi seçin, tələbəni axtarıb işarələyin, imtahanı seçin və əsası yazın.": t(
            "Choose the reason, find and tick the student, pick the exam and record the basis.",
            "Выберите причину, найдите и отметьте студента, выберите экзамен и укажите основание.",
            "Gerekçeyi seçin, öğrenciyi arayıp işaretleyin, sınavı seçin ve dayanağı yazın.",
            "Grund wählen, Studierende suchen und markieren, Prüfung wählen und Grundlage eintragen.",
        ),
        "1-ci addım: yuxarıdakı süzgəcdə «Şansın səbəbi»ni seçin — səbəbsiz şans verilmir.": t(
            "Step 1: choose the “Reason for the chance” in the filter above — no chance is granted without a reason.",
            "Шаг 1: выберите «Причину попытки» в фильтре выше — без причины попытка не выдаётся.",
            "1. adım: yukarıdaki filtrede «Hakkın gerekçesi»ni seçin — gerekçesiz hak tanınmaz.",
            "Schritt 1: Oben im Filter den „Grund der Chance“ wählen — ohne Grund wird keine Chance gewährt.",
        ),
        "Yuxarıdakı «Tələbə axtarışı» sahəsinə ad, istifadəçi adı və ya qrup yazın.": t(
            "Type a name, username or group in the “Student search” field above.",
            "Введите имя, логин или группу в поле «Поиск студента» выше.",
            "Yukarıdaki «Öğrenci arama» alanına ad, kullanıcı adı veya grup yazın.",
            "Namen, Benutzernamen oder Gruppe oben im Feld „Studierendensuche“ eingeben.",
        ),
        "25%% müraciəti yoxdur (ödəniş təsdiqlənib + buraxılıb)": t(
            "No 25%% application (payment verified + admitted)",
            "Нет заявки на 25%% (оплата подтверждена + допущен)",
            "%%25 başvurusu yok (ödeme onaylı + kabul edilmiş)",
            "Kein 25-%%-Antrag (Zahlung bestätigt + zugelassen)",
        ),
        "Yalnız final imtahanları; seçilmiş tələbənin 25%% müraciəti olan fənnə görə süzülür.": t(
            "Final exams only; filtered to the subjects of the selected student's 25%% applications.",
            "Только итоговые экзамены; отфильтровано по предметам заявок 25%% выбранного студента.",
            "Yalnızca final sınavları; seçilen öğrencinin %%25 başvurusu olan derslere göre süzülür.",
            "Nur Abschlussprüfungen; gefiltert nach den Fächern der 25-%%-Anträge des gewählten Studierenden.",
        ),
        "Əsas": t("Basis", "Основание", "Dayanak", "Grundlage"),
        "Əmr / sərəncam №": t(
            "Order / decree no.", "№ приказа / распоряжения", "Emir / karar no.", "Anordnung / Verfügung Nr."
        ),
        "Əmr tarixi": t("Order date", "Дата приказа", "Emir tarihi", "Datum der Anordnung"),
        "Apellyasiya qərarının №": t(
            "Appeal decision no.", "№ решения по апелляции", "İtiraz kararı no.", "Nr. der Widerspruchsentscheidung"
        ),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Nə baş verib, kim qərar verib…": t(
            "What happened, who decided…",
            "Что произошло, кто принял решение…",
            "Ne oldu, kim karar verdi…",
            "Was ist passiert, wer hat entschieden…",
        ),
        "Şans veriləndə: cəhd limiti artır, final/midterm üçün YENİ fərdi PIN yaradılır, finalın köhnə giriş bileti sıfırlanır və imtahan «Təyin olunmuş tapşırıqlar»da yenidən görünür. Qərar səbəbi və əsası ilə silinməyən qeydə yazılır və tələbənin 25%% izində görünür.": t(
            "When granted: the attempt limit grows, a NEW personal PIN is created for final/midterm exams, the old final entry ticket is reset and the exam reappears under “Assigned tasks”. The decision is written to a permanent record with its reason and basis and shows in the student's 25%% trail.",
            "При выдаче: лимит попыток увеличивается, для итогового/промежуточного экзамена создаётся НОВЫЙ личный PIN, старый входной билет итогового экзамена сбрасывается, и экзамен снова появляется в «Назначенных заданиях». Решение с причиной и основанием записывается в неудаляемую запись и видно в истории 25%% студента.",
            "Hak tanındığında: deneme sınırı artar, final/vize için YENİ kişisel PIN oluşturulur, finalin eski giriş bileti sıfırlanır ve sınav «Atanmış görevler»de yeniden görünür. Karar gerekçesi ve dayanağıyla silinmeyen bir kayda yazılır ve öğrencinin %%25 geçmişinde görünür.",
            "Bei Gewährung: das Versuchslimit steigt, für Abschluss-/Zwischenprüfungen wird eine NEUE persönliche PIN erzeugt, das alte Zutrittsticket der Abschlussprüfung wird zurückgesetzt und die Prüfung erscheint wieder unter „Zugewiesene Aufgaben“. Die Entscheidung wird mit Grund und Grundlage in einem unlöschbaren Eintrag gespeichert und ist im 25-%%-Verlauf des Studierenden sichtbar.",
        ),
        "Təsdiqlə və şans ver": t(
            "Confirm and grant", "Подтвердить и выдать попытку", "Onayla ve hak tanı", "Bestätigen und gewähren"
        ),
        "Seçilmiş final/midterm imtahanı üzrə konkret tələbəyə rəsmi səbəblə yenidən cəhd hüququ verin (test, yazılı və praktiki imtahanlar üçün eynidir). Sistem yeni giriş PIN-i yaradır, finalın köhnə girişini yenidən açır, imtahan tələbənin təyin olunmuş tapşırıqlarında yenidən görünür və qərar silinməyən qeydə düşür.": t(
            "Grant a specific student a new attempt at the selected final/midterm exam with an official reason (the same for test, written and practical exams). The system creates a new entry PIN, reopens the final's old entry, the exam reappears in the student's assigned tasks and the decision is kept in a permanent record.",
            "Выдайте конкретному студенту новую попытку по выбранному итоговому/промежуточному экзамену с официальной причиной (одинаково для тестовых, письменных и практических экзаменов). Система создаёт новый PIN, повторно открывает вход на итоговый экзамен, экзамен снова появляется в назначенных заданиях студента, а решение сохраняется в неудаляемой записи.",
            "Seçilen final/vize sınavı için belirli bir öğrenciye resmî gerekçeyle yeniden deneme hakkı verin (test, yazılı ve uygulamalı sınavlar için aynıdır). Sistem yeni giriş PIN'i oluşturur, finalin eski girişini yeniden açar, sınav öğrencinin atanmış görevlerinde yeniden görünür ve karar silinmeyen bir kayda düşer.",
            "Gewähren Sie einem bestimmten Studierenden mit offiziellem Grund einen neuen Versuch für die gewählte Abschluss-/Zwischenprüfung (gleich für Test-, schriftliche und praktische Prüfungen). Das System erzeugt eine neue Zutritts-PIN, öffnet den alten Zutritt zur Abschlussprüfung erneut, die Prüfung erscheint wieder in den zugewiesenen Aufgaben und die Entscheidung bleibt in einem unlöschbaren Eintrag.",
        ),
        "Şansın səbəbi": t("Reason for the chance", "Причина попытки", "Hakkın gerekçesi", "Grund der Chance"),
        "Səbəb seçin…": t("Choose a reason…", "Выберите причину…", "Gerekçe seçin…", "Grund wählen…"),
        "Rəsmi qeyd: kim, kimə, hansı imtahan, hansı səbəb və əsasla. Qeydlər silinmir və dəyişdirilmir.": t(
            "Official record: who granted it to whom, for which exam, with which reason and basis. Records are never deleted or changed.",
            "Официальная запись: кто, кому, по какому экзамену, по какой причине и на каком основании. Записи не удаляются и не изменяются.",
            "Resmî kayıt: kim, kime, hangi sınav, hangi gerekçe ve dayanakla. Kayıtlar silinmez ve değiştirilmez.",
            "Offizieller Eintrag: wer wem für welche Prüfung mit welchem Grund und welcher Grundlage. Einträge werden nie gelöscht oder geändert.",
        ),
        "Səbəb": t("Reason", "Причина", "Gerekçe", "Grund"),
    },
}

# ── registrar.retake (Python + şablon) ──────────────────────────────────────
ENTRIES[RT] = {
    # status / növ / mənbə / hadisə / rol
    "25% təkrar imtahan": t("25% re-exam", "Пересдача 25%", "%25 bütünleme", "25-%-Wiederholungsprüfung"),
    "Alt qrupda yenidən keçmək": t(
        "Retake in a subgroup",
        "Повторное изучение в подгруппе",
        "Alt grupta yeniden almak",
        "In einer Untergruppe wiederholen",
    ),
    "Göndərilib": t("Submitted", "Подана", "Gönderildi", "Eingereicht"),
    "Ödəniş yoxlanılır": t("Payment under review", "Оплата проверяется", "Ödeme inceleniyor", "Zahlung wird geprüft"),
    "Qəbz rədd edilib": t("Receipt rejected", "Квитанция отклонена", "Makbuz reddedildi", "Beleg abgelehnt"),
    "Ödəniş təsdiqlənib": t("Payment verified", "Оплата подтверждена", "Ödeme onaylandı", "Zahlung bestätigt"),
    "Buraxılıb": t("Admitted", "Допущен", "Kabul edildi", "Zugelassen"),
    "İmtahan cəhdi verilib": t(
        "Exam attempt granted", "Попытка экзамена выдана", "Sınav hakkı tanındı", "Prüfungsversuch gewährt"
    ),
    "Tamamlanıb": t("Completed", "Завершена", "Tamamlandı", "Abgeschlossen"),
    "Rədd edilib": t("Rejected", "Отклонена", "Reddedildi", "Abgelehnt"),
    "Geri götürülüb": t("Withdrawn", "Отозвана", "Geri çekildi", "Zurückgezogen"),
    "Dekanlıq daxil edib": t(
        "Entered by the dean's office", "Внесено деканатом", "Dekanlık girdi", "Vom Dekanat eingetragen"
    ),
    "İmtahan balından": t("From the exam score", "Из балла экзамена", "Sınav puanından", "Aus der Prüfungsnote"),
    "Müraciət göndərildi": t("Application submitted", "Заявка подана", "Başvuru gönderildi", "Antrag eingereicht"),
    "Qəbz yükləndi": t("Receipt uploaded", "Квитанция загружена", "Makbuz yüklendi", "Beleg hochgeladen"),
    "Ödəniş təsdiqləndi": t("Payment verified", "Оплата подтверждена", "Ödeme onaylandı", "Zahlung bestätigt"),
    "Qəbz rədd edildi": t("Receipt rejected", "Квитанция отклонена", "Makbuz reddedildi", "Beleg abgelehnt"),
    "İmtahana buraxıldı": t(
        "Admitted to the exam", "Допущен к экзамену", "Sınava kabul edildi", "Zur Prüfung zugelassen"
    ),
    "Alt qrup təsdiqləndi": t("Subgroup approved", "Подгруппа одобрена", "Alt grup onaylandı", "Untergruppe genehmigt"),
    "Alt qrupa yerləşdirildi": t(
        "Placed in a subgroup", "Зачислен в подгруппу", "Alt gruba yerleştirildi", "Einer Untergruppe zugewiesen"
    ),
    "Rədd edildi": t("Rejected", "Отклонено", "Reddedildi", "Abgelehnt"),
    "İmtahan cəhdi verildi": t(
        "Exam attempt granted", "Выдана попытка экзамена", "Sınav hakkı tanındı", "Prüfungsversuch gewährt"
    ),
    "Nəticə yazıldı": t("Result recorded", "Результат внесён", "Sonuç girildi", "Ergebnis erfasst"),
    "Geri götürüldü": t("Withdrawn", "Отозвано", "Geri çekildi", "Zurückgezogen"),
    "Tələbə": t("Student", "Студент", "Öğrenci", "Studierende/r"),
    "Mühasibatlıq": t("Accounting", "Бухгалтерия", "Muhasebe", "Buchhaltung"),
    "Dekanlıq / tədris şöbəsi": t(
        "Dean's office / academic office",
        "Деканат / учебный отдел",
        "Dekanlık / öğrenci işleri",
        "Dekanat / Studienbüro",
    ),
    "İmtahan mərkəzi": t("Exam centre", "Экзаменационный центр", "Sınav merkezi", "Prüfungszentrum"),
    "Sistem": t("System", "Система", "Sistem (otomatik)", "System"),
    "25% müraciəti": t("25% application", "Заявка на 25%", "%25 başvurusu", "25-%-Antrag"),
    "Universitet güzəşti": t(
        "University concession", "Уступка университета", "Üniversite muafiyeti", "Entgegenkommen der Universität"
    ),
    "Texniki problem": t("Technical problem", "Техническая проблема", "Teknik sorun", "Technisches Problem"),
    "Apellyasiya qərarı": t("Appeal decision", "Решение по апелляции", "İtiraz kararı", "Widerspruchsentscheidung"),
    "Digər": t("Other", "Другое", "Diğer", "Sonstiges"),
    # növbəti addım / qaydalar
    "Ödəniş qəbzini yükləyin — Mühasibatlıq yalnız qəbzdən sonra yoxlayır.": t(
        "Upload the payment receipt — Accounting reviews only after a receipt is uploaded.",
        "Загрузите квитанцию об оплате — бухгалтерия проверяет только после загрузки квитанции.",
        "Ödeme makbuzunu yükleyin — Muhasebe yalnızca makbuzdan sonra inceler.",
        "Laden Sie den Zahlungsbeleg hoch — die Buchhaltung prüft erst nach dem Hochladen.",
    ),
    "Qəbziniz Mühasibatlıqda yoxlanılır.": t(
        "Your receipt is being reviewed by Accounting.",
        "Ваша квитанция проверяется бухгалтерией.",
        "Makbuzunuz Muhasebe tarafından inceleniyor.",
        "Ihr Beleg wird von der Buchhaltung geprüft.",
    ),
    "Qəbz rədd edilib — səbəbi oxuyun və düzgün qəbzi yenidən yükləyin.": t(
        "The receipt was rejected — read the reason and upload the correct receipt.",
        "Квитанция отклонена — прочитайте причину и загрузите правильную квитанцию.",
        "Makbuz reddedildi — gerekçeyi okuyun ve doğru makbuzu yeniden yükleyin.",
        "Der Beleg wurde abgelehnt — lesen Sie den Grund und laden Sie den richtigen Beleg hoch.",
    ),
    "Ödəniş təsdiqlənib — dekanlığın buraxılış qərarı gözlənilir.": t(
        "Payment verified — waiting for the dean's office admission decision.",
        "Оплата подтверждена — ожидается решение деканата о допуске.",
        "Ödeme onaylandı — dekanlığın kabul kararı bekleniyor.",
        "Zahlung bestätigt — die Zulassungsentscheidung des Dekanats steht aus.",
    ),
    "İmtahana buraxılmısınız — imtahan vaxtı İmtahan mərkəzi tərəfindən bildiriləcək.": t(
        "You are admitted — the exam centre will announce the exam time.",
        "Вы допущены — время экзамена сообщит экзаменационный центр.",
        "Sınava kabul edildiniz — sınav zamanını Sınav merkezi bildirecek.",
        "Sie sind zugelassen — das Prüfungszentrum teilt den Prüfungstermin mit.",
    ),
    "İmtahan cəhdi açılıb — imtahan «Təyin olunmuş tapşırıqlar»da görünür.": t(
        "Exam attempt opened — the exam appears under “Assigned tasks”.",
        "Попытка открыта — экзамен появился в «Назначенных заданиях».",
        "Sınav hakkı açıldı — sınav «Atanmış görevler»de görünür.",
        "Prüfungsversuch freigeschaltet — die Prüfung erscheint unter „Zugewiesene Aufgaben“.",
    ),
    "Müraciətiniz dekanlıqdadır — alt qrup qərarı gözlənilir.": t(
        "Your application is with the dean's office — waiting for the subgroup decision.",
        "Ваша заявка в деканате — ожидается решение о подгруппе.",
        "Başvurunuz dekanlıkta — alt grup kararı bekleniyor.",
        "Ihr Antrag liegt beim Dekanat — die Entscheidung über die Untergruppe steht aus.",
    ),
    "Alt qrup təsdiqlənib — yerləşdirmə gözlənilir.": t(
        "Subgroup approved — placement pending.",
        "Подгруппа одобрена — ожидается зачисление.",
        "Alt grup onaylandı — yerleştirme bekleniyor.",
        "Untergruppe genehmigt — Zuweisung ausstehend.",
    ),
    "Bu addım müraciətin cari vəziyyətində mümkün deyil ({current} → {target}).": t(
        "This step is not possible in the application's current state ({current} → {target}).",
        "Этот шаг невозможен в текущем состоянии заявки ({current} → {target}).",
        "Bu adım başvurunun mevcut durumunda mümkün değil ({current} → {target}).",
        "Dieser Schritt ist im aktuellen Antragsstatus nicht möglich ({current} → {target}).",
    ),
    "Səbəb ən azı {n} simvol olmalıdır — qərar zəncirində görünəcək.": t(
        "The reason must be at least {n} characters — it is shown in the decision chain.",
        "Причина должна содержать не менее {n} символов — она видна в цепочке решений.",
        "Gerekçe en az {n} karakter olmalıdır — karar zincirinde görünecek.",
        "Der Grund muss mindestens {n} Zeichen lang sein — er erscheint in der Entscheidungskette.",
    ),
    "Müraciət pəncərəsi hazırda bağlıdır.": t(
        "The application window is currently closed.",
        "Приём заявок сейчас закрыт.",
        "Başvuru dönemi şu anda kapalı.",
        "Das Antragsfenster ist derzeit geschlossen.",
    ),
    "Qayıb həddi keçildiyi üçün 25% imtahan mümkün deyil — yalnız alt qrup.": t(
        "The absence limit was exceeded, so a 25% exam is not possible — subgroup only.",
        "Лимит пропусков превышен, пересдача 25% невозможна — только подгруппа.",
        "Devamsızlık sınırı aşıldığı için %25 sınav mümkün değil — yalnızca alt grup.",
        "Die Fehlzeitengrenze wurde überschritten, daher ist keine 25-%-Prüfung möglich — nur Untergruppe.",
    ),
    "Bu fənn üzrə 25% cəhd limiti dolub ({used}/{limit}).": t(
        "The 25% attempt limit for this subject is used up ({used}/{limit}).",
        "Лимит попыток 25% по этому предмету исчерпан ({used}/{limit}).",
        "Bu ders için %25 deneme sınırı doldu ({used}/{limit}).",
        "Das 25-%-Versuchslimit für dieses Fach ist ausgeschöpft ({used}/{limit}).",
    ),
    "Bu fənn üzrə aktiv müraciətiniz var.": t(
        "You already have an active application for this subject.",
        "У вас уже есть активная заявка по этому предмету.",
        "Bu ders için aktif bir başvurunuz var.",
        "Sie haben bereits einen aktiven Antrag für dieses Fach.",
    ),
    "Bu fənn hazırda yenidən keçilir.": t(
        "This subject is currently being retaken.",
        "Этот предмет сейчас изучается повторно.",
        "Bu ders şu anda yeniden alınıyor.",
        "Dieses Fach wird derzeit wiederholt.",
    ),
    "Qayıb həddi keçilib — imtahana buraxılmamısınız": t(
        "Absence limit exceeded — you were not admitted to the exam",
        "Лимит пропусков превышен — вы не допущены к экзамену",
        "Devamsızlık sınırı aşıldı — sınava kabul edilmediniz",
        "Fehlzeitengrenze überschritten — Sie wurden nicht zur Prüfung zugelassen",
    ),
    "İmtahandan keçid balı toplanmayıb": t(
        "The pass mark was not reached in the exam",
        "На экзамене не набран проходной балл",
        "Sınavda geçme puanı alınmadı",
        "Die Bestehensgrenze in der Prüfung wurde nicht erreicht",
    ),
    "Yekun bal keçid həddindən aşağıdır": t(
        "The final score is below the pass threshold",
        "Итоговый балл ниже проходного",
        "Final puanı geçme sınırının altında",
        "Die Gesamtnote liegt unter der Bestehensgrenze",
    ),
    # xətalar / mesajlar
    "Fayl seçilməyib.": t("No file selected.", "Файл не выбран.", "Dosya seçilmedi.", "Keine Datei ausgewählt."),
    "Müraciət növü seçilməyib.": t(
        "No application type selected.",
        "Не выбран тип заявки.",
        "Başvuru türü seçilmedi.",
        "Kein Antragstyp ausgewählt.",
    ),
    "Bu fənn üzrə müraciət etmək mümkün deyil — fənn kəsr siyahısında yoxdur.": t(
        "You cannot apply for this subject — it is not in your failed subjects list.",
        "Подать заявку по этому предмету нельзя — его нет в списке несданных.",
        "Bu ders için başvuru yapılamaz — ders başarısız dersler listesinde yok.",
        "Für dieses Fach ist kein Antrag möglich — es steht nicht in der Liste der nicht bestandenen Fächer.",
    ),
    "Alt qrup müraciətinə ödəniş qəbzi tələb olunmur.": t(
        "A subgroup application does not need a payment receipt.",
        "Для заявки в подгруппу квитанция не требуется.",
        "Alt grup başvurusu için ödeme makbuzu gerekmez.",
        "Für einen Untergruppenantrag ist kein Zahlungsbeleg nötig.",
    ),
    "Qəbz yalnız ödəniş yoxlanmazdan əvvəl və ya rəddən sonra yüklənir.": t(
        "A receipt can be uploaded only before the payment is reviewed or after a rejection.",
        "Квитанцию можно загрузить только до проверки оплаты или после отклонения.",
        "Makbuz yalnızca ödeme incelenmeden önce veya retten sonra yüklenebilir.",
        "Ein Beleg kann nur vor der Zahlungsprüfung oder nach einer Ablehnung hochgeladen werden.",
    ),
    "Qərar verilmiş müraciəti geri götürmək olmaz.": t(
        "A decided application cannot be withdrawn.",
        "Заявку, по которой принято решение, отозвать нельзя.",
        "Karar verilmiş başvuru geri çekilemez.",
        "Ein entschiedener Antrag kann nicht zurückgezogen werden.",
    ),
    "Bu fənn üzrə aktiv müraciətiniz artıq var.": t(
        "You already have an active application for this subject.",
        "У вас уже есть активная заявка по этому предмету.",
        "Bu ders için zaten aktif bir başvurunuz var.",
        "Sie haben bereits einen aktiven Antrag für dieses Fach.",
    ),
    "Bu müraciətdə yoxlanacaq qəbz yoxdur.": t(
        "This application has no receipt to review.",
        "В этой заявке нет квитанции для проверки.",
        "Bu başvuruda incelenecek makbuz yok.",
        "Dieser Antrag hat keinen zu prüfenden Beleg.",
    ),
    "Alt qrup müraciəti sənədlə təsdiqlənir.": t(
        "A subgroup application is approved with a document.",
        "Заявка в подгруппу одобряется с документом.",
        "Alt grup başvurusu belgeyle onaylanır.",
        "Ein Untergruppenantrag wird mit einem Dokument genehmigt.",
    ),
    "Buraxılış yalnız ödəniş təsdiqləndikdən sonra mümkündür.": t(
        "Admission is possible only after the payment is verified.",
        "Допуск возможен только после подтверждения оплаты.",
        "Kabul yalnızca ödeme onaylandıktan sonra mümkündür.",
        "Die Zulassung ist erst nach bestätigter Zahlung möglich.",
    ),
    "Bu mərhələdə dekanlıq qərarı verilmir.": t(
        "No dean's office decision is made at this stage.",
        "На этом этапе деканат решение не принимает.",
        "Bu aşamada dekanlık kararı verilmez.",
        "In dieser Phase entscheidet das Dekanat nicht.",
    ),
    "Seçilmiş jurnal bu fənnə aid deyil.": t(
        "The selected journal does not belong to this subject.",
        "Выбранный журнал не относится к этому предмету.",
        "Seçilen yoklama defteri bu derse ait değil.",
        "Das gewählte Kursbuch gehört nicht zu diesem Fach.",
    ),
    "Bu müraciət alt qrup qərarı gözləmir.": t(
        "This application is not awaiting a subgroup decision.",
        "Эта заявка не ожидает решения о подгруппе.",
        "Bu başvuru alt grup kararı beklemiyor.",
        "Dieser Antrag wartet nicht auf eine Untergruppenentscheidung.",
    ),
    "Bu müraciət yerləşdirmə gözləmir.": t(
        "This application is not awaiting placement.",
        "Эта заявка не ожидает зачисления.",
        "Bu başvuru yerleştirme beklemiyor.",
        "Dieser Antrag wartet nicht auf eine Zuweisung.",
    ),
    "Hədəf jurnal seçilməlidir.": t(
        "A target journal must be selected.",
        "Нужно выбрать целевой журнал.",
        "Hedef yoklama defteri seçilmelidir.",
        "Ein Ziel-Kursbuch muss gewählt werden.",
    ),
    "Nəticə yalnız imtahana buraxılmış 25% müraciətinə yazılır.": t(
        "A result can be recorded only for an admitted 25% application.",
        "Результат вносится только для допущенной заявки на 25%.",
        "Sonuç yalnızca kabul edilmiş %25 başvurusuna girilir.",
        "Ein Ergebnis kann nur für einen zugelassenen 25-%-Antrag erfasst werden.",
    ),
    "Alt qrupa yerləşdirmə servisi hələ aktiv deyil — sonra yenidən cəhd edin.": t(
        "The subgroup placement service is not active yet — try again later.",
        "Сервис зачисления в подгруппу ещё не активен — попробуйте позже.",
        "Alt gruba yerleştirme hizmeti henüz aktif değil — daha sonra tekrar deneyin.",
        "Der Dienst für die Untergruppenzuweisung ist noch nicht aktiv — bitte später erneut versuchen.",
    ),
    "Bal rəqəm olmalıdır.": t(
        "The score must be a number.",
        "Балл должен быть числом.",
        "Puan sayı olmalıdır.",
        "Die Punktzahl muss eine Zahl sein.",
    ),
    "Şansın səbəbini seçin.": t(
        "Choose the reason for the chance.",
        "Выберите причину попытки.",
        "Hakkın gerekçesini seçin.",
        "Wählen Sie den Grund der Chance.",
    ),
    "Ən azı bir tələbə seçilməlidir.": t(
        "Select at least one student.",
        "Нужно выбрать хотя бы одного студента.",
        "En az bir öğrenci seçilmelidir.",
        "Mindestens ein/e Studierende/r muss gewählt werden.",
    ),
    "Universitet güzəşti üçün əmr / sərəncam nömrəsi və tarixi məcburidir.": t(
        "A university concession needs an order / decree number and date.",
        "Для уступки университета обязательны номер и дата приказа / распоряжения.",
        "Üniversite muafiyeti için emir / karar numarası ve tarihi zorunludur.",
        "Für ein Entgegenkommen der Universität sind Nummer und Datum der Anordnung / Verfügung Pflicht.",
    ),
    "Əmr tarixi düzgün deyil.": t(
        "The order date is not valid.",
        "Неверная дата приказа.",
        "Emir tarihi geçerli değil.",
        "Das Datum der Anordnung ist ungültig.",
    ),
    "25% müraciəti yalnız yekun (final) imtahan üçün şans verir.": t(
        "A 25% application grants a chance only for the final exam.",
        "Заявка на 25% даёт попытку только по итоговому экзамену.",
        "%25 başvurusu yalnızca final sınavı için hak tanır.",
        "Ein 25-%-Antrag gewährt nur eine Chance für die Abschlussprüfung.",
    ),
    "Bu səbəb üçün qeyd məcburidir (ən azı {n} simvol).": t(
        "A note is required for this reason (at least {n} characters).",
        "Для этой причины примечание обязательно (не менее {n} символов).",
        "Bu gerekçe için not zorunludur (en az {n} karakter).",
        "Für diesen Grund ist eine Notiz Pflicht (mindestens {n} Zeichen).",
    ),
    "Bu fənn üzrə ödənişi təsdiqlənmiş və buraxılmış 25% müraciəti yoxdur: {names}.": t(
        "No payment-verified and admitted 25% application for this subject: {names}.",
        "Нет заявки на 25% с подтверждённой оплатой и допуском по этому предмету: {names}.",
        "Bu ders için ödemesi onaylanmış ve kabul edilmiş %25 başvurusu yok: {names}.",
        "Kein 25-%-Antrag mit bestätigter Zahlung und Zulassung für dieses Fach: {names}.",
    ),
    "Əsas imtahan": t("Main exam", "Основной экзамен", "Ana sınav", "Hauptprüfung"),
    "25%": t("25%", "25%", "%25", "25 %"),
    "Ödəniş №": t("Payment no.", "№ оплаты", "Ödeme no.", "Zahlung Nr."),
    "Bal": t("Score", "Балл", "Puan", "Punkte"),
    "Hamısı": t("All", "Все", "Tümü", "Alle"),
    "Ödəniş yoxlaması": t("Payment review", "Проверка оплаты", "Ödeme incelemesi", "Zahlungsprüfung"),
    "Qəbul və qərar": t(
        "Admission and decisions", "Допуск и решения", "Kabul ve kararlar", "Zulassung und Entscheidungen"
    ),
    "Naməlum əməl.": t("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem.", "Unbekannte Aktion."),
    "Müraciətiniz göndərildi.": t(
        "Your application has been sent.",
        "Ваша заявка отправлена.",
        "Başvurunuz gönderildi.",
        "Ihr Antrag wurde gesendet.",
    ),
    "Qəbz faylını seçin (PDF, JPG və ya PNG).": t(
        "Choose the receipt file (PDF, JPG or PNG).",
        "Выберите файл квитанции (PDF, JPG или PNG).",
        "Makbuz dosyasını seçin (PDF, JPG veya PNG).",
        "Belegdatei wählen (PDF, JPG oder PNG).",
    ),
    "Qəbz yükləndi — Mühasibatlıq yoxlayacaq.": t(
        "Receipt uploaded — Accounting will review it.",
        "Квитанция загружена — бухгалтерия проверит её.",
        "Makbuz yüklendi — Muhasebe inceleyecek.",
        "Beleg hochgeladen — die Buchhaltung prüft ihn.",
    ),
    "Müraciət geri götürüldü.": t(
        "Application withdrawn.", "Заявка отозвана.", "Başvuru geri çekildi.", "Antrag zurückgezogen."
    ),
    "25% imtahanın nəticəsi yazıldı.": t(
        "The 25% exam result was recorded.",
        "Результат экзамена 25% внесён.",
        "%25 sınavının sonucu girildi.",
        "Das Ergebnis der 25-%-Prüfung wurde erfasst.",
    ),
    "Ödəniş təsdiqləndi.": t("Payment verified.", "Оплата подтверждена.", "Ödeme onaylandı.", "Zahlung bestätigt."),
    "Qəbz rədd edildi — tələbəyə bildiriş göndərildi.": t(
        "Receipt rejected — the student has been notified.",
        "Квитанция отклонена — студент уведомлён.",
        "Makbuz reddedildi — öğrenciye bildirim gönderildi.",
        "Beleg abgelehnt — der/die Studierende wurde benachrichtigt.",
    ),
    "Tələbə 25% imtahana buraxıldı.": t(
        "The student was admitted to the 25% exam.",
        "Студент допущен к экзамену 25%.",
        "Öğrenci %25 sınavına kabul edildi.",
        "Der/die Studierende wurde zur 25-%-Prüfung zugelassen.",
    ),
    "Müraciət rədd edildi.": t(
        "Application rejected.", "Заявка отклонена.", "Başvuru reddedildi.", "Antrag abgelehnt."
    ),
    "Sənəd (təqdimat / sərəncam) yüklənməlidir — alt qrup sənədsiz olmur.": t(
        "A document (submission / decree) must be uploaded — no subgroup without a document.",
        "Нужно загрузить документ (представление / распоряжение) — без документа подгруппы нет.",
        "Belge (sunum / karar) yüklenmelidir — belgesiz alt grup olmaz.",
        "Ein Dokument (Vorlage / Verfügung) muss hochgeladen werden — ohne Dokument keine Untergruppe.",
    ),
    "Alt qrup qərarı yazıldı.": t(
        "Subgroup decision recorded.",
        "Решение о подгруппе записано.",
        "Alt grup kararı kaydedildi.",
        "Untergruppenentscheidung erfasst.",
    ),
    "Tələbə alt qrupa yerləşdirildi.": t(
        "The student was placed in the subgroup.",
        "Студент зачислен в подгруппу.",
        "Öğrenci alt gruba yerleştirildi.",
        "Der/die Studierende wurde der Untergruppe zugewiesen.",
    ),
}

# Şablon sətirləri (faiz — %%).
ENTRIES[RT].update(
    {
        "Bal mənfi ola bilməz.": t(
            "The score cannot be negative.",
            "Балл не может быть отрицательным.",
            "Puan negatif olamaz.",
            "Die Punktzahl darf nicht negativ sein.",
        ),
        "Bal bu fənnin imtahan tavanından ({cap}) çox ola bilməz.": t(
            "The score cannot exceed this subject's exam maximum ({cap}).",
            "Балл не может превышать максимум экзамена по предмету ({cap}).",
            "Puan bu dersin sınav üst sınırını ({cap}) aşamaz.",
            "Die Punktzahl darf das Prüfungsmaximum dieses Fachs ({cap}) nicht überschreiten.",
        ),
        "Başqasının adından baxış rejimində dəyişiklik etmək olmaz.": t(
            "Changes are not allowed while viewing as another user.",
            "В режиме просмотра от имени другого пользователя изменения запрещены.",
            "Başka bir kullanıcı adına görüntüleme modunda değişiklik yapılamaz.",
            "Im Modus „Ansicht als anderer Benutzer“ sind keine Änderungen erlaubt.",
        ),
        "Çıxış balı (adətən 0–50) — fənnin imtahan tavanından çox bal qəbul olunmur.": t(
            "Exam (exit) score, usually 0–50 — a score above the subject's exam maximum is not accepted.",
            "Выходной балл (обычно 0–50) — балл выше максимума экзамена по предмету не принимается.",
            "Çıkış puanı (genellikle 0–50) — dersin sınav üst sınırını aşan puan kabul edilmez.",
            "Abschlusspunkte (meist 0–50) — Punkte über dem Prüfungsmaximum des Fachs werden nicht angenommen.",
        ),
        "Ödəniş addımları": t("Payment steps", "Шаги оплаты", "Ödeme adımları", "Zahlungsschritte"),
        "Aktiv təşkilat tapılmadı.": t(
            "No active organisation found.",
            "Активная организация не найдена.",
            "Aktif kurum bulunamadı.",
            "Keine aktive Organisation gefunden.",
        ),
        "Əməl yerinə yetirilmədi — icazənizi yoxlayın və ya səhifəni yeniləyin.": t(
            "The action failed — check your permission or reload the page.",
            "Действие не выполнено — проверьте права или обновите страницу.",
            "İşlem gerçekleştirilemedi — yetkinizi kontrol edin veya sayfayı yenileyin.",
            "Die Aktion ist fehlgeschlagen — prüfen Sie Ihre Berechtigung oder laden Sie die Seite neu.",
        ),
        "Kəsr fənlər üzrə 25%% təkrar imtahana (ödənişlə) və ya alt qrupda fənni yenidən keçməyə buradan müraciət edin. Bir fənn üzrə 25%% cəhd limiti: %(limit)s. Qayıb həddi keçilibsə yalnız alt qrup yolu açıqdır.": t(
            "Apply here for a 25%% re-exam (paid) or to retake a failed subject in a subgroup. 25%% attempt limit per subject: %(limit)s. If the absence limit was exceeded, only the subgroup route is open.",
            "Здесь подаётся заявка на пересдачу 25%% (платно) или на повторное изучение несданного предмета в подгруппе. Лимит попыток 25%% по предмету: %(limit)s. Если лимит пропусков превышен, доступна только подгруппа.",
            "Başarısız dersler için %%25 bütünlemeye (ücretli) veya dersi alt grupta yeniden almaya buradan başvurun. Ders başına %%25 deneme sınırı: %(limit)s. Devamsızlık sınırı aşıldıysa yalnızca alt grup yolu açıktır.",
            "Beantragen Sie hier für nicht bestandene Fächer eine 25-%%-Wiederholungsprüfung (kostenpflichtig) oder die Wiederholung in einer Untergruppe. 25-%%-Versuchslimit pro Fach: %(limit)s. Bei überschrittener Fehlzeitengrenze ist nur die Untergruppe möglich.",
        ),
        "Müraciət pəncərəsi bağlıdır": t(
            "The application window is closed",
            "Приём заявок закрыт",
            "Başvuru dönemi kapalı",
            "Das Antragsfenster ist geschlossen",
        ),
        "Hazırda yeni müraciət qəbul olunmur. Göndərdiyiniz müraciətlərin vəziyyətini aşağıda izləyə bilərsiniz.": t(
            "No new applications are accepted right now. You can follow the status of your submitted applications below.",
            "Сейчас новые заявки не принимаются. Статус поданных заявок можно отслеживать ниже.",
            "Şu anda yeni başvuru alınmıyor. Gönderdiğiniz başvuruların durumunu aşağıda izleyebilirsiniz.",
            "Derzeit werden keine neuen Anträge angenommen. Den Status Ihrer eingereichten Anträge sehen Sie unten.",
        ),
        "Kəsr fənn": t("Failed subjects", "Несданные предметы", "Başarısız ders", "Nicht bestandene Fächer"),
        "Müraciət mümkündür": t("Can apply", "Можно подать", "Başvurulabilir", "Antrag möglich"),
        "Aktiv müraciət": t("Active application", "Активная заявка", "Aktif başvuru", "Aktiver Antrag"),
        "25%% cəhd limiti": t("25%% attempt limit", "Лимит попыток 25%%", "%%25 deneme sınırı", "25-%%-Versuchslimit"),
        "25%% və alt qrup bölmələri": t(
            "25%% and subgroup sections",
            "Разделы 25%% и подгруппы",
            "%%25 ve alt grup bölümleri",
            "Bereiche 25 %% und Untergruppe",
        ),
        "Kəsr fənlər": t("Failed subjects", "Несданные предметы", "Başarısız dersler", "Nicht bestandene Fächer"),
        "Müraciətlərim": t("My applications", "Мои заявки", "Başvurularım", "Meine Anträge"),
        "Cəhd tarixçəsi": t("Attempt history", "История попыток", "Deneme geçmişi", "Versuchsverlauf"),
        "Kəsr fənniniz yoxdur": t(
            "You have no failed subjects",
            "У вас нет несданных предметов",
            "Başarısız dersiniz yok",
            "Sie haben keine nicht bestandenen Fächer",
        ),
        "Bütün fənlərinizi keçmisiniz və ya nəticələr hələ yazılmayıb. Kəsr olan fənn burada avtomatik görünəcək.": t(
            "You have passed all subjects or results are not recorded yet. A failed subject will appear here automatically.",
            "Вы сдали все предметы или результаты ещё не внесены. Несданный предмет появится здесь автоматически.",
            "Tüm derslerinizi geçtiniz veya sonuçlar henüz girilmedi. Başarısız ders burada otomatik görünecek.",
            "Sie haben alle Fächer bestanden oder die Ergebnisse sind noch nicht erfasst. Ein nicht bestandenes Fach erscheint hier automatisch.",
        ),
        "Hələ müraciət yoxdur": t("No applications yet", "Заявок пока нет", "Henüz başvuru yok", "Noch keine Anträge"),
        "«Kəsr fənlər» tabından fənni seçib müraciət edin.": t(
            "Choose a subject in the “Failed subjects” tab and apply.",
            "Выберите предмет во вкладке «Несданные предметы» и подайте заявку.",
            "«Başarısız dersler» sekmesinden dersi seçip başvurun.",
            "Wählen Sie im Reiter „Nicht bestandene Fächer“ ein Fach und stellen Sie einen Antrag.",
        ),
        "Müraciət": t("Application", "Заявка", "Başvuru", "Antrag"),
        "Göndər": t("Send", "Отправить", "Gönder", "Senden"),
        "Müraciəti geri götür": t(
            "Withdraw application", "Отозвать заявку", "Başvuruyu geri çek", "Antrag zurückziehen"
        ),
        "Geri götür": t("Withdraw", "Отозвать", "Geri çek", "Zurückziehen"),
        "İmtahan balı": t("Exam score", "Балл экзамена", "Sınav puanı", "Prüfungspunkte"),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Bank arayışı / ödəniş nömrəsi": t(
            "Bank reference / payment number",
            "Банковская справка / номер платежа",
            "Banka referansı / ödeme numarası",
            "Bankreferenz / Zahlungsnummer",
        ),
        "%(n)s-ci cəhd": t("attempt %(n)s", "попытка %(n)s", "%(n)s. deneme", "Versuch %(n)s"),
        "Keçdi": t("Passed", "Сдал", "Geçti", "Bestanden"),
        "Keçmədi": t("Failed", "Не сдал", "Geçemedi", "Nicht bestanden"),
        "Qəbz yüklənib": t("Receipt uploaded", "Квитанция загружена", "Makbuz yüklendi", "Beleg hochgeladen"),
        "Bax": t("View", "Посмотреть", "Görüntüle", "Ansehen"),
        "Qəbz hələ yüklənməyib": t(
            "No receipt uploaded yet",
            "Квитанция ещё не загружена",
            "Makbuz henüz yüklenmedi",
            "Noch kein Beleg hochgeladen",
        ),
        "Yeni qəbz yüklə": t(
            "Upload a new receipt", "Загрузить новую квитанцию", "Yeni makbuz yükle", "Neuen Beleg hochladen"
        ),
        "Qəbzi yüklə": t("Upload receipt", "Загрузить квитанцию", "Makbuzu yükle", "Beleg hochladen"),
        "PDF, JPG və ya PNG · ən çox 10 MB": t(
            "PDF, JPG or PNG · up to 10 MB",
            "PDF, JPG или PNG · не более 10 МБ",
            "PDF, JPG veya PNG · en fazla 10 MB",
            "PDF, JPG oder PNG · höchstens 10 MB",
        ),
        "Addımlar": t("Steps", "Шаги", "Adımlar", "Schritte"),
        "Müraciətin addımları": t("Application steps", "Шаги заявки", "Başvurunun adımları", "Schritte des Antrags"),
        "25%% təkrar imtahan ödənişlidir. Qəbzi indi yükləyə və ya sonra «Müraciətlərim» tabından əlavə edə bilərsiniz. Ödənişi Mühasibatlıq yoxlayır, sonra dekanlıq imtahana buraxır.": t(
            "The 25%% re-exam is paid. You can upload the receipt now or add it later in the “My applications” tab. Accounting verifies the payment, then the dean's office admits you to the exam.",
            "Пересдача 25%% платная. Квитанцию можно загрузить сейчас или позже во вкладке «Мои заявки». Оплату проверяет бухгалтерия, затем деканат допускает к экзамену.",
            "%%25 bütünleme ücretlidir. Makbuzu şimdi yükleyebilir veya daha sonra «Başvurularım» sekmesinden ekleyebilirsiniz. Ödemeyi Muhasebe inceler, ardından dekanlık sınava kabul eder.",
            "Die 25-%%-Wiederholungsprüfung ist kostenpflichtig. Sie können den Beleg jetzt hochladen oder später im Reiter „Meine Anträge“ ergänzen. Die Buchhaltung prüft die Zahlung, danach lässt das Dekanat zur Prüfung zu.",
        ),
        "Alt qrup ödənişsizdir: fənni başqa qrupla yenidən keçəcəksiniz. Dekanlıq təqdimat sənədi ilə təsdiqləyib sizi uyğun jurnala yerləşdirir.": t(
            "The subgroup is free: you will retake the subject with another group. The dean's office approves it with a submission document and places you in the right journal.",
            "Подгруппа бесплатна: вы повторно изучите предмет с другой группой. Деканат утверждает это документом и зачисляет вас в нужный журнал.",
            "Alt grup ücretsizdir: dersi başka bir grupla yeniden alacaksınız. Dekanlık sunum belgesiyle onaylayıp sizi uygun yoklama defterine yerleştirir.",
            "Die Untergruppe ist kostenlos: Sie wiederholen das Fach mit einer anderen Gruppe. Das Dekanat genehmigt dies mit einem Dokument und weist Sie dem passenden Kursbuch zu.",
        ),
        "Ödəniş qəbzi": t("Payment receipt", "Квитанция об оплате", "Ödeme makbuzu", "Zahlungsbeleg"),
        "Ödənişi təsdiqlə": t("Verify payment", "Подтвердить оплату", "Ödemeyi onayla", "Zahlung bestätigen"),
        "Təsdiqlə": t("Confirm", "Подтвердить", "Onayla", "Bestätigen"),
        "Qəbzi rədd et": t("Reject receipt", "Отклонить квитанцию", "Makbuzu reddet", "Beleg ablehnen"),
        "Tələbə səbəbi görəcək və düzgün qəbzi yenidən yükləyə biləcək.": t(
            "The student will see the reason and can upload the correct receipt again.",
            "Студент увидит причину и сможет снова загрузить правильную квитанцию.",
            "Öğrenci gerekçeyi görecek ve doğru makbuzu yeniden yükleyebilecek.",
            "Der/die Studierende sieht den Grund und kann den richtigen Beleg erneut hochladen.",
        ),
        "Rədd et": t("Reject", "Отклонить", "Reddet", "Ablehnen"),
        "25%% imtahana burax": t(
            "Admit to the 25%% exam",
            "Допустить к экзамену 25%%",
            "%%25 sınavına kabul et",
            "Zur 25-%%-Prüfung zulassen",
        ),
        "Burax": t("Admit", "Допустить", "Kabul et", "Zulassen"),
        "Müraciəti rədd et": t("Reject application", "Отклонить заявку", "Başvuruyu reddet", "Antrag ablehnen"),
        "Alt qrup qərarı": t("Subgroup decision", "Решение о подгруппе", "Alt grup kararı", "Untergruppenentscheidung"),
        "Təqdimat sənədi məcburidir; hədəf jurnal seçilsə tələbə rəsmi xidmətlə dərhal yerləşdirilir.": t(
            "A submission document is required; if a target journal is chosen, the student is placed right away through the official service.",
            "Документ-представление обязателен; если выбран целевой журнал, студент сразу зачисляется через официальный сервис.",
            "Sunum belgesi zorunludur; hedef yoklama defteri seçilirse öğrenci resmî hizmetle hemen yerleştirilir.",
            "Ein Vorlagedokument ist Pflicht; wird ein Ziel-Kursbuch gewählt, wird der/die Studierende sofort über den offiziellen Dienst zugewiesen.",
        ),
        "Yadda saxla": t("Save", "Сохранить", "Kaydet", "Speichern"),
        "25%% imtahanın nəticəsi": t(
            "25%% exam result", "Результат экзамена 25%%", "%%25 sınavının sonucu", "Ergebnis der 25-%%-Prüfung"
        ),
        "Bal ResitRecord-a yazılır və yekun nəticə yenidən hesablanır (təkrar imtahan balı əsas imtahan balını əvəz edir).": t(
            "The score is stored as the resit record and the final result is recalculated (the re-exam score replaces the main exam score).",
            "Балл записывается в запись пересдачи, итог пересчитывается (балл пересдачи заменяет балл основного экзамена).",
            "Puan bütünleme kaydına yazılır ve final sonucu yeniden hesaplanır (bütünleme puanı ana sınav puanının yerine geçer).",
            "Die Punkte werden als Wiederholungseintrag gespeichert und das Endergebnis neu berechnet (die Wiederholungsnote ersetzt die Note der Hauptprüfung).",
        ),
        "Yaz": t("Record", "Внести", "Kaydet", "Erfassen"),
        "Tələbə tapılmadı və ya əhatənizdə deyil": t(
            "Student not found or outside your scope",
            "Студент не найден или вне вашей зоны",
            "Öğrenci bulunamadı veya yetki alanınızda değil",
            "Studierende/r nicht gefunden oder außerhalb Ihres Zuständigkeitsbereichs",
        ),
        "%(name)s — 25%% izi": t(
            "%(name)s — 25%% trail", "%(name)s — история 25%%", "%(name)s — %%25 geçmişi", "%(name)s — 25-%%-Verlauf"
        ),
        "Bütün müraciətlər, addımlar, qəbzlər, imtahan şansları və nəticələr.": t(
            "All applications, steps, receipts, exam chances and results.",
            "Все заявки, шаги, квитанции, попытки экзаменов и результаты.",
            "Tüm başvurular, adımlar, makbuzlar, sınav hakları ve sonuçlar.",
            "Alle Anträge, Schritte, Belege, Prüfungschancen und Ergebnisse.",
        ),
        "Bağla": t("Close", "Закрыть", "Kapat", "Schließen"),
        "Qəbz %(n)s": t("Receipt %(n)s", "Квитанция %(n)s", "Makbuz %(n)s", "Beleg %(n)s"),
        "25%% təkrar imtahan": t("25%% re-exam", "Пересдача 25%%", "%%25 bütünleme", "25-%%-Wiederholungsprüfung"),
        "Buraxılışdan sonra İmtahan mərkəzi «İmtahan şansı ver» bölməsində «25%% müraciəti» səbəbi ilə cəhd açır və ya kağız imtahanın balı yazılır.": t(
            "After admission the exam centre opens an attempt in “Grant exam chance” with the reason “25%% application”, or the paper exam score is entered.",
            "После допуска экзаменационный центр открывает попытку в разделе «Выдать попытку экзамена» с причиной «Заявка на 25%%», либо вносится балл бумажного экзамена.",
            "Kabulden sonra Sınav merkezi «Sınav hakkı tanı» bölümünde «%%25 başvurusu» gerekçesiyle hak açar veya kâğıt sınavın puanı girilir.",
            "Nach der Zulassung öffnet das Prüfungszentrum unter „Prüfungschance gewähren“ mit dem Grund „25-%%-Antrag“ einen Versuch, oder die Note der Papierprüfung wird erfasst.",
        ),
        "25%% cəhd sayı: %(n)s": t(
            "25%% attempts: %(n)s", "Попыток 25%%: %(n)s", "%%25 deneme sayısı: %(n)s", "25-%%-Versuche: %(n)s"
        ),
        "Son nəticə: keçdi": t(
            "Latest result: passed", "Последний результат: сдал", "Son sonuç: geçti", "Letztes Ergebnis: bestanden"
        ),
        "Son nəticə: keçmədi": t(
            "Latest result: failed",
            "Последний результат: не сдал",
            "Son sonuç: geçemedi",
            "Letztes Ergebnis: nicht bestanden",
        ),
        "Status": t("Status", "Статус", "Durum", "Bearbeitungsstand"),
        "Yekun": t("Total", "Итог", "Toplam", "Gesamt"),
        "Tarix": t("Date", "Дата", "Tarih", "Datum"),
        "İmtahan şansı: «%(title)s» · +%(n)s · %(reason)s · %(when)s": t(
            "Exam chance: “%(title)s” · +%(n)s · %(reason)s · %(when)s",
            "Попытка экзамена: «%(title)s» · +%(n)s · %(reason)s · %(when)s",
            "Sınav hakkı: «%(title)s» · +%(n)s · %(reason)s · %(when)s",
            "Prüfungschance: „%(title)s“ · +%(n)s · %(reason)s · %(when)s",
        ),
        "Alt qrup müraciəti": t(
            "Subgroup application", "Заявка в подгруппу", "Alt grup başvurusu", "Untergruppenantrag"
        ),
        "25%% tarixçəsi boşdur": t(
            "No 25%% history yet", "История 25%% пуста", "%%25 geçmişi boş", "Noch kein 25-%%-Verlauf"
        ),
        "Buraxıldığınız hər 25%% cəhdi, onun balı və yekun nəticə burada qalır.": t(
            "Every 25%% attempt you were admitted to, its score and the final result stay here.",
            "Каждая попытка 25%%, к которой вы были допущены, её балл и итог хранятся здесь.",
            "Kabul edildiğiniz her %%25 denemesi, puanı ve sonucu burada kalır.",
            "Jeder 25-%%-Versuch, zu dem Sie zugelassen wurden, seine Punkte und das Endergebnis bleiben hier.",
        ),
        "Hədəf jurnal (cari semestr)": t(
            "Target journal (current semester)",
            "Целевой журнал (текущий семестр)",
            "Hedef yoklama defteri (mevcut dönem)",
            "Ziel-Kursbuch (aktuelles Semester)",
        ),
        "(istəyə bağlı — sonra da yerləşdirmək olar)": t(
            "(optional — placement can also be done later)",
            "(необязательно — зачислить можно и позже)",
            "(isteğe bağlı — yerleştirme daha sonra da yapılabilir)",
            "(optional — die Zuweisung ist auch später möglich)",
        ),
        "— Seçilməyib —": t("— Not selected —", "— Не выбрано —", "— Seçilmedi —", "— Nicht gewählt —"),
        "Təqdimat / sərəncam sənədi": t(
            "Submission / decree document",
            "Документ-представление / распоряжение",
            "Sunum / karar belgesi",
            "Vorlage-/Verfügungsdokument",
        ),
        "Bu qəbz başqa müraciətdə də yüklənib": t(
            "This receipt was also uploaded on another application",
            "Эта квитанция загружена и в другой заявке",
            "Bu makbuz başka bir başvuruda da yüklendi",
            "Dieser Beleg wurde auch bei einem anderen Antrag hochgeladen",
        ),
        "Səbəb": t("Reason", "Причина", "Gerekçe", "Grund"),
        "Nəticə": t("Result", "Результат", "Sonuç", "Ergebnis"),
        "Qəbzə bax": t("View receipt", "Посмотреть квитанцию", "Makbuzu görüntüle", "Beleg ansehen"),
        "yüklənib: %(when)s": t(
            "uploaded: %(when)s", "загружено: %(when)s", "yüklendi: %(when)s", "hochgeladen: %(when)s"
        ),
        "Qəbz yüklənməyib": t(
            "No receipt uploaded", "Квитанция не загружена", "Makbuz yüklenmedi", "Kein Beleg hochgeladen"
        ),
        "Qərar sənədi": t("Decision document", "Документ решения", "Karar belgesi", "Entscheidungsdokument"),
        "İmtahana burax": t("Admit to exam", "Допустить к экзамену", "Sınava kabul et", "Zur Prüfung zulassen"),
        "Alt qrupu təsdiqlə": t("Approve subgroup", "Одобрить подгруппу", "Alt grubu onayla", "Untergruppe genehmigen"),
        "Alt qrupa yerləşdir": t(
            "Place in subgroup", "Зачислить в подгруппу", "Alt gruba yerleştir", "Der Untergruppe zuweisen"
        ),
        "Nəticəni yaz": t("Record result", "Внести результат", "Sonucu gir", "Ergebnis erfassen"),
        "Bu bölmə 25%% müraciətlərini yoxlayan heyət üçündür.": t(
            "This section is for staff who review 25%% applications.",
            "Этот раздел предназначен для сотрудников, проверяющих заявки на 25%%.",
            "Bu bölüm %%25 başvurularını inceleyen personel içindir.",
            "Dieser Bereich ist für Mitarbeitende, die 25-%%-Anträge prüfen.",
        ),
        "Tələbələrin 25%% təkrar imtahan və alt qrup müraciətləri: Mühasibatlıq qəbzi yoxlayır, dekanlıq / tədris şöbəsi buraxır və ya alt qrupa yerləşdirir. Hər addım tarixçədə qalır.": t(
            "Students' 25%% re-exam and subgroup applications: Accounting checks the receipt, the dean's office / academic office admits or places in a subgroup. Every step stays in the history.",
            "Заявки студентов на пересдачу 25%% и в подгруппу: бухгалтерия проверяет квитанцию, деканат / учебный отдел допускает или зачисляет в подгруппу. Каждый шаг сохраняется в истории.",
            "Öğrencilerin %%25 bütünleme ve alt grup başvuruları: Muhasebe makbuzu inceler, dekanlık / öğrenci işleri kabul eder veya alt gruba yerleştirir. Her adım geçmişte kalır.",
            "25-%%-Wiederholungs- und Untergruppenanträge der Studierenden: Die Buchhaltung prüft den Beleg, Dekanat / Studienbüro lässt zu oder weist einer Untergruppe zu. Jeder Schritt bleibt im Verlauf.",
        ),
        "Növbələr": t("Queues", "Очереди", "Kuyruklar", "Warteschlangen"),
        "Axtarış": t("Search", "Поиск", "Arama", "Suche"),
        "Tələbə, fənn və ya qrup": t(
            "Student, subject or group",
            "Студент, предмет или группа",
            "Öğrenci, ders veya grup",
            "Studierende/r, Fach oder Gruppe",
        ),
        "Bütün statuslar": t("All statuses", "Все статусы", "Tüm durumlar", "Alle Status"),
        "Növ": t("Type", "Тип", "Tür", "Art"),
        "Hər iki növ": t("Both types", "Оба типа", "Her iki tür", "Beide Arten"),
        "Nəticə: %(n)s": t("Results: %(n)s", "Результатов: %(n)s", "Sonuç: %(n)s", "Ergebnisse: %(n)s"),
        "Səhifələmə": t("Pagination", "Пагинация", "Sayfalama", "Seitennavigation"),
        "Növbə boşdur": t("The queue is empty", "Очередь пуста", "Kuyruk boş", "Die Warteschlange ist leer"),
        "Bu süzgəclərə uyğun müraciət yoxdur.": t(
            "No applications match these filters.",
            "Нет заявок, соответствующих фильтрам.",
            "Bu filtrelere uyan başvuru yok.",
            "Keine Anträge entsprechen diesen Filtern.",
        ),
        "Geri götürülən müraciət bağlanır və tarixçədə qalır. Lazım olsa sonra yenidən müraciət edə bilərsiniz.": t(
            "A withdrawn application is closed and stays in the history. You can apply again later if needed.",
            "Отозванная заявка закрывается и остаётся в истории. При необходимости можно подать снова.",
            "Geri çekilen başvuru kapanır ve geçmişte kalır. Gerekirse daha sonra yeniden başvurabilirsiniz.",
            "Ein zurückgezogener Antrag wird geschlossen und bleibt im Verlauf. Bei Bedarf können Sie später erneut einen Antrag stellen.",
        ),
        "Kəsr": t("Failed", "Не сдан", "Başarısız", "Nicht bestanden"),
        "İmtahan": t("Exam", "Экзамен", "Sınav", "Prüfung"),
        "25%% cəhd": t("25%% attempts", "Попытки 25%%", "%%25 denemesi", "25-%%-Versuche"),
        "Ödəniş qəbzi ilə — Mühasibatlıq təsdiqləyəndən sonra dekanlıq buraxır.": t(
            "With a payment receipt — after Accounting verifies it, the dean's office admits you.",
            "С квитанцией об оплате — после проверки бухгалтерией деканат допускает.",
            "Ödeme makbuzuyla — Muhasebe onayladıktan sonra dekanlık kabul eder.",
            "Mit Zahlungsbeleg — nach Bestätigung durch die Buchhaltung lässt das Dekanat zu.",
        ),
        "25%% müraciət et": t("Apply for 25%%", "Подать на 25%%", "%%25 başvurusu yap", "25 %% beantragen"),
        "Ödənişsiz — fənni başqa qrupla yenidən keçirsiniz; dekanlıq sənədlə təsdiqləyir.": t(
            "Free — you retake the subject with another group; the dean's office approves with a document.",
            "Бесплатно — вы повторно изучаете предмет с другой группой; деканат утверждает документом.",
            "Ücretsiz — dersi başka bir grupla yeniden alırsınız; dekanlık belgeyle onaylar.",
            "Kostenlos — Sie wiederholen das Fach mit einer anderen Gruppe; das Dekanat genehmigt mit einem Dokument.",
        ),
        "Alt qrupa müraciət et": t(
            "Apply for a subgroup", "Подать в подгруппу", "Alt gruba başvur", "Untergruppe beantragen"
        ),
    }
)


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
            flag = "#, python-format\n" if "%%" in msgid or "%(" in msgid else ""
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
