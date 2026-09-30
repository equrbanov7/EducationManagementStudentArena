#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 «Sorğu qurucusu» (SRV): ümumi sorğular, sual redaktoru,
«Sorğular» inbox-u, respondent forması, qapı siyasətləri, nəticələr və CSV ixracı.

Kontekstlər: ``surveys.builder``, ``surveys.inbox``, ``surveys.respond``, ``surveys.export``,
``surveys.notify``, ``surveys.form``, ``surveys.choice``, ``surveys.model``, ``surveys.student``,
``surveys.cabinet``, ``profile.sidebar``. Mənbə dil AZ-dır (msgid = az mətni).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_srv_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

B = "surveys.builder"
I = "surveys.inbox"  # noqa: E741
R = "surveys.respond"
X = "surveys.export"
N = "surveys.notify"
F = "surveys.form"
C = "surveys.choice"
M = "surveys.model"
S = "surveys.student"
K = "surveys.cabinet"
P = "profile.sidebar"

# (kontekst, az msgid, en, ru, tr)
ROWS = [
    # ── profile.sidebar ──────────────────────────────────────────────────
    (P, "Sorğular", "Surveys", "Опросы", "Anketler"),
    (P, "Sorğu qurucusu", "Survey builder", "Конструктор опросов", "Anket oluşturucu"),
    # ── surveys.choice ───────────────────────────────────────────────────
    (C, "Tək seçim", "Single choice", "Один вариант", "Tek seçim"),
    (C, "Çox seçim", "Multiple choice", "Несколько вариантов", "Çoklu seçim"),
    (C, "Reytinq / NPS (0–10)", "Rating / NPS (0–10)", "Оценка / NPS (0–10)", "Puan / NPS (0–10)"),
    (C, "Bəli / Xeyr", "Yes / No", "Да / Нет", "Evet / Hayır"),
    (C, "Qısa mətn", "Short text", "Короткий текст", "Kısa metin"),
    (C, "Müəllim qiymətləndirməsi", "Teacher evaluation", "Оценка преподавателя", "Öğretim elemanı değerlendirmesi"),
    (C, "Ümumi sorğu", "General survey", "Общий опрос", "Genel anket"),
    (C, "Fənn / kurs rəyi", "Subject / course feedback", "Отзыв о предмете / курсе", "Ders geri bildirimi"),
    (C, "Tədbir / digər", "Event / other", "Мероприятие / другое", "Etkinlik / diğer"),
    (C, "Tələbələr", "Students", "Студенты", "Öğrenciler"),
    (C, "Müəllimlər", "Teachers", "Преподаватели", "Öğretim elemanları"),
    (C, "İnzibati heyət", "Administrative staff", "Административный персонал", "İdari personel"),
    (C, "Hamı", "Everyone", "Все", "Herkes"),
    (
        C,
        "Doldurulmayınca kabinet bağlıdır",
        "Cabinet blocked until completed",
        "Кабинет закрыт до заполнения",
        "Doldurulana kadar panel kapalı",
    ),
    (C, "Bir dəfə keçmək olar", "May skip once", "Можно пропустить один раз", "Bir kez atlanabilir"),
    (
        C,
        "«Sonra doldur» möhləti (gün)",
        "“Fill in later” grace period (days)",
        "Отсрочка «Заполнить позже» (дни)",
        "“Sonra doldur” süresi (gün)",
    ),
    (C, "Dərc olunub", "Published", "Опубликован", "Yayında"),
    (C, "Arxivdə", "Archived", "В архиве", "Arşivde"),
    # ── surveys.model ────────────────────────────────────────────────────
    (M, "sorğu", "survey", "опрос", "anket"),
    (M, "sorğular", "surveys", "опросы", "anketler"),
    (M, "sorğu bölməsi", "survey section", "раздел опроса", "anket bölümü"),
    (M, "sorğu bölmələri", "survey sections", "разделы опроса", "anket bölümleri"),
    (M, "sorğu iştirakı", "survey participation", "участие в опросе", "anket katılımı"),
    (M, "sorğu iştirakları", "survey participations", "участия в опросах", "anket katılımları"),
    (M, "sorğu cavabı (forma)", "survey response (form)", "ответ на опрос (форма)", "anket yanıtı (form)"),
    (M, "sorğu cavabları (forma)", "survey responses (forms)", "ответы на опрос (формы)", "anket yanıtları (formlar)"),
    (M, "sual cavabı", "question answer", "ответ на вопрос", "soru yanıtı"),
    (M, "sual cavabları", "question answers", "ответы на вопросы", "soru yanıtları"),
    (
        M,
        "dərc gözləyən sorğu cavabı",
        "survey response awaiting publication",
        "ответ на опрос, ожидающий публикации",
        "yayın bekleyen anket yanıtı",
    ),
    (
        M,
        "dərc gözləyən sorğu cavabları",
        "survey responses awaiting publication",
        "ответы на опрос, ожидающие публикации",
        "yayın bekleyen anket yanıtları",
    ),
    (M, "sorğu qaralaması", "survey draft", "черновик опроса", "anket taslağı"),
    (M, "sorğu qaralamaları", "survey drafts", "черновики опросов", "anket taslakları"),
    (M, "sorğu keçidi", "survey skip", "пропуск опроса", "anket atlama"),
    (M, "sorğu keçidləri", "survey skips", "пропуски опросов", "anket atlamaları"),
    # ── surveys.form ─────────────────────────────────────────────────────
    (
        F,
        "Seçim etibarsızdır — səhifəni yeniləyin.",
        "Invalid choice — please reload the page.",
        "Недопустимый вариант — обновите страницу.",
        "Geçersiz seçim — sayfayı yenileyin.",
    ),
    (F, "Ən azı %(n)s seçim edin.", "Select at least %(n)s.", "Выберите не менее %(n)s.", "En az %(n)s seçim yapın."),
    (
        F,
        "Ən çoxu %(n)s seçim edə bilərsiniz.",
        "You can select at most %(n)s.",
        "Можно выбрать не более %(n)s.",
        "En fazla %(n)s seçim yapabilirsiniz.",
    ),
    # ── surveys.notify ───────────────────────────────────────────────────
    (N, "Yeni sorğu: %(title)s", "New survey: %(title)s", "Новый опрос: %(title)s", "Yeni anket: %(title)s"),
    (
        N,
        "Məcburi sorğu — son tarix %(day)s. Kabinetdə «Sorğular» bölməsinə keçin.",
        "Mandatory survey — deadline %(day)s. Open “Surveys” in your cabinet.",
        "Обязательный опрос — срок до %(day)s. Откройте раздел «Опросы» в кабинете.",
        "Zorunlu anket — son tarih %(day)s. Paneldeki “Anketler” bölümüne gidin.",
    ),
    (
        N,
        "Könüllü sorğu — son tarix %(day)s. Fikriniz bizim üçün vacibdir.",
        "Voluntary survey — deadline %(day)s. Your opinion matters to us.",
        "Добровольный опрос — срок до %(day)s. Ваше мнение важно для нас.",
        "Gönüllü anket — son tarih %(day)s. Görüşünüz bizim için önemli.",
    ),
    # ── surveys.cabinet ──────────────────────────────────────────────────
    (K, "Sorğu qurucusu", "Survey builder", "Конструктор опросов", "Anket oluşturucu"),
    (K, "Sual dəsti", "Question set", "Набор вопросов", "Soru seti"),
    (
        K,
        "Sualları yazmaq, yeni sual dəsti yaratmaq və ya başqa auditoriya (müəllim, heyət, hamı) üçün sorğu açmaq —",
        "To write questions, create a new question set or open a survey for another audience (teachers, staff, "
        "everyone) —",
        "Чтобы написать вопросы, создать новый набор вопросов или открыть опрос для другой аудитории "
        "(преподаватели, персонал, все) —",
        "Soruları yazmak, yeni soru seti oluşturmak veya başka bir hedef kitle (öğretim elemanları, personel, "
        "herkes) için anket açmak —",
    ),
    # ── surveys.student ──────────────────────────────────────────────────
    (S, "Sorğular", "Surveys", "Опросы", "Anketler"),
    (S, "Sizi gözləyən sorğular", "Surveys waiting for you", "Опросы, ожидающие вас", "Sizi bekleyen anketler"),
    (
        S,
        "Məcburi sorğu doldurulmayınca kabinet bağlı qala bilər. İmtahan səhifələri heç vaxt bağlanmır.",
        "Until a mandatory survey is completed your cabinet may stay locked. Exam pages are never blocked.",
        "Пока обязательный опрос не заполнен, кабинет может оставаться закрытым. Страницы экзаменов никогда "
        "не блокируются.",
        "Zorunlu anket doldurulmadan panel kapalı kalabilir. Sınav sayfaları asla engellenmez.",
    ),
    (S, "Məcburi", "Mandatory", "Обязательный", "Zorunlu"),
    (S, "Könüllü", "Voluntary", "Добровольный", "Gönüllü"),
    (S, "Anonim", "Anonymous", "Анонимный", "Anonim"),
    (
        S,
        "Bu sorğunu artıq bir dəfə keçmisiniz — kabinetə daxil olmaq üçün onu doldurun.",
        "You have already skipped this survey once — complete it to enter your cabinet.",
        "Вы уже один раз пропустили этот опрос — заполните его, чтобы войти в кабинет.",
        "Bu anketi zaten bir kez atladınız — panele girmek için doldurun.",
    ),
    (
        S,
        "Bu dəfə keçə bilərsiniz, amma növbəti dəfə sorğunu doldurmadan kabinetə daxil ola bilməyəcəksiniz.",
        "You may skip it this time, but next time you will not be able to enter your cabinet without completing "
        "the survey.",
        "Сейчас можно пропустить, но в следующий раз вы не сможете войти в кабинет, не заполнив опрос.",
        "Bu sefer atlayabilirsiniz, ancak bir dahaki sefere anketi doldurmadan panele giremeyeceksiniz.",
    ),
    (
        S,
        "Doldurulmayınca kabinet bağlı qalır.",
        "The cabinet stays locked until it is completed.",
        "Кабинет остаётся закрытым до заполнения.",
        "Doldurulana kadar panel kapalı kalır.",
    ),
    (S, "Bu dəfə keç", "Skip this time", "Пропустить в этот раз", "Bu sefer atla"),
    # ── surveys.inbox ────────────────────────────────────────────────────
    (
        I,
        "Baxış rejimində (başqa istifadəçinin profili) sorğular göstərilmir — sorğunu yalnız istifadəçinin özü "
        "doldura bilər.",
        "Surveys are not shown in view-as mode (another user's profile) — only the user can complete them.",
        "В режиме просмотра (профиль другого пользователя) опросы не показываются — заполнить их может только "
        "сам пользователь.",
        "Görüntüleme modunda (başka bir kullanıcının profili) anketler gösterilmez — anketi yalnızca kullanıcının "
        "kendisi doldurabilir.",
    ),
    (
        I,
        "Təşkilat konteksti tapılmadı.",
        "Organization context not found.",
        "Контекст организации не найден.",
        "Kurum bağlamı bulunamadı.",
    ),
    (
        I,
        "Universitetin sizə ünvanladığı sorğular. Məcburi sorğular doldurulmayınca kabinet bağlana bilər; anonim "
        "sorğularda cavabınız adınızla saxlanılmır.",
        "Surveys the university has addressed to you. Mandatory surveys may lock your cabinet until completed; in "
        "anonymous surveys your answer is not stored with your name.",
        "Опросы, адресованные вам университетом. Обязательные опросы могут закрыть кабинет до заполнения; в "
        "анонимных опросах ваш ответ не хранится с вашим именем.",
        "Üniversitenin size yönelttiği anketler. Zorunlu anketler doldurulana kadar paneli kilitleyebilir; anonim "
        "anketlerde yanıtınız adınızla saklanmaz.",
    ),
    (I, "Gözləyir: %(n)s", "Waiting: %(n)s", "Ожидают: %(n)s", "Bekleyen: %(n)s"),
    (I, "Gözləyən", "Pending", "Ожидают", "Bekleyen"),
    (
        I,
        "Müəllimlərin anonim qiymətləndirilməsi",
        "Anonymous teacher evaluation",
        "Анонимная оценка преподавателей",
        "Öğretim elemanlarının anonim değerlendirmesi",
    ),
    (I, "Anonim", "Anonymous", "Анонимно", "Anonim"),
    (I, "Adla", "Named", "С именем", "İsimli"),
    (I, "Məcburi", "Mandatory", "Обязательный", "Zorunlu"),
    (I, "Könüllü", "Voluntary", "Добровольный", "Gönüllü"),
    (
        I,
        "%(done)s / %(total)s tamamlanıb",
        "%(done)s / %(total)s completed",
        "%(done)s / %(total)s заполнено",
        "%(done)s / %(total)s tamamlandı",
    ),
    (I, "son tarix %(day)s", "deadline %(day)s", "срок до %(day)s", "son tarih %(day)s"),
    (I, "Davam et", "Continue", "Продолжить", "Devam et"),
    (
        I,
        "Bu sorğunu artıq bir dəfə keçmisiniz — növbəti girişdə kabinet onu doldurmadan açılmayacaq.",
        "You have already skipped this survey once — next time the cabinet will not open until you complete it.",
        "Вы уже один раз пропустили этот опрос — при следующем входе кабинет не откроется, пока вы его не "
        "заполните.",
        "Bu anketi zaten bir kez atladınız — bir sonraki girişte panel anket doldurulmadan açılmayacak.",
    ),
    (
        I,
        "Bir dəfə keçmək olar; növbəti dəfə sorğunu doldurmadan kabinetə daxil ola bilməyəcəksiniz.",
        "You may skip it once; next time you will not be able to enter your cabinet without completing it.",
        "Можно пропустить один раз; в следующий раз вы не сможете войти в кабинет, не заполнив опрос.",
        "Bir kez atlayabilirsiniz; bir dahaki sefere anketi doldurmadan panele giremeyeceksiniz.",
    ),
    (
        I,
        "Doldurulmayınca kabinet bağlı qalır.",
        "The cabinet stays locked until it is completed.",
        "Кабинет остаётся закрытым до заполнения.",
        "Doldurulana kadar panel kapalı kalır.",
    ),
    (
        I,
        "«Sonra doldur» imkanı %(day)s tarixinə qədərdir (hər dəfə 24 saat).",
        "“Fill in later” is available until %(day)s (24 hours each time).",
        "«Заполнить позже» доступно до %(day)s (каждый раз на 24 часа).",
        "“Sonra doldur” seçeneği %(day)s tarihine kadar geçerlidir (her seferinde 24 saat).",
    ),
    (I, "Doldur", "Fill in", "Заполнить", "Doldur"),
    (
        I,
        "Hazırda sizi gözləyən sorğu yoxdur.",
        "There are no surveys waiting for you right now.",
        "Сейчас нет ожидающих вас опросов.",
        "Şu anda sizi bekleyen anket yok.",
    ),
    (I, "Tamamlanmış", "Completed", "Заполненные", "Tamamlanan"),
    (I, "Bağlı", "Closed", "Закрытые", "Kapalı"),
    (I, "doldurulmayıb", "not completed", "не заполнен", "doldurulmadı"),
    # ── surveys.respond ──────────────────────────────────────────────────
    (R, "Sorğu naviqasiyası", "Survey navigation", "Навигация по опросу", "Anket gezinmesi"),
    (R, "Sorğular", "Surveys", "Опросы", "Anketler"),
    (R, "Anonim sorğu", "Anonymous survey", "Анонимный опрос", "Anonim anket"),
    (R, "Adla sorğu", "Named survey", "Именной опрос", "İsimli anket"),
    (R, "Məcburi", "Mandatory", "Обязательный", "Zorunlu"),
    (R, "Son tarix: %(day)s", "Deadline: %(day)s", "Срок: %(day)s", "Son tarih: %(day)s"),
    (
        R,
        "Cavabınız adınızla saxlanılmır: yalnız «doldurdu» qeydi qalır, nəticələr ən azı k cavab yığılanda və "
        "sorğu bağlandıqdan sonra ümumiləşdirilmiş şəkildə görünür. Yarımçıq cavablar yalnız bu brauzer tabında "
        "saxlanılır.",
        "Your answer is not stored with your name: only a “completed” mark remains, and results are shown in "
        "aggregate once at least k answers are collected and the survey is closed. Unfinished answers are kept "
        "only in this browser tab.",
        "Ваш ответ не хранится с вашим именем: остаётся лишь отметка «заполнено», а результаты показываются "
        "обобщённо, когда собрано не менее k ответов и опрос закрыт. Незавершённые ответы хранятся только в этой "
        "вкладке браузера.",
        "Yanıtınız adınızla saklanmaz: yalnızca “doldurdu” kaydı kalır; sonuçlar en az k yanıt toplandığında ve "
        "anket kapandıktan sonra toplu olarak görünür. Yarım kalan yanıtlar yalnızca bu tarayıcı sekmesinde "
        "saklanır.",
    ),
    (
        R,
        "Bu sorğu anonim deyil — cavablarınızı adınızla sorğunun idarəçiləri görür. Yarımçıq cavablar avtomatik "
        "saxlanılır.",
        "This survey is not anonymous — the survey managers see your answers with your name. Unfinished answers "
        "are saved automatically.",
        "Этот опрос не анонимный — администраторы опроса видят ваши ответы с вашим именем. Незавершённые ответы "
        "сохраняются автоматически.",
        "Bu anket anonim değildir — anket yöneticileri yanıtlarınızı adınızla görür. Yarım kalan yanıtlar "
        "otomatik kaydedilir.",
    ),
    (R, "0 / %(total)s cavablanıb", "0 / %(total)s answered", "0 / %(total)s отвечено", "0 / %(total)s yanıtlandı"),
    (R, "__N__ / __T__ cavablanıb", "__N__ / __T__ answered", "__N__ / __T__ отвечено", "__N__ / __T__ yanıtlandı"),
    (R, "Yadda saxlanıldı", "Saved", "Сохранено", "Kaydedildi"),
    (R, "Bu tabda saxlanıldı", "Saved in this tab", "Сохранено в этой вкладке", "Bu sekmede kaydedildi"),
    (R, "Bu sual məcburidir.", "This question is required.", "Этот вопрос обязателен.", "Bu soru zorunludur."),
    (R, "Ən azı __N__ seçim edin.", "Select at least __N__.", "Выберите не менее __N__.", "En az __N__ seçim yapın."),
    (
        R,
        "Ən çoxu __N__ seçim edə bilərsiniz.",
        "You can select at most __N__.",
        "Можно выбрать не более __N__.",
        "En fazla __N__ seçim yapabilirsiniz.",
    ),
    (
        R,
        "Bəzi suallar cavabsız qalıb və ya düzgün deyil — qırmızı ilə işarələnmiş sualları yoxlayın.",
        "Some questions are unanswered or invalid — check the questions marked in red.",
        "Некоторые вопросы остались без ответа или заполнены неверно — проверьте вопросы, отмеченные красным.",
        "Bazı sorular yanıtsız kaldı veya geçersiz — kırmızıyla işaretlenen soruları kontrol edin.",
    ),
    (R, "Anonim göndər", "Submit anonymously", "Отправить анонимно", "Anonim gönder"),
    (R, "Göndər", "Submit", "Отправить", "Gönder"),
    (
        R,
        "Göndərdikdən sonra cavabı dəyişmək mümkün deyil.",
        "Answers cannot be changed after submission.",
        "После отправки изменить ответ нельзя.",
        "Gönderdikten sonra yanıt değiştirilemez.",
    ),
    (R, "(məcburi)", "(required)", "(обязательно)", "(zorunlu)"),
    (
        R,
        "%(low)s–%(high)s variant seçin.",
        "Select %(low)s–%(high)s options.",
        "Выберите %(low)s–%(high)s вариантов.",
        "%(low)s–%(high)s seçenek seçin.",
    ),
    (
        R,
        "Ən azı %(low)s variant seçin.",
        "Select at least %(low)s options.",
        "Выберите не менее %(low)s вариантов.",
        "En az %(low)s seçenek seçin.",
    ),
    (
        R,
        "Ən çoxu %(high)s variant seçin.",
        "Select at most %(high)s options.",
        "Выберите не более %(high)s вариантов.",
        "En fazla %(high)s seçenek seçin.",
    ),
    (R, "Bəli", "Yes", "Да", "Evet"),
    (R, "Xeyr", "No", "Нет", "Hayır"),
    (R, "Heç ehtimal etmirəm", "Not at all likely", "Совсем маловероятно", "Hiç olası değil"),
    (R, "Mütləq", "Extremely likely", "Обязательно", "Kesinlikle"),
    (R, "Təşəkkür edirik!", "Thank you!", "Спасибо!", "Teşekkür ederiz!"),
    (
        R,
        "Cavabınız anonim şəkildə qeydə alındı. Nəticələr sorğu bağlandıqdan sonra ümumiləşdirilmiş şəkildə təhlil "
        "olunacaq.",
        "Your answer has been recorded anonymously. Results will be analysed in aggregate after the survey closes.",
        "Ваш ответ записан анонимно. Результаты будут проанализированы обобщённо после закрытия опроса.",
        "Yanıtınız anonim olarak kaydedildi. Sonuçlar anket kapandıktan sonra toplu olarak analiz edilecek.",
    ),
    (R, "Cavabınız qeydə alındı.", "Your answer has been recorded.", "Ваш ответ записан.", "Yanıtınız kaydedildi."),
    (R, "Digər sorğular", "Other surveys", "Другие опросы", "Diğer anketler"),
    (R, "Kabinetə qayıt", "Back to cabinet", "Вернуться в кабинет", "Panele dön"),
    (
        R,
        "Bu sorğu %(day)s tarixində açılacaq.",
        "This survey opens on %(day)s.",
        "Этот опрос откроется %(day)s.",
        "Bu anket %(day)s tarihinde açılacak.",
    ),
    (
        R,
        "Bu sorğu sizə ünvanlanmayıb.",
        "This survey is not addressed to you.",
        "Этот опрос адресован не вам.",
        "Bu anket size yönelik değil.",
    ),
    (
        R,
        "Bu sorğu artıq cavab qəbul etmir.",
        "This survey no longer accepts answers.",
        "Этот опрос больше не принимает ответы.",
        "Bu anket artık yanıt kabul etmiyor.",
    ),
    (R, "Sorğulara qayıt", "Back to surveys", "Вернуться к опросам", "Anketlere dön"),
    (
        R,
        "Sorğu artıq qəbul edilmir.",
        "The survey is no longer accepting answers.",
        "Опрос больше не принимается.",
        "Anket artık kabul edilmiyor.",
    ),
    (
        R,
        "Bu sorğunu artıq doldurmusunuz.",
        "You have already completed this survey.",
        "Вы уже заполнили этот опрос.",
        "Bu anketi zaten doldurdunuz.",
    ),
    (
        R,
        "Anonim sorğunun qaralaması yalnız brauzerdə saxlanır.",
        "Drafts of an anonymous survey are kept only in the browser.",
        "Черновик анонимного опроса хранится только в браузере.",
        "Anonim anketin taslağı yalnızca tarayıcıda saklanır.",
    ),
    (
        R,
        "Bu sorğunu keçmək mümkün deyil.",
        "This survey cannot be skipped.",
        "Этот опрос нельзя пропустить.",
        "Bu anket atlanamaz.",
    ),
    (
        R,
        "Bu sorğunu artıq bir dəfə keçmisiniz — kabinetə daxil olmaq üçün onu doldurun.",
        "You have already skipped this survey once — complete it to enter your cabinet.",
        "Вы уже один раз пропустили этот опрос — заполните его, чтобы войти в кабинет.",
        "Bu anketi zaten bir kez atladınız — panele girmek için doldurun.",
    ),
    (
        R,
        "Bu sorğu üçün möhlət yoxdur.",
        "There is no grace period for this survey.",
        "Для этого опроса нет отсрочки.",
        "Bu anket için erteleme süresi yok.",
    ),
    (
        R,
        "Möhlət müddəti bitib — sorğunu doldurmaq məcburidir.",
        "The grace period is over — completing the survey is mandatory.",
        "Срок отсрочки истёк — заполнение опроса обязательно.",
        "Erteleme süresi doldu — anketi doldurmak zorunludur.",
    ),
    (
        R,
        "Bu dəfə keçdiniz. Növbəti girişdə sorğunu doldurmadan kabinetə daxil ola bilməyəcəksiniz.",
        "You skipped it this time. Next time you will not be able to enter your cabinet without completing the "
        "survey.",
        "Вы пропустили опрос в этот раз. При следующем входе вы не сможете войти в кабинет, не заполнив его.",
        "Bu sefer atladınız. Bir sonraki girişte anketi doldurmadan panele giremeyeceksiniz.",
    ),
    (
        R,
        "Sorğunu 24 saat ərzində doldurmağı unutmayın.",
        "Remember to complete the survey within 24 hours.",
        "Не забудьте заполнить опрос в течение 24 часов.",
        "Anketi 24 saat içinde doldurmayı unutmayın.",
    ),
    # ── surveys.export ───────────────────────────────────────────────────
    (X, "Ad", "Name", "Имя", "Ad"),
    (X, "İstifadəçi adı", "Username", "Имя пользователя", "Kullanıcı adı"),
    (X, "Vaxt", "Time", "Время", "Zaman"),
    (X, "Sual", "Question", "Вопрос", "Soru"),
    (X, "Variant", "Option", "Вариант", "Seçenek"),
    (X, "Faiz / cavab", "Percent / answer", "Процент / ответ", "Yüzde / yanıt"),
    (X, "Orta", "Average", "Среднее", "Ortalama"),
    (X, "Cavab sayı", "Answers", "Количество ответов", "Yanıt sayısı"),
    (
        X,
        "Cavab sayı k-həddindən azdır — nəticələr gizlidir.",
        "Fewer answers than the k threshold — results are hidden.",
        "Ответов меньше порога k — результаты скрыты.",
        "Yanıt sayısı k eşiğinden az — sonuçlar gizli.",
    ),
    (
        X,
        "gizli (k-dan az cavab)",
        "hidden (fewer than k answers)",
        "скрыто (меньше k ответов)",
        "gizli (k'dan az yanıt)",
    ),
    (X, "açıq cavab", "open answer", "открытый ответ", "açık yanıt"),
    (
        X,
        "Sorğu nəticələrinin ixracı",
        "Survey results export",
        "Экспорт результатов опроса",
        "Anket sonuçlarının dışa aktarımı",
    ),
]

