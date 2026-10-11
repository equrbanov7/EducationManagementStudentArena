#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 (WP3): müəllim imtahan səhifələrinin redizaynı + «Mövcud imtahanlar».

Əlavə olunan mətnlər (sahib 2026-10-10 «modern UX/UI»):
  * `exams.template.language_manager`: «Dil variantları» səhifəsi. Sətir düyməsi «Deaktiv et»
    kontekstlə gəlir — kontekstsiz az msgstr-i «Bəli, deaktiv et» idi və düyməyə sızırdı;
  * `exams.template.teacher_exam_results`: «İmtahan nəticələri» (filtrlər, gg.aa.iiii tarix, boş hallar);
  * `exams.template.bank_picker`: «Mövcud bankdan sual əlavə et»;
  * `exams.template.question_form`: «Yeni sual əlavə et» modalı (bölmələr, fayl zonası);
  * `exams.template.teacher_questions_bank`: «Sual bankı» (alət zolağı, təhlükə zonası, yazılı təsdiq);
  * `exams.form.question.label`: «Variant %%(n)s» — `{% trans %}` literalında `%` ikiqat saxlanılır
    (Django render zamanı `%%` → `%` edir), ona görə msgid/msgstr ikiqat `%%` ilədir;
  * `exams.available_page`: «Mövcud imtahanlar» bağlı olanda göstərilən məlumat mesajı.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp3exams.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AVAILABLE = "exams.available_page"
LABEL = "exams.form.question.label"
PICKER = "exams.template.bank_picker"
LANGUAGES = "exams.template.language_manager"
FORM = "exams.template.question_form"
RESULTS = "exams.template.teacher_exam_results"
BANK = "exams.template.teacher_questions_bank"

_AVAILABLE = [
    _t(
        "«Mövcud imtahanlar» səhifəsi hələlik bağlıdır. İmtahanlarınızı kabinetdən başlaya bilərsiniz.",
        "The “Available exams” page is closed for now. You can start your exams from your dashboard.",
        "Страница «Доступные экзамены» пока закрыта. Начать экзамены можно из личного кабинета.",
        "«Mevcut sınavlar» sayfası şimdilik kapalı. Sınavlarınızı panelinizden başlatabilirsiniz.",
    ),
]

_LABEL = [
    _t("Variant %%(n)s", "Option %%(n)s", "Вариант %%(n)s", "Seçenek %%(n)s"),
]

