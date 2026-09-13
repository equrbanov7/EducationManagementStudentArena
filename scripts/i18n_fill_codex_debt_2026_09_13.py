#!/usr/bin/env python3
"""EMSArena i18n — Codex auditi P2-06: lokallaşdırma borcunun bağlanması (2026-09-13).

Nə səhv idi
-----------
`scripts/check_i18n_catalogs.py --update` baseline-i 169 (django) + 52 (djangojs)
`source_missing` və 240/125/339 (django en/ru/tr) + 9/106 (djangojs en/tr)
`identity` girişi ilə dondurmuşdu. Praktikada bu o deməkdir ki:

1. **`source_missing`** — kodda çağırılan, amma AZ kataloqunda OLMAYAN mətn.
   Dörd kataloqun heç birində olmadığı üçün EN/RU/TR ekranlarda azərbaycanca
   (snake_case açar olanda isə açarın özü — `kpi_total`) görünürdü. Mənbələr:
   «Gözləmədə olan cavablar», «Statistika», «Fənlərim» redizaynları,
   İmtahan Mərkəzinin bal köçürmə paneli, akademik qeydlər, sehrbaz JS-i.
2. **`identity`** (msgstr == msgid) üç növ idi:
   a) msgid İNGİLİS və ya TÜRK mənbədir (kod ingiliscə/türkcə yazılıb —
      `registrar.correction`, `exams.template.coding_exam`, rol icazə paneli
      JS-i, canlı imtahan lobbisi JS-i), AZ kataloqu isə onu tərcümə etməyib →
      AZ istifadəçi ingilis/türk mətn görürdü. Düzəliş: AZ (lazım olanda RU/TR)
      msgstr yazılır; bundan sonra EN/TR identity də qapı üçün borc sayılmır.
   b) msgid AZ-dır, hədəf dildə söz HƏQİQƏTƏN eynidir («Sil», «Saat», «Ad»,
      «Telefon», «Status», «ECTS», «PIN», e-poçt ünvanları) — bunlara toxunulmur,
      sayı hesabatda göstərilir.
   c) msgid AZ-dır, TR-də fərqli olmalıdır («Jurnal» → «Yoklama defteri»,
      «Blokla» → «Engelle», «Yer limiti» → «Kontenjan») — düzəldilir.
3. Venv-dən sızmış kitabxana sətirləri (click/argparse/qpid/httpx: «Aborted!»,
   «Missing parameter» …) — kodda işlənmir, dörd kataloqda da identity-dir,
   tərcüməsinin runtime-a təsiri sıfırdır. Onlara toxunulmur (hesabatda ayrıca).

Mexanizm
--------
`makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silir). Skript kataloqu boş
sətirlə ayrılmış bloklara bölür, `(msgctxt, msgid)` açarı ilə indeksləyir və:
- ENTRIES: kataloqda olmayan girişi tək-sətirli blok kimi əlavə edir (az üçün
  msgstr = `az` verilibsə o, yoxsa msgid-in özü);
- FIXES: mövcud girişin msgstr-ini (çoxsətirli/bükülmüş olsa da) dəyişir.
İdempotentdir — ikinci icra heç nə dəyişmir. Bükülmüş (`msgid ""` + davam
sətirləri) girişlər də tanınır — köhnə fill skriptlərinin tək-sətirli axtarışı
belə girişi «yoxdur» sayıb DUBLİKAT yaradardı (msgfmt xətası).

İstifadə:  python scripts/i18n_fill_codex_debt_2026_09_13.py
           python manage.py compilemessages -l az -l en -l ru -l tr
           python scripts/check_i18n_catalogs.py --update
"""

from __future__ import annotations

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

PAX = "accounts.pending_answers"
STAT = "profile.statistics"
SUBJ = "profile.subjects"
ESE = "registrar.exam_score_entry"
REC = "registrar.records"

