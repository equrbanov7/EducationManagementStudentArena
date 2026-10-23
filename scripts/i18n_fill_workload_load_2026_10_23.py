#!/usr/bin/env python3
"""EMSArena i18n — Tədris şöbəsinin «Dərs yükü faylı» (Excel/Forma 1 yükləmə) + icazə açarı (2026-10-23).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WL = "accounts.workload_load"
WC = "accounts.workload_center"
PERM = "organizations.permission.label"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    WC: {"Dərs yükü faylı": t("Teaching load file", "Файл учебной нагрузки", "Ders yükü dosyası", "Lehrdeputat-Datei")},
    PERM: {
        "Dərs yükü faylını yükləmək (bölgü, açılış və tələbə qeydiyyatı avtomatik)": t(
            "Upload the teaching load file (distribution, course openings and student enrolment are automatic)",
            "Загружать файл учебной нагрузки (распределение, открытие курсов и запись студентов — автоматически)",
            "Ders yükü dosyasını yüklemek (dağıtım, açılış ve öğrenci kaydı otomatik)",
            "Lehrdeputat-Datei hochladen (Verteilung, Kurseröffnung und Einschreibung automatisch)",
        ),
    },
    WL: {
        "%(chair)s — «%(file)s». Aşağıdakı nəticəni yoxlayın və «Tətbiq et» basın. Qırmızı sətirlər yazılmayacaq (müəllim vakant qalır və ya sətir yaradılmır) — faylı düzəldib yenidən yükləyə bilərsiniz.": t(
            "%(chair)s — “%(file)s”. Check the result below and press “Apply”. Red rows will not be written (the teacher stays vacant or the row is not created) — you can fix the file and upload it again.",
            "%(chair)s — «%(file)s». Проверьте результат ниже и нажмите «Применить». Красные строки не будут записаны (преподаватель остаётся вакантным или строка не создаётся) — можно исправить файл и загрузить снова.",
            "%(chair)s — “%(file)s”. Aşağıdaki sonucu kontrol edip “Uygula”ya basın. Kırmızı satırlar yazılmayacak (öğretim elemanı boş kalır veya satır oluşturulmaz) — dosyayı düzeltip yeniden yükleyebilirsiniz.",
            "%(chair)s — „%(file)s“. Prüfen Sie das Ergebnis unten und klicken Sie auf „Anwenden“. Rote Zeilen werden nicht geschrieben (Lehrkraft bleibt unbesetzt oder Zeile wird nicht angelegt) — Sie können die Datei korrigieren und erneut hochladen.",
        ),
        "%(chair)s — «%(file)s». Müəllimlərə bildiriş getdi, fənlər tələbələrin kabinetində görünür.": t(
            "%(chair)s — “%(file)s”. Teachers have been notified; the subjects are visible in the students' accounts.",
            "%(chair)s — «%(file)s». Преподаватели уведомлены, дисциплины видны в кабинетах студентов.",
            "%(chair)s — “%(file)s”. Öğretim elemanlarına bildirim gitti, dersler öğrencilerin hesabında görünüyor.",
            "%(chair)s — „%(file)s“. Die Lehrkräfte wurden benachrichtigt, die Fächer sind in den Studierendenkonten sichtbar.",
        ),
        "Açılacaq yeni müəllim hesabları": t(
            "New teacher accounts to be created",
            "Будут созданы новые учётные записи преподавателей",
            "Açılacak yeni öğretim elemanı hesapları",
            "Neu anzulegende Lehrkraft-Konten",
        ),
        "Açılmış yeni müəllim hesabları": t(
            "New teacher accounts created",
            "Созданные учётные записи преподавателей",
            "Açılan yeni öğretim elemanı hesapları",
            "Neu angelegte Lehrkraft-Konten",
        ),
        "Bir neçə uyğun hesab — vakant qalır": t(
            "Several matching accounts — stays vacant",
            "Несколько подходящих учётных записей — остаётся вакантным",
            "Birden çok uygun hesap — boş kalır",
            "Mehrere passende Konten — bleibt unbesetzt",
        ),
        "Bölgü": t("Distribution", "Распределение", "Dağıtım", "Verteilung"),
        "Daha %(count)s sətir göstərilmir (problemli sətirlər yuxarıdadır).": t(
            "%(count)s more rows are not shown (problem rows are at the top).",
            "Ещё %(count)s строк не показано (проблемные строки вверху).",
            "%(count)s satır daha gösterilmiyor (sorunlu satırlar üstte).",
            "Weitere %(count)s Zeilen werden nicht angezeigt (Problemzeilen stehen oben).",
        ),
        "DƏYİŞMƏYƏN": t("UNCHANGED", "БЕЗ ИЗМЕНЕНИЙ", "DEĞİŞMEYEN", "UNVERÄNDERT"),
        "Dəqiq tapılmadı — vakant qalır": t(
            "Not found exactly — stays vacant",
            "Точно не найден — остаётся вакантным",
            "Tam bulunamadı — boş kalır",
            "Nicht eindeutig gefunden — bleibt unbesetzt",
        ),
        "Dərs deyil (dissertasiya rəhbərliyi və s.)": t(
            "Not a class (thesis supervision, etc.)",
            "Не занятие (руководство диссертацией и т. п.)",
            "Ders değil (tez danışmanlığı vb.)",
            "Keine Lehrveranstaltung (Betreuung von Abschlussarbeiten usw.)",
        ),
        "Dərs yükü faylı": t("Teaching load file", "Файл учебной нагрузки", "Ders yükü dosyası", "Lehrdeputat-Datei"),
        "Dərs yükü faylını yükləmək üçün icazə yoxdur": t(
            "You are not allowed to upload the teaching load file",
            "Нет права загружать файл учебной нагрузки",
            "Ders yükü dosyasını yükleme yetkiniz yok",
            "Keine Berechtigung zum Hochladen der Lehrdeputat-Datei",
        ),
        "Dərs yükü sistemə yazıldı": t(
            "The teaching load has been written to the system",
            "Учебная нагрузка записана в систему",
            "Ders yükü sisteme yazıldı",
            "Das Lehrdeputat wurde ins System übernommen",
        ),
        "Dərs yükü sistemə yazılsın? Müəllimlərə bildiriş gedəcək, fənlər tələbələrin kabinetinə düşəcək. Bu bir neçə dəqiqə çəkə bilər.": t(
            "Write the teaching load to the system? Teachers will be notified and the subjects will appear in the students' accounts. This may take a few minutes.",
            "Записать учебную нагрузку в систему? Преподаватели получат уведомление, дисциплины появятся в кабинетах студентов. Это может занять несколько минут.",
            "Ders yükü sisteme yazılsın mı? Öğretim elemanlarına bildirim gidecek, dersler öğrencilerin hesabına düşecek. Bu birkaç dakika sürebilir.",
            "Lehrdeputat ins System übernehmen? Die Lehrkräfte werden benachrichtigt, die Fächer erscheinen in den Studierendenkonten. Das kann einige Minuten dauern.",
        ),
        "Dəyişiklik yoxdur": t("No change", "Без изменений", "Değişiklik yok", "Keine Änderung"),
        "Excel şablonu (.xlsx) və ya kafedranın «Forma 1» sənədi (.docx) · %(year)s tədris ili · maksimum 10 MB. Yoxlama bir neçə dəqiqə çəkə bilər.": t(
            "Excel template (.xlsx) or the chair's “Form 1” document (.docx) · academic year %(year)s · max 10 MB. The check may take a few minutes.",
            "Шаблон Excel (.xlsx) или документ кафедры «Форма 1» (.docx) · %(year)s учебный год · максимум 10 МБ. Проверка может занять несколько минут.",
            "Excel şablonu (.xlsx) veya bölümün “Form 1” belgesi (.docx) · %(year)s eğitim yılı · en fazla 10 MB. Kontrol birkaç dakika sürebilir.",
            "Excel-Vorlage (.xlsx) oder das „Formular 1“ des Lehrstuhls (.docx) · Studienjahr %(year)s · max. 10 MB. Die Prüfung kann einige Minuten dauern.",
        ),
        "Excel şablonunu yüklə": t(
            "Download the Excel template",
            "Скачать шаблон Excel",
            "Excel şablonunu indir",
            "Excel-Vorlage herunterladen",
        ),
        "FAYL SƏTRİ": t("FILE ROWS", "СТРОКИ ФАЙЛА", "DOSYA SATIRI", "DATEIZEILEN"),
        "Fayldakı hər sətir — müəllim, qrup, fənn, saatlar — kafedranın tapşırığına yazılır, müəllimə bölünür, fənn qrupun tələbələrinin kabinetinə düşür və müəllim elektron jurnalı yaza bilir. Əvvəlcə önizləmə göstərilir — «Tətbiq et» basılmayınca heç nə yazılmır. Eyni faylı təkrar yükləmək heç nəyi ikiqat etmir.": t(
            "Every row of the file — teacher, group, subject, hours — is written to the chair's assignment, distributed to the teacher, the subject appears in the group's student accounts and the teacher can keep the e-journal. A preview comes first — nothing is written until you press “Apply”. Uploading the same file again duplicates nothing.",
            "Каждая строка файла — преподаватель, группа, дисциплина, часы — записывается в задание кафедры, распределяется преподавателю, дисциплина появляется в кабинетах студентов группы, и преподаватель может вести электронный журнал. Сначала показывается предпросмотр — пока не нажата «Применить», ничего не записывается. Повторная загрузка того же файла ничего не дублирует.",
            "Dosyadaki her satır — öğretim elemanı, grup, ders, saatler — bölümün görevine yazılır, öğretim elemanına dağıtılır, ders grubun öğrencilerinin hesabına düşer ve öğretim elemanı e-yoklamayı yazabilir. Önce ön izleme gösterilir — “Uygula”ya basılmadan hiçbir şey yazılmaz. Aynı dosyayı yeniden yüklemek hiçbir şeyi çoğaltmaz.",
            "Jede Zeile der Datei — Lehrkraft, Gruppe, Fach, Stunden — wird in den Lehrauftrag des Lehrstuhls geschrieben, der Lehrkraft zugeteilt, das Fach erscheint in den Konten der Studierenden der Gruppe und die Lehrkraft kann das elektronische Journal führen. Zuerst gibt es eine Vorschau — vor „Anwenden“ wird nichts geschrieben. Ein erneutes Hochladen derselben Datei verdoppelt nichts.",
        ),
        "Faylı oxu və yoxla": t(
            "Read and check the file",
            "Прочитать и проверить файл",
            "Dosyayı oku ve kontrol et",
            "Datei lesen und prüfen",
        ),
        "FİN və e-poçt sonra: müəllim ilk girişdə özü yazır. Birdəfəlik parolu RİM mərkəzi «Parol təyini» ilə verir.": t(
            "PIN and e-mail come later: the teacher enters them at first login. The Digital Development Centre issues the one-time password via “Set password”.",
            "ФИН и e-mail — позже: преподаватель вводит их сам при первом входе. Одноразовый пароль выдаёт ЦЦР через «Назначение пароля».",
            "FİN ve e-posta sonra: öğretim elemanı ilk girişte kendisi yazar. Tek kullanımlık parolayı RİM merkezi “Parola atama” ile verir.",
            "FIN und E-Mail später: Die Lehrkraft gibt sie bei der ersten Anmeldung selbst ein. Das Einmalpasswort vergibt das Digitalzentrum über „Passwort festlegen“.",
        ),
        "Fənn": t("Subject", "Дисциплина", "Ders", "Fach"),
        "Fənn müəyyən olunmadı": t(
            "Subject could not be determined",
            "Дисциплина не определена",
            "Ders belirlenemedi",
            "Fach konnte nicht bestimmt werden",
        ),
        "Fənnin adı boşdur": t(
            "Subject name is empty", "Название дисциплины пустое", "Ders adı boş", "Fachname ist leer"
        ),
        "Hesab bloklanıb — RİM aktivləşdirməlidir": t(
            "Account is blocked — the Digital Development Centre must reactivate it",
            "Учётная запись заблокирована — ЦЦР должен её активировать",
            "Hesap engellenmiş — RİM etkinleştirmeli",
            "Konto gesperrt — das Digitalzentrum muss es reaktivieren",
        ),
        "HƏLL OLUNMAYAN": t("UNRESOLVED", "НЕ РЕШЕНО", "ÇÖZÜLMEYEN", "UNGELÖST"),
        "Kafedra": t("Chair", "Кафедра", "Bölüm", "Lehrstuhl"),
        "Kafedra adı ilə axtar…": t(
            "Search by chair name…", "Поиск по названию кафедры…", "Bölüm adıyla ara…", "Nach Lehrstuhl suchen…"
        ),
        "Kafedranın dərs yükünü bir faylla sistemə yükləyin": t(
            "Upload the chair's teaching load with one file",
            "Загрузите учебную нагрузку кафедры одним файлом",
            "Bölümün ders yükünü tek dosyayla sisteme yükleyin",
            "Laden Sie das Lehrdeputat des Lehrstuhls mit einer Datei hoch",
        ),
        "Ləğv et": t("Cancel", "Отмена", "İptal", "Abbrechen"),
        "Mövcud sətir": t("Existing row", "Существующая строка", "Mevcut satır", "Bestehende Zeile"),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretim elemanı", "Lehrkraft"),
        "Müəllim dəyişdirildi": t(
            "Teacher changed", "Преподаватель изменён", "Öğretim elemanı değiştirildi", "Lehrkraft geändert"
        ),
        "Müəllim yazılmayıb": t(
            "No teacher given", "Преподаватель не указан", "Öğretim elemanı yazılmamış", "Keine Lehrkraft angegeben"
        ),
        "Müəllimin adı oxunmadı": t(
            "Teacher's name could not be read",
            "Имя преподавателя не распознано",
            "Öğretim elemanının adı okunamadı",
            "Name der Lehrkraft nicht lesbar",
        ),
        "Namizədlər:": t("Candidates:", "Кандидаты:", "Adaylar:", "Kandidaten:"),
        "Qrup sistemdə tapılmadı: %(groups)s": t(
            "Group not found in the system: %(groups)s",
            "Группа не найдена в системе: %(groups)s",
            "Grup sistemde bulunamadı: %(groups)s",
            "Gruppe im System nicht gefunden: %(groups)s",
        ),
        "Qrup(lar)": t("Group(s)", "Группа(ы)", "Grup(lar)", "Gruppe(n)"),
        "Saat": t("Hours", "Часы", "Saatler", "Stunden"),
        "Saat yoxdur": t("No hours", "Нет часов", "Saat yok", "Keine Stunden"),
        "Sem.": t("Semester", "Сем.", "Dönem", "Semester"),
        "Seçin": t("Select", "Выберите", "Seçiniz", "Auswählen"),
        "Seçmə bloku — seçilmiş fənni yazın": t(
            "Elective block — write the chosen subject",
            "Блок по выбору — укажите выбранную дисциплину",
            "Seçmeli blok — seçilen dersi yazın",
            "Wahlblock — tragen Sie das gewählte Fach ein",
        ),
        "Sətir": t("Row", "Строка", "Satır", "Zeile"),
        "Sətir tapılmadı": t("Row not found", "Строка не найдена", "Satır bulunamadı", "Zeile nicht gefunden"),
        "Tapıldı": t("Found", "Найден", "Bulundu", "Gefunden"),
        "Tapıldı (inisiallarla)": t(
            "Found (by initials)", "Найден (по инициалам)", "Bulundu (baş harflerle)", "Gefunden (über Initialen)"
        ),
        "Tapıldı (yazı səhvi nəzərə alındı)": t(
            "Found (typo taken into account)",
            "Найден (с учётом опечатки)",
            "Bulundu (yazım hatası dikkate alındı)",
            "Gefunden (Tippfehler berücksichtigt)",
        ),
        "Tapıldı — ata adı fərqli yazılıb, yoxlayın": t(
            "Found — patronymic is spelled differently, please check",
            "Найден — отчество написано иначе, проверьте",
            "Bulundu — baba adı farklı yazılmış, kontrol edin",
            "Gefunden — Vatersname anders geschrieben, bitte prüfen",
        ),
        "Tapşırıq bu statusda yeni sətir qəbul etmir": t(
            "The assignment does not accept new rows in this status",
            "Задание в этом статусе не принимает новые строки",
            "Görev bu durumda yeni satır kabul etmiyor",
            "Der Lehrauftrag nimmt in diesem Status keine neuen Zeilen an",
        ),
        "Tapşırıq sətri": t("Assignment row", "Строка задания", "Görev satırı", "Auftragszeile"),
        "TƏLƏBƏ QEYDİYYATI": t("STUDENT ENROLMENTS", "ЗАПИСИ СТУДЕНТОВ", "ÖĞRENCİ KAYDI", "EINSCHREIBUNGEN"),
        "TƏYİN / DƏYİŞİKLİK": t(
            "ASSIGNED / CHANGED", "НАЗНАЧЕНО / ИЗМЕНЕНО", "ATAMA / DEĞİŞİKLİK", "ZUGEWIESEN / GEÄNDERT"
        ),
        "Tətbiq et": t("Apply", "Применить", "Uygula", "Anwenden"),
        "Təyin olundu": t("Assigned", "Назначено", "Atandı", "Zugewiesen"),
        "Uyğun kafedra tapılmadı": t(
            "No matching chair found",
            "Подходящая кафедра не найдена",
            "Uygun bölüm bulunamadı",
            "Kein passender Lehrstuhl gefunden",
        ),
        "YENİ JURNAL (AÇILIŞ)": t(
            "NEW JOURNALS (OPENINGS)",
            "НОВЫЕ ЖУРНАЛЫ (ОТКРЫТИЯ)",
            "YENİ YOKLAMA (AÇILIŞ)",
            "NEUE JOURNALE (ERÖFFNUNGEN)",
        ),
        "YENİ MÜƏLLİM": t("NEW TEACHERS", "НОВЫЕ ПРЕПОДАВАТЕЛИ", "YENİ ÖĞRETİM ELEMANI", "NEUE LEHRKRÄFTE"),
        "YENİ SƏTİR": t("NEW ROWS", "НОВЫЕ СТРОКИ", "YENİ SATIR", "NEUE ZEILEN"),
        "Yeni fayl yüklə": t("Upload a new file", "Загрузить новый файл", "Yeni dosya yükle", "Neue Datei hochladen"),
        "Yeni hesab — eyni adlı başqa şəxs var, yoxlayın": t(
            "New account — another person with the same name exists, please check",
            "Новая учётная запись — есть другой человек с тем же именем, проверьте",
            "Yeni hesap — aynı adlı başka biri var, kontrol edin",
            "Neues Konto — es gibt eine andere Person mit gleichem Namen, bitte prüfen",
        ),
        "Yeni müəllim hesabı": t(
            "New teacher account",
            "Новая учётная запись преподавателя",
            "Yeni öğretim elemanı hesabı",
            "Neues Lehrkraft-Konto",
        ),
        "Yeni sətir": t("New row", "Новая строка", "Yeni satır", "Neue Zeile"),
        "Yeni sətir; tapılmayan qrup: %(groups)s": t(
            "New row; group not found: %(groups)s",
            "Новая строка; группа не найдена: %(groups)s",
            "Yeni satır; bulunamayan grup: %(groups)s",
            "Neue Zeile; Gruppe nicht gefunden: %(groups)s",
        ),
        "müəllim: %(n)d": t("teachers: %(n)d", "преподаватели: %(n)d", "öğretim elemanı: %(n)d", "Lehrkräfte: %(n)d"),
        "«Dərs yükü faylını yükləmək» açarı Tədris şöbəsinə və RİM-ə verilir. Lazımdırsa rolunuza əlavə etdirin.": t(
            "The “Upload the teaching load file” permission is given to the Teaching Office and the Digital Development Centre. Ask for it to be added to your role if needed.",
            "Право «Загружать файл учебной нагрузки» выдаётся учебному отделу и ЦЦР. При необходимости попросите добавить его вашей роли.",
            "“Ders yükü dosyasını yüklemek” yetkisi Eğitim bölümüne ve RİM'e verilir. Gerekirse rolünüze eklettirin.",
            "Die Berechtigung „Lehrdeputat-Datei hochladen“ erhalten das Studienbüro und das Digitalzentrum. Lassen Sie sie bei Bedarf Ihrer Rolle hinzufügen.",
        ),
        "Önizləmə — hələ heç nə yazılmayıb": t(
            "Preview — nothing has been written yet",
            "Предпросмотр — пока ничего не записано",
            "Ön izleme — henüz hiçbir şey yazılmadı",
            "Vorschau — es wurde noch nichts geschrieben",
        ),
        "Ötürülən sətirlər": t("Skipped rows", "Пропущенные строки", "Atlanan satırlar", "Übersprungene Zeilen"),
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
