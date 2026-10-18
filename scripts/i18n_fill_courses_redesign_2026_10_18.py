#!/usr/bin/env python3
"""EMSArena i18n — «Kurslarım» redizaynı + «Sillabusdan mövzuları götür» (2026-10-18).

Kontekstlər: ``courses.list`` (kabinet siyahısı, kart, KPI, filtr), ``courses.syllabus_import`` (dialoq, endpoint
mesajları, kurs paneli çipi) və ``ui.status`` (status kataloqunun yeni ``course`` ailəsi).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud ``(msgctxt, msgid)`` cütü toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CL = "courses.list"
SI = "courses.syllabus_import"
ST = "ui.status"

ENTRIES = {
    ST: {
        "Yayımlanıb": {"en": "Published", "ru": "Опубликован", "tr": "Yayınlandı", "de": "Veröffentlicht"},
        "Arxivdədir": {"en": "Archived", "ru": "В архиве", "tr": "Arşivde", "de": "Archiviert"},
    },
    CL: {
        "Yaratdığınız və müəllim kimi qoşulduğunuz kurslar: mövzular, tapşırıqlar, imtahanlar və tələbələr bir yerdə.": {
            "en": "Courses you created or teach: topics, tasks, exams and students in one place.",
            "ru": "Курсы, которые вы создали или ведёте: темы, задания, экзамены и студенты в одном месте.",
            "tr": "Oluşturduğunuz veya öğretmen olarak katıldığınız dersler: konular, görevler, sınavlar ve öğrenciler tek yerde.",
            "de": "Kurse, die Sie erstellt haben oder unterrichten: Themen, Aufgaben, Prüfungen und Studierende an einem Ort.",
        },
        "Kurslar": {"en": "Courses", "ru": "Курсы", "tr": "Dersler", "de": "Kurse"},
        "Arxivdə: %(n)s": {
            "en": "Archived: %(n)s",
            "ru": "В архиве: %(n)s",
            "tr": "Arşivde: %(n)s",
            "de": "Archiviert: %(n)s",
        },
        "Yayımlanıb": {"en": "Published", "ru": "Опубликовано", "tr": "Yayında", "de": "Veröffentlicht"},
        "tələbələr görür": {
            "en": "visible to students",
            "ru": "видны студентам",
            "tr": "öğrenciler görür",
            "de": "für Studierende sichtbar",
        },
        "Qaralama": {"en": "Drafts", "ru": "Черновики", "tr": "Taslaklar", "de": "Entwürfe"},
        "tələbələrdən gizlidir": {
            "en": "hidden from students",
            "ru": "скрыты от студентов",
            "tr": "öğrencilerden gizli",
            "de": "für Studierende verborgen",
        },
        "Tələbələr": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler", "de": "Studierende"},
        "bütün kurslar üzrə unikal": {
            "en": "unique across all courses",
            "ru": "уникальных по всем курсам",
            "tr": "tüm derslerde benzersiz",
            "de": "eindeutig über alle Kurse",
        },
        "Sillabusa bağlı": {
            "en": "Linked to a syllabus",
            "ru": "Привязаны к силлабусу",
            "tr": "Müfredata bağlı",
            "de": "Mit Syllabus verknüpft",
        },
        "%(n)s kursdan": {
            "en": "of %(n)s courses",
            "ru": "из %(n)s курсов",
            "tr": "%(n)s dersten",
            "de": "von %(n)s Kursen",
        },
        "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama", "de": "Suche"},
        "Kurs adı, təsviri və ya fənn": {
            "en": "Course title, description or subject",
            "ru": "Название курса, описание или предмет",
            "tr": "Ders adı, açıklaması veya branşı",
            "de": "Kurstitel, Beschreibung oder Fach",
        },
        "Status": {"en": "Course status", "ru": "Статус", "tr": "Durum", "de": "Kursstatus"},
        "Bütün statuslar": {"en": "All statuses", "ru": "Все статусы", "tr": "Tüm durumlar", "de": "Alle Status"},
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Branş", "de": "Fach"},
        "Bütün fənlər": {"en": "All subjects", "ru": "Все предметы", "tr": "Tüm branşlar", "de": "Alle Fächer"},
        "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Dönem", "de": "Semester"},
        "Bütün semestrlər": {"en": "All semesters", "ru": "Все семестры", "tr": "Tüm dönemler", "de": "Alle Semester"},
        "Sıralama": {"en": "Sort", "ru": "Сортировка", "tr": "Sıralama ölçütü", "de": "Sortierung"},
        "Ən yenisi əvvəl": {"en": "Newest first", "ru": "Сначала новые", "tr": "Önce en yeni", "de": "Neueste zuerst"},
        "Son yenilənən": {
            "en": "Recently updated",
            "ru": "Недавно обновлённые",
            "tr": "Son güncellenen",
            "de": "Zuletzt aktualisiert",
        },
        "Ada görə (A–Z)": {
            "en": "By title (A–Z)",
            "ru": "По названию (А–Я)",
            "tr": "Ada göre (A–Z)",
            "de": "Nach Titel (A–Z)",
        },
        "Ən çox tələbə": {
            "en": "Most students",
            "ru": "Больше всего студентов",
            "tr": "En çok öğrenci",
            "de": "Meiste Studierende",
        },
        "Nəticə: %(n)s kurs": {
            "en": "Results: %(n)s courses",
            "ru": "Найдено курсов: %(n)s",
            "tr": "Sonuç: %(n)s ders",
            "de": "Ergebnis: %(n)s Kurse",
        },
        "Filtrə uyğun kurs tapılmadı": {
            "en": "No courses match the filters",
            "ru": "Нет курсов, подходящих под фильтр",
            "tr": "Filtreye uyan ders bulunamadı",
            "de": "Keine Kurse entsprechen dem Filter",
        },
        "Axtarışı qısaldın və ya «Sıfırla» ilə bütün kurslara qayıdın.": {
            "en": "Shorten the search or use “Reset” to see all courses again.",
            "ru": "Сократите запрос или нажмите «Сбросить», чтобы вернуться ко всем курсам.",
            "tr": "Aramayı kısaltın veya «Sıfırla» ile tüm derslere dönün.",
            "de": "Kürzen Sie die Suche oder kehren Sie mit „Zurücksetzen“ zu allen Kursen zurück.",
        },
        "Kursu yaradın — ad və qısa təsvir kifayətdir.": {
            "en": "Create the course — a title and a short description are enough.",
            "ru": "Создайте курс — достаточно названия и краткого описания.",
            "tr": "Dersi oluşturun — ad ve kısa açıklama yeterlidir.",
            "de": "Kurs anlegen — Titel und kurze Beschreibung genügen.",
        },
        "Mövzuları sillabusun həftəlik planından bir kliklə götürün.": {
            "en": "Pull topics from the syllabus weekly plan in one click.",
            "ru": "Перенесите темы из недельного плана силлабуса одним кликом.",
            "tr": "Konuları müfredatın haftalık planından tek tıkla alın.",
            "de": "Übernehmen Sie Themen mit einem Klick aus dem Wochenplan des Syllabus.",
        },
        "Qrupları əlavə edib kursu yayımlayın.": {
            "en": "Add groups and publish the course.",
            "ru": "Добавьте группы и опубликуйте курс.",
            "tr": "Grupları ekleyin ve dersi yayınlayın.",
            "de": "Gruppen hinzufügen und den Kurs veröffentlichen.",
        },
        "Görünüş": {"en": "View", "ru": "Вид", "tr": "Görünüm", "de": "Ansicht"},
        "Kartlar": {"en": "Cards", "ru": "Карточки", "tr": "Kartlar görünümü", "de": "Karten"},
        "Siyahı": {"en": "List", "ru": "Список", "tr": "Liste", "de": "Liste"},
        "Bağlı sillabus": {
            "en": "Linked syllabus",
            "ru": "Привязанный силлабус",
            "tr": "Bağlı müfredat",
            "de": "Verknüpfter Syllabus",
        },
        "Kursun göstəriciləri": {
            "en": "Course figures",
            "ru": "Показатели курса",
            "tr": "Ders göstergeleri",
            "de": "Kurskennzahlen",
        },
        "Mövzu": {"en": "Topics", "ru": "Темы", "tr": "Konu", "de": "Themen"},
        "Tapşırıq": {"en": "Tasks", "ru": "Задания", "tr": "Görev", "de": "Aufgaben"},
        "İmtahan": {"en": "Exams", "ru": "Экзамены", "tr": "Sınav", "de": "Prüfungen"},
        "Tələbə": {"en": "Students", "ru": "Студенты", "tr": "Öğrenci", "de": "Studierende"},
        "Qruplar": {"en": "Groups", "ru": "Группы", "tr": "Gruplar", "de": "Gruppen"},
        "Yeniləndi: %(date)s": {
            "en": "Updated: %(date)s",
            "ru": "Обновлено: %(date)s",
            "tr": "Güncellendi: %(date)s",
            "de": "Aktualisiert: %(date)s",
        },
        "Qaralamaya qaytar — tələbələr görməyəcək": {
            "en": "Back to draft — students will not see it",
            "ru": "Вернуть в черновик — студенты не увидят",
            "tr": "Taslağa döndür — öğrenciler görmeyecek",
            "de": "Zurück zum Entwurf — Studierende sehen ihn nicht",
        },
        "Qaralamaya qaytar": {
            "en": "Back to draft",
            "ru": "Вернуть в черновик",
            "tr": "Taslağa döndür",
            "de": "Zurück zum Entwurf",
        },
        "Yayımla — tələbələr görəcək": {
            "en": "Publish — students will see it",
            "ru": "Опубликовать — студенты увидят",
            "tr": "Yayınla — öğrenciler görecek",
            "de": "Veröffentlichen — Studierende sehen ihn",
        },
        "Yayımla": {"en": "Publish", "ru": "Опубликовать", "tr": "Yayınla", "de": "Veröffentlichen"},
        "Redaktə et": {"en": "Edit", "ru": "Редактировать", "tr": "Düzenle", "de": "Bearbeiten"},
    },
    SI: {
        "Sillabusdan götür": {
            "en": "From syllabus",
            "ru": "Из силлабуса",
            "tr": "Müfredattan al",
            "de": "Aus Syllabus",
        },
        "Sillabusdan mövzuları götür": {
            "en": "Import topics from syllabus",
            "ru": "Взять темы из силлабуса",
            "tr": "Konuları müfredattan al",
            "de": "Themen aus dem Syllabus übernehmen",
        },
        "Həftəlik plandakı mövzular kursa bir dəfəyə əlavə olunur; kursda artıq olanlar təkrarlanmır.": {
            "en": "Topics from the weekly plan are added to the course in one go; topics already in the course are not duplicated.",
            "ru": "Темы недельного плана добавляются в курс за один раз; уже существующие темы не дублируются.",
            "tr": "Haftalık plandaki konular derse tek seferde eklenir; derste zaten olanlar tekrarlanmaz.",
            "de": "Die Themen des Wochenplans werden in einem Schritt hinzugefügt; vorhandene Themen werden nicht dupliziert.",
        },
        "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat", "de": "Schließen"},
        "Sillabus seçimi": {
            "en": "Choose a syllabus",
            "ru": "Выбор силлабуса",
            "tr": "Müfredat seçimi",
            "de": "Syllabus auswählen",
        },
        "Sillabus": {"en": "Syllabus", "ru": "Силлабус", "tr": "Müfredat", "de": "Syllabus (Lehrplan)"},
        "Fənn adı və ya kodu ilə axtar": {
            "en": "Search by subject name or code",
            "ru": "Поиск по названию или коду предмета",
            "tr": "Branş adı veya koduyla ara",
            "de": "Nach Fachname oder -code suchen",
        },
        "Siyahıda yalnız baxmaq icazəniz olan sillabuslar var: öz sillabuslarınız və əhatənizdəki kafedraların sillabusları.": {
            "en": "Only syllabi you may view are listed: your own and those of departments in your scope.",
            "ru": "В списке только доступные вам силлабусы: ваши собственные и силлабусы кафедр в вашей зоне.",
            "tr": "Listede yalnızca görme yetkiniz olan müfredatlar var: kendi müfredatlarınız ve kapsamınızdaki bölümlerinkiler.",
            "de": "Aufgeführt sind nur Syllabi, die Sie einsehen dürfen: Ihre eigenen und die der Lehrstühle in Ihrem Bereich.",
        },
        "Uyğun sillabus tapılmadı. Axtarışı dəyişin və ya əvvəlcə «Sillabuslar» bölməsində sillabus hazırlayın.": {
            "en": "No matching syllabus. Change the search or prepare a syllabus in the “Syllabi” section first.",
            "ru": "Подходящий силлабус не найден. Измените запрос или сначала подготовьте силлабус в разделе «Силлабусы».",
            "tr": "Uygun müfredat bulunamadı. Aramayı değiştirin veya önce «Müfredatlar» bölümünde bir müfredat hazırlayın.",
            "de": "Kein passender Syllabus. Ändern Sie die Suche oder erstellen Sie zuerst einen Syllabus im Bereich „Syllabi“.",
        },
        "Başqa sillabus": {
            "en": "Another syllabus",
            "ru": "Другой силлабус",
            "tr": "Başka müfredat",
            "de": "Anderer Syllabus",
        },
        "Kursu bu sillabusla əlaqələndir — fənn kursun başlığında və «Kurslarım» kartında görünəcək.": {
            "en": "Link the course to this syllabus — the subject will show in the course header and on its “My courses” card.",
            "ru": "Связать курс с этим силлабусом — предмет появится в заголовке курса и на карточке «Мои курсы».",
            "tr": "Dersi bu müfredatla ilişkilendir — branş ders başlığında ve «Derslerim» kartında görünecek.",
            "de": "Kurs mit diesem Syllabus verknüpfen — das Fach erscheint im Kurskopf und auf der Karte „Meine Kurse“.",
        },
        "Ləğv et": {"en": "Cancel", "ru": "Отмена", "tr": "İptal", "de": "Abbrechen"},
        "Bağlıdır": {"en": "Linked", "ru": "Привязан", "tr": "Bağlı", "de": "Verknüpft"},
        "Mənim": {"en": "Mine", "ru": "Мой", "tr": "Benim", "de": "Meins"},
        "Yeni": {"en": "New", "ru": "Новая", "tr": "Yeni konu", "de": "Neu"},
        "Artıq var": {"en": "Already there", "ru": "Уже есть", "tr": "Zaten mevcut", "de": "Bereits vorhanden"},
        "{new} yeni mövzu · {existing} artıq var": {
            "en": "{new} new topics · {existing} already there",
            "ru": "Новых тем: {new} · уже есть: {existing}",
            "tr": "{new} yeni konu · {existing} zaten mevcut",
            "de": "{new} neue Themen · {existing} bereits vorhanden",
        },
        "Mövzuları əlavə et ({n})": {
            "en": "Add topics ({n})",
            "ru": "Добавить темы ({n})",
            "tr": "Konuları ekle ({n})",
            "de": "Themen hinzufügen ({n})",
        },
        "Yalnız kursu əlaqələndir": {
            "en": "Only link the course",
            "ru": "Только привязать курс",
            "tr": "Yalnızca dersi ilişkilendir",
            "de": "Nur den Kurs verknüpfen",
        },
        "Əlavə ediləcək yeni mövzu yoxdur — hamısı kursda var.": {
            "en": "No new topics to add — all of them are already in the course.",
            "ru": "Новых тем нет — все уже есть в курсе.",
            "tr": "Eklenecek yeni konu yok — hepsi derste mevcut.",
            "de": "Keine neuen Themen — alle sind bereits im Kurs.",
        },
        "Bu sillabusun həftəlik planında mövzu yazılmayıb.": {
            "en": "This syllabus has no topics in its weekly plan.",
            "ru": "В недельном плане этого силлабуса нет тем.",
            "tr": "Bu müfredatın haftalık planında konu yazılmamış.",
            "de": "Der Wochenplan dieses Syllabus enthält keine Themen.",
        },
        "Xəta baş verdi. Yenidən cəhd edin.": {
            "en": "Something went wrong. Please try again.",
            "ru": "Произошла ошибка. Попробуйте ещё раз.",
            "tr": "Bir hata oluştu. Tekrar deneyin.",
            "de": "Ein Fehler ist aufgetreten. Bitte erneut versuchen.",
        },
        "Əlavə olunur…": {"en": "Adding…", "ru": "Добавление…", "tr": "Ekleniyor…", "de": "Wird hinzugefügt…"},
        "Bağlı sillabus": {
            "en": "Linked syllabus",
            "ru": "Привязанный силлабус",
            "tr": "Bağlı müfredat",
            "de": "Verknüpfter Syllabus",
        },
        "Sillabus: %(subject)s": {
            "en": "Syllabus: %(subject)s",
            "ru": "Силлабус: %(subject)s",
            "tr": "Müfredat: %(subject)s",
            "de": "Syllabus: %(subject)s",
        },
        "Həftə %(n)s": {"en": "Week %(n)s", "ru": "Неделя %(n)s", "tr": "Hafta %(n)s", "de": "Woche %(n)s"},
        "%(kind)s: %(n)s saat": {
            "en": "%(kind)s: %(n)s h",
            "ru": "%(kind)s: %(n)s ч",
            "tr": "%(kind)s: %(n)s saat ders",
            "de": "%(kind)s: %(n)s Std.",
        },
        "Mühazirə": {"en": "Lecture", "ru": "Лекция", "tr": "Ders anlatımı", "de": "Vorlesung"},
        "Seminar": {"en": "Seminar class", "ru": "Семинар", "tr": "Uygulama", "de": "Übung"},
        "Laboratoriya": {"en": "Lab", "ru": "Лабораторная", "tr": "Laboratuvar", "de": "Labor"},
        "Baza sillabus (semestrsiz)": {
            "en": "Base syllabus (no semester)",
            "ru": "Базовый силлабус (без семестра)",
            "tr": "Temel müfredat (dönemsiz)",
            "de": "Basis-Syllabus (ohne Semester)",
        },
        "Bu kursda mövzu idxalına icazəniz yoxdur.": {
            "en": "You are not allowed to import topics into this course.",
            "ru": "У вас нет права импортировать темы в этот курс.",
            "tr": "Bu derse konu aktarma yetkiniz yok.",
            "de": "Sie dürfen in diesen Kurs keine Themen importieren.",
        },
        "Sillabus tapılmadı və ya ona baxmaq icazəniz yoxdur.": {
            "en": "Syllabus not found, or you are not allowed to view it.",
            "ru": "Силлабус не найден или у вас нет права его просматривать.",
            "tr": "Müfredat bulunamadı veya görme yetkiniz yok.",
            "de": "Syllabus nicht gefunden oder Sie dürfen ihn nicht einsehen.",
        },
        "Kurs tapılmadı.": {
            "en": "Course not found.",
            "ru": "Курс не найден.",
            "tr": "Ders bulunamadı.",
            "de": "Kurs nicht gefunden.",
        },
        "%(created)s mövzu əlavə olundu, %(skipped)s artıq var idi.": {
            "en": "%(created)s topics added, %(skipped)s were already there.",
            "ru": "Добавлено тем: %(created)s, уже было: %(skipped)s.",
            "tr": "%(created)s konu eklendi, %(skipped)s zaten vardı.",
            "de": "%(created)s Themen hinzugefügt, %(skipped)s waren bereits vorhanden.",
        },
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
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            flag = "#, python-format\n" if "%(" in msgid else ""
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
