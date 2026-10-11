#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 (WP6): «Jurnal təmizliyi» (RİM rəhbəri) mətnləri.

Əlavə olunan mətnlər:
  * `registrar.journal_hygiene`: səbəb / mənbə etiketləri, qərar növləri, xidmət xətaları, önləmə səbəbləri;
  * `registrar.model.journal_hygiene.meta`: model adı;
  * `accounts.journal_hygiene`: bölmə paneli, süzgəclər, cədvəl başlıqları, dialoq, JS mətnləri (json_script);
  * `profile.section`: «Jurnal təmizliyi»;
  * `ui.dialog`: «Bağla» / «Ləğv et» (artıq varsa toxunulmur).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp6hygiene.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


RH = "registrar.journal_hygiene"
RM = "registrar.model.journal_hygiene.meta"
AH = "accounts.journal_hygiene"
PS = "profile.section"
UD = "ui.dialog"

_REGISTRAR = [
    # Ayrılmış tələbə səbəbləri
    _t("Hesab arxivdədir", "Account is archived", "Учётная запись в архиве", "Hesap arşivde"),
    _t("Xaric olunub", "Expelled", "Отчислен", "Kaydı silindi"),
    _t("Akademik məzuniyyətdədir", "On academic leave", "В академическом отпуске", "Akademik izinde"),
    _t("Məzun olub", "Graduated", "Выпускник", "Mezun oldu"),
    _t(
        "Akademik qeyd passivdir",
        "Academic record is inactive",
        "Академическая запись неактивна",
        "Akademik kayıt pasif",
    ),
    _t("Oxu müddəti bitib", "Study period has ended", "Срок обучения истёк", "Öğrenim süresi bitti"),
    _t("Akademik qeydi yoxdur", "No academic record", "Нет академической записи", "Akademik kaydı yok"),
    _t("Qrupu dəyişib", "Group changed", "Сменил группу", "Grubu değişti"),
    # Boş fənn mənbələri
    _t("Açılış ləğv olunub", "Offering cancelled", "Курс отменён", "Ders açılışı iptal edildi"),
    _t("Seçmə fənn dəyişdirilib", "Elective was changed", "Элективный предмет заменён", "Seçmeli ders değiştirildi"),
    _t("Tədris planında yoxdur", "Not in the curriculum", "Нет в учебном плане", "Öğretim planında yok"),
    _t(
        "Köhnə sistemdə nəticə yoxdur",
        "No result in the old system",
        "Нет результата в старой системе",
        "Eski sistemde sonuç yok",
    ),
    _t("Mənbəsi bəlli deyil", "Source unknown", "Источник неизвестен", "Kaynağı belli değil"),
    _t("Güclü siqnal", "Strong signal", "Сильный сигнал", "Güçlü sinyal"),
    _t("Yoxlanmalı", "Needs review", "Требует проверки", "İncelenmeli"),
    # Qərar növləri
    _t("Ayrılmış tələbə", "Student who left", "Выбывший студент", "Ayrılan öğrenci"),
    _t("Boş fənn", "Empty subject", "Пустой предмет", "Boş ders"),
    # Xidmət xətaları
    _t(
        "Jurnal təmizliyi üçün səlahiyyətiniz yoxdur (journal.correct).",
        "You do not have permission for journal cleanup (journal.correct).",
        "У вас нет прав на очистку журналов (journal.correct).",
        "Yoklama defteri temizliği için yetkiniz yok (journal.correct).",
    ),
    _t("Heç bir sətir seçilməyib.", "No rows selected.", "Не выбрано ни одной строки.", "Hiç satır seçilmedi."),
    _t(
        "Bir əməldə ən çox %(n)d sətir emal olunur.",
        "At most %(n)d rows can be processed in one action.",
        "За одно действие обрабатывается не более %(n)d строк.",
        "Bir işlemde en fazla %(n)d satır işlenir.",
    ),
    _t(
        "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.",
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — короткой записи недостаточно для аудита.",
        "Gerekçe en az 20 karakter olmalıdır — kısa not denetim için yeterli değil.",
    ),
    _t(
        "Bu kateqoriya üçün naməlum əməliyyat.",
        "Unknown action for this category.",
        "Неизвестное действие для этой категории.",
        "Bu kategori için bilinmeyen işlem.",
    ),
    _t(
        "Seçilmiş sətirlər bu arada dəyişib — siyahını yeniləyin.",
        "The selected rows have changed in the meantime — refresh the list.",
        "Выбранные строки за это время изменились — обновите список.",
        "Seçilen satırlar bu arada değişti — listeyi yenileyin.",
    ),
    _t(
        "Əvvəlcə önizləməyə baxın.",
        "Open the preview first.",
        "Сначала откройте предпросмотр.",
        "Önce önizlemeye bakın.",
    ),
    _t(
        "Siyahı önizləmədən sonra dəyişib — yenidən önizləyin.",
        "The list changed after the preview — preview again.",
        "Список изменился после предпросмотра — повторите предпросмотр.",
        "Liste önizlemeden sonra değişti — yeniden önizleyin.",
    ),
    _t(
        "Məlumatı olan sətir yalnız dondurula bilər.",
        "A row that has data can only be frozen.",
        "Строку с данными можно только заморозить.",
        "Verisi olan satır yalnızca dondurulabilir.",
    ),
    _t("Sistem", "System", "Система", "Sistem"),
    _t(
        "Qərar tapılmadı və ya artıq geri qaytarılıb.",
        "Decision not found or already reverted.",
        "Решение не найдено или уже отменено.",
        "Karar bulunamadı veya zaten geri alındı.",
    ),
    _t(
        "Bəzi qərarlar geri qaytarıla bilmir: qeydiyyatın statusu o vaxtdan dəyişib "
        "və ya tələbə həmin fənn üzrə başqa jurnalda aktivdir.",
        "Some decisions cannot be reverted: the enrollment status has changed since "
        "or the student is active in another journal for the same subject.",
        "Некоторые решения нельзя отменить: статус записи с тех пор изменился "
        "или студент активен в другом журнале по тому же предмету.",
        "Bazı kararlar geri alınamıyor: kaydın durumu o zamandan beri değişti "
        "veya öğrenci aynı ders için başka bir defterde aktif.",
    ),
    # Önləmə axınlarının səbəbləri (qərar tarixçəsində görünür)
    _t(
        "Qrupun seçmə fənni dəyişdirildi (%(group)s → %(subject)s): köhnə seçimin boş qeydiyyatı çıxarıldı.",
        "The group's elective was changed (%(group)s → %(subject)s): the empty enrollment of the old choice was removed.",
        "Элективный предмет группы изменён (%(group)s → %(subject)s): пустая запись прежнего выбора исключена.",
        "Grubun seçmeli dersi değiştirildi (%(group)s → %(subject)s): eski seçimin boş kaydı çıkarıldı.",
    ),
    _t(
        "Qrup bu seçmə fənni yenidən seçdi — əvvəl çıxarılmış boş qeydiyyat bərpa olundu.",
        "The group chose this elective again — the previously removed empty enrollment was restored.",
        "Группа снова выбрала этот элективный предмет — ранее исключённая пустая запись восстановлена.",
        "Grup bu seçmeli dersi yeniden seçti — daha önce çıkarılan boş kayıt geri yüklendi.",
    ),
    _t(
        "Açılış ləğv olundu: %(reason)s",
        "Offering cancelled: %(reason)s",
        "Курс отменён: %(reason)s",
        "Ders açılışı iptal edildi: %(reason)s",
    ),
]