# ── 1. ƏLAVƏ: kodda çağırılan, AZ kataloqunda olmayan msgid-lər ─────────────
# domen → ctx → msgid → {az?, en, ru, tr}. `az` yalnız msgid AZ mətn OLMAYANDA
# (snake_case açar, ingilis/türk mənbə) verilir.
ENTRIES = {
    "django": {
        "": {
            "Hələ zal yaradılmayıb.": {
                "en": "No halls have been created yet.",
                "ru": "Залы ещё не созданы.",
                "tr": "Henüz salon oluşturulmadı.",
            },
            "süzgəcə uyğun": {"en": "matching the filter", "ru": "по фильтру", "tr": "filtreye uyan"},
        },
        PAX: {
            "Göstərilir: <strong>%(count)s</strong> iş": {
                "en": "Showing: <strong>%(count)s</strong> submissions",
                "ru": "Показано: <strong>%(count)s</strong> работ",
                "tr": "Gösterilen: <strong>%(count)s</strong> çalışma",
            },
            "Növ üzrə süz": {"en": "Filter by type", "ru": "Фильтр по типу", "tr": "Türe göre filtrele"},
            (
                "Təhvil verdiyiniz, lakin nəticəsi hələ açılmamış işlər. Müəllim yoxlayıb təsdiqləyəndən sonra "
                "nəticə «Nəticələrim» bölməsində görünür."
            ): {
                "en": (
                    "Work you have submitted whose result has not been released yet. Once the teacher reviews "
                    "and confirms it, the result appears in the “My results” section."
                ),
                "ru": (
                    "Сданные вами работы, результат которых ещё не открыт. После проверки и подтверждения "
                    "преподавателем результат появится в разделе «Мои результаты»."
                ),
                "tr": (
                    "Teslim ettiğiniz ancak sonucu henüz açıklanmamış çalışmalar. Öğretmen inceleyip "
                    "onayladıktan sonra sonuç «Sonuçlarım» bölümünde görünür."
                ),
            },
            "action_open_results": {
                "az": "Nəticələrimə keç",
                "en": "Open my results",
                "ru": "Открыть мои результаты",
                "tr": "Sonuçlarımı aç",
            },
            "empty_all_checked_body": {
                "az": "Bütün işləriniz yoxlanılıb — yeni nəticələr «Nəticələrim» bölməsindədir.",
                "en": "All your submissions have been reviewed — new results are in the “My results” section.",
                "ru": "Все ваши работы проверены — новые результаты в разделе «Мои результаты».",
                "tr": "Tüm çalışmalarınız incelendi — yeni sonuçlar «Sonuçlarım» bölümünde.",
            },
            "empty_filtered_action": {
                "az": "Süzgəci sıfırla",
                "en": "Reset filter",
                "ru": "Сбросить фильтр",
                "tr": "Filtreyi sıfırla",
            },
            "empty_filtered_body": {
                "az": "Seçilmiş növ və ya axtarış üzrə gözləmədə olan iş yoxdur. Süzgəci dəyişin və ya sıfırlayın.",
                "en": "There are no pending submissions for the selected type or search. Change or reset the filter.",
                "ru": "По выбранному типу или запросу нет работ в ожидании. Измените или сбросьте фильтр.",
                "tr": "Seçilen tür veya aramaya göre bekleyen çalışma yok. Filtreyi değiştirin veya sıfırlayın.",
            },
            "empty_filtered_title": {
                "az": "Süzgəcə uyğun iş tapılmadı",
                "en": "No submissions match the filter",
                "ru": "Нет работ, соответствующих фильтру",
                "tr": "Filtreye uyan çalışma bulunamadı",
            },
            "filter_label_type": {"az": "Növ", "en": "Type", "ru": "Тип", "tr": "Tür"},
            "kpi_coursework_note": {
                "az": "kurs işləri",
                "en": "coursework submissions",
                "ru": "курсовые работы",
                "tr": "kurs işi teslimleri",
            },
            "kpi_free_work_note": {
                "az": "sərbəst iş təqdimatları",
                "en": "independent work submissions",
                "ru": "сдачи самостоятельных работ",
                "tr": "serbest çalışma teslimleri",
            },
            "kpi_lab_note": {
                "az": "laboratoriya işləri",
                "en": "lab work submissions",
                "ru": "лабораторные работы",
                "tr": "laboratuvar çalışmaları",
            },
            "kpi_total": {"az": "Cəmi", "en": "Total", "ru": "Всего", "tr": "Toplam"},
            "kpi_total_note": {
                "az": "bütün növlər üzrə",
                "en": "across all types",
                "ru": "по всем типам",
                "tr": "tüm türler genelinde",
            },
            "legend_pending": {
                "az": "Gözləyir — müəllim hələ yoxlamağa başlamayıb",
                "en": "Pending — the teacher has not started reviewing yet",
                "ru": "Ожидает — преподаватель ещё не начал проверку",
                "tr": "Bekliyor — öğretmen henüz incelemeye başlamadı",
            },
            "legend_reviewing": {
                "az": "Yoxlanılır — müəllim işi nəzərdən keçirir",
                "en": "Under review — the teacher is reviewing the submission",
                "ru": "Проверяется — преподаватель рассматривает работу",
                "tr": "İnceleniyor — öğretmen çalışmayı gözden geçiriyor",
            },
            "legend_title": {
                "az": "Status izahı",
                "en": "Status legend",
                "ru": "Пояснение статусов",
                "tr": "Durum açıklaması",
            },
            "meta_submitted": {"az": "Təhvil verilib:", "en": "Submitted:", "ru": "Сдано:", "tr": "Teslim edildi:"},
            "type_exam": {"az": "İmtahan", "en": "Exam", "ru": "Экзамен", "tr": "Sınav"},
        },
        STAT: {
            "AI xülasəsi": {"en": "AI summary", "ru": "AI-сводка", "tr": "AI özeti"},
            "Bu rol üçün statistika əhatəsi təyin edilməyib.": {
                "en": "No statistics scope is defined for this role.",
                "ru": "Для этой роли не задана область статистики.",
                "tr": "Bu rol için istatistik kapsamı tanımlanmamış.",
            },
            "Bütün dövrlər üzrə.": {
                "en": "Across all periods.",
                "ru": "За все периоды.",
                "tr": "Tüm dönemler genelinde.",
            },
            "Cari akademik vəziyyətiniz: kredit, ÜOMG, davamiyyət və imtahan nəticələri.": {
                "en": "Your current academic standing: credits, GPA, attendance and exam results.",
                "ru": "Ваше текущее академическое состояние: кредиты, GPA, посещаемость и результаты экзаменов.",
                "tr": "Güncel akademik durumunuz: kredi, GNO, devam ve sınav sonuçları.",
            },
            "Cari dövrdə fənləriniz, tələbələriniz, jurnal və imtahan göstəriciləriniz.": {
                "en": "Your subjects, students, journal and exam indicators for the current period.",
                "ru": "Ваши предметы, студенты, показатели журнала и экзаменов за текущий период.",
                "tr": "Güncel dönemde dersleriniz, öğrencileriniz, yoklama defteri ve sınav göstergeleriniz.",
            },
            "Cəhdlər": {"en": "Attempts", "ru": "Попытки", "tr": "Denemeler"},
            "Dövr: %(period)s (%(start)s – %(end)s) — fəaliyyət göstəriciləri bu aralığa aiddir.": {
                "en": "Period: %(period)s (%(start)s – %(end)s) — activity indicators refer to this range.",
                "ru": "Период: %(period)s (%(start)s – %(end)s) — показатели активности относятся к этому диапазону.",
                "tr": "Dönem: %(period)s (%(start)s – %(end)s) — etkinlik göstergeleri bu aralığa aittir.",
            },
            "Göndərişlər (CSV)": {"en": "Submissions (CSV)", "ru": "Отправки (CSV)", "tr": "Gönderimler (CSV)"},
            # Codex audit §7 (2026-09-13) — rol-aware göstərici ixracı düyməsi (paralel agent əlavə edib).
            "Göstəricilər (CSV)": {"en": "Indicators (CSV)", "ru": "Показатели (CSV)", "tr": "Göstergeler (CSV)"},
            "Göstərilən göstəricilər üzrə xülasə yaradın.": {
                "en": "Generate a summary of the displayed indicators.",
                "ru": "Создайте сводку по отображаемым показателям.",
                "tr": "Gösterilen göstergeler için özet oluşturun.",
            },
            "Növbəti": {"en": "Next", "ru": "Далее", "tr": "Sonraki"},
            "Platforma üzrə göstəricilər; təşkilat seçərək daraltmaq olar.": {
                "en": "Platform-wide indicators; narrow them down by selecting an organization.",
                "ru": "Показатели по всей платформе; их можно сузить, выбрав организацию.",
                "tr": "Platform genelindeki göstergeler; kurum seçerek daraltabilirsiniz.",
            },
            "Seçilmiş aralıq: %(start)s – %(end)s.": {
                "en": "Selected range: %(start)s – %(end)s.",
                "ru": "Выбранный диапазон: %(start)s – %(end)s.",
                "tr": "Seçilen aralık: %(start)s – %(end)s.",
            },
            (
                "Statistika əhatəsi analitika icazəsi olan rola bağlıdır — rol təyinatınızı təşkilat "
                "administratoru ilə dəqiqləşdirin."
            ): {
                "en": (
                    "The statistics scope is tied to a role with analytics permission — check your role "
                    "assignment with the organization administrator."
                ),
                "ru": (
                    "Область статистики привязана к роли с правом на аналитику — уточните назначение роли "
                    "у администратора организации."
                ),
                "tr": (
                    "İstatistik kapsamı, analitik izni olan bir role bağlıdır — rol atamanızı kurum "
                    "yöneticisiyle netleştirin."
                ),
            },
            "Struktur vahidinizin (fakültə / kafedra / qruplar) cari dövr üzrə mənzərəsi.": {
                "en": "An overview of your structural unit (faculty / department / groups) for the current period.",
                "ru": "Обзор вашего структурного подразделения (факультет / кафедра / группы) за текущий период.",
                "tr": "Yapısal biriminizin (fakülte / bölüm / gruplar) güncel dönem görünümü.",
            },
            "Səhifələr": {"en": "Pages", "ru": "Страницы", "tr": "Sayfalar"},
            "Təşkilat": {"en": "Organization", "ru": "Организация", "tr": "Kurum"},
            "Təşkilatlar": {"en": "Organizations", "ru": "Организации", "tr": "Kurumlar"},
            "Təşkilatın cari dövr üzrə mənzərəsi: üzvlər, tələbələr, jurnal, sillabus, dərs yükü, imtahanlar.": {
                "en": (
                    "The organization's overview for the current period: members, students, journal, "
                    "syllabus, teaching load, exams."
                ),
                "ru": (
                    "Обзор организации за текущий период: участники, студенты, журнал, силлабус, "
                    "учебная нагрузка, экзамены."
                ),
                "tr": (
                    "Kurumun güncel dönem görünümü: üyeler, öğrenciler, yoklama defteri, ders izlencesi, "
                    "ders yükü, sınavlar."
                ),
            },
            "Xülasə alınmadı. Yenidən cəhd edin.": {
                "en": "The summary could not be generated. Try again.",
                "ru": "Не удалось получить сводку. Попробуйте ещё раз.",
                "tr": "Özet alınamadı. Yeniden deneyin.",
            },
            "Xülasə yarat": {"en": "Generate summary", "ru": "Создать сводку", "tr": "Özet oluştur"},
            "Üzvlər": {"en": "Members", "ru": "Участники", "tr": "Üyeler"},
            "İmtahan mərkəzinin dövr üzrə göstəriciləri: imtahanlar, cəhdlər, apellyasiya, zallar.": {
                "en": "The exam centre's indicators for the period: exams, attempts, appeals, halls.",
                "ru": "Показатели экзаменационного центра за период: экзамены, попытки, апелляции, залы.",
                "tr": "Sınav merkezinin dönem göstergeleri: sınavlar, denemeler, itirazlar, salonlar.",
            },
            "İmtahanlar": {"en": "Exams", "ru": "Экзамены", "tr": "Sınavlar"},
            "Əvvəlki": {"en": "Previous", "ru": "Назад", "tr": "Önceki"},
        },
        SUBJ: {
            "Akademik kontekst": {"en": "Academic context", "ru": "Академический контекст", "tr": "Akademik bağlam"},
            "Akademik qeydiniz hələ yaradılmayıb": {
                "en": "Your academic record has not been created yet",
                "ru": "Ваша академическая запись ещё не создана",
                "tr": "Akademik kaydınız henüz oluşturulmamış",
            },
            "Başqa dövrün aktiv qeydiyyatı": {
                "en": "Active enrollment in another period",
                "ru": "Активная запись в другом периоде",
                "tr": "Başka bir dönemin etkin kaydı",
            },
            (
                "Bu semestr qeydiyyatda olduğunuz fənlər — giriş balı, davamiyyət və imtahana buraxılış "
                "vəziyyəti bir yerdə."
            ): {
                "en": (
                    "The subjects you are enrolled in this semester — entry score, attendance and exam "
                    "admission status in one place."
                ),
                "ru": (
                    "Предметы, на которые вы записаны в этом семестре — входной балл, посещаемость и допуск "
                    "к экзамену в одном месте."
                ),
                "tr": "Bu dönem kayıtlı olduğunuz dersler — giriş puanı, devam ve sınava giriş durumu bir arada.",
            },
            "Giriş balı": {"en": "Entry score", "ru": "Входной балл", "tr": "Giriş puanı"},
            (
                "Giriş balı = davamiyyət + sərbəst iş + cari qiymətləndirmə (imtahana qədər toplanan hissə); "
                "yekun bal = giriş balı + yekun imtahan."
            ): {
                "en": (
                    "Entry score = attendance + independent work + current assessment (the part accumulated "
                    "before the exam); final score = entry score + final exam."
                ),
                "ru": (
                    "Входной балл = посещаемость + самостоятельная работа + текущее оценивание (часть, "
                    "набранная до экзамена); итоговый балл = входной балл + итоговый экзамен."
                ),
                "tr": (
                    "Giriş puanı = devam + serbest çalışma + güncel değerlendirme (sınava kadar toplanan "
                    "kısım); nihai puan = giriş puanı + final sınavı."
                ),
            },
            "Kredit yalnız keçilmiş fənlərdən toplanır; «davam edən» — hələ yekunlaşmamış cari fənlərin krediti.": {
                "en": (
                    "Credits are earned only from passed subjects; “in progress” is the credit of current "
                    "subjects that are not finalised yet."
                ),
                "ru": (
                    "Кредиты начисляются только за сданные предметы; «в процессе» — кредиты текущих предметов, "
                    "которые ещё не завершены."
                ),
                "tr": (
                    "Kredi yalnızca geçilen derslerden toplanır; «devam eden» — henüz sonuçlanmamış güncel "
                    "derslerin kredisidir."
                ),
            },
            (
                "Qeydiyyat semestr açılışında dekanlıq tərəfindən aparılır. Fənləriniz görünmürsə, tyutor və ya "
                "dekanlığa müraciət edin."
            ): {
                "en": (
                    "Enrollment is done by the dean's office at the start of the semester. If your subjects are "
                    "not shown, contact your tutor or the dean's office."
                ),
                "ru": (
                    "Запись проводит деканат в начале семестра. Если ваши предметы не отображаются, обратитесь "
                    "к тьютору или в деканат."
                ),
                "tr": (
                    "Kayıt, dönem başında dekanlık tarafından yapılır. Dersleriniz görünmüyorsa danışmanınıza "
                    "veya dekanlığa başvurun."
                ),
            },
            "Qiymətləndirmə komponentləri": {
                "en": "Assessment components",
                "ru": "Компоненты оценивания",
                "tr": "Değerlendirme bileşenleri",
            },
            "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Dönem"},
            "Status nişanları": {"en": "Status badges", "ru": "Значки статусов", "tr": "Durum rozetleri"},
            "İmtahan cəhdləri": {"en": "Exam attempts", "ru": "Попытки экзамена", "tr": "Sınav denemeleri"},
        },
        ESE: {
            (
                "Artıq yazılmış balı dəyişirsiniz — sahibin qaydası ilə səbəb, qeyd və skan edilmiş sənəd üçü də "
                "məcburidir. Hər dəyişən sətir eyni səbəb və qeydlə audit olunur."
            ): {
                "en": (
                    "You are changing a score that has already been recorded — by the owner's rule, a reason, "
                    "a note and a scanned document are all three mandatory. Every changed row is audited with "
                    "the same reason and note."
                ),
                "ru": (
                    "Вы изменяете уже выставленный балл — по правилу владельца обязательны все три: причина, "
                    "примечание и отсканированный документ. Каждая изменённая строка аудируется с той же "
                    "причиной и примечанием."
                ),
                "tr": (
                    "Zaten girilmiş bir puanı değiştiriyorsunuz — sahibin kuralına göre gerekçe, not ve "
                    "taranmış belge üçü de zorunludur. Değişen her satır aynı gerekçe ve notla denetlenir."
                ),
            },
            "Bal daxiletmə üsulu": {
                "en": "Score entry method",
                "ru": "Способ ввода баллов",
                "tr": "Puan giriş yöntemi",
            },
            "Bal tarixçəsi": {"en": "Score history", "ru": "История баллов", "tr": "Puan geçmişi"},
            "Ballar sistemə yazılsın? Yeni ballar sərbəst yazılır; dəyişdirilən ballar səbəb, qeyd və skan ilə audit olunur.": {
                "en": (
                    "Record the scores in the system? New scores are recorded freely; changed scores are "
                    "audited with a reason, a note and a scan."
                ),
                "ru": (
                    "Записать баллы в систему? Новые баллы записываются свободно; изменённые баллы аудируются "
                    "с причиной, примечанием и сканом."
                ),
                "tr": (
                    "Puanlar sisteme yazılsın mı? Yeni puanlar serbestçe yazılır; değiştirilen puanlar "
                    "gerekçe, not ve taramayla denetlenir."
                ),
            },
            "Balları fayldan yüklə": {
                "en": "Upload scores from a file",
                "ru": "Загрузить баллы из файла",
                "tr": "Puanları dosyadan yükle",
            },
            "Balları sistemə yaz": {
                "en": "Record scores in the system",
                "ru": "Записать баллы в систему",
                "tr": "Puanları sisteme yaz",
            },
            "Boş buraxılan sahə toxunulmur. İlk daxiletmə sərbəstdir; artıq yazılmış balı dəyişmək təqdimatlıdır.": {
                "en": (
                    "A field left empty is not touched. The first entry is free; changing an already recorded "
                    "score requires a submission."
                ),
                "ru": (
                    "Пустое поле не затрагивается. Первый ввод свободный; изменение уже выставленного балла "
                    "требует представления."
                ),
                "tr": (
                    "Boş bırakılan alana dokunulmaz. İlk giriş serbesttir; zaten girilmiş puanı değiştirmek "
                    "belge gerektirir."
                ),
            },
            "Bu açılış üzrə hələ köçürmə olmayıb.": {
                "en": "No transfer has been made for this offering yet.",
                "ru": "По этому открытию переносов ещё не было.",
                "tr": "Bu açılış için henüz aktarım yapılmadı.",
            },
            "Bu semestrdə açılışı olan qrup yoxdur.": {
                "en": "There is no group with an offering in this semester.",
                "ru": "В этом семестре нет группы с открытием.",
                "tr": "Bu dönemde açılışı olan grup yok.",
            },
            "Bu seçim üçün açılış tapılmadı.": {
                "en": "No offering found for this selection.",
                "ru": "Для этого выбора открытие не найдено.",
                "tr": "Bu seçim için açılış bulunamadı.",
            },
            "Bu tələbənin imtahan balı üzrə bütün daxiletmələr, köçürmə partiyaları və (varsa) rəqəmsal cəhdləri.": {
                "en": "All entries, transfer batches and (if any) digital attempts for this student's exam score.",
                "ru": (
                    "Все вводы, партии переноса и (при наличии) цифровые попытки по экзаменационному баллу "
                    "этого студента."
                ),
                "tr": (
                    "Bu öğrencinin sınav puanına ilişkin tüm girişler, aktarım partileri ve (varsa) dijital "
                    "denemeleri."
                ),
            },
            "Bəli, sistemə yaz": {
                "en": "Yes, record in the system",
                "ru": "Да, записать в систему",
                "tr": "Evet, sisteme yaz",
            },
            "CSV şablon": {"en": "CSV template", "ru": "Шаблон CSV", "tr": "CSV şablonu"},
            "Cari bal": {"en": "Current score", "ru": "Текущий балл", "tr": "Mevcut puan"},
            "Daxiletmələr": {"en": "Entries", "ru": "Вводы", "tr": "Girişler"},
            "Default: açılışın müəllimi; fərqlidirsə dəyişin.": {
                "en": "Default: the offering's teacher; change it if different.",
                "ru": "По умолчанию: преподаватель открытия; измените, если отличается.",
                "tr": "Varsayılan: açılışın öğretmeni; farklıysa değiştirin.",
            },
            "Doldurulmuş faylı yükləyib yoxlayın": {
                "en": "Upload and check the completed file",
                "ru": "Загрузите и проверьте заполненный файл",
                "tr": "Doldurulmuş dosyayı yükleyip kontrol edin",
            },
            "Doldurulmuş şablonu endirin": {
                "en": "Download the pre-filled template",
                "ru": "Скачайте заполненный шаблон",
                "tr": "Doldurulmuş şablonu indirin",
            },
            "Dəyişdirilmiş bal yoxdur — yadda saxlamağa ehtiyac yoxdur.": {
                "en": "No score has been changed — nothing to save.",
                "ru": "Изменённых баллов нет — сохранять нечего.",
                "tr": "Değiştirilen puan yok — kaydetmeye gerek yok.",
            },
            "Dəyişdirilən bal üçün səbəb, qeyd və skan edilmiş sənəd (vərəq məlumatlarında) tələb olunur.": {
                "en": "A reason, a note and a scanned document (in the sheet details) are required for a changed score.",
                "ru": (
                    "Для изменённого балла требуются причина, примечание и отсканированный документ "
                    "(в данных ведомости)."
                ),
                "tr": "Değiştirilen puan için gerekçe, not ve taranmış belge (çizelge bilgilerinde) gereklidir.",
            },
            "Dəyişiklikləri sıfırla": {
                "en": "Reset changes",
                "ru": "Сбросить изменения",
                "tr": "Değişiklikleri sıfırla",
            },
            "Emal olunur…": {"en": "Processing…", "ru": "Обработка…", "tr": "İşleniyor…"},
            "Fayl emal olunmadı — yenidən cəhd edin.": {
                "en": "The file could not be processed — try again.",
                "ru": "Файл не обработан — попробуйте ещё раз.",
                "tr": "Dosya işlenemedi — yeniden deneyin.",
            },
            "Faylda artıq yazılmış balı dəyişən sətirlər var — səbəb, qeyd və skan (vərəq məlumatlarında) tələb olunur.": {
                "en": (
                    "The file contains rows that change already recorded scores — a reason, a note and a scan "
                    "(in the sheet details) are required."
                ),
                "ru": (
                    "В файле есть строки, изменяющие уже выставленные баллы — требуются причина, примечание "
                    "и скан (в данных ведомости)."
                ),
                "tr": (
                    "Dosyada zaten girilmiş puanı değiştiren satırlar var — gerekçe, not ve tarama (çizelge "
                    "bilgilerinde) gereklidir."
                ),
            },
            "Faylı bura sürüşdürün və ya seçmək üçün klikləyin": {
                "en": "Drag the file here or click to choose",
                "ru": "Перетащите файл сюда или нажмите, чтобы выбрать",
                "tr": "Dosyayı buraya sürükleyin veya seçmek için tıklayın",
            },
            "Fənn → Qrup": {"en": "Subject → Group", "ru": "Предмет → Группа", "tr": "Ders → Grup"},
            "Hələ daxiletmə yoxdur.": {"en": "No entries yet.", "ru": "Вводов пока нет.", "tr": "Henüz giriş yok."},
            "Hər yadda saxlama / fayl tətbiqi bir vərəq kimi qeyd olunur: tarix, müəllim, protokol və nəticə.": {
                "en": "Every save / file application is recorded as a sheet: date, teacher, protocol and result.",
                "ru": (
                    "Каждое сохранение / применение файла записывается как ведомость: дата, преподаватель, "
                    "протокол и результат."
                ),
                "tr": (
                    "Her kaydetme / dosya uygulaması bir çizelge olarak kaydedilir: tarih, öğretmen, tutanak "
                    "ve sonuç."
                ),
            },
            "Kim": {"en": "Who", "ru": "Кто", "tr": "Kaydeden"},
            "Köçürmə": {"en": "Transfer", "ru": "Перенос", "tr": "Aktarım"},
            "Köçürmə addımları": {"en": "Transfer steps", "ru": "Шаги переноса", "tr": "Aktarım adımları"},
            "Köçürmə partiyaları": {"en": "Transfer batches", "ru": "Партии переноса", "tr": "Aktarım partileri"},
            "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretmen"},
            "Mənbə": {"en": "Source", "ru": "Источник", "tr": "Kaynak"},
            "Nəzarətçi": {"en": "Invigilator", "ru": "Наблюдатель", "tr": "Gözetmen"},
            "Protokol / vərəq №": {
                "en": "Protocol / sheet No.",
                "ru": "Протокол / ведомость №",
                "tr": "Tutanak / çizelge No",
            },
            "Protokol №": {"en": "Protocol No.", "ru": "Протокол №", "tr": "Tutanak No"},
            "Qrup → Fənn": {"en": "Group → Subject", "ru": "Группа → Предмет", "tr": "Grup → Ders"},
            "Qrupsuz açılışlar «Fənn → Qrup» sırasında görünür.": {
                "en": "Offerings without a group are shown in the “Subject → Group” order.",
                "ru": "Открытия без группы отображаются в порядке «Предмет → Группа».",
                "tr": "Grupsuz açılışlar «Ders → Grup» sırasında görünür.",
            },
            "Quru icra nəticəsi — heç nə yazılmayıb": {
                "en": "Dry-run result — nothing has been written",
                "ru": "Результат сухого прогона — ничего не записано",
                "tr": "Kuru çalışma sonucu — hiçbir şey yazılmadı",
            },
            "Rəqəmsal cəhdlər": {"en": "Digital attempts", "ru": "Цифровые попытки", "tr": "Dijital denemeler"},
            "Seçim sırası": {"en": "Selection order", "ru": "Порядок выбора", "tr": "Seçim düzeni"},
            "Siyahını yenilə": {"en": "Refresh the list", "ru": "Обновить список", "tr": "Listeyi yenile"},
            "Skan": {"en": "Scan", "ru": "Скан", "tr": "Tarama"},
            "Skan edilmiş protokol / vərəq (PDF və ya şəkil)": {
                "en": "Scanned protocol / sheet (PDF or image)",
                "ru": "Отсканированный протокол / ведомость (PDF или изображение)",
                "tr": "Taranmış tutanak / çizelge (PDF veya görsel)",
            },
            "Skan seçilib": {"en": "Scan selected", "ru": "Скан выбран", "tr": "Tarama seçildi"},
            "Skan seçilməyib": {"en": "No scan selected", "ru": "Скан не выбран", "tr": "Tarama seçilmedi"},
            "Sütunlar": {"en": "Columns", "ru": "Столбцы", "tr": "Kolonlar"},
            "Sətir": {"en": "Row", "ru": "Строка", "tr": "Satır"},
            "Sətir seçilməyib.": {"en": "No row selected.", "ru": "Строка не выбрана.", "tr": "Satır seçilmedi."},
            "Tarixçə": {"en": "History", "ru": "История", "tr": "Geçmiş"},
            "Tətbiq et — balları sistemə yaz": {
                "en": "Apply — record the scores in the system",
                "ru": "Применить — записать баллы в систему",
                "tr": "Uygula — puanları sisteme yaz",
            },
            "Tətbiq nəticəsi": {"en": "Application result", "ru": "Результат применения", "tr": "Uygulama sonucu"},
            "Vəziyyət": {"en": "State", "ru": "Состояние", "tr": "Durum"},
            "XLSX şablon": {"en": "XLSX template", "ru": "Шаблон XLSX", "tr": "XLSX şablonu"},
            "Xətalı bal var — 0 ilə maksimum arasında tam ədəd yazın.": {
                "en": "There is an invalid score — enter a whole number between 0 and the maximum.",
                "ru": "Есть некорректный балл — введите целое число от 0 до максимума.",
                "tr": "Hatalı puan var — 0 ile maksimum arasında tam sayı yazın.",
            },
            "Yazılacaq balların icmalı. Dəyişdirilən ballar səbəb, qeyd və skan ilə audit olunur.": {
                "en": "Summary of the scores to be recorded. Changed scores are audited with a reason, a note and a scan.",
                "ru": "Сводка баллов к записи. Изменённые баллы аудируются с причиной, примечанием и сканом.",
                "tr": "Yazılacak puanların özeti. Değiştirilen puanlar gerekçe, not ve taramayla denetlenir.",
            },
            "Yazıldı / dəyişmədi / rədd": {
                "en": "Written / unchanged / rejected",
                "ru": "Записано / без изменений / отклонено",
                "tr": "Yazıldı / değişmedi / reddedildi",
            },
            (
                "Yazılı imtahan kağız üzərində keçir — nəticəni sistemə İmtahan Mərkəzi köçürür. Qrupu və fənni "
                "seçin, vərəq məlumatlarını (tarix, müəllim, protokol) yazın, sonra balları siyahıda daxil edin "
                "və ya XLSX/CSV faylından yükləyin."
            ): {
                "en": (
                    "The written exam is taken on paper — the Exam Centre transfers the result into the system. "
                    "Select the group and the subject, fill in the sheet details (date, teacher, protocol), then "
                    "enter the scores in the list or upload them from an XLSX/CSV file."
                ),
                "ru": (
                    "Письменный экзамен проходит на бумаге — результат в систему переносит Экзаменационный "
                    "центр. Выберите группу и предмет, заполните данные ведомости (дата, преподаватель, "
                    "протокол), затем введите баллы в списке или загрузите их из файла XLSX/CSV."
                ),
                "tr": (
                    "Yazılı sınav kâğıt üzerinde yapılır — sonucu sisteme Sınav Merkezi aktarır. Grubu ve dersi "
                    "seçin, çizelge bilgilerini (tarih, öğretmen, tutanak) yazın, ardından puanları listede "
                    "girin veya XLSX/CSV dosyasından yükleyin."
                ),
            },
            "Yeni bal": {"en": "New score", "ru": "Новый балл", "tr": "Yeni puan"},
            "Yoxla (quru icra)": {
                "en": "Check (dry run)",
                "ru": "Проверить (сухой прогон)",
                "tr": "Kontrol et (kuru çalışma)",
            },
            "Yoxlama heç nə yazmır — nəticəni sətir-sətir görürsünüz.": {
                "en": "Checking writes nothing — you see the result row by row.",
                "ru": "Проверка ничего не записывает — вы видите результат построчно.",
                "tr": "Kontrol hiçbir şey yazmaz — sonucu satır satır görürsünüz.",
            },
            "Yoxlayan müəllim": {
                "en": "Examining teacher",
                "ru": "Проверяющий преподаватель",
                "tr": "Sınavı yapan öğretmen",
            },
            "alt qrupdan": {"en": "from the subgroup", "ru": "из подгруппы", "tr": "alt gruptan"},
            "bal yazılacaq": {"en": "scores to be written", "ru": "баллов будет записано", "tr": "puan yazılacak"},
            "boş": {"en": "empty", "ru": "пусто", "tr": "boş"},
            "cari imtahan balı": {
                "en": "current exam score",
                "ru": "текущий балл за экзамен",
                "tr": "mevcut sınav puanı",
            },
            "dəyişdirilib": {"en": "changed", "ru": "изменено", "tr": "değiştirildi"},
            "dəyişiklik": {"en": "change", "ru": "изменение", "tr": "değişiklik"},
            "dəyişiklik səbəb tələb edir": {
                "en": "the change requires a reason",
                "ru": "изменение требует причины",
                "tr": "değişiklik gerekçe gerektirir",
            },
            "dəyişiklik · səbəb tələb olunur": {
                "en": "change · reason required",
                "ru": "изменение · требуется причина",
                "tr": "değişiklik · gerekçe gerekli",
            },
            "eyni bal": {"en": "same score", "ru": "тот же балл", "tr": "aynı puan"},
            "fayl": {"en": "file", "ru": "файл", "tr": "dosya"},
            "faylda olmayan tələbə": {
                "en": "student not in the file",
                "ru": "студент отсутствует в файле",
                "tr": "dosyada olmayan öğrenci",
            },
            "fayldan": {"en": "from file", "ru": "из файла", "tr": "dosyadan"},
            "ilkin daxiletmə": {"en": "initial entry", "ru": "первичный ввод", "tr": "ilk giriş"},
            "imtahan": {"en": "exam", "ru": "экзамен", "tr": "sınav"},
            "nəzarətçi": {"en": "invigilator", "ru": "наблюдатель", "tr": "gözetmen"},
            "skan": {"en": "scan", "ru": "скан", "tr": "tarama"},
            "sənədli düzəliş": {
                "en": "documented correction",
                "ru": "документированное исправление",
                "tr": "belgeli düzeltme",
            },
            "sətir": {"en": "rows", "ru": "строк", "tr": "satır"},
            "sətir toxunulmur": {"en": "rows untouched", "ru": "строк не затронуто", "tr": "satıra dokunulmaz"},
            "tələbə": {"en": "students", "ru": "студентов", "tr": "öğrenci"},
            "tələbə Tələbə № (istifadəçi adı), FİN və ya Ad Soyad ilə tanınır.": {
                "en": "the student is identified by Student No. (username), FIN or full name.",
                "ru": "студент распознаётся по № студента (имени пользователя), FİN или ФИО.",
                "tr": "öğrenci, Öğrenci No (kullanıcı adı), FİN veya Ad Soyad ile tanınır.",
            },
            "vərəq skanı": {"en": "sheet scan", "ru": "скан ведомости", "tr": "çizelge taraması"},
            "xəta": {"en": "error", "ru": "ошибка", "tr": "hata"},
            "yazıldı": {"en": "written", "ru": "записано", "tr": "kaydedildi"},
            "yazılıb": {"en": "recorded", "ru": "записан", "tr": "girilmiş"},
            "yeni": {"en": "new", "ru": "новый", "tr": "yeni"},
            (
                "İlk daxiletmədə opsionaldır; artıq yazılmış balı dəyişəndə MƏCBURİDİR (səbəb və qeydlə birlikdə). "
                "Bir partiyanın bütün dəyişikliklərinə eyni skan aiddir."
            ): {
                "en": (
                    "Optional for the first entry; MANDATORY when changing an already recorded score (together "
                    "with a reason and a note). The same scan applies to all changes of one batch."
                ),
                "ru": (
                    "Необязателен при первом вводе; ОБЯЗАТЕЛЕН при изменении уже выставленного балла (вместе с "
                    "причиной и примечанием). Один скан относится ко всем изменениям партии."
                ),
                "tr": (
                    "İlk girişte isteğe bağlıdır; zaten girilmiş puanı değiştirirken ZORUNLUDUR (gerekçe ve "
                    "notla birlikte). Bir partinin tüm değişikliklerine aynı tarama aittir."
                ),
            },
            "İmtahan tarixi": {"en": "Exam date", "ru": "Дата экзамена", "tr": "Sınav tarihi"},
            "İzah": {"en": "Explanation", "ru": "Пояснение", "tr": "Açıklama"},
            (
                "Şablon bu qrupun siyahısı ilə doludur — yalnız «Bal» sütununu doldurun. Sütunların sırası "
                "sərbəstdir (başlığa görə tanınır). Ən çox %(limit)s sətir, %(size)s MB."
            ): {
                "en": (
                    "The template is pre-filled with this group's roster — fill in only the “Score” column. "
                    "Column order is free (columns are recognised by header). At most %(limit)s rows, %(size)s MB."
                ),
                "ru": (
                    "Шаблон заполнен списком этой группы — заполните только столбец «Балл». Порядок столбцов "
                    "произвольный (распознаются по заголовку). Не более %(limit)s строк, %(size)s МБ."
                ),
                "tr": (
                    "Şablon bu grubun listesiyle doludur — yalnızca «Puan» sütununu doldurun. Sütun sırası "
                    "serbesttir (başlığa göre tanınır). En fazla %(limit)s satır, %(size)s MB."
                ),
            },
            "Əvvəlcə faylı seçin.": {
                "en": "Choose a file first.",
                "ru": "Сначала выберите файл.",
                "tr": "Önce dosyayı seçin.",
            },
            "əl ilə": {"en": "manual", "ru": "вручную", "tr": "elle"},
        },
        # Python modelində ingiliscə yazılmış seçim etiketləri / meta adları.
        "registrar.exam_score_sheet_source": {
            "File import (XLSX/CSV)": {
                "az": "Fayl idxalı (XLSX/CSV)",
                "en": "File import (XLSX/CSV)",
                "ru": "Импорт файла (XLSX/CSV)",
                "tr": "Dosya içe aktarma (XLSX/CSV)",
            },
            "Manual roster entry": {
                "az": "Siyahıdan əl ilə daxiletmə",
                "en": "Manual roster entry",
                "ru": "Ручной ввод по списку",
                "tr": "Listeden elle giriş",
            },
        },
        "registrar.model.exam_score_sheet.meta": {
            "exam score sheet": {
                "az": "imtahan bal vərəqi",
                "en": "exam score sheet",
                "ru": "ведомость экзаменационных баллов",
                "tr": "sınav puan çizelgesi",
            },
            "exam score sheets": {
                "az": "imtahan bal vərəqləri",
                "en": "exam score sheets",
                "ru": "ведомости экзаменационных баллов",
                "tr": "sınav puan çizelgeleri",
            },
        },
        REC: {
            "Akademik qeyd süzgəcləri": {
                "en": "Academic record filters",
                "ru": "Фильтры академических записей",
                "tr": "Akademik kayıt filtreleri",
            },
            "Akademik qeydlər yalnız öz strukturunuz üzrə görünür — icazə üçün idarəetməyə müraciət edin.": {
                "en": "Academic records are visible only within your own structure — contact the administration for access.",
                "ru": "Академические записи видны только в рамках вашей структуры — за доступом обратитесь к администрации.",
                "tr": "Akademik kayıtlar yalnızca kendi yapınız için görünür — izin için yönetime başvurun.",
            },
            "Göstərilir": {"en": "Showing", "ru": "Показано", "tr": "Gösterilen"},
            "Siyahı yüklənmədi.": {
                "en": "The list could not be loaded.",
                "ru": "Не удалось загрузить список.",
                "tr": "Liste yüklenemedi.",
            },
            "Süzgəc üzrə ümumi mənzərə": {
                "en": "Overview for the filter",
                "ru": "Общая картина по фильтру",
                "tr": "Filtreye göre genel görünüm",
            },
            "Süzgəci genişləndirin və ya «Sıfırla» düyməsini basın.": {
                "en": "Widen the filter or press “Reset”.",
                "ru": "Расширьте фильтр или нажмите «Сбросить».",
                "tr": "Filtreyi genişletin veya «Sıfırla» düğmesine basın.",
            },
            "Səhifədə": {"en": "Per page", "ru": "На странице", "tr": "Sayfada"},
            "Tələbənin semestr üzrə nəticələrinə bax": {
                "en": "View the student's results by semester",
                "ru": "Посмотреть результаты студента по семестрам",
                "tr": "Öğrencinin dönem sonuçlarını görüntüle",
            },
            "Yoxdur": {"en": "None", "ru": "Нет", "tr": "Yok"},
            "tələbədən": {"en": "students", "ru": "студентов", "tr": "öğrenciden"},
            (
                "Öz strukturunuzdakı tələbələrin akademik nəticələri — fakültə, kafedra, ixtisas, qrup üzrə süzün "
                "və ya tələbə axtarın. Qutular seçilmiş süzgəcin TAMI üzrə, cədvəl isə yalnız görünən səhifə üzrədir."
            ): {
                "en": (
                    "Academic results of the students within your own structure — filter by faculty, department, "
                    "specialty, group, or search for a student. The tiles cover the WHOLE selected filter, the "
                    "table only the visible page."
                ),
                "ru": (
                    "Академические результаты студентов в рамках вашей структуры — фильтруйте по факультету, "
                    "кафедре, специальности, группе или найдите студента. Плитки охватывают ВЕСЬ выбранный "
                    "фильтр, таблица — только видимую страницу."
                ),
                "tr": (
                    "Kendi yapınızdaki öğrencilerin akademik sonuçları — fakülte, bölüm, program, gruba göre "
                    "filtreleyin veya öğrenci arayın. Kutular seçilen filtrenin TAMAMINI, tablo ise yalnızca "
                    "görünen sayfayı kapsar."
                ),
            },
            "Şəbəkə və ya server xətası — bir azdan yenidən cəhd edin.": {
                "en": "Network or server error — try again in a moment.",
                "ru": "Ошибка сети или сервера — попробуйте ещё раз чуть позже.",
                "tr": "Ağ veya sunucu hatası — birazdan yeniden deneyin.",
            },
            "Əməliyyat": {"en": "Action", "ru": "Действие", "tr": "İşlem"},
        },
    },
    "djangojs": {
        "": {
            "Ad": {"en": "Name", "ru": "Название", "tr": "Adı"},
            "Alıcılar": {"en": "Recipients", "ru": "Получатели", "tr": "Atananlar"},
            "Anladım": {"en": "Got it", "ru": "Понятно", "tr": "Tamam"},
            "Apellyasiya açıldıqdan sonra heç bir sual qərarsız qala bilməz. Qərar verilməmiş suallar:": {
                "en": "Once the appeal is opened, no question may be left undecided. Undecided questions:",
                "ru": "После открытия апелляции ни один вопрос не может остаться без решения. Вопросы без решения:",
                "tr": "İtiraz açıldıktan sonra hiçbir soru kararsız kalamaz. Karar verilmemiş sorular:",
            },
            "Axtar…": {"en": "Search…", "ru": "Поиск…", "tr": "Ara…"},
            "Başlama": {"en": "Start", "ru": "Начало", "tr": "Başlangıç"},
            "Başlama vaxtını seçin.": {
                "en": "Choose the start time.",
                "ru": "Укажите время начала.",
                "tr": "Başlangıç zamanını seçin.",
            },
            "Bitmə vaxtını seçin.": {
                "en": "Choose the end time.",
                "ru": "Укажите время окончания.",
                "tr": "Bitiş zamanını seçin.",
            },
            "Bu PIN-i imtahan giriş səhifəsində istifadəçi adınızla birlikdə istifadə edin.": {
                "en": "Use this PIN together with your username on the exam entry page.",
                "ru": "Используйте этот PIN вместе с именем пользователя на странице входа в экзамен.",
                "tr": "Bu PIN'i sınav giriş sayfasında kullanıcı adınızla birlikte kullanın.",
            },
            # course_panel_tabs.js: TR mətn birbaşa gettext()-ə verilib — AZ qarşılığı məcburidir.
            "Bu dersin atandığı gruplar": {
                "az": "Bu fənnin tədris olunduğu qruplar",
                "en": "Groups assigned to this subject",
                "ru": "Группы этого предмета",
                "tr": "Bu dersin atandığı gruplar",
            },
            "Bu fənnin tədris olunduğu qruplar": {
                "en": "Groups assigned to this subject",
                "ru": "Группы этого предмета",
                "tr": "Bu dersin atandığı gruplar",
            },
            "Bütün suallara qərar verin": {
                "en": "Decide on all questions",
                "ru": "Примите решение по всем вопросам",
                "tr": "Tüm sorular için karar verin",
            },
            "Cari cavablarınız yadda saxlanılıb. Ətraflı nəticəyə keçə bilərsiniz.": {
                "en": "Your current answers have been saved. You can go to the detailed result.",
                "ru": "Ваши текущие ответы сохранены. Вы можете перейти к подробному результату.",
                "tr": "Mevcut cevaplarınız kaydedildi. Ayrıntılı sonuca geçebilirsiniz.",
            },
            "Deaktiv": {"en": "Off", "ru": "Выключен", "tr": "Kapalı"},
            "Düzəlişi geri al": {
                "en": "Revert the correction",
                "ru": "Отменить исправление",
                "tr": "Düzeltmeyi geri al",
            },
            "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
            "Fənn seçilməlidir.": {
                "en": "A subject must be selected.",
                "ru": "Нужно выбрать предмет.",
                "tr": "Ders seçilmelidir.",
            },
            "Fənn yoxdur": {"en": "No subjects", "ru": "Нет предметов", "tr": "Ders yok"},
            "Fərdi tələbələr": {"en": "Individual students", "ru": "Отдельные студенты", "tr": "Bireysel öğrenciler"},
            "Geri": {"en": "Back", "ru": "Назад", "tr": "Geri dön"},
            "Hamıya açıq": {"en": "Open to everyone", "ru": "Открыт для всех", "tr": "Herkese açık"},
            "Kateqoriya": {"en": "Category", "ru": "Категория", "tr": "Kategori"},
            "Kateqoriyanı seçin.": {"en": "Choose a category.", "ru": "Выберите категорию.", "tr": "Kategori seçin."},
            "Müddət (dəq)": {"en": "Duration (min)", "ru": "Длительность (мин)", "tr": "Süre (dk)"},
            "Nəticəyə keç": {"en": "Go to the result", "ru": "Перейти к результату", "tr": "Sonuca geç"},
            "Nəzarət": {"en": "Proctoring", "ru": "Контроль", "tr": "Gözetim"},
            "PIN yalnız imtahan vaxtına yaxın görünəcək və ya imtahan mərkəzindən əldə edilir.": {
                "en": "The PIN will only be shown close to the exam time, or it can be obtained from the exam centre.",
                "ru": "PIN появится только ближе ко времени экзамена, либо его можно получить в экзаменационном центре.",
                "tr": "PIN yalnızca sınav saatine yakın görünür veya sınav merkezinden alınır.",
            },
            "Qruplar": {"en": "Groups", "ru": "Группы", "tr": "Gruplar"},
            "Salam! Suallarınızı cavablandırmağa hazıram. Necə kömək edə bilərəm?": {
                "en": "Hello! I'm ready to answer your questions. How can I help?",
                "ru": "Здравствуйте! Я готов ответить на ваши вопросы. Чем могу помочь?",
                "tr": "Merhaba! Sorularınızı yanıtlamaya hazırım. Nasıl yardımcı olabilirim?",
            },
            "Seçilmiş qrupla daxildir": {
                "en": "Included via the selected group",
                "ru": "Включён через выбранную группу",
                "tr": "Seçilen grupla dahil",
            },
            "Seçilməyib": {"en": "Not selected", "ru": "Не выбрано", "tr": "Seçilmedi"},
            "Sistemdə yalnız {n} sual var.": {
                "en": "There are only {n} questions in the system.",
                "ru": "В системе только {n} вопросов.",
                "tr": "Sistemde yalnızca {n} soru var.",
            },
            "Sual sayı": {"en": "Question count", "ru": "Число вопросов", "tr": "Soru sayısı"},
            "Səbəb": {"en": "Reason", "ru": "Причина", "tr": "Neden"},
            "Səbəb tipini seçin və izahı ən azı {min} simvol yazın.": {
                "en": "Choose the reason type and write an explanation of at least {min} characters.",
                "ru": "Выберите тип причины и напишите пояснение не короче {min} символов.",
                "tr": "Neden türünü seçin ve en az {min} karakterlik açıklama yazın.",
            },
            "Tip": {"en": "Type", "ru": "Тип", "tr": "Tür"},
            "Tələbə sayı (ümumi)": {
                "en": "Students (total)",
                "ru": "Студентов (всего)",
                "tr": "Öğrenci sayısı (toplam)",
            },
            "Tələbələr": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler"},
            "Təsdiqlə və yarat": {"en": "Confirm and create", "ru": "Подтвердить и создать", "tr": "Onayla ve oluştur"},
            "hesablanır…": {"en": "calculating…", "ru": "подсчёт…", "tr": "hesaplanıyor…"},
            "{q}-ci sualda izahı ən azı {min} simvol yazmalısınız, ya da “Apellyasiya et” düyməsini söndürməlisiniz.": {
                "en": "For question {q} you must write an explanation of at least {min} characters, or turn off the “Appeal” toggle.",
                "ru": "Для вопроса {q} нужно написать пояснение не короче {min} символов или выключить переключатель «Подать апелляцию».",
                "tr": "{q}. soruda en az {min} karakterlik açıklama yazmalı ya da «İtiraz et» düğmesini kapatmalısınız.",
            },
            (
                "{q}-ci sualda səbəb tipini seçib izahı ən azı {min} simvol yazmalısınız, ya da “Apellyasiya et” "
                "düyməsini söndürməlisiniz."
            ): {
                "en": (
                    "For question {q} you must choose the reason type and write an explanation of at least "
                    "{min} characters, or turn off the “Appeal” toggle."
                ),
                "ru": (
                    "Для вопроса {q} нужно выбрать тип причины и написать пояснение не короче {min} символов "
                    "или выключить переключатель «Подать апелляцию»."
                ),
                "tr": (
                    "{q}. soruda neden türünü seçip en az {min} karakterlik açıklama yazmalı ya da «İtiraz et» "
                    "düğmesini kapatmalısınız."
                ),
            },
            "{q}-ci sualda səbəb tipini seçməlisiniz, ya da “Apellyasiya et” düyməsini söndürməlisiniz.": {
                "en": "For question {q} you must choose the reason type, or turn off the “Appeal” toggle.",
                "ru": "Для вопроса {q} нужно выбрать тип причины или выключить переключатель «Подать апелляцию».",
                "tr": "{q}. soruda neden türünü seçmeli ya da «İtiraz et» düğmesini kapatmalısınız.",
            },
            "İmtahan adı": {"en": "Exam title", "ru": "Название экзамена", "tr": "Sınav adı"},
            "İmtahan aşağıdakı məlumatlarla yaradılıb təyin olunacaq.": {
                "en": "The exam will be created and assigned with the details below.",
                "ru": "Экзамен будет создан и назначен с указанными ниже данными.",
                "tr": "Sınav aşağıdaki bilgilerle oluşturulup atanacak.",
            },
            "İmtahan mərkəzi hələ sizə bilet təyin etməyib.": {
                "en": "The exam centre has not assigned you a ticket yet.",
                "ru": "Экзаменационный центр ещё не назначил вам билет.",
                "tr": "Sınav merkezi size henüz bilet atamadı.",
            },
            "İmtahandan çıxarıldınız": {
                "en": "You have been removed from the exam",
                "ru": "Вы отстранены от экзамена",
                "tr": "Sınavdan çıkarıldınız",
            },
            "İmtahanı təsdiqlə": {"en": "Confirm the exam", "ru": "Подтвердите экзамен", "tr": "Sınavı onayla"},
            "İmtahanın ümumi müddətini yazın.": {
                "en": "Enter the total exam duration.",
                "ru": "Укажите общую длительность экзамена.",
                "tr": "Sınavın toplam süresini yazın.",
            },
            "İmtahanınız texniki səbəblə dayandırıldı": {
                "en": "Your exam was stopped for a technical reason",
                "ru": "Ваш экзамен остановлен по технической причине",
                "tr": "Sınavınız teknik bir nedenle durduruldu",
            },
            "İşarələnmişləri ləğv et": {
                "en": "Deselect the marked",
                "ru": "Отменить выбор отмеченных",
                "tr": "İşaretlenenlerin seçimini kaldır",
            },
            "İşarələnmişləri seç": {"en": "Select the marked", "ru": "Выбрать отмеченные", "tr": "İşaretlenenleri seç"},
        },
    },
}

