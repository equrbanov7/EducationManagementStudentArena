#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-17: fərdi əlavə vaxt + nəticənin ləğvi / bərpası.

Sahib: «monitorda tələbəyə əlavə N dəqiqə vermək olsun»; «köçürmə sonradan aşkarlanarsa nəticə ləğv edilsin —
səbəb, izahat, tarix, sənəd, təsdiq pəncərəsi; səhv olarsa bərpa». ``django`` kataloquna beş dildə; AZ msgstr = msgid.
Şablon (``{% trans %}``) mətnlərində ``%`` ikiqatdır (``%%(minutes)s``) — Django-nun templatize qaydası. İdempotent.
İstifadə:  python scripts/i18n_add_exam_time_annul_2026_11_17.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_A = "exams.final_center.annul"
_E = "exams.final_center.error"
_M = "exams.final_center.message"
_R = "exams.model.result_annulment"
_T = "exams.time_extension"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    # ── Nəticənin ləğvi / bərpası ──
    (_A, "Qadağan olunmuş vasitədən istifadə (telefon və s.)"): (
        "Use of a prohibited device (phone, etc.)",
        "Использование запрещённых средств (телефон и т. п.)",
        "Yasaklı araç kullanımı (telefon vb.)",
        "Nutzung unerlaubter Hilfsmittel (Telefon usw.)",
    ),
    (_A, "İmtahanı başqası verib"): (
        "Someone else took the exam",
        "Экзамен сдавал другой человек",
        "Sınava başkası girdi",
        "Jemand anderes hat die Prüfung abgelegt",
    ),
    (
        _A,
        "Bu tələbənin nəticəsi ləğv ediləcək: jurnalda 0 bal yazılacaq və tələbəyə səbəb göstəriləcək. Təsdiq edirsiniz?",
    ): (
        "This student's result will be annulled: 0 points will be written to the journal and the reason shown to the student. Do you confirm?",
        "Результат этого студента будет аннулирован: в журнал запишется 0 баллов, студенту будет показана причина. Подтверждаете?",
        "Bu öğrencinin sonucu iptal edilecek: deftere 0 puan yazılacak ve öğrenciye neden gösterilecek. Onaylıyor musunuz?",
        "Das Ergebnis dieses Studierenden wird annulliert: 0 Punkte werden ins Journal eingetragen und der Grund wird angezeigt. Bestätigen Sie?",
    ),
    (_A, "Bərpa səbəbi"): (
        "Reason for restoring",
        "Причина восстановления",
        "Geri alma nedeni",
        "Grund der Wiederherstellung",
    ),
    (_A, "Bərpa səbəbi (məcburi)"): (
        "Reason for restoring (required)",
        "Причина восстановления (обязательно)",
        "Geri alma nedeni (zorunlu)",
        "Grund der Wiederherstellung (Pflicht)",
    ),
    (_A, "Bərpa səbəbini yazın."): (
        "Enter the reason for restoring.",
        "Укажите причину восстановления.",
        "Geri alma nedenini yazın.",
        "Geben Sie den Grund der Wiederherstellung an.",
    ),
    (
        _A,
        "Cəhd silinmir. Jurnalda 0 bal yazılır, tələbənin kabinetində «Nəticəniz ləğv olunub» və səbəb görünür. Səhv olarsa «Ləğvi bərpa et» ilə geri qaytarmaq olar.",
    ): (
        "The attempt is not deleted. 0 points are written to the journal and the student's cabinet shows “Your result has been annulled” with the reason. If this is a mistake, use “Restore” to undo it.",
        "Попытка не удаляется. В журнал записывается 0 баллов, в кабинете студента видно «Ваш результат аннулирован» и причина. При ошибке можно вернуть кнопкой «Восстановить».",
        "Deneme silinmez. Deftere 0 puan yazılır, öğrencinin kabinesinde «Sonucunuz iptal edildi» ve neden görünür. Hata varsa «İptali geri al» ile geri alınabilir.",
        "Der Versuch wird nicht gelöscht. Im Journal werden 0 Punkte eingetragen, im Studierendenkonto erscheint „Ihr Ergebnis wurde annulliert“ mit Grund. Bei einem Fehler kann es mit „Wiederherstellen“ rückgängig gemacht werden.",
    ),
    (_A, "Davam et"): ("Continue", "Далее", "Devam et", "Weiter"),
    (_A, "Geri"): ("Back", "Назад", "Geri dön", "Zurück"),
    (_A, "Hadisə tarixi"): ("Date of the incident", "Дата инцидента", "Olay tarihi", "Datum des Vorfalls"),
    (_A, "Ləğv geri qaytarılsın? Tələbənin əvvəlki nəticəsi kabinetdə və jurnalda bərpa olunacaq."): (
        "Undo the annulment? The student's previous result will be restored in the cabinet and the journal.",
        "Отменить аннулирование? Прежний результат студента будет восстановлен в кабинете и журнале.",
        "İptal geri alınsın mı? Öğrencinin önceki sonucu kabinede ve defterde geri yüklenecek.",
        "Annullierung rückgängig machen? Das frühere Ergebnis wird im Konto und im Journal wiederhergestellt.",
    ),
    (_A, "Ləğv geri qaytarılır: əvvəlki bal və jurnal dəyəri bərpa olunur. Ləğv qeydi tarixçədə qalır."): (
        "The annulment is undone: the previous score and journal value are restored. The annulment record stays in the history.",
        "Аннулирование отменяется: прежний балл и значение в журнале восстанавливаются. Запись об аннулировании остаётся в истории.",
        "İptal geri alınır: önceki puan ve defter değeri geri yüklenir. İptal kaydı geçmişte kalır.",
        "Die Annullierung wird aufgehoben: frühere Punktzahl und Journalwert werden wiederhergestellt. Der Eintrag bleibt im Verlauf.",
    ),
    (_A, "Ləğvi bərpa et"): ("Restore result", "Восстановить результат", "İptali geri al", "Ergebnis wiederherstellen"),
    (_A, "Səbəbi seçin və izahatı yazın."): (
        "Choose a reason and write an explanation.",
        "Выберите причину и напишите пояснение.",
        "Bir neden seçin ve açıklama yazın.",
        "Wählen Sie einen Grund und schreiben Sie eine Begründung.",
    ),
    (_A, "Sənəd"): ("Document", "Документ", "Belge", "Dokument"),
    (_A, "Sənəd (istəyə görə)"): (
        "Document (optional)",
        "Документ (необязательно)",
        "Belge (isteğe bağlı)",
        "Dokument (optional)",
    ),
    (_A, "Təsdiq et və bərpa et"): (
        "Confirm and restore",
        "Подтвердить и восстановить",
        "Onayla ve geri al",
        "Bestätigen und wiederherstellen",
    ),
    (_A, "Təsdiq et və ləğv et"): (
        "Confirm and annul",
        "Подтвердить и аннулировать",
        "Onayla ve iptal et",
        "Bestätigen und annullieren",
    ),
    (_A, "İmtina"): ("Cancel", "Отмена", "Vazgeç", "Abbrechen"),
    (_A, "İzahat (məcburi)"): (
        "Explanation (required)",
        "Пояснение (обязательно)",
        "Açıklama (zorunlu)",
        "Begründung (Pflicht)",
    ),
    (_E, "Bərpa səbəbi yazılmadan ləğv geri qaytarılmır."): (
        "An annulment cannot be undone without a reason.",
        "Аннулирование нельзя отменить без указания причины.",
        "Neden yazılmadan iptal geri alınamaz.",
        "Eine Annullierung kann ohne Grund nicht aufgehoben werden.",
    ),
    (_E, "Hadisə tarixi gələcəkdə ola bilməz."): (
        "The incident date cannot be in the future.",
        "Дата инцидента не может быть в будущем.",
        "Olay tarihi gelecekte olamaz.",
        "Das Datum des Vorfalls darf nicht in der Zukunft liegen.",
    ),
    (_E, "Sənəd 10 MB-dan böyük ola bilməz."): (
        "The document cannot be larger than 10 MB.",
        "Документ не может быть больше 10 МБ.",
        "Belge 10 MB'tan büyük olamaz.",
        "Das Dokument darf nicht größer als 10 MB sein.",
    ),
    (_E, "Sənəd PDF, şəkil (PNG/JPG) və ya Word faylı olmalıdır."): (
        "The document must be a PDF, an image (PNG/JPG) or a Word file.",
        "Документ должен быть PDF, изображением (PNG/JPG) или файлом Word.",
        "Belge PDF, resim (PNG/JPG) veya Word dosyası olmalıdır.",
        "Das Dokument muss eine PDF-, Bild- (PNG/JPG) oder Word-Datei sein.",
    ),
    (_E, "Tarix düzgün deyil."): (
        "The date is not valid.",
        "Неверная дата.",
        "Tarih geçersiz.",
        "Das Datum ist ungültig.",
    ),
    (_M, "Bu nəticə ləğv olunmayıb — bərpa ediləcək bir şey yoxdur."): (
        "This result is not annulled — there is nothing to restore.",
        "Этот результат не аннулирован — восстанавливать нечего.",
        "Bu sonuç iptal edilmemiş — geri alınacak bir şey yok.",
        "Dieses Ergebnis ist nicht annulliert — es gibt nichts wiederherzustellen.",
    ),
    (_M, "Ləğv geri qaytarıldı: əvvəlki nəticə bərpa olundu."): (
        "The annulment was undone: the previous result is restored.",
        "Аннулирование отменено: прежний результат восстановлен.",
        "İptal geri alındı: önceki sonuç geri yüklendi.",
        "Die Annullierung wurde aufgehoben: das frühere Ergebnis ist wiederhergestellt.",
    ),
    (_R, "İmtahan nəticəsinin ləğvi"): (
        "Exam result annulment",
        "Аннулирование результата экзамена",
        "Sınav sonucunun iptali",
        "Annullierung eines Prüfungsergebnisses",
    ),
    (_R, "İmtahan nəticələrinin ləğvi"): (
        "Exam result annulments",
        "Аннулирования результатов экзамена",
        "Sınav sonuçlarının iptali",
        "Annullierungen von Prüfungsergebnissen",
    ),
    # ── Fərdi əlavə vaxt ──
    (_T, "Artıq verilib: +%%(minutes)s dəq"): (
        "Already given: +%%(minutes)s min",
        "Уже добавлено: +%%(minutes)s мин",
        "Zaten verildi: +%%(minutes)s dk",
        "Bereits gewährt: +%%(minutes)s Min.",
    ),
    (_T, "Bir dəfəyə %(min)d–%(max)d dəqiqə əlavə etmək olar."): (
        "You can add %(min)d–%(max)d minutes at a time.",
        "За один раз можно добавить %(min)d–%(max)d минут.",
        "Bir seferde %(min)d–%(max)d dakika eklenebilir.",
        "Pro Vorgang können %(min)d–%(max)d Minuten hinzugefügt werden.",
    ),
    (_T, "Bir tələbəyə cəmi %(max)d dəqiqədən çox əlavə vaxt verilə bilməz (artıq verilib: %(given)d dəq)."): (
        "A student cannot get more than %(max)d extra minutes in total (already given: %(given)d min).",
        "Студенту нельзя добавить больше %(max)d минут в сумме (уже добавлено: %(given)d мин).",
        "Bir öğrenciye toplam %(max)d dakikadan fazla ek süre verilemez (zaten verildi: %(given)d dk).",
        "Insgesamt dürfen höchstens %(max)d Zusatzminuten gewährt werden (bereits gewährt: %(given)d Min.).",
    ),
    (_T, "Bu imtahanda vaxt limiti yoxdur — əlavə vaxt lazım deyil."): (
        "This exam has no time limit — extra time is not needed.",
        "У этого экзамена нет ограничения по времени — дополнительное время не нужно.",
        "Bu sınavda süre sınırı yok — ek süre gerekmez.",
        "Diese Prüfung hat kein Zeitlimit — Zusatzzeit ist nicht nötig.",
    ),
    (
        _T,
        "Bu tələbəyə %%(minutes)s dəqiqə əlavə vaxt verilsin? Yalnız onun vaxtı uzanacaq, digər tələbələrə toxunulmur.",
    ): (
        "Give this student %%(minutes)s extra minutes? Only their time is extended; other students are not affected.",
        "Добавить этому студенту %%(minutes)s минут? Продлится только его время, других студентов это не затронет.",
        "Bu öğrenciye %%(minutes)s dakika ek süre verilsin mi? Yalnızca onun süresi uzar, diğer öğrenciler etkilenmez.",
        "Diesem Studierenden %%(minutes)s Zusatzminuten geben? Nur seine Zeit wird verlängert, andere sind nicht betroffen.",
    ),
    (_T, "Dəqiqə"): ("Minutes", "Минуты", "Dakika", "Minuten"),
    (_T, "Dəqiqə sayını rəqəmlə yazın."): (
        "Enter the number of minutes as a number.",
        "Укажите количество минут числом.",
        "Dakika sayısını rakamla yazın.",
        "Geben Sie die Minutenzahl als Zahl ein.",
    ),
    (_T, "Məs.: kompüter dondu, tələbə 7 dəqiqə itirdi"): (
        "E.g.: the computer froze, the student lost 7 minutes",
        "Напр.: компьютер завис, студент потерял 7 минут",
        "Örn.: bilgisayar dondu, öğrenci 7 dakika kaybetti",
        "Z. B.: Der Computer ist abgestürzt, 7 Minuten verloren",
    ),
    (_T, "Sizə %(minutes)s dəqiqə əlavə vaxt verildi."): (
        "You have been given %(minutes)s extra minutes.",
        "Вам добавлено %(minutes)s минут.",
        "Size %(minutes)s dakika ek süre verildi.",
        "Ihnen wurden %(minutes)s Zusatzminuten gewährt.",
    ),
    (_T, "Səbəb (məcburi)"): ("Reason (required)", "Причина (обязательно)", "Neden (zorunlu)", "Grund (Pflicht)"),
    (_T, "Tez seçim"): ("Quick pick", "Быстрый выбор", "Hızlı seçim", "Schnellauswahl"),
    (_T, "Tələbə imtahanı artıq bitirib — əlavə vaxt verilə bilməz."): (
        "The student has already finished the exam — extra time cannot be given.",
        "Студент уже завершил экзамен — дополнительное время дать нельзя.",
        "Öğrenci sınavı zaten bitirdi — ek süre verilemez.",
        "Der Studierende hat die Prüfung bereits beendet — keine Zusatzzeit möglich.",
    ),
    (_T, "Tələbənin davam edən imtahanı yoxdur."): (
        "The student has no exam in progress.",
        "У студента нет текущего экзамена.",
        "Öğrencinin devam eden sınavı yok.",
        "Der Studierende hat keine laufende Prüfung.",
    ),
    (_T, "Tələbəyə %(added)d dəqiqə əlavə olundu (cəmi əlavə: %(total)d dəq). Yeni bitmə vaxtı: %(time)s."): (
        "%(added)d minutes added for the student (total extra: %(total)d min). New end time: %(time)s.",
        "Студенту добавлено %(added)d мин (всего добавлено: %(total)d мин). Новое время окончания: %(time)s.",
        "Öğrenciye %(added)d dakika eklendi (toplam ek: %(total)d dk). Yeni bitiş saati: %(time)s.",
        "%(added)d Minuten hinzugefügt (insgesamt: %(total)d Min.). Neues Ende: %(time)s.",
    ),
    (_T, "Çox tez-tez sorğu — bir az sonra yenidən cəhd edin."): (
        "Too many requests — try again in a moment.",
        "Слишком частые запросы — попробуйте чуть позже.",
        "Çok sık istek — biraz sonra tekrar deneyin.",
        "Zu viele Anfragen — bitte gleich noch einmal versuchen.",
    ),
    (_T, "İmtahan vaxtı artıq bitib — əlavə vaxt yalnız davam edən imtahana verilir."): (
        "The exam time is already over — extra time is only given to an exam in progress.",
        "Время экзамена уже истекло — дополнительное время даётся только идущему экзамену.",
        "Sınav süresi zaten doldu — ek süre yalnızca devam eden sınava verilir.",
        "Die Prüfungszeit ist bereits abgelaufen — Zusatzzeit nur für laufende Prüfungen.",
    ),
    (_T, "Əlavə vaxt"): ("Extra time", "Дополнительное время", "Ek süre", "Zusatzzeit"),
    (_T, "Əlavə vaxt ver"): ("Give extra time", "Добавить время", "Ek süre ver", "Zusatzzeit gewähren"),
    (_T, "Əlavə vaxtın səbəbini yazın."): (
        "Enter the reason for the extra time.",
        "Укажите причину дополнительного времени.",
        "Ek sürenin nedenini yazın.",
        "Geben Sie den Grund für die Zusatzzeit an.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid and "%%(" not in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
