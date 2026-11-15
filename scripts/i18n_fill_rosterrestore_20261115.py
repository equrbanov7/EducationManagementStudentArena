#!/usr/bin/env python3
"""«Tələbəni bərpa et» (sahib 2026-11-15): yalnız yeni msgid-ləri əlavə edir; mövcudlara toxunmur."""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


ENTRIES = {
    "django": {
        "registrar.roster_restore": {
            "Tələbəni bərpa et": t(
                "Restore a student", "Восстановить студента", "Öğrenciyi geri al", "Studierende wiederherstellen"
            ),
            "Səhvən çıxarılmış və ya dondurulmuş tələbəni jurnala qaytarın": t(
                "Return a student who was removed or frozen by mistake to the journal",
                "Вернуть в журнал студента, исключённого или замороженного по ошибке",
                "Yanlışlıkla çıkarılan veya dondurulan öğrenciyi deftere geri alın",
                "Versehentlich entfernte oder eingefrorene Studierende wieder ins Journal aufnehmen",
            ),
            "Səhvən çıxarılmış və ya dondurulmuş tələbəni bu jurnala qaytarın. Tələbənin əvvəlki balları və "
            "davamiyyəti yerində qalır — yeni sətir yaradılmır.": t(
                "Return a student who was removed or frozen by mistake to this journal. The student's earlier "
                "scores and attendance stay in place — no new row is created.",
                "Верните в этот журнал студента, исключённого или замороженного по ошибке. Прежние баллы и "
                "посещаемость студента сохраняются — новая строка не создаётся.",
                "Yanlışlıkla çıkarılan veya dondurulan öğrenciyi bu deftere geri alın. Öğrencinin önceki puanları "
                "ve devamı yerinde kalır — yeni satır oluşturulmaz.",
                "Versehentlich entfernte oder eingefrorene Studierende wieder in dieses Journal aufnehmen. "
                "Bisherige Punkte und Anwesenheit bleiben erhalten — es wird keine neue Zeile angelegt.",
            ),
            "Siyahı yüklənir…": t("Loading the list…", "Загрузка списка…", "Liste yükleniyor…", "Liste wird geladen…"),
            "Bu jurnaldan çıxarılmış tələbə yoxdur.": t(
                "No students have been removed from this journal.",
                "Из этого журнала никто не исключён.",
                "Bu defterden çıkarılmış öğrenci yok.",
                "Aus diesem Journal wurden keine Studierenden entfernt.",
            ),
            "Bərpa ediləcək tələbəni seçin.": t(
                "Select the student to restore.",
                "Выберите студента для восстановления.",
                "Geri alınacak öğrenciyi seçin.",
                "Wählen Sie die wiederherzustellende Person.",
            ),
            "Əməliyyat alınmadı — yenidən cəhd edin.": t(
                "The action failed — please try again.",
                "Операция не удалась — попробуйте ещё раз.",
                "İşlem başarısız — tekrar deneyin.",
                "Der Vorgang ist fehlgeschlagen — bitte erneut versuchen.",
            ),
            "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
            "alt qrupdan": t("from subgroup", "из подгруппы", "alt gruptan", "aus Untergruppe"),
            "Kim": t("By", "Кто", "Kim", "Von"),
            "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
            "Bağla": t("Close", "Закрыть", "Kapat", "Schließen"),
            "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
            "(istəyə bağlı)": t("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
            "Məs.: səhvən çıxarılmışdı, dekanlığın tələbi ilə qaytarıldı": t(
                "E.g.: removed by mistake, returned at the dean's office request",
                "Напр.: исключён по ошибке, возвращён по запросу деканата",
                "Örn.: yanlışlıkla çıkarılmıştı, dekanlığın talebiyle geri alındı",
                "Z. B.: versehentlich entfernt, auf Wunsch des Dekanats zurückgeholt",
            ),
            "Ləğv et": t("Cancel", "Отмена", "İptal", "Abbrechen"),
            "Bərpa et": t("Restore", "Восстановить", "Geri al", "Wiederherstellen"),
            "Xarici nəticə tanınıb — «Xarici nəticələrin tanınması» bölməsində ləğv olunur.": t(
                "An external result was recognised — cancel it in «Recognition of external results».",
                "Признан внешний результат — отменяется в разделе «Признание внешних результатов».",
                "Dış sonuç tanınmış — «Dış sonuçların tanınması» bölümünde iptal edilir.",
                "Ein externes Ergebnis wurde anerkannt — Aufhebung im Bereich «Anerkennung externer Ergebnisse».",
            ),
            "Əvvəl də jurnalda aktiv deyildi — bərpa onu qaytarmır.": t(
                "The student was not active in the journal before either — restoring does not bring them back.",
                "Студент и раньше не был активен в журнале — восстановление его не вернёт.",
                "Öğrenci daha önce de defterde aktif değildi — geri alma onu döndürmez.",
                "Die Person war auch vorher nicht aktiv im Journal — die Wiederherstellung holt sie nicht zurück.",
            ),
            "Rəsmi qrup köçürməsi ilə başqa jurnala keçib — qrup yalnız köçürmə əmri ilə dəyişir.": t(
                "Moved to another journal by an official group transfer — the group changes only by a transfer "
                "order.",
                "Переведён в другой журнал официальным переводом группы — группа меняется только приказом о "
                "переводе.",
                "Resmi grup nakli ile başka deftere geçti — grup yalnızca nakil emriyle değişir.",
                "Durch einen offiziellen Gruppenwechsel in ein anderes Journal gewechselt — die Gruppe ändert sich "
                "nur per Wechselanordnung.",
            ),
            "Akademik statusa görə dondurulub (məzuniyyət / xaric / məzun) — qrup reyestrində «Bərpa et» əmri ilə "
            "qayıdır.": t(
                "Frozen because of the academic status (leave / expelled / graduated) — returns with the «Restore» "
                "order in the group registry.",
                "Заморожен из-за академического статуса (отпуск / отчисление / выпуск) — возвращается приказом "
                "«Восстановить» в реестре групп.",
                "Akademik durum nedeniyle donduruldu (izin / kayıt silme / mezun) — grup sicilinde «Geri al» "
                "emriyle döner.",
                "Wegen des akademischen Status eingefroren (Beurlaubung / Exmatrikulation / Abschluss) — kehrt per "
                "Anordnung «Wiederherstellen» im Gruppenregister zurück.",
            ),
            "Sistem tərəfindən çıxarılıb — bu pəncərədən bərpa olunmur.": t(
                "Removed by the system — cannot be restored from this window.",
                "Исключён системой — из этого окна не восстанавливается.",
                "Sistem tarafından çıkarıldı — bu pencereden geri alınamaz.",
                "Vom System entfernt — kann in diesem Fenster nicht wiederhergestellt werden.",
            ),
            "Tələbə bu fənn üzrə «%(group)s» qrupunun jurnalında aktivdir. Bu jurnala qaytarmaq üçün «Alt qrupdan "
            "tələbə əlavə et» pəncərəsində «öz jurnalından azad et» seçin.": t(
                "The student is active in the journal of group «%(group)s» for this subject. To bring them back "
                "here, choose «release from own journal» in «Add a student from a subgroup».",
                "Студент активен по этому предмету в журнале группы «%(group)s». Чтобы вернуть его сюда, выберите "
                "«освободить из своего журнала» в окне «Добавить студента из подгруппы».",
                "Öğrenci bu derste «%(group)s» grubunun defterinde aktif. Buraya geri almak için «Alt gruptan "
                "öğrenci ekle» penceresinde «kendi defterinden serbest bırak» seçin.",
                "Die Person ist in diesem Fach im Journal der Gruppe «%(group)s» aktiv. Um sie hierher "
                "zurückzuholen, wählen Sie unter «Studierende aus Untergruppe hinzufügen» die Option «aus dem "
                "eigenen Journal freigeben».",
            ),
            "Tələbə bu fənn üzrə «%(group)s» qrupunun jurnalında aktivdir — əvvəlcə oradan çıxarın, sonra bərpa "
            "edin.": t(
                "The student is active in the journal of group «%(group)s» for this subject — remove them there "
                "first, then restore.",
                "Студент активен по этому предмету в журнале группы «%(group)s» — сначала исключите его оттуда, "
                "затем восстановите.",
                "Öğrenci bu derste «%(group)s» grubunun defterinde aktif — önce oradan çıkarın, sonra geri alın.",
                "Die Person ist in diesem Fach im Journal der Gruppe «%(group)s» aktiv — zuerst dort entfernen, "
                "dann wiederherstellen.",
            ),
            "Dondurulub": t("Frozen", "Заморожен", "Donduruldu", "Eingefroren"),
            "Çıxarılıb": t("Removed", "Исключён", "Çıkarıldı", "Entfernt"),
            "Bu qərarı yalnız RİM geri qaytara bilər.": t(
                "Only the registrar's office can reverse this decision.",
                "Отменить это решение может только РИМ.",
                "Bu kararı yalnızca RİM geri alabilir.",
                "Nur das Registeramt (RİM) kann diese Entscheidung zurücknehmen.",
            ),
            "Jurnala bərpa edildi": t(
                "Restored to the journal", "Восстановлен в журнале", "Deftere geri alındı", "Ins Journal zurückgeholt"
            ),
            "Qeydiyyat tapılmadı.": t(
                "Enrolment not found.", "Запись не найдена.", "Kayıt bulunamadı.", "Einschreibung nicht gefunden."
            ),
            "Tələbə artıq jurnaldadır.": t(
                "The student is already in the journal.",
                "Студент уже в журнале.",
                "Öğrenci zaten defterde.",
                "Die Person ist bereits im Journal.",
            ),
            "Qərar artıq geri qaytarılıb.": t(
                "The decision has already been reversed.",
                "Решение уже отменено.",
                "Karar zaten geri alındı.",
                "Die Entscheidung wurde bereits zurückgenommen.",
            ),
            "Tələbəni jurnala bərpa etmək üçün səlahiyyətiniz yoxdur.": t(
                "You are not allowed to restore students to the journal.",
                "У вас нет прав восстанавливать студентов в журнале.",
                "Öğrenciyi deftere geri almak için yetkiniz yok.",
                "Sie sind nicht berechtigt, Studierende im Journal wiederherzustellen.",
            ),
            "Tələbə jurnala qaytarıldı — əvvəlki balları və davamiyyəti yerindədir.": t(
                "The student is back in the journal — earlier scores and attendance are in place.",
                "Студент возвращён в журнал — прежние баллы и посещаемость на месте.",
                "Öğrenci deftere geri alındı — önceki puanları ve devamı yerinde.",
                "Die Person ist wieder im Journal — bisherige Punkte und Anwesenheit sind erhalten.",
            ),
        },
        "registrar.journal_removal": {
            "Jurnal təmizliyi": t("Journal cleanup", "Очистка журналов", "Defter temizliği", "Journalbereinigung"),
        },
    },
}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%" in msgid else []
                    if context:
                        lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