# ── 2. DÜZƏLİŞ: mövcud girişlərin msgstr-i ──────────────────────────────────
# domen → (ctx, msgid) → {dil: msgstr}. Üç qrup: (a) ingilis/türk mənbəli
# msgid-ə AZ (lazımsa RU/TR) qarşılığı; (b) AZ msgid-ə TR-də fərqli olmalı söz;
# (c) djangojs-də türk mənbəli rol-icazə / canlı-imtahan / AI-kurs mətnlərinə AZ.
FIXES = {
    "django": {
        # (a) ingilis mənbə — AZ kataloqu tərcümə etməmişdi
        ("", "Email"): {"az": "E-poçt"},
        ("", "Metadata"): {"az": "Metaməlumatlar", "tr": "Üstveri"},
        ("", "Review public contact form messages and reply from the official %(site_brand_name)s mailboxes."): {
            "az": "İctimai əlaqə formasından gələn mesajlara baxın və rəsmi %(site_brand_name)s poçt qutularından cavab verin.",
        },
        ("", "This marks the request as added and emails the student."): {
            "az": "Bu, sorğunu əlavə edilmiş kimi işarələyir və tələbəyə e-poçt göndərir.",
            "ru": "Это помечает запрос как добавленный и отправляет студенту письмо.",
            "tr": "Bu, talebi eklenmiş olarak işaretler ve öğrenciye e-posta gönderir.",
        },
        ("", "Too many login attempts. Please try again later."): {
            "az": "Həddindən çox giriş cəhdi. Bir azdan yenidən cəhd edin.",
            "ru": "Слишком много попыток входа. Попробуйте позже.",
            "tr": "Çok fazla giriş denemesi. Lütfen daha sonra tekrar deneyin.",
        },
        ("", "Trial"): {"az": "Sınaq", "ru": "Пробный", "tr": "Deneme"},
        ("", "[%(brand)s Contact] %(subject)s — %(name)s"): {"az": "[%(brand)s Əlaqə] %(subject)s — %(name)s"},
        ("", "Error: The two entered values do not match."): {"az": "Xəta: daxil edilən iki dəyər uyğun gəlmir."},
        ("accounts.first_login", "Email"): {"az": "E-poçt", "ru": "Эл. почта"},
        ("accounts.superadmin_org_features", "Default"): {"az": "Standart"},
        ("accounts.workload_center", "Excel import"): {"az": "Excel idxalı"},
        ("admin.verify_otp", "Please wait %(seconds)s seconds before trying again."): {
            "az": "Yenidən cəhd etməzdən əvvəl %(seconds)s saniyə gözləyin.",
            "ru": "Подождите %(seconds)s секунд, прежде чем повторить попытку.",
            "tr": "Yeniden denemeden önce %(seconds)s saniye bekleyin.",
        },
        ("ai_assistant.aria", "AI Assistant"): {"az": "AI Assistent"},
        ("appeals.template", "Reviewer workspace"): {"az": "Yoxlayanın iş sahəsi"},
        ("core.errors.csrf", "If the problem persists, make sure browser cookies are enabled."): {
            "az": "Problem davam edərsə, brauzerdə kukilərin aktiv olduğundan əmin olun.",
        },
        (
            "core.middleware.request_queue.message",
            "Server is busy processing previous requests. Please try again shortly.",
        ): {
            "az": "Server əvvəlki sorğuları emal etməklə məşğuldur. Bir azdan yenidən cəhd edin.",
            "ru": "Сервер занят обработкой предыдущих запросов. Повторите попытку чуть позже.",
            "tr": "Sunucu önceki istekleri işlemekle meşgul. Lütfen kısa süre sonra tekrar deneyin.",
        },
        ("courses.create_page", "Select the organization where this course should be created."): {
            "az": "Bu kursun yaradılacağı təşkilatı seçin.",
            "ru": "Выберите организацию, в которой нужно создать этот курс.",
            "tr": "Bu kursun oluşturulacağı kurumu seçin.",
        },
        ("exams.model.attempt_grant.meta", "extra attempt grant"): {"az": "əlavə cəhd hüququ"},
        ("exams.model.attempt_grant.meta", "extra attempt grants"): {"az": "əlavə cəhd hüquqları"},
        ("exams.model.student_pin.meta", "student exam PIN"): {"az": "tələbə imtahan PIN-i"},
        ("exams.model.student_pin.meta", "student exam PINs"): {"az": "tələbə imtahan PIN-ləri"},
        ("exams.template.coding_exam", "Advanced: paste all stdin values manually"): {
            "az": "Qabaqcıl: bütün stdin dəyərlərini əl ilə yapışdırın",
            "ru": "Расширенно: вставьте все значения stdin вручную",
            "tr": "Gelişmiş: tüm stdin değerlerini elle yapıştırın",
        },
        ("exams.template.coding_exam", "Console cleared."): {
            "az": "Konsol təmizləndi.",
            "ru": "Консоль очищена.",
            "tr": "Konsol temizlendi.",
        },
        ("exams.template.coding_exam", "Download ZIP"): {"az": "ZIP endir"},
        ("exams.template.coding_exam", "Finished in {ms} ms"): {
            "az": "{ms} ms-də tamamlandı",
            "ru": "Завершено за {ms} мс",
            "tr": "{ms} ms içinde tamamlandı",
        },
        ("exams.template.coding_exam", "Input description"): {"az": "Giriş məlumatlarının təsviri"},
        ("exams.template.coding_exam", "Program expects {count} input value(s). Provide them above before running."): {
            "az": "Proqram {count} giriş dəyəri gözləyir. İşə salmazdan əvvəl onları yuxarıda daxil edin.",
            "ru": "Программа ожидает {count} входных значений. Укажите их выше перед запуском.",
            "tr": "Program {count} girdi değeri bekliyor. Çalıştırmadan önce bunları yukarıda girin.",
        },
        ("exams.template.coding_exam", "Stdin ready ({count} line(s))."): {
            "az": "Stdin hazırdır ({count} sətir).",
            "ru": "Stdin готов ({count} строк).",
            "tr": "Stdin hazır ({count} satır).",
        },
        ("exams.template.coding_exam", "Tip: Ctrl+Enter runs · Ctrl+Space autocomplete · Ctrl+/ comment"): {
            "az": "İpucu: Ctrl+Enter işə salır · Ctrl+Space avtotamamlama · Ctrl+/ şərh",
            "ru": "Подсказка: Ctrl+Enter — запуск · Ctrl+Space — автодополнение · Ctrl+/ — комментарий",
            "tr": "İpucu: Ctrl+Enter çalıştırır · Ctrl+Space otomatik tamamlama · Ctrl+/ yorum",
        },
        ("exams.template.coding_exam", "Type the value here and press Enter."): {
            "az": "Dəyəri bura yazın və Enter basın.",
            "ru": "Введите значение здесь и нажмите Enter.",
            "tr": "Değeri buraya yazın ve Enter'a basın.",
        },
        ("exams.template.coding_exam", "Waiting for runner..."): {
            "az": "İcraçı gözlənilir...",
            "ru": "Ожидание исполнителя...",
            "tr": "Çalıştırıcı bekleniyor...",
        },
        ("exams.template.coding_exam", "{extra} extra input line(s) will be ignored."): {
            "az": "{extra} əlavə giriş sətri nəzərə alınmayacaq.",
            "ru": "{extra} лишних строк ввода будут проигнорированы.",
            "tr": "{extra} fazladan girdi satırı yok sayılacak.",
        },
        (
            "exams.template.create_exam_modal_form",
            "Configure the coding task, starter code, test cases, and execution controls.",
        ): {
            "az": "Kodlaşdırma tapşırığını, başlanğıc kodu, test hallarını və icra parametrlərini konfiqurasiya edin.",
            "ru": "Настройте задачу по программированию, стартовый код, тестовые случаи и параметры выполнения.",
            "tr": "Kodlama görevini, başlangıç kodunu, test durumlarını ve çalıştırma ayarlarını yapılandırın.",
        },
        ("exams.view.coding.error", "You already have a code run in progress. Wait for it to finish."): {
            "az": "Artıq icrada olan kod işləməniz var. Bitməsini gözləyin.",
            "ru": "У вас уже выполняется запуск кода. Дождитесь его завершения.",
            "tr": "Zaten devam eden bir kod çalıştırmanız var. Bitmesini bekleyin.",
        },
        ("exams.view.coding.error", "You are running code too quickly. Please wait a moment and try again."): {
            "az": "Kodu çox tez-tez işə salırsınız. Bir az gözləyib yenidən cəhd edin.",
            "ru": "Вы запускаете код слишком часто. Подождите немного и попробуйте снова.",
            "tr": "Kodu çok sık çalıştırıyorsunuz. Lütfen biraz bekleyip tekrar deneyin.",
        },
        (
            "exams.view.student.result.message",
            "Result is not available yet. It will appear after the teacher review window closes.",
        ): {"az": "Nəticə hələ mövcud deyil. Müəllimin yoxlama pəncərəsi bağlandıqdan sonra görünəcək."},
        ("live_exam.view.message", "Players can only be removed in the lobby."): {
            "az": "İştirakçılar yalnız lobbidə çıxarıla bilər.",
            "ru": "Участников можно удалить только в лобби.",
            "tr": "Katılımcılar yalnızca lobide çıkarılabilir.",
        },
        ("live_exam.view.message", "Reactions are disabled for this live exam."): {
            "az": "Bu canlı imtahan üçün reaksiyalar söndürülüb.",
            "ru": "Реакции для этого живого экзамена отключены.",
            "tr": "Bu canlı sınav için tepkiler devre dışı.",
        },
        ("notifications.event", "Email: {email}"): {"az": "E-poçt: {email}", "ru": "Эл. почта: {email}"},
        ("notifications.event", "Invited by: {actor}."): {"az": "Dəvət edən: {actor}."},
        ("notifications.event", "Username: @{username}"): {"az": "İstifadəçi adı: @{username}"},
        ("profile.rim", "Email"): {"az": "E-poçt", "ru": "Эл. почта"},
        ("registrar.component_kind", "Generic"): {"az": "Ümumi"},
        ("registrar.component_kind", "Independent work"): {"az": "Sərbəst iş"},
        ("registrar.correction", "Course work"): {"az": "Kurs işi"},
        ("registrar.correction", "Date"): {"az": "Tarix"},
        ("registrar.correction", "Hours"): {"az": "Saat"},
        ("registrar.correction", "Instructor"): {"az": "Müəllim"},
        ("registrar.correction", "Lesson deleted"): {"az": "Dərs silindi"},
        ("registrar.correction", "Nothing changed — adjust a field before saving."): {
            "az": "Heç nə dəyişməyib — yadda saxlamazdan əvvəl bir sahəni dəyişin.",
        },
        ("registrar.correction", "Self-work"): {"az": "Sərbəst iş"},
        ("registrar.correction", "The journal is published — it can't be changed."): {
            "az": "Jurnal dərc olunub — dəyişdirilə bilməz.",
        },
        ("registrar.correction", "The journal is published — the lesson can't be changed."): {
            "az": "Jurnal dərc olunub — dərs dəyişdirilə bilməz.",
        },
        ("registrar.correction", "Time"): {"az": "Vaxt"},
        ("registrar.correction", "Topic"): {"az": "Mövzu"},
        ("registrar.correction", "Type"): {"az": "Növ"},
        ("registrar.correction", "correction reverted"): {"az": "düzəliş geri alındı"},
        ("registrar.model.component_correction.meta", "component-score correction"): {"az": "komponent balı düzəlişi"},
        ("registrar.model.component_correction.meta", "component-score corrections"): {
            "az": "komponent balı düzəlişləri"
        },
        ("registrar.model.correction.meta", "journal correction"): {"az": "jurnal düzəlişi"},
        ("registrar.model.correction.meta", "journal corrections"): {"az": "jurnal düzəlişləri"},
        ("registrar.model.coursework.meta", "course work"): {"az": "kurs işi"},
        ("registrar.model.coursework.meta", "course works"): {"az": "kurs işləri"},
        ("registrar.model.coursework_correction.meta", "course-work correction"): {"az": "kurs işi düzəlişi"},
        ("registrar.model.coursework_correction.meta", "course-work corrections"): {"az": "kurs işi düzəlişləri"},
        ("registrar.model.criterion_score.meta", "criterion score"): {"az": "meyar balı"},
        ("registrar.model.criterion_score.meta", "criterion scores"): {"az": "meyar balları"},
        ("registrar.model.lesson_correction.meta", "lesson correction"): {"az": "dərs düzəlişi"},
        ("registrar.model.lesson_correction.meta", "lesson corrections"): {"az": "dərs düzəlişləri"},
        ("registrar.model.rubric.meta", "rubric"): {"az": "qiymətləndirmə rubriki"},
        ("registrar.model.rubric.meta", "rubrics"): {"az": "qiymətləndirmə rubrikləri"},
        ("registrar.model.rubric_criterion.meta", "rubric criteria"): {"az": "rubrik meyarları"},
        ("registrar.model.rubric_criterion.meta", "rubric criterion"): {"az": "rubrik meyarı"},
        ("registrar.model.selfwork_correction.meta", "self-work correction"): {"az": "sərbəst iş düzəlişi"},
        ("registrar.model.selfwork_correction.meta", "self-work corrections"): {"az": "sərbəst iş düzəlişləri"},
        ("registrar.model.selfwork_mark.meta", "independent work mark"): {"az": "sərbəst iş qiyməti"},
        ("registrar.model.selfwork_mark.meta", "independent work marks"): {"az": "sərbəst iş qiymətləri"},
        ("registrar.model.selfwork_topic.meta", "independent work topic"): {"az": "sərbəst iş mövzusu"},
        ("registrar.model.selfwork_topic.meta", "independent work topics"): {"az": "sərbəst iş mövzuları"},
        ("staff.management", "Email"): {"az": "E-poçt"},
        (
            "staff.management",
            "If nothing is selected, all sections stay open and panels are shown according to the filters you choose.",
        ): {"az": "Heç nə seçilməyibsə, bütün bölmələr açıq qalır və panellər seçdiyiniz süzgəclərə görə göstərilir."},
        ("staff.management", "Inactive"): {"az": "Qeyri-aktiv"},
        ("staff.management", "Individual"): {"az": "Fərdi"},
        ("staff.management", "Invite"): {"az": "Dəvət et"},
        ("staff.management", "Invite selected teachers"): {"az": "Seçilmiş müəllimləri dəvət et"},
        ("staff.management", "Invite selected teachers ({count} selected)"): {
            "az": "Seçilmiş müəllimləri dəvət et ({count} seçilib)",
        },
        ("staff.management", "Invite user"): {"az": "İstifadəçini dəvət et"},
        ("staff.management", "Username"): {"az": "İstifadəçi adı"},
        # (b) AZ msgid — TR-də fərqli olmalıdır (kataloq konvensiyası: «Yoklama defteri», «Engelle»)
        ("", "Jurnal"): {"tr": "Yoklama defteri"},
        ("registrar.journal", "Jurnal"): {"tr": "Yoklama defteri"},
        ("registrar.journal", "Jurnallar"): {"tr": "Yoklama defterleri"},
        ("registrar.journal_close", "Jurnallar"): {"tr": "Yoklama defterleri"},
        ("accounts.lessons_log", "Jurnalı aç"): {"tr": "Yoklama defterini aç"},
        ("accounts.semester", "Jurnal açıldı"): {"tr": "Yoklama defteri açıldı"},
        ("", "Blokla"): {"tr": "Engelle"},
        ("profile.rim", "Blokla"): {"tr": "Engelle"},
        ("profile.rim", "Bloklanmış"): {"tr": "Engellendi"},
        ("registrar.correction", "№ · SOYAD AD"): {"tr": "No · SOYAD AD"},
        ("accounts.student_admission", "Yer limiti"): {"tr": "Kontenjan"},
        ("accounts.dashboard", "sonuncu"): {"tr": "en son"},
    },
    "djangojs": {
        # ingilis mənbə (monitorinq paneli)
        ("", "Alert"): {"az": "Xəbərdarlıq"},
        ("", "Cache hit"): {"az": "Keş isabəti"},
        ("", "Image"): {"az": "İmic"},
        ("", "Load 1/5/15"): {"az": "Yük 1/5/15"},
        ("", "Uptime"): {"az": "İşləmə müddəti"},
        # (c) türk mənbə — rol icazə paneli, canlı imtahan lobbisi, AI kurs köməkçisi
        ("", '" bölümünde "'): {"az": '" bölməsində "'},
        ("", '" işlemini yapmaya izin verir.'): {"az": '" əməliyyatını yerinə yetirməyə icazə verir.'},
        ("", "1 sınav"): {"az": "1 imtahan"},
        ("", "3 ödev"): {"az": "3 tapşırıq"},
        ("", "AI Kurs Asistanı"): {"az": "AI Kurs Assistenti"},
        ("", "AI konulardan gruplara kadar her şeyi önerir. Hiçbir şey otomatik uygulanmaz."): {
            "az": "AI mövzulardan qruplara qədər hər şeyi təklif edir. Heç nə avtomatik tətbiq olunmur.",
        },
        ("", "AI kursu hazırlıyor…"): {"az": "AI kursu hazırlayır…"},
        ("", "Adım"): {"az": "Addım"},
        ("", "Adım adım"): {"az": "Addım-addım"},
        ("", "Aktif: izin açık, özellik kullanılabilir."): {
            "az": "Aktiv: icazə açıqdır, funksiya istifadə edilə bilər."
        },
        ("", "Alanları AI ile doldur"): {"az": "Sahələri AI ilə doldur"},
        ("", "Arşivleme"): {"az": "Arxivləmə"},
        ("", "Bağlantılar"): {"az": "Qoşulmalar"},
        ("", "Bir modül açın (örnek: Organizasyon, Üyeler)"): {"az": "Bir modul açın (məs.: Təşkilat, Üzvlər)"},
        ("", "Bu bölüm ne içindir?"): {"az": "Bu bölmə nə üçündür?"},
        ("", "Bu modül için izinler"): {"az": "Bu modul üçün icazələr"},
        ("", "Bu rol için hangi özelliklerin açık olacağını buradan yönetirsiniz."): {
            "az": "Bu rol üçün hansı funksiyaların açıq olacağını buradan idarə edirsiniz.",
        },
        ("", "Bu rol için tüm izinler aktiftir."): {"az": "Bu rol üçün bütün icazələr aktivdir."},
        ("", "Bulk: birden fazla izni aynı anda değiştirir."): {"az": "Toplu: bir neçə icazəni eyni anda dəyişir."},
        ("", "Büyük ölçekli kurs projeleri"): {"az": "Böyük miqyaslı kurs layihələri"},
        ("", "Dersler, dosyalar, video ve bağlantılar"): {"az": "Dərslər, fayllar, video və linklər"},
        ("", "Değerlendirme"): {"az": "Qiymətləndirmə"},
        ("", "Değerlendirme ve sonuç akışları"): {"az": "Qiymətləndirmə və nəticə axınları"},
        ("", "Düzenleme"): {"az": "Redaktə"},
        ("", "Dışa aktarma"): {"az": "İxrac"},
        ("", "Fakülte, bölüm ve yapısal birimler"): {"az": "Fakültə, kafedra və struktur vahidləri"},
        ("", "Geri çekme"): {"az": "Geri çəkmə"},
        ("", "Geçmiş ve denetim logu erişimi"): {"az": "Tarixçə və audit jurnalına giriş"},
        ("", "Giriş Kodu"): {"az": "Giriş kodu"},
        ("", "Görüntüleme"): {"az": "Baxış"},
        ("", "Güncelleme"): {"az": "Yeniləmə"},
        ("", "Henüz kimse bağlanmadı"): {"az": "Hələ heç kim qoşulmayıb"},
        ("", "Her adımı siz onaylarsınız"): {"az": "Hər addımı siz təsdiqləyirsiniz"},
        ("", "Kalite kontrol işlemleri"): {"az": "Keyfiyyət nəzarəti əməliyyatları"},
        ("", "Katılan katılımcılar"): {"az": "Qoşulmuş iştirakçılar"},
        ("", "Katılımcılar bekleniyor"): {"az": "İştirakçılar gözlənilir"},
        ("", "Katılımcılar burada görünecek."): {"az": "İştirakçılar burada görünəcək."},
        ("", "Katılımcıyı çıkar"): {"az": "İştirakçını çıxar"},
        ("", "Kullanıcı ve üyelik işlemleri"): {"az": "İstifadəçi və üzvlük əməliyyatları"},
        ("", "Kurs oluşturma ve kurs yönetimi"): {"az": "Kurs yaratma və kurs idarəetməsi"},
        ("", "Kursa dön"): {"az": "Kursa qayıt"},
        ("", "Laboratuvar çalışmaları"): {"az": "Laboratoriya işləri"},
        ("", "Lobi açık"): {"az": "Lobbi açıqdır"},
        ("", "MDN Web Docs — HTML referansı"): {"az": "MDN Web Docs — HTML istinadı"},
        ("", "Müfredat ve haftalık yapı"): {"az": "Sillabus və həftəlik struktur"},
        ("", "Müfredat, kaynaklar ve görevler planlanıyor"): {
            "az": "Sillabus, resurslar və tapşırıqlar planlaşdırılır"
        },
        ("", "Oluştur"): {"az": "Yarat"},
        ("", "Oluşturma"): {"az": "Yaratma"},
        ("", "Onaylandı"): {"az": "Təsdiqləndi"},
        ("", "Organizasyon ayarları ve yönetim işlemleri"): {"az": "Təşkilat parametrləri və idarəetmə əməliyyatları"},
        ("", "Pasif: izin kapalı, özellik kısıtlı."): {"az": "Passiv: icazə bağlıdır, funksiya məhduddur."},
        ("", "Plan hazır"): {"az": "Plan hazırdır"},
        ("", "Plan hazır 🎓"): {"az": "Plan hazırdır 🎓"},
        ("", "Python · başlangıç"): {"az": "Python · başlanğıc"},
        ("", "Servis"): {"az": "Xidmət"},
        ("", "Seçilenleri ekle"): {"az": "Seçilənləri əlavə et"},
        ("", "Seçilenleri sil"): {"az": "Seçilənləri sil"},
        ("", "Seçimi temizle"): {"az": "Seçimi təmizlə"},
        ("", "Sonuç bulunamadı."): {"az": "Nəticə tapılmadı."},
        ("", "Sınav"): {"az": "İmtahan"},
        ("", "Sınav yönetimi ve izleme"): {"az": "İmtahan idarəetməsi və monitorinq"},
        ("", "Sınavlar"): {"az": "İmtahanlar"},
        ("", "Test ve yazılı sınavlar, gözetim"): {"az": "Test və yazılı imtahanlar, nəzarət"},
        ("", "Tüm izinler (*)"): {"az": "Bütün icazələr (*)"},
        ("", "Tümünü seç"): {"az": "Hamısını seç"},
        ("", "Veritabanı (SQL) · pratik"): {"az": "Verilənlər bazası (SQL) · praktika"},
        ("", "Web teknolojileri · 2. sınıf · 14 hafta"): {"az": "Veb texnologiyaları · 2-ci kurs · 14 həftə"},
        ("", "Yapı"): {"az": "Struktur"},
        ("", "Yayınlama"): {"az": "Dərc etmə"},
        ("", "Yönetim"): {"az": "İdarəetmə"},
        ("", "aşağıdakileri onaylayayım mı?"): {"az": "aşağıdakıları təsdiqləyimmi?"},
        ("", "bölüm"): {"az": "bölmə"},
        ("", "işlem"): {"az": "əməliyyat"},
        ("", "{count} katılımcı bağlandı"): {"az": "{count} iştirakçı qoşuldu"},
        ("", "ÖRNEKLER"): {"az": "NÜMUNƏLƏR"},
        ("", "Ödevler"): {"az": "Tapşırıqlar"},
        ("", "Öğrenciler bağlantı, PIN veya QR kod ile katılabilir."): {
            "az": "Tələbələr link, PIN və ya QR kod ilə qoşula bilər.",
        },
        ("", "Öğrenciler için görevler ve teslimler"): {"az": "Tələbələr üçün tapşırıqlar və təhvillər"},
        ("", "Öğrenciler ve gruplar"): {"az": "Tələbələr və qruplar"},
        ("", "Öğretmen Başlat'a basar basmaz ilk soru gösterilecek."): {
            "az": "Müəllim «Başlat» düyməsini basan kimi ilk sual göstəriləcək.",
        },
        ("", "Öğretmen yeniden açana kadar yeni katılımcı giremez."): {
            "az": "Müəllim yenidən açana qədər yeni iştirakçı daxil ola bilməz.",
        },
        ("", "Üyeler"): {"az": "Üzvlər"},
        ("", "önerilen öğe"): {"az": "təklif olunan element"},
        ("", "öğe"): {"az": "element"},
        ("", "İtiraz başvuruları"): {"az": "Apellyasiya müraciətləri"},
        ("", "İtirazlar"): {"az": "Apellyasiyalar"},
        ("", "İzin"): {"az": "İcazə"},
        ("", "İzin ara (ör: view, edit, member)"): {"az": "İcazə axtar (məs.: view, edit, member)"},
        ("", "İzinler"): {"az": "İcazələr"},
        ("", "İçe aktarma"): {"az": "İdxal"},
        ("", "Şans ver"): {"az": "Əlavə cəhd ver"},
    },
}


