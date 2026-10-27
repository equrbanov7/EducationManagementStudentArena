#!/usr/bin/env python3
"""EMSArena i18n — «Data bərpası» rejimi: müəllimin keçmiş tarixli jurnalı səbəb ilə tam redaktəsi (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "core.runtime_settings": {
        "Müəllimlər keçmiş tarixli jurnalı tam redaktə edə bilər (data bərpası)": t(
            "Teachers may fully edit past-dated journals (data recovery)",
            "Преподаватели могут полностью редактировать журнал за прошлые даты (восстановление данных)",
            "Öğretmenler geçmiş tarihli yoklama defterini tamamen düzenleyebilir (veri kurtarma)",
            "Lehrkräfte dürfen das Journal für vergangene Daten vollständig bearbeiten (Datenwiederherstellung)",
        ),
        (
            "Yandırılanda müəllim öz jurnalında (bölünmüş jurnalda yalnız öz payında) istənilən keçmiş tarixə "
            "(semestr daxilində) dərs əlavə edə, dərsi və mövzusunu redaktə edə, dərsi qeydləri ilə birlikdə "
            "silə, q/b, i/e və balı dəyişib təmizləyə bilər — bağlanmış jurnalda da. Təqdimat və sənəd "
            "tələb olunmur, yalnız qısa səbəb yazılır; hər dəyişiklik köhnə və yeni dəyərlə audit jurnalına "
            "düşür. İmtahandan gələn ballar (midterm, yekun) və RİM-in sənədli düzəlişi olan xana bu rejimə "
            "tabe deyil. Söndürüləndə bütün adi qaydalar (yazma müddəti, xana kilidi, bağlı jurnal) qayıdır."
        ): t(
            "When on, a teacher can, in their own journal (in a split journal only within their share), add a "
            "lesson on any past date (within the semester), edit a lesson and its topic, delete a lesson together "
            "with its records, and change or clear absences, attendance and scores — even in a closed journal. No "
            "submission or document is required, only a short reason; every change is written to the audit log "
            "with its old and new value. Scores coming from exams (midterm, final) and cells with a documented "
            "Registrar correction are not affected by this mode. When off, all the usual rules (entry period, "
            "cell lock, closed journal) apply again.",
            "Когда включено, преподаватель в своём журнале (в разделённом журнале — только в своей доле) может "
            "добавить занятие на любую прошедшую дату (в пределах семестра), редактировать занятие и его тему, "
            "удалить занятие вместе с записями, изменить и очистить пропуски, посещаемость и баллы — даже в "
            "закрытом журнале. Представление и документ не требуются, пишется только краткая причина; каждое "
            "изменение со старым и новым значением попадает в журнал аудита. Баллы из экзаменов (мидтерм, итог) "
            "и ячейки с документальным исправлением Регистратуры этому режиму не подчиняются. При выключении "
            "возвращаются все обычные правила (срок записи, блокировка ячейки, закрытый журнал).",
            "Açıkken öğretmen kendi yoklama defterinde (bölünmüş defterde yalnızca kendi payında) herhangi bir "
            "geçmiş tarihe (dönem içinde) ders ekleyebilir, dersi ve konusunu düzenleyebilir, dersi kayıtlarıyla "
            "birlikte silebilir, devamsızlık, katılım ve puanları değiştirip temizleyebilir — kapatılmış defterde "
            "de. Dilekçe ve belge gerekmez, yalnızca kısa bir gerekçe yazılır; her değişiklik eski ve yeni "
            "değeriyle denetim günlüğüne düşer. Sınavlardan gelen puanlar (ara sınav, final) ve Öğrenci İşlerinin "
            "belgeli düzeltmesi olan hücreler bu moda tabi değildir. Kapatıldığında tüm olağan kurallar (yazma "
            "süresi, hücre kilidi, kapalı defter) geri gelir.",
            "Wenn aktiviert, kann eine Lehrkraft in ihrem eigenen Journal (in einem geteilten Journal nur in ihrem "
            "Anteil) an jedem vergangenen Datum (innerhalb des Semesters) eine Stunde anlegen, eine Stunde und ihr "
            "Thema bearbeiten, eine Stunde samt Einträgen löschen sowie Fehlzeiten, Anwesenheit und Punkte ändern "
            "und leeren — auch in einem geschlossenen Journal. Es ist weder ein Antrag noch ein Dokument nötig, nur "
            "eine kurze Begründung; jede Änderung wird mit altem und neuem Wert im Audit-Protokoll erfasst. Punkte "
            "aus Prüfungen (Midterm, Abschluss) und Zellen mit einer dokumentierten Korrektur des "
            "Studierendensekretariats sind von diesem Modus ausgenommen. Wenn deaktiviert, gelten wieder alle "
            "üblichen Regeln (Eintragungsfrist, Zellsperre, geschlossenes Journal).",
        ),
    },
    "registrar.journal_full_edit": {
        "Keçmiş tarixli və ya bağlanmış jurnaldakı dəyişiklik üçün səbəbi yazın (ən azı %(n)s simvol).": t(
            "Enter a reason for a change to a past-dated or closed journal (at least %(n)s characters).",
            "Укажите причину изменения в журнале за прошлую дату или в закрытом журнале (не менее %(n)s символов).",
            "Geçmiş tarihli veya kapatılmış defterdeki değişiklik için gerekçe yazın (en az %(n)s karakter).",
            "Geben Sie eine Begründung für die Änderung in einem vergangenen oder geschlossenen Journal ein "
            "(mindestens %(n)s Zeichen).",
        ),
        "Gələcək tarixə dərs əlavə etmək olmaz.": t(
            "A lesson cannot be added for a future date.",
            "Нельзя добавить занятие на будущую дату.",
            "Gelecek bir tarihe ders eklenemez.",
            "Für ein zukünftiges Datum kann keine Stunde angelegt werden.",
        ),
        "Dərs tarixi semestrin başlanğıcından (%(date)s) əvvəl ola bilməz.": t(
            "The lesson date cannot be before the start of the semester (%(date)s).",
            "Дата занятия не может быть раньше начала семестра (%(date)s).",
            "Ders tarihi dönem başlangıcından (%(date)s) önce olamaz.",
            "Das Stundendatum darf nicht vor dem Semesterbeginn (%(date)s) liegen.",
        ),
        "Dərs tarixi semestrin sonundan (%(date)s) sonra ola bilməz.": t(
            "The lesson date cannot be after the end of the semester (%(date)s).",
            "Дата занятия не может быть позже конца семестра (%(date)s).",
            "Ders tarihi dönem sonundan (%(date)s) sonra olamaz.",
            "Das Stundendatum darf nicht nach dem Semesterende (%(date)s) liegen.",
        ),
        "Dərs %(n)s qeydi ilə birlikdə silindi.": t(
            "The lesson was deleted together with its %(n)s records.",
            "Занятие удалено вместе с записями (%(n)s).",
            "Ders, %(n)s kaydıyla birlikte silindi.",
            "Die Stunde wurde zusammen mit ihren %(n)s Einträgen gelöscht.",
        ),
        "Data bərpası rejimi: keçmiş tarixli dəyişikliklər səbəb ilə açıqdır": t(
            "Data recovery mode: past-dated changes are open with a reason",
            "Режим восстановления данных: изменения за прошлые даты открыты с указанием причины",
            "Veri kurtarma modu: geçmiş tarihli değişiklikler gerekçeyle açık",
            "Datenwiederherstellungsmodus: Änderungen an vergangenen Daten sind mit Begründung möglich",
        ),
        (
            "Keçmiş tarixə dərs əlavə edə, dərsi və mövzusunu dəyişə, dərsi qeydləri ilə birlikdə silə, q/b, i/e və "
            "balı dəyişib təmizləyə bilərsiniz. Hər belə dəyişiklik üçün yalnız qısa səbəb soruşulur və köhnə/yeni "
            "dəyərlə audit jurnalına yazılır."
        ): t(
            "You can add a lesson on a past date, change a lesson and its topic, delete a lesson together with its "
            "records, and change or clear absences, attendance and scores. Each such change only asks for a short "
            "reason and is written to the audit log with its old/new value.",
            "Вы можете добавить занятие на прошедшую дату, изменить занятие и его тему, удалить занятие вместе с "
            "записями, изменить и очистить пропуски, посещаемость и баллы. Для каждого такого изменения "
            "запрашивается только краткая причина, и оно записывается в журнал аудита со старым/новым значением.",
            "Geçmiş bir tarihe ders ekleyebilir, dersi ve konusunu değiştirebilir, dersi kayıtlarıyla birlikte "
            "silebilir, devamsızlık, katılım ve puanları değiştirip temizleyebilirsiniz. Her değişiklik için "
            "yalnızca kısa bir gerekçe sorulur ve eski/yeni değeriyle denetim günlüğüne yazılır.",
            "Sie können an einem vergangenen Datum eine Stunde anlegen, eine Stunde und ihr Thema ändern, eine "
            "Stunde samt Einträgen löschen sowie Fehlzeiten, Anwesenheit und Punkte ändern und leeren. Für jede "
            "solche Änderung wird nur eine kurze Begründung abgefragt; sie wird mit altem/neuem Wert im "
            "Audit-Protokoll erfasst.",
        ),
        "Jurnal bağlanıb — bu rejimdə dəyişiklik yenə səbəb ilə mümkündür.": t(
            "The journal is closed — in this mode changes are still possible with a reason.",
            "Журнал закрыт — в этом режиме изменения всё равно возможны с указанием причины.",
            "Defter kapatıldı — bu modda değişiklik yine gerekçeyle mümkündür.",
            "Das Journal ist geschlossen — in diesem Modus sind Änderungen mit Begründung dennoch möglich.",
        ),
        "İmtahandan gələn ballar (Midterm, yekun) və RİM-in sənədli düzəlişi olan xanalar bu rejimdə dəyişmir.": t(
            "Scores coming from exams (Midterm, final) and cells with a documented Registrar correction do not "
            "change in this mode.",
            "Баллы из экзаменов (мидтерм, итог) и ячейки с документальным исправлением Регистратуры в этом режиме "
            "не изменяются.",
            "Sınavlardan gelen puanlar (ara sınav, final) ve Öğrenci İşlerinin belgeli düzeltmesi olan hücreler bu "
            "modda değişmez.",
            "Punkte aus Prüfungen (Midterm, Abschluss) und Zellen mit dokumentierter Korrektur des "
            "Studierendensekretariats ändern sich in diesem Modus nicht.",
        ),
        "Dəyişikliyin səbəbi": t(
            "Reason for the change", "Причина изменения", "Değişikliğin gerekçesi", "Grund der Änderung"
        ),
        (
            "Bu dəyişiklik keçmiş tarixli, kilidlənmiş və ya bağlanmış jurnaldakı xanaya aiddir. Qısa səbəb yazın — "
            "təqdimat və sənəd tələb olunmur. Səbəb bu səhifədəki sonrakı dəyişikliklər üçün də yadda qalır."
        ): t(
            "This change concerns a cell that is past-dated, locked or in a closed journal. Enter a short reason — "
            "no submission or document is required. The reason is also remembered for further changes on this page.",
            "Это изменение касается ячейки за прошлую дату, заблокированной или в закрытом журнале. Укажите краткую "
            "причину — представление и документ не требуются. Причина запоминается и для следующих изменений на "
            "этой странице.",
            "Bu değişiklik geçmiş tarihli, kilitli veya kapatılmış defterdeki bir hücreye aittir. Kısa bir gerekçe "
            "yazın — dilekçe ve belge gerekmez. Gerekçe bu sayfadaki sonraki değişiklikler için de hatırlanır.",
            "Diese Änderung betrifft eine Zelle mit vergangenem Datum, eine gesperrte Zelle oder ein geschlossenes "
            "Journal. Geben Sie eine kurze Begründung ein — kein Antrag und kein Dokument nötig. Die Begründung "
            "wird auch für weitere Änderungen auf dieser Seite gemerkt.",
        ),
        "Məs.: köhnə sistemdən köçməyən davamiyyətin bərpası": t(
            "E.g.: restoring attendance that was not migrated from the old system",
            "Напр.: восстановление посещаемости, не перенесённой из старой системы",
            "Örn.: eski sistemden aktarılmayan devamsızlığın geri yüklenmesi",
            "Z. B.: Wiederherstellung der Anwesenheit, die nicht aus dem alten System übernommen wurde",
        ),
        "Səbəb ən azı %(n)s simvol olmalıdır.": t(
            "The reason must be at least %(n)s characters long.",
            "Причина должна содержать не менее %(n)s символов.",
            "Gerekçe en az %(n)s karakter olmalıdır.",
            "Die Begründung muss mindestens %(n)s Zeichen lang sein.",
        ),
        "Səbəblə yadda saxla": t(
            "Save with reason", "Сохранить с причиной", "Gerekçeyle kaydet", "Mit Begründung speichern"
        ),
        "Bu dərs sütunu və ona aid {n} qeyd (q/b, i/e, bal) birlikdə silinəcək. Səbəb audit jurnalına yazılır.": t(
            "This lesson column and its {n} records (absences, attendance, scores) will be deleted together. The "
            "reason is written to the audit log.",
            "Этот столбец занятия и связанные с ним записи ({n}: пропуски, посещаемость, баллы) будут удалены "
            "вместе. Причина записывается в журнал аудита.",
            "Bu ders sütunu ve ona ait {n} kayıt (devamsızlık, katılım, puan) birlikte silinecek. Gerekçe denetim "
            "günlüğüne yazılır.",
            "Diese Stundenspalte und ihre {n} Einträge (Fehlzeiten, Anwesenheit, Punkte) werden zusammen gelöscht. "
            "Die Begründung wird im Audit-Protokoll erfasst.",
        ),
        (
            "Data bərpası rejimi: semestr ərzində istənilən keçmiş tarix seçilə bilər — yazma müddətindən köhnə "
            "tarix üçün səbəb yazılır."
        ): t(
            "Data recovery mode: any past date within the semester can be chosen — a date older than the entry "
            "period needs a reason.",
            "Режим восстановления данных: можно выбрать любую прошедшую дату в пределах семестра — для даты старше "
            "срока записи указывается причина.",
            "Veri kurtarma modu: dönem içinde herhangi bir geçmiş tarih seçilebilir — yazma süresinden eski tarih "
            "için gerekçe yazılır.",
            "Datenwiederherstellungsmodus: Jedes vergangene Datum innerhalb des Semesters ist wählbar — für ein "
            "Datum vor der Eintragungsfrist ist eine Begründung nötig.",
        ),
        "DƏYİŞİKLİYİN SƏBƏBİ (DATA BƏRPASI)": t(
            "REASON FOR THE CHANGE (DATA RECOVERY)",
            "ПРИЧИНА ИЗМЕНЕНИЯ (ВОССТАНОВЛЕНИЕ ДАННЫХ)",
            "DEĞİŞİKLİĞİN GEREKÇESİ (VERİ KURTARMA)",
            "GRUND DER ÄNDERUNG (DATENWIEDERHERSTELLUNG)",
        ),
        "Məs.: köhnə sistemdən köçməyən dərsin bərpası": t(
            "E.g.: restoring a lesson that was not migrated from the old system",
            "Напр.: восстановление занятия, не перенесённого из старой системы",
            "Örn.: eski sistemden aktarılmayan dersin geri yüklenmesi",
            "Z. B.: Wiederherstellung einer Stunde, die nicht aus dem alten System übernommen wurde",
        ),
        (
            "Keçmiş tarixli, redaktə vaxtı bitmiş və ya bağlanmış jurnaldakı dərs üçün məcburidir — təqdimat və "
            "sənəd tələb olunmur. Səbəb audit jurnalına yazılır."
        ): t(
            "Required for a past-dated lesson, a lesson whose edit time has expired or one in a closed journal — no "
            "submission or document is required. The reason is written to the audit log.",
            "Обязательно для занятия за прошлую дату, занятия с истёкшим сроком редактирования или в закрытом "
            "журнале — представление и документ не требуются. Причина записывается в журнал аудита.",
            "Geçmiş tarihli, düzenleme süresi dolmuş veya kapatılmış defterdeki ders için zorunludur — dilekçe ve "
            "belge gerekmez. Gerekçe denetim günlüğüne yazılır.",
            "Pflicht für eine Stunde mit vergangenem Datum, mit abgelaufener Bearbeitungszeit oder in einem "
            "geschlossenen Journal — kein Antrag und kein Dokument nötig. Die Begründung wird im Audit-Protokoll "
            "erfasst.",
        ),
    },
    "registrar.journal_history": {
        "Data bərpası (səbəb ilə)": t(
            "Data recovery (with reason)",
            "Восстановление данных (с причиной)",
            "Veri kurtarma (gerekçeli)",
            "Datenwiederherstellung (mit Begründung)",
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