_MODEL = [
    _t(
        "journal hygiene decision",
        "journal hygiene decision",
        "решение по очистке журнала",
        "yoklama defteri temizlik kararı",
    ),
    _t(
        "journal hygiene decisions",
        "journal hygiene decisions",
        "решения по очистке журналов",
        "yoklama defteri temizlik kararları",
    ),
]

_SOURCES = [
    _t(
        "Dərs xanası (davamiyyət / bal)",
        "Lesson cell (attendance / score)",
        "Ячейка занятия (посещаемость / балл)",
        "Ders hücresi (yoklama / puan)",
    ),
    _t("Komponent balı", "Component score", "Балл компонента", "Bileşen puanı"),
    _t("Rubrik balı", "Rubric score", "Балл по рубрике", "Rubrik puanı"),
    _t("Sərbəst iş", "Independent work", "Самостоятельная работа", "Serbest çalışma"),
    _t("Kurs işi", "Coursework", "Курсовая работа", "Dönem ödevi"),
    _t("Təkrar imtahan", "Resit", "Пересдача", "Bütünleme"),
    _t("İmtahan balı yazısı", "Exam score entry", "Запись экзаменационного балла", "Sınav puanı kaydı"),
    _t("Köhnə sistemin nəticəsi", "Old system result", "Результат из старой системы", "Eski sistemin sonucu"),
    _t("Yekun qiymət", "Final grade", "Итоговая оценка", "Nihai not"),
    _t("Jurnal düzəlişi", "Journal correction", "Исправление журнала", "Defter düzeltmesi"),
    _t(
        "Sərbəst iş düzəlişi",
        "Independent work correction",
        "Исправление самостоятельной работы",
        "Serbest çalışma düzeltmesi",
    ),
    _t("Kurs işi düzəlişi", "Coursework correction", "Исправление курсовой работы", "Dönem ödevi düzeltmesi"),
    _t("Komponent düzəlişi", "Component correction", "Исправление компонента", "Bileşen düzeltmesi"),
    _t("Alt qrup sənədi", "Subgroup document", "Документ подгруппы", "Alt grup belgesi"),
    _t("Köçürmə tarixçəsi", "Transfer history", "История перевода", "Nakil geçmişi"),
    _t("Fənn qovluğu təhvili", "Subject folder submission", "Сдача в папку предмета", "Ders klasörü teslimi"),
]

