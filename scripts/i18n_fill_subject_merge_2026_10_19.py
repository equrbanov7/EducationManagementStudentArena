#!/usr/bin/env python3
"""EMSArena i18n — «Fənləri birləşdir» (dublikat fənlərin birləşdirilməsi) 2026-10-19.

Əlavə olunan mətnlər (yalnız ``django`` domeni):
  * `registrar.subject_merge` — önizləmə/toqquşma/xəbərdarlıq mesajları (`subject_merge*.py`),
    cədvəl adları (`subject_merge_inventory.py`), HTTP xətaları (`subject_merge_views.py`),
    dialoq (`teaching_office/_subject_merge_dialog.html`), kataloq düymələri
    (`_subject_catalog.html`, `teaching_office/_subject_actions.html`);
  * `accounts.catalog` — dublikat lentinin yeni mətnləri (`catalog_sections.py`).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan
blokları əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra
`compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_subject_merge_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MERGE = "registrar.subject_merge"
CATALOG = "accounts.catalog"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


# ctx → msgid → {lang: msgstr}. az msgstr = msgid.
ENTRIES = {
    MERGE: {
        # ── xətalar / yoxlamalar ──
        "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": t(
            "The reason must be at least 20 characters — a short note is not enough for the audit.",
            "Причина должна содержать не менее 20 символов — короткой заметки для аудита недостаточно.",
            "Gerekçe en az 20 karakter olmalıdır — kısa bir not denetim için yeterli değildir.",
            "Die Begründung muss mindestens 20 Zeichen lang sein — eine kurze Notiz reicht für das Audit nicht.",
        ),
        "Saxlanılacaq fənni seçin.": t(
            "Choose the subject to keep.",
            "Выберите сохраняемую дисциплину.",
            "Korunacak dersi seçin.",
            "Wählen Sie das beizubehaltende Fach.",
        ),
        "Ən azı bir birləşdiriləcək fənn seçin.": t(
            "Choose at least one subject to merge.",
            "Выберите хотя бы одну объединяемую дисциплину.",
            "Birleştirilecek en az bir ders seçin.",
            "Wählen Sie mindestens ein zusammenzuführendes Fach.",
        ),
        "Fənn tapılmadı.": t(
            "Subject not found.", "Дисциплина не найдена.", "Ders bulunamadı.", "Fach nicht gefunden."
        ),
        "Saxlanılacaq fənn birləşdiriləcəklər siyahısında ola bilməz.": t(
            "The subject to keep cannot also be in the list of subjects to merge.",
            "Сохраняемая дисциплина не может быть в списке объединяемых.",
            "Korunacak ders, birleştirilecekler listesinde olamaz.",
            "Das beizubehaltende Fach darf nicht in der Liste der zusammenzuführenden Fächer stehen.",
        ),
        "Saxlanılacaq fənn arxivdədir — əvvəlcə onu arxivdən qaytarın.": t(
            "The subject to keep is archived — restore it from the archive first.",
            "Сохраняемая дисциплина в архиве — сначала восстановите её из архива.",
            "Korunacak ders arşivde — önce arşivden geri alın.",
            "Das beizubehaltende Fach ist archiviert — stellen Sie es zuerst aus dem Archiv wieder her.",
        ),
        "Bir dəfəyə ən çox %(n)s fənn birləşdirilə bilər.": t(
            "At most %(n)s subjects can be merged at once.",
            "За один раз можно объединить не более %(n)s дисциплин.",
            "Tek seferde en fazla %(n)s ders birleştirilebilir.",
            "Es können höchstens %(n)s Fächer auf einmal zusammengeführt werden.",
        ),
        "Məlumat önizləmədən sonra dəyişib — yenidən önizləyin.": t(
            "The data changed after the preview — preview again.",
            "Данные изменились после предпросмотра — выполните предпросмотр заново.",
            "Veriler önizlemeden sonra değişti — yeniden önizleyin.",
            "Die Daten haben sich nach der Vorschau geändert — erneut in der Vorschau prüfen.",
        ),
        "Əvvəlcə önizləməyə baxın.": t(
            "Check the preview first.",
            "Сначала посмотрите предпросмотр.",
            "Önce önizlemeye bakın.",
            "Prüfen Sie zuerst die Vorschau.",
        ),
        "Toqquşmalar həll edilməyib — birləşdirmə bloklanır.": t(
            "Conflicts are not resolved — the merge is blocked.",
            "Конфликты не устранены — объединение заблокировано.",
            "Çakışmalar giderilmedi — birleştirme engellendi.",
            "Konflikte sind nicht gelöst — die Zusammenführung ist gesperrt.",
        ),
        "Aktiv təşkilat konteksti yoxdur.": t(
            "No active organisation context.",
            "Нет активного контекста организации.",
            "Etkin kurum bağlamı yok.",
            "Kein aktiver Organisationskontext.",
        ),
        "Fənləri birləşdirmək səlahiyyətiniz yoxdur.": t(
            "You do not have permission to merge subjects.",
            "У вас нет прав на объединение дисциплин.",
            "Dersleri birleştirme yetkiniz yok.",
            "Sie sind nicht berechtigt, Fächer zusammenzuführen.",
        ),
        "Səhifə tapılmadı.": t("Page not found.", "Страница не найдена.", "Sayfa bulunamadı.", "Seite nicht gefunden."),
        "Birləşdirildi: %(sources)s → %(target)s.": t(
            "Merged: %(sources)s → %(target)s.",
            "Объединено: %(sources)s → %(target)s.",
            "Birleştirildi: %(sources)s → %(target)s.",
            "Zusammengeführt: %(sources)s → %(target)s.",
        ),
        # ── xəbərdarlıq / qeyd ──
        "Fənn növləri fərqlidir — saxlanılan fənnin növü qalır.": t(
            "The subject types differ — the type of the kept subject remains.",
            "Типы дисциплин различаются — остаётся тип сохраняемой дисциплины.",
            "Ders türleri farklı — korunan dersin türü kalır.",
            "Die Fachtypen unterscheiden sich — der Typ des beibehaltenen Fachs bleibt.",
        ),
        "Adlar (boşluq/registr nəzərə alınmadan) fərqlidir — bunun həqiqətən eyni fənn olduğunu yoxlayın.": t(
            "The names differ (ignoring spaces/case) — check that this really is the same subject.",
            "Названия различаются (без учёта пробелов/регистра) — убедитесь, что это действительно одна дисциплина.",
            "Adlar (boşluk/büyük-küçük harf hariç) farklı — bunun gerçekten aynı ders olduğunu kontrol edin.",
            "Die Namen unterscheiden sich (ohne Leerzeichen/Groß-/Kleinschreibung) — prüfen Sie, ob es "
            "wirklich dasselbe Fach ist.",
        ),
        "Birləşdiriləcək fənlərdən biri artıq arxivdədir — istinadları yenə köçürüləcək.": t(
            "One of the subjects to merge is already archived — its references will still be moved.",
            "Одна из объединяемых дисциплин уже в архиве — её ссылки всё равно будут перенесены.",
            "Birleştirilecek derslerden biri zaten arşivde — bağlantıları yine de taşınacak.",
            "Eines der zusammenzuführenden Fächer ist bereits archiviert — seine Verweise werden trotzdem "
            "übertragen.",
        ),
        "Kredit fərqlidir: %(list)s. Fərqli kreditli fənn üzrə yekun qiymət yoxdur — birləşmədən sonra saxlanılan "
        "fənnin krediti (%(ects)s ECTS) işlənir; plan sətirlərindəki kredit dəyişmir.": t(
            "Credits differ: %(list)s. There are no final grades in the subject with different credits — after the "
            "merge the kept subject's credits (%(ects)s ECTS) apply; credits in plan rows do not change.",
            "Кредиты различаются: %(list)s. По дисциплине с другим кредитом нет итоговых оценок — после объединения "
            "действует кредит сохраняемой дисциплины (%(ects)s ECTS); кредиты в строках планов не меняются.",
            "Krediler farklı: %(list)s. Farklı kredili derste final notu yok — birleştirmeden sonra korunan dersin "
            "kredisi (%(ects)s AKTS) geçerli olur; plan satırlarındaki krediler değişmez.",
            "Die Leistungspunkte unterscheiden sich: %(list)s. Im Fach mit abweichenden Punkten gibt es keine "
            "Endnoten — nach der Zusammenführung gelten die Punkte des beibehaltenen Fachs (%(ects)s ECTS); die "
            "Punkte in den Planzeilen ändern sich nicht.",
        ),
        "Kredit fərqi: %(source)s — %(source_ects)s ECTS, saxlanılan %(target)s — %(target_ects)s ECTS. "
        "%(source)s üzrə %(n)s tələbənin yekun qiyməti var — birləşmə onların keçmiş transkriptində krediti və "
        "ÜOMG-ni dəyişərdi. Əvvəlcə ECTS-i uyğunlaşdırın və ya hər iki kartı saxlayın.": t(
            "Credit mismatch: %(source)s — %(source_ects)s ECTS, kept %(target)s — %(target_ects)s ECTS. "
            "%(n)s students have final grades in %(source)s — the merge would change the credits and GPA on their "
            "past transcripts. Align the ECTS first or keep both cards.",
            "Расхождение кредитов: %(source)s — %(source_ects)s ECTS, сохраняемая %(target)s — %(target_ects)s ECTS. "
            "По %(source)s итоговые оценки есть у %(n)s студентов — объединение изменило бы кредиты и GPA в их "
            "прошлых транскриптах. Сначала согласуйте ECTS или сохраните обе карточки.",
            "Kredi uyuşmazlığı: %(source)s — %(source_ects)s AKTS, korunan %(target)s — %(target_ects)s AKTS. "
            "%(source)s dersinde %(n)s öğrencinin final notu var — birleştirme geçmiş transkriptlerindeki krediyi ve "
            "GNO'yu değiştirirdi. Önce AKTS'yi eşitleyin veya iki kartı da koruyun.",
            "Abweichende Leistungspunkte: %(source)s — %(source_ects)s ECTS, beibehalten %(target)s — %(target_ects)s "
            "ECTS. %(n)s Studierende haben in %(source)s eine Endnote — die Zusammenführung würde Punkte und "
            "Notendurchschnitt in ihren bisherigen Transkripten ändern. Gleichen Sie zuerst die ECTS an oder "
            "behalten Sie beide Karten.",
        ),
        "Birləşmə DB qaydasını pozur — heç nə yazılmadı.": t(
            "The merge violates a database rule — nothing was written.",
            "Объединение нарушает правило базы данных — ничего не записано.",
            "Birleştirme bir veritabanı kuralını ihlal ediyor — hiçbir şey yazılmadı.",
            "Die Zusammenführung verletzt eine Datenbankregel — es wurde nichts geschrieben.",
        ),
        "%(n)s təsdiqlənmiş və ya baxışdakı planın sətrində fənn kartı dəyişəcək — bu, məzmun deyil, identiklik "
        "düzəlişidir (kredit/saat/semestr dəyişmir) və audit-ə yazılır.": t(
            "The subject card will change in rows of %(n)s approved or in-review plans — this is an identity fix, "
            "not a content change (credits/hours/semester stay the same), and it is recorded in the audit.",
            "В строках %(n)s утверждённых или находящихся на рассмотрении планов изменится карточка дисциплины — это "
            "исправление идентичности, а не содержания (кредиты/часы/семестр не меняются), оно записывается в аудит.",
            "%(n)s onaylı veya incelemedeki planın satırlarında ders kartı değişecek — bu içerik değil, kimlik "
            "düzeltmesidir (kredi/saat/dönem değişmez) ve denetime yazılır.",
            "In den Zeilen von %(n)s genehmigten oder in Prüfung befindlichen Plänen ändert sich die Fachkarte — "
            "das ist eine Identitätskorrektur, keine inhaltliche Änderung (Punkte/Stunden/Semester bleiben gleich), "
            "und sie wird im Audit protokolliert.",
        ),
        "%(n)s açılışın qeydiyyatı var — açılışlar qiymət və davamiyyətləri ilə birlikdə köçür.": t(
            "%(n)s offerings have enrolments — the offerings move together with their grades and attendance.",
            "В %(n)s потоках есть записи студентов — потоки переносятся вместе с оценками и посещаемостью.",
            "%(n)s ders açılışında kayıt var — açılışlar notları ve devamlarıyla birlikte taşınır.",
            "%(n)s Lehrveranstaltungen haben Einschreibungen — sie werden mit Noten und Anwesenheit übertragen.",
        ),
        "%(n)s imtahan qrupunda hər iki fənn var — təkrar əlaqə çıxarılacaq.": t(
            "%(n)s exam groups contain both subjects — the duplicate link will be removed.",
            "В %(n)s экзаменационных группах есть обе дисциплины — повторная связь будет удалена.",
            "%(n)s sınav grubunda her iki ders var — yinelenen bağlantı kaldırılacak.",
            "%(n)s Prüfungsgruppen enthalten beide Fächer — die doppelte Verknüpfung wird entfernt.",
        ),
        "%(n)s imtahan şansı qeydi dəyişməz tarixçədir — arxivlənmiş fənndə qalır.": t(
            "%(n)s exam chance records are immutable history — they stay on the archived subject.",
            "%(n)s записей о дополнительной попытке — неизменяемая история, они остаются у архивной дисциплины.",
            "%(n)s sınav hakkı kaydı değiştirilemez geçmiştir — arşivlenen derste kalır.",
            "%(n)s Einträge zu Prüfungsversuchen sind unveränderliche Historie — sie bleiben beim archivierten Fach.",
        ),
        # ── toqquşmalar ──
        "Dövrsüz": t("No period", "Без периода", "Dönemsiz", "Ohne Zeitraum"),
        "Qrupsuz": t("No group", "Без группы", "Grupsuz", "Ohne Gruppe"),
        "%(period)s: hər iki fənn üzrə qrupsuz açılış var — birləşmədən sonra ikisi qalır.": t(
            "%(period)s: both subjects have an offering without a group — both remain after the merge.",
            "%(period)s: у обеих дисциплин есть поток без группы — после объединения останутся оба.",
            "%(period)s: her iki dersin grupsuz açılışı var — birleştirmeden sonra ikisi de kalır.",
            "%(period)s: Beide Fächer haben eine Lehrveranstaltung ohne Gruppe — nach der Zusammenführung bleiben "
            "beide bestehen.",
        ),
        "%(period)s · %(group)s: hər iki fənn üzrə açılış var — əvvəlcə birini ləğv edin.": t(
            "%(period)s · %(group)s: both subjects have an offering — cancel one of them first.",
            "%(period)s · %(group)s: есть потоки по обеим дисциплинам — сначала отмените один из них.",
            "%(period)s · %(group)s: her iki ders için açılış var — önce birini iptal edin.",
            "%(period)s · %(group)s: Für beide Fächer gibt es eine Lehrveranstaltung — heben Sie zuerst eine auf.",
        ),
        "Plan «%(plan)s» (%(status)s) · %(semester)s-ci semestr: hər iki fənn sətri var — bu statusda plan dəyişmir; "
        "əvvəlcə yeni versiyada birini çıxarın.": t(
            "Plan «%(plan)s» (%(status)s) · semester %(semester)s: both subjects have a row — the plan cannot change "
            "in this status; remove one of them in a new version first.",
            "План «%(plan)s» (%(status)s) · семестр %(semester)s: есть строки обеих дисциплин — в этом статусе план "
            "не меняется; сначала уберите одну из них в новой версии.",
            "Plan «%(plan)s» (%(status)s) · %(semester)s. dönem: her iki dersin satırı var — bu durumda plan "
            "değişmez; önce yeni sürümde birini çıkarın.",
            "Plan «%(plan)s» (%(status)s) · Semester %(semester)s: Beide Fächer haben eine Zeile — in diesem Status "
            "ändert sich der Plan nicht; entfernen Sie zuerst eine davon in einer neuen Version.",
        ),
        "Plan «%(plan)s» (%(status)s) · %(semester)s-ci semestr: hər iki fənn sətri var — saxlanılan fənnin sətri "
        "qalır, digəri plandan çıxarılır.": t(
            "Plan «%(plan)s» (%(status)s) · semester %(semester)s: both subjects have a row — the kept subject's "
            "row stays, the other is removed from the plan.",
            "План «%(plan)s» (%(status)s) · семестр %(semester)s: есть строки обеих дисциплин — строка сохраняемой "
            "дисциплины остаётся, другая удаляется из плана.",
            "Plan «%(plan)s» (%(status)s) · %(semester)s. dönem: her iki dersin satırı var — korunan dersin satırı "
            "kalır, diğeri plandan çıkarılır.",
            "Plan «%(plan)s» (%(status)s) · Semester %(semester)s: Beide Fächer haben eine Zeile — die Zeile des "
            "beibehaltenen Fachs bleibt, die andere wird aus dem Plan entfernt.",
        ),
        "Plan «%(plan)s»: fənlər müxtəlif semestrlərdədir — birləşmədən sonra fənn planda %(n)s dəfə olacaq.": t(
            "Plan «%(plan)s»: the subjects are in different semesters — after the merge the subject will appear "
            "%(n)s times in the plan.",
            "План «%(plan)s»: дисциплины в разных семестрах — после объединения дисциплина будет в плане %(n)s раз.",
            "Plan «%(plan)s»: dersler farklı dönemlerde — birleştirmeden sonra ders planda %(n)s kez yer alacak.",
            "Plan «%(plan)s»: Die Fächer liegen in verschiedenen Semestern — nach der Zusammenführung steht das Fach "
            "%(n)s-mal im Plan.",
        ),
        "%(student)s · %(period)s: eyni dövrdə hər iki fənn üzrə aktiv qeydiyyat var — əvvəlcə birini bağlayın.": t(
            "%(student)s · %(period)s: active enrolments in both subjects in the same period — close one of them "
            "first.",
            "%(student)s · %(period)s: в одном периоде есть активные записи по обеим дисциплинам — сначала закройте "
            "одну из них.",
            "%(student)s · %(period)s: aynı dönemde her iki derste etkin kayıt var — önce birini kapatın.",
            "%(student)s · %(period)s: Im selben Zeitraum bestehen aktive Einschreibungen in beiden Fächern — "
            "schließen Sie zuerst eine davon.",
        ),
        "Hər ikisində yekun qiymət yazılıb.": t(
            "Both have a final grade.",
            "В обеих выставлена итоговая оценка.",
            "Her ikisinde de final notu girilmiş.",
            "Für beide ist eine Endnote eingetragen.",
        ),
        "Sillabus · %(period)s: hər iki fənnin semestr sillabusu var — əvvəlcə birini ləğv edin.": t(
            "Syllabus · %(period)s: both subjects have a semester syllabus — cancel one of them first.",
            "Силлабус · %(period)s: у обеих дисциплин есть семестровый силлабус — сначала отмените один из них.",
            "İzlence · %(period)s: her iki dersin dönem izlencesi var — önce birini iptal edin.",
            "Syllabus · %(period)s: Beide Fächer haben ein Semester-Syllabus — heben Sie zuerst eines auf.",
        ),
        "Sillabus (baza) · %(author)s: hər iki fənn üzrə baza sillabusu var — əvvəlcə birini ləğv edin.": t(
            "Syllabus (base) · %(author)s: both subjects have a base syllabus — cancel one of them first.",
            "Силлабус (базовый) · %(author)s: по обеим дисциплинам есть базовый силлабус — сначала отмените один.",
            "İzlence (temel) · %(author)s: her iki ders için temel izlence var — önce birini iptal edin.",
            "Syllabus (Basis) · %(author)s: Für beide Fächer gibt es ein Basis-Syllabus — heben Sie zuerst eines auf.",
        ),
        "Fənn qovluğu · %(owner)s · %(period)s: hər iki fənn üzrə qovluq var — əvvəlcə birini ləğv edin.": t(
            "Subject folder · %(owner)s · %(period)s: both subjects have a folder — cancel one of them first.",
            "Папка дисциплины · %(owner)s · %(period)s: есть папки по обеим дисциплинам — сначала отмените одну.",
            "Ders klasörü · %(owner)s · %(period)s: her iki ders için klasör var — önce birini iptal edin.",
            "Fachordner · %(owner)s · %(period)s: Für beide Fächer gibt es einen Ordner — heben Sie zuerst einen auf.",
        ),
        "Təkrar imtahan · %(student)s: hər iki fənn üzrə aktiv müraciət var — əvvəlcə birini bağlayın.": t(
            "Retake · %(student)s: active applications in both subjects — close one of them first.",
            "Пересдача · %(student)s: есть активные заявки по обеим дисциплинам — сначала закройте одну.",
            "Bütünleme · %(student)s: her iki derste etkin başvuru var — önce birini kapatın.",
            "Wiederholungsprüfung · %(student)s: aktive Anträge in beiden Fächern — schließen Sie zuerst einen.",
        ),
        "Tədris tapşırığı «%(task)s» · %(groups)s: eyni ixtisas və qruplar üçün hər iki fənn sətri var — əvvəlcə "
        "birini silin.": t(
            "Teaching assignment «%(task)s» · %(groups)s: both subjects have a row for the same programme and "
            "groups — delete one of them first.",
            "Учебное задание «%(task)s» · %(groups)s: для той же специальности и групп есть строки обеих дисциплин — "
            "сначала удалите одну.",
            "Öğretim görevi «%(task)s» · %(groups)s: aynı bölüm ve gruplar için her iki dersin satırı var — önce "
            "birini silin.",
            "Lehrauftrag «%(task)s» · %(groups)s: Für denselben Studiengang und dieselben Gruppen gibt es Zeilen "
            "beider Fächer — löschen Sie zuerst eine.",
        ),
        # ── cədvəl adları ──
        "Fənn açılışları (jurnallar)": t(
            "Subject offerings (journals)",
            "Потоки дисциплины (журналы)",
            "Ders açılışları (defterler)",
            "Lehrveranstaltungen (Journale)",
        ),
        "Tədris planı sətirləri": t(
            "Curriculum rows", "Строки учебного плана", "Öğretim planı satırları", "Studienplanzeilen"
        ),
        "Qrupun seçmə fənn qərarları": t(
            "Group elective decisions",
            "Решения группы по дисциплинам по выбору",
            "Grubun seçmeli ders kararları",
            "Wahlfachentscheidungen der Gruppe",
        ),
        "Təkrar imtahan müraciətləri": t(
            "Retake applications", "Заявки на пересдачу", "Bütünleme başvuruları", "Anträge auf Wiederholungsprüfung"
        ),
        "İmtahan şansı qeydləri (dəyişməz tarixçə)": t(
            "Exam chance records (immutable history)",
            "Записи о дополнительных попытках (неизменяемая история)",
            "Sınav hakkı kayıtları (değiştirilemez geçmiş)",
            "Einträge zu Prüfungsversuchen (unveränderliche Historie)",
        ),
        "Sillabuslar": t("Syllabi", "Силлабусы", "İzlenceler", "Syllabi"),
        "Tədris tapşırığı sətirləri": t(
            "Teaching assignment rows", "Строки учебного задания", "Öğretim görevi satırları", "Lehrauftragszeilen"
        ),
        "İmtahan qrupları (əlaqə)": t(
            "Exam groups (link)",
            "Экзаменационные группы (связь)",
            "Sınav grupları (bağlantı)",
            "Prüfungsgruppen (Verknüpfung)",
        ),
        "İmtahanlar": t("Exams", "Экзамены", "Sınavlar", "Prüfungen"),
        "Sual bankları": t("Question banks", "Банки вопросов", "Soru bankaları", "Fragenpools"),
        "Sual göndərişləri": t("Question submissions", "Отправки вопросов", "Soru gönderimleri", "Frageneinreichungen"),
        "Sorğu cavabları (anonim)": t(
            "Survey responses (anonymous)",
            "Ответы на опрос (анонимно)",
            "Anket yanıtları (anonim)",
            "Umfrageantworten (anonym)",
        ),
        "Fənn qovluqları": t("Subject folders", "Папки дисциплин", "Ders klasörleri", "Fachordner"),
        "Cədvəl: müəllimin fənn prioritetləri": t(
            "Timetable: teacher's subject priorities",
            "Расписание: приоритеты дисциплин преподавателя",
            "Ders programı: öğretim elemanının ders öncelikleri",
            "Stundenplan: Fachprioritäten der Lehrkraft",
        ),
        # ── dialoq ──
        "Fənləri birləşdir": t(
            "Merge subjects", "Объединить дисциплины", "Dersleri birleştir", "Fächer zusammenführen"
        ),
        "Birləşdir": t("Merge", "Объединить", "Birleştir", "Zusammenführen"),
        "Bütün istinadlar (açılış, plan sətri, sillabus, tapşırıq, imtahan…) saxlanılan fənnə köçür; digər kartlar "
        "SİLİNMİR — arxivlənir.": t(
            "All references (offering, plan row, syllabus, assignment, exam…) move to the kept subject; the other "
            "cards are NOT deleted — they are archived.",
            "Все ссылки (поток, строка плана, силлабус, задание, экзамен…) переходят к сохраняемой дисциплине; "
            "остальные карточки НЕ удаляются — архивируются.",
            "Tüm bağlantılar (açılış, plan satırı, izlence, görev, sınav…) korunan derse taşınır; diğer kartlar "
            "SİLİNMEZ — arşivlenir.",
            "Alle Verweise (Lehrveranstaltung, Planzeile, Syllabus, Auftrag, Prüfung…) gehen auf das beibehaltene "
            "Fach über; die anderen Karten werden NICHT gelöscht, sondern archiviert.",
        ),
        "Ad üzrə dublikat qrupları (hazır təklif)": t(
            "Duplicate groups by name (ready suggestion)",
            "Группы дубликатов по названию (готовое предложение)",
            "Ada göre yinelenen gruplar (hazır öneri)",
            "Dublettengruppen nach Namen (fertiger Vorschlag)",
        ),
        "Saxlanılacaq fənn": t("Subject to keep", "Сохраняемая дисциплина", "Korunacak ders", "Beizubehaltendes Fach"),
        "Birləşdiriləcək fənn(lər)": t(
            "Subject(s) to merge",
            "Объединяемые дисциплины",
            "Birleştirilecek ders(ler)",
            "Zusammenzuführende(s) Fach/Fächer",
        ),
        "Uyğun fənn tapılmadı": t(
            "No matching subject", "Подходящая дисциплина не найдена", "Uygun ders bulunamadı", "Kein passendes Fach"
        ),
        "Kod və ya ad ilə axtar…": t(
            "Search by code or name…",
            "Поиск по коду или названию…",
            "Kod veya ada göre ara…",
            "Nach Code oder Name suchen…",
        ),
        "Bir dəfəyə ən çox 10 fənn. Arxivdəki kartlar da seçilə bilər.": t(
            "At most 10 subjects at once. Archived cards can be selected too.",
            "Не более 10 дисциплин за раз. Можно выбрать и архивные карточки.",
            "Tek seferde en fazla 10 ders. Arşivdeki kartlar da seçilebilir.",
            "Höchstens 10 Fächer auf einmal. Auch archivierte Karten können gewählt werden.",
        ),
        "Önizlə": t("Preview", "Предпросмотр", "Önizle", "Vorschau"),
        "Səbəb": t("Reason", "Причина", "Gerekçe", "Begründung"),
        "Məs. Tədris şöbəsinin təklifi: eyni fənnin iki kartı (əmr/protokol nömrəsi)": t(
            "E.g. Teaching Office proposal: two cards of the same subject (order/protocol number)",
            "Напр. предложение учебного отдела: две карточки одной дисциплины (номер приказа/протокола)",
            "Örn. Öğretim biriminin önerisi: aynı dersin iki kartı (karar/tutanak numarası)",
            "Z. B. Vorschlag des Studienbüros: zwei Karten desselben Fachs (Anordnungs-/Protokollnummer)",
        ),
        "Ən azı 20 simvol — audit jurnalına aktor və vaxtla yazılır.": t(
            "At least 20 characters — recorded in the audit log with the actor and time.",
            "Не менее 20 символов — записывается в журнал аудита с исполнителем и временем.",
            "En az 20 karakter — denetim günlüğüne işlemi yapan ve zamanla yazılır.",
            "Mindestens 20 Zeichen — wird mit Akteur und Zeit im Audit-Protokoll gespeichert.",
        ),
        "köçür": t("moves", "переносится", "taşınır", "wird übertragen"),
        "qalır (dəyişməz tarixçə)": t(
            "stays (immutable history)",
            "остаётся (неизменяемая история)",
            "kalır (değiştirilemez geçmiş)",
            "bleibt (unveränderliche Historie)",
        ),
        "Köçürüləcək istinad yoxdur — yalnız kart arxivlənəcək.": t(
            "There are no references to move — only the card will be archived.",
            "Ссылок для переноса нет — будет архивирована только карточка.",
            "Taşınacak bağlantı yok — yalnızca kart arşivlenecek.",
            "Es gibt keine zu übertragenden Verweise — nur die Karte wird archiviert.",
        ),
        "Toqquşmalar — əvvəlcə bunları həll edin": t(
            "Conflicts — resolve these first",
            "Конфликты — сначала устраните их",
            "Çakışmalar — önce bunları giderin",
            "Konflikte — lösen Sie diese zuerst",
        ),
        "Avtomatik həll olunur": t(
            "Resolved automatically",
            "Устраняется автоматически",
            "Otomatik olarak giderilir",
            "Wird automatisch gelöst",
        ),
        "Xəbərdarlıqlar": t("Warnings", "Предупреждения", "Uyarılar", "Warnungen"),
        "Qeydlər": t("Notes", "Примечания", "Notlar", "Hinweise"),
        "və daha {n}": t("and {n} more", "и ещё {n}", "ve {n} tane daha", "und {n} weitere"),
        "Mənbə kartların arxiv səbəbi:": t(
            "Archive reason for the source cards:",
            "Причина архивирования исходных карточек:",
            "Kaynak kartların arşivlenme gerekçesi:",
            "Archivierungsgrund der Quellkarten:",
        ),
        "Toqquşma yoxdur — səbəbi yazıb birləşdirə bilərsiniz.": t(
            "No conflicts — enter the reason and merge.",
            "Конфликтов нет — укажите причину и объедините.",
            "Çakışma yok — gerekçeyi yazıp birleştirebilirsiniz.",
            "Keine Konflikte — Begründung eingeben und zusammenführen.",
        ),
        "Saxlanılacaq və ən azı bir birləşdiriləcək fənn seçin.": t(
            "Choose the subject to keep and at least one subject to merge.",
            "Выберите сохраняемую и хотя бы одну объединяемую дисциплину.",
            "Korunacak dersi ve birleştirilecek en az bir dersi seçin.",
            "Wählen Sie das beizubehaltende Fach und mindestens ein zusammenzuführendes Fach.",
        ),
        "Seçim dəyişdi — yenidən önizləyin.": t(
            "The selection changed — preview again.",
            "Выбор изменился — выполните предпросмотр заново.",
            "Seçim değişti — yeniden önizleyin.",
            "Die Auswahl hat sich geändert — erneut in der Vorschau prüfen.",
        ),
        "Seç": t("Select", "Выбрать", "Seçin", "Auswählen"),
        "arxivdə": t("archived", "в архиве", "arşivde", "archiviert"),
        "saxlanılır": t("kept", "сохраняется", "korunur", "wird beibehalten"),
        "açılış": t("offerings", "потоков", "şube", "Lehrveranstaltungen"),
        "Ad üzrə dublikat qrupu tapılmadı — fənləri axtarışla seçin.": t(
            "No duplicate groups by name — select the subjects via search.",
            "Групп дубликатов по названию не найдено — выберите дисциплины через поиск.",
            "Ada göre yinelenen grup bulunamadı — dersleri arayarak seçin.",
            "Keine Dublettengruppen nach Namen — wählen Sie die Fächer über die Suche.",
        ),
        "Sorğu alınmadı — yenidən cəhd edin.": t(
            "The request failed — try again.",
            "Запрос не выполнен — попробуйте ещё раз.",
            "İstek başarısız — yeniden deneyin.",
            "Die Anfrage ist fehlgeschlagen — versuchen Sie es erneut.",
        ),
    },
    CATALOG: {
        "Eyni adlı fənlər avtomatik birləşdirilmir. «Fənləri birləşdir» ilə saxlanılacaq kartı seçin — önizləmə "
        "bütün istinadları və toqquşmaları göstərir, mənbə kartlar silinmir, arxivlənir.": t(
            "Subjects with the same name are not merged automatically. Use «Merge subjects» to choose the card to "
            "keep — the preview shows all references and conflicts; source cards are not deleted but archived.",
            "Одноимённые дисциплины не объединяются автоматически. Выберите сохраняемую карточку через «Объединить "
            "дисциплины» — предпросмотр покажет все ссылки и конфликты; исходные карточки не удаляются, а "
            "архивируются.",
            "Aynı adlı dersler otomatik birleştirilmez. «Dersleri birleştir» ile korunacak kartı seçin — önizleme "
            "tüm bağlantıları ve çakışmaları gösterir; kaynak kartlar silinmez, arşivlenir.",
            "Gleichnamige Fächer werden nicht automatisch zusammengeführt. Wählen Sie über «Fächer zusammenführen» "
            "die beizubehaltende Karte — die Vorschau zeigt alle Verweise und Konflikte; Quellkarten werden nicht "
            "gelöscht, sondern archiviert.",
        ),
        "Eyni adlı fənlər avtomatik birləşdirilmir — birləşdirməni Tədris şöbəsi (təşkilat səviyyəli «Kataloqu "
        "idarə et» səlahiyyəti) aparır.": t(
            "Subjects with the same name are not merged automatically — merging is done by the Teaching Office "
            "(organisation-wide «Manage catalogue» permission).",
            "Одноимённые дисциплины не объединяются автоматически — объединение выполняет учебный отдел (право "
            "«Управлять каталогом» на уровне организации).",
            "Aynı adlı dersler otomatik birleştirilmez — birleştirmeyi Öğretim birimi (kurum düzeyinde «Kataloğu "
            "yönet» yetkisi) yapar.",
            "Gleichnamige Fächer werden nicht automatisch zusammengeführt — das übernimmt das Studienbüro "
            "(organisationsweite Berechtigung «Katalog verwalten»).",
        ),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