_PICKER = [
    _t("Axtarış", "Search", "Поиск", "Arama"),
    _t(
        "Axtarışı dəyişin və ya filtrləri sıfırlayın.",
        "Change the search or reset the filters.",
        "Измените запрос или сбросьте фильтры.",
        "Aramayı değiştirin veya filtreleri sıfırlayın.",
    ),
    _t("Bank axtar…", "Search banks…", "Поиск банка…", "Banka ara…"),
    _t("Bank seçin", "Choose a bank", "Выберите банк", "Banka seçin"),
    _t("Bank və filtrlər", "Bank and filters", "Банк и фильтры", "Banka ve filtreler"),
    _t("Bank xülasəsi", "Bank summary", "Сводка по банку", "Banka özeti"),
    _t("Bankdan sual əlavə et", "Add questions from a bank", "Добавить вопросы из банка", "Bankadan soru ekle"),
    _t(
        "Bu imtahanın tipinə uyğun bank tapılmadı. Sual bankları kitabxanasında yeni bank yaradın və ya "
        "sizinlə paylaşılmasını xahiş edin.",
        "No bank matches this exam's type. Create a new bank in the question bank library or ask a colleague "
        "to share one with you.",
        "Нет банка, подходящего к типу этого экзамена. Создайте новый банк в библиотеке банков вопросов или "
        "попросите коллегу поделиться банком.",
        "Bu sınavın türüne uygun banka bulunamadı. Soru bankası kitaplığında yeni bir banka oluşturun veya "
        "sizinle paylaşılmasını isteyin.",
    ),
    _t("Bu səhifədəkiləri seç", "Select this page", "Выбрать на этой странице", "Bu sayfadakileri seç"),
    _t(
        "Bütün %(n)s sualı seç", "Select all %(n)s questions", "Выбрать все вопросы (%(n)s)", "%(n)s sorunun tümünü seç"
    ),
    _t("Bütün dillər", "All languages", "Все языки", "Tüm diller"),
    _t("Dil", "Language", "Язык", "Dil"),
    _t("Dil üzrə süz", "Filter by language", "Фильтр по языку", "Dile göre filtrele"),
    _t("Düzgün", "Correct", "Верный", "Doğru"),
    _t("Filtrləri sıfırla", "Reset filters", "Сбросить фильтры", "Filtreleri sıfırla"),
    _t(
        "Filtrlərə uyğun sual tapılmadı",
        "No questions match the filters",
        "Нет вопросов, подходящих под фильтры",
        "Filtrelere uyan soru bulunamadı",
    ),
    _t("Hamısı", "All", "Все", "Tümü"),
    _t(
        "Bu bankda uyğun sual yoxdur",
        "This bank has no matching questions",
        "В этом банке нет подходящих вопросов",
        "Bu bankta uygun soru yok",
    ),
    _t(
        "Başqa bank seçin və ya kitabxanada bu banka sual əlavə edin.",
        "Choose another bank or add questions to this bank in the library.",
        "Выберите другой банк или добавьте вопросы в этот банк в библиотеке.",
        "Başka bir banka seçin veya kütüphanede bu bankaya soru ekleyin.",
    ),
    _t("Heç bir sual seçilməyib", "No questions selected", "Вопросы не выбраны", "Hiç soru seçilmedi"),
    _t(
        "Kitabxanadakı sual bankından sual seçib bu imtahana əlavə edin. Yalnız test bankları göstərilir.",
        "Pick questions from a library question bank and add them to this exam. Only test banks are shown.",
        "Выберите вопросы из банка в библиотеке и добавьте их в этот экзамен. Показаны только тестовые банки.",
        "Kitaplıktaki bir soru bankasından soru seçip bu sınava ekleyin. Yalnızca test bankaları gösterilir.",
    ),
    _t(
        "Kitabxanadakı sual bankından sual seçib bu imtahana əlavə edin. Yalnız yazılı sual bankları göstərilir.",
        "Pick questions from a library question bank and add them to this exam. Only written question banks "
        "are shown.",
        "Выберите вопросы из банка в библиотеке и добавьте их в этот экзамен. Показаны только банки письменных "
        "вопросов.",
        "Kitaplıktaki bir soru bankasından soru seçip bu sınava ekleyin. Yalnızca yazılı soru bankaları " "gösterilir.",
    ),
    _t(
        "Mövcud bankdan sual əlavə et",
        "Add questions from an existing bank",
        "Добавить вопросы из существующего банка",
        "Mevcut bankadan soru ekle",
    ),
    _t("Növbəti", "Next", "Далее", "Sonraki"),
    _t("Seçilənləri əlavə et", "Add selected", "Добавить выбранные", "Seçilenleri ekle"),
    _t("Seçim", "Selection", "Выбор", "Seçim"),
    _t("Sual banklarına keç", "Go to question banks", "Перейти к банкам вопросов", "Soru bankalarına git"),
    _t("Sual bankı", "Question bank", "Банк вопросов", "Soru bankası"),
    _t("Sual mətnində axtar", "Search question text", "Поиск по тексту вопроса", "Soru metninde ara"),
    _t(
        "Sualları görmək üçün yuxarıdan sual bankını seçin — sonra axtarış və filtrlərlə daraldın.",
        "Choose a question bank above to see its questions, then narrow them down with search and filters.",
        "Выберите банк вопросов выше, чтобы увидеть вопросы, затем сузьте список поиском и фильтрами.",
        "Soruları görmek için yukarıdan bir soru bankası seçin, ardından arama ve filtrelerle daraltın.",
    ),
    _t("Səhifələr", "Pages", "Страницы", "Sayfalar"),
    _t(
        "Səhifəni dəyişəndə seçim sıfırlanır — hamısını əlavə etmək üçün «Bütün sualları seç» düyməsindən "
        "istifadə edin.",
        "Changing the page clears the selection — to add everything, use “Select all questions”.",
        "При смене страницы выбор сбрасывается — чтобы добавить всё, используйте «Выбрать все вопросы».",
        "Sayfa değişince seçim sıfırlanır — tümünü eklemek için «Tüm soruları seç» düğmesini kullanın.",
    ),
    _t("Tapılan suallar", "Questions found", "Найденные вопросы", "Bulunan sorular"),
    _t("Test sualı", "Test question", "Тестовый вопрос", "Test sorusu"),
    _t("Təmizlə", "Clear", "Очистить", "Temizle"),
    _t("Uyğun bank yoxdur", "No matching bank", "Нет подходящего банка", "Uygun banka yok"),
    _t(
        "Uyğun sual bankı yoxdur",
        "No matching question bank",
        "Нет подходящего банка вопросов",
        "Uygun soru bankası yok",
    ),
    _t("Variant yoxdur", "No options", "Нет вариантов", "Seçenek yok"),
    _t("Variantlar", "Options", "Варианты", "Seçenekler"),
    _t("Yazılı sual", "Written question", "Письменный вопрос", "Yazılı soru"),
    _t("{n} sual seçildi", "{n} questions selected", "Выбрано вопросов: {n}", "{n} soru seçildi"),
    _t("Çətinlik", "Difficulty", "Сложность", "Zorluk"),
    _t("İmtahana qayıt", "Back to exam", "Назад к экзамену", "Sınava dön"),
    _t("Əvvəl bank seçin", "Choose a bank first", "Сначала выберите банк", "Önce bir banka seçin"),
    _t("Əvvəlki", "Previous", "Назад", "Önceki"),
]

