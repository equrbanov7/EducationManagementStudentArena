#!/usr/bin/env python3
"""EMSArena i18n — «İmtahan balının daxil edilməsi»: midterm / final, sütunlar, 15 dəqiqə, apellyasiya, qaralama
(sahib 2026-10-25).

msgid AZ cümlədir → az msgstr = msgid (``az`` açarı verilibsə o). İdempotentdir (mövcud msgctxt+msgid
toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ESE = "registrar.exam_score_entry"
RS = "core.runtime_settings"


def t(en, ru, tr, de, az=None):
    data = {"en": en, "ru": ru, "tr": tr, "de": de}
    if az is not None:
        data["az"] = az
    return data


ENTRIES = {
    RS: {
        "Kağız imtahan nəticəsinin tələbəyə görünmə gecikməsi": t(
            "Delay before a paper exam result is shown to the student",
            "Задержка показа студенту результата бумажного экзамена",
            "Kâğıt sınav sonucunun öğrenciye gösterilme gecikmesi",
            "Verzögerung, bis das Ergebnis einer Papierprüfung dem Studierenden angezeigt wird",
        ),
        "Yazılı / praktiki (kağız) midterm və final nəticəsi təsdiqdən bu qədər saat sonra tələbə kabinetində "
        "görünür. 0 — dərhal.": t(
            "A written / practical (paper) midterm or final result appears in the student cabinet this many hours "
            "after confirmation. 0 — immediately.",
            "Результат письменного / практического (бумажного) мидтерма и финала появляется в кабинете студента "
            "через указанное число часов после подтверждения. 0 — сразу.",
            "Yazılı / uygulamalı (kâğıt) ara sınav ve final sonucu onaydan bu kadar saat sonra öğrenci panelinde "
            "görünür. 0 — hemen.",
            "Ein schriftliches / praktisches (Papier-)Midterm- oder Final-Ergebnis erscheint so viele Stunden nach "
            "der Bestätigung im Studierendenbereich. 0 — sofort.",
        ),
        "«İmtahan balının daxil edilməsi» ekranında balı daxil edən təsdiqdən sonra bu qədər dəqiqə ərzində onu "
        "sənədsiz dəyişə bilər. Müddət bitəndən sonra bal yalnız apellyasiya (sənəd məcburi) və ya RİM "
        "rəhbərinin təqdimat əsasında düzəlişi ilə dəyişir.": t(
            "On the «Entry of exam score» screen the person who entered a score can change it without a document "
            "for this many minutes after confirmation. Afterwards the score changes only through an appeal "
            "(document required) or a correction by the head of RİM based on a submission.",
            "На экране «Ввод экзаменационного балла» внёсший балл может изменить его без документа в течение "
            "указанного числа минут после подтверждения. После этого балл меняется только через апелляцию "
            "(документ обязателен) или исправление руководителем РİМ на основании представления.",
            "«Sınav puanı girişi» ekranında puanı giren kişi onaydan sonra bu kadar dakika içinde belgesiz "
            "değiştirebilir. Süre bitince puan yalnızca itiraz (belge zorunlu) veya RİM başkanının yazılı talebe "
            "dayalı düzeltmesiyle değişir.",
            "Auf der Seite «Eingabe der Prüfungspunkte» kann die eingebende Person die Punktzahl so viele Minuten "
            "nach der Bestätigung ohne Dokument ändern. Danach ändert sie sich nur per Einspruch (Dokument "
            "erforderlich) oder durch eine Korrektur der RİM-Leitung auf Antrag.",
        ),
        "İmtahan balını təsdiqdən sonra dəyişmə müddəti": t(
            "Time to change an exam score after confirmation",
            "Время на изменение экзаменационного балла после подтверждения",
            "Onaydan sonra sınav puanını değiştirme süresi",
            "Zeitraum zum Ändern der Prüfungspunkte nach der Bestätigung",
        ),
    },
    "registrar.exam_assessment": {
        "Final": t("Final", "Финал", "Final", "Final", az="Final"),
        "Midterm": t("Midterm", "Мидтерм", "Ara sınav", "Midterm", az="Midterm"),
    },
    "registrar.exam_score_entry_kind": {
        "Edit within 15 minutes": t(
            "Edit within 15 minutes",
            "Исправление в течение 15 минут",
            "15 dakika içinde düzeltme",
            "Korrektur innerhalb von 15 Minuten",
            az="15 dəqiqə ərzində düzəliş",
        ),
    },
    "registrar.exam_score_entry.state": {
        "Yekun": t("Final", "Итог", "Kesin", "Endgültig"),
    },
    "registrar.journal": {
        "nəticə %(when)s-də görünəcək": t(
            "result visible at %(when)s",
            "результат будет виден %(when)s",
            "sonuç %(when)s tarihinde görünecek",
            "Ergebnis sichtbar ab %(when)s",
        ),
    },
    ESE: {
        "%(t)s-dək": t("until %(t)s", "до %(t)s", "%(t)s'e kadar", "bis %(t)s"),
        "Apellyasiya ilə dəyiş": t(
            "Change by appeal", "Изменить по апелляции", "İtirazla değiştir", "Per Einspruch ändern"
        ),
        "Apellyasiya ilə dəyişiklik üçün apellyasiya sənədi yüklənməlidir.": t(
            "A change by appeal requires the appeal document to be uploaded.",
            "Для изменения по апелляции нужно загрузить документ апелляции.",
            "İtirazla değişiklik için itiraz belgesi yüklenmelidir.",
            "Für eine Änderung per Einspruch muss das Einspruchsdokument hochgeladen werden.",
        ),
        "Apellyasiya ilə dəyişiklik üçün apellyasiya sənədini seçin.": t(
            "Select the appeal document for a change by appeal.",
            "Выберите документ апелляции для изменения по апелляции.",
            "İtirazla değişiklik için itiraz belgesini seçin.",
            "Wählen Sie das Einspruchsdokument für die Änderung per Einspruch.",
        ),
        "Apellyasiya ilə dəyişiklik — apellyasiya sənədi (qərar / ərizə) MƏCBURİDİR. Dəyişiklik «apellyasiya» kimi "
        "işarələnir: kim, köhnə → yeni bal, nə vaxt — tarixçədə görünür.": t(
            "Change by appeal — the appeal document (decision / application) is REQUIRED. The change is marked as "
            "«appeal»: who, old → new score and when are shown in the history.",
            "Изменение по апелляции — документ апелляции (решение / заявление) ОБЯЗАТЕЛЕН. Изменение помечается "
            "как «апелляция»: кто, старый → новый балл, когда — видно в истории.",
            "İtirazla değişiklik — itiraz belgesi (karar / dilekçe) ZORUNLUDUR. Değişiklik «itiraz» olarak "
            "işaretlenir: kim, eski → yeni puan, ne zaman — geçmişte görünür.",
            "Änderung per Einspruch — das Einspruchsdokument (Entscheidung / Antrag) ist PFLICHT. Die Änderung wird "
            "als «Einspruch» markiert: wer, alte → neue Punktzahl, wann — im Verlauf sichtbar.",
        ),
        "Apellyasiya rejimi: «Yekun» ballar açıldı. Yadda saxlayanda apellyasiya sənədi məcburidir.": t(
            "Appeal mode: «Final» scores are unlocked. The appeal document is required when saving.",
            "Режим апелляции: «итоговые» баллы открыты. При сохранении документ апелляции обязателен.",
            "İtiraz modu: «Kesin» puanlar açıldı. Kaydederken itiraz belgesi zorunludur.",
            "Einspruchsmodus: «endgültige» Punkte sind entsperrt. Beim Speichern ist das Einspruchsdokument Pflicht.",
        ),
        "Balı daxil edən": t("Entered by", "Балл внёс", "Puanı giren", "Eingegeben von"),
        "Balın daxil edilmə tarixi": t("Date of entry", "Дата ввода балла", "Puanın giriş tarihi", "Eingabedatum"),
        "Boş buraxılan sahə toxunulmur. Təsdiqdən sonra %(w)s ərzində dəyişə bilərsiniz; sonra yalnız apellyasiya və "
        "ya RİM təqdimatı ilə.": t(
            "Empty fields are left untouched. You can change scores for %(w)s after confirmation; afterwards only by "
            "appeal or a RİM submission.",
            "Пустые поля не затрагиваются. После подтверждения можно менять в течение %(w)s; затем только по "
            "апелляции или представлению в РİМ.",
            "Boş bırakılan alan değiştirilmez. Onaydan sonra %(w)s içinde değiştirebilirsiniz; sonra yalnızca itiraz "
            "veya RİM talebiyle.",
            "Leere Felder bleiben unverändert. Nach der Bestätigung können Sie %(w)s lang ändern; danach nur per "
            "Einspruch oder RİM-Antrag.",
        ),
        "Bu semestrdə midterm yoxdur (kollokvium rejimi) — yalnız final.": t(
            "This semester has no midterm (colloquium mode) — final only.",
            "В этом семестре нет мидтерма (режим коллоквиумов) — только финал.",
            "Bu dönemde ara sınav yok (kolokyum modu) — yalnızca final.",
            "In diesem Semester gibt es kein Midterm (Kolloquiumsmodus) — nur Final.",
        ),
        "Bərabər böl": t("Split equally", "Разделить поровну", "Eşit böl", "Gleichmäßig aufteilen"),
        "Cəm": t("Total", "Сумма", "Toplam", "Summe"),
        "Daxil etdiyiniz ballar hələ sistemə yazılmayıb (qaralama saxlanılıb). Səhifədən çıxmaq istəyirsiniz?": t(
            "The scores you entered are not recorded yet (a draft is saved). Do you want to leave the page?",
            "Введённые баллы ещё не записаны в систему (черновик сохранён). Покинуть страницу?",
            "Girdiğiniz puanlar henüz sisteme kaydedilmedi (taslak saklandı). Sayfadan çıkmak istiyor musunuz?",
            "Die eingegebenen Punkte sind noch nicht gespeichert (Entwurf gesichert). Seite verlassen?",
        ),
        "Dəyişiklik rejimi": t("Change mode", "Режим изменения", "Değişiklik modu", "Änderungsmodus"),
        "Dəyişmək üçün rejim seçin:": t(
            "Choose a mode to change them:",
            "Чтобы изменить, выберите режим:",
            "Değiştirmek için mod seçin:",
            "Wählen Sie zum Ändern einen Modus:",
        ),
        "FİNAL (maks %(cap)s)": t(
            "FINAL (max %(cap)s)", "ФИНАЛ (макс. %(cap)s)", "FİNAL (maks. %(cap)s)", "FINAL (max. %(cap)s)"
        ),
        "Hər sütunun maksimum balı yazılmalıdır.": t(
            "Enter the maximum score of every column.",
            "Укажите максимальный балл каждого столбца.",
            "Her sütunun azami puanı yazılmalıdır.",
            "Geben Sie die Höchstpunktzahl jeder Spalte an.",
        ),
        "Hər sütunun maksimumu 1 ilə tavan arasında tam ədəd olmalıdır.": t(
            "Each column maximum must be a whole number between 1 and the cap.",
            "Максимум каждого столбца — целое число от 1 до предела.",
            "Her sütunun azamisi 1 ile tavan arasında tam sayı olmalıdır.",
            "Das Maximum jeder Spalte muss eine ganze Zahl zwischen 1 und der Obergrenze sein.",
        ),
        "Jurnal bağlıdır (dərc olunub) — midterm balı yazıla bilməz. RİM-ə müraciət edin.": t(
            "The journal is closed (published) — the midterm score cannot be written. Contact RİM.",
            "Журнал закрыт (опубликован) — балл мидтерма нельзя записать. Обратитесь в РİМ.",
            "Defter kapalı (yayımlandı) — ara sınav puanı yazılamaz. RİM'e başvurun.",
            "Das Journal ist geschlossen (veröffentlicht) — die Midterm-Punktzahl kann nicht eingetragen werden. "
            "Wenden Sie sich an RİM.",
        ),
        "Kağız midterm (İmtahan Mərkəzi)": t(
            "Paper midterm (Exam Centre)",
            "Бумажный мидтерм (Экзаменационный центр)",
            "Kâğıt ara sınav (Sınav Merkezi)",
            "Papier-Midterm (Prüfungszentrum)",
        ),
        "Midterm balı": t("Midterm score", "Балл мидтерма", "Ara sınav puanı", "Midterm-Punktzahl"),
        "Midterm balı elektron jurnalın «Midterm» xanasına yazılır — müəllim onu jurnalda dəyişə bilmir.": t(
            "The midterm score is written to the «Midterm» cell of the e-journal — the teacher cannot change it there.",
            "Балл мидтерма записывается в ячейку «Midterm» электронного журнала — преподаватель не может его изменить.",
            "Ara sınav puanı e-defterin «Midterm» hücresine yazılır — öğretmen onu defterde değiştiremez.",
            "Die Midterm-Punktzahl wird in die Zelle «Midterm» des E-Journals geschrieben — die Lehrkraft kann sie "
            "dort nicht ändern.",
        ),
        "MİDTERM (maks %(cap)s)": t(
            "MIDTERM (max %(cap)s)", "МИДТЕРМ (макс. %(cap)s)", "ARA SINAV (maks. %(cap)s)", "MIDTERM (max. %(cap)s)"
        ),
        "Nəticə tələbə kabinetində təsdiqdən %(h)s saat sonra görünür.": t(
            "The result appears in the student cabinet %(h)s hours after confirmation.",
            "Результат появится в кабинете студента через %(h)s ч после подтверждения.",
            "Sonuç, onaydan %(h)s saat sonra öğrenci panelinde görünür.",
            "Das Ergebnis erscheint %(h)s Stunden nach der Bestätigung im Studierendenbereich.",
        ),
        "Nəticə tələbə kabinetində təsdiqdən dərhal sonra görünür.": t(
            "The result appears in the student cabinet right after confirmation.",
            "Результат появится в кабинете студента сразу после подтверждения.",
            "Sonuç, onaydan hemen sonra öğrenci panelinde görünür.",
            "Das Ergebnis erscheint direkt nach der Bestätigung im Studierendenbereich.",
        ),
        "Qal": t("Stay", "Остаться", "Kal", "Bleiben"),
        "Qaralama saxlanıldı": t("Draft saved", "Черновик сохранён", "Taslak kaydedildi", "Entwurf gespeichert"),
        "Qaralamanı sil": t("Discard draft", "Удалить черновик", "Taslağı sil", "Entwurf verwerfen"),
        "Rejimdən çıx": t("Exit mode", "Выйти из режима", "Moddan çık", "Modus beenden"),
        "RİM təqdimatı ilə düzəliş": t(
            "Correction by RİM submission",
            "Исправление по представлению РİМ",
            "RİM talebiyle düzeltme",
            "Korrektur per RİM-Antrag",
        ),
        "RİM təqdimatı ilə düzəliş — səbəb, qeyd və skan edilmiş sənəd üçü də məcburidir və audit olunur.": t(
            "Correction by RİM submission — reason, note and a scanned document are all required and audited.",
            "Исправление по представлению РİМ — причина, примечание и скан документа обязательны и аудируются.",
            "RİM talebiyle düzeltme — neden, not ve taranmış belge üçü de zorunludur ve denetlenir.",
            "Korrektur per RİM-Antrag — Grund, Notiz und gescanntes Dokument sind Pflicht und werden protokolliert.",
        ),
        "RİM təqdimatı rejimi: «Yekun» ballar açıldı. Yadda saxlayanda səbəb, qeyd və sənəd məcburidir.": t(
            "RİM submission mode: «Final» scores are unlocked. Reason, note and document are required when saving.",
            "Режим представления РİМ: «итоговые» баллы открыты. При сохранении нужны причина, примечание и документ.",
            "RİM talep modu: «Kesin» puanlar açıldı. Kaydederken neden, not ve belge zorunludur.",
            "RİM-Antragsmodus: «endgültige» Punkte sind entsperrt. Beim Speichern sind Grund, Notiz und Dokument "
            "Pflicht.",
        ),
        "S%(n)s sütununun maksimumu 1 ilə %(max)s arasında olmalıdır.": t(
            "The maximum of column S%(n)s must be between 1 and %(max)s.",
            "Максимум столбца S%(n)s должен быть от 1 до %(max)s.",
            "S%(n)s sütununun azamisi 1 ile %(max)s arasında olmalıdır.",
            "Das Maximum der Spalte S%(n)s muss zwischen 1 und %(max)s liegen.",
        ),
        "Sistem semestr təqviminə görə «%(name)s» seçdi — lazım olsa dəyişin.": t(
            "The system chose «%(name)s» from the semester calendar — change it if needed.",
            "Система выбрала «%(name)s» по календарю семестра — при необходимости измените.",
            "Sistem dönem takvimine göre «%(name)s» seçti — gerekirse değiştirin.",
            "Das System hat anhand des Semesterkalenders «%(name)s» gewählt — bei Bedarf ändern.",
        ),
        "Skan edilmiş sənəd (təqdimat / apellyasiya)": t(
            "Scanned document (submission / appeal)",
            "Скан документа (представление / апелляция)",
            "Taranmış belge (talep / itiraz)",
            "Gescanntes Dokument (Antrag / Einspruch)",
        ),
        "Suallar": t("Questions", "Вопросы", "Sorular", "Fragen"),
        "Sütun sayı %(max)s-dən çox ola bilməz.": t(
            "There cannot be more than %(max)s columns.",
            "Столбцов не может быть больше %(max)s.",
            "Sütun sayısı %(max)s'den fazla olamaz.",
            "Es darf nicht mehr als %(max)s Spalten geben.",
        ),
        "Sütun sayı 10-dan çox ola bilməz.": t(
            "There cannot be more than 10 columns.",
            "Столбцов не может быть больше 10.",
            "Sütun sayısı 10'dan fazla olamaz.",
            "Es darf nicht mehr als 10 Spalten geben.",
        ),
        "Sütun əlavə et": t("Add column", "Добавить столбец", "Sütun ekle", "Spalte hinzufügen"),
        "Sütunlar (suallar) və maksimum balları": t(
            "Columns (questions) and their maximum scores",
            "Столбцы (вопросы) и их максимальные баллы",
            "Sütunlar (sorular) ve azami puanları",
            "Spalten (Fragen) und ihre Höchstpunktzahlen",
        ),
        "Sütunların cəmi tavana bərabər deyil — əvvəlcə sütunları düzəldin.": t(
            "The columns do not add up to the cap — fix the columns first.",
            "Сумма столбцов не равна пределу — сначала исправьте столбцы.",
            "Sütunların toplamı tavana eşit değil — önce sütunları düzeltin.",
            "Die Spalten ergeben nicht die Obergrenze — korrigieren Sie zuerst die Spalten.",
        ),
        "Sütunların maksimum cəmi %(cap)s olmalıdır (indi %(total)s).": t(
            "The column maximums must add up to %(cap)s (now %(total)s).",
            "Сумма максимумов столбцов должна быть %(cap)s (сейчас %(total)s).",
            "Sütun azamilerinin toplamı %(cap)s olmalıdır (şu an %(total)s).",
            "Die Spaltenmaxima müssen %(cap)s ergeben (derzeit %(total)s).",
        ),
        "Sütunların maksimum cəmi həmişə %(cap)s olmalıdır — uyğun gəlmirsə ballar yadda saxlanmır. «Bərabər böl» "
        "balı tam ədədlərlə bölür, qalıq sonuncu sütuna düşür.": t(
            "The column maximums must always add up to %(cap)s — otherwise the scores are not saved. «Split "
            "equally» divides the points in whole numbers; the remainder goes to the last column.",
            "Сумма максимумов столбцов всегда должна быть %(cap)s — иначе баллы не сохраняются. «Разделить "
            "поровну» делит баллы целыми числами, остаток — в последний столбец.",
            "Sütun azamilerinin toplamı her zaman %(cap)s olmalıdır — uymazsa puanlar kaydedilmez. «Eşit böl» "
            "puanı tam sayılarla böler, kalan son sütuna düşer.",
            "Die Spaltenmaxima müssen immer %(cap)s ergeben — sonst werden die Punkte nicht gespeichert. "
            "«Gleichmäßig aufteilen» teilt in ganzen Zahlen auf, der Rest geht in die letzte Spalte.",
        ),
        "Sütunların maksimum cəmi tavana bərabər olmalıdır — indi": t(
            "The column maximums must equal the cap — now",
            "Сумма максимумов столбцов должна равняться пределу — сейчас",
            "Sütun azamilerinin toplamı tavana eşit olmalıdır — şu an",
            "Die Spaltenmaxima müssen der Obergrenze " "entsprechen — derzeit",
        ),
        "Sütunu sil": t("Remove column", "Удалить столбец", "Sütunu sil", "Spalte entfernen"),
        "Sütunun maksimum balı": t("Column maximum", "Максимум столбца", "Sütunun azami puanı", "Spaltenmaximum"),
        "Sütunun maksimum balı tam ədəd olmalıdır.": t(
            "The column maximum must be a whole number.",
            "Максимум столбца должен быть целым числом.",
            "Sütunun azami puanı tam sayı olmalıdır.",
            "Das Spaltenmaximum muss eine ganze Zahl sein.",
        ),
        "Tələbə nəticəni %(h)s saat sonra görəcək.": t(
            "The student will see the result in %(h)s hours.",
            "Студент увидит результат через %(h)s ч.",
            "Öğrenci sonucu %(h)s saat sonra görecek.",
            "Der Studierende sieht das Ergebnis in %(h)s Stunden.",
        ),
        "Təqdimat əsasında düzəliş yalnız RİM rəhbəri tərəfindən edilir — apellyasiya seçin.": t(
            "A correction based on a submission is made only by the head of RİM — choose appeal.",
            "Исправление по представлению делает только руководитель РİМ — выберите апелляцию.",
            "Talebe dayalı düzeltmeyi yalnızca RİM başkanı yapar — itirazı seçin.",
            "Eine Korrektur auf Antrag nimmt nur die RİM-Leitung vor — wählen Sie Einspruch.",
        ),
        "Təqvimə görə defolt: «%(name)s». Siz başqa imtahanı seçmisiniz.": t(
            "Calendar default: «%(name)s». You have chosen another exam.",
            "По календарю по умолчанию: «%(name)s». Вы выбрали другой экзамен.",
            "Takvime göre varsayılan: «%(name)s». Başka bir sınav seçtiniz.",
            "Kalender-Standard: «%(name)s». Sie haben eine andere Prüfung gewählt.",
        ),
        "Təsdiqdən %(w)s keçib — bal yalnız apellyasiya (sənəd məcburi) və ya RİM rəhbərinin təqdimat əsasında "
        "düzəlişi ilə dəyişdirilə bilər.": t(
            "More than %(w)s have passed since confirmation — the score can only be changed by appeal (document "
            "required) or a correction by the head of RİM based on a submission.",
            "С подтверждения прошло больше %(w)s — балл можно изменить только по апелляции (документ обязателен) "
            "или исправлением руководителя РİМ на основании представления.",
            "Onaydan bu yana %(w)s geçti — puan yalnızca itiraz (belge zorunlu) veya RİM başkanının talebe dayalı "
            "düzeltmesiyle değiştirilebilir.",
            "Seit der Bestätigung sind mehr als %(w)s vergangen — die Punktzahl kann nur per Einspruch (Dokument "
            "erforderlich) oder durch eine Korrektur der RİM-Leitung auf Antrag geändert werden.",
        ),
        "Təsdiqdən sonra %(w)s ərzində balı dəyişə bilərsiniz; sonra yalnız apellyasiya (sənəd məcburi) və ya RİM "
        "rəhbərinin təqdimatı ilə.": t(
            "You can change the score for %(w)s after confirmation; afterwards only by appeal (document required) or "
            "a submission to the head of RİM.",
            "После подтверждения балл можно менять в течение %(w)s; затем только по апелляции (документ обязателен) "
            "или по представлению руководителю РİМ.",
            "Onaydan sonra %(w)s içinde puanı değiştirebilirsiniz; sonra yalnızca itiraz (belge zorunlu) veya RİM "
            "başkanına talep ile.",
            "Nach der Bestätigung können Sie die Punktzahl %(w)s lang ändern; danach nur per Einspruch (Dokument "
            "erforderlich) oder Antrag an die RİM-Leitung.",
        ),
        "Təsdiqdən sonra %(w)s ərzində bu balları dəyişə bilərsiniz; sonra yalnız təqdimat əsasında RİM tərəfindən "
        "və ya apellyasiya ilə.": t(
            "You can change these scores for %(w)s after confirmation; afterwards only by RİM based on a submission "
            "or by appeal.",
            "После подтверждения эти баллы можно менять в течение %(w)s; затем только РİМ по представлению или по "
            "апелляции.",
            "Onaydan sonra %(w)s içinde bu puanları değiştirebilirsiniz; sonra yalnızca talebe dayalı RİM "
            "tarafından veya itirazla.",
            "Nach der Bestätigung können Sie diese Punkte %(w)s lang ändern; danach nur durch RİM auf Antrag oder "
            "per Einspruch.",
        ),
        "Vərəqin və bütün sətirlərinin növü.": t(
            "The type of the sheet and all its rows.",
            "Тип листа и всех его строк.",
            "Sayfanın ve tüm satırlarının türü.",
            "Art des Blatts und aller seiner Zeilen.",
        ),
        "Yadda saxlamamısınız": t("You have not saved", "Вы не сохранили", "Kaydetmediniz", "Nicht gespeichert"),
        "Yadda saxlanmamış qaralama bərpa olundu": t(
            "An unsaved draft was restored",
            "Восстановлен несохранённый черновик",
            "Kaydedilmemiş taslak geri yüklendi",
            "Ein ungespeicherter Entwurf wurde wiederhergestellt",
        ),
        "Yazılı / praktiki": t(
            "Written / practical", "Письменный / практический", "Yazılı / uygulamalı", "Schriftlich / praktisch"
        ),
        "Yekun təsdiq: yoxlayın, yoxlanma tarixini seçin və təsdiq edin — ballar sistemə (jurnala) yazılır.": t(
            "Final confirmation: review, pick the checking date and confirm — the scores are recorded in the system "
            "(journal).",
            "Окончательное подтверждение: проверьте, выберите дату проверки и подтвердите — баллы записываются в "
            "систему (журнал).",
            "Kesin onay: kontrol edin, kontrol tarihini seçin ve onaylayın — puanlar sisteme (deftere) yazılır.",
            "Endgültige Bestätigung: prüfen, Korrekturdatum wählen und bestätigen — die Punkte werden ins System "
            "(Journal) übernommen.",
        ),
        "Yoxlanma tarixi gələcək tarix ola bilməz.": t(
            "The checking date cannot be in the future.",
            "Дата проверки не может быть в будущем.",
            "Kontrol tarihi gelecekte olamaz.",
            "Das Korrekturdatum darf nicht in der Zukunft liegen.",
        ),
        "avtomatik": t("automatic", "автоматически", "otomatik", "automatisch"),
        "bu semestrdə yoxdur": t(
            "not in this semester", "нет в этом семестре", "bu dönemde yok", "nicht in diesem Semester"
        ),
        "dəyişmək olar": t("editable", "можно изменить", "değiştirilebilir", "änderbar"),
        "dəyişmək üçün qalıb": t(
            "left to edit", "осталось для изменения", "değiştirmek için kalan", "verbleibend zum Ändern"
        ),
        "təqvimə görə": t("per calendar", "по календарю", "takvime göre", "laut Kalender"),
        "yoxlanıb": t("checked", "проверено", "kontrol edildi", "korrigiert"),
        "«Yekun» bal: %(n)s tələbə.": t(
            "«Final» scores: %(n)s students.",
            "«Итоговые» баллы: %(n)s студ.",
            "«Kesin» puan: %(n)s öğrenci.",
            "«Endgültige» Punkte: %(n)s Studierende.",
        ),
        "Çıx": t("Leave", "Выйти", "Çık", "Verlassen"),
        "İlk daxiletmədə opsionaldır; apellyasiya və ya RİM təqdimatı ilə dəyişiklikdə MƏCBURİDİR (təsdiq "
        "dialoqunda da seçmək olar).": t(
            "Optional on first entry; REQUIRED for a change by appeal or RİM submission (can also be chosen in the "
            "confirmation dialog).",
            "Необязательно при первом вводе; ОБЯЗАТЕЛЬНО при изменении по апелляции или представлению РİМ (можно "
            "выбрать и в окне подтверждения).",
            "İlk girişte isteğe bağlı; itiraz veya RİM talebiyle değişiklikte ZORUNLU (onay penceresinde de "
            "seçilebilir).",
            "Bei der Ersteingabe optional; PFLICHT bei Änderung per Einspruch oder RİM-Antrag (auch im "
            "Bestätigungsdialog wählbar).",
        ),
        "İmtahan növü midterm və ya final olmalıdır.": t(
            "The exam type must be midterm or final.",
            "Тип экзамена должен быть мидтерм или финал.",
            "Sınav türü ara sınav veya final olmalıdır.",
            "Die Prüfungsart muss Midterm oder Final sein.",
        ),
        "İmtahanın yoxlanma tarixi": t(
            "Date the exam was checked",
            "Дата проверки экзамена",
            "Sınavın kontrol tarihi",
            "Korrekturdatum der Prüfung",
        ),
        "İmtahanın yoxlanma tarixini seçin (gələcək tarix olmaz).": t(
            "Choose the date the exam was checked (not in the future).",
            "Выберите дату проверки экзамена (не в будущем).",
            "Sınavın kontrol tarihini seçin (gelecek tarih olamaz).",
            "Wählen Sie das Korrekturdatum (nicht in der Zukunft).",
        ),
        "Ən azı bir sütun (sual) olmalıdır.": t(
            "There must be at least one column (question).",
            "Должен быть хотя бы один столбец (вопрос).",
            "En az bir sütun (soru) olmalıdır.",
            "Es muss mindestens eine Spalte (Frage) geben.",
        ),
        "Ən azı bir sütun qalmalıdır.": t(
            "At least one column must remain.",
            "Должен остаться хотя бы один столбец.",
            "En az bir sütun kalmalıdır.",
            "Mindestens eine Spalte muss bleiben.",
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
            msgstr = translations.get("az", msgid) if lang == "az" else (translations.get(lang) or msgid)
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
