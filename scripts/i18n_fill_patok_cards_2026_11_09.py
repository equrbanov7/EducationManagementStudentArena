#!/usr/bin/env python3
"""«Bir fənn = bir kart» (Yük bölgüsü, sahib 2026-11-09): yalnız YENİ msgid-ləri əlavə edir.

Mövcud tərcümələrə toxunmur; kataloqa düz mətn kimi əlavə olunur (polib yalnız oxuyur), sonra ``msgfmt``.
"""

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
        "accounts.workload": {
            "Alt qrup": t("Sub-group", "Подгруппа", "Alt grup", "Untergruppe"),
            "Aşağıda hər sətri bir axına salın və axının mühazirəçisini seçin. Bir sətrin qrupları birlikdə hərəkət edir — qrupları ayırmaq üçün sətri «Redaktə» ilə bölün.": t(
                "Below, put each row into a stream and pick the stream's lecturer. The groups of one row move together — to separate them, split the row via “Edit”.",
                "Ниже поместите каждую строку в поток и выберите лектора потока. Группы одной строки перемещаются вместе — чтобы разделить их, разбейте строку через «Редактировать».",
                "Aşağıda her satırı bir akışa yerleştirin ve akışın öğretim üyesini seçin. Bir satırın grupları birlikte hareket eder — ayırmak için satırı «Düzenle» ile bölün.",
                "Ordnen Sie unten jede Zeile einem Strom zu und wählen Sie den Dozenten des Stroms. Die Gruppen einer Zeile bewegen sich gemeinsam — zum Trennen die Zeile über „Bearbeiten“ aufteilen.",
            ),
            "Hər qrup üçün müəllimi və saatı seçin; bir qrupa bir neçə müəllim (saat bölgüsü və ya Lab-1 / Lab-2) əlavə edilə bilər. Saat sətrin cəmindən çox ola bilməz.": t(
                "Pick a teacher and hours for each group; a group may get several teachers (hour split or Lab-1 / Lab-2). Hours cannot exceed the row total.",
                "Выберите преподавателя и часы для каждой группы; у группы может быть несколько преподавателей (разделение часов или Lab-1 / Lab-2). Часы не могут превышать итог строки.",
                "Her grup için öğretmeni ve saati seçin; bir gruba birden fazla öğretmen (saat bölüşümü veya Lab-1 / Lab-2) eklenebilir. Saat, satır toplamını aşamaz.",
                "Wählen Sie für jede Gruppe Lehrkraft und Stunden; eine Gruppe kann mehrere Lehrkräfte haben (Stundenaufteilung oder Lab-1 / Lab-2). Die Stunden dürfen die Zeilensumme nicht überschreiten.",
            ),
            "Kafedranın illik tədris tapşırığını müəllimlər arasında bölün. Eyni fənn, semestr və kredit — bir kartdır: mühazirə axınları (patok), seminar və laboratoriya qrup-qrup bölünür; qalıq saat real vaxtda göstərilir. Bölgü təsdiqlənəndə müəllimlərə bildiriş gedir və elektron jurnal açılışları yaradılır.": t(
                "Distribute the department's annual teaching assignment among teachers. Same subject, semester and credits form one card: lecture streams (joint lectures), seminars and labs are distributed group by group; remaining hours update live. Confirming the distribution notifies teachers and creates the e-journal offerings.",
                "Распределите годовое учебное поручение кафедры между преподавателями. Один предмет, семестр и кредиты — одна карточка: лекционные потоки, семинары и лабораторные распределяются по группам; остаток часов обновляется в реальном времени. При подтверждении преподаватели получают уведомление и создаются электронные журналы.",
                "Bölümün yıllık ders görevini öğretmenler arasında dağıtın. Aynı ders, dönem ve kredi tek karttır: ders akışları (ortak dersler), seminer ve laboratuvar grup grup dağıtılır; kalan saat anlık gösterilir. Dağıtım onaylandığında öğretmenlere bildirim gider ve e-defter açılışları oluşturulur.",
                "Verteilen Sie den jährlichen Lehrauftrag des Lehrstuhls auf die Lehrkräfte. Gleiches Fach, Semester und Credits bilden eine Karte: Vorlesungsströme (gemeinsame Vorlesungen), Seminare und Labore werden gruppenweise verteilt; die Reststunden werden live angezeigt. Mit der Bestätigung werden die Lehrkräfte benachrichtigt und die E-Journale angelegt.",
            ),
            "Mühazirə axınları (patok)": t(
                "Lecture streams (joint lectures)",
                "Лекционные потоки",
                "Ders akışları (ortak dersler)",
                "Vorlesungsströme (gemeinsame Vorlesungen)",
            ),
            "Nəticə": t("Result", "Результат", "Sonuç", "Ergebnis"),
            "Patok — bir neçə qrupun mühazirəni birlikdə dinləməsidir. Eyni axındakı qrupların mühazirəsi müəllimin yükünə BİR dəfə düşür.": t(
                "A joint lecture (stream) is several groups attending the lecture together. The lecture of groups in one stream counts ONCE in the teacher's load.",
                "Поток — несколько групп слушают лекцию вместе. Лекция групп одного потока учитывается в нагрузке преподавателя ОДИН раз.",
                "Ortak ders (akış), birkaç grubun dersi birlikte dinlemesidir. Aynı akıştaki grupların dersi öğretmenin yüküne BİR kez sayılır.",
                "Ein Strom (gemeinsame Vorlesung) bedeutet, dass mehrere Gruppen die Vorlesung zusammen hören. Die Vorlesung der Gruppen eines Stroms zählt EINMAL in der Lehrbelastung.",
            ),
            "Qayda": t("Rule", "Правило", "Kural", "Regel"),
            "Qruplar üzrə bölgü": t(
                "Distribution by groups", "Распределение по группам", "Gruplara göre dağıtım", "Verteilung nach Gruppen"
            ),
            "Sil": t("Delete", "Удалить", "Kaldır", "Löschen"),
            "Sistem axını «aparıcı sətir» bağı ilə tanıyır: axının mühazirə saatı aparıcı sətirdə qalır, digər sətirlərdə mühazirə cəmi 0 olur və onlar aparıcıya bağlanır. Hər qrupun jurnalında mühazirə öz saatı ilə görünür.": t(
                "The system recognises a stream by the “lead row” link: the stream's lecture hours stay on the lead row, the other rows get a lecture total of 0 and are linked to the lead. Each group's journal still shows the lecture with its own hours.",
                "Система распознаёт поток по связи «ведущая строка»: лекционные часы потока остаются в ведущей строке, у остальных строк итог лекций становится 0, и они привязываются к ведущей. В журнале каждой группы лекция отображается со своими часами.",
                "Sistem akışı «öncü satır» bağıyla tanır: akışın ders saati öncü satırda kalır, diğer satırlarda ders toplamı 0 olur ve öncüye bağlanır. Her grubun defterinde ders kendi saatiyle görünür.",
                "Das System erkennt einen Strom über die Verknüpfung „führende Zeile“: die Vorlesungsstunden bleiben in der führenden Zeile, die übrigen Zeilen erhalten eine Vorlesungssumme von 0 und werden mit ihr verknüpft. Im Journal jeder Gruppe erscheint die Vorlesung mit ihren eigenen Stunden.",
            ),
            "Sətirlər → axın": t("Rows → stream", "Строки → поток", "Satırlar → akış", "Zeilen → Strom"),
            "Ödəniş": t("Payment", "Оплата", "Ödeme", "Vergütung"),
        },
    },
    "djangojs": {
        "": {
            "%(credits)s kredit": t(
                "%(credits)s credits", "%(credits)s кредитов", "%(credits)s kredi", "%(credits)s Credits"
            ),
            "%(hours)s s": t("%(hours)s h", "%(hours)s ч", "%(hours)s sa", "%(hours)s Std."),
            "%(hours)s saat": t("%(hours)s hours", "%(hours)s часов", "%(hours)s ders saati", "%(hours)s Stunden"),
            "%(kind)s bölgüsü — %(subject)s": t(
                "%(kind)s distribution — %(subject)s",
                "Распределение: %(kind)s — %(subject)s",
                "%(kind)s dağıtımı — %(subject)s",
                "Verteilung %(kind)s — %(subject)s",
            ),
            "%(n)s axın (qruplar ayrılmayıb)": t(
                "%(n)s streams (groups not separated)",
                "%(n)s потока (группы не разделены)",
                "%(n)s akış (gruplar ayrılmamış)",
                "%(n)s Ströme (Gruppen nicht getrennt)",
            ),
            "%(n)s axın · yükə %(hours)s": t(
                "%(n)s stream(s) · %(hours)s in load",
                "%(n)s поток(а) · в нагрузку %(hours)s",
                "%(n)s akış · yüke %(hours)s",
                "%(n)s Strom/Ströme · %(hours)s in der Belastung",
            ),
            "%(n)s qrup": t("%(n)s groups", "%(n)s групп", "%(n)s grup", "%(n)s Gruppen"),
            "%(n)s qrup · %(hours)s": t(
                "%(n)s groups · %(hours)s",
                "%(n)s групп · %(hours)s",
                "%(n)s grup · %(hours)s",
                "%(n)s Gruppen · %(hours)s",
            ),
            "%(n)s tələbə": t("%(n)s students", "%(n)s студентов", "%(n)s öğrenci", "%(n)s Studierende"),
            "Aparıcı başqa kartdadır": t(
                "Lead row is on another card",
                "Ведущая строка в другой карточке",
                "Öncü satır başka kartta",
                "Führende Zeile ist auf einer anderen Karte",
            ),
            "Aparıcı seçilməyib — mühazirə yükə düşmür": t(
                "No lead row selected — lecture is not counted in the load",
                "Ведущая строка не выбрана — лекция не входит в нагрузку",
                "Öncü satır seçilmemiş — ders yüke girmiyor",
                "Keine führende Zeile gewählt — Vorlesung zählt nicht zur Belastung",
            ),
            "Axın %(n)s": t("Stream %(n)s", "Поток %(n)s", "Akış %(n)s", "Strom %(n)s"),
            "Axınları dəyiş": t("Change streams", "Изменить потоки", "Akışları değiştir", "Ströme ändern"),
            "Bir sətrin qrupları birlikdə hərəkət edir — ayırmaq üçün sətri «Redaktə» ilə bölün.": t(
                "The groups of one row move together — split the row via “Edit” to separate them.",
                "Группы одной строки перемещаются вместе — чтобы разделить, разбейте строку через «Редактировать».",
                "Bir satırın grupları birlikte hareket eder — ayırmak için satırı «Düzenle» ile bölün.",
                "Die Gruppen einer Zeile bewegen sich gemeinsam — zum Trennen die Zeile über „Bearbeiten“ aufteilen.",
            ),
            "Birgə — saat başqa sətirdədir": t(
                "Joint — hours are on another row",
                "Совместно — часы в другой строке",
                "Ortak — saat başka satırda",
                "Gemeinsam — Stunden stehen in einer anderen Zeile",
            ),
            "Bu fəndə aparıcısı seçilməmiş patok sətri var — «Axınları dəyiş» ilə qrupları axına bağlayın.": t(
                "This subject has a joint-lecture row without a lead — link the groups to a stream via “Change streams”.",
                "У этого предмета есть строка потока без ведущей — свяжите группы с потоком через «Изменить потоки».",
                "Bu derste öncüsü seçilmemiş ortak ders satırı var — «Akışları değiştir» ile grupları akışa bağlayın.",
                "Dieses Fach hat eine Stromzeile ohne führende Zeile — verknüpfen Sie die Gruppen über „Ströme ändern“.",
            ),
            "Bütün qrup": t("Whole group", "Вся группа", "Tüm grup", "Ganze Gruppe"),
            "Bütün qruplar birlikdə": t(
                "All groups together", "Все группы вместе", "Tüm gruplar birlikte", "Alle Gruppen zusammen"
            ),
            "Göstərilir: %(shown)s / %(total)s fənn": t(
                "Showing %(shown)s of %(total)s subjects",
                "Показано %(shown)s из %(total)s предметов",
                "%(total)s dersten %(shown)s tanesi gösteriliyor",
                "%(shown)s von %(total)s Fächern angezeigt",
            ),
            "Mühazirə": t("Lecture", "Лекция", "Ders", "Vorlesung"),
            "Mühazirəsiz qruplar: %(groups)s": t(
                "Groups without lecture: %(groups)s",
                "Группы без лекции: %(groups)s",
                "Dersi olmayan gruplar: %(groups)s",
                "Gruppen ohne Vorlesung: %(groups)s",
            ),
            "Mühazirəçi": t("Lecturer", "Лектор", "Öğretim üyesi", "Dozent"),
            "Mühazirəçi seçilməyib": t(
                "No lecturer selected", "Лектор не выбран", "Öğretim üyesi seçilmemiş", "Kein Dozent gewählt"
            ),
            "Müəllim axtar…": t("Search teacher…", "Поиск преподавателя…", "Öğretmen ara…", "Lehrkraft suchen…"),
            "Müəllim əlavə et": t("Add teacher", "Добавить преподавателя", "Öğretmen ekle", "Lehrkraft hinzufügen"),
            "Patok: bir axının mühazirəsi müəllimin yükünə bir dəfə düşür və hər qrupun jurnalında görünür.": t(
                "Joint lecture: a stream's lecture counts once in the teacher's load and appears in every group's journal.",
                "Поток: лекция потока учитывается в нагрузке один раз и отображается в журнале каждой группы.",
                "Ortak ders: bir akışın dersi öğretmenin yüküne bir kez sayılır ve her grubun defterinde görünür.",
                "Gemeinsame Vorlesung: die Vorlesung eines Stroms zählt einmal zur Belastung und erscheint im Journal jeder Gruppe.",
            ),
            "Qalıq %(hours)s": t("Remaining %(hours)s", "Остаток %(hours)s", "Kalan %(hours)s", "Rest %(hours)s"),
            "Qrup qeydi tanınmadı": t(
                "Group note not recognised",
                "Запись о группе не распознана",
                "Grup notu tanınmadı",
                "Gruppenvermerk nicht erkannt",
            ),
            "Qrupsuz bölgü": t(
                "Distribution without a group", "Распределение без группы", "Grupsuz dağıtım", "Verteilung ohne Gruppe"
            ),
            "Saat": t("Hours", "Часы", "Saat (ders)", "Stunden"),
            "Saat sıfırdan böyük olmalıdır.": t(
                "Hours must be greater than zero.",
                "Часы должны быть больше нуля.",
                "Saat sıfırdan büyük olmalıdır.",
                "Die Stunden müssen größer als null sein.",
            ),
            "Sətirlər (%(n)s)": t("Rows (%(n)s)", "Строки (%(n)s)", "Satırlar (%(n)s)", "Zeilen (%(n)s)"),
            "Sətri sil": t("Remove line", "Удалить строку", "Satırı sil", "Zeile entfernen"),
            "Sətrin cəmindən çox saat bölünüb: %(groups)s": t(
                "More hours allocated than the row total: %(groups)s",
                "Распределено больше часов, чем итог строки: %(groups)s",
                "Satır toplamından fazla saat dağıtıldı: %(groups)s",
                "Mehr Stunden verteilt als die Zeilensumme: %(groups)s",
            ),
            "Tapşırıq sətirləri (%(n)s) — redaktə, silmə, saatlar": t(
                "Assignment rows (%(n)s) — edit, delete, hours",
                "Строки поручения (%(n)s) — редактирование, удаление, часы",
                "Görev satırları (%(n)s) — düzenleme, silme, saatler",
                "Auftragszeilen (%(n)s) — bearbeiten, löschen, Stunden",
            ),
            "Təyin olunmayıb": t("Not assigned", "Не назначено", "Atanmamış", "Nicht zugewiesen"),
            "bir sətir": t("one row", "одна строка", "tek satır", "eine Zeile"),
            "mühazirə %(hours)s · yükə bir dəfə": t(
                "lecture %(hours)s · counted once",
                "лекция %(hours)s · в нагрузку один раз",
                "ders %(hours)s · yüke bir kez",
                "Vorlesung %(hours)s · einmal gezählt",
            ),
            "qrup planı %(hours)s": t(
                "group plan %(hours)s", "план группы %(hours)s", "grup planı %(hours)s", "Gruppenplan %(hours)s"
            ),
            "saathesabı": t("hourly paid", "почасовая", "saat ücretli", "Stundenbasis"),
            "sətir qalığı %(hours)s": t(
                "row remaining %(hours)s", "остаток строки %(hours)s", "satır kalanı %(hours)s", "Zeilenrest %(hours)s"
            ),
            "№%(n)s": t("No. %(n)s", "№ %(n)s", "No %(n)s", "Nr. %(n)s"),
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
                    lines = []
                    if "%(" in msgid:
                        lines.append("#, javascript-format" if domain == "djangojs" else "#, python-format")
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
