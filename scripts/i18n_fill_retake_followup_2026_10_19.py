#!/usr/bin/env python3
"""EMSArena i18n — 25% müraciəti, sahibin cavabları (2026-10-19): məbləğ / təhsil haqqı cədvəli, İmtahan mərkəzinin
pəncərəsi, ödənişdən sonra qərarla bağlanış («İmtahana gəlmədi»), Mühasibatlığın kənarlaşma bandı.

msgid AZ cümlədir → az msgstr = msgid (model meta adları ingiliscə msgid-dir — az ayrıca verilir).
Şablon sətirlərində faiz ``%%`` kimi (Django ``trans`` / ``blocktrans``), Python sətirlərində tək ``%``.
İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RT = "registrar.retake"
RS = "core.runtime_settings"
SB = "profile.sidebar"
AC = "accounts.accounting"


def t(en, ru, tr, de, az=None):
    row = {"en": en, "ru": ru, "tr": tr, "de": de}
    if az is not None:
        row["az"] = az
    return row


ENTRIES = {
    "registrar.model.retake_window.meta": {
        "retake application window": t(
            "retake application window",
            "окно приёма заявок на пересдачу",
            "bütünleme başvuru dönemi",
            "Antragsfenster für Wiederholungen",
            az="25% müraciət pəncərəsi",
        ),
        "retake application windows": t(
            "retake application windows",
            "окна приёма заявок на пересдачу",
            "bütünleme başvuru dönemleri",
            "Antragsfenster für Wiederholungen",
            az="25% müraciət pəncərələri",
        ),
    },
    "registrar.model.retake_tuition.meta": {
        "annual tuition": t(
            "annual tuition",
            "годовая плата за обучение",
            "yıllık öğrenim ücreti",
            "Jahresstudiengebühr",
            az="illik təhsil haqqı",
        ),
        "annual tuition table": t(
            "annual tuition table",
            "таблица годовой платы за обучение",
            "yıllık öğrenim ücreti tablosu",
            "Tabelle der Jahresstudiengebühren",
            az="təhsil haqqı cədvəli",
        ),
    },
    SB: {
        "25% müraciət pəncərəsi": t(
            "25% application window", "Окно заявок на 25%", "%25 başvuru dönemi", "25-%-Antragsfenster"
        ),
        "25%% müraciət pəncərəsi": t(
            "25%% application window", "Окно заявок на 25%%", "%%25 başvuru dönemi", "25-%%-Antragsfenster"
        ),
    },
    AC: {
        "müəllim (> +{pct}%)": t(
            "teachers (> +{pct}%)", "преподаватели (> +{pct}%)", "öğretim üyesi (> +{pct}%)", "Lehrkräfte (> +{pct} %)"
        ),
        "müəllim (< −{pct}%)": t(
            "teachers (< −{pct}%)", "преподаватели (< −{pct}%)", "öğretim üyesi (< −{pct}%)", "Lehrkräfte (< −{pct} %)"
        ),
        "Status — fakt planın ±%(pct)s%%-i daxilindədirsə «Plana uyğun»; az və ya çoxdursa müvafiq olaraq «Plandan az» / «Plandan çox». Band «Sistem tənzimləmələri»ndə dəyişdirilir.": t(
            "Status — if actual hours are within ±%(pct)s%% of the plan they are “On plan”; otherwise “Below plan” / “Above plan”. The band is changed in “System settings”.",
            "Статус — если факт в пределах ±%(pct)s%% плана, «По плану»; меньше или больше — «Ниже плана» / «Выше плана». Диапазон меняется в «Системных настройках».",
            "Durum — gerçekleşen planın ±%%%(pct)s'i içindeyse «Plana uygun»; az veya fazlaysa «Planın altında» / «Planın üstünde». Bant «Sistem ayarları»ndan değiştirilir.",
            "Status — liegt das Ist innerhalb von ±%(pct)s %% des Plans, gilt „Planmäßig“; sonst „Unter Plan“ / „Über Plan“. Das Band wird in den „Systemeinstellungen“ geändert.",
        ),
    },
    RS: {
        "Mühasibatlıq": t("Accounting", "Бухгалтерия", "Muhasebe", "Buchhaltung"),
        "25% ödənişinin faizi": t(
            "25% payment percent", "Процент оплаты 25%", "%25 ödeme yüzdesi", "Prozentsatz der 25-%-Zahlung"
        ),
        "Təxmini məbləğ = illik təhsil haqqı × bu faiz ÷ 100 × (fənnin krediti ÷ illik kredit). Dəqiq məbləği Mühasibatlıq qəbzi yoxlayanda təsdiqləyir; fərq xəbərdarlıqdır, blok deyil.": t(
            "Estimated amount = annual tuition × this percent ÷ 100 × (subject credits ÷ annual credits). Accounting confirms the exact amount when it checks the receipt; a difference is a warning, not a block.",
            "Примерная сумма = годовая плата × этот процент ÷ 100 × (кредиты предмета ÷ годовые кредиты). Точную сумму подтверждает бухгалтерия при проверке квитанции; расхождение — предупреждение, а не блокировка.",
            "Tahmini tutar = yıllık öğrenim ücreti × bu yüzde ÷ 100 × (dersin kredisi ÷ yıllık kredi). Kesin tutarı Muhasebe makbuzu incelerken onaylar; fark uyarıdır, engel değildir.",
            "Geschätzter Betrag = Jahresgebühr × dieser Prozentsatz ÷ 100 × (Fachcredits ÷ Jahrescredits). Den genauen Betrag bestätigt die Buchhaltung bei der Belegprüfung; eine Abweichung ist eine Warnung, keine Sperre.",
        ),
        "İllik kredit (məbləğ düsturu üçün)": t(
            "Annual credits (for the amount formula)",
            "Годовые кредиты (для формулы суммы)",
            "Yıllık kredi (tutar formülü için)",
            "Jahrescredits (für die Betragsformel)",
        ),
        "Fənnin payı = fənnin krediti ÷ bu ədəd. 0 yazılsa kreditə bölünmür: məbləğ = illik haqq × faiz ÷ 100.": t(
            "Subject share = subject credits ÷ this number. With 0 there is no credit division: amount = annual fee × percent ÷ 100.",
            "Доля предмета = кредиты предмета ÷ это число. При 0 деления на кредиты нет: сумма = годовая плата × процент ÷ 100.",
            "Dersin payı = dersin kredisi ÷ bu sayı. 0 yazılırsa krediye bölünmez: tutar = yıllık ücret × yüzde ÷ 100.",
            "Fachanteil = Fachcredits ÷ diese Zahl. Bei 0 wird nicht durch Credits geteilt: Betrag = Jahresgebühr × Prozentsatz ÷ 100.",
        ),
        "Plan ↔ fakt kənarlaşma bandı": t(
            "Plan ↔ actual deviation band",
            "Допустимое отклонение план ↔ факт",
            "Plan ↔ gerçekleşen sapma bandı",
            "Abweichungsband Plan ↔ Ist",
        ),
        "Keçirilmiş dərs saatı planın ±bu faiz daxilindədirsə «Plana uyğun» sayılır; azdırsa «Plandan az», çoxdursa «Plandan çox».": t(
            "Taught hours within ±this percent of the plan count as “On plan”; fewer is “Below plan”, more is “Above plan”.",
            "Проведённые часы в пределах ±этого процента плана считаются «По плану»; меньше — «Ниже плана», больше — «Выше плана».",
            "İşlenen ders saati planın ±bu yüzdesi içindeyse «Plana uygun» sayılır; azsa «Planın altında», fazlaysa «Planın üstünde».",
            "Gehaltene Stunden innerhalb von ±diesem Prozentsatz des Plans gelten als „Planmäßig“; weniger ist „Unter Plan“, mehr „Über Plan“.",
        ),
    },
}

ENTRIES[RT] = {
    # Python
    "İmtahana gəlmədi": t(
        "Did not attend the exam", "Не явился на экзамен", "Sınava girmedi", "Nicht zur Prüfung erschienen"
    ),
    "Təhsil haqqı cədvəli": t(
        "Tuition table", "Таблица платы за обучение", "Öğrenim ücreti tablosu", "Gebührentabelle"
    ),
    "«İmtahana gəlmədi» qərarı yazıldı — cəhd istifadə olunmuş sayılır.": t(
        "The “did not attend” decision was recorded — the attempt counts as used.",
        "Решение «не явился» записано — попытка считается использованной.",
        "«Sınava girmedi» kararı kaydedildi — deneme kullanılmış sayılır.",
        "Die Entscheidung „nicht erschienen“ wurde erfasst — der Versuch gilt als verbraucht.",
    ),
    "Müraciət qərarla geri götürüldü.": t(
        "The application was withdrawn by decision.",
        "Заявка отозвана по решению.",
        "Başvuru kararla geri çekildi.",
        "Der Antrag wurde per Entscheidung zurückgezogen.",
    ),
    "Bağlanış vaxtı açılışdan sonra olmalıdır.": t(
        "The closing time must be after the opening time.",
        "Время закрытия должно быть позже открытия.",
        "Kapanış zamanı açılıştan sonra olmalıdır.",
        "Die Schließzeit muss nach der Öffnungszeit liegen.",
    ),
    "Pəncərə artıq bağlanıb.": t(
        "The window is already closed.",
        "Окно уже закрыто.",
        "Dönem zaten kapatıldı.",
        "Das Fenster ist bereits geschlossen.",
    ),
    "Bu dövr üçün artıq açıq (və ya planlaşdırılmış) pəncərə var — əvvəlcə onu bağlayın.": t(
        "There is already an open (or scheduled) window for this period — close it first.",
        "Для этого периода уже есть открытое (или запланированное) окно — сначала закройте его.",
        "Bu dönem için zaten açık (veya planlanmış) bir başvuru dönemi var — önce onu kapatın.",
        "Für diesen Zeitraum gibt es bereits ein offenes (oder geplantes) Fenster — schließen Sie es zuerst.",
    ),
    "Açılış vaxtı göstərilməlidir.": t(
        "An opening time is required.",
        "Нужно указать время открытия.",
        "Açılış zamanı belirtilmelidir.",
        "Eine Öffnungszeit ist erforderlich.",
    ),
    "Tarix və saat düzgün deyil.": t(
        "The date and time are not valid.",
        "Неверные дата и время.",
        "Tarih ve saat geçerli değil.",
        "Datum und Uhrzeit sind ungültig.",
    ),
    "Məbləğ 0 ilə 1 000 000 AZN arasında olmalıdır.": t(
        "The amount must be between 0 and 1,000,000 AZN.",
        "Сумма должна быть от 0 до 1 000 000 AZN.",
        "Tutar 0 ile 1.000.000 AZN arasında olmalıdır.",
        "Der Betrag muss zwischen 0 und 1.000.000 AZN liegen.",
    ),
    "Qəbul ili düzgün deyil.": t(
        "The admission year is not valid.",
        "Неверный год поступления.",
        "Giriş yılı geçerli değil.",
        "Das Aufnahmejahr ist ungültig.",
    ),
    "Tədris ilini seçin.": t(
        "Choose the academic year.", "Выберите учебный год.", "Akademik yılı seçin.", "Wählen Sie das Studienjahr."
    ),
    "Ödənilən məbləği yazın (AZN).": t(
        "Enter the amount paid (AZN).",
        "Введите оплаченную сумму (AZN).",
        "Ödenen tutarı yazın (AZN).",
        "Geben Sie den gezahlten Betrag ein (AZN).",
    ),
    "Məbləğ rəqəm olmalıdır.": t(
        "The amount must be a number.",
        "Сумма должна быть числом.",
        "Tutar sayı olmalıdır.",
        "Der Betrag muss eine Zahl sein.",
    ),
    "İxtisas tapılmadı.": t(
        "Programme not found.", "Специальность не найдена.", "Program bulunamadı.", "Studiengang nicht gefunden."
    ),
    "Bu sətir artıq var.": t(
        "This row already exists.", "Такая строка уже есть.", "Bu satır zaten var.", "Diese Zeile existiert bereits."
    ),
    "Ödənişdən sonra bağlanış rəsmi qərarla olur: əmr nömrəsi və tarixi və ya qərar sənədi əlavə edin.": t(
        "Closing after payment needs an official decision: add an order number and date or a decision document.",
        "Закрытие после оплаты — только по официальному решению: укажите номер и дату приказа или приложите документ.",
        "Ödemeden sonra kapatma resmî kararla olur: emir numarası ve tarihi veya karar belgesi ekleyin.",
        "Das Schließen nach der Zahlung erfordert eine offizielle Entscheidung: Nummer und Datum der Anordnung oder ein Entscheidungsdokument angeben.",
    ),
    "Bu mərhələdə bu bağlanış mümkün deyil.": t(
        "This closure is not possible at this stage.",
        "На этом этапе такое закрытие невозможно.",
        "Bu aşamada bu kapatma mümkün değil.",
        "Dieses Schließen ist in dieser Phase nicht möglich.",
    ),
    "Qaytarılma yoxdur.": t("No refund.", "Возврата нет.", "İade yok.", "Keine Erstattung."),
    "Müraciət pəncərəsi açıldı.": t(
        "The application window was opened.",
        "Окно приёма заявок открыто.",
        "Başvuru dönemi açıldı.",
        "Das Antragsfenster wurde geöffnet.",
    ),
    "Müraciət pəncərəsi bağlandı.": t(
        "The application window was closed.",
        "Окно приёма заявок закрыто.",
        "Başvuru dönemi kapatıldı.",
        "Das Antragsfenster wurde geschlossen.",
    ),
    "Təhsil haqqı sətri yadda saxlanıldı.": t(
        "Tuition row saved.",
        "Строка платы за обучение сохранена.",
        "Öğrenim ücreti satırı kaydedildi.",
        "Gebührenzeile gespeichert.",
    ),
    "Təhsil haqqı sətri silindi.": t(
        "Tuition row deleted.",
        "Строка платы за обучение удалена.",
        "Öğrenim ücreti satırı silindi.",
        "Gebührenzeile gelöscht.",
    ),
    # Şablon (faiz — %%)
    "Gözlənilən məbləğ": t("Expected amount", "Ожидаемая сумма", "Beklenen tutar", "Erwarteter Betrag"),
    "Ödənilən məbləğ": t("Amount paid", "Оплаченная сумма", "Ödenen tutar", "Gezahlter Betrag"),
    "Ödənilən məbləğ gözləniləndən fərqlidir": t(
        "The amount paid differs from the expected amount",
        "Оплаченная сумма отличается от ожидаемой",
        "Ödenen tutar beklenenden farklı",
        "Der gezahlte Betrag weicht vom erwarteten ab",
    ),
    "Müraciət pəncərəsi açıqdır — %(until)s tarixinədək": t(
        "The application window is open until %(until)s",
        "Приём заявок открыт до %(until)s",
        "Başvuru dönemi %(until)s tarihine kadar açık",
        "Das Antragsfenster ist bis %(until)s geöffnet",
    ),
    "Müraciət pəncərəsi açıqdır": t(
        "The application window is open",
        "Приём заявок открыт",
        "Başvuru dönemi açık",
        "Das Antragsfenster ist geöffnet",
    ),
    "Dövr: %(period)s. Pəncərəni İmtahan mərkəzi açır və bağlayır.": t(
        "Period: %(period)s. The exam centre opens and closes the window.",
        "Период: %(period)s. Окно открывает и закрывает экзаменационный центр.",
        "Dönem: %(period)s. Başvuru dönemini Sınav merkezi açar ve kapatır.",
        "Zeitraum: %(period)s. Das Prüfungszentrum öffnet und schließt das Fenster.",
    ),
    "Pəncərə %(when)s tarixində açılacaq. Göndərdiyiniz müraciətlərin vəziyyətini aşağıda izləyə bilərsiniz.": t(
        "The window opens on %(when)s. You can follow your submitted applications below.",
        "Окно откроется %(when)s. Статус поданных заявок можно отслеживать ниже.",
        "Başvuru dönemi %(when)s tarihinde açılacak. Gönderdiğiniz başvuruları aşağıda izleyebilirsiniz.",
        "Das Fenster öffnet am %(when)s. Ihre eingereichten Anträge sehen Sie unten.",
    ),
    "Təxmini məbləğ: %(amount)s AZN — dəqiq məbləği Mühasibatlıq təsdiqləyir": t(
        "Estimated amount: %(amount)s AZN — Accounting confirms the exact amount",
        "Примерная сумма: %(amount)s AZN — точную сумму подтверждает бухгалтерия",
        "Tahmini tutar: %(amount)s AZN — kesin tutarı Muhasebe onaylar",
        "Geschätzter Betrag: %(amount)s AZN — den genauen Betrag bestätigt die Buchhaltung",
    ),
    "Məbləği Mühasibatlıqdan öyrənin": t(
        "Ask Accounting for the amount",
        "Уточните сумму в бухгалтерии",
        "Tutarı Muhasebeden öğrenin",
        "Erfragen Sie den Betrag bei der Buchhaltung",
    ),
    "Bu bölmə İmtahan mərkəzinin qərar səlahiyyəti olanlar üçündür.": t(
        "This section is for exam-centre staff with decision rights.",
        "Этот раздел для сотрудников экзаменационного центра с правом решения.",
        "Bu bölüm karar yetkisi olan Sınav merkezi personeli içindir.",
        "Dieser Bereich ist für Mitarbeitende des Prüfungszentrums mit Entscheidungsbefugnis.",
    ),
    "Tələbələr 25%% təkrar imtahan və alt qrup müraciətini yalnız açıq pəncərə müddətində göndərə bilir. Pəncərəni burada açıb bağlayın; bütün açılış və bağlanışlar tarixçədə qalır.": t(
        "Students can send 25%% re-exam and subgroup applications only while a window is open. Open and close the window here; every opening and closing stays in the history.",
        "Студенты могут подавать заявки на пересдачу 25%% и в подгруппу только при открытом окне. Открывайте и закрывайте окно здесь; каждое открытие и закрытие сохраняется в истории.",
        "Öğrenciler %%25 bütünleme ve alt grup başvurusunu yalnızca dönem açıkken gönderebilir. Dönemi buradan açıp kapatın; her açılış ve kapanış geçmişte kalır.",
        "Studierende können 25-%%-Wiederholungs- und Untergruppenanträge nur bei geöffnetem Fenster stellen. Öffnen und schließen Sie das Fenster hier; jedes Öffnen und Schließen bleibt im Verlauf.",
    ),
    "Ümumi açar söndürülüb": t(
        "The master switch is off", "Общий переключатель выключен", "Ana anahtar kapalı", "Der Hauptschalter ist aus"
    ),
    "«Sistem tənzimləmələri»ndə «Müraciət pəncərəsi açıqdır» söndürülüb — pəncərə açıq olsa belə müraciət qəbul olunmur.": t(
        "“Application window is open” is switched off in “System settings” — no applications are accepted even if a window is open.",
        "В «Системных настройках» выключено «Приём заявок открыт» — заявки не принимаются, даже если окно открыто.",
        "«Sistem ayarları»nda «Başvuru dönemi açık» kapatılmış — dönem açık olsa bile başvuru alınmaz.",
        "In den „Systemeinstellungen“ ist „Antragsfenster ist geöffnet“ ausgeschaltet — auch bei offenem Fenster werden keine Anträge angenommen.",
    ),
    "Cari vəziyyət": t("Current status", "Текущее состояние", "Mevcut durum", "Aktueller Stand"),
    "Açıqdır": t("Open", "Открыто", "Açık", "Geöffnet"),
    "əl ilə bağlanana qədər": t(
        "until closed manually", "до ручного закрытия", "elle kapatılana kadar", "bis zum manuellen Schließen"
    ),
    "Planlaşdırılıb": t("Scheduled", "Запланировано", "Planlandı", "Geplant"),
    "Bağlıdır": t("Closed", "Закрыто", "Kapalı", "Geschlossen"),
    "Pəncərə bağlansın? Yeni müraciət qəbul olunmayacaq.": t(
        "Close the window? No new applications will be accepted.",
        "Закрыть окно? Новые заявки приниматься не будут.",
        "Dönem kapatılsın mı? Yeni başvuru alınmayacak.",
        "Fenster schließen? Es werden keine neuen Anträge angenommen.",
    ),
    "Pəncərəni bağla": t("Close window", "Закрыть окно", "Dönemi kapat", "Fenster schließen"),
    "Akademik dövr": t("Academic period", "Академический период", "Akademik dönem", "Studienabschnitt"),
    "Açılış": t("Opens", "Открытие", "Açılış", "Öffnung"),
    "(boş — indi)": t("(empty — now)", "(пусто — сейчас)", "(boş — şimdi)", "(leer — jetzt)"),
    "Bağlanış": t("Closes", "Закрытие", "Kapanış", "Schließung"),
    "Pəncərəni aç": t("Open window", "Открыть окно", "Dönemi aç", "Fenster öffnen"),
    "Tarixçə": t("History", "История", "Geçmiş", "Verlauf"),
    "Dövr": t("Period", "Период", "Dönem", "Zeitraum"),
    "Açan": t("Opened by", "Открыл", "Açan", "Geöffnet von"),
    "Bağlayan": t("Closed by", "Закрыл", "Kapatan", "Geschlossen von"),
    "Ödənilən məbləğ (AZN)": t(
        "Amount paid (AZN)", "Оплаченная сумма (AZN)", "Ödenen tutar (AZN)", "Gezahlter Betrag (AZN)"
    ),
    "Gözlənilən (təxmini): {amount} AZN": t(
        "Expected (estimated): {amount} AZN",
        "Ожидаемая (примерно): {amount} AZN",
        "Beklenen (tahmini): {amount} AZN",
        "Erwartet (geschätzt): {amount} AZN",
    ),
    "Təhsil haqqı cədvəlində sətir yoxdur — gözlənilən məbləğ hesablanmır.": t(
        "There is no tuition table row — the expected amount is not calculated.",
        "В таблице платы нет строки — ожидаемая сумма не рассчитывается.",
        "Öğrenim ücreti tablosunda satır yok — beklenen tutar hesaplanmaz.",
        "In der Gebührentabelle fehlt eine Zeile — der erwartete Betrag wird nicht berechnet.",
    ),
    "Məbləğ gözləniləndən fərqlidir — təsdiq bloklanmır, fərq qərar zəncirində qeyd olunur.": t(
        "The amount differs from the expected one — verification is not blocked; the difference is recorded in the decision chain.",
        "Сумма отличается от ожидаемой — подтверждение не блокируется, разница фиксируется в цепочке решений.",
        "Tutar beklenenden farklı — onay engellenmez, fark karar zincirine kaydedilir.",
        "Der Betrag weicht vom erwarteten ab — die Bestätigung wird nicht gesperrt, die Differenz wird in der Entscheidungskette vermerkt.",
    ),
    "Təsdiqlənmiş ödəniş: %(amount)s AZN": t(
        "Verified payment: %(amount)s AZN",
        "Подтверждённая оплата: %(amount)s AZN",
        "Onaylanmış ödeme: %(amount)s AZN",
        "Bestätigte Zahlung: %(amount)s AZN",
    ),
    "Ödənişdən sonra bağlanış": t(
        "Closing after payment", "Закрытие после оплаты", "Ödemeden sonra kapatma", "Schließen nach der Zahlung"
    ),
    "Rəsmi qərar məcburidir: əmr nömrəsi və tarixi və ya qərar sənədi. Qaytarılma yoxdur — qərar və qeyd tarixçədə qalır.": t(
        "An official decision is required: order number and date or a decision document. No refund — the decision and note stay in the history.",
        "Нужно официальное решение: номер и дата приказа или документ. Возврата нет — решение и запись остаются в истории.",
        "Resmî karar zorunludur: emir numarası ve tarihi veya karar belgesi. İade yok — karar ve not geçmişte kalır.",
        "Eine offizielle Entscheidung ist Pflicht: Nummer und Datum der Anordnung oder ein Dokument. Keine Erstattung — Entscheidung und Vermerk bleiben im Verlauf.",
    ),
    "Qərarı yaz": t("Record decision", "Записать решение", "Kararı kaydet", "Entscheidung erfassen"),
    "Təxmini 25%% məbləği = illik haqq × %(pct)s%% × (fənnin krediti ÷ %(credits)s). Faiz və illik kredit «Sistem tənzimləmələri»ndədir; illik kredit 0 olarsa kreditə bölünmür.": t(
        "Estimated 25%% amount = annual fee × %(pct)s%% × (subject credits ÷ %(credits)s). The percent and annual credits are in “System settings”; with 0 annual credits there is no credit division.",
        "Примерная сумма 25%% = годовая плата × %(pct)s%% × (кредиты предмета ÷ %(credits)s). Процент и годовые кредиты — в «Системных настройках»; при 0 годовых кредитов деления нет.",
        "Tahmini %%25 tutarı = yıllık ücret × %%%(pct)s × (dersin kredisi ÷ %(credits)s). Yüzde ve yıllık kredi «Sistem ayarları»ndadır; yıllık kredi 0 ise krediye bölünmez.",
        "Geschätzter 25-%%-Betrag = Jahresgebühr × %(pct)s %% × (Fachcredits ÷ %(credits)s). Prozentsatz und Jahrescredits stehen in den „Systemeinstellungen“; bei 0 Jahrescredits wird nicht geteilt.",
    ),
    "Tədris ili": t("Academic year", "Учебный год", "Akademik yıl", "Studienjahr"),
    "Qəbul ili": t("Admission year", "Год поступления", "Giriş yılı", "Aufnahmejahr"),
    "İxtisas": t("Programme", "Специальность", "Program", "Studiengang"),
    "(boş — defolt)": t("(empty — default)", "(пусто — по умолчанию)", "(boş — varsayılan)", "(leer — Standard)"),
    "Bütün ixtisaslar (defolt)": t(
        "All programmes (default)",
        "Все специальности (по умолчанию)",
        "Tüm programlar (varsayılan)",
        "Alle Studiengänge (Standard)",
    ),
    "İllik təhsil haqqı (AZN)": t(
        "Annual tuition (AZN)",
        "Годовая плата за обучение (AZN)",
        "Yıllık öğrenim ücreti (AZN)",
        "Jahresstudiengebühr (AZN)",
    ),
    "İllik haqq": t("Annual fee", "Годовая плата", "Yıllık ücret", "Jahresgebühr"),
    "Əməl": t("Action", "Действие", "İşlem", "Aktion"),
    "Bu sətir silinsin?": t("Delete this row?", "Удалить эту строку?", "Bu satır silinsin mi?", "Diese Zeile löschen?"),
    "Sil": t("Delete", "Удалить", "Kaldır", "Löschen"),
    "Cədvəl boşdur": t("The table is empty", "Таблица пуста", "Tablo boş", "Die Tabelle ist leer"),
    "Sətir olmayanda tələbə «Məbləği Mühasibatlıqdan öyrənin» görür.": t(
        "Without a row the student sees “Ask Accounting for the amount”.",
        "Если строки нет, студент видит «Уточните сумму в бухгалтерии».",
        "Satır yoksa öğrenci «Tutarı Muhasebeden öğrenin» görür.",
        "Ohne Zeile sieht der/die Studierende „Erfragen Sie den Betrag bei der Buchhaltung“.",
    ),
    "Əmr / qərar №": t(
        "Order / decision no.", "№ приказа / решения", "Emir / karar no.", "Anordnung / Entscheidung Nr."
    ),
    "Əmr tarixi": t("Order date", "Дата приказа", "Emir tarihi", "Datum der Anordnung"),
    "və ya qərar sənədi": t(
        "or a decision document", "или документ решения", "veya karar belgesi", "oder ein Entscheidungsdokument"
    ),
    "Qaytarılma yoxdur: sistem məbləği geri qaytarmır, yalnız qərar qeyd olunur.": t(
        "No refund: the system does not return the amount; only the decision is recorded.",
        "Возврата нет: система не возвращает сумму, фиксируется только решение.",
        "İade yok: sistem tutarı geri ödemez, yalnızca karar kaydedilir.",
        "Keine Erstattung: das System zahlt den Betrag nicht zurück, nur die Entscheidung wird erfasst.",
    ),
    "Bağlanış qərarı": t("Closure decision", "Решение о закрытии", "Kapatma kararı", "Schließungsentscheidung"),
    "Sənəd": t("Document", "Документ", "Belge", "Dokument"),
    "Qərarla geri götür": t(
        "Withdraw by decision", "Отозвать по решению", "Kararla geri çek", "Per Entscheidung zurückziehen"
    ),
    "Qərarla rədd et": t("Reject by decision", "Отклонить по решению", "Kararla reddet", "Per Entscheidung ablehnen"),
}


# Müstəqil rəyin düzəlişləri (2026-10-19): bağlanışda cəhdin geri alınması, pəncərə, tədris ili, məbləğ.
ENTRIES[RT].update(
    {
        "Pəncərə yalnız cari və ya gələcək dövr üçün açılır.": t(
            "A window can only be opened for the current or an upcoming period.",
            "Окно можно открыть только для текущего или будущего периода.",
            "Başvuru dönemi yalnızca mevcut veya gelecek dönem için açılabilir.",
            "Ein Fenster kann nur für den aktuellen oder einen künftigen Zeitraum geöffnet werden.",
        ),
        "Bu tədris ili üçün hələ akademik dövr yoxdur — sətir dövr yaradılanda işləyəcək.": t(
            "There is no academic period for this academic year yet — the row takes effect once the period is created.",
            "Для этого учебного года ещё нет академического периода — строка заработает, когда период будет создан.",
            "Bu akademik yıl için henüz akademik dönem yok — satır dönem oluşturulunca geçerli olacak.",
            "Für dieses Studienjahr gibt es noch keinen Studienabschnitt — die Zeile gilt, sobald er angelegt ist.",
        ),
        "Ödənilən məbləğ 0-dan böyük olmalıdır.": t(
            "The amount paid must be greater than 0.",
            "Оплаченная сумма должна быть больше 0.",
            "Ödenen tutar 0'dan büyük olmalıdır.",
            "Der gezahlte Betrag muss größer als 0 sein.",
        ),
        "Tədris ili «2026/2027» formatında olmalıdır.": t(
            "The academic year must be in the “2026/2027” format.",
            "Учебный год должен быть в формате «2026/2027».",
            "Akademik yıl «2026/2027» biçiminde olmalıdır.",
            "Das Studienjahr muss im Format „2026/2027“ angegeben werden.",
        ),
        "İmtahan cəhdi geri alına bilmir — imtahan cəhdi açılmış müraciət hələ bağlanmır.": t(
            "The exam attempt cannot be revoked — an application with an opened exam attempt cannot be closed yet.",
            "Попытку экзамена нельзя отозвать — заявку с открытой попыткой пока нельзя закрыть.",
            "Sınav denemesi geri alınamıyor — sınav denemesi açılmış başvuru henüz kapatılamaz.",
            "Der Prüfungsversuch kann nicht zurückgenommen werden — ein Antrag mit freigegebenem Versuch "
            "kann noch nicht geschlossen werden.",
        ),
        "(%(year)s tədris ilinin haqqı ilə)": t(
            "(at the %(year)s academic-year fee)",
            "(по плате за %(year)s учебный год)",
            "(%(year)s akademik yılı ücretiyle)",
            "(nach der Gebühr des Studienjahrs %(year)s)",
        ),
        "Müraciət pəncərəsi bağlıdır — imtahan mərkəzi açanda burada görünəcək": t(
            "The application window is closed — it will appear here when the exam centre opens it",
            "Приём заявок закрыт — когда экзаменационный центр откроет окно, оно появится здесь",
            "Başvuru dönemi kapalı — Sınav merkezi açtığında burada görünecek",
            "Das Antragsfenster ist geschlossen — sobald das Prüfungszentrum es öffnet, erscheint es hier",
        ),
        "Hələ pəncərə açılmayıb — müraciət qəbulu üçün pəncərə açın": t(
            "No window has been opened yet — open one to accept applications",
            "Окно ещё не открывалось — откройте его, чтобы принимать заявки",
            "Henüz dönem açılmadı — başvuru almak için bir dönem açın",
            "Es wurde noch kein Fenster geöffnet — öffnen Sie eines, um Anträge anzunehmen",
        ),
        "Tələbələr hazırda 25%% və alt qrup müraciəti göndərə bilmir. Aşağıdakı formadan dövrü seçib pəncərəni açın.": t(
            "Students cannot send 25%% or subgroup applications right now. Choose the period in the form below and "
            "open the window.",
            "Сейчас студенты не могут подавать заявки на 25%% и в подгруппу. Выберите период в форме ниже и "
            "откройте окно.",
            "Öğrenciler şu anda %%25 ve alt grup başvurusu gönderemiyor. Aşağıdaki formdan dönemi seçip başvuru "
            "dönemini açın.",
            "Studierende können derzeit keine 25-%%- oder Untergruppenanträge stellen. Wählen Sie unten den "
            "Zeitraum und öffnen Sie das Fenster.",
        ),
        "Cari və ya gələcək akademik dövr yoxdur — əvvəlcə dövr yaradılmalıdır.": t(
            "There is no current or upcoming academic period — create a period first.",
            "Нет текущего или будущего академического периода — сначала создайте период.",
            "Mevcut veya gelecek akademik dönem yok — önce bir dönem oluşturulmalıdır.",
            "Es gibt keinen aktuellen oder künftigen Studienabschnitt — legen Sie zuerst einen an.",
        ),
        "sistem (vaxtı bitdi)": t(
            "system (expired)", "система (срок истёк)", "sistem (süresi doldu)", "System (abgelaufen)"
        ),
    }
)
ENTRIES["exams.second_chance.error"] = {
    "Tələbə «{exam}» imtahanında hazırda cəhd edir — cəhd bitməmiş müraciət bağlanmır.": t(
        "The student is currently taking “{exam}” — the application cannot be closed until the attempt ends.",
        "Студент сейчас проходит «{exam}» — заявку нельзя закрыть, пока попытка не завершена.",
        "Öğrenci şu anda «{exam}» sınavına giriyor — deneme bitmeden başvuru kapatılamaz.",
        "Der Prüfungsversuch in „{exam}“ läuft gerade — der Antrag kann erst nach Ende des Versuchs "
        "geschlossen werden.",
    ),
    "Tələbənin «{exam}» imtahanındakı cəhdi hələ yoxlanmayıb — əvvəlcə yoxlanmalıdır.": t(
        "The student's attempt in “{exam}” has not been graded yet — it must be graded first.",
        "Попытка студента в «{exam}» ещё не проверена — сначала её нужно проверить.",
        "Öğrencinin «{exam}» sınavındaki denemesi henüz değerlendirilmedi — önce değerlendirilmelidir.",
        "Der Versuch in „{exam}“ ist noch nicht bewertet — er muss zuerst bewertet werden.",
    ),
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
