#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: «Sorğu nəticələri» analitika UI-ı (apps/surveys F2) —
filtr paneli, KPI, qrafiklər və cədvəl qarşılıqları, müəllim reytinqi və kartı, ümumi
təkliflər, ixrac, anonimlik izahları. Kontekst: ``surveys.results``.

Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
DİQQƏT: ``{% trans %}`` mətnindəki «%» şablonda «%%» kimi saxlanılır (Django
``templatize``) — msgid-lər burada məhz həmin formadadır.
Tərcümələr AZ mənbə ilə EYNİ olmamalıdır (identity borcu) — məs. tr «Seçim» əvəzinə
«Seçili küme», «İş yükü» əvəzinə «Ders yükü».
İstifadə:  python scripts/i18n_add_survey2_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
C = "surveys.results"

STRINGS = {
    (C, "%%s seçimini götür"): ("Remove %%s", "Убрать «%%s»", "%%s seçimini kaldır"),
    (C, "%(done)s / %(expected)s hədəf"): (
        "%(done)s / %(expected)s targets",
        "%(done)s / %(expected)s целей",
        "%(done)s / %(expected)s hedef",
    ),
    (C, "%(label)s ilə müqayisədə"): (
        "compared with %(label)s",
        "по сравнению с %(label)s",
        "%(label)s ile karşılaştırıldığında",
    ),
    (C, "%(n)s cavab"): ("%(n)s responses", "ответов: %(n)s", "%(n)s yanıt"),
    (C, "%(n)s şərh — tarixsiz, identifikatorsuz, təsadüfi sırada."): (
        "%(n)s comments — no dates, no identifiers, in random order.",
        "Комментариев: %(n)s — без дат и идентификаторов, в случайном порядке.",
        "%(n)s yorum — tarihsiz, kimliksiz, rastgele sırada.",
    ),
    (C, "%(pct)s%% razıdır"): ("%(pct)s%% agree", "%(pct)s%% согласны", "%(pct)s%% katılıyor"),
    (C, "%(total)s təklif (identifikatorsuz, təsadüfi sırada)."): (
        "%(total)s suggestions (no identifiers, random order).",
        "Предложений: %(total)s (без идентификаторов, в случайном порядке).",
        "%(total)s öneri (kimliksiz, rastgele sırada).",
    ),
    (
        C,
        "%(visible)s müəllimin nəticəsi görünür, %(hidden)s müəllim gizlidir (n &lt; %(k)s və ya tamamlayıcı qayda). "
        "Fərq — müəllimin ümumi balı ilə kafedra/universitet ortası arasındakı fərqdir.",
    ): (
        "Results are shown for %(visible)s teachers; %(hidden)s teachers are hidden (n &lt; %(k)s or the complementary "
        "rule). Difference — the teacher's overall score minus the department/university average.",
        "Показаны результаты %(visible)s преподавателей, %(hidden)s скрыты (n &lt; %(k)s или правило дополнения). "
        "Разница — общий балл преподавателя минус среднее по кафедре/университету.",
        "%(visible)s öğretim üyesinin sonucu görünüyor, %(hidden)s öğretim üyesi gizli (n &lt; %(k)s veya tamamlayıcı "
        "kural). Fark — öğretim üyesinin genel puanı ile bölüm/üniversite ortalaması arasındaki farktır.",
    ),
    (C, "%(year)s — bütün il"): ("%(year)s — whole year", "%(year)s — весь год", "%(year)s — tüm yıl"),
    (C, "Ad"): ("Name", "Название", "Adı"),
    (
        C,
        "Anonim müəllim qiymətləndirmə sorğusunun nəticələri — süzün, müqayisə edin, müəllim kartına baxın və "
        "aqreqatları ixrac edin.",
    ): (
        "Results of the anonymous teacher evaluation survey — filter, compare, open a teacher card and export aggregates.",
        "Результаты анонимного опроса об оценке преподавателей — фильтруйте, сравнивайте, открывайте карточку "
        "преподавателя и экспортируйте агрегаты.",
        "Anonim öğretim üyesi değerlendirme anketinin sonuçları — filtreleyin, karşılaştırın, öğretim üyesi kartına "
        "bakın ve toplu verileri dışa aktarın.",
    ),
    (C, "Anonim şərhlər"): ("Anonymous comments", "Анонимные комментарии", "Anonim yorumlar"),
    (C, "Anonimlik həddi (k)"): ("Anonymity threshold (k)", "Порог анонимности (k)", "Anonimlik eşiği (k)"),
    (C, "Anonimlik həddinə çatmayan kampaniyalar: %(n)s — onların təklifləri göstərilmir."): (
        "Campaigns below the anonymity threshold: %(n)s — their suggestions are not shown.",
        "Кампаний ниже порога анонимности: %(n)s — их предложения не показываются.",
        "Anonimlik eşiğine ulaşmayan kampanyalar: %(n)s — önerileri gösterilmez.",
    ),
    (
        C,
        "Anonimlik: nəticə yalnız ən azı %(k)s cavabı olan qrup üçün göstərilir; kiçik qrupu çıxma yolu ilə aça "
        "biləcək sətirlər də gizlədilir. Şərhlər tarixsiz, identifikatorsuz və təsadüfi sıradadır.",
    ): (
        "Anonymity: results are shown only for groups with at least %(k)s responses; rows that could reveal a small "
        "group by subtraction are hidden as well. Comments carry no dates or identifiers and appear in random order.",
        "Анонимность: результаты показываются только для групп минимум с %(k)s ответами; строки, по которым "
        "вычитанием можно вычислить малую группу, тоже скрываются. Комментарии без дат и идентификаторов, в "
        "случайном порядке.",
        "Anonimlik: sonuçlar yalnızca en az %(k)s yanıtı olan gruplar için gösterilir; çıkarma yoluyla küçük bir "
        "grubu açığa çıkarabilecek satırlar da gizlenir. Yorumlar tarihsiz, kimliksiz ve rastgele sıradadır.",
    ),
    (C, "Axtarışa uyğun nəticə yoxdur."): (
        "No results match the search.",
        "Ничего не найдено.",
        "Aramayla eşleşen sonuç yok.",
    ),
    (C, "Axtarışa uyğun təklif yoxdur."): (
        "No suggestions match the search.",
        "Подходящих предложений нет.",
        "Aramayla eşleşen öneri yok.",
    ),
    (C, "Aydın izah"): ("Clear explanation", "Понятное объяснение", "Anlaşılır anlatım"),
    (C, "Açar sözlər"): ("Keywords", "Ключевые слова", "Anahtar kelimeler"),
    (C, "Bal"): ("Score", "Балл", "Puan"),
    (C, "Bal paylanması qrafiki; eyni rəqəmlər aşağıdakı cədvəldədir."): (
        "Score distribution chart; the same figures are in the table below.",
        "График распределения баллов; те же данные — в таблице ниже.",
        "Puan dağılımı grafiği; aynı rakamlar aşağıdaki tablodadır.",
    ),
    (C, "Bu dövr üçün hələ cavab yoxdur"): (
        "No responses for this period yet",
        "Ответов за этот период пока нет",
        "Bu dönem için henüz yanıt yok",
    ),
    (C, "Bu filtr kombinasiyası anonimliyi poza bilər"): (
        "This filter combination could break anonymity",
        "Эта комбинация фильтров может нарушить анонимность",
        "Bu filtre kombinasyonu anonimliği bozabilir",
    ),
    (C, "Bu məlumata baxmaq üçün icazəniz yoxdur."): (
        "You do not have permission to view this information.",
        "У вас нет прав на просмотр этих данных.",
        "Bu bilgiyi görüntüleme izniniz yok.",
    ),
    (
        C,
        "Bu nəticə göstərilsəydi, kafedra və ya universitet ortasından çıxma yolu ilə anonimlik həddindən az cavablı "
        "müəllimin nəticəsi hesablana bilərdi.",
    ): (
        "If this result were shown, the result of a teacher with fewer responses than the anonymity threshold could "
        "be calculated by subtraction from the department or university average.",
        "Если бы этот результат был показан, вычитанием из среднего по кафедре или университету можно было бы "
        "вычислить результат преподавателя с числом ответов ниже порога анонимности.",
        "Bu sonuç gösterilseydi, bölüm veya üniversite ortalamasından çıkarma yoluyla anonimlik eşiğinin altında "
        "yanıtı olan bir öğretim üyesinin sonucu hesaplanabilirdi.",
    ),
    (C, "Bu seçim üzrə şərh yazılmayıb."): (
        "No comments were written for this selection.",
        "По этому выбору комментариев нет.",
        "Bu seçim için yorum yazılmamış.",
    ),
    (C, "Bölgü: məmnunluq və tədris şəraiti"): (
        "Breakdown: satisfaction and learning conditions",
        "Разбивка: удовлетворённость и условия обучения",
        "Dağılım: memnuniyet ve öğrenim koşulları",
    ),
    (C, "Bütün dövrlər"): ("All periods", "Все периоды", "Tüm dönemler"),
    (C, "Bütün universitet"): ("Whole university", "Весь университет", "Tüm üniversite"),
    (C, "CSV — bir cədvəl"): ("CSV — single table", "CSV — одна таблица", "CSV — tek tablo"),
    (C, "Cavab"): ("Responses", "Ответы", "Yanıt"),
    (C, "Cavab faizi"): ("Response rate", "Доля ответивших", "Yanıt oranı"),
    (C, "Cavab faizi (%)"): ("Response rate (%)", "Доля ответивших (%)", "Yanıt oranı (%)"),
    (C, "Cavab sayı"): ("Responses", "Число ответов", "Yanıt sayısı"),
    (C, "Cavab sayı anonimlik həddindən azdır."): (
        "The number of responses is below the anonymity threshold.",
        "Число ответов ниже порога анонимности.",
        "Yanıt sayısı anonimlik eşiğinin altında.",
    ),
    (C, "Cavab sayı azdır (%(n)s &lt; %(k)s) — anonimliyi qorumaq üçün nəticə göstərilmir."): (
        "Too few responses (%(n)s &lt; %(k)s) — results are hidden to protect anonymity.",
        "Слишком мало ответов (%(n)s &lt; %(k)s) — результаты скрыты для защиты анонимности.",
        "Yanıt sayısı az (%(n)s &lt; %(k)s) — anonimliği korumak için sonuç gösterilmiyor.",
    ),
    (C, "Cavabların Likert paylanması; eyni rəqəmlər aşağıdakı cədvəldədir."): (
        "Likert distribution of responses; the same figures are in the table below.",
        "Распределение ответов по шкале Лайкерта; те же данные — в таблице ниже.",
        "Yanıtların Likert dağılımı; aynı rakamlar aşağıdaki tablodadır.",
    ),
    (C, "Cavabların paylanması (Likert 1–5)"): (
        "Response distribution (Likert 1–5)",
        "Распределение ответов (Лайкерт 1–5)",
        "Yanıt dağılımı (Likert 1–5)",
    ),
    (C, "Cədvəl kimi göstər"): ("Show as table", "Показать таблицей", "Tablo olarak göster"),
    (C, "Daha çox göstər"): ("Show more", "Показать ещё", "Daha fazla göster"),
    (
        C,
        "Daraldılmış dəst ilə daraldılmamış dəst arasındakı fərq %(k)s cavabdan azdır — çıxma yolu ilə bir neçə "
        "tələbənin cavabı açıla bilərdi. Filtri genişləndirin.",
    ): (
        "The difference between the narrowed and the full set is fewer than %(k)s responses — a few students' answers "
        "could be revealed by subtraction. Broaden the filter.",
        "Разница между суженной и полной выборкой меньше %(k)s ответов — вычитанием можно было бы раскрыть ответы "
        "нескольких студентов. Расширьте фильтр.",
        "Daraltılmış küme ile tam küme arasındaki fark %(k)s yanıttan az — çıkarma yoluyla birkaç öğrencinin yanıtı "
        "açığa çıkabilirdi. Filtreyi genişletin.",
    ),
    (C, "Digər şərhlər"): ("Other comments", "Другие комментарии", "Diğer yorumlar"),
    (C, "Dinamika"): ("Trend", "Динамика", "Değişim"),
    (C, "Dinamika üçün hələ kampaniya yoxdur."): (
        "No campaigns for a trend yet.",
        "Для динамики пока нет кампаний.",
        "Değişim için henüz kampanya yok.",
    ),
    (C, "Doldurulmuş hədəf"): ("Completed targets", "Заполнено целей", "Doldurulan hedef"),
    (C, "Dövr"): ("Period", "Период", "Dönem"),
    (C, "Dövrlər üzrə dinamika"): ("Trend across periods", "Динамика по периодам", "Dönemlere göre değişim"),
    (C, "Dövrlər üzrə dinamika qrafiki; eyni rəqəmlər aşağıdakı cədvəldədir."): (
        "Trend chart across periods; the same figures are in the table below.",
        "График динамики по периодам; те же данные — в таблице ниже.",
        "Dönemlere göre değişim grafiği; aynı rakamlar aşağıdaki tablodadır.",
    ),
    (C, "Dərs materialları"): ("Course materials", "Учебные материалы", "Ders materyalleri"),
    (C, "Dəyər"): ("Value", "Значение", "Değer"),
    (C, "Excel — bütün cədvəllər"): ("Excel — all tables", "Excel — все таблицы", "Excel — tüm tablolar"),
    (C, "Fakültə"): ("Faculty", "Факультет", "Fakülte"),
    (C, "Fakültə və kafedra müqayisəsi"): (
        "Faculty and department comparison",
        "Сравнение факультетов и кафедр",
        "Fakülte ve bölüm karşılaştırması",
    ),
    (C, "Fakültə və kafedra müqayisəsi qrafiki; eyni rəqəmlər aşağıdakı cədvəldədir."): (
        "Faculty and department comparison chart; the same figures are in the table below.",
        "График сравнения факультетов и кафедр; те же данные — в таблице ниже.",
        "Fakülte ve bölüm karşılaştırma grafiği; aynı rakamlar aşağıdaki tablodadır.",
    ),
    (C, "Fakültə və kafedralar"): ("Faculties and departments", "Факультеты и кафедры", "Fakülteler ve bölümler"),
    (C, "Fakültələr"): ("Faculties", "Факультеты", "Fakülteler"),
    (C, "Filtrlər"): ("Filters", "Фильтры", "Filtreler"),
    (C, "Fəal iştirak"): ("Active participation", "Активное участие", "Aktif katılım"),
    (C, "Fənn"): ("Subject", "Предмет", "Ders"),
    (C, "Fənn və qrup üzrə"): ("By subject and group", "По предметам и группам", "Ders ve gruba göre"),
    (C, "Fənn/qrup filtri tətbiq olunub — göstəricilər yalnız seçilmiş dəst üzrədir."): (
        "A subject/group filter is applied — figures cover only the selected set.",
        "Применён фильтр предмета/группы — показатели только по выбранной выборке.",
        "Ders/grup filtresi uygulandı — göstergeler yalnızca seçilen küme içindir.",
    ),
    (
        C,
        "Fənn/qrup filtri: müəllim eyni tələbəyə bir neçə fənn deyirsə, tələbə onu bir dəfə qiymətləndirir və cavab "
        "müəllimin əsas (ilk) fənninə aid edilir.",
    ): (
        "Subject/group filter: when a teacher teaches the same student several subjects, the student rates the teacher "
        "once and the response is attributed to the teacher's main (first) subject.",
        "Фильтр предмета/группы: если преподаватель ведёт у студента несколько предметов, студент оценивает его один "
        "раз, и ответ относится к основному (первому) предмету.",
        "Ders/grup filtresi: öğretim üyesi aynı öğrenciye birden fazla ders veriyorsa öğrenci onu bir kez değerlendirir "
        "ve yanıt ana (ilk) derse atfedilir.",
    ),
    (C, "Fərq: kafedra"): ("Diff.: department", "Разница: кафедра", "Fark: bölüm"),
    (C, "Fərq: universitet"): ("Diff.: university", "Разница: университет", "Fark: üniversite"),
    (C, "Görünən cəmdən çıxma yolu ilə kiçik qrupu hesablamağın qarşısını almaq üçün gizlədilib."): (
        "Hidden so that a small group cannot be calculated by subtraction from a visible total.",
        "Скрыто, чтобы малую группу нельзя было вычислить вычитанием из видимой суммы.",
        "Görünen toplamdan çıkarma yoluyla küçük bir grubun hesaplanmasını önlemek için gizlendi.",
    ),
    (C, "Göstər"): ("Show", "Показать", "Göster"),
    (C, "Göstərici"): ("Indicator", "Показатель", "Gösterge"),
    (C, "Göstərilir"): ("Shown", "Показано", "Gösterilen"),
    (C, "Göstərilən təkliflərdə axtar"): (
        "Search the shown suggestions",
        "Поиск по показанным предложениям",
        "Gösterilen önerilerde ara",
    ),
    (C, "Gözlənilən hədəf"): ("Expected targets", "Ожидается целей", "Beklenen hedef"),
    (C, "Güclü cəhətlər"): ("Strengths", "Сильные стороны", "Güçlü yönler"),
    (C, "Hamısı"): ("All", "Все", "Tümü"),
    (C, "Hazırlıq və plan"): ("Preparation and plan", "Подготовка и план", "Hazırlık ve plan"),
    (C, "Hörmət və ədalət"): ("Respect and fairness", "Уважение и справедливость", "Saygı ve adalet"),
    (C, "Hələ heç bir sorğu kampaniyası keçirilməyib"): (
        "No survey campaign has been held yet",
        "Кампании опроса ещё не проводились",
        "Henüz hiç anket kampanyası yapılmadı",
    ),
    (C, "Hələ təklif yoxdur"): ("No suggestions yet", "Предложений пока нет", "Henüz öneri yok"),
    (
        C,
        "Hər dövr öz anonimlik həddi ilə; gizli nöqtələr xətdə boşluq kimi görünür. Fənn/qrup filtri dinamikaya tətbiq "
        "olunmur.",
    ): (
        "Each period uses its own anonymity threshold; hidden points appear as gaps in the line. Subject/group filters "
        "do not apply to the trend.",
        "Каждый период — со своим порогом анонимности; скрытые точки видны как разрывы линии. Фильтр "
        "предмета/группы к динамике не применяется.",
        "Her dönem kendi anonimlik eşiğiyle; gizli noktalar çizgide boşluk olarak görünür. Ders/grup filtresi "
        "değişime uygulanmaz.",
    ),
    (C, "Hər kampaniyada cavab sayı anonimlik həddindən azdır — təkliflər göstərilmir."): (
        "Each campaign has fewer responses than the anonymity threshold — suggestions are not shown.",
        "В каждой кампании ответов меньше порога анонимности — предложения не показываются.",
        "Her kampanyada yanıt sayısı anonimlik eşiğinin altında — öneriler gösterilmiyor.",
    ),
    (
        C,
        "Hər sətir 100%%-dir: solda «razı deyiləm» cavabları, mərkəzdə «qismən», sağda «razıyam». Kənardakı rəqəmlər "
        "cəm paylardır.",
    ): (
        "Each row totals 100%%: “disagree” answers on the left, “partly” in the middle, “agree” on the right. The "
        "figures at the ends are the combined shares.",
        "Каждая строка — 100%%: слева ответы «не согласен», в центре «частично», справа «согласен». Числа по краям — "
        "суммарные доли.",
        "Her satır %%100: solda «katılmıyorum», ortada «kısmen», sağda «katılıyorum» yanıtları. Uçlardaki rakamlar "
        "toplam paylardır.",
    ),
    (C, "Kafedra"): ("Department", "Кафедра", "Bölüm"),
    (C, "Kafedra ortası"): ("Department average", "Среднее по кафедре", "Bölüm ortalaması"),
    (C, "Kafedralar"): ("Departments", "Кафедры", "Bölümler"),
    (C, "Kampaniya RİM semestr jurnallarını bağlayanda özü açılır; cavablar toplandıqca nəticələr burada görünəcək."): (
        "A campaign opens automatically when RİM closes the semester journals; results will appear here as responses "
        "come in.",
        "Кампания открывается автоматически, когда RİM закрывает журналы семестра; по мере поступления ответов "
        "результаты появятся здесь.",
        "Kampanya, RİM dönem defterlerini kapattığında otomatik açılır; yanıtlar geldikçe sonuçlar burada görünecek.",
    ),
    (C, "Kampaniya davam edir: %(done)s / %(expected)s hədəf doldurulub. Cavablar toplandıqca nəticələr görünəcək."): (
        "The campaign is ongoing: %(done)s / %(expected)s targets completed. Results will appear as responses come in.",
        "Кампания продолжается: заполнено %(done)s / %(expected)s. Результаты появятся по мере поступления ответов.",
        "Kampanya devam ediyor: %(done)s / %(expected)s hedef dolduruldu. Yanıtlar geldikçe sonuçlar görünecek.",
    ),
    (C, "Kampaniyalar"): ("Campaigns", "Кампании", "Kampanyalar"),
    (C, "Kod"): ("Code", "Код", "Soru kodu"),
    (C, "Kurs"): ("Year", "Курс", "Sınıf"),
    (C, "Kurs %(year)s"): ("Year %(year)s", "%(year)s курс", "%(year)s. sınıf"),
    (C, "Kurslar"): ("Years", "Курсы", "Sınıflar"),
    (C, "Likert indeksi"): ("Likert index", "Индекс Лайкерта", "Likert endeksi"),
    (C, "Likert indeksi (1–5)"): ("Likert index (1–5)", "Индекс Лайкерта (1–5)", "Likert endeksi (1–5)"),
    (C, "Likert şkalası 1–5 (5 — tamamilə razıyam). İşarələr müqayisə nöqtələridir."): (
        "Likert scale 1–5 (5 — strongly agree). The markers are comparison points.",
        "Шкала Лайкерта 1–5 (5 — полностью согласен). Метки — точки сравнения.",
        "Likert ölçeği 1–5 (5 — kesinlikle katılıyorum). İşaretler karşılaştırma noktalarıdır.",
    ),
    (C, "Minimum cavab"): ("Minimum responses", "Минимум ответов", "Asgari yanıt"),
    (C, "Müəllim"): ("Teacher", "Преподаватель", "Öğretim üyesi"),
    (
        C,
        "Müəllim eyni tələbəyə bir neçə fənn deyirsə, tələbə onu bir dəfə qiymətləndirir — bu cavab müəllimin əsas "
        "(ilk) fənninə aid edilir, yəni fənlər birləşmiş görünə bilər.",
    ): (
        "When a teacher teaches the same student several subjects, the student rates the teacher once — the response is "
        "attributed to the teacher's main (first) subject, so subjects may appear merged.",
        "Если преподаватель ведёт у студента несколько предметов, студент оценивает его один раз — ответ относится к "
        "основному (первому) предмету, поэтому предметы могут выглядеть объединёнными.",
        "Öğretim üyesi aynı öğrenciye birden fazla ders veriyorsa öğrenci onu bir kez değerlendirir — yanıt ana (ilk) "
        "derse atfedilir, bu yüzden dersler birleşmiş görünebilir.",
    ),
    (C, "Müəllim kartı"): ("Teacher card", "Карточка преподавателя", "Öğretim üyesi kartı"),
    (C, "Müəllim reytinqi"): ("Teacher ranking", "Рейтинг преподавателей", "Öğretim üyesi sıralaması"),
    (C, "Müəllim reytinqi — sütun başlığı sıralayır"): (
        "Teacher ranking — column headers sort the table",
        "Рейтинг преподавателей — заголовок столбца сортирует",
        "Öğretim üyesi sıralaması — sütun başlığı sıralar",
    ),
    (C, "Müəllim tapılmadı"): ("No teacher found", "Преподаватель не найден", "Öğretim üyesi bulunamadı"),
    (C, "Müəllim və ya kafedra"): ("Teacher or department", "Преподаватель или кафедра", "Öğretim üyesi veya bölüm"),
    (C, "Müəllimlər"): ("Teachers", "Преподаватели", "Öğretim üyeleri"),
    (C, "Müəllimlər (cəmi)"): ("Teachers (total)", "Преподавателей (всего)", "Öğretim üyeleri (toplam)"),
    (C, "Məlumat yoxdur."): ("No data.", "Нет данных.", "Veri yok."),
    (C, "Məmnunluq və tədris şəraiti (Likert 1–5)"): (
        "Satisfaction and learning conditions (Likert 1–5)",
        "Удовлетворённость и условия обучения (Лайкерт 1–5)",
        "Memnuniyet ve öğrenim koşulları (Likert 1–5)",
    ),
    (C, "Məxfi — anonim sorğunun aqreqat nəticələri; yalnız xidməti istifadə üçün."): (
        "Confidential — aggregate results of an anonymous survey; for official use only.",
        "Конфиденциально — агрегированные результаты анонимного опроса; только для служебного пользования.",
        "Gizli — anonim anketin toplu sonuçları; yalnızca kurum içi kullanım içindir.",
    ),
    (C, "Neçə təklifdə keçir"): ("Number of suggestions", "В скольких предложениях", "Kaç öneride geçiyor"),
    (C, "Nəticə bölmələri"): ("Result sections", "Разделы результатов", "Sonuç bölümleri"),
    (C, "Nəticə filtrləri"): ("Result filters", "Фильтры результатов", "Sonuç filtreleri"),
    (C, "Nəticə gizlidir"): ("Result hidden", "Результат скрыт", "Sonuç gizli"),
    (C, "Nəticə tamamlayıcı qayda ilə gizlədilib"): (
        "Result hidden by the complementary rule",
        "Результат скрыт по правилу дополнения",
        "Sonuç tamamlayıcı kuralla gizlendi",
    ),
    (
        C,
        "Nəticələri kafedra müdiri (öz kafedrası), tədris şöbəsi, keyfiyyətə nəzarət, prorektor, rektor və RİM "
        "rəhbəri görür.",
    ): (
        "Results are visible to heads of department (their own department), the academic affairs office, quality "
        "assurance, vice-rectors, the rector and the head of RİM.",
        "Результаты видят заведующие кафедрами (свою кафедру), учебный отдел, служба контроля качества, проректоры, "
        "ректор и руководитель RİM.",
        "Sonuçları bölüm başkanları (kendi bölümleri), öğrenci işleri, kalite kontrol, rektör yardımcıları, rektör ve "
        "RİM başkanı görür.",
    ),
    (C, "Nəticəsi görünən müəllimlər"): (
        "Teachers with visible results",
        "Преподаватели с видимыми результатами",
        "Sonucu görünen öğretim üyeleri",
    ),
    (C, "Orta"): ("Mean", "Среднее", "Ortalama"),
    (C, "Orta bal (1–5); ən yüksək məmnunluq yuxarıda."): (
        "Mean score (1–5); highest satisfaction on top.",
        "Средний балл (1–5); наибольшая удовлетворённость сверху.",
        "Ortalama puan (1–5); en yüksek memnuniyet üstte.",
    ),
    (C, "Orta ümumi bal"): ("Mean overall score", "Средний общий балл", "Ortalama genel puan"),
    (C, "Orta ümumi bal (1–10)"): (
        "Mean overall score (1–10)",
        "Средний общий балл (1–10)",
        "Ortalama genel puan (1–10)",
    ),
    (C, "Orta ümumi bal (1–10), yuxarıdan aşağı azalan sıra."): (
        "Mean overall score (1–10), in descending order.",
        "Средний общий балл (1–10), по убыванию.",
        "Ortalama genel puan (1–10), azalan sırada.",
    ),
    (C, "Orta: %(avg)s · %(n)s cavab"): (
        "Mean: %(avg)s · %(n)s responses",
        "Среднее: %(avg)s · ответов: %(n)s",
        "Ortalama: %(avg)s · %(n)s yanıt",
    ),
    (C, "Pay"): ("Share", "Доля", "Oran"),
    (C, "Paylanma: %(label)s"): ("Distribution: %(label)s", "Распределение: %(label)s", "Dağılım: %(label)s"),
    (C, "Praktika ilə əlaqə"): ("Link to practice", "Связь с практикой", "Uygulamayla bağlantı"),
    (C, "Qrup"): ("Group", "Группа", "Grup"),
    (C, "Qısa ad"): ("Short name", "Краткое название", "Kısa ad"),
    (C, "Razı (4–5)"): ("Agree (4–5)", "Согласны (4–5)", "Katılıyor (4–5)"),
    (C, "Razı deyil (1–2)"): ("Disagree (1–2)", "Не согласны (1–2)", "Katılmıyor (1–2)"),
    (C, "Say"): ("Count", "Количество", "Sayı"),
    (C, "Seriya"): ("Series", "Ряд", "Seri"),
    (C, "Seçilmiş filtrlərdə bu müəllim üçün cavab yoxdur və ya o, sizin əhatənizdə deyil."): (
        "There are no responses for this teacher with the selected filters, or the teacher is outside your scope.",
        "По выбранным фильтрам ответов для этого преподавателя нет, либо он вне вашей области доступа.",
        "Seçilen filtrelerde bu öğretim üyesi için yanıt yok veya sizin kapsamınızda değil.",
    ),
    (C, "Seçilmiş filtrlərə uyğun cavab yoxdur"): (
        "No responses match the selected filters",
        "Нет ответов по выбранным фильтрам",
        "Seçilen filtrelere uyan yanıt yok",
    ),
    (C, "Seçim"): ("Selection", "Выборка", "Seçili küme"),
    (C, "Sillabusa əməl"): ("Follows the syllabus", "Соблюдение силлабуса", "Ders izlencesine uyum"),
    (C, "Siyahı ilk 500 müəllimlə məhdudlaşır — filtrlə daraldın."): (
        "The list is limited to the first 500 teachers — narrow it with filters.",
        "Список ограничен первыми 500 преподавателями — сузьте фильтрами.",
        "Liste ilk 500 öğretim üyesiyle sınırlı — filtreyle daraltın.",
    ),
    (C, "Son kampaniya — %(label)s"): (
        "Latest campaign — %(label)s",
        "Последняя кампания — %(label)s",
        "Son kampanya — %(label)s",
    ),
    (C, "Sonrakı"): ("Next", "Далее", "Sonraki"),
    (C, "Sorğu kampaniyaları"): ("Survey campaigns", "Кампании опроса", "Anket kampanyaları"),
    (C, "Sorğu nəticələri"): ("Survey results", "Результаты опроса", "Anket sonuçları"),
    (C, "Sorğu nəticələrinin ixracı (aqreqatlar)"): (
        "Export of survey results (aggregates)",
        "Экспорт результатов опроса (агрегаты)",
        "Anket sonuçlarının dışa aktarımı (toplu veriler)",
    ),
    (C, "Sorğu nəticələrinə baxmaq üçün icazəniz yoxdur"): (
        "You do not have permission to view survey results",
        "У вас нет прав на просмотр результатов опроса",
        "Anket sonuçlarını görüntüleme izniniz yok",
    ),
    (C, "Sorğu nəticələrinə qayıt"): (
        "Back to survey results",
        "Вернуться к результатам опроса",
        "Anket sonuçlarına dön",
    ),
    (C, "Struktur əhatəniz"): ("Your structural scope", "Ваша область доступа", "Yapısal kapsamınız"),
    (C, "Sual"): ("Question", "Вопрос", "Soru"),
    (C, "Sual üzrə paylanma"): ("Distribution by question", "Распределение по вопросам", "Soruya göre dağılım"),
    (C, "Suallar"): ("Questions", "Вопросы", "Sorular"),
    (C, "Suallar və paylanma"): ("Questions and distribution", "Вопросы и распределение", "Sorular ve dağılım"),
    (C, "Suallar üzrə orta bal"): ("Mean score by question", "Средний балл по вопросам", "Soruya göre ortalama puan"),
    (C, "Suallar üzrə orta bal qrafiki; eyni rəqəmlər aşağıdakı cədvəldədir."): (
        "Mean score by question chart; the same figures are in the table below.",
        "График среднего балла по вопросам; те же данные — в таблице ниже.",
        "Soruya göre ortalama puan grafiği; aynı rakamlar aşağıdaki tablodadır.",
    ),
    (C, "Söz"): ("Word", "Слово", "Kelime"),
    (C, "Səhifə"): ("Page", "Страница", "Sayfa"),
    (C, "Səhifələr"): ("Pages", "Страницы", "Sayfalar"),
    (C, "Səviyyə"): ("Level", "Уровень", "Düzey"),
    (C, "Tövsiyə"): ("Recommendation", "Рекомендация", "Tavsiye"),
    (C, "Tövsiyə edənlər"): ("Would recommend", "Рекомендуют", "Tavsiye edenler"),
    (C, "Tövsiyə edənlər (%)"): ("Would recommend (%)", "Рекомендуют (%)", "Tavsiye edenler (%)"),
    (C, "Tədris şəraiti"): ("Learning conditions", "Условия обучения", "Öğrenim koşulları"),
    (C, "Tədris şəraiti (1–5)"): ("Learning conditions (1–5)", "Условия обучения (1–5)", "Öğrenim koşulları (1–5)"),
    (C, "Təkliflər"): ("Suggestions", "Предложения", "Öneriler"),
    (C, "Təyin olunmayıb"): ("Not assigned", "Не указано", "Belirtilmemiş"),
    (C, "Universitet"): ("University", "Университет", "Üniversite"),
    (C, "Universitet ortası"): ("University average", "Среднее по университету", "Üniversite ortalaması"),
    (C, "Universitet üçün təkliflər"): (
        "Suggestions for the university",
        "Предложения для университета",
        "Üniversite için öneriler",
    ),
    (C, "Universiteti necə yaxşılaşdırmaq olar — tələbə təklifləri"): (
        "How to improve the university — student suggestions",
        "Как улучшить университет — предложения студентов",
        "Üniversite nasıl iyileştirilebilir — öğrenci önerileri",
    ),
    (C, "Vaxtında başlama"): ("Punctuality", "Пунктуальность", "Dakiklik"),
    (C, "Vaxtında rəy"): ("Timely feedback", "Своевременная обратная связь", "Zamanında geri bildirim"),
    (C, "Vəziyyət"): ("Status", "Статус", "Durum"),
    (C, "Xanada: ümumi bal (1–10) · Likert indeksi (1–5)."): (
        "Each cell: overall score (1–10) · Likert index (1–5).",
        "В ячейке: общий балл (1–10) · индекс Лайкерта (1–5).",
        "Hücrede: genel puan (1–10) · Likert endeksi (1–5).",
    ),
    (C, "Xülasə"): ("Summary", "Сводка", "Özet"),
    (C, "Yalnız aqreqatlar — şərh mətni və fərdi cavab ixrac olunmur."): (
        "Aggregates only — comment texts and individual responses are never exported.",
        "Только агрегаты — тексты комментариев и отдельные ответы не экспортируются.",
        "Yalnızca toplu veriler — yorum metinleri ve bireysel yanıtlar dışa aktarılmaz.",
    ),
    (C, "Yaradılıb"): ("Generated", "Создано", "Oluşturuldu"),
    (C, "Yer"): ("Rank", "Место", "Sıra"),
    (C, "Yüklənir…"): ("Loading…", "Загрузка…", "Yükleniyor…"),
    (C, "Yüklənmə alınmadı, yenidən cəhd edin."): (
        "Loading failed, please try again.",
        "Не удалось загрузить, попробуйте ещё раз.",
        "Yüklenemedi, lütfen tekrar deneyin.",
    ),
    (C, "ad, soyad, kafedra…"): ("name, surname, department…", "имя, фамилия, кафедра…", "ad, soyad, bölüm…"),
    (C, "aşağı"): ("lower", "ниже", "düşük"),
    (C, "bəli"): ("yes", "да", "evet"),
    (C, "cəmi"): ("total", "всего", "toplam"),
    (C, "cəmi %(n)s müəllim"): ("%(n)s teachers in total", "всего преподавателей: %(n)s", "toplam %(n)s öğretim üyesi"),
    (C, "dəyişməyib"): ("no change", "без изменений", "değişmedi"),
    (C, "gizli"): ("hidden", "скрыто", "gizlendi"),
    (C, "gizli — n < k"): ("hidden — n < k", "скрыто — n < k", "gizlendi — n < k"),
    (C, "gizli — tamamlayıcı qayda"): (
        "hidden — complementary rule",
        "скрыто — правило дополнения",
        "gizlendi — tamamlayıcı kural",
    ),
    (C, "görünür"): ("shown", "показано", "görünüyor"),
    (C, "göstərilən təkliflərdə axtar…"): (
        "search the shown suggestions…",
        "поиск по показанным предложениям…",
        "gösterilen önerilerde ara…",
    ),
    (C, "ixtisas/kurs filtrində hesablanmır"): (
        "not calculated with a programme/year filter",
        "не рассчитывается при фильтре специальности/курса",
        "program/sınıf filtresinde hesaplanmaz",
    ),
    (C, "kampaniya davam edir"): ("campaign ongoing", "кампания идёт", "kampanya devam ediyor"),
    (C, "müəllim axtar…"): ("search teacher…", "поиск преподавателя…", "öğretim üyesi ara…"),
    (C, "qrup gizlidir (n &lt; k və ya tamamlayıcı qayda) — qrafikdə göstərilmir."): (
        "groups hidden (n &lt; k or complementary rule) — not shown in the chart.",
        "групп скрыто (n &lt; k или правило дополнения) — на графике не показаны.",
        "grup gizli (n &lt; k veya tamamlayıcı kural) — grafikte gösterilmiyor.",
    ),
    (C, "söz və ya ifadə…"): ("word or phrase…", "слово или фраза…", "kelime veya ifade…"),
    (C, "uyğun"): ("matches", "совпадений", "eşleşme"),
    (C, "xeyr"): ("no", "нет", "hayır"),
    (C, "yoxdur"): ("none", "нет", "yok"),
    (C, "yüksək"): ("higher", "выше", "yüksek"),
    (C, "«Razı» payı"): ("“Agree” share", "Доля «согласен»", "«Katılıyorum» oranı"),
    (C, "«Razı» payı (%)"): ("“Agree” share (%)", "Доля «согласен» (%)", "«Katılıyorum» oranı (%)"),
    (C, "«razıyam» və «tamamilə razıyam»"): (
        "“agree” and “strongly agree”",
        "«согласен» и «полностью согласен»",
        "«katılıyorum» ve «kesinlikle katılıyorum»",
    ),
    (C, "Çap et"): ("Print", "Печать", "Yazdır"),
    (C, "Çap versiyası"): ("Print version", "Версия для печати", "Yazdırma sürümü"),
    (C, "Öyrənmə nəticəsi"): ("Learning outcome", "Результат обучения", "Öğrenme çıktısı"),
    (C, "Ümumi bal"): ("Overall score", "Общий балл", "Genel puan"),
    (C, "Ümumi bal (1–10)"): ("Overall score (1–10)", "Общий балл (1–10)", "Genel puan (1–10)"),
    (C, "Ümumi baxış"): ("Overview", "Обзор", "Genel bakış"),
    (C, "Ümumi bölmə"): ("General section", "Общий раздел", "Genel bölüm"),
    (C, "Ümumi bölmə cavabları"): ("General section responses", "Ответы общего раздела", "Genel bölüm yanıtları"),
    (C, "Ümumi bölmə göstəriciləri"): (
        "General section indicators",
        "Показатели общего раздела",
        "Genel bölüm göstergeleri",
    ),
    (C, "Ümumi bölmənin bölgü qrafiki; eyni rəqəmlər aşağıdakı cədvəldədir."): (
        "General section breakdown chart; the same figures are in the table below.",
        "График разбивки общего раздела; те же данные — в таблице ниже.",
        "Genel bölüm dağılım grafiği; aynı rakamlar aşağıdaki tablodadır.",
    ),
    (C, "Ümumi məmnunluq"): ("Overall satisfaction", "Общая удовлетворённость", "Genel memnuniyet"),
    (C, "Ümumi məmnunluq (1–5)"): (
        "Overall satisfaction (1–5)",
        "Общая удовлетворённость (1–5)",
        "Genel memnuniyet (1–5)",
    ),
    (C, "Ümumi təkliflər"): ("General suggestions", "Общие предложения", "Genel öneriler"),
    (C, "ümumi bölmə: %(n)s"): ("general section: %(n)s", "общий раздел: %(n)s", "genel bölüm: %(n)s"),
    (
        C,
        "İlk %(shown)s təklif göstərilir (cəmi %(total)s) — filtr panelindəki «Şərhlərdə axtar» ilə daraldın.",
    ): (
        "The first %(shown)s suggestions are shown (of %(total)s) — narrow them with “Search comments” in the filter bar.",
        "Показаны первые %(shown)s предложений (всего %(total)s) — сузьте через «Поиск в комментариях» в панели "
        "фильтров.",
        "İlk %(shown)s öneri gösteriliyor (toplam %(total)s) — filtre panelindeki «Yorumlarda ara» ile daraltın.",
    ),
    (C, "İxrac"): ("Export", "Экспорт", "Dışa aktar"),
    (C, "İxtisas"): ("Programme", "Специальность", "Program"),
    (C, "İxtisaslar"): ("Programmes", "Специальности", "Programlar"),
    (C, "İş yükü"): ("Workload", "Нагрузка", "Ders yükü"),
    (C, "Şərhlər yalnız cavab sayı anonimlik həddini keçəndə göstərilir."): (
        "Comments are shown only when the number of responses reaches the anonymity threshold.",
        "Комментарии показываются, только если число ответов достигает порога анонимности.",
        "Yorumlar yalnızca yanıt sayısı anonimlik eşiğine ulaştığında gösterilir.",
    ),
    (C, "Şərhlərdə axtar"): ("Search comments", "Поиск в комментариях", "Yorumlarda ara"),
    (C, "şərhlərdə axtar…"): ("search comments…", "поиск в комментариях…", "yorumlarda ara…"),
    (C, "Ədalətli qiymətləndirmə"): ("Fair assessment", "Справедливое оценивание", "Adil değerlendirme"),
    (C, "Əhatə"): ("Scope", "Область", "Kapsam"),
    (C, "Əlçatanlıq"): ("Availability", "Доступность", "Ulaşılabilirlik"),
    (C, "Ən aşağı %(n)s"): ("Bottom %(n)s", "Худшие %(n)s", "En düşük %(n)s"),
    (C, "Ən yüksək %(n)s"): ("Top %(n)s", "Лучшие %(n)s", "En yüksek %(n)s"),
    (C, "Ən çox işlənən sözlər"): ("Most frequent words", "Самые частые слова", "En sık geçen kelimeler"),
    (C, "Ən çox işlənən sözlər (neçə təklifdə keçir)"): (
        "Most frequent words (number of suggestions containing them)",
        "Самые частые слова (в скольких предложениях встречаются)",
        "En sık geçen kelimeler (kaç öneride geçtiği)",
    ),
    (C, "Əsas göstəricilər"): ("Key indicators", "Ключевые показатели", "Temel göstergeler"),
    (C, "Ətraflı"): ("Details", "Подробнее", "Ayrıntılar"),
    (C, "Əvvəlki"): ("Previous", "Назад", "Önceki"),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
