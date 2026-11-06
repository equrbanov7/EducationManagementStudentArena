#!/usr/bin/env python3
"""i18n — «Nəzarət otağı» + məcburi imtahan dili addımı (sahib 2026-11-06). İdempotent.

Hər (msgctxt, msgid) cütü az/en/ru/tr/de `django.po`-nun sonuna əlavə olunur (artıq varsa toxunulmur);
sonra `python manage.py compilemessages` ilə `.mo` yenilənir. msgid = AZ mətni.
"""

from __future__ import annotations

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

LS = "exams.language_step"
SR = "exams.supervision_room"

# (ctx, msgid): (en, ru, tr, de)
ENTRIES = {
    (LS, "Suallar seçdiyiniz dildə veriləcək. İmtahan başladıqdan sonra dili dəyişmək mümkün deyil."): (
        "Questions will be shown in the language you choose. The language cannot be changed after the exam starts.",
        "Вопросы будут показаны на выбранном языке. После начала экзамена язык изменить нельзя.",
        "Sorular seçtiğiniz dilde gösterilecek. Sınav başladıktan sonra dil değiştirilemez.",
        "Die Fragen werden in der gewählten Sprache angezeigt. Nach Prüfungsbeginn kann die Sprache nicht mehr geändert werden.",
    ),
    (LS, "məcburi"): ("required", "обязательно", "zorunlu", "Pflicht"),
    (LS, "İmtahan dili"): ("Exam language", "Язык экзамена", "Sınav dili", "Prüfungssprache"),
    (LS, "İmtahan dilini seçin"): (
        "Choose the exam language",
        "Выберите язык экзамена",
        "Sınav dilini seçin",
        "Prüfungssprache wählen",
    ),
    (LS, "İmtahana başlamaq üçün əvvəlcə imtahan dilini seçin."): (
        "Choose the exam language before starting the exam.",
        "Чтобы начать экзамен, сначала выберите язык экзамена.",
        "Sınava başlamak için önce sınav dilini seçin.",
        "Wählen Sie vor dem Start zuerst die Prüfungssprache.",
    ),
    (SR, "Ad və ya istifadəçi adı…"): (
        "Name or username…",
        "Имя или логин…",
        "Ad veya kullanıcı adı…",
        "Name oder Benutzername…",
    ),
    (SR, "Aktiv təşkilat seçilməyib."): (
        "No active organization selected.",
        "Активная организация не выбрана.",
        "Aktif kurum seçilmedi.",
        "Keine aktive Organisation ausgewählt.",
    ),
    (SR, "Bax"): ("View", "Просмотр", "Gör", "Ansehen"),
    (SR, "Bağla"): ("Close", "Закрыть", "Kapat", "Schließen"),
    (SR, "Bağlantı"): ("Connection", "Связь", "Bağlantı durumu", "Verbindung"),
    (SR, "Bağlantı yoxdur — yenidən cəhd edilir…"): (
        "No connection — retrying…",
        "Нет связи — повторная попытка…",
        "Bağlantı yok — yeniden deneniyor…",
        "Keine Verbindung — neuer Versuch…",
    ),
    (SR, "Başlayıb"): ("Started", "Начал", "Başladı", "Begonnen"),
    (SR, "Bitirib"): ("Finished", "Завершил", "Bitirdi", "Beendet"),
    (
        SR,
        "Bu imtahan imtahan mərkəzi zalında keçirilir — PIN, yenidən giriş və zal əməliyyatları zal monitorundadır.",
    ): (
        "This exam is held in an exam-centre hall — PINs, re-entry and hall actions are in the hall monitor.",
        "Этот экзамен проходит в зале экзаменационного центра — PIN, повторный вход и действия зала находятся в мониторе зала.",
        "Bu sınav sınav merkezi salonunda yapılır — PIN, yeniden giriş ve salon işlemleri salon monitöründedir.",
        "Diese Prüfung findet in einem Saal des Prüfungszentrums statt — PIN, Wiedereintritt und Saalaktionen sind im Saalmonitor.",
    ),
    (SR, "Bu imtahanda nəzarət rejimi aktiv deyil."): (
        "Proctoring is not enabled for this exam.",
        "Режим наблюдения для этого экзамена не включён.",
        "Bu sınavda gözetim modu etkin değil.",
        "Die Aufsicht ist für diese Prüfung nicht aktiviert.",
    ),
    (
        SR,
        "Bu imtahanda nəzarət rejimi yandırılmayıb: cəhdlərin gedişatı görünür, amma tam ekran/tab pozuntuları "
        "izlənmir. Yandırmaq üçün imtahanı redaktə edin.",
    ): (
        "Proctoring is off for this exam: progress is visible, but full-screen/tab violations are not tracked. "
        "Edit the exam to turn it on.",
        "Режим наблюдения для этого экзамена выключен: ход попыток виден, но нарушения полноэкранного режима/вкладок "
        "не отслеживаются. Чтобы включить, отредактируйте экзамен.",
        "Bu sınavda gözetim modu kapalı: ilerleme görünür, ancak tam ekran/sekme ihlalleri izlenmez. "
        "Açmak için sınavı düzenleyin.",
        "Die Aufsicht ist für diese Prüfung aus: Der Fortschritt ist sichtbar, Vollbild-/Tab-Verstöße werden aber "
        "nicht erfasst. Bearbeiten Sie die Prüfung, um sie einzuschalten.",
    ),
    (SR, "Bərpa et"): ("Restore", "Восстановить", "Geri yükle", "Wiederherstellen"),
    (SR, "Canlı"): ("Live", "В эфире", "Canlı izleme", "Live"),
    (SR, "Canlı izləmə, pozuntular və kilidlənənlərin bərpası"): (
        "Live monitoring, violations and restoring locked students",
        "Живое наблюдение, нарушения и восстановление заблокированных",
        "Canlı izleme, ihlaller ve kilitlenenlerin geri yüklenmesi",
        "Live-Überwachung, Verstöße und Freigabe gesperrter Studierender",
    ),
    (SR, "Cavablar"): ("Answers", "Ответы", "Cevaplar", "Antworten"),
    (SR, "Cəhdi bərpa etmək mümkün olmadı."): (
        "The attempt could not be restored.",
        "Не удалось восстановить попытку.",
        "Deneme geri yüklenemedi.",
        "Der Versuch konnte nicht wiederhergestellt werden.",
    ),
    (SR, "Cəhdi dayandırmaq mümkün olmadı."): (
        "The attempt could not be paused.",
        "Не удалось приостановить попытку.",
        "Deneme durdurulamadı.",
        "Der Versuch konnte nicht pausiert werden.",
    ),
    (SR, "Dayandır"): ("Pause", "Приостановить", "Durdur", "Pausieren"),
    (SR, "Dil"): ("Language", "Язык", "Sınav dili", "Sprache"),
    (SR, "Hamısı"): ("All", "Все", "Tümü", "Alle"),
    (SR, "Hələ heç kim imtahana başlamayıb"): (
        "Nobody has started the exam yet",
        "Пока никто не начал экзамен",
        "Henüz kimse sınava başlamadı",
        "Noch niemand hat die Prüfung begonnen",
    ),
    (SR, "Kilidlənib"): ("Locked", "Заблокирован", "Kilitlendi", "Gesperrt"),
    (SR, "Limitsiz"): ("Unlimited", "Без ограничений", "Sınırsız", "Unbegrenzt"),
    (SR, "Ləğv et"): ("Cancel", "Отмена", "İptal", "Abbrechen"),
    (SR, "Müəllim dayandırıb"): (
        "Paused by teacher",
        "Приостановлено преподавателем",
        "Öğretmen durdurdu",
        "Von der Lehrkraft pausiert",
    ),
    (SR, "Məsələn: telefondan istifadə"): (
        "For example: using a phone",
        "Например: использование телефона",
        "Örneğin: telefon kullanımı",
        "Zum Beispiel: Handynutzung",
    ),
    (SR, "Nəzarət aktivdir"): ("Proctoring on", "Наблюдение включено", "Gözetim açık", "Aufsicht aktiv"),
    (SR, "Nəzarət otağı"): ("Supervision room", "Комната наблюдения", "Gözetim odası", "Aufsichtsraum"),
    (SR, "Nəzarət sistemi platformada söndürülüb — pozuntular qeydə alınmır, bərpa əməliyyatları işləmir."): (
        "Proctoring is turned off platform-wide — violations are not recorded and restore actions do not work.",
        "Система наблюдения отключена на платформе — нарушения не фиксируются, восстановление не работает.",
        "Gözetim sistemi platformada kapalı — ihlaller kaydedilmez, geri yükleme işlemleri çalışmaz.",
        "Die Aufsicht ist plattformweit ausgeschaltet — Verstöße werden nicht erfasst, Freigaben funktionieren nicht.",
    ),
    (SR, "Nəzarət siyasəti bərpaya icazə vermir («İkinci şans yoxdur»)."): (
        "The proctoring policy does not allow restoring («No second chance»).",
        "Политика наблюдения не разрешает восстановление («Без второго шанса»).",
        "Gözetim politikası geri yüklemeye izin vermiyor («İkinci şans yok»).",
        "Die Aufsichtsrichtlinie erlaubt keine Freigabe («Keine zweite Chance»).",
    ),
    (SR, "Nəzarət sönülüdür"): ("Proctoring off", "Наблюдение выключено", "Gözetim kapalı", "Aufsicht aus"),
    (SR, "Nəzarət xronologiyası"): (
        "Proctoring timeline",
        "Хронология наблюдения",
        "Gözetim zaman çizelgesi",
        "Aufsichtsverlauf",
    ),
    (SR, "Onlayn"): ("Online", "Онлайн", "Çevrimiçi", "Online"),
    (SR, "Pozuntu"): ("Violations", "Нарушения", "İhlal", "Verstöße"),
    (SR, "Pozuntu limiti: %(limit)s"): (
        "Violation limit: %(limit)s",
        "Лимит нарушений: %(limit)s",
        "İhlal sınırı: %(limit)s",
        "Verstoßgrenze: %(limit)s",
    ),
    (SR, "Pozuntu var"): ("Has violations", "Есть нарушения", "İhlal var", "Mit Verstößen"),
    (SR, "Qalan vaxt"): ("Time left", "Осталось времени", "Kalan süre", "Verbleibende Zeit"),
    (SR, "Qeydə alınmış hadisə yoxdur."): (
        "No recorded events.",
        "Зафиксированных событий нет.",
        "Kayıtlı olay yok.",
        "Keine erfassten Ereignisse.",
    ),
    (SR, "Risk xalı"): ("Risk score", "Балл риска", "Risk puanı", "Risikowert"),
    (SR, "Siqnal kəsilib"): ("Signal lost", "Сигнал пропал", "Sinyal kesildi", "Signal verloren"),
    (SR, "Siyasət bərpaya icazə vermir"): (
        "Policy does not allow restoring",
        "Политика не разрешает восстановление",
        "Politika geri yüklemeye izin vermiyor",
        "Richtlinie erlaubt keine Freigabe",
    ),
    (SR, "Səbəb (tələbəyə göstərilir)"): (
        "Reason (shown to the student)",
        "Причина (показывается студенту)",
        "Neden (öğrenciye gösterilir)",
        "Grund (wird den Studierenden angezeigt)",
    ),
    (SR, "Tələbə"): ("Student", "Студент", "Öğrenci", "Studierende/r"),
    (SR, "Tələbə axtarışı"): ("Student search", "Поиск студента", "Öğrenci ara", "Studierende suchen"),
    (SR, "Tələbə imtahana başlayan kimi burada görünəcək. Səhifə özü yenilənir."): (
        "Students appear here as soon as they start the exam. The page refreshes itself.",
        "Студент появится здесь, как только начнёт экзамен. Страница обновляется сама.",
        "Öğrenci sınava başlar başlamaz burada görünecek. Sayfa kendini yeniler.",
        "Studierende erscheinen hier, sobald sie die Prüfung beginnen. Die Seite aktualisiert sich selbst.",
    ),
    (SR, "Tələbə kilidli deyil — bərpa lazım deyil."): (
        "The student is not locked — nothing to restore.",
        "Студент не заблокирован — восстанавливать нечего.",
        "Öğrenci kilitli değil — geri yüklemeye gerek yok.",
        "Die/der Studierende ist nicht gesperrt — keine Freigabe nötig.",
    ),
    (SR, "Tələbə əlavə şansından artıq istifadə edib."): (
        "The student has already used their extra chance.",
        "Студент уже использовал дополнительный шанс.",
        "Öğrenci ek şansını zaten kullandı.",
        "Die zusätzliche Chance wurde bereits genutzt.",
    ),
    (SR, "Tələbələr"): ("Students", "Студенты", "Öğrenciler", "Studierende"),
    (
        SR,
        "Tələbələrin imtahan gedişatı, qayda pozuntuları və kilidlənmələri canlı görünür. Kilidlənən tələbəni buradan "
        "bərpa edin.",
    ): (
        "Students' progress, rule violations and locks are shown live. Restore a locked student from here.",
        "Ход экзамена, нарушения правил и блокировки студентов видны в реальном времени. Восстанавливайте "
        "заблокированного студента отсюда.",
        "Öğrencilerin sınav ilerleyişi, kural ihlalleri ve kilitlenmeleri canlı görünür. Kilitlenen öğrenciyi "
        "buradan geri yükleyin.",
        "Fortschritt, Regelverstöße und Sperren der Studierenden werden live angezeigt. Gesperrte Studierende "
        "hier freigeben.",
    ),
    (SR, "Tələbəni bərpa et"): (
        "Restore student",
        "Восстановить студента",
        "Öğrenciyi geri yükle",
        "Studierende freigeben",
    ),
    (SR, "Tələbənin ekranı açılacaq və o, imtahana olduğu yerdən davam edəcək. Cavabları və vaxtı qorunur."): (
        "The student's screen will unlock and they will continue where they left off. Answers and time are kept.",
        "Экран студента разблокируется, и он продолжит с того же места. Ответы и время сохраняются.",
        "Öğrencinin ekranı açılacak ve kaldığı yerden devam edecek. Cevapları ve süresi korunur.",
        "Der Bildschirm wird entsperrt und die Prüfung geht an derselben Stelle weiter. Antworten und Zeit bleiben erhalten.",
    ),
    (SR, "Tələbənin ekranı kilidlənir, cəhd təhvil verilmir. «Bərpa et» ilə davam etdirə bilərsiniz."): (
        "The student's screen is locked; the attempt is not submitted. Use «Restore» to let them continue.",
        "Экран студента блокируется, попытка не сдаётся. Продолжить можно кнопкой «Восстановить».",
        "Öğrencinin ekranı kilitlenir, deneme teslim edilmez. «Geri yükle» ile devam ettirebilirsiniz.",
        "Der Bildschirm wird gesperrt, der Versuch wird nicht abgegeben. Mit «Wiederherstellen» geht es weiter.",
    ),
    (SR, "Vəziyyət"): ("Status", "Состояние", "Durum", "Status"),
    (SR, "Xülasə"): ("Summary", "Сводка", "Özet", "Übersicht"),
    (SR, "Zal monitoru"): ("Hall monitor", "Монитор зала", "Salon monitörü", "Saalmonitor"),
    (SR, "İmtahan artıq bitib."): (
        "The exam has already ended.",
        "Экзамен уже завершён.",
        "Sınav zaten bitti.",
        "Die Prüfung ist bereits beendet.",
    ),
    (SR, "İmtahana qayıt"): ("Back to the exam", "Назад к экзамену", "Sınava dön", "Zurück zur Prüfung"),
    (SR, "İmtahanda"): ("In exam", "На экзамене", "Sınavda", "In der Prüfung"),
    (SR, "İmtahanı müvəqqəti dayandır"): (
        "Pause the exam temporarily",
        "Временно приостановить экзамен",
        "Sınavı geçici olarak durdur",
        "Prüfung vorübergehend pausieren",
    ),
    (SR, "Şübhəli"): ("Suspicious", "Подозрительно", "Şüpheli", "Verdächtig"),
    (SR, "Əlavə şans istifadə olunub"): (
        "Extra chance already used",
        "Дополнительный шанс использован",
        "Ek şans kullanıldı",
        "Zusätzliche Chance genutzt",
    ),
    (SR, "Əlavə şans ver (pozuntu sayğacı bir vahid azalır)"): (
        "Grant an extra chance (violation counter decreases by one)",
        "Дать дополнительный шанс (счётчик нарушений уменьшится на один)",
        "Ek şans ver (ihlal sayacı bir azalır)",
        "Zusätzliche Chance gewähren (Verstoßzähler sinkt um eins)",
    ),
    (SR, "Əməliyyat mümkün olmadı."): (
        "The action failed.",
        "Операция не удалась.",
        "İşlem başarısız oldu.",
        "Die Aktion ist fehlgeschlagen.",
    ),
    (SR, "Əməllər"): ("Actions", "Действия", "İşlemler", "Aktionen"),
}


def _po_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _has_entry(content: str, ctx: str, msgid: str) -> bool:
    return f'msgctxt "{_po_escape(ctx)}"\nmsgid "{_po_escape(msgid)}"\n' in content


def main() -> None:
    for index, lang in enumerate(LOCALES):
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        added = []
        for (ctx, msgid), translations in ENTRIES.items():
            if _has_entry(content, ctx, msgid):
                continue
            msgstr = msgid if lang == "az" else translations[index - 1]
            added.append(f'\nmsgctxt "{_po_escape(ctx)}"\nmsgid "{_po_escape(msgid)}"\nmsgstr "{_po_escape(msgstr)}"\n')
        if added:
            with open(path, "a", encoding="utf-8") as handle:
                if not content.endswith("\n"):
                    handle.write("\n")
                handle.write("".join(added))
        print(f"{lang}: +{len(added)}")


if __name__ == "__main__":
    main()
