#!/usr/bin/env python3
"""EMSArena i18n — imtahan zalı çərçivəsi, «açar yalnız zalda», zal apellyasiyasının uğur ekranı, apellyasiya
qərarında «qərarı verən müəllim» / əsaslandırıcı sənəd / «Fənni tədris edən» / müəllim görünüşü (sahib 2026-10-21).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

FRAME = "exams.template.hall_frame"
RESULT = "exams.template.student_exam_result"
TPL = "appeals.template"
DONE = "appeals.template.hall_done"
TEACHING = "appeals.template.teaching"
MSG = "appeals.view.message"
DOC = "appeals.document"
NOTE = "appeals.notification"
HIST = "appeals.history"
RS = "core.runtime_settings"
ITEM_FIELD = "appeals.model.item.field"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {(ITEM_FIELD, "decided_by_teacher"): "Qərarı verən müəllim"}

HALL_NOTE = (
    "Düzgün və səhv cavabları yalnız imtahan verdiyiniz zal kompüterində, imtahan bitəndən sonrakı %(minutes)s "
    "dəqiqə ərzində görə bilərsiniz. Zalı tərk etdikdən sonra verilən apellyasiyada yalnız suallar göstərilir."
)
HALL_NOTE_T = t(
    "You can see the correct and incorrect answers only on the exam hall computer you took the exam on, within "
    "%(minutes)s minutes after the exam ends. An appeal filed after leaving the hall shows the questions only.",
    "Правильные и неправильные ответы можно увидеть только на компьютере экзаменационного зала, на котором вы "
    "сдавали экзамен, в течение %(minutes)s минут после окончания экзамена. В апелляции, поданной после выхода из "
    "зала, показываются только вопросы.",
    "Doğru ve yanlış cevapları yalnızca sınava girdiğiniz salon bilgisayarında, sınav bittikten sonraki "
    "%(minutes)s dakika içinde görebilirsiniz. Salondan ayrıldıktan sonra yapılan itirazda yalnızca sorular "
    "gösterilir.",
    "Richtige und falsche Antworten sehen Sie nur am Prüfungssaal-Computer, an dem Sie die Prüfung abgelegt haben, "
    "innerhalb von %(minutes)s Minuten nach Prüfungsende. In einem Widerspruch nach Verlassen des Saals werden nur "
    "die Fragen angezeigt.",
)

ENTRIES = {
    ITEM_FIELD: {
        "decided_by_teacher": t(
            "deciding teacher", "преподаватель, принявший решение", "kararı veren öğretmen", "entscheidende Lehrkraft"
        ),
    },
    FRAME: {
        "Zal sessiyası bağlansın? Yenidən daxil olmaq üçün nəzarətçinin verdiyi PIN lazım olacaq.": t(
            "Close the hall session? To sign in again you will need a PIN from the invigilator.",
            "Закрыть сессию зала? Для повторного входа понадобится PIN от наблюдателя.",
            "Salon oturumu kapatılsın mı? Yeniden giriş için gözetmenin vereceği PIN gerekecek.",
            "Saalsitzung beenden? Für eine erneute Anmeldung benötigen Sie eine PIN von der Aufsicht.",
        ),
        "Zaldan çıx": t("Leave the hall", "Выйти из зала", "Salondan çık", "Saal verlassen"),
    },
    RESULT: {HALL_NOTE: HALL_NOTE_T},
    TPL: {
        HALL_NOTE: HALL_NOTE_T,
        "Fənni tədris edən": t("Subject teacher", "Преподаватель предмета", "Dersi veren", "Fachlehrkraft"),
        "təyin edilməyib": t("not assigned", "не назначен", "atanmamış", "nicht zugewiesen"),
        "Qərarı verən müəllim": t(
            "Deciding teacher", "Преподаватель, принявший решение", "Kararı veren öğretmen", "Entscheidende Lehrkraft"
        ),
        "Qərarı verən": t("Decided by", "Решение принял", "Kararı veren", "Entschieden von"),
        "Qərarın sahibi": t("Decision owner", "Ответственный за решение", "Kararın sahibi", "Verantwortlich"),
        "Müəllim axtar…": t("Search teacher…", "Поиск преподавателя…", "Öğretmen ara…", "Lehrkraft suchen…"),
        "Müəllim seçin": t("Select a teacher", "Выберите преподавателя", "Öğretmen seçin", "Lehrkraft wählen"),
        "Digər müəllimlər": t("Other teachers", "Другие преподаватели", "Diğer öğretmenler", "Andere Lehrkräfte"),
        "fənni tədris edir": t("teaches the subject", "ведёт предмет", "dersi veriyor", "unterrichtet das Fach"),
        "Yadda saxlayan siz olsanız da, qərarı (bal artımını) verən müəllim qeyd olunur.": t(
            "Even though you save it, the teacher who made the decision (the score increase) is recorded.",
            "Даже если сохраняете вы, фиксируется преподаватель, принявший решение (повышение балла).",
            "Kaydeden siz olsanız da kararı (puan artışını) veren öğretmen kaydedilir.",
            "Auch wenn Sie speichern, wird die Lehrkraft erfasst, die die Entscheidung (Punkteerhöhung) getroffen hat.",
        ),
        "Əsaslandırıcı sənəd": t(
            "Supporting document", "Обосновывающий документ", "Gerekçe belgesi", "Begründungsdokument"
        ),
        "Məcburidir: PDF, JPG və ya PNG, 10 MB-dək.": t(
            "Required: PDF, JPG or PNG, up to 10 MB.",
            "Обязательно: PDF, JPG или PNG, до 10 МБ.",
            "Zorunlu: PDF, JPG veya PNG, 10 MB'a kadar.",
            "Pflicht: PDF, JPG oder PNG, bis 10 MB.",
        ),
        "Opsional: PDF, JPG və ya PNG, 10 MB-dək.": t(
            "Optional: PDF, JPG or PNG, up to 10 MB.",
            "Необязательно: PDF, JPG или PNG, до 10 МБ.",
            "İsteğe bağlı: PDF, JPG veya PNG, 10 MB'a kadar.",
            "Optional: PDF, JPG oder PNG, bis 10 MB.",
        ),
        "Sənəd": t("Document", "Документ", "Belge", "Dokument"),
        "Şərh yazılmayıb": t("No comment", "Комментарий не написан", "Yorum yazılmamış", "Kein Kommentar"),
        "Tələbənin şərhi": t(
            "Student's comment", "Комментарий студента", "Öğrencinin yorumu", "Kommentar der Studierenden"
        ),
    },
    MSG: {
        "Qərarı verən müəllimi seçin.": t(
            "Select the deciding teacher.",
            "Выберите преподавателя, принявшего решение.",
            "Kararı veren öğretmeni seçin.",
            "Wählen Sie die entscheidende Lehrkraft.",
        ),
    },
    DOC: {
        "Qərar üçün əsaslandırıcı sənəd yükləmək məcburidir.": t(
            "Uploading a supporting document for the decision is required.",
            "Для решения необходимо загрузить обосновывающий документ.",
            "Karar için gerekçe belgesi yüklemek zorunludur.",
            "Für die Entscheidung muss ein Begründungsdokument hochgeladen werden.",
        ),
    },
    DONE: {
        "Apellyasiyanız qəbul edildi": t(
            "Your appeal has been received",
            "Ваша апелляция принята",
            "İtirazınız alındı",
            "Ihr Widerspruch ist eingegangen",
        ),
        "Midterm imtahanı": t("Midterm exam", "Промежуточный экзамен", "Ara sınav", "Zwischenprüfung"),
        "Final imtahanı": t("Final exam", "Итоговый экзамен", "Final sınavı", "Abschlussprüfung"),
        "%(count)s sual üzrə etiraz qeydə alındı.": t(
            "An objection was recorded for %(count)s question(s).",
            "Возражение зарегистрировано по вопросам: %(count)s.",
            "%(count)s soru için itiraz kaydedildi.",
            "Für %(count)s Frage(n) wurde ein Einwand erfasst.",
        ),
        "Apellyasiya komissiyası müraciətinizə baxacaq; qərar kabinetinizdə «Apellyasiyalarım» bölməsində "
        "görünəcək.": t(
            "The appeals committee will review your request; the decision will appear in your account under «My appeals».",
            "Апелляционная комиссия рассмотрит ваше обращение; решение появится в кабинете в разделе «Мои апелляции».",
            "İtiraz komisyonu başvurunuzu inceleyecek; karar hesabınızda «İtirazlarım» bölümünde görünecek.",
            "Die Widerspruchskommission prüft Ihren Antrag; die Entscheidung erscheint in Ihrem Konto unter «Meine Widersprüche».",
        ),
        "Bal dəyişərsə, nəticəniz və jurnal avtomatik yenilənəcək.": t(
            "If the score changes, your result and the gradebook will be updated automatically.",
            "Если балл изменится, ваш результат и журнал обновятся автоматически.",
            "Puan değişirse sonucunuz ve not defteri otomatik güncellenecek.",
            "Ändert sich die Punktzahl, werden Ihr Ergebnis und das Notenbuch automatisch aktualisiert.",
        ),
        "Zal sessiyanız bağlandı — kompüteri növbəti tələbə üçün bu vəziyyətdə saxlayın.": t(
            "Your hall session is closed — leave the computer as it is for the next student.",
            "Ваша сессия зала закрыта — оставьте компьютер в таком виде для следующего студента.",
            "Salon oturumunuz kapandı — bilgisayarı bir sonraki öğrenci için bu şekilde bırakın.",
            "Ihre Saalsitzung ist beendet — lassen Sie den Computer für die nächste Person so.",
        ),
        "Bitir": t("Finish", "Завершить", "Bitir", "Beenden"),
        "<span data-hall-done-countdown>%(seconds)s</span> saniyədən sonra giriş səhifəsinə qayıdacaqsınız.": t(
            "You will return to the sign-in page in <span data-hall-done-countdown>%(seconds)s</span> seconds.",
            "Через <span data-hall-done-countdown>%(seconds)s</span> секунд вы вернётесь на страницу входа.",
            "<span data-hall-done-countdown>%(seconds)s</span> saniye sonra giriş sayfasına döneceksiniz.",
            "In <span data-hall-done-countdown>%(seconds)s</span> Sekunden kehren Sie zur Anmeldeseite zurück.",
        ),
    },
    TEACHING: {
        "Fənnimə aid apellyasiyalar": t(
            "Appeals in my subjects",
            "Апелляции по моим предметам",
            "Derslerimle ilgili itirazlar",
            "Widersprüche in meinen Fächern",
        ),
        "Tədris etdiyiniz qrupların tələbələrinin bu fənlər üzrə apellyasiyaları. Qərarı imtahan mərkəzi verir — "
        "burada yalnız baxış var.": t(
            "Appeals by students of the groups you teach in these subjects. The exam centre makes the decision — "
            "this page is view-only.",
            "Апелляции студентов ваших групп по этим предметам. Решение принимает экзаменационный центр — здесь "
            "только просмотр.",
            "Ders verdiğiniz grupların öğrencilerinin bu derslerle ilgili itirazları. Kararı sınav merkezi verir — "
            "burada yalnızca görüntüleme vardır.",
            "Widersprüche von Studierenden Ihrer Gruppen in diesen Fächern. Die Entscheidung trifft das "
            "Prüfungszentrum — hier nur Ansicht.",
        ),
        "%(count)s sual": t("%(count)s question(s)", "Вопросов: %(count)s", "%(count)s soru", "%(count)s Frage(n)"),
        "%(accepted)s qəbul, %(rejected)s rədd": t(
            "%(accepted)s accepted, %(rejected)s rejected",
            "принято: %(accepted)s, отклонено: %(rejected)s",
            "%(accepted)s kabul, %(rejected)s ret",
            "%(accepted)s angenommen, %(rejected)s abgelehnt",
        ),
        "Apellyasiya yoxdur": t("No appeals", "Апелляций нет", "İtiraz yok", "Keine Widersprüche"),
        "Tədris etdiyiniz fənlər üzrə tələbələrinizin apellyasiyası olanda burada görünəcək.": t(
            "Appeals by your students in the subjects you teach will appear here.",
            "Здесь появятся апелляции ваших студентов по предметам, которые вы ведёте.",
            "Ders verdiğiniz derslerde öğrencilerinizin itirazları burada görünecek.",
            "Widersprüche Ihrer Studierenden in Ihren Fächern erscheinen hier.",
        ),
    },
    NOTE: {
        "Tələbəniz apellyasiya verdi": t(
            "Your student filed an appeal",
            "Ваш студент подал апелляцию",
            "Öğrenciniz itiraz etti",
            "Ihre Studierende/Ihr Studierender hat Widerspruch eingelegt",
        ),
        '{student} "{exam}" imtahanı üzrə {count} sual üçün apellyasiya verdi. Qərarı imtahan mərkəzi verir.': t(
            '{student} filed an appeal for {count} question(s) in the "{exam}" exam. The exam centre decides.',
            '{student} подал(а) апелляцию по {count} вопросам экзамена "{exam}". Решение принимает экзаменационный центр.',
            '{student}, "{exam}" sınavında {count} soru için itiraz etti. Kararı sınav merkezi verir.',
            '{student} hat zu {count} Frage(n) der Prüfung "{exam}" Widerspruch eingelegt. Das Prüfungszentrum entscheidet.',
        ),
        "Apellyasiya qərarı verildi": t(
            "Appeal decision made",
            "Решение по апелляции принято",
            "İtiraz kararı verildi",
            "Widerspruchsentscheidung getroffen",
        ),
        '{student} — "{exam}": {accepted} qəbul, {rejected} rədd. Qərarı verən müəllim: {teacher}, bal: {before} → '
        "{after}.": t(
            '{student} — "{exam}": {accepted} accepted, {rejected} rejected. Deciding teacher: {teacher}, score: {before} → {after}.',
            '{student} — "{exam}": принято {accepted}, отклонено {rejected}. Решение принял(а): {teacher}, балл: {before} → {after}.',
            '{student} — "{exam}": {accepted} kabul, {rejected} ret. Kararı veren öğretmen: {teacher}, puan: {before} → {after}.',
            '{student} — "{exam}": {accepted} angenommen, {rejected} abgelehnt. Entscheidende Lehrkraft: {teacher}, Punkte: {before} → {after}.',
        ),
    },
    HIST: {
        "Qərar yadda saxlanıldı — qərarı verən müəllim: {teacher} ({accepted} qəbul, {rejected} rədd)": t(
            "Decision saved — deciding teacher: {teacher} ({accepted} accepted, {rejected} rejected)",
            "Решение сохранено — решение принял(а): {teacher} (принято {accepted}, отклонено {rejected})",
            "Karar kaydedildi — kararı veren öğretmen: {teacher} ({accepted} kabul, {rejected} ret)",
            "Entscheidung gespeichert — entscheidende Lehrkraft: {teacher} ({accepted} angenommen, {rejected} abgelehnt)",
        ),
    },
    RS: {
        "Apellyasiya qərarında sənəd məcburidir": t(
            "Document required for appeal decisions",
            "Документ обязателен для решения по апелляции",
            "İtiraz kararında belge zorunludur",
            "Dokument für Widerspruchsentscheidungen erforderlich",
        ),
        "Yandırılıbsa apellyasiya qərarı (qəbul/rədd) əsaslandırıcı sənəd (PDF, JPG və ya PNG, 10 MB-dək) "
        "yüklənmədən yadda saxlanılmır. Söndürüləndə sənəd yükləmək opsionaldır. Qərarı verən müəllimin "
        "seçilməsi hər iki halda məcburidir.": t(
            "When on, an appeal decision (accept/reject) cannot be saved without uploading a supporting document "
            "(PDF, JPG or PNG, up to 10 MB). When off, uploading a document is optional. Selecting the deciding "
            "teacher is required in both cases.",
            "Если включено, решение по апелляции (принять/отклонить) нельзя сохранить без загрузки обосновывающего "
            "документа (PDF, JPG или PNG, до 10 МБ). Если выключено, загрузка документа необязательна. Выбор "
            "преподавателя, принявшего решение, обязателен в обоих случаях.",
            "Açıksa itiraz kararı (kabul/ret) gerekçe belgesi (PDF, JPG veya PNG, 10 MB'a kadar) yüklenmeden "
            "kaydedilmez. Kapalıysa belge yüklemek isteğe bağlıdır. Kararı veren öğretmenin seçilmesi her iki "
            "durumda da zorunludur.",
            "Wenn aktiviert, kann eine Widerspruchsentscheidung (annehmen/ablehnen) nicht ohne hochgeladenes "
            "Begründungsdokument (PDF, JPG oder PNG, bis 10 MB) gespeichert werden. Wenn deaktiviert, ist das "
            "Hochladen optional. Die Auswahl der entscheidenden Lehrkraft ist in beiden Fällen Pflicht.",
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
            if lang == "az":
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