# ── 3. TƏMİZLƏMƏ: venv-dən sızmış kitabxana sətirləri ───────────────────────
# Kodda (apps/core/config/templates/static) İŞLƏNMİR — `scripts/i18n_source_scan`
# tapmır; click / argparse / qpid-kombu / httpx (digest auth) / django-haystack
# və Django-nun öz `django.utils.text` sətirləridir. Dörd kataloqda da
# msgstr == msgid olduğu üçün silinmələrinin runtime-a təsiri SIFIRDIR
# (tərcümə onsuz da msgid-i qaytarırdı; Django-nun öz sətirlərini isə Django-nun
# öz kataloqu verir). Qapıda EN/RU/TR `identity` borcu kimi görünürdülər.
# Qoruyucu: giriş yalnız həmin kataloqda msgstr == msgid olduqda silinir.
PRUNE = {
    ("", "%(prog)s, version %(version)s"),
    ("", "(deprecated) "),
    ("", "(dynamic)"),
    ("", ", "),
    ("", ":"),
    ("", ":?.!"),
    (
        "",
        "A short code to identify the type of this package. For example: gem for a Rubygem, docker for a "
        "container, pypi for a Python Wheel or Egg, maven for a Maven Jar, deb for a Debian package, etc.",
    ),
    ("", "Aborted!"),
    ("", "Aborted."),
    ("", "Argument {name!r} takes {nargs} values."),
    ("", "Arguments take exactly one parameter declaration, got {length}: {decls}."),
    ("", "Attempting to connect to qpid with SASL mechanism %s"),
    ("", "Backend Alias"),
    ("", "Boolean option {decl!r} cannot use the same flag for true/false."),
    ("", "Choice({choices})"),
    ("", "Choose from:\n\t{choices}"),
    ("", "Confirm the action without prompting."),
    ("", "Connected to qpid with SASL mechanism %s"),
    ("", "Content purported to be compressed with %s but failed to decompress."),
    ("", "Could not determine name for option with declarations {decls!r}"),
    ("", "Could not open file {filename!r}: {message}"),
    ("", "Couldn't detect Bash version, shell completion is not supported."),
    ("", "DeprecationWarning: The command {name!r} is deprecated.{extra_message}"),
    ("", "DeprecationWarning: The {param_type} {name!r} is deprecated.{extra_message}"),
    ("", "Django site admin"),
    ("", "Do you want to continue?"),
    ("", "Extra qualifying data for a package such as the name of an OS, architecture, distro, etc."),
    ("", "Extra subpath within a package, relative to the package root."),
    ("", "Haystack"),
    ("", "IPv4"),
    ("", "IPv6"),
    ("", "Invalid start character for option ({option})"),
    ("", "Invalid value for {param_hint}: {message}"),
    ("", "Invalid value: {message}"),
    ("", "Kwargs"),
    ("", "Missing command."),
    ("", "Missing parameter"),
    ("", "Missing parameter: {param_name}"),
    ("", "Missing {param_type}"),
    ("", "Name '{name}' defined twice"),
    (
        "",
        "No options defined but a name was passed ({name}). Did you mean to declare an argument instead? "
        "Did you mean to pass '--{name}'?",
    ),
    ("", "No such command {name!r}."),
    ("", "No such option {name!r}."),
    ("", "Option {name!r} does not take a value."),
    ("", "Package name prefix, such as Maven groupid, Docker image owner, GitHub user or organization, etc."),
    ("", "Press any key to continue..."),
    ("", "Query"),
    ("", "Re: [EMSArena] %(subject)s"),
    ("", "Redirected but the response is missing a Location: header."),
    ("", "Shell completion is not supported for Bash versions older than 4.4."),
    ("", "Show the version and exit."),
    ("", "Show this message and exit."),
    ("", "The challenge doesn't contain a server nonce, or this one is empty."),
    ("", "Try '{command} {option}' for help."),
    ("", "Try [blue]'{command_path} {help_option}'[/] for help."),
    ("", "URL"),
    ("", "Unable to connect to qpid with SASL mechanism %s"),
    ("", "Unknown color {colour!r}"),
    ("", "Unknown standard stream '{name}'"),
    ("", "Unsupported value for algorithm: %s."),
    ("", "Unsupported value for pw-algorithm: %s."),
    ("", "Unsupported value for qop: %s."),
    ("", "Value must be an iterable."),
    ("", 'Value too long for field "{field_name}".'),
    ("", "Windows error: {error}"),
    ("", "[env var: {}]"),
    ("", "env var: {var}"),
    ("", "path"),
    ("", "show this help message and exit"),
    ("", "{editor}: Editing failed"),
    ("", "{editor}: Editing failed: {e}"),
    ("", "{name} {filename!r} does not exist."),
    ("", "{name} {filename!r} is a directory."),
    ("", "{name} {filename!r} is a file."),
    ("", "{name} {filename!r} is not executable."),
    ("", "{name} {filename!r} is not readable."),
    ("", "{name} {filename!r} is not writable."),
    ("", "{value!r} is not a valid UUID."),
    ("", "{value!r} is not a valid boolean. Recognized values: {states}"),
    ("", "{value!r} is not a valid {number_type}."),
    ("", "{value} is not in the range {range}."),
    ("", "…"),
    ("String to return when truncating text", "%(truncated_text)s…"),
}