ROWS += [
    # ── surveys.builder (1/2) ────────────────────────────────────────────
    (
        B,
        "Sorğunun adı boş ola bilməz.",
        "The survey title cannot be empty.",
        "Название опроса не может быть пустым.",
        "Anket adı boş olamaz.",
    ),
    (
        B,
        "Ad %(limit)s simvoldan uzun ola bilməz.",
        "The title cannot exceed %(limit)s characters.",
        "Название не может быть длиннее %(limit)s символов.",
        "Ad %(limit)s karakterden uzun olamaz.",
    ),
    (B, "Sorğu növü seçilməlidir.", "Select a survey type.", "Выберите тип опроса.", "Anket türü seçilmelidir."),
    (
        B,
        "Bağlanma tarixi açılış tarixindən əvvəl ola bilməz.",
        "The closing date cannot be before the opening date.",
        "Дата закрытия не может быть раньше даты открытия.",
        "Kapanış tarihi açılış tarihinden önce olamaz.",
    ),
    (
        B,
        "Sorğu %(days)s gündən uzun ola bilməz.",
        "A survey cannot last longer than %(days)s days.",
        "Опрос не может длиться дольше %(days)s дней.",
        "Anket %(days)s günden uzun olamaz.",
    ),
    (
        B,
        "Təsvir %(limit)s simvoldan uzun ola bilməz.",
        "The description cannot exceed %(limit)s characters.",
        "Описание не может быть длиннее %(limit)s символов.",
        "Açıklama %(limit)s karakterden uzun olamaz.",
    ),
    (
        B,
        "Bu sorğunun növünü dəyişmək olmaz.",
        "The type of this survey cannot be changed.",
        "Тип этого опроса изменить нельзя.",
        "Bu anketin türü değiştirilemez.",
    ),
    (B, "Auditoriya seçilməlidir.", "Select an audience.", "Выберите аудиторию.", "Hedef kitle seçilmelidir."),
    (
        B,
        "Dərc olunmuş sorğunun anonimliyi və auditoriyası dəyişmir — dublikat yaradın.",
        "Anonymity and audience of a published survey cannot change — create a duplicate.",
        "Анонимность и аудитория опубликованного опроса не меняются — создайте копию.",
        "Yayındaki anketin anonimliği ve hedef kitlesi değişmez — bir kopya oluşturun.",
    ),
    (
        B,
        "Artıq açılmış sorğunun açılış tarixi dəyişmir.",
        "The opening date of an already opened survey cannot change.",
        "Дату открытия уже открытого опроса изменить нельзя.",
        "Zaten açılmış anketin açılış tarihi değişmez.",
    ),
    (
        B,
        "Dərc olunmuş sorğunun bağlanma tarixi olmalıdır.",
        "A published survey must have a closing date.",
        "У опубликованного опроса должна быть дата закрытия.",
        "Yayındaki anketin kapanış tarihi olmalıdır.",
    ),
    (
        B,
        "Qapı siyasəti seçilməlidir.",
        "Select a gate policy.",
        "Выберите политику доступа.",
        "Erişim politikası seçilmelidir.",
    ),
    (
        B,
        "Möhlət 0 ilə %(high)s gün arasında olmalıdır.",
        "The grace period must be between 0 and %(high)s days.",
        "Отсрочка должна быть от 0 до %(high)s дней.",
        "Erteleme süresi 0 ile %(high)s gün arasında olmalıdır.",
    ),
    (
        B,
        "Minimum qrup ölçüsü %(low)s ilə %(high)s arasında olmalıdır.",
        "The minimum group size must be between %(low)s and %(high)s.",
        "Минимальный размер группы должен быть от %(low)s до %(high)s.",
        "Minimum grup büyüklüğü %(low)s ile %(high)s arasında olmalıdır.",
    ),
    (
        B,
        "Nəticələr dərc olunandan sonra k-həddi dəyişmir.",
        "The k threshold cannot change after results are published.",
        "Порог k нельзя менять после публикации результатов.",
        "Sonuçlar yayımlandıktan sonra k eşiği değişmez.",
    ),
    (
        B,
        "Yalnız qaralama sorğu dərc oluna bilər.",
        "Only a draft survey can be published.",
        "Опубликовать можно только черновик.",
        "Yalnızca taslak anket yayımlanabilir.",
    ),
    (
        B,
        "Dərc etmək üçün ən azı bir sual əlavə edin.",
        "Add at least one question before publishing.",
        "Добавьте хотя бы один вопрос перед публикацией.",
        "Yayımlamak için en az bir soru ekleyin.",
    ),
    (
        B,
        "Dərc etmək üçün bağlanma tarixini seçin.",
        "Choose a closing date before publishing.",
        "Выберите дату закрытия перед публикацией.",
        "Yayımlamak için kapanış tarihini seçin.",
    ),
    (
        B,
        "Yalnız dərc olunmuş sorğu bağlana bilər.",
        "Only a published survey can be closed.",
        "Закрыть можно только опубликованный опрос.",
        "Yalnızca yayındaki anket kapatılabilir.",
    ),
    (
        B,
        "Yalnız bağlı sorğu yenidən açıla bilər.",
        "Only a closed survey can be reopened.",
        "Повторно открыть можно только закрытый опрос.",
        "Yalnızca kapalı anket yeniden açılabilir.",
    ),
    (
        B,
        "Yenidən açmaq üçün gələcək bağlanma tarixi seçin.",
        "Choose a future closing date to reopen.",
        "Для повторного открытия выберите будущую дату закрытия.",
        "Yeniden açmak için ileri bir kapanış tarihi seçin.",
    ),
    (
        B,
        "Defolt sual dəsti arxivlənmir — əvvəl başqa dəsti defolt edin.",
        "The default question set cannot be archived — make another set the default first.",
        "Набор вопросов по умолчанию нельзя архивировать — сначала назначьте другой набор.",
        "Varsayılan soru seti arşivlenemez — önce başka bir seti varsayılan yapın.",
    ),
    (
        B,
        "Açıq kampaniyanın sual dəsti arxivlənmir.",
        "The question set of an open campaign cannot be archived.",
        "Набор вопросов открытой кампании нельзя архивировать.",
        "Açık kampanyanın soru seti arşivlenemez.",
    ),
    (B, "Sorğu arxivdə deyil.", "The survey is not archived.", "Опрос не в архиве.", "Anket arşivde değil."),
    (
        B,
        "Yalnız heç dərc olunmamış qaralama silinə bilər.",
        "Only a never-published draft can be deleted.",
        "Удалить можно только ни разу не опубликованный черновик.",
        "Yalnızca hiç yayımlanmamış taslak silinebilir.",
    ),
    (
        B,
        "Kampaniyada istifadə olunan dəst silinmir.",
        "A set used by a campaign cannot be deleted.",
        "Набор, используемый в кампании, удалить нельзя.",
        "Kampanyada kullanılan set silinemez.",
    ),
    (
        B,
        "Defolt yalnız dərc olunmuş müəllim qiymətləndirməsi dəsti ola bilər.",
        "Only a ready teacher-evaluation set can be the default.",
        "По умолчанию может быть только готовый набор оценки преподавателей.",
        "Yalnızca hazır öğretim elemanı değerlendirme seti varsayılan olabilir.",
    ),
    (B, "nüsxə", "copy", "копия", "kopya"),
    (
        B,
        "Cavab gəlmiş sualda yalnız kiçik düzəliş (yazı səhvi) mümkündür — mənanı dəyişmək üçün sorğunun dublikatını yaradın.",
        "An answered question allows only small fixes (typos) — to change its meaning, duplicate the survey.",
        "В вопросе с ответами возможны только мелкие исправления (опечатки) — чтобы изменить смысл, создайте копию опроса.",
        "Yanıt alınmış soruda yalnızca küçük düzeltme (yazım hatası) yapılabilir — anlamı değiştirmek için anketin kopyasını oluşturun.",
    ),
    (
        B,
        "Sualın mətni boş ola bilməz.",
        "The question text cannot be empty.",
        "Текст вопроса не может быть пустым.",
        "Soru metni boş olamaz.",
    ),
    (
        B,
        "«%(field)s» %(limit)s simvoldan uzun ola bilməz.",
        "“%(field)s” cannot exceed %(limit)s characters.",
        "«%(field)s» не может быть длиннее %(limit)s символов.",
        "“%(field)s” %(limit)s karakterden uzun olamaz.",
    ),
    (
        B,
        "Ən azı %(n)s seçim yazın (hər sətirdə bir).",
        "Enter at least %(n)s options (one per line).",
        "Введите не менее %(n)s вариантов (по одному в строке).",
        "En az %(n)s seçenek yazın (her satıra bir tane).",
    ),
    (
        B,
        "Ən çoxu %(n)s seçim ola bilər.",
        "There can be at most %(n)s options.",
        "Может быть не более %(n)s вариантов.",
        "En fazla %(n)s seçenek olabilir.",
    ),
    (
        B,
        "Seçim %(n)s simvoldan uzun ola bilməz.",
        "An option cannot exceed %(n)s characters.",
        "Вариант не может быть длиннее %(n)s символов.",
        "Seçenek %(n)s karakterden uzun olamaz.",
    ),
    (
        B,
        "Seçimlər təkrarlanmamalıdır.",
        "Options must not repeat.",
        "Варианты не должны повторяться.",
        "Seçenekler tekrarlanmamalıdır.",
    ),
    (
        B,
        "Cavab gəlmiş sualın seçim sayı dəyişmir.",
        "The number of options of an answered question cannot change.",
        "Количество вариантов у вопроса с ответами изменить нельзя.",
        "Yanıt alınmış sorunun seçenek sayısı değişmez.",
    ),
    (B, "Etiket", "Label", "Подпись", "Etiket"),
    (
        B,
        "Minimum/maksimum seçim sayı tam ədəd olmalıdır.",
        "The minimum/maximum number of selections must be a whole number.",
        "Минимальное/максимальное число выбора должно быть целым.",
        "Minimum/maksimum seçim sayısı tam sayı olmalıdır.",
    ),
    (
        B,
        "Minimum/maksimum seçim sayı seçimlərin sayına uyğun olmalıdır.",
        "The minimum/maximum number of selections must fit the number of options.",
        "Минимальное/максимальное число выбора должно соответствовать количеству вариантов.",
        "Minimum/maksimum seçim sayısı seçenek sayısına uygun olmalıdır.",
    ),
    (B, "Variant %(n)s", "Option %(n)s", "Вариант %(n)s", "Seçenek %(n)s"),
    (
        B,
        "Minimum seçim sayı maksimumdan böyük ola bilməz.",
        "The minimum number of selections cannot exceed the maximum.",
        "Минимальное число выбора не может превышать максимальное.",
        "Minimum seçim sayısı maksimumdan büyük olamaz.",
    ),
    (B, "Bölmə seçilməlidir.", "Select a section.", "Выберите раздел.", "Bölüm seçilmelidir."),
    (
        B,
        "Cavab gəlmiş sorğuya sual əlavə etmək olmaz — dublikat yaradın.",
        "You cannot add questions to an answered survey — create a duplicate.",
        "В опрос с ответами нельзя добавлять вопросы — создайте копию.",
        "Yanıt alınmış ankete soru eklenemez — bir kopya oluşturun.",
    ),
    (
        B,
        "Sorğuda ən çoxu %(n)s sual ola bilər.",
        "A survey can have at most %(n)s questions.",
        "В опросе может быть не более %(n)s вопросов.",
        "Ankette en fazla %(n)s soru olabilir.",
    ),
    (
        B,
        "Bu sorğu üçün sual növü uyğun deyil.",
        "This question type is not allowed for this survey.",
        "Этот тип вопроса не подходит для данного опроса.",
        "Bu soru türü bu anket için uygun değil.",
    ),
    (B, "Sual", "Question", "Вопрос", "Soru"),
    (B, "İzah", "Hint", "Пояснение", "Açıklama"),
    (
        B,
        "Cavab gəlmiş sorğudan sual silinmir.",
        "Questions cannot be deleted from an answered survey.",
        "Из опроса с ответами нельзя удалять вопросы.",
        "Yanıt alınmış anketten soru silinemez.",
    ),
    (
        B,
        "Cavab gəlmiş sorğuda sualların sırası dəyişmir.",
        "The question order of an answered survey cannot change.",
        "Порядок вопросов в опросе с ответами изменить нельзя.",
        "Yanıt alınmış ankette soru sırası değişmez.",
    ),
    (
        B,
        "Sıra köhnəlib — səhifəni yeniləyin.",
        "The order is out of date — reload the page.",
        "Порядок устарел — обновите страницу.",
        "Sıralama güncel değil — sayfayı yenileyin.",
    ),
    (
        B,
        "Müəllim qiymətləndirməsinin bölmələri sabitdir.",
        "Teacher-evaluation sections are fixed.",
        "Разделы оценки преподавателей фиксированы.",
        "Öğretim elemanı değerlendirmesinin bölümleri sabittir.",
    ),
    (
        B,
        "Cavab gəlmiş sorğuya bölmə əlavə etmək olmaz.",
        "You cannot add sections to an answered survey.",
        "В опрос с ответами нельзя добавлять разделы.",
        "Yanıt alınmış ankete bölüm eklenemez.",
    ),
    (
        B,
        "Ən çoxu %(n)s bölmə ola bilər.",
        "There can be at most %(n)s sections.",
        "Может быть не более %(n)s разделов.",
        "En fazla %(n)s bölüm olabilir.",
    ),
    (B, "Bölmə adı", "Section title", "Название раздела", "Bölüm adı"),
    (
        B,
        "Cavab gəlmiş sorğudan bölmə silinmir.",
        "Sections cannot be deleted from an answered survey.",
        "Из опроса с ответами нельзя удалять разделы.",
        "Yanıt alınmış anketten bölüm silinemez.",
    ),
    (
        B,
        "Sorğuda ən azı bir bölmə qalmalıdır.",
        "A survey must keep at least one section.",
        "В опросе должен остаться хотя бы один раздел.",
        "Ankette en az bir bölüm kalmalıdır.",
    ),
    (
        B,
        "Cavab gəlmiş sorğuda bölmələrin sırası dəyişmir.",
        "The section order of an answered survey cannot change.",
        "Порядок разделов в опросе с ответами изменить нельзя.",
        "Yanıt alınmış ankette bölüm sırası değişmez.",
    ),
    (
        B,
        "Tarix düzgün formatda deyil.",
        "The date is not in a valid format.",
        "Неверный формат даты.",
        "Tarih geçerli biçimde değil.",
    ),
    (
        B,
        "Bu əməliyyat üçün icazəniz yoxdur.",
        "You do not have permission for this action.",
        "У вас нет прав на это действие.",
        "Bu işlem için yetkiniz yok.",
    ),
    (
        B,
        "Sorğu yaradıldı — indi sualları yazın.",
        "Survey created — now write the questions.",
        "Опрос создан — теперь напишите вопросы.",
        "Anket oluşturuldu — şimdi soruları yazın.",
    ),
    (B, "Ayarlar yadda saxlanıldı.", "Settings saved.", "Настройки сохранены.", "Ayarlar kaydedildi."),
    (B, "Sorğu dərc olundu.", "Survey published.", "Опрос опубликован.", "Anket yayımlandı."),
    (B, "Sorğu bağlandı.", "Survey closed.", "Опрос закрыт.", "Anket kapatıldı."),
    (B, "Sorğu arxivə köçürüldü.", "Survey moved to the archive.", "Опрос перемещён в архив.", "Anket arşive taşındı."),
    (
        B,
        "Sorğu arxivdən çıxarıldı.",
        "Survey restored from the archive.",
        "Опрос восстановлен из архива.",
        "Anket arşivden çıkarıldı.",
    ),
    (
        B,
        "Sual dəsti yeni kampaniyalar üçün defolt edildi.",
        "The question set is now the default for new campaigns.",
        "Набор вопросов назначен по умолчанию для новых кампаний.",
        "Soru seti yeni kampanyalar için varsayılan yapıldı.",
    ),
    (
        B,
        "Nüsxə yaradıldı (qaralama).",
        "Copy created (draft).",
        "Копия создана (черновик).",
        "Kopya oluşturuldu (taslak).",
    ),
    (B, "Qaralama silindi.", "Draft deleted.", "Черновик удалён.", "Taslak silindi."),
    (B, "Sorğu yenidən açıldı.", "Survey reopened.", "Опрос снова открыт.", "Anket yeniden açıldı."),
    (B, "Naməlum əməliyyat.", "Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    (B, "Sual tapılmadı.", "Question not found.", "Вопрос не найден.", "Soru bulunamadı."),
    (B, "Bölmə tapılmadı.", "Section not found.", "Раздел не найден.", "Bölüm bulunamadı."),
    (B, "Sual əlavə olundu.", "Question added.", "Вопрос добавлен.", "Soru eklendi."),
    (B, "Sual yadda saxlanıldı.", "Question saved.", "Вопрос сохранён.", "Soru kaydedildi."),
    (B, "Sual silindi.", "Question deleted.", "Вопрос удалён.", "Soru silindi."),
    (B, "Sıra dəyişdi.", "Order changed.", "Порядок изменён.", "Sıra değişti."),
    (B, "Bölmə əlavə olundu.", "Section added.", "Раздел добавлен.", "Bölüm eklendi."),
    (B, "Bölmə yadda saxlanıldı.", "Section saved.", "Раздел сохранён.", "Bölüm kaydedildi."),
    (
        B,
        "Bölmə silindi, sualları qonşu bölməyə keçdi.",
        "Section deleted; its questions moved to the neighbouring section.",
        "Раздел удалён, его вопросы перенесены в соседний раздел.",
        "Bölüm silindi, soruları komşu bölüme taşındı.",
    ),
]

ROWS += [
    # ── surveys.builder (2/2) — şablonlar ────────────────────────────────
    (
        B,
        "Sorğu qurucusu üçün təşkilat səviyyəsində «survey.manage» icazəsi lazımdır.",
        "The survey builder requires the organization-wide “survey.manage” permission.",
        "Для конструктора опросов нужно право «survey.manage» на уровне организации.",
        "Anket oluşturucu için kurum düzeyinde “survey.manage” yetkisi gerekir.",
    ),
    (
        B,
        "Sorğunu yaradın, suallarını yazın, kimin dolduracağını (tələbə, müəllim, heyət və ya hamı) və məcburiliyini seçin. «Müəllim qiymətləndirməsi» növü semestr kampaniyalarının sual dəstidir — tarixləri «Sorğu kampaniyaları» bölməsində idarə olunur.",
        "Create a survey, write its questions, choose who must fill it in (students, teachers, staff or everyone) and whether it is mandatory. The “Teacher evaluation” type is the question set of semester campaigns — its dates are managed in “Survey campaigns”.",
        "Создайте опрос, напишите вопросы, выберите, кто должен его заполнить (студенты, преподаватели, персонал или все), и обязателен ли он. Тип «Оценка преподавателя» — это набор вопросов семестровых кампаний; их даты управляются в разделе «Кампании опросов».",
        "Anketi oluşturun, sorularını yazın, kimin dolduracağını (öğrenciler, öğretim elemanları, personel veya herkes) ve zorunlu olup olmadığını seçin. “Öğretim elemanı değerlendirmesi” türü dönem kampanyalarının soru setidir — tarihleri “Anket kampanyaları” bölümünde yönetilir.",
    ),
    (B, "Sorğu növü", "Survey type", "Тип опроса", "Anket türü"),
    (B, "Sorğunun adı", "Survey title", "Название опроса", "Anket adı"),
    (
        B,
        "məs. Kitabxana xidmətlərindən məmnunluq",
        "e.g. Satisfaction with library services",
        "напр. Удовлетворённость услугами библиотеки",
        "örn. Kütüphane hizmetlerinden memnuniyet",
    ),
    (B, "Sorğu yarat", "Create survey", "Создать опрос", "Anket oluştur"),
    (B, "Status filtri", "Status filter", "Фильтр по статусу", "Durum filtresi"),
    (B, "Aktiv", "Active", "Активные", "Aktif"),
    (B, "Qaralama", "Draft", "Черновик", "Taslak"),
    (B, "Dərc olunub", "Published", "Опубликован", "Yayında"),
    (B, "Bağlı", "Closed", "Закрыт", "Kapalı"),
    (B, "Arxiv", "Archive", "Архив", "Arşiv"),
    (B, "Hamısı", "All", "Все", "Tümü"),
    (B, "Defolt dəst", "Default set", "Набор по умолчанию", "Varsayılan set"),
    (B, "Anonim", "Anonymous", "Анонимный", "Anonim"),
    (B, "Məcburi", "Mandatory", "Обязательный", "Zorunlu"),
    (B, "Auditoriya", "Audience", "Аудитория", "Hedef kitle"),
    (
        B,
        "Jurnalı bağlanmış fənlərin tələbələri",
        "Students of subjects with closed gradebooks",
        "Студенты предметов с закрытым журналом",
        "Not defteri kapatılmış derslerin öğrencileri",
    ),
    (B, "Kampaniyalar", "Campaigns", "Кампании", "Kampanyalar"),
    (B, "daraldılıb", "narrowed", "сужена", "daraltılmış"),
    (B, "Açılış", "Opens", "Открытие", "Açılış"),
    (B, "Bağlanma", "Closes", "Закрытие", "Kapanış"),
    (B, "Dolduran", "Completed", "Заполнили", "Dolduran"),
    (B, "Redaktə et", "Edit", "Редактировать", "Düzenle"),
    (B, "Nəticələr", "Results", "Результаты", "Sonuçlar"),
    (
        B,
        "Bu filtrdə sorğu yoxdur. Yuxarıdan yeni sorğu yaradın.",
        "No surveys match this filter. Create a new survey above.",
        "Нет опросов с этим фильтром. Создайте новый опрос выше.",
        "Bu filtrede anket yok. Yukarıdan yeni anket oluşturun.",
    ),
    (B, "Hazır", "Ready", "Готов", "Hazır"),
    (B, "Açıq", "Open", "Открыт", "Açık"),
    (B, "Planlaşdırılıb", "Scheduled", "Запланирован", "Planlandı"),
    (B, "Arxivdə", "Archived", "В архиве", "Arşivde"),
    (B, "Bütün sorğular", "All surveys", "Все опросы", "Tüm anketler"),
    (B, "Adla", "Named", "С именем", "İsimli"),
    (B, "Struktur kilidlidir", "Structure locked", "Структура заблокирована", "Yapı kilitli"),
    (B, "Suallar: %(n)s", "Questions: %(n)s", "Вопросов: %(n)s", "Sorular: %(n)s"),
    (
        B,
        "Sual dəsti kampaniyalar üçün hazır elan olunsun?",
        "Mark the question set as ready for campaigns?",
        "Отметить набор вопросов как готовый для кампаний?",
        "Soru seti kampanyalar için hazır olarak işaretlensin mi?",
    ),
    (
        B,
        "Sorğu dərc olunsun? Açılış günü auditoriyaya bildiriş gedəcək; dərcdən sonra anonimlik və auditoriya dəyişmir.",
        "Publish the survey? The audience will be notified on the opening day; anonymity and audience cannot change after publishing.",
        "Опубликовать опрос? В день открытия аудитория получит уведомление; после публикации анонимность и аудитория не меняются.",
        "Anket yayımlansın mı? Açılış günü hedef kitleye bildirim gidecek; yayından sonra anonimlik ve hedef kitle değişmez.",
    ),
    (B, "Hazır et", "Mark ready", "Сделать готовым", "Hazır yap"),
    (B, "Dərc et", "Publish", "Опубликовать", "Yayımla"),
    (
        B,
        "Yeni semestr kampaniyaları bu sual dəstini götürsün? Mövcud kampaniyalar öz dəstində qalır.",
        "Should new semester campaigns use this question set? Existing campaigns keep their own set.",
        "Использовать этот набор вопросов в новых семестровых кампаниях? Существующие кампании сохранят свой набор.",
        "Yeni dönem kampanyaları bu soru setini kullansın mı? Mevcut kampanyalar kendi setinde kalır.",
    ),
    (B, "Defolt et", "Make default", "Сделать по умолчанию", "Varsayılan yap"),
    (B, "Formaya bax", "View form", "Посмотреть форму", "Formu gör"),
    (
        B,
        "Sorğu bağlansın? Cavab qəbulu dayanacaq, məcburi qapı açılacaq, anonim nəticələr dərc olunacaq.",
        "Close the survey? Answers will stop, the mandatory gate will lift and anonymous results will be published.",
        "Закрыть опрос? Приём ответов прекратится, обязательная блокировка снимется, анонимные результаты будут опубликованы.",
        "Anket kapatılsın mı? Yanıt kabulü duracak, zorunlu engel kalkacak, anonim sonuçlar yayımlanacak.",
    ),
    (B, "Bağla", "Close", "Закрыть", "Kapat"),
    (B, "Yeni bağlanma tarixi", "New closing date", "Новая дата закрытия", "Yeni kapanış tarihi"),
    (B, "Yenidən aç", "Reopen", "Открыть снова", "Yeniden aç"),
    (B, "Dublikat", "Duplicate", "Дублировать", "Kopyala"),
    (B, "Arxivdən çıxar", "Restore", "Восстановить", "Arşivden çıkar"),
    (
        B,
        "Qaralama birdəfəlik silinsin?",
        "Delete the draft permanently?",
        "Удалить черновик навсегда?",
        "Taslak kalıcı olarak silinsin mi?",
    ),
    (B, "Sil", "Delete", "Удалить", "Sil"),
    (
        B,
        "Sorğu arxivə köçürülsün? Açıqdırsa bağlanacaq; nəticələr qalır.",
        "Archive the survey? If open it will be closed; results are kept.",
        "Переместить опрос в архив? Если он открыт, он будет закрыт; результаты сохранятся.",
        "Anket arşivlensin mi? Açıksa kapatılacak; sonuçlar korunur.",
    ),
    (B, "Arxivlə", "Archive", "В архив", "Arşivle"),
    (B, "Redaktor bölmələri", "Editor tabs", "Разделы редактора", "Düzenleyici sekmeleri"),
    (B, "Ayarlar", "Settings", "Настройки", "Ayarlar"),
    (B, "Suallar", "Questions", "Вопросы", "Sorular"),
    (B, "Əsas məlumat", "Basics", "Основное", "Temel bilgiler"),
    (B, "Ad", "Title", "Название", "Ad"),
    (
        B,
        "Təsvir (respondentə göstərilir)",
        "Description (shown to respondents)",
        "Описание (видно респондентам)",
        "Açıklama (katılımcıya gösterilir)",
    ),
    (B, "Növ", "Type", "Тип", "Tür"),
    (B, "Anonim sorğu", "Anonymous survey", "Анонимный опрос", "Anonim anket"),
    (
        B,
        "cavab adla saxlanılmır; nəticələr yalnız bağlandıqdan sonra və ən azı k cavab olanda görünür.",
        "answers are not stored with names; results appear only after closing and with at least k answers.",
        "ответы не хранятся с именами; результаты видны только после закрытия и при наличии не менее k ответов.",
        "yanıtlar isimle saklanmaz; sonuçlar yalnızca kapanıştan sonra ve en az k yanıt olduğunda görünür.",
    ),
    (
        B,
        "Müəllim qiymətləndirməsi həmişə anonimdir. Auditoriya — semestrdə jurnalı bağlanmış fənlərin tələbələri; açılış, bağlanma, «Sonra doldur» möhləti və məcburilik «Sorğu kampaniyaları» bölməsində hər semestr üçün ayrıca seçilir. Burada yalnız sual dəstini idarə edirsiniz.",
        "Teacher evaluation is always anonymous. Its audience is the students of subjects whose gradebooks are closed in the semester; opening, closing, the “Fill in later” grace period and obligation are set per semester in “Survey campaigns”. Here you only manage the question set.",
        "Оценка преподавателя всегда анонимна. Аудитория — студенты предметов с закрытым в семестре журналом; открытие, закрытие, отсрочка «Заполнить позже» и обязательность задаются для каждого семестра в разделе «Кампании опросов». Здесь вы управляете только набором вопросов.",
        "Öğretim elemanı değerlendirmesi her zaman anonimdir. Hedef kitle — dönemde not defteri kapatılmış derslerin öğrencileridir; açılış, kapanış, “Sonra doldur” süresi ve zorunluluk her dönem için “Anket kampanyaları” bölümünde ayrıca seçilir. Burada yalnızca soru setini yönetirsiniz.",
    ),
    (B, "Kim doldurmalıdır", "Who must fill it in", "Кто должен заполнить", "Kim doldurmalı"),
    (
        B,
        "Dərc olunmuş sorğunun auditoriyası dəyişmir — fərqli auditoriya üçün dublikat yaradın.",
        "The audience of a published survey cannot change — duplicate it for a different audience.",
        "Аудитория опубликованного опроса не меняется — создайте копию для другой аудитории.",
        "Yayındaki anketin hedef kitlesi değişmez — farklı hedef kitle için kopya oluşturun.",
    ),
    (
        B,
        "Auditoriyanı daralt (fakültə, kafedra, qrup, ixtisas, kurs)",
        "Narrow the audience (faculty, department, group, programme, year)",
        "Сузить аудиторию (факультет, кафедра, группа, специальность, курс)",
        "Hedef kitleyi daralt (fakülte, bölüm, grup, program, sınıf)",
    ),
    (
        B,
        "Heç nə seçilməsə — bütün təşkilat. İxtisas və kurs yalnız tələbələrə aiddir: seçiləndə auditoriyada yalnız uyğun tələbələr qalır.",
        "If nothing is selected — the whole organization. Programme and year apply to students only: when selected, only matching students remain in the audience.",
        "Если ничего не выбрано — вся организация. Специальность и курс относятся только к студентам: при выборе в аудитории остаются только подходящие студенты.",
        "Hiçbir şey seçilmezse — tüm kurum. Program ve sınıf yalnızca öğrencilere uygulanır: seçildiğinde hedef kitlede yalnızca uygun öğrenciler kalır.",
    ),
    (B, "Struktur vahidləri", "Organizational units", "Структурные подразделения", "Birimler"),
    (B, "Axtar…", "Search…", "Поиск…", "Ara…"),
    (B, "Struktur vahidi yoxdur.", "No organizational units.", "Нет подразделений.", "Birim yok."),
    (
        B,
        "İxtisaslar (yalnız tələbələr)",
        "Programmes (students only)",
        "Специальности (только студенты)",
        "Programlar (yalnızca öğrenciler)",
    ),
    (B, "İxtisas yoxdur.", "No programmes.", "Нет специальностей.", "Program yok."),
    (B, "Kurs (yalnız tələbələr)", "Year (students only)", "Курс (только студенты)", "Sınıf (yalnızca öğrenciler)"),
    (B, "%(n)s. kurs", "Year %(n)s", "%(n)s-й курс", "%(n)s. sınıf"),
    (B, "Tarixlər", "Dates", "Даты", "Tarihler"),
    (
        B,
        "Açılış boşdursa dərc günü açılır. Bağlanma tarixi dərc üçün məcburidir; sonradan uzatmaq olar.",
        "If the opening date is empty, the survey opens on the day it is published. A closing date is required to publish; it can be extended later.",
        "Если дата открытия пуста, опрос откроется в день публикации. Дата закрытия обязательна для публикации; её можно продлить позже.",
        "Açılış boşsa anket yayım günü açılır. Yayım için kapanış tarihi zorunludur; sonradan uzatılabilir.",
    ),
    (B, "Məcburilik", "Obligation", "Обязательность", "Zorunluluk"),
    (B, "Könüllü", "Voluntary", "Добровольный", "Gönüllü"),
    (
        B,
        "Doldurulmayanda kabinet necə davransın?",
        "How should the cabinet behave until it is completed?",
        "Как должен вести себя кабинет, пока опрос не заполнен?",
        "Doldurulmadığında panel nasıl davransın?",
    ),
    (
        B,
        "İstifadəçi kabinetə girəndə dərhal sorğuya yönləndirilir; doldurmadan kabinet açılmır.",
        "The user is redirected to the survey on entering the cabinet; the cabinet does not open until it is completed.",
        "При входе в кабинет пользователь сразу перенаправляется на опрос; кабинет не откроется, пока опрос не заполнен.",
        "Kullanıcı panele girince hemen ankete yönlendirilir; doldurmadan panel açılmaz.",
    ),
    (
        B,
        "İlk dəfə «Bu dəfə keç» deyə bilər və xəbərdarlıq alır: növbəti dəfə doldurmadan kabinetə daxil ola bilməyəcək.",
        "The first time they may choose “Skip this time” and are warned that next time they cannot enter the cabinet without completing it.",
        "В первый раз можно нажать «Пропустить в этот раз» с предупреждением: в следующий раз без заполнения войти в кабинет нельзя.",
        "İlk seferde “Bu sefer atla” diyebilir ve uyarılır: bir dahaki sefere doldurmadan panele giremeyecek.",
    ),
    (
        B,
        "Açılışdan sonra N gün ərzində «Sonra doldur» (hər dəfə 24 saat), sonra kabinet bağlanır.",
        "For N days after opening “Fill in later” is allowed (24 hours each time), then the cabinet locks.",
        "В течение N дней после открытия доступно «Заполнить позже» (каждый раз на 24 часа), затем кабинет закрывается.",
        "Açılıştan sonra N gün boyunca “Sonra doldur” (her seferinde 24 saat), ardından panel kilitlenir.",
    ),
    (B, "Möhlət (gün)", "Grace period (days)", "Отсрочка (дни)", "Erteleme (gün)"),
    (
        B,
        "İmtahan səhifələri, parol dəyişmə və çıxış heç vaxt bağlanmır — sorğu yalnız kabineti bağlayır.",
        "Exam pages, password change and logout are never blocked — a survey only locks the cabinet.",
        "Страницы экзаменов, смена пароля и выход никогда не блокируются — опрос закрывает только кабинет.",
        "Sınav sayfaları, şifre değiştirme ve çıkış asla engellenmez — anket yalnızca paneli kilitler.",
    ),
    (B, "Anonimlik həddi", "Anonymity threshold", "Порог анонимности", "Anonimlik eşiği"),
    (B, "Minimum qrup (k)", "Minimum group (k)", "Минимальная группа (k)", "Minimum grup (k)"),
    (
        B,
        "k-dan az cavab olan nəticə və açıq cavablar göstərilmir; faizlər 5-ə yuvarlaqlaşdırılır.",
        "Results and open answers with fewer than k answers are hidden; percentages are rounded to 5.",
        "Результаты и открытые ответы при числе ответов меньше k скрываются; проценты округляются до 5.",
        "k'dan az yanıtlı sonuçlar ve açık yanıtlar gösterilmez; yüzdeler 5'e yuvarlanır.",
    ),
    (B, "Yadda saxla", "Save", "Сохранить", "Kaydet"),
]

ROWS += [
    # ── surveys.builder — sual redaktoru və nəticələr ────────────────────
    (
        B,
        "Sıranı dəyişmək üçün tutacağı sürükləyin və ya tutacaqda Alt + yuxarı/aşağı ox düymələrini basın.",
        "To reorder, drag the handle or press Alt + Up/Down arrow on the handle.",
        "Чтобы изменить порядок, перетащите маркер или нажмите Alt + стрелку вверх/вниз на маркере.",
        "Sırayı değiştirmek için tutamacı sürükleyin veya tutamaçta Alt + yukarı/aşağı ok tuşlarına basın.",
    ),
    (
        B,
        "Bu sorğuya cavab gəlib — nəticələrin bütövlüyü üçün sual əlavə etmək, silmək, növünü, sırasını və məcburiliyini dəyişmək bağlıdır. Yalnız kiçik mətn düzəlişi (yazı səhvi) mümkündür; hər düzəliş versiya kimi saxlanılır. Böyük dəyişiklik üçün dublikat yaradın.",
        "This survey has answers — to protect result integrity, adding, deleting, retyping, reordering and changing whether questions are required is locked. Only small text fixes (typos) are allowed; each fix is kept as a version. Create a duplicate for larger changes.",
        "На этот опрос уже есть ответы — ради целостности результатов добавление, удаление, смена типа, порядка и обязательности вопросов заблокированы. Возможны только мелкие правки текста (опечатки); каждая правка сохраняется как версия. Для крупных изменений создайте копию.",
        "Bu ankete yanıt geldi — sonuç bütünlüğü için soru ekleme, silme, tür, sıra ve zorunluluk değiştirme kilitlidir. Yalnızca küçük metin düzeltmeleri (yazım hatası) yapılabilir; her düzeltme sürüm olarak saklanır. Büyük değişiklik için kopya oluşturun.",
    ),
    (
        B,
        "Müəllim qiymətləndirməsində sual növləri: Likert (1–5), bal (1–10) və açıq cavab. «Ümumi bal» (1–10) və «Tövsiyə» sualları nəticə panelinin göstəricilərini qidalandırır; «İndeksə daxil» Likert sualları orta indeksi təşkil edir.",
        "Teacher evaluation question types: Likert (1–5), score (1–10) and open answer. The “Overall score” (1–10) and “Recommend” questions feed the results dashboard metrics; Likert questions marked “In index” make up the average index.",
        "Типы вопросов в оценке преподавателя: Лайкерт (1–5), балл (1–10) и открытый ответ. Вопросы «Общий балл» (1–10) и «Рекомендация» питают показатели панели результатов; вопросы Лайкерта с отметкой «В индексе» составляют средний индекс.",
        "Öğretim elemanı değerlendirmesinde soru türleri: Likert (1–5), puan (1–10) ve açık yanıt. “Genel puan” (1–10) ve “Tavsiye” soruları sonuç panelinin göstergelerini besler; “Endekse dahil” Likert soruları ortalama endeksi oluşturur.",
    ),
    (B, "Adsız bölmə", "Untitled section", "Раздел без названия", "Adsız bölüm"),
    (B, "Bölməni yuxarı", "Move section up", "Раздел вверх", "Bölümü yukarı taşı"),
    (B, "Bölməni aşağı", "Move section down", "Раздел вниз", "Bölümü aşağı taşı"),
    (B, "Bölməni sil", "Delete section", "Удалить раздел", "Bölümü sil"),
    (
        B,
        "Bölmə silinsin? Sualları qonşu bölməyə keçəcək.",
        "Delete the section? Its questions will move to the neighbouring section.",
        "Удалить раздел? Его вопросы перейдут в соседний раздел.",
        "Bölüm silinsin mi? Soruları komşu bölüme taşınacak.",
    ),
    (
        B,
        "Bölmənin adı və izahı",
        "Section title and description",
        "Название и описание раздела",
        "Bölüm adı ve açıklaması",
    ),
    (B, "Bölmənin adı", "Section title", "Название раздела", "Bölüm adı"),
    (
        B,
        "Bu bölmədə hələ sual yoxdur.",
        "No questions in this section yet.",
        "В этом разделе пока нет вопросов.",
        "Bu bölümde henüz soru yok.",
    ),
    (B, "Yeni sual", "New question", "Новый вопрос", "Yeni soru"),
    (B, "Sualın mətni…", "Question text…", "Текст вопроса…", "Soru metni…"),
    (B, "Əlavə et", "Add", "Добавить", "Ekle"),
    (B, "Yeni bölmə", "New section", "Новый раздел", "Yeni bölüm"),
    (B, "məs. Xidmətin keyfiyyəti", "e.g. Service quality", "напр. Качество обслуживания", "örn. Hizmet kalitesi"),
    (B, "Bölmə əlavə et", "Add section", "Добавить раздел", "Bölüm ekle"),
    (
        B,
        "Sualın sırasını dəyiş: %(n)s",
        "Reorder question %(n)s",
        "Изменить порядок вопроса %(n)s",
        "Soru sırasını değiştir: %(n)s",
    ),
    (B, "İndeksə daxil", "In index", "В индексе", "Endekse dahil"),
    (
        B,
        "Nəticə panelinin göstəricisini qidalandırır",
        "Feeds a results dashboard metric",
        "Питает показатель панели результатов",
        "Sonuç panelinin göstergesini besler",
    ),
    (B, "Göstərici", "Metric", "Показатель", "Gösterge"),
    (B, "Düzəlişlər: %(n)s", "Revisions: %(n)s", "Правок: %(n)s", "Düzeltmeler: %(n)s"),
    (B, "Yuxarı", "Up", "Вверх", "Yukarı"),
    (B, "Aşağı", "Down", "Вниз", "Aşağı"),
    (B, "Sualı sil", "Delete question", "Удалить вопрос", "Soruyu sil"),
    (B, "Sual silinsin?", "Delete the question?", "Удалить вопрос?", "Soru silinsin mi?"),
    (B, "İzah (istəyə görə)", "Hint (optional)", "Пояснение (необязательно)", "Açıklama (isteğe bağlı)"),
    (B, "Bölmə", "Section", "Раздел", "Bölüm"),
    (B, "Bölmə %(n)s", "Section %(n)s", "Раздел %(n)s", "Bölüm %(n)s"),
    (B, "Məcburi sual", "Required question", "Обязательный вопрос", "Zorunlu soru"),
    (
        B,
        "Variantlar — hər sətirdə bir",
        "Options — one per line",
        "Варианты — по одному в строке",
        "Seçenekler — her satıra bir tane",
    ),
    (
        B,
        "Variantların sayı və sırası dəyişmir — yalnız yazı düzəlişi.",
        "The number and order of options cannot change — only typo fixes.",
        "Количество и порядок вариантов не меняются — только исправление опечаток.",
        "Seçeneklerin sayısı ve sırası değişmez — yalnızca yazım düzeltmesi.",
    ),
    (B, "Ən az seçim", "Minimum selections", "Минимум выбора", "En az seçim"),
    (B, "Ən çox seçim", "Maximum selections", "Максимум выбора", "En çok seçim"),
    (
        B,
        "Şkala etiketləri (boş — standart)",
        "Scale labels (empty — default)",
        "Подписи шкалы (пусто — стандартные)",
        "Ölçek etiketleri (boş — varsayılan)",
    ),
    (
        B,
        "Şkalanın uc etiketləri (0 və 10)",
        "Scale end labels (0 and 10)",
        "Подписи краёв шкалы (0 и 10)",
        "Ölçeğin uç etiketleri (0 ve 10)",
    ),
    (
        B,
        "Müəllim qiymətləndirməsinin nəticələri (müəllim reytinqi, kafedra/fakültə bölgüsü, dinamika) «Sorğu nəticələri» bölməsindədir.",
        "Teacher evaluation results (teacher ranking, department/faculty breakdown, trends) are in “Survey results”.",
        "Результаты оценки преподавателей (рейтинг, разбивка по кафедрам/факультетам, динамика) находятся в разделе «Результаты опросов».",
        "Öğretim elemanı değerlendirmesinin sonuçları (sıralama, bölüm/fakülte dağılımı, dinamik) “Anket sonuçları” bölümündedir.",
    ),
    (B, "Nəticələrə keç", "Go to results", "Перейти к результатам", "Sonuçlara git"),
    (
        B,
        "Sorğu hələ dərc olunmayıb — nəticə yoxdur.",
        "The survey is not published yet — no results.",
        "Опрос ещё не опубликован — результатов нет.",
        "Anket henüz yayımlanmadı — sonuç yok.",
    ),
    (B, "İştirak", "Participation", "Участие", "Katılım"),
    (B, "Vahidlər üzrə iştirak", "Participation by unit", "Участие по подразделениям", "Birimlere göre katılım"),
    (B, "Vahid", "Unit", "Подразделение", "Birim"),
    (
        B,
        "Anonim sorğu davam edir — nəticələr sorğu bağlandıqdan sonra görünəcək (canlı nəticə cavab verənin kimliyini aça bilər).",
        "The anonymous survey is still running — results will appear after it closes (live results could reveal who answered).",
        "Анонимный опрос продолжается — результаты появятся после закрытия (живые результаты могут раскрыть личность отвечающего).",
        "Anonim anket devam ediyor — sonuçlar anket kapandıktan sonra görünecek (canlı sonuçlar yanıtlayanın kimliğini açığa çıkarabilir).",
    ),
    (B, "Cavab sayı: %(n)s", "Answers: %(n)s", "Ответов: %(n)s", "Yanıt sayısı: %(n)s"),
    (
        B,
        "anonimlik həddi k = %(k)s",
        "anonymity threshold k = %(k)s",
        "порог анонимности k = %(k)s",
        "anonimlik eşiği k = %(k)s",
    ),
    (B, "CSV ixrac", "Export CSV", "Экспорт CSV", "CSV dışa aktar"),
    (
        B,
        "Cavab sayı anonimlik həddindən (k) azdır — nəticələr gizlidir.",
        "Fewer answers than the anonymity threshold (k) — results are hidden.",
        "Ответов меньше порога анонимности (k) — результаты скрыты.",
        "Yanıt sayısı anonimlik eşiğinden (k) az — sonuçlar gizli.",
    ),
    (B, "%(n)s cavab", "%(n)s answers", "Ответов: %(n)s", "%(n)s yanıt"),
    (
        B,
        "Bu suala k-dan az cavab verilib — gizlidir.",
        "This question has fewer than k answers — hidden.",
        "На этот вопрос меньше k ответов — скрыто.",
        "Bu soruya k'dan az yanıt verildi — gizli.",
    ),
    (
        B,
        "və daha %(n)s cavab (CSV ixracında)",
        "and %(n)s more answers (in the CSV export)",
        "и ещё %(n)s ответов (в экспорте CSV)",
        "ve %(n)s yanıt daha (CSV dışa aktarımında)",
    ),
    (B, "Açıq cavab yoxdur.", "No open answers.", "Нет открытых ответов.", "Açık yanıt yok."),
    (B, "Orta", "Average", "Среднее", "Ortalama"),
    (B, "tərəfdar", "promoters", "сторонники", "destekçiler"),
    (B, "neytral", "passives", "нейтральные", "pasifler"),
    (B, "tənqidçi", "detractors", "критики", "eleştirenler"),
    (
        B,
        "Respondentlər (yalnız idarəçi görür)",
        "Respondents (visible to managers only)",
        "Респонденты (видны только администраторам)",
        "Katılımcılar (yalnızca yöneticiler görür)",
    ),
    (B, "İstifadəçi adı", "Username", "Имя пользователя", "Kullanıcı adı"),
    (B, "Vaxt", "Time", "Время", "Zaman"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES: dict = {}
for _ctx, _az, _en, _ru, _tr in ROWS:
    ENTRIES.setdefault(_ctx, {})[_az] = {"az": _az, "en": _en, "ru": _ru, "tr": _tr}

#: Mövcud, lakin səhv tərcümələr üstələnir (bu dalğada yoxdur).
FORCE: set = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
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
