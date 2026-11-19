#!/usr/bin/env python3
"""«Yük bölgüsü» aydınlıq dalğası (sahib 2026-11-19): yalnız yeni msgid-ləri əlavə edir.

Fənn kartı (addımlar, axın nişanları, vəziyyət, «saatı yoxlayın»), axın / qrup bölgüsü modalları, «Bölgü necə
işləyir?» izahı və sağ paneldəki müəllim axtarışı. Mövcud tərcümələrə toxunmur; təkrar işlətmək təhlükəsizdir.
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


TEACHER_SEARCH = t("Search teacher…", "Поиск преподавателя…", "Öğretim elemanı ara…", "Lehrkraft suchen…")
NOT_SPLIT = t("Not split by group", "Не разделено по группам", "Gruplara ayrılmamış", "Nicht nach Gruppen aufgeteilt")

ENTRIES = {
    "django": {
        "accounts.workload": {
            "Bölgü necə işləyir?": t(
                "How does the distribution work?",
                "Как работает распределение?",
                "Dağılım nasıl çalışır?",
                "Wie funktioniert die Verteilung?",
            ),
            "Mühazirə.": t("Lecture.", "Лекция.", "Ders (teorik).", "Vorlesung."),
            "Mühazirəni birlikdə dinləyən qruplar bir «axın»dır (patok). «Patok qur» / «Axınları dəyiş» ilə qrupları axınlara yığın və hər axının mühazirəçisini seçin. Bir axının saatı müəllimin yükünə 1 dəfə yazılır, jurnal isə hər qrupda açılır.": t(
                "Groups that attend the lecture together form one “stream”. Use “Create stream” / “Change streams” to put the groups into streams and choose a lecturer for each stream. A stream's hours count towards the teacher's load once, while a journal is opened for every group.",
                "Группы, которые слушают лекцию вместе, образуют один «поток». Кнопкой «Создать поток» / «Изменить потоки» соберите группы в потоки и выберите лектора для каждого потока. Часы потока засчитываются в нагрузку преподавателя один раз, а журнал открывается для каждой группы.",
                "Dersi birlikte dinleyen gruplar bir «akış» oluşturur. «Akış kur» / «Akışları değiştir» ile grupları akışlara toplayın ve her akışın öğretim üyesini seçin. Bir akışın saati öğretim elemanının yüküne 1 kez yazılır, defter ise her grupta açılır.",
                "Gruppen, die die Vorlesung gemeinsam hören, bilden einen „Strom“. Ordnen Sie die Gruppen mit „Strom bilden“ / „Ströme ändern“ den Strömen zu und wählen Sie für jeden Strom einen Dozenten. Die Stunden eines Stroms zählen einmal zur Lehrlast, das Journal wird für jede Gruppe geöffnet.",
            ),
            "Seminar və laboratoriya.": t(
                "Seminar and laboratory.", "Семинар и лабораторная.", "Seminer ve laboratuvar.", "Seminar und Labor."
            ),
            "Hər qrup ayrıca keçir. «Bölüşdür» ilə hər qrupa müəllim və saat verin; qrup Lab-1 / Lab-2 kimi alt qruplara bölünübsə, hər alt qrupa öz müəllimini seçin.": t(
                "Each group is taught separately. Use “Distribute” to give every group a teacher and hours; if a group is split into subgroups such as Lab-1 / Lab-2, choose a teacher for each subgroup.",
                "Каждая группа занимается отдельно. Кнопкой «Распределить» назначьте каждой группе преподавателя и часы; если группа разделена на подгруппы (Lab-1 / Lab-2), выберите преподавателя для каждой подгруппы.",
                "Her grup ayrı işlenir. «Dağıt» ile her gruba öğretim elemanı ve saat verin; grup Lab-1 / Lab-2 gibi alt gruplara ayrılmışsa her alt gruba kendi öğretim elemanını seçin.",
                "Jede Gruppe wird getrennt unterrichtet. Weisen Sie mit „Verteilen“ jeder Gruppe Lehrkraft und Stunden zu; ist eine Gruppe in Untergruppen (Lab-1 / Lab-2) geteilt, wählen Sie für jede Untergruppe eine Lehrkraft.",
            ),
            "Saatı və ya qrupu dəyişmək.": t(
                "Changing hours or groups.",
                "Изменение часов или групп.",
                "Saati veya grubu değiştirmek.",
                "Stunden oder Gruppen ändern.",
            ),
            "Kartın altındakı «Tapşırıq sətirləri» → «Redaktə». Eyni fənnin digər qruplarından fərqlənən saat kartda «saatı yoxlayın» nişanı ilə göstərilir.": t(
                "“Assignment rows” at the bottom of the card → “Edit”. Hours that differ from the other groups of the same subject are marked “check the hours” on the card.",
                "«Строки задания» внизу карточки → «Редактировать». Часы, отличающиеся от других групп того же предмета, отмечаются на карточке значком «проверьте часы».",
                "Kartın altındaki «Görev satırları» → «Düzenle». Aynı dersin diğer gruplarından farklı olan saat kartta «saati kontrol edin» işaretiyle gösterilir.",
                "„Auftragszeilen“ unten auf der Karte → „Bearbeiten“. Stunden, die von den anderen Gruppen desselben Fachs abweichen, werden auf der Karte mit „Stunden prüfen“ markiert.",
            ),
            "tam bölünüb": t("fully distributed", "распределено полностью", "tamamı dağıtıldı", "vollständig verteilt"),
            "vakant və ya bölünməyib": t(
                "vacant or not distributed",
                "вакансия или не распределено",
                "boş veya dağıtılmamış",
                "unbesetzt oder nicht verteilt",
            ),
            "müəllim təyin olunmayıb": t(
                "no teacher assigned",
                "преподаватель не назначен",
                "öğretim elemanı atanmamış",
                "keine Lehrkraft zugewiesen",
            ),
            "Müəllim axtar…": TEACHER_SEARCH,
            "Uyğun müəllim tapılmadı.": t(
                "No matching teacher found.",
                "Подходящий преподаватель не найден.",
                "Uygun öğretim elemanı bulunamadı.",
                "Keine passende Lehrkraft gefunden.",
            ),
            "Axın nədir?": t("What is a stream?", "Что такое поток?", "Akış nedir?", "Was ist ein Strom?"),
            "Axın (patok) — mühazirəni eyni vaxtda BİRLİKDƏ dinləyən qruplardır. Ayrıca keçən qrup öz axınında tək qalır.": t(
                "A stream is a set of groups that attend the lecture TOGETHER at the same time. A group taught separately stays alone in its own stream.",
                "Поток — это группы, которые слушают лекцию ВМЕСТЕ в одно время. Группа, занимающаяся отдельно, остаётся одна в своём потоке.",
                "Akış, dersi aynı anda BİRLİKTE dinleyen gruplardır. Ayrı işlenen grup kendi akışında tek kalır.",
                "Ein Strom sind Gruppen, die die Vorlesung zur selben Zeit GEMEINSAM hören. Eine getrennt unterrichtete Gruppe bleibt allein in ihrem Strom.",
            ),
            "Bir axının mühazirə saatı müəllimin yükünə BİR dəfə yazılır; jurnal isə hər qrupda ayrıca açılır və mühazirə hər birində görünür.": t(
                "A stream's lecture hours count towards the teacher's load ONCE; a separate journal is opened for every group and the lecture appears in each of them.",
                "Лекционные часы потока засчитываются в нагрузку преподавателя ОДИН раз; журнал открывается отдельно для каждой группы, и лекция видна в каждом из них.",
                "Bir akışın ders saati öğretim elemanının yüküne BİR kez yazılır; defter ise her grupta ayrı açılır ve ders her birinde görünür.",
                "Die Vorlesungsstunden eines Stroms zählen EINMAL zur Lehrlast; das Journal wird für jede Gruppe separat geöffnet und die Vorlesung erscheint in jedem.",
            ),
            "Bir tapşırıq sətrinin qrupları birlikdə hərəkət edir — onları ayırmaq üçün əvvəlcə sətri «Redaktə» ilə bölün.": t(
                "The groups of one assignment row move together — to separate them, first split the row with “Edit”.",
                "Группы одной строки задания перемещаются вместе — чтобы разделить их, сначала разбейте строку через «Редактировать».",
                "Bir görev satırının grupları birlikte hareket eder — ayırmak için önce satırı «Düzenle» ile bölün.",
                "Die Gruppen einer Auftragszeile bewegen sich gemeinsam — um sie zu trennen, teilen Sie die Zeile zuerst über „Bearbeiten“.",
            ),
            "«Alt qrup» sütunu boşdursa qrup hələ Lab-1 / Lab-2-yə bölünməyib. Alt qruplar «Lab qrupları» bölməsində yaradılır; sonra burada hər alt qrupa öz müəllimini seçin.": t(
                "If the “Subgroup” column is empty, the group has not been split into Lab-1 / Lab-2 yet. Subgroups are created in the “Lab groups” section; then choose a teacher for each subgroup here.",
                "Если столбец «Подгруппа» пуст, группа ещё не разделена на Lab-1 / Lab-2. Подгруппы создаются в разделе «Лабораторные группы»; затем выберите здесь преподавателя для каждой подгруппы.",
                "«Alt grup» sütunu boşsa grup henüz Lab-1 / Lab-2 olarak ayrılmamıştır. Alt gruplar «Laboratuvar grupları» bölümünde oluşturulur; ardından burada her alt gruba öğretim elemanını seçin.",
                "Ist die Spalte „Untergruppe“ leer, wurde die Gruppe noch nicht in Lab-1 / Lab-2 geteilt. Untergruppen werden im Bereich „Laborgruppen“ angelegt; wählen Sie danach hier für jede Untergruppe eine Lehrkraft.",
            ),
            "1. Hər qrupu bir axına salın": t(
                "1. Put each group into a stream",
                "1. Отнесите каждую группу к потоку",
                "1. Her grubu bir akışa yerleştirin",
                "1. Ordnen Sie jede Gruppe einem Strom zu",
            ),
            "Hamısı bir axında": t(
                "All in one stream", "Все в одном потоке", "Hepsi tek akışta", "Alle in einem Strom"
            ),
            "Hər qrup ayrıca": t(
                "Each group separately", "Каждая группа отдельно", "Her grup ayrı", "Jede Gruppe getrennt"
            ),
            "2. Hər axının mühazirəçisini seçin": t(
                "2. Choose a lecturer for each stream",
                "2. Выберите лектора для каждого потока",
                "2. Her akışın öğretim üyesini seçin",
                "2. Wählen Sie für jeden Strom einen Dozenten",
            ),
            "Hər qrupun altında müəllimi və saatı seçin. Qrup alt qruplara (Lab-1 / Lab-2) bölünübsə «Müəllim əlavə et» ilə hər alt qrupa ayrıca müəllim verin. Bölünən saat qrupun planından çox ola bilməz — «bölünməyib» 0 olanda qrup hazırdır.": t(
                "Choose the teacher and hours under each group. If a group is split into subgroups (Lab-1 / Lab-2), use “Add teacher” to give each subgroup its own teacher. Distributed hours cannot exceed the group's plan — the group is done when “not distributed” is 0.",
                "Под каждой группой выберите преподавателя и часы. Если группа разделена на подгруппы (Lab-1 / Lab-2), кнопкой «Добавить преподавателя» назначьте преподавателя каждой подгруппе. Распределённые часы не могут превышать план группы — группа готова, когда «не распределено» равно 0.",
                "Her grubun altında öğretim elemanını ve saati seçin. Grup alt gruplara (Lab-1 / Lab-2) ayrılmışsa «Öğretim elemanı ekle» ile her alt gruba ayrı öğretim elemanı verin. Dağıtılan saat grubun planını aşamaz — «dağıtılmamış» 0 olduğunda grup hazırdır.",
                "Wählen Sie unter jeder Gruppe Lehrkraft und Stunden. Ist eine Gruppe in Untergruppen (Lab-1 / Lab-2) geteilt, geben Sie mit „Lehrkraft hinzufügen“ jeder Untergruppe eine eigene Lehrkraft. Die verteilten Stunden dürfen den Plan der Gruppe nicht überschreiten — die Gruppe ist fertig, wenn „nicht verteilt“ 0 ist.",
            ),
        },
    },
    "djangojs": {
        "": {
            "Eyni fənnin digər qruplarında saat fərqlidir. Səhvdirsə «Tapşırıq sətirləri» → «Redaktə» ilə düzəldin.": t(
                "The hours differ from the other groups of the same subject. If this is a mistake, fix it via “Assignment rows” → “Edit”.",
                "Часы отличаются от других групп того же предмета. Если это ошибка, исправьте через «Строки задания» → «Редактировать».",
                "Saat, aynı dersin diğer gruplarından farklı. Hatalıysa «Görev satırları» → «Düzenle» ile düzeltin.",
                "Die Stunden weichen von den anderen Gruppen desselben Fachs ab. Falls das ein Fehler ist, korrigieren Sie ihn über „Auftragszeilen“ → „Bearbeiten“.",
            ),
            "digər qruplarda %(hours)s — saatı yoxlayın": t(
                "other groups have %(hours)s — check the hours",
                "в других группах %(hours)s — проверьте часы",
                "diğer gruplarda %(hours)s — saati kontrol edin",
                "andere Gruppen haben %(hours)s — Stunden prüfen",
            ),
            "Bu sətrin qrupları mühazirəni bir neçə axında keçir, amma sətir qruplara ayrılmayıb.": t(
                "The groups of this row attend the lecture in several streams, but the row is not split by group.",
                "Группы этой строки слушают лекцию в нескольких потоках, но строка не разделена по группам.",
                "Bu satırın grupları dersi birkaç akışta işliyor, ancak satır gruplara ayrılmamış.",
                "Die Gruppen dieser Zeile hören die Vorlesung in mehreren Strömen, die Zeile ist aber nicht nach Gruppen aufgeteilt.",
            ),
            "%(n)s axın bir sətirdə": t(
                "%(n)s streams in one row",
                "%(n)s потока в одной строке",
                "tek satırda %(n)s akış",
                "%(n)s Ströme in einer Zeile",
            ),
            "Axının mühazirəçisi başqa kartdadır": t(
                "The stream's lecturer is on another card",
                "Лектор потока находится в другой карточке",
                "Akışın öğretim üyesi başka kartta",
                "Der Dozent des Stroms steht auf einer anderen Karte",
            ),
            "Axına bağlanmayıb — mühazirə heç kimin yükünə düşmür": t(
                "Not linked to a stream — the lecture counts towards nobody's load",
                "Не привязано к потоку — лекция не засчитывается ни в чью нагрузку",
                "Akışa bağlanmamış — ders kimsenin yüküne yazılmıyor",
                "Keinem Strom zugeordnet — die Vorlesung zählt zu niemandes Lehrlast",
            ),
            "Bu qruplar mühazirəni birlikdə dinləyir: saat müəllimin yükünə 1 dəfə yazılır, jurnal hər qrupda açılır.": t(
                "These groups attend the lecture together: the hours count towards the teacher's load once, and a journal is opened for every group.",
                "Эти группы слушают лекцию вместе: часы засчитываются в нагрузку преподавателя один раз, журнал открывается для каждой группы.",
                "Bu gruplar dersi birlikte dinliyor: saat öğretim elemanının yüküne 1 kez yazılır, defter her grupta açılır.",
                "Diese Gruppen hören die Vorlesung gemeinsam: Die Stunden zählen einmal zur Lehrlast, das Journal wird für jede Gruppe geöffnet.",
            ),
            "%(n)s qrup birlikdə": t(
                "%(n)s groups together", "%(n)s группы вместе", "%(n)s grup birlikte", "%(n)s Gruppen gemeinsam"
            ),
            "tək qrup": t("single group", "одна группа", "tek grup", "einzelne Gruppe"),
            "%(n)s axın · müəllim yükünə cəmi %(hours)s": t(
                "%(n)s streams · %(hours)s towards teacher load in total",
                "%(n)s потока · всего в нагрузку %(hours)s",
                "%(n)s akış · yüke toplam %(hours)s",
                "%(n)s Ströme · insgesamt %(hours)s Lehrlast",
            ),
            "Hansı qrupların mühazirəni birlikdə dinlədiyini (patok) və mühazirəçini seçin.": t(
                "Choose which groups attend the lecture together and who the lecturer is.",
                "Выберите, какие группы слушают лекцию вместе, и лектора.",
                "Hangi grupların dersi birlikte dinlediğini ve öğretim üyesini seçin.",
                "Wählen Sie, welche Gruppen die Vorlesung gemeinsam hören, und den Dozenten.",
            ),
            "Patok qur": t("Create stream", "Создать поток", "Akış kur", "Strom bilden"),
            "%(n)s qrup ayrıca keçir · müəllim yükünə cəmi %(hours)s": t(
                "%(n)s groups taught separately · %(hours)s towards teacher load in total",
                "%(n)s группы отдельно · всего в нагрузку %(hours)s",
                "%(n)s grup ayrı işliyor · yüke toplam %(hours)s",
                "%(n)s Gruppen getrennt · insgesamt %(hours)s Lehrlast",
            ),
            "Mühazirəçi seç": t("Choose lecturer", "Выбрать лектора", "Öğretim üyesi seç", "Dozenten wählen"),
            "Axın (patok) — mühazirəni birlikdə dinləyən qruplar. Bir axının saatı müəllimin yükünə 1 dəfə yazılır, jurnal isə hər qrupda açılır.": t(
                "A stream is a set of groups that attend the lecture together. A stream's hours count towards the teacher's load once, while a journal is opened for every group.",
                "Поток — группы, которые слушают лекцию вместе. Часы потока засчитываются в нагрузку преподавателя один раз, а журнал открывается для каждой группы.",
                "Akış — dersi birlikte dinleyen gruplar. Bir akışın saati öğretim elemanının yüküne 1 kez yazılır, defter ise her grupta açılır.",
                "Strom — Gruppen, die die Vorlesung gemeinsam hören. Die Stunden eines Stroms zählen einmal zur Lehrlast, das Journal wird für jede Gruppe geöffnet.",
            ),
            "Bölünməyib: %(hours)s": t(
                "Not distributed: %(hours)s",
                "Не распределено: %(hours)s",
                "Dağıtılmamış: %(hours)s",
                "Nicht verteilt: %(hours)s",
            ),
            "%(n)s qrup · %(hours)s": t(
                "%(n)s groups · %(hours)s",
                "%(n)s групп · %(hours)s",
                "%(n)s grup · %(hours)s",
                "%(n)s Gruppen · %(hours)s",
            ),
            "Bu qruplar məşğələni birlikdə keçir — saat müəllimin yükünə 1 dəfə yazılır.": t(
                "These groups have the class together — the hours count towards the teacher's load once.",
                "Эти группы занимаются вместе — часы засчитываются в нагрузку преподавателя один раз.",
                "Bu gruplar dersi birlikte işliyor — saat öğretim elemanının yüküne 1 kez yazılır.",
                "Diese Gruppen haben den Unterricht gemeinsam — die Stunden zählen einmal zur Lehrlast.",
            ),
            "Qruplar birlikdə keçir": t(
                "Groups taught together", "Группы занимаются вместе", "Gruplar birlikte işliyor", "Gruppen gemeinsam"
            ),
            "Saat bütün sətrə yazılıb. Hər qrupa ayrıca müəllim vermək üçün «Bölüşdür» düyməsinə basın.": t(
                "The hours are recorded for the whole row. To give each group its own teacher, press “Distribute”.",
                "Часы записаны на всю строку. Чтобы назначить преподавателя каждой группе отдельно, нажмите «Распределить».",
                "Saat tüm satıra yazılmış. Her gruba ayrı öğretim elemanı vermek için «Dağıt» düğmesine basın.",
                "Die Stunden sind für die ganze Zeile eingetragen. Um jeder Gruppe eine eigene Lehrkraft zu geben, klicken Sie auf „Verteilen“.",
            ),
            "Qruplara ayrılmayıb": NOT_SPLIT,
            "Ümumi bölgüyə daxildir": t(
                "Included in the shared assignment",
                "Входит в общее распределение",
                "Ortak dağılıma dahil",
                "In der gemeinsamen Zuweisung enthalten",
            ),
            "Birgə keçilir": t(
                "Taught jointly", "Проводится совместно", "Birlikte işleniyor", "Gemeinsam unterrichtet"
            ),
            "Müəllim təyin olunmayıb": t(
                "No teacher assigned",
                "Преподаватель не назначен",
                "Öğretim elemanı atanmamış",
                "Keine Lehrkraft zugewiesen",
            ),
            "cəmi %(total)s · bölünüb %(assigned)s": t(
                "%(total)s in total · %(assigned)s distributed",
                "всего %(total)s · распределено %(assigned)s",
                "toplam %(total)s · dağıtılan %(assigned)s",
                "insgesamt %(total)s · verteilt %(assigned)s",
            ),
            "Hər qrupa müəllim və saat verin; qrupu Lab-1 / Lab-2 kimi alt qruplara da bölə bilərsiniz.": t(
                "Give each group a teacher and hours; you can also split a group into subgroups such as Lab-1 / Lab-2.",
                "Назначьте каждой группе преподавателя и часы; группу можно также разделить на подгруппы (Lab-1 / Lab-2).",
                "Her gruba öğretim elemanı ve saat verin; grubu Lab-1 / Lab-2 gibi alt gruplara da bölebilirsiniz.",
                "Weisen Sie jeder Gruppe Lehrkraft und Stunden zu; eine Gruppe kann auch in Untergruppen (Lab-1 / Lab-2) geteilt werden.",
            ),
            "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
            "Plan saatı": t("Planned hours", "Часы по плану", "Plan saati", "Planstunden"),
            "Müəllim və saat": t(
                "Teacher and hours", "Преподаватель и часы", "Öğretim elemanı ve saat", "Lehrkraft und Stunden"
            ),
            "Saat bölünüb, amma müəllim hələ təyin edilməyib (vakant).": t(
                "The hours are distributed, but no teacher is assigned yet (vacant).",
                "Часы распределены, но преподаватель ещё не назначен (вакансия).",
                "Saat dağıtılmış, ancak öğretim elemanı henüz atanmamış (boş).",
                "Die Stunden sind verteilt, aber noch keiner Lehrkraft zugewiesen (unbesetzt).",
            ),
            "Vakant: %(hours)s": t(
                "Vacant: %(hours)s", "Вакансия: %(hours)s", "Boş: %(hours)s", "Unbesetzt: %(hours)s"
            ),
            "Tam bölünüb": t("Fully distributed", "Распределено полностью", "Tamamı dağıtıldı", "Vollständig verteilt"),
            "Natamam": t("Incomplete", "Не завершено", "Eksik", "Unvollständig"),
            "Bu fəndə heç bir axına bağlanmamış mühazirə sətri var — «Axınları dəyiş» ilə qrupları axına salın.": t(
                "This subject has a lecture row that is not linked to any stream — use “Change streams” to put the groups into a stream.",
                "В этом предмете есть лекционная строка, не привязанная ни к одному потоку — кнопкой «Изменить потоки» отнесите группы к потоку.",
                "Bu derste hiçbir akışa bağlanmamış ders satırı var — «Akışları değiştir» ile grupları akışa yerleştirin.",
                "In diesem Fach gibt es eine Vorlesungszeile ohne Strom — ordnen Sie die Gruppen mit „Ströme ändern“ einem Strom zu.",
            ),
            "birlikdə dinləyir": t("attend together", "слушают вместе", "birlikte dinliyor", "hören gemeinsam"),
            "Yekun: %(n)s axın · müəllimlərin yükünə cəmi %(load)s (axınlar birləşdirilməsəydi %(separate)s olardı).": t(
                "Result: %(n)s streams · %(load)s towards teacher load in total (without merging the streams it would be %(separate)s).",
                "Итог: %(n)s потока · всего в нагрузку преподавателей %(load)s (без объединения потоков было бы %(separate)s).",
                "Sonuç: %(n)s akış · öğretim elemanlarının yüküne toplam %(load)s (akışlar birleştirilmeseydi %(separate)s olurdu).",
                "Ergebnis: %(n)s Ströme · insgesamt %(load)s Lehrlast (ohne Zusammenlegung wären es %(separate)s).",
            ),
            "Yekun: %(n)s axın · müəllimlərin yükünə cəmi %(load)s.": t(
                "Result: %(n)s streams · %(load)s towards teacher load in total.",
                "Итог: %(n)s потока · всего в нагрузку преподавателей %(load)s.",
                "Sonuç: %(n)s akış · öğretim elemanlarının yüküne toplam %(load)s.",
                "Ergebnis: %(n)s Ströme · insgesamt %(load)s Lehrlast.",
            ),
            "artıq bölünüb: %(hours)s": t(
                "over-distributed: %(hours)s",
                "распределено лишнее: %(hours)s",
                "fazla dağıtılmış: %(hours)s",
                "zu viel verteilt: %(hours)s",
            ),
            "bölünməyib: %(hours)s": t(
                "not distributed: %(hours)s",
                "не распределено: %(hours)s",
                "dağıtılmamış: %(hours)s",
                "nicht verteilt: %(hours)s",
            ),
            "Bu saat qruplara ayrılmadan bütün sətrə yazılıb. Hər qrupa ayrıca müəllim vermək üçün buradakı müəllimi silin və yuxarıdakı qrupların altında «Müəllim əlavə et» düyməsinə basın.": t(
                "These hours are recorded for the whole row without splitting by group. To give each group its own teacher, remove the teacher here and press “Add teacher” under the groups above.",
                "Эти часы записаны на всю строку без разделения по группам. Чтобы назначить преподавателя каждой группе, удалите преподавателя здесь и нажмите «Добавить преподавателя» под группами выше.",
                "Bu saat gruplara ayrılmadan tüm satıra yazılmış. Her gruba ayrı öğretim elemanı vermek için buradaki öğretim elemanını silin ve yukarıdaki grupların altında «Öğretim elemanı ekle» düğmesine basın.",
                "Diese Stunden sind ohne Aufteilung nach Gruppen für die ganze Zeile eingetragen. Um jeder Gruppe eine eigene Lehrkraft zu geben, entfernen Sie die Lehrkraft hier und klicken Sie unter den Gruppen oben auf „Lehrkraft hinzufügen“.",
            ),
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