#: click-in cəm formalı (msgid_plural) sətirləri — kodda işlənmir. AZ/EN/TR-də
#: identity, RU-da isə YANLIŞ tərcümə (msgstr[0]-da tək formada olmayan
#: `{len}` / `{possibilities}`). GNU gettext 1.0-ın `msgfmt --check-format`-ı
#: «a format specification for argument 'possibility' … doesn't exist in
#: 'msgid_plural'» deyib FATAL xəta verir — `compilemessages` bu girişə görə
#: qırılırdı (köhnə gettext bunu keçirdi). Dörd kataloqdan da silinir.
PRUNE_PLURAL = {
    "Takes {nargs} values but 1 was given.",
    "Did you mean {possibility}?",
}


# ── kataloq oxu/yaz köməkçiləri ─────────────────────────────────────────────
_FIELD_RE_CACHE: dict[str, re.Pattern] = {}


def _field_re(name: str) -> re.Pattern:
    # `name "…"` + istənilən sayda `"…"` davam sətri (bükülmüş giriş).
    if name not in _FIELD_RE_CACHE:
        _FIELD_RE_CACHE[name] = re.compile(
            r"^" + name + r' "((?:[^"\\]|\\.)*)"((?:\n"(?:[^"\\]|\\.)*")*)',
            re.M,
        )
    return _FIELD_RE_CACHE[name]