_LANGUAGES = [
    _t("Aktiv", "Active", "Активен", "Aktif"),
    _t("Aktiv et", "Activate", "Активировать", "Etkinleştir"),
    _t("Aktiv sual", "Active questions", "Активные вопросы", "Aktif soru"),
    _t(
        "Boş qalsa dilin adı göstərilir.",
        "If left empty, the language name is shown.",
        "Если оставить пустым, показывается название языка.",
        "Boş bırakılırsa dilin adı gösterilir.",
    ),
    _t(
        "Bütün dəstəklənən dillər artıq əlavə olunub.",
        "All supported languages have already been added.",
        "Все поддерживаемые языки уже добавлены.",
        "Desteklenen tüm diller zaten eklendi.",
    ),
    _t("Deaktiv", "Inactive", "Неактивен", "Pasif"),
    _t(
        "Deaktiv dil tələbəyə təklif olunmur; sualları silinmir.",
        "An inactive language is not offered to students; its questions are kept.",
        "Неактивный язык не предлагается студентам; его вопросы не удаляются.",
        "Pasif dil öğrenciye sunulmaz; soruları silinmez.",
    ),
    _t("Deaktiv et", "Deactivate", "Деактивировать", "Devre dışı bırak"),
    _t("Dil", "Language", "Язык", "Dil"),
    _t("Dil variantları", "Language versions", "Языковые версии", "Dil sürümleri"),
    _t(
        "Dil variantını deaktiv et",
        "Deactivate language version",
        "Деактивировать языковую версию",
        "Dil sürümünü devre dışı bırak",
    ),
    _t("Dil əlavə et", "Add language", "Добавить язык", "Dil ekle"),
    _t("Dillər", "Languages", "Языки", "Diller"),
    _t("Göstəriş adı", "Display name", "Отображаемое название", "Görünen ad"),
    _t("Hələ dil variantı yoxdur", "No language versions yet", "Языковых версий пока нет", "Henüz dil sürümü yok"),
    _t("Mövcud dillər", "Current languages", "Текущие языки", "Mevcut diller"),
    _t(
        "Sağdakı formadan ilk dili əlavə edin — sonra bu dilə sual yükləyə bilərsiniz.",
        "Add the first language with the form on the right — then you can upload questions in it.",
        "Добавьте первый язык с помощью формы справа — затем в него можно загружать вопросы.",
        "Sağdaki formdan ilk dili ekleyin — ardından bu dile soru yükleyebilirsiniz.",
    ),
    _t("Status", "Status", "Статус", "Durum"),
    _t(
        "Tələbə imtahana başlayanda aktiv dillərdən birini seçir və yalnız həmin dilin sualları yüklənir.",
        "When starting the exam, the student chooses one of the active languages and only that language's "
        "questions are loaded.",
        "Начиная экзамен, студент выбирает один из активных языков, и загружаются только вопросы на этом языке.",
        "Öğrenci sınava başlarken aktif dillerden birini seçer ve yalnızca o dilin soruları yüklenir.",
    ),
    _t("Yeni dil əlavə et", "Add a new language", "Добавить новый язык", "Yeni dil ekle"),
    _t("istəyə bağlı", "optional", "необязательно", "isteğe bağlı"),
    _t(
        "məs. Azərbaycan (2024 buraxılış)",
        "e.g. Azerbaijani (2024 edition)",
        "напр. Азербайджанский (выпуск 2024)",
        "örn. Azerbaycanca (2024 baskısı)",
    ),
    _t(
        "«%(name)s» deaktiv edilsin? Tələbələr bu dildə imtahana başlaya bilməyəcək. Suallar silinmir — "
        "istənilən vaxt yenidən aktiv edə bilərsiniz.",
        "Deactivate “%(name)s”? Students will not be able to start the exam in this language. Questions are "
        "kept — you can reactivate it at any time.",
        "Деактивировать «%(name)s»? Студенты не смогут начать экзамен на этом языке. Вопросы не удаляются — "
        "язык можно снова активировать в любое время.",
        "«%(name)s» devre dışı bırakılsın mı? Öğrenciler bu dilde sınava başlayamayacak. Sorular silinmez — "
        "istediğiniz zaman yeniden etkinleştirebilirsiniz.",
    ),
    _t("«%(name)s» dilini aktiv et", "Activate “%(name)s”", "Активировать «%(name)s»", "«%(name)s» dilini etkinleştir"),
    _t(
        "«%(name)s» dilini deaktiv et",
        "Deactivate “%(name)s”",
        "Деактивировать «%(name)s»",
        "«%(name)s» dilini devre dışı bırak",
    ),
    _t("İmtahana qayıt", "Back to exam", "Назад к экзамену", "Sınava dön"),
    _t(
        "Əlavə olunan dil dərhal aktiv olur.",
        "A newly added language is active immediately.",
        "Добавленный язык сразу становится активным.",
        "Eklenen dil hemen aktif olur.",
    ),
    _t("Əməliyyat", "Action", "Действие", "İşlem"),
]

