#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: anonim müəllim qiymətləndirmə sorğusu (apps.surveys, F1).

Tələbə səhifələri (/sorgu/), kabinet bölmələri (tələbə statusu, nəticə xülasəsi,
kampaniyalar), servis/forma mesajları, sorğu sualları (``surveys.question`` —
şablonda ``pgettext`` ilə dinamik göstərilir), şkala etiketləri, icazə etiketləri.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_survey_core_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_Q = "surveys.question"
_SC = "surveys.scale"
_ST = "surveys.student"
_CB = "surveys.cabinet"

STRINGS = {
    # ── Sorğu sualları (defolt şablon v1) ─────────────────────────────────────
    (_Q, "Müəllim dərsə hazırlıqlı gəlir, dərsi planlı və ardıcıl aparır."): (
        "The teacher comes to class prepared and conducts it in a planned, well-structured way.",
        "Преподаватель приходит на занятие подготовленным и ведёт его планомерно и последовательно.",
        "Öğretmen derse hazırlıklı gelir, dersi planlı ve tutarlı bir şekilde yürütür.",
    ),
    (_Q, "Mövzuları aydın və başa düşülən şəkildə izah edir."): (
        "Explains topics clearly and understandably.",
        "Объясняет темы ясно и понятно.",
        "Konuları açık ve anlaşılır biçimde anlatır.",
    ),
    (_Q, "Sillabusda göstərilən mövzulara, tələblərə və qiymətləndirmə qaydasına əməl edir."): (
        "Follows the topics, requirements and assessment rules stated in the syllabus.",
        "Соблюдает темы, требования и порядок оценивания, указанные в силлабусе.",
        "İzlencede belirtilen konulara, gerekliliklere ve değerlendirme kurallarına uyar.",
    ),
    (_Q, "Dərsləri vaxtında başlayır və dərs vaxtından səmərəli istifadə edir."): (
        "Starts classes on time and uses class time effectively.",
        "Начинает занятия вовремя и эффективно использует учебное время.",
        "Dersleri zamanında başlatır ve ders süresini verimli kullanır.",
    ),
    (_Q, "Suallar verməyə, müzakirəyə və fəal iştiraka həvəsləndirir."): (
        "Encourages questions, discussion and active participation.",
        "Поощряет вопросы, обсуждение и активное участие.",
        "Soru sormaya, tartışmaya ve aktif katılıma teşvik eder.",
    ),
    (_Q, "Tələbələrə hörmətlə, ədalətli və qərəzsiz yanaşır."): (
        "Treats students with respect, fairly and without bias.",
        "Относится к студентам с уважением, справедливо и беспристрастно.",
        "Öğrencilere saygılı, adil ve tarafsız davranır.",
    ),
    (_Q, "Qiymətləndirmə meyarları əvvəlcədən aydın idi və ballar bu meyarlara uyğun verilirdi."): (
        "Assessment criteria were clear in advance and marks were given according to them.",
        "Критерии оценивания были заранее понятны, и баллы выставлялись в соответствии с ними.",
        "Değerlendirme ölçütleri önceden açıktı ve puanlar bu ölçütlere göre verildi.",
    ),
    (_Q, "Tapşırıq, sərbəst iş və midterm nəticələri üzrə vaxtında və faydalı rəy (izah) verir."): (
        "Gives timely and useful feedback (explanations) on assignments, independent work and midterm results.",
        "Своевременно даёт полезную обратную связь (пояснения) по заданиям, самостоятельной работе и результатам мидтерма.",
        "Ödevler, bağımsız çalışmalar ve ara sınav sonuçları hakkında zamanında ve faydalı geri bildirim (açıklama) verir.",
    ),
    (_Q, "Dərsdən kənar (məsləhət saatı, e-poçt və s.) suallara cavab vermək üçün əlçatandır."): (
        "Is available outside class (office hours, e-mail, etc.) to answer questions.",
        "Доступен вне занятий (консультации, электронная почта и т. п.), чтобы отвечать на вопросы.",
        "Ders dışında (görüşme saatleri, e-posta vb.) soruları yanıtlamak için ulaşılabilirdir.",
    ),
    (_Q, "Nəzəri bilikləri praktiki nümunələr və real həyatla əlaqələndirir."): (
        "Connects theory with practical examples and real life.",
        "Связывает теорию с практическими примерами и реальной жизнью.",
        "Kuramsal bilgiyi uygulamalı örnekler ve gerçek yaşamla ilişkilendirir.",
    ),
    (_Q, "Dərs materialları (təqdimat, ədəbiyyat, tapşırıqlar) faydalı və müasirdir."): (
        "Course materials (slides, readings, assignments) are useful and up to date.",
        "Учебные материалы (презентации, литература, задания) полезны и современны.",
        "Ders materyalleri (sunumlar, kaynaklar, ödevler) faydalı ve günceldir.",
    ),
    (_Q, "Bu fənn üzrə bilik və bacarıqlarım nəzərəçarpacaq dərəcədə artdı."): (
        "My knowledge and skills in this subject improved noticeably.",
        "Мои знания и навыки по этому предмету заметно выросли.",
        "Bu dersteki bilgi ve becerilerim belirgin biçimde arttı.",
    ),
    (_Q, "Fənnin iş yükü (tapşırıq, hazırlıq) onun kreditinə uyğun idi."): (
        "The workload of the course (assignments, preparation) matched its credits.",
        "Нагрузка по предмету (задания, подготовка) соответствовала его кредитам.",
        "Dersin iş yükü (ödevler, hazırlık) kredisine uygundu.",
    ),
    (_Q, "Razılıq iş yükünün uyğun olduğunu bildirir — çox və ya az olması uyğunsuzluqdur."): (
        "Agreeing means the workload was appropriate — too much or too little both count as a mismatch.",
        "Согласие означает, что нагрузка была уместной; слишком большая или слишком малая — несоответствие.",
        "Katılmak iş yükünün uygun olduğunu gösterir — fazla ya da az olması uyumsuzluktur.",
    ),
    (_Q, "Bu müəllimin bu fəndəki tədrisini ümumilikdə 1–10 bal şkalası ilə qiymətləndirin."): (
        "Rate this teacher's teaching in this subject overall on a 1–10 scale.",
        "Оцените в целом преподавание этого преподавателя по данному предмету по шкале от 1 до 10.",
        "Bu öğretmenin bu dersteki öğretimini genel olarak 1–10 ölçeğinde değerlendirin.",
    ),
    (_Q, "1 — çox zəif, 10 — əla."): (
        "1 — very poor, 10 — excellent.",
        "1 — очень плохо, 10 — отлично.",
        "1 — çok zayıf, 10 — mükemmel.",
    ),
    (_Q, "Bu müəllimin dərsini digər tələbələrə tövsiyə edərdim."): (
        "I would recommend this teacher's class to other students.",
        "Я бы рекомендовал(а) занятия этого преподавателя другим студентам.",
        "Bu öğretmenin dersini diğer öğrencilere tavsiye ederim.",
    ),
    (_Q, "Bu müəllimin tədrisində ən çox nəyi bəyəndiniz?"): (
        "What did you like most about this teacher's teaching?",
        "Что вам больше всего понравилось в преподавании этого преподавателя?",
        "Bu öğretmenin öğretiminde en çok neyi beğendiniz?",
    ),
    (_Q, "Dərsin daha yaxşı olması üçün nə təklif edərdiniz?"): (
        "What would you suggest to make the class better?",
        "Что бы вы предложили, чтобы занятия стали лучше?",
        "Dersin daha iyi olması için ne önerirsiniz?",
    ),
    (_Q, "Bu semestr tədris prosesindən ümumilikdə məmnunam."): (
        "Overall, I am satisfied with the teaching process this semester.",
        "В целом я доволен(на) учебным процессом в этом семестре.",
        "Genel olarak bu dönemki öğretim sürecinden memnunum.",
    ),
    (
        _Q,
        "Tədris şəraiti (auditoriya, texniki təchizat, kitabxana, elektron resurslar) təhsilim üçün yetərli idi.",
    ): (
        "Learning conditions (classrooms, equipment, library, e-resources) were adequate for my studies.",
        "Условия обучения (аудитории, техническое оснащение, библиотека, электронные ресурсы) были достаточными для моей учёбы.",
        "Öğrenim koşulları (derslikler, teknik donanım, kütüphane, elektronik kaynaklar) eğitimim için yeterliydi.",
    ),
    (_Q, "Universitetdə tədrisi və tələbə xidmətlərini daha da yaxşılaşdırmaq üçün nə təklif edərdiniz?"): (
        "What would you suggest to further improve teaching and student services at the university?",
        "Что бы вы предложили для дальнейшего улучшения преподавания и студенческих сервисов в университете?",
        "Üniversitede öğretimi ve öğrenci hizmetlerini daha da iyileştirmek için ne önerirsiniz?",
    ),
    (_Q, "Ad, qrup və ya sizi tanıda biləcək məlumat yazmayın — cavabınız anonim qalsın."): (
        "Do not write your name, group or anything that could identify you — keep your answer anonymous.",
        "Не указывайте имя, группу или сведения, по которым вас можно узнать, — пусть ответ останется анонимным.",
        "Adınızı, grubunuzu veya sizi tanıtabilecek bir bilgiyi yazmayın — yanıtınız anonim kalsın.",
    ),
    # ── Şkala etiketləri ──────────────────────────────────────────────────────
    (_SC, "Tamamilə razı deyiləm"): ("Strongly disagree", "Совершенно не согласен", "Kesinlikle katılmıyorum"),
    (_SC, "Razı deyiləm"): ("Disagree", "Не согласен", "Katılmıyorum"),
    (_SC, "Qismən razıyam"): ("Partly agree", "Частично согласен", "Kısmen katılıyorum"),
    (_SC, "Razıyam"): ("Agree", "Согласен", "Katılıyorum"),
    (_SC, "Tamamilə razıyam"): ("Strongly agree", "Полностью согласен", "Kesinlikle katılıyorum"),
    (_SC, "Çox zəif"): ("Very poor", "Очень плохо", "Çok zayıf"),
    (_SC, "Əla"): ("Excellent", "Отлично", "Mükemmel"),
    # ── Seçimlər / model adları ───────────────────────────────────────────────
    ("surveys.choice", "Müəllim"): ("Teacher", "Преподаватель", "Öğretmen"),
    ("surveys.choice", "Ümumi"): ("General", "Общий", "Genel"),
    ("surveys.choice", "Razılıq şkalası (1–5)"): (
        "Agreement scale (1–5)",
        "Шкала согласия (1–5)",
        "Katılım ölçeği (1–5)",
    ),
    ("surveys.choice", "Bal şkalası (1–10)"): ("Rating scale (1–10)", "Шкала оценки (1–10)", "Puan ölçeği (1–10)"),
    ("surveys.choice", "Sərbəst mətn"): ("Free text", "Свободный текст", "Serbest metin"),
    ("surveys.choice", "Qaralama"): ("Draft", "Черновик", "Taslak"),
    ("surveys.choice", "Açıq"): ("Open", "Открыта", "Açık"),
    ("surveys.choice", "Bağlı"): ("Closed", "Закрыта", "Kapalı"),
    ("surveys.choice", "Jurnal bağlanması"): ("Journal closing", "Закрытие журнала", "Not defteri kapanışı"),
    ("surveys.choice", "Əl ilə"): ("Manual", "Вручную", "Elle"),
    ("surveys.model", "sorğu şablonu"): ("survey template", "шаблон опроса", "anket şablonu"),
    ("surveys.model", "sorğu şablonları"): ("survey templates", "шаблоны опросов", "anket şablonları"),
    ("surveys.model", "sorğu sualı"): ("survey question", "вопрос опроса", "anket sorusu"),
    ("surveys.model", "sorğu sualları"): ("survey questions", "вопросы опроса", "anket soruları"),
    ("surveys.model", "sorğu kampaniyası"): ("survey campaign", "кампания опроса", "anket kampanyası"),
    ("surveys.model", "sorğu kampaniyaları"): ("survey campaigns", "кампании опросов", "anket kampanyaları"),
    ("surveys.model", "sorğu qəbzi"): ("survey receipt", "квитанция опроса", "anket makbuzu"),
    ("surveys.model", "sorğu qəbzləri"): ("survey receipts", "квитанции опроса", "anket makbuzları"),
    ("surveys.model", "anonim cavab"): ("anonymous response", "анонимный ответ", "anonim yanıt"),
    ("surveys.model", "anonim cavablar"): ("anonymous responses", "анонимные ответы", "anonim yanıtlar"),
    ("surveys.model", "sorğu cavabı"): ("survey answer", "ответ на вопрос", "anket cevabı"),
    ("surveys.model", "sorğu cavabları"): ("survey answers", "ответы на вопросы", "anket cevapları"),
    # ── İcazə etiketləri ──────────────────────────────────────────────────────
    ("organizations.permission.label", "Anonim sorğu nəticələrinə baxış"): (
        "View anonymous survey results",
        "Просмотр результатов анонимного опроса",
        "Anonim anket sonuçlarını görüntüleme",
    ),
    ("organizations.permission.label", "Sorğu kampaniyalarını idarə etmək"): (
        "Manage survey campaigns",
        "Управление кампаниями опросов",
        "Anket kampanyalarını yönetme",
    ),
    # ── Kabinet bölmə başlıqları (sidebar ilə eyni) ───────────────────────────
    ("profile.sidebar", "Anonim sorğu"): ("Anonymous survey", "Анонимный опрос", "Anonim anket"),
    ("profile.sidebar", "Sorğu nəticələri"): ("Survey results", "Результаты опроса", "Anket sonuçları"),
    ("profile.sidebar", "Sorğu kampaniyaları"): ("Survey campaigns", "Кампании опросов", "Anket kampanyaları"),
    # ── Forma / servis mesajları ──────────────────────────────────────────────
    ("surveys.form", "Bu sual məcburidir."): (
        "This question is required.",
        "Это обязательный вопрос.",
        "Bu soru zorunludur.",
    ),
    ("surveys.form", "Bir cavab seçin."): ("Choose an answer.", "Выберите ответ.", "Bir yanıt seçin."),
    ("surveys.form", "Mətn %(limit)s simvoldan uzun ola bilməz."): (
        "The text cannot be longer than %(limit)s characters.",
        "Текст не может быть длиннее %(limit)s символов.",
        "Metin %(limit)s karakterden uzun olamaz.",
    ),
    ("surveys.form", "Cavab %(low)s ilə %(high)s arasında olmalıdır."): (
        "The answer must be between %(low)s and %(high)s.",
        "Ответ должен быть от %(low)s до %(high)s.",
        "Yanıt %(low)s ile %(high)s arasında olmalıdır.",
    ),
    ("surveys.submit", "Sorğu artıq qəbul edilmir."): (
        "The survey is no longer accepting responses.",
        "Опрос больше не принимает ответы.",
        "Anket artık yanıt kabul etmiyor.",
    ),
    ("surveys.submit", "Bu sorğunu artıq doldurmusunuz."): (
        "You have already completed this survey.",
        "Вы уже заполнили этот опрос.",
        "Bu anketi zaten doldurdunuz.",
    ),
    ("surveys.campaigns", "Minimum qrup ölçüsü %(low)s ilə %(high)s arasında olmalıdır."): (
        "The minimum group size must be between %(low)s and %(high)s.",
        "Минимальный размер группы должен быть от %(low)s до %(high)s.",
        "En küçük grup boyutu %(low)s ile %(high)s arasında olmalıdır.",
    ),
    ("surveys.campaigns", "Bağlanma tarixi açılış tarixindən əvvəl ola bilməz."): (
        "The closing date cannot be earlier than the opening date.",
        "Дата закрытия не может быть раньше даты открытия.",
        "Kapanış tarihi açılış tarihinden önce olamaz.",
    ),
    ("surveys.campaigns", "Kampaniya %(days)s gündən uzun ola bilməz."): (
        "A campaign cannot be longer than %(days)s days.",
        "Кампания не может длиться дольше %(days)s дней.",
        "Bir kampanya %(days)s günden uzun olamaz.",
    ),
    ("surveys.campaigns", "«Sonra doldur» müddəti açılış tarixindən əvvəl bitə bilməz."): (
        "The “Fill in later” period cannot end before the opening date.",
        "Срок «Заполнить позже» не может закончиться раньше даты открытия.",
        "“Sonra doldur” süresi açılış tarihinden önce bitemez.",
    ),
    ("surveys.campaigns", "«Sonra doldur» müddəti bağlanma tarixindən sonra ola bilməz."): (
        "The “Fill in later” period cannot extend past the closing date.",
        "Срок «Заполнить позже» не может быть позже даты закрытия.",
        "“Sonra doldur” süresi kapanış tarihinden sonra olamaz.",
    ),
    ("surveys.campaigns", "Yalnız qaralama kampaniyası açıla bilər."): (
        "Only a draft campaign can be opened.",
        "Открыть можно только черновик кампании.",
        "Yalnızca taslak kampanya açılabilir.",
    ),
    ("surveys.campaigns", "Yalnız bağlı kampaniya yenidən açıla bilər."): (
        "Only a closed campaign can be reopened.",
        "Повторно открыть можно только закрытую кампанию.",
        "Yalnızca kapalı kampanya yeniden açılabilir.",
    ),
    ("surveys.campaigns", "Yenidən açmaq üçün gələcək bağlanma tarixi seçin."): (
        "Choose a future closing date to reopen.",
        "Чтобы открыть повторно, выберите будущую дату закрытия.",
        "Yeniden açmak için ileri bir kapanış tarihi seçin.",
    ),
    ("surveys.manage", "Bu əməliyyat üçün icazəniz yoxdur."): (
        "You do not have permission for this action.",
        "У вас нет прав на это действие.",
        "Bu işlem için yetkiniz yok.",
    ),
    ("surveys.manage", "Tarix düzgün formatda deyil."): (
        "The date is not in a valid format.",
        "Дата указана в неверном формате.",
        "Tarih geçerli biçimde değil.",
    ),
    ("surveys.manage", "Kampaniya tapılmadı."): ("Campaign not found.", "Кампания не найдена.", "Kampanya bulunamadı."),
    ("surveys.manage", "Semestr seçilməlidir."): (
        "A semester must be selected.",
        "Нужно выбрать семестр.",
        "Bir dönem seçilmelidir.",
    ),
    ("surveys.manage", "Bu semestrin kampaniyası artıq var — onu cədvəldən idarə edin."): (
        "This semester already has a campaign — manage it from the list.",
        "Для этого семестра кампания уже есть — управляйте ею из списка.",
        "Bu dönemin kampanyası zaten var — onu listeden yönetin.",
    ),
    ("surveys.manage", "Kampaniya açıldı."): ("Campaign opened.", "Кампания открыта.", "Kampanya açıldı."),
    ("surveys.manage", "Kampaniya bağlandı."): ("Campaign closed.", "Кампания закрыта.", "Kampanya kapatıldı."),
    ("surveys.manage", "Kampaniya yenidən açıldı."): (
        "Campaign reopened.",
        "Кампания открыта повторно.",
        "Kampanya yeniden açıldı.",
    ),
    ("surveys.manage", "Minimum qrup ölçüsü tam ədəd olmalıdır."): (
        "The minimum group size must be a whole number.",
        "Минимальный размер группы должен быть целым числом.",
        "En küçük grup boyutu tam sayı olmalıdır.",
    ),
    ("surveys.manage", "Kampaniya yeniləndi."): ("Campaign updated.", "Кампания обновлена.", "Kampanya güncellendi."),
    ("surveys.manage", "Naməlum əməliyyat."): ("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
    ("surveys.notify", "Müəllim qiymətləndirmə sorğusu açıldı"): (
        "The teacher evaluation survey is open",
        "Открыт опрос по оценке преподавателей",
        "Öğretmen değerlendirme anketi açıldı",
    ),
    (
        "surveys.notify",
        "Semestr sonu anonim sorğusunu doldurun: müəllimlərinizi qiymətləndirin və "
        "tədrisin yaxşılaşması üçün təklif yazın. Cavablarınız anonimdir.",
    ): (
        "Please complete the end-of-semester anonymous survey: rate your teachers and suggest how teaching could "
        "improve. Your answers are anonymous.",
        "Заполните анонимный опрос в конце семестра: оцените преподавателей и предложите, как улучшить обучение. "
        "Ваши ответы анонимны.",
        "Dönem sonu anonim anketini doldurun: öğretmenlerinizi değerlendirin ve öğretimin iyileşmesi için öneri "
        "yazın. Yanıtlarınız anonimdir.",
    ),
    # ── Tələbə səhifələri ─────────────────────────────────────────────────────
    (_ST, "Anonim sorğu"): ("Anonymous survey", "Анонимный опрос", "Anonim anket"),
    (_ST, "Semestr sonu sorğusu"): ("End-of-semester survey", "Опрос в конце семестра", "Dönem sonu anketi"),
    (_ST, "Müəllimlərinizi anonim qiymətləndirin"): (
        "Rate your teachers anonymously",
        "Оцените своих преподавателей анонимно",
        "Öğretmenlerinizi anonim olarak değerlendirin",
    ),
    (
        _ST,
        "Hər müəllim üçün qısa bir forma — təxminən 2 dəqiqə. Sonda universitetdə nəyi yaxşılaşdırmaq olar sualı var.",
    ): (
        "One short form per teacher — about 2 minutes. At the end there is a question on what the university could improve.",
        "Короткая форма для каждого преподавателя — около 2 минут. В конце — вопрос о том, что можно улучшить в университете.",
        "Her öğretmen için kısa bir form — yaklaşık 2 dakika. Sonunda üniversitede neyin iyileştirilebileceğine dair bir soru var.",
    ),
    (_ST, "%(done)s / %(total)s tamamlanıb"): (
        "%(done)s / %(total)s completed",
        "Выполнено %(done)s / %(total)s",
        "%(done)s / %(total)s tamamlandı",
    ),
    (_ST, "Son tarix: %(day)s"): ("Deadline: %(day)s", "Крайний срок: %(day)s", "Son tarih: %(day)s"),
    (_ST, "Doldurulmayınca kabinet açılmır."): (
        "Your dashboard stays locked until you complete it.",
        "Личный кабинет не откроется, пока опрос не заполнен.",
        "Doldurulmadan kabine açılmaz.",
    ),
    (_ST, "Dolduruldu"): ("Completed", "Заполнено", "Tamamlandı"),
    (_ST, "Qiymətləndir"): ("Rate", "Оценить", "Değerlendir"),
    (_ST, "Ümumi suallar"): ("General questions", "Общие вопросы", "Genel sorular"),
    (_ST, "Tədris prosesi, şərait və təklifləriniz"): (
        "Teaching process, conditions and your suggestions",
        "Учебный процесс, условия и ваши предложения",
        "Öğretim süreci, koşullar ve önerileriniz",
    ),
    (_ST, "Müəllimlərdən sonra"): ("After the teachers", "После преподавателей", "Öğretmenlerden sonra"),
    (_ST, "Doldur"): ("Fill in", "Заполнить", "Formu doldur"),
    (_ST, "Davam et"): ("Continue", "Продолжить", "Devam et"),
    (_ST, "Başla"): ("Start", "Начать", "Başlat"),
    (_ST, "Sonra doldur"): ("Fill in later", "Заполнить позже", "Daha sonra doldur"),
    (_ST, "Möhlət %(day)s tarixinə qədərdir (hər dəfə 24 saat)."): (
        "Postponing is possible until %(day)s (24 hours at a time).",
        "Отсрочка возможна до %(day)s (каждый раз на 24 часа).",
        "Erteleme %(day)s tarihine kadar mümkündür (her seferinde 24 saat).",
    ),
    (_ST, "Bu semestrin sorğusunu tam doldurmusunuz. Təşəkkür edirik!"): (
        "You have fully completed this semester's survey. Thank you!",
        "Вы полностью заполнили опрос этого семестра. Спасибо!",
        "Bu dönemin anketini tamamen doldurdunuz. Teşekkür ederiz!",
    ),
    (_ST, "Kabinetə keç"): ("Go to dashboard", "Перейти в кабинет", "Kabineye git"),
    (_ST, "Hazırda sizin üçün açıq sorğu yoxdur."): (
        "There is no open survey for you at the moment.",
        "Сейчас для вас нет открытых опросов.",
        "Şu anda sizin için açık bir anket yok.",
    ),
    (
        _ST,
        "Cavablarınız adınızdan ayrı saxlanılır. Nəticələr yalnız ən azı bir neçə tələbə cavab verdikdə, ümumiləşdirilmiş şəkildə göstərilir.",
    ): (
        "Your answers are stored separately from your name. Results are shown only in aggregate, and only once several students have responded.",
        "Ваши ответы хранятся отдельно от вашего имени. Результаты показываются только в обобщённом виде и лишь когда ответили несколько студентов.",
        "Yanıtlarınız adınızdan ayrı saklanır. Sonuçlar yalnızca birkaç öğrenci yanıt verdiğinde ve toplu biçimde gösterilir.",
    ),
    (_ST, "Sorğu anonimdir — bu, necə təmin olunur"): (
        "The survey is anonymous — here is how",
        "Опрос анонимный — вот как это обеспечивается",
        "Anket anonimdir — bu nasıl sağlanıyor",
    ),
    (_ST, "Nə qeydə alınır"): ("What is recorded", "Что сохраняется", "Neler kaydedilir"),
    (_ST, "Cavablarınızın özü — adınız, tələbə nömrəniz və göndərmə vaxtı OLMADAN."): (
        "Your answers themselves — WITHOUT your name, student number or submission time.",
        "Сами ваши ответы — БЕЗ имени, студенческого номера и времени отправки.",
        "Yanıtlarınızın kendisi — adınız, öğrenci numaranız ve gönderim zamanı OLMADAN.",
    ),
    (
        _ST,
        "Ayrıca, cavabla əlaqəsi olmayan bir qeyd: «bu tələbə bu müəllim üçün sorğunu doldurub» — yalnız təkrar doldurmanın qarşısını almaq və kabineti açmaq üçün.",
    ): (
        "Separately, a note unconnected to your answers: “this student completed the survey for this teacher” — only to prevent duplicates and to unlock the dashboard.",
        "Отдельно — запись, не связанная с ответами: «этот студент заполнил опрос по этому преподавателю» — только чтобы исключить повторы и открыть кабинет.",
        "Ayrıca, yanıtlarla bağlantısı olmayan bir kayıt: “bu öğrenci bu öğretmen için anketi doldurdu” — yalnızca tekrarları önlemek ve kabineyi açmak için.",
    ),
    (_ST, "Kim nə görür"): ("Who sees what", "Кто что видит", "Kim neyi görür"),
    (
        _ST,
        "Kafedra müdiri, tədris şöbəsi, keyfiyyətə nəzarət şöbəsi və universitet rəhbərliyi yalnız ümumiləşdirilmiş nəticələri görür: orta ballar və paylanmalar.",
    ): (
        "Heads of department, the academic office, the quality assurance office and university leadership see only aggregated results: averages and distributions.",
        "Заведующие кафедрами, учебный отдел, отдел контроля качества и руководство университета видят только обобщённые результаты: средние баллы и распределения.",
        "Bölüm başkanları, eğitim birimi, kalite güvence birimi ve üniversite yönetimi yalnızca toplu sonuçları görür: ortalamalar ve dağılımlar.",
    ),
    (
        _ST,
        "Cavab sayı azdırsa (məsələn, 3-dən az), nəticə ümumiyyətlə göstərilmir — kiçik qrupda kimin nə yazdığını tapmaq olmasın.",
    ): (
        "If there are too few answers (for example, fewer than 3), no result is shown at all — so nobody can work out who wrote what in a small group.",
        "Если ответов слишком мало (например, меньше 3), результат не показывается вовсе, чтобы в маленькой группе нельзя было понять, кто что написал.",
        "Yanıt sayı azsa (örneğin 3'ten az), sonuç hiç gösterilmez — küçük bir grupta kimin ne yazdığı anlaşılamasın.",
    ),
    (
        _ST,
        "Sərbəst mətnlər də adsız və qarışıq sırada göstərilir. Mətndə adınızı və ya sizi tanıda biləcək məlumat yazmayın.",
    ): (
        "Free-text answers are also shown without names and in mixed order. Do not write your name or anything that could identify you.",
        "Свободные ответы тоже показываются без имён и в перемешанном порядке. Не пишите своё имя или сведения, по которым вас можно узнать.",
        "Serbest metinler de isimsiz ve karışık sırayla gösterilir. Metne adınızı veya sizi tanıtabilecek bilgi yazmayın.",
    ),
    (
        _ST,
        "Dürüst olun: sorğu jurnallar bağlandıqdan sonra açılır, rəyiniz yalnız tədrisin keyfiyyətini yaxşılaşdırmaq üçün istifadə olunur və qiymətlərinizə heç bir təsir göstərmir.",
    ): (
        "Be honest: the survey opens only after journals are closed, your feedback is used solely to improve teaching quality and has no effect on your grades.",
        "Будьте честны: опрос открывается только после закрытия журналов, ваш отзыв используется только для улучшения качества преподавания и никак не влияет на ваши оценки.",
        "Dürüst olun: anket not defterleri kapandıktan sonra açılır, görüşünüz yalnızca öğretim kalitesini iyileştirmek için kullanılır ve notlarınızı hiçbir şekilde etkilemez.",
    ),
    (_ST, "Sorğu naviqasiyası"): ("Survey navigation", "Навигация по опросу", "Anket gezinmesi"),
    (_ST, "Siyahıya qayıt"): ("Back to the list", "Назад к списку", "Listeye dön"),
    (_ST, "Tədris prosesi və təklifləriniz"): (
        "Teaching process and your suggestions",
        "Учебный процесс и ваши предложения",
        "Öğretim süreci ve önerileriniz",
    ),
    (_ST, "Bəzi suallar cavabsız qalıb və ya düzgün deyil — qırmızı ilə işarələnmiş sualları yoxlayın."): (
        "Some questions are unanswered or invalid — check the questions marked in red.",
        "Некоторые вопросы остались без ответа или заполнены неверно — проверьте вопросы, отмеченные красным.",
        "Bazı sorular yanıtsız kaldı ya da geçersiz — kırmızıyla işaretlenen soruları kontrol edin.",
    ),
    (_ST, "Anonim göndər"): ("Submit anonymously", "Отправить анонимно", "Anonim gönder"),
    (_ST, "Göndərdikdən sonra cavabı dəyişmək mümkün deyil."): (
        "Answers cannot be changed after submission.",
        "После отправки изменить ответы нельзя.",
        "Gönderdikten sonra yanıtlar değiştirilemez.",
    ),
    (_ST, "Təşəkkür edirik!"): ("Thank you!", "Спасибо!", "Teşekkür ederiz!"),
    (
        _ST,
        "Bütün sorğuları doldurdunuz. Cavablarınız anonim şəkildə qeydə alındı və tədrisin yaxşılaşdırılması üçün ümumiləşdirilmiş şəkildə istifadə olunacaq.",
    ): (
        "You have completed all surveys. Your answers were recorded anonymously and will be used in aggregate to improve teaching.",
        "Вы заполнили все опросы. Ваши ответы сохранены анонимно и будут использованы в обобщённом виде для улучшения обучения.",
        "Tüm anketleri doldurdunuz. Yanıtlarınız anonim olarak kaydedildi ve öğretimin iyileştirilmesi için toplu biçimde kullanılacak.",
    ),
    (
        _ST,
        "Baxış rejimində (başqa istifadəçinin profili) sorğu səhifəsi açılmır — anonim sorğunu yalnız tələbənin özü doldura bilər.",
    ): (
        "The survey page does not open in view-as mode (another user's profile) — only the student can fill in the anonymous survey.",
        "В режиме просмотра (профиль другого пользователя) страница опроса не открывается — анонимный опрос может заполнить только сам студент.",
        "Görüntüleme modunda (başka bir kullanıcının profili) anket sayfası açılmaz — anonim anketi yalnızca öğrencinin kendisi doldurabilir.",
    ),
    (_ST, "Bu səhifə yalnız tələbələr üçündür."): (
        "This page is for students only.",
        "Эта страница только для студентов.",
        "Bu sayfa yalnızca öğrenciler içindir.",
    ),
    (_ST, "Təşkilat konteksti tapılmadı."): (
        "Organisation context not found.",
        "Контекст организации не найден.",
        "Kurum bağlamı bulunamadı.",
    ),
    (_ST, "Bu forma sizin üçün açıq deyil."): (
        "This form is not open for you.",
        "Эта форма вам недоступна.",
        "Bu form sizin için açık değil.",
    ),
    (_ST, "Bu sorğunu artıq doldurmusunuz."): (
        "You have already completed this survey.",
        "Вы уже заполнили этот опрос.",
        "Bu anketi zaten doldurdunuz.",
    ),
    (_ST, "Cavabınız anonim şəkildə qeydə alındı."): (
        "Your answer was recorded anonymously.",
        "Ваш ответ сохранён анонимно.",
        "Yanıtınız anonim olarak kaydedildi.",
    ),
    (_ST, "Bu sorğu hazırda qəbul edilmir."): (
        "This survey is not accepting responses right now.",
        "Этот опрос сейчас не принимает ответы.",
        "Bu anket şu anda yanıt kabul etmiyor.",
    ),
    (_ST, "Möhlət müddəti bitib — sorğunu doldurmaq məcburidir."): (
        "The grace period is over — completing the survey is mandatory.",
        "Срок отсрочки истёк — заполнение опроса обязательно.",
        "Erteleme süresi doldu — anketi doldurmak zorunludur.",
    ),
    (_ST, "Sorğunu 24 saat ərzində doldurmağı unutmayın."): (
        "Remember to complete the survey within 24 hours.",
        "Не забудьте заполнить опрос в течение 24 часов.",
        "Anketi 24 saat içinde doldurmayı unutmayın.",
    ),
    # ── Kabinet bölmələri ─────────────────────────────────────────────────────
    (_CB, "Gözləyən qiymətləndirmə: %(counter)s"): (
        "Pending evaluations: %(counter)s",
        "Ожидают оценки: %(counter)s",
        "Bekleyen değerlendirme: %(counter)s",
    ),
    (_CB, "Semestr sonu anonim sorğusu: müəllimlərinizi qiymətləndirin və tədrisin yaxşılaşması üçün təklif yazın."): (
        "End-of-semester anonymous survey: rate your teachers and suggest how teaching could improve.",
        "Анонимный опрос в конце семестра: оцените преподавателей и предложите, как улучшить обучение.",
        "Dönem sonu anonim anketi: öğretmenlerinizi değerlendirin ve öğretimin iyileşmesi için öneri yazın.",
    ),
    (_CB, "Sorğunu tam doldurmusunuz"): (
        "You have completed the survey",
        "Вы полностью заполнили опрос",
        "Anketi tamamen doldurdunuz",
    ),
    (_CB, "Təşəkkür edirik! Cavablarınız anonim şəkildə qeydə alınıb."): (
        "Thank you! Your answers have been recorded anonymously.",
        "Спасибо! Ваши ответы сохранены анонимно.",
        "Teşekkür ederiz! Yanıtlarınız anonim olarak kaydedildi.",
    ),
    (_CB, "%(done)s / %(total)s tamamlanıb"): (
        "%(done)s / %(total)s completed",
        "Выполнено %(done)s / %(total)s",
        "%(done)s / %(total)s tamamlandı",
    ),
    (_CB, "son tarix %(day)s"): ("deadline %(day)s", "крайний срок %(day)s", "son tarih %(day)s"),
    (_CB, "Sorğunu doldur"): ("Fill in the survey", "Заполнить опрос", "Anketi doldur"),
    (_CB, "Hazırda sizin üçün açıq sorğu yoxdur."): (
        "There is no open survey for you at the moment.",
        "Сейчас для вас нет открытых опросов.",
        "Şu anda sizin için açık bir anket yok.",
    ),
    (_CB, "Sorğu nəticələrinə baxmaq üçün icazəniz və ya struktur əhatəniz yoxdur."): (
        "You do not have the permission or structural scope to view survey results.",
        "У вас нет прав или структурного охвата для просмотра результатов опроса.",
        "Anket sonuçlarını görmek için yetkiniz veya yapısal kapsamınız yok.",
    ),
    (_CB, "Hələ heç bir sorğu kampaniyası keçirilməyib."): (
        "No survey campaign has been run yet.",
        "Кампании опросов ещё не проводились.",
        "Henüz hiçbir anket kampanyası yapılmadı.",
    ),
    (_CB, "yalnız sizin struktur əhatəniz"): (
        "your structural scope only",
        "только ваш структурный охват",
        "yalnızca yapısal kapsamınız",
    ),
    (_CB, "Cavablar"): ("Responses", "Ответы", "Yanıtlar"),
    (_CB, "İştirak"): ("Participation", "Участие", "Katılım"),
    (_CB, "Ümumi bal (1–10)"): ("Overall score (1–10)", "Общая оценка (1–10)", "Genel puan (1–10)"),
    (_CB, "Likert indeksi (1–5)"): ("Likert index (1–5)", "Индекс Лайкерта (1–5)", "Likert endeksi (1–5)"),
    (_CB, "Anonimliyi qorumaq üçün nəticələr ən azı %(k)s cavab toplandıqdan sonra göstərilir."): (
        "To protect anonymity, results are shown only after at least %(k)s responses have been collected.",
        "Для защиты анонимности результаты показываются только после сбора не менее %(k)s ответов.",
        "Anonimliği korumak için sonuçlar en az %(k)s yanıt toplandıktan sonra gösterilir.",
    ),
    (_CB, "Müəllim, kafedra və sual üzrə ətraflı analitika, filtrlər və qrafiklər bu bölməyə əlavə olunur."): (
        "Detailed analytics, filters and charts by teacher, department and question are being added to this section.",
        "В этот раздел добавляется подробная аналитика, фильтры и графики по преподавателям, кафедрам и вопросам.",
        "Öğretmen, bölüm ve soru bazında ayrıntılı analizler, filtreler ve grafikler bu bölüme ekleniyor.",
    ),
    (_CB, "Kampaniyaları idarə etmək üçün təşkilat səviyyəsində «survey.manage» icazəsi lazımdır."): (
        "Managing campaigns requires the organisation-level “survey.manage” permission.",
        "Для управления кампаниями нужно право «survey.manage» на уровне организации.",
        "Kampanyaları yönetmek için kurum düzeyinde “survey.manage” yetkisi gerekir.",
    ),
    (
        _CB,
        "RİM semestr jurnallarını bağlayanda həmin dövrün sorğusu özü açılır: %(days)s gün açıq qalır, ilk %(grace)s gün tələbə «Sonra doldur» deyə bilər, sonra kabinet sorğu doldurulmayınca açılmır. Burada kampaniyanı əl ilə də aça, bağlaya və uzada bilərsiniz.",
    ): (
        "When the Digital Development Centre closes the semester journals, that period's survey opens automatically: it stays open for %(days)s days, for the first %(grace)s days students may choose “Fill in later”, after that the dashboard stays locked until the survey is completed. Here you can also open, close and extend a campaign manually.",
        "Когда Центр цифрового развития закрывает журналы семестра, опрос за этот период открывается автоматически: он открыт %(days)s дней, первые %(grace)s дней студент может выбрать «Заполнить позже», затем кабинет не открывается, пока опрос не заполнен. Здесь кампанию можно также открыть, закрыть и продлить вручную.",
        "Dijital Gelişim Merkezi dönem not defterlerini kapattığında o dönemin anketi kendiliğinden açılır: %(days)s gün açık kalır, ilk %(grace)s gün öğrenci “Sonra doldur” diyebilir, sonra anket doldurulmadıkça kabine açılmaz. Burada kampanyayı elle de açabilir, kapatabilir ve uzatabilirsiniz.",
    ),
    (_CB, "Yeni kampaniya — semestr"): ("New campaign — semester", "Новая кампания — семестр", "Yeni kampanya — dönem"),
    (_CB, "Seçilmiş semestr üçün sorğu kampaniyası açılsın? Tələbələrə bildiriş göndəriləcək."): (
        "Open a survey campaign for the selected semester? Students will be notified.",
        "Открыть кампанию опроса для выбранного семестра? Студенты получат уведомление.",
        "Seçilen dönem için anket kampanyası açılsın mı? Öğrencilere bildirim gönderilecek.",
    ),
    (_CB, "Kampaniyanı aç"): ("Open campaign", "Открыть кампанию", "Kampanyayı aç"),
    (_CB, "Açıq"): ("Open", "Открыта", "Açık"),
    (_CB, "Planlaşdırılıb"): ("Scheduled", "Запланирована", "Planlandı"),
    (_CB, "Qaralama"): ("Draft", "Черновик", "Taslak"),
    (_CB, "Bağlı"): ("Closed", "Закрыта", "Kapalı"),
    (_CB, "Jurnal bağlanması ilə"): ("Via journal closing", "По закрытию журнала", "Not defteri kapanışıyla"),
    (_CB, "Əl ilə"): ("Manual", "Вручную", "Elle"),
    (_CB, "Məcburi"): ("Mandatory", "Обязательная", "Zorunlu"),
    (_CB, "Doldurulmuş hədəf"): ("Completed targets", "Заполненные цели", "Doldurulan hedefler"),
    (_CB, "Gözlənilən"): ("Expected", "Ожидается", "Beklenen"),
    (_CB, "Açılış"): ("Opens", "Открытие", "Açılış tarihi"),
    (_CB, "Bağlanma"): ("Closes", "Закрытие", "Kapanış"),
    (_CB, "«Sonra» möhləti"): ("“Later” grace", "Отсрочка «Позже»", "“Sonra” süresi"),
    (_CB, "Minimum qrup (k)"): ("Minimum group (k)", "Минимальная группа (k)", "En küçük grup (k)"),
    (_CB, "Bağlanma tarixi"): ("Closing date", "Дата закрытия", "Kapanış tarihi"),
    (_CB, "«Sonra doldur» son günü"): (
        "Last day for “Fill in later”",
        "Последний день «Заполнить позже»",
        "“Sonra doldur” son günü",
    ),
    (_CB, "Məcburi (kabineti bağlayır)"): (
        "Mandatory (locks the dashboard)",
        "Обязательная (блокирует кабинет)",
        "Zorunlu (kabineyi kilitler)",
    ),
    (_CB, "Yadda saxla"): ("Save", "Сохранить", "Kaydet"),
    (_CB, "Aç"): ("Open", "Открыть", "Etkinleştir"),
    (_CB, "Yeni bağlanma tarixi"): ("New closing date", "Новая дата закрытия", "Yeni kapanış tarihi"),
    (_CB, "Yenidən aç"): ("Reopen", "Открыть снова", "Yeniden aç"),
    (_CB, "Kampaniya bağlansın? Tələbələr artıq cavab göndərə bilməyəcək və kabinet qapısı açılacaq."): (
        "Close the campaign? Students will no longer be able to submit answers and the dashboard lock will be lifted.",
        "Закрыть кампанию? Студенты больше не смогут отправлять ответы, а блокировка кабинета будет снята.",
        "Kampanya kapatılsın mı? Öğrenciler artık yanıt gönderemeyecek ve kabine kilidi kalkacak.",
    ),
    (_CB, "Bağla"): ("Close", "Закрыть", "Kapat"),
    (
        _CB,
        "Hələ heç bir sorğu kampaniyası yoxdur. İlk kampaniya RİM jurnalları bağlayanda özü yaranır və ya yuxarıdan əl ilə açılır.",
    ): (
        "There are no survey campaigns yet. The first one is created automatically when the Digital Development Centre closes the journals, or you can open one manually above.",
        "Кампаний опросов пока нет. Первая создаётся автоматически, когда Центр цифрового развития закрывает журналы, или её можно открыть вручную выше.",
        "Henüz anket kampanyası yok. İlki Dijital Gelişim Merkezi not defterlerini kapattığında kendiliğinden oluşur ya da yukarıdan elle açılabilir.",
    ),
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