def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def unesc(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), value)


def field(chunk: str, name: str):
    match = _field_re(name).search(chunk)
    if not match:
        return None
    parts = [match.group(1)]
    parts += re.findall(r'^"((?:[^"\\]|\\.)*)"$', match.group(2), re.M)
    return unesc("".join(parts))


def chunk_key(chunk: str):
    """(ctx, msgid) — sıradan giriş; başlıq/plural/köhnəlmiş → None."""
    if "\nmsgid_plural " in chunk or re.search(r"^#~", chunk, re.M):
        return None
    msgid = field(chunk, "msgid")
    if msgid is None or msgid == "":
        return None
    return (field(chunk, "msgctxt") or "", msgid)


def set_msgstr(chunk: str, new: str) -> str:
    return _field_re("msgstr").sub(lambda m: f'msgstr "{esc(new)}"', chunk, count=1)


def po_path(lang: str, domain: str) -> str:
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def fill(lang: str, domain: str) -> tuple[int, int]:
    path = po_path(lang, domain)
    with open(path, encoding="utf-8") as handle:
        original = handle.read()

    chunks = original.split("\n\n")
    index: dict[tuple[str, str], int] = {}
    for i, chunk in enumerate(chunks):
        key = chunk_key(chunk)
        if key is not None and key not in index:
            index[key] = i

    added = 0
    for ctx, messages in ENTRIES.get(domain, {}).items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in index:
                continue
            msgstr = translations.get("az", msgid) if lang == "az" else translations.get(lang, msgid)
            block = ""
            if ctx:
                block += f'msgctxt "{esc(ctx)}"\n'
            block += f'msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n'
            chunks.append(block)
            index[(ctx, msgid)] = len(chunks) - 1
            added += 1

    fixed = 0
    for key, per_lang in FIXES.get(domain, {}).items():
        new = per_lang.get(lang)
        if new is None or key not in index:
            continue
        i = index[key]
        if field(chunks[i], "msgstr") == new:
            continue
        chunks[i] = set_msgstr(chunks[i], new)
        fixed += 1

    pruned = 0
    if domain == "django":
        for key in PRUNE:
            i = index.get(key)
            # Qoruyucu: yalnız tərcüməsiz (msgstr == msgid) giriş silinir.
            if i is None or chunks[i] is None or field(chunks[i], "msgstr") != key[1]:
                continue
            chunks[i] = None
            pruned += 1
        for i, chunk in enumerate(chunks):
            if chunk and "\nmsgid_plural " in chunk and field(chunk, "msgid") in PRUNE_PLURAL:
                chunks[i] = None
                pruned += 1
        chunks = [c for c in chunks if c is not None]

    # Bloklar tək boş sətirlə ayrılır, fayl bir «\n» ilə bitir — kataloqlar
    # onsuz da bu formadadır (yoxlanılıb), ona görə dəyişiklik olmayanda
    # nəticə orijinala bayt-bayt bərabərdir (idempotentlik).
    text = "\n\n".join(c.rstrip("\n") for c in chunks) + "\n"
    if text != original:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{domain}/{lang}: +{added} giriş, {fixed} düzəliş, −{pruned} kitabxana sətri")
    return added, fixed


def _self_check() -> None:
    """Hədəf dil qarşılığı msgid ilə eyni olan (yeni identity yaradan) sətirləri göstər."""
    for domain, ctxs in ENTRIES.items():
        for ctx, messages in ctxs.items():
            for msgid, tr in messages.items():
                for lang in ("en", "ru", "tr"):
                    if tr.get(lang) == msgid and "az" not in tr:
                        print(f"   ⚠️ identity qalır: {domain} {ctx!r} {msgid[:50]!r} [{lang}]")


if __name__ == "__main__":
    for domain in ("django", "djangojs"):
        for locale in LOCALES:
            fill(locale, domain)
    _self_check()