_FORM = [
    _t(
        "Bu fayl növü qəbul olunmur — siyahıdakı formatlardan birini seçin.",
        "This file type is not accepted — choose one of the listed formats.",
        "Этот тип файла не принимается — выберите один из указанных форматов.",
        "Bu dosya türü kabul edilmiyor — listedeki biçimlerden birini seçin.",
    ),
    _t("Cavab", "Answer", "Ответ", "Cevap"),
    _t("Düzgün cavab", "Correct answer", "Правильный ответ", "Doğru cevap"),
    _t(
        "Fayl çox böyükdür — ən çox {max} MB ola bilər.",
        "The file is too large — the limit is {max} MB.",
        "Файл слишком большой — максимум {max} МБ.",
        "Dosya çok büyük — en fazla {max} MB olabilir.",
    ),
    _t(
        "JPG, PNG, GIF, WEBP · ən çox 10 MB",
        "JPG, PNG, GIF, WEBP · up to 10 MB",
        "JPG, PNG, GIF, WEBP · до 10 МБ",
        "JPG, PNG, GIF, WEBP · en fazla 10 MB",
    ),
    _t(
        "MP4, WEBM, MOV · ən çox 30 MB",
        "MP4, WEBM, MOV · up to 30 MB",
        "MP4, WEBM, MOV · до 30 МБ",
        "MP4, WEBM, MOV · en fazla 30 MB",
    ),
    _t("Media", "Media", "Медиа", "Medya"),
    _t("Parametrlər", "Settings", "Параметры", "Ayarlar"),
    _t("Seçilmiş videonu götür", "Remove selected video", "Убрать выбранное видео", "Seçilen videoyu kaldır"),
    _t("Seçilmiş şəkli götür", "Remove selected image", "Убрать выбранное изображение", "Seçilen görseli kaldır"),
    _t("Sual", "Question", "Вопрос", "Soru"),
    _t("Video seçin", "Choose a video", "Выберите видео", "Video seçin"),
    _t("istəyə bağlı", "optional", "необязательно", "isteğe bağlı"),
    _t(
        "və ya faylı bura sürüşdürüb buraxın",
        "or drag and drop the file here",
        "или перетащите файл сюда",
        "veya dosyayı buraya sürükleyip bırakın",
    ),
    _t("İmtahana qayıt", "Back to exam", "Назад к экзамену", "Sınava dön"),
    _t("Şəkil seçin", "Choose an image", "Выберите изображение", "Görsel seçin"),
]