_ACCOUNTS = _SOURCES + [
    # Panel çərçivəsi
    _t(
        "Oxumayan, amma jurnalda adı qalan tələbələri və nəticələrə «boş» düşmüş fənləri tapın. Heç nə silinmir: "
        "sətir dondurulur və ya nəticələrdən çıxarılır, hər qərar tarixçəyə və audit jurnalına yazılır və "
        "«Bərpa et» ilə geri qaytarılır.",
        "Find students who no longer study but remain in journals, and subjects that show up «empty» in results. "
        "Nothing is deleted: a row is frozen or removed from results, every decision is written to the history and "
        "the audit log and can be undone with «Restore».",
        "Найдите студентов, которые больше не учатся, но остались в журналах, и предметы, попавшие в результаты "
        "«пустыми». Ничего не удаляется: строка замораживается или исключается из результатов, каждое решение "
        "записывается в историю и журнал аудита и отменяется кнопкой «Восстановить».",
        "Artık okumayan ama defterde adı kalan öğrencileri ve sonuçlara «boş» düşen dersleri bulun. Hiçbir şey "
        "silinmez: satır dondurulur veya sonuçlardan çıkarılır, her karar geçmişe ve denetim günlüğüne yazılır ve "
        "«Geri yükle» ile geri alınır.",
    ),
    _t(
        "Jurnal təmizliyi yalnız RİM rəhbəri və superadmin üçündür.",
        "Journal cleanup is available only to the RİM head and the superadmin.",
        "Очистка журналов доступна только руководителю RİM и суперадмину.",
        "Defter temizliği yalnızca RİM başkanı ve süper yönetici içindir.",
    ),
    _t(
        "Jurnal təmizliyi əməlləri yalnız RİM rəhbəri üçündür.",
        "Journal cleanup actions are available only to the RİM head.",
        "Действия очистки журналов доступны только руководителю RİM.",
        "Defter temizliği işlemleri yalnızca RİM başkanı içindir.",
    ),
    _t(
        "«Başqasının adından» rejimindəsiniz — siyahılar yalnız oxunur.",
        "You are in «view as» mode — the lists are read-only.",
        "Вы в режиме «от имени другого» — списки доступны только для чтения.",
        "«Başkası adına» modundasınız — listeler salt okunur.",
    ),
    _t(
        "Siyahıları görürsünüz, amma qərar vermək üçün təşkilat miqyaslı «journal.correct» səlahiyyəti lazımdır.",
        "You can see the lists, but deciding requires the organization-wide «journal.correct» permission.",
        "Вы видите списки, но для решений нужно право «journal.correct» на уровне организации.",
        "Listeleri görüyorsunuz, ancak karar vermek için kurum genelinde «journal.correct» yetkisi gerekir.",
    ),
    _t("Ayrılmış tələbələr", "Students who left", "Выбывшие студенты", "Ayrılan öğrenciler"),
    _t("jurnalda adı qalan sətir", "rows still in journals", "строк ещё в журналах", "defterde kalan satır"),
    _t("Boş fənlər", "Empty subjects", "Пустые предметы", "Boş dersler"),
    _t(
        "nəticədə boş görünən sətir",
        "rows shown empty in results",
        "строк пустых в результатах",
        "sonuçta boş görünen satır",
    ),
    _t("Güclü siqnal", "Strong signal", "Сильный сигнал", "Güçlü sinyal"),
    _t("seçilmiş tab üzrə", "for the selected tab", "по выбранной вкладке", "seçili sekme için"),
    _t("Qərarlar", "Decisions", "Решения", "Kararlar"),
    _t("geri qaytarılan daxil", "including reverted", "включая отменённые", "geri alınanlar dahil"),
    _t(
        "Jurnal təmizliyi bölmələri",
        "Journal cleanup sections",
        "Разделы очистки журналов",
        "Defter temizliği bölümleri",
    ),
    _t("Tarixçə", "History", "История", "Geçmiş"),
    _t(
        "Cari və gələcək semestrin AÇIQ jurnallarında qalan, amma oxumayan tələbələr: hesab arxivdədir, xaric / "
        "akademik məzuniyyət / məzun, qeyd passivdir, oxu müddəti bitib və ya akademik qeydi yoxdur. «Dondur» "
        "sətri jurnal və imtahan siyahısından çıxarır (bərpa əmri onu qaytarır); məlumatı olmayan sətir "
        "nəticələrdən də çıxarıla bilər.",
        "Students who no longer study but remain in OPEN journals of the current and upcoming semesters: the account "
        "is archived, expelled / on academic leave / graduated, the record is inactive, the study period has ended or "
        "there is no academic record. «Freeze» removes the row from the journal and the exam roster (a reinstatement "
        "order brings it back); a row without data can also be removed from results.",
        "Студенты, которые больше не учатся, но остались в ОТКРЫТЫХ журналах текущего и следующего семестров: "
        "учётная запись в архиве, отчислен / академический отпуск / выпускник, запись неактивна, срок обучения истёк "
        "или нет академической записи. «Заморозить» убирает строку из журнала и экзаменационного списка (приказ о "
        "восстановлении возвращает её); строку без данных можно также исключить из результатов.",
        "Artık okumayan ama mevcut ve gelecek dönemin AÇIK defterlerinde kalan öğrenciler: hesap arşivde, kaydı "
        "silinmiş / akademik izinde / mezun, kayıt pasif, öğrenim süresi bitmiş veya akademik kaydı yok. «Dondur» "
        "satırı defterden ve sınav listesinden çıkarır (geri alma kararı onu geri getirir); verisi olmayan satır "
        "sonuçlardan da çıkarılabilir.",
    ),
    _t(
        "Heç bir balı, davamiyyəti, sənədi və ya imtahan yazısı olmayan qeydiyyatlar: dövr bitib / jurnal bağlanıb, "
        "açılış ləğv olunub və ya qrup seçmə fənni dəyişib. «Güclü siqnal» — açılışda bir dərs də yoxdur və qrupda "
        "heç kimin datası yoxdur; qalanları əvvəlcə yoxlayın.",
        "Enrollments without any score, attendance, document or exam entry: the period has ended / the journal is "
        "closed, the offering was cancelled or the group changed its elective. «Strong signal» — the offering has no "
        "lessons and nobody in the group has data; review the rest first.",
        "Записи без единого балла, посещаемости, документа или экзаменационной записи: период завершён / журнал "
        "закрыт, курс отменён или группа сменила элективный предмет. «Сильный сигнал» — в курсе нет ни одного "
        "занятия и ни у кого в группе нет данных; остальные сначала проверьте.",
        "Hiç puanı, yoklaması, belgesi veya sınav kaydı olmayan kayıtlar: dönem bitti / defter kapandı, ders açılışı "
        "iptal edildi veya grup seçmeli dersini değiştirdi. «Güçlü sinyal» — açılışta hiç ders yok ve grupta kimsenin "
        "verisi yok; diğerlerini önce inceleyin.",
    ),
    _t(
        "Bu alətin bütün qərarları. «Bərpa et» yalnız statusu o vaxtdan dəyişməmiş sətirləri əvvəlki vəziyyətinə "
        "qaytarır.",
        "All decisions made with this tool. «Restore» returns a row to its previous state only if its status has not "
        "changed since.",
        "Все решения этого инструмента. «Восстановить» возвращает в прежнее состояние только строки, статус которых "
        "с тех пор не менялся.",
        "Bu aracın tüm kararları. «Geri yükle» yalnızca o zamandan beri durumu değişmemiş satırları önceki hâline "
        "döndürür.",
    ),
    # Süzgəclər
    _t("Axtarış", "Search", "Поиск", "Arama"),
    _t(
        "Tələbə, istifadəçi adı, fənn…",
        "Student, username, subject…",
        "Студент, логин, предмет…",
        "Öğrenci, kullanıcı adı, ders…",
    ),
    _t("Semestr", "Semester", "Семестр", "Dönem"),
    _t("Semestr axtar…", "Search semester…", "Поиск семестра…", "Dönem ara…"),
    _t("Hamısı", "All", "Все", "Tümü"),
    _t("cari", "current", "текущий", "mevcut"),
    _t("Fakültə", "Faculty", "Факультет", "Fakülte"),
    _t("Qrup", "Group", "Группа", "Grup"),
    _t("Qrup axtar…", "Search group…", "Поиск группы…", "Grup ara…"),
    _t("Səbəb", "Reason", "Причина", "Gerekçe"),
    _t("Mənbə", "Source", "Источник", "Kaynak"),
    _t("Növ", "Type", "Тип", "Tür"),
    _t("Vəziyyət", "State", "Состояние", "Durum"),
    _t("Qüvvədədir", "In effect", "Действует", "Yürürlükte"),
    _t("Geri qaytarılıb", "Reverted", "Отменено", "Geri alındı"),
    _t("Səbəb süzgəcləri", "Reason filters", "Фильтры причин", "Gerekçe filtreleri"),
    # Alət paneli
    _t("Uyğun olanların hamısını seç", "Select all matching", "Выбрать все подходящие", "Uyanların tümünü seç"),
    _t("Seçimi təmizlə", "Clear selection", "Снять выбор", "Seçimi temizle"),
    _t("Jurnaldan dondur", "Freeze in journal", "Заморозить в журнале", "Defterde dondur"),
    _t("Nəticələrdən çıxar", "Remove from results", "Исключить из результатов", "Sonuçlardan çıkar"),
    _t("Bərpa et", "Restore", "Восстановить", "Geri yükle"),
    # Cədvəllər
    _t(
        "Səhifədəki bütün sətirləri seç",
        "Select all rows on the page",
        "Выбрать все строки на странице",
        "Sayfadaki tüm satırları seç",
    ),
    _t("Tələbə", "Student", "Студент", "Öğrenci"),
    _t("Fənn · qrup", "Subject · group", "Предмет · группа", "Ders · grup"),
    _t("Niyə burada", "Why it is here", "Почему здесь", "Neden burada"),
    _t("Məlumat", "Data", "Данные", "Veri"),
    _t("Status", "Status", "Статус", "Durum"),
    _t("Tarix", "Date", "Дата", "Tarih"),
    _t("Fənn · qrup · semestr", "Subject · group · semester", "Предмет · группа · семестр", "Ders · grup · dönem"),
    _t("Qərar", "Decision", "Решение", "Karar"),
    _t("Kim / səbəb", "Who / reason", "Кто / причина", "Kim / gerekçe"),
    # Dialoq
    _t(
        "Məs.: Rektorun 12.09.2026 tarixli xaric əmrləri əsasında jurnallar təmizlənir.",
        "E.g.: Journals are cleaned up based on the rector's expulsion orders of 12.09.2026.",
        "Напр.: журналы очищаются на основании приказов ректора об отчислении от 12.09.2026.",
        "Örn.: Defterler rektörün 12.09.2026 tarihli kayıt silme kararlarına göre temizleniyor.",
    ),
    _t(
        "Səbəb qərar tarixçəsinə və audit jurnalına yazılır.",
        "The reason is written to the decision history and the audit log.",
        "Причина записывается в историю решений и журнал аудита.",
        "Gerekçe karar geçmişine ve denetim günlüğüne yazılır.",
    ),
    _t(
        "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.",
        "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "Причина должна содержать не менее 20 символов — короткой записи недостаточно для аудита.",
        "Gerekçe en az 20 karakter olmalıdır — kısa not denetim için yeterli değil.",
    ),
    _t("Yenidən önizlə", "Preview again", "Повторить предпросмотр", "Yeniden önizle"),
    _t("Təsdiqlə", "Confirm", "Подтвердить", "Onayla"),
    # Endpoint mesajları
    _t("Naməlum əməliyyat.", "Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    _t(
        "Yazıldı: %(n)d sətir. Geri qaytarmaq üçün «Tarixçə»yə keçin.",
        "Saved: %(n)d row(s). To undo, open «History».",
        "Записано строк: %(n)d. Чтобы отменить, откройте «История».",
        "Kaydedildi: %(n)d satır. Geri almak için «Geçmiş» sekmesine gidin.",
    ),
    _t(
        "Geri qaytarıldı: %(n)d qərar.",
        "Reverted: %(n)d decision(s).",
        "Отменено решений: %(n)d.",
        "Geri alındı: %(n)d karar.",
    ),
    # JS mətnləri (json_script)
    _t(
        "Bu süzgəcə uyğun ayrılmış tələbə yoxdur.",
        "No students who left match this filter.",
        "Нет выбывших студентов по этому фильтру.",
        "Bu filtreye uyan ayrılan öğrenci yok.",
    ),
    _t(
        "Bu süzgəcə uyğun boş fənn yoxdur.",
        "No empty subjects match this filter.",
        "Нет пустых предметов по этому фильтру.",
        "Bu filtreye uyan boş ders yok.",
    ),
    _t("Hələ qərar yoxdur.", "No decisions yet.", "Решений пока нет.", "Henüz karar yok."),
    _t(
        "Siyahı yüklənmədi. Bir az sonra yenidən cəhd edin.",
        "The list did not load. Please try again shortly.",
        "Список не загрузился. Попробуйте ещё раз чуть позже.",
        "Liste yüklenmedi. Biraz sonra yeniden deneyin.",
    ),
    _t("Yüklənir…", "Loading…", "Загрузка…", "Yükleniyor…"),
    _t("{n} sətir seçilib", "{n} row(s) selected", "Выбрано строк: {n}", "{n} satır seçildi"),
    _t(
        "Sətir seçin — əməl düymələri seçimdən sonra açılır.",
        "Select rows — the action buttons become available after a selection.",
        "Выберите строки — кнопки действий станут доступны после выбора.",
        "Satır seçin — işlem düğmeleri seçimden sonra açılır.",
    ),
    _t(
        "Süzgəcə uyğun ilk {n} sətir seçildi.",
        "The first {n} matching rows were selected.",
        "Выбраны первые {n} подходящих строк.",
        "Filtreye uyan ilk {n} satır seçildi.",
    ),
    _t("Əvvəlki", "Previous", "Назад", "Önceki"),
    _t("Sonrakı", "Next", "Далее", "Sonraki"),
    _t(
        "Səhifə {page} / {pages} · {total} sətir",
        "Page {page} / {pages} · {total} rows",
        "Страница {page} / {pages} · строк: {total}",
        "Sayfa {page} / {pages} · {total} satır",
    ),
    _t("Məlumat var", "Has data", "Есть данные", "Veri var"),
    _t("Boş", "Empty", "Пусто", "Boş"),
    _t("{n} saat qayıb", "{n} h absent", "{n} ч пропусков", "{n} saat devamsız"),
    _t("Jurnal bağlıdır", "Journal is closed", "Журнал закрыт", "Defter kapalı"),
    _t(
        "Status o vaxtdan dəyişib — geri qaytarılmır",
        "Status has changed since — cannot be reverted",
        "Статус с тех пор изменился — отмена невозможна",
        "Durum o zamandan beri değişti — geri alınamaz",
    ),
    _t(
        "Jurnaldan dondurmaq — önizləmə",
        "Freeze in journal — preview",
        "Заморозить в журнале — предпросмотр",
        "Defterde dondurma — önizleme",
    ),
    _t(
        "Nəticələrdən çıxarmaq — önizləmə",
        "Remove from results — preview",
        "Исключить из результатов — предпросмотр",
        "Sonuçlardan çıkarma — önizleme",
    ),
    _t("Qərarları geri qaytarmaq", "Revert decisions", "Отменить решения", "Kararları geri al"),
    _t(
        "Sətirlər jurnaldan və imtahan siyahısından çıxır, tarixçə qalır; bərpa əmri və ya «Bərpa et» qaytarır.",
        "The rows leave the journal and the exam roster, the history stays; a reinstatement order or «Restore» brings "
        "them back.",
        "Строки уходят из журнала и экзаменационного списка, история сохраняется; приказ о восстановлении или "
        "«Восстановить» возвращает их.",
        "Satırlar defterden ve sınav listesinden çıkar, geçmiş kalır; geri alma kararı veya «Geri yükle» onları geri "
        "getirir.",
    ),
    _t(
        "Sətirlər nəticə səthlərindən (transkript, statistika) də çıxır. Qeydiyyat silinmir — «Bərpa et» qaytarır.",
        "The rows also leave the result views (transcript, statistics). The enrollment is not deleted — «Restore» "
        "brings it back.",
        "Строки исключаются и из результатов (транскрипт, статистика). Запись не удаляется — «Восстановить» "
        "возвращает её.",
        "Satırlar sonuç ekranlarından (transkript, istatistik) da çıkar. Kayıt silinmez — «Geri yükle» geri getirir.",
    ),
    _t(
        "Seçilmiş qərarlar ləğv olunur və qeydiyyatlar əvvəlki statusuna qayıdır.",
        "The selected decisions are cancelled and the enrollments return to their previous status.",
        "Выбранные решения отменяются, записи возвращаются к прежнему статусу.",
        "Seçilen kararlar iptal edilir ve kayıtlar önceki durumuna döner.",
    ),
    _t(
        "{n} qərar geri qaytarılacaq.",
        "{n} decision(s) will be reverted.",
        "Будет отменено решений: {n}.",
        "{n} karar geri alınacak.",
    ),
    _t("Sətir", "Rows", "Строки", "Satır"),
    _t("Jurnal", "Journals", "Журналы", "Defter"),
    _t("Məlumatı olan", "With data", "С данными", "Verisi olan"),
    _t("Yeni status", "New status", "Новый статус", "Yeni durum"),
    _t("Toxunulan jurnallar", "Affected journals", "Затронутые журналы", "Etkilenen defterler"),
    _t("və daha {n} jurnal", "and {n} more journal(s)", "и ещё журналов: {n}", "ve {n} defter daha"),
    _t("Qeydiyyatlardakı məlumat", "Data in the enrollments", "Данные в записях", "Kayıtlardaki veri"),
    _t(
        "Seçilmiş sətirlərdə heç bir bal, davamiyyət və ya sənəd yoxdur.",
        "The selected rows have no scores, attendance or documents.",
        "В выбранных строках нет баллов, посещаемости или документов.",
        "Seçilen satırlarda hiç puan, yoklama veya belge yok.",
    ),
    _t(
        "{n} sətirdə məlumat var — onlar nəticələrdən çıxarıla bilməz, yalnız dondurula bilər. Seçimi dəyişin.",
        "{n} row(s) have data — they cannot be removed from results, only frozen. Change the selection.",
        "В {n} строках есть данные — их нельзя исключить из результатов, только заморозить. Измените выбор.",
        "{n} satırda veri var — sonuçlardan çıkarılamaz, yalnızca dondurulabilir. Seçimi değiştirin.",
    ),
    _t(
        "{n} sətir artıq siyahıda deyil — siyahını yeniləyib yenidən seçin.",
        "{n} row(s) are no longer in the list — refresh the list and select again.",
        "{n} строк(и) больше нет в списке — обновите список и выберите снова.",
        "{n} satır artık listede değil — listeyi yenileyip yeniden seçin.",
    ),
    _t(
        "Siyahı önizləmədən sonra dəyişib — yenidən önizləyin.",
        "The list changed after the preview — preview again.",
        "Список изменился после предпросмотра — повторите предпросмотр.",
        "Liste önizlemeden sonra değişti — yeniden önizleyin.",
    ),
    _t("sətir", "rows", "строк", "satır"),
]

_PROFILE = [
    _t("Jurnal təmizliyi", "Journal cleanup", "Очистка журналов", "Defter temizliği"),
]

_DIALOG = [
    _t("Bağla", "Close", "Закрыть", "Kapat"),
    _t("Ləğv et", "Cancel", "Отмена", "İptal"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    RH: {row["az"]: row for row in _REGISTRAR},
    RM: {row["az"]: row for row in _MODEL},
    AH: {row["az"]: row for row in _ACCOUNTS},
    PS: {row["az"]: row for row in _PROFILE},
    UD: {row["az"]: row for row in _DIALOG},
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