_RESULTS = [
    _t("Ad Soyad", "Full name", "Имя и фамилия", "Ad Soyad"),
    _t("Ad gizli qalacaq müddət", "Time the name stays hidden", "Время, пока имя скрыто", "Adın gizli kalacağı süre"),
    _t(
        "Ad, soyad və ya istifadəçi adı",
        "First name, last name or username",
        "Имя, фамилия или имя пользователя",
        "Ad, soyad veya kullanıcı adı",
    ),
    _t("Aktiv", "Active", "Активен", "Aktif"),
    _t("Axtarış", "Search", "Поиск", "Arama"),
    _t(
        "Axtarışı dəyişin və ya filtrləri sıfırlayın.",
        "Change the search or reset the filters.",
        "Измените запрос или сбросьте фильтры.",
        "Aramayı değiştirin veya filtreleri sıfırlayın.",
    ),
    _t("Bal", "Score", "Балл", "Puan"),
    _t("Başlama", "Start", "Начало", "Başlangıç"),
    _t("Başlama: -dan", "Started from", "Начало: с", "Başlangıç: itibaren"),
    _t("Başlama: -dək", "Started until", "Начало: по", "Başlangıç: kadar"),
    _t("Bitmə", "Finish", "Окончание", "Bitiş"),
    _t("Cavabsız", "Unanswered", "Без ответа", "Cevapsız"),
    _t("Cəhdləri sil", "Delete attempts", "Удалить попытки", "Denemeleri sil"),
    _t("Deaktiv", "Inactive", "Неактивен", "Pasif"),
    _t("Düzgün", "Correct", "Верно", "Doğru"),
    _t(
        "Düzgün / verilmiş sual",
        "Correct / questions given",
        "Верно / выдано вопросов",
        "Doğru / verilen soru",
    ),
    _t("E-poçt", "Email", "Эл. почта", "E-posta"),
    _t("Excel-ə yüklə", "Export to Excel", "Выгрузить в Excel", "Excel'e aktar"),
    _t("Faiz", "Percent", "Процент", "Yüzde"),
    _t("Filtrlər", "Filters", "Фильтры", "Filtreler"),
    _t("Filtrləri sıfırla", "Reset filters", "Сбросить фильтры", "Filtreleri sıfırla"),
    _t(
        "Filtrlərə uyğun nəticə yoxdur",
        "No results match the filters",
        "Нет результатов, подходящих под фильтры",
        "Filtrelere uyan sonuç yok",
    ),
    _t("Gözləyir", "Pending", "Ожидает", "Bekliyor"),
    _t("Hamısı", "All", "Все", "Tümü"),
    _t("Hələ iştirakçı yoxdur", "No participants yet", "Участников пока нет", "Henüz katılımcı yok"),
    _t("Ləğv et", "Cancel", "Отмена", "İptal"),
    _t("Maks. bal", "Max score", "Макс. балл", "Maks. puan"),
    _t("Müddət", "Duration", "Длительность", "Süre"),
    _t("Qrup", "Group", "Группа", "Grup"),
    _t("Qrup axtar…", "Search groups…", "Поиск группы…", "Grup ara…"),
    _t("Seçim", "Selection", "Выбор", "Seçim"),
    _t("Status", "Status", "Статус", "Durum"),
    _t("Sınaq cəhdləri", "Exam attempts", "Попытки экзамена", "Sınav denemeleri"),
    _t("Səhv", "Wrong", "Неверно", "Yanlış"),
    _t("Səhv / verilmiş sual", "Wrong / questions given", "Неверно / выдано вопросов", "Yanlış / verilen soru"),
    _t(
        "Tarix imtahana başlama gününə görə süzülür (gg.aa.iiii).",
        "Dates filter by the day the exam was started (dd.mm.yyyy).",
        "Даты фильтруются по дню начала экзамена (дд.мм.гггг).",
        "Tarih, sınava başlama gününe göre filtrelenir (gg.aa.yyyy).",
    ),
    _t(
        "Tarixi gg.aa.iiii formatında yazın (məs. 06.10.2026).",
        "Enter the date as dd.mm.yyyy (e.g. 06.10.2026).",
        "Введите дату в формате дд.мм.гггг (напр. 06.10.2026).",
        "Tarihi gg.aa.yyyy biçiminde yazın (örn. 06.10.2026).",
    ),
    _t(
        "Tələbələr imtahanı verdikcə nəticələr burada görünəcək.",
        "Results will appear here as students take the exam.",
        "Результаты появятся здесь по мере прохождения экзамена студентами.",
        "Öğrenciler sınava girdikçe sonuçlar burada görünecek.",
    ),
    _t("Uyğun qrup yoxdur", "No matching group", "Нет подходящей группы", "Uygun grup yok"),
    _t("Xülasə", "Summary", "Сводка", "Özet"),
    _t(
        "Yenidən yoxlama üçün qalan vaxt",
        "Time left for re-checking",
        "Время, оставшееся на перепроверку",
        "Yeniden kontrol için kalan süre",
    ),
    _t("Yoxlanma", "Review status", "Статус проверки", "Kontrol durumu"),
    _t("Yoxlanılıb", "Checked", "Проверено", "Kontrol edildi"),
    _t(
        "Yükləmək üçün nəticə yoxdur.",
        "There are no results to export.",
        "Нет результатов для выгрузки.",
        "Dışa aktarılacak sonuç yok.",
    ),
    _t("avto", "auto", "авто", "otomatik"),
    _t("gg.aa.iiii", "dd.mm.yyyy", "дд.мм.гггг", "gg.aa.yyyy"),
    _t("İstifadəçi adı", "Username", "Имя пользователя", "Kullanıcı adı"),
    _t("İştirakçı", "Participant", "Участник", "Katılımcı"),
    _t(
        "İştirakçıların nəticələri · Müəllim: %(teacher)s (@%(handle)s)",
        "Participant results · Teacher: %(teacher)s (@%(handle)s)",
        "Результаты участников · Преподаватель: %(teacher)s (@%(handle)s)",
        "Katılımcı sonuçları · Öğretmen: %(teacher)s (@%(handle)s)",
    ),
]

_BANK = [
    _t("Aktiv", "Active", "Активные", "Aktif"),
    _t("Axtarış", "Search", "Поиск", "Arama"),
    _t("Axtarış və süzgəclər", "Search and filters", "Поиск и фильтры", "Arama ve filtreler"),
    _t(
        "Bank və içindəki bütün suallar həmişəlik silinir.",
        "The bank and all its questions are deleted permanently.",
        "Банк и все его вопросы удаляются безвозвратно.",
        "Banka ve içindeki tüm sorular kalıcı olarak silinir.",
    ),
    _t(
        "Başqa söz yoxlayın və ya süzgəcləri dəyişin.",
        "Try another word or change the filters.",
        "Попробуйте другое слово или измените фильтры.",
        "Başka bir kelime deneyin veya filtreleri değiştirin.",
    ),
    _t(
        "Bu əməliyyatlar geri qaytarılmır.",
        "These actions cannot be undone.",
        "Эти действия нельзя отменить.",
        "Bu işlemler geri alınamaz.",
    ),
    _t("Cəmi", "Total", "Всего", "Toplam"),
    _t("Deaktiv", "Inactive", "Неактивные", "Pasif"),
    _t("Digər əlavə üsulları", "Other ways to add", "Другие способы добавления", "Diğer ekleme yolları"),
    _t("Düzgün", "Correct", "Верный", "Doğru"),
    _t("Hamısını sil", "Delete all", "Удалить всё", "Tümünü sil"),
    _t("Keyfiyyət", "Quality", "Качество", "Kalite"),
    _t("Keyfiyyət hesabatı (Excel)", "Quality report (Excel)", "Отчёт о качестве (Excel)", "Kalite raporu (Excel)"),
    _t("Keyfiyyət süzgəci", "Quality filter", "Фильтр качества", "Kalite filtresi"),
    _t("Seçilmiş suallar", "Selected questions", "Выбранные вопросы", "Seçilen sorular"),
    _t("Status", "Status", "Статус", "Durum"),
    _t(
        "Sual, blok və ya variant mətni",
        "Question, block or option text",
        "Текст вопроса, блока или варианта",
        "Soru, blok veya seçenek metni",
    ),
    _t("Suallar", "Questions", "Вопросы", "Sorular"),
    _t("Suallar (Word)", "Questions (Word)", "Вопросы (Word)", "Sorular (Word)"),
    _t("Sıralama", "Sort", "Сортировка", "Sıralama"),
    _t("Təhlükəli əməliyyatlar", "Danger zone", "Опасная зона", "Tehlikeli işlemler"),
    _t(
        "Təsdiq üçün imtahanın adını yazın",
        "To confirm, type the exam name",
        "Для подтверждения введите название экзамена",
        "Onaylamak için sınavın adını yazın",
    ),
    _t("Xülasə", "Summary", "Сводка", "Özet"),
    _t("Yüklə", "Download", "Скачать", "İndir"),
    _t(
        "«Sual əlavə et» ilə tək-tək və ya toplu əlavə ilə fayldan yükləyin.",
        "Use “Add question” one at a time, or bulk add to upload from a file.",
        "Добавляйте по одному через «Добавить вопрос» или загрузите из файла массовым добавлением.",
        "«Soru ekle» ile tek tek ekleyin veya toplu ekleme ile dosyadan yükleyin.",
    ),
    _t(
        "İmtahanın bütün sualları həmişəlik silinir. Təsdiq üçün imtahanın adını yazmaq lazımdır.",
        "All of the exam's questions are deleted permanently. You will need to type the exam name to confirm.",
        "Все вопросы экзамена удаляются безвозвратно. Для подтверждения нужно ввести название экзамена.",
        "Sınavın tüm soruları kalıcı olarak silinir. Onaylamak için sınavın adını yazmanız gerekir.",
    ),
    _t(
        "İmtahanın {count} sualı həmişəlik silinəcək. Bu əməliyyat geri qaytarılmır.",
        "{count} questions of this exam will be deleted permanently. This cannot be undone.",
        "Вопросы экзамена ({count}) будут удалены безвозвратно. Это действие нельзя отменить.",
        "Sınavın {count} sorusu kalıcı olarak silinecek. Bu işlem geri alınamaz.",
    ),
    _t("Ən köhnə", "Oldest", "Сначала старые", "En eski"),
    _t("Ən yeni", "Newest", "Сначала новые", "En yeni"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AVAILABLE: {row["az"]: row for row in _AVAILABLE},
    LABEL: {row["az"]: row for row in _LABEL},
    PICKER: {row["az"]: row for row in _PICKER},
    LANGUAGES: {row["az"]: row for row in _LANGUAGES},
    FORM: {row["az"]: row for row in _FORM},
    RESULTS: {row["az"]: row for row in _RESULTS},
    BANK: {row["az"]: row for row in _BANK},
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
