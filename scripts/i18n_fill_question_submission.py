#!/usr/bin/env python3
"""EMSArena i18n — sual göndərişi (question submission) sətirləri. İdempotent.

2026-07 redesign-ə qədər bu feature-in HEÇ BİR template/servis sətri kataloqda
yox idi (makemessages işlədilməmişdi) — EN/RU/TR interfeysdə xam AZ mətn
görünürdü. Bu skript bölmə (filtr/axtarış/səhifələmə), müəllim detalı (qərar
banneri + timeline), mərkəz baxışı (2 yollu qərar), workbench meta kartı,
view mesajları, servis xətaları və bildiriş mətnlərini 4 dildə doldurur.

İstifadə:  python scripts/i18n_fill_question_submission.py
Sonra:     msgfmt ilə .mo kompilyasiyası (deploy skripti/CI onsuz da edir).
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

SECTION_CTX = "accounts.profile.question_submissions"
TEMPLATE_CTX = "exams.template.question_submission"

# ctx -> msgid -> {"en": ..., "ru": ..., "tr": ...}   (az üçün msgstr = msgid)
ENTRIES = {
    SECTION_CTX: {
        "Aktiv filtrlər": {"en": "Active filters", "ru": "Активные фильтры", "tr": "Etkin filtreler"},
        "Baxılır": {"en": "In review", "ru": "На рассмотрении", "tr": "İncelemede"},
        "Başlıq, fənn və ya qrup üzrə axtar…": {
            "en": "Search by title, subject or group…",
            "ru": "Поиск по названию, предмету или группе…",
            "tr": "Başlık, ders veya gruba göre ara…",
        },
        "Başlıq, fənn, qrup və ya müəllim üzrə axtar…": {
            "en": "Search by title, subject, group or teacher…",
            "ru": "Поиск по названию, предмету, группе или преподавателю…",
            "tr": "Başlık, ders, grup veya öğretmene göre ara…",
        },
        "Bu göndəriş həmişəlik silinəcək. Davam edilsin?": {
            "en": "This submission will be permanently deleted. Continue?",
            "ru": "Эта отправка будет удалена безвозвратно. Продолжить?",
            "tr": "Bu gönderim kalıcı olarak silinecek. Devam edilsin mi?",
        },
        "Bu şərtlərə uyğun göndəriş tapılmadı.": {
            "en": "No submissions match these filters.",
            "ru": "По заданным условиям отправок не найдено.",
            "tr": "Bu koşullara uygun gönderim bulunamadı.",
        },
        "Bütün dillər": {"en": "All languages", "ru": "Все языки", "tr": "Tüm diller"},
        "Bütün fakültələr": {"en": "All faculties", "ru": "Все факультеты", "tr": "Tüm fakülteler"},
        "Bütün illər": {"en": "All years", "ru": "Все годы", "tr": "Tüm yıllar"},
        "Bütün kafedralar": {"en": "All departments", "ru": "Все кафедры", "tr": "Tüm bölümler"},
        "Bütün müəllimlər": {"en": "All teachers", "ru": "Все преподаватели", "tr": "Tüm öğretmenler"},
        "Bütün semestrlər": {"en": "All semesters", "ru": "Все семестры", "tr": "Tüm dönemler"},
        "Dil": {"en": "Language", "ru": "Язык", "tr": "Dil"},
        "Düzəlt": {"en": "Edit", "ru": "Редактировать", "tr": "Düzenle"},
        "Düzəliş gözləyən": {"en": "Awaiting corrections", "ru": "Ожидают исправления", "tr": "Düzeltme bekleyen"},
        "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
        "Filtri sil": {"en": "Remove filter", "ru": "Убрать фильтр", "tr": "Filtreyi kaldır"},
        "Filtri təmizlə": {"en": "Clear filters", "ru": "Сбросить фильтры", "tr": "Filtreleri temizle"},
        "Geri qaytarılıb — düzəliş gözlənilir": {
            "en": "Returned — awaiting corrections",
            "ru": "Возвращено — ожидаются исправления",
            "tr": "İade edildi — düzeltme bekleniyor",
        },
        "Göndərişlərdə axtar": {"en": "Search submissions", "ru": "Поиск по отправкам", "tr": "Gönderimlerde ara"},
        "Hamısını təmizlə": {"en": "Clear all", "ru": "Сбросить все", "tr": "Tümünü temizle"},
        "Hələ göndərişiniz yoxdur — «Yeni göndəriş» ilə başlayın.": {
            "en": "You have no submissions yet — start with “New submission”.",
            "ru": "У вас пока нет отправок — начните с «Новая отправка».",
            "tr": "Henüz gönderiminiz yok — «Yeni gönderim» ile başlayın.",
        },
        "Hələ heç bir sual göndərişi yoxdur.": {
            "en": "There are no question submissions yet.",
            "ru": "Пока нет ни одной отправки вопросов.",
            "tr": "Henüz hiç soru gönderimi yok.",
        },
        "Kafedra": {"en": "Department", "ru": "Кафедра", "tr": "Bölüm"},
        "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretmen"},
        "Müəllimlərin göndərdiyi sual toplularına baxın: qəbul edin (banka yazılır) və ya qeydlə geri qaytarın.": {
            "en": "Review question sets submitted by teachers: accept them (saved to a bank) or return them with a note.",
            "ru": "Просматривайте наборы вопросов от преподавателей: принимайте (записываются в банк) или возвращайте с примечанием.",
            "tr": "Öğretmenlerin gönderdiği soru setlerini inceleyin: kabul edin (bankaya yazılır) veya notla iade edin.",
        },
        "Qeydə baxın, düzəldin və yenidən göndərin.": {
            "en": "Read the note, make corrections and resubmit.",
            "ru": "Прочитайте примечание, исправьте и отправьте заново.",
            "tr": "Notu okuyun, düzeltin ve yeniden gönderin.",
        },
        "Qəbul": {"en": "Accepted", "ru": "Принято", "tr": "Kabul"},
        "Qəbul edilmiş": {"en": "Accepted", "ru": "Принятые", "tr": "Kabul edilmiş"},
        "Rədd": {"en": "Rejected", "ru": "Отклонено", "tr": "Red"},
        "Rədd edilmiş": {"en": "Rejected", "ru": "Отклонённые", "tr": "Reddedilmiş"},
        "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Dönem"},
        "Sil": {"en": "Delete", "ru": "Удалить", "tr": "Sil"},
        "Status filtri": {"en": "Status filter", "ru": "Фильтр по статусу", "tr": "Durum filtresi"},
        "Suallarınızı elektron şəkildə imtahan mərkəzinə göndərin — xəbərdarlıqları görün, düzəldin və ya birbaşa göndərin.": {
            "en": "Send your questions to the exam centre electronically — see the warnings, fix them or submit right away.",
            "ru": "Отправляйте вопросы в экзаменационный центр в электронном виде — просматривайте предупреждения, исправляйте или отправляйте сразу.",
            "tr": "Sorularınızı sınav merkezine elektronik olarak gönderin — uyarıları görün, düzeltin veya doğrudan gönderin.",
        },
        "Tədris ili": {"en": "Academic year", "ru": "Учебный год", "tr": "Öğretim yılı"},
        "Yeni göndəriş": {"en": "New submission", "ru": "Новая отправка", "tr": "Yeni gönderim"},
        "Ümumi göndəriş": {"en": "Total submissions", "ru": "Всего отправок", "tr": "Toplam gönderim"},
        "sual": {"en": "questions", "ru": "вопр.", "tr": "soru"},
        "«%(title)s» göndərişini düzəlt": {
            "en": "Edit submission “%(title)s”",
            "ru": "Редактировать отправку «%(title)s»",
            "tr": "«%(title)s» gönderimini düzenle",
        },
        "«%(title)s» göndərişini sil": {
            "en": "Delete submission “%(title)s”",
            "ru": "Удалить отправку «%(title)s»",
            "tr": "«%(title)s» gönderimini sil",
        },
    },
    TEMPLATE_CTX: {
        "(bir və ya bir neçə)": {"en": "(one or more)", "ru": "(одна или несколько)", "tr": "(bir veya birkaç)"},
        "(boşdursa başlıq götürülür)": {
            "en": "(if empty, the title is used)",
            "ru": "(если пусто — берётся название)",
            "tr": "(boşsa başlık kullanılır)",
        },
        "(opsional)": {"en": "(optional)", "ru": "(необязательно)", "tr": "(isteğe bağlı)"},
        "Baxılır": {"en": "In review", "ru": "На рассмотрении", "tr": "İncelemede"},
        "Başlıq": {"en": "Title", "ru": "Название", "tr": "Başlık"},
        "Boş saxlasanız suallar yeni banka yazılacaq.": {
            "en": "Leave empty to write the questions to a new bank.",
            "ru": "Если оставить пустым, вопросы будут записаны в новый банк.",
            "tr": "Boş bırakırsanız sorular yeni bir bankaya yazılır.",
        },
        "Bu göndəriş həmişəlik silinəcək. Davam edilsin?": {
            "en": "This submission will be permanently deleted. Continue?",
            "ru": "Эта отправка будет удалена безвозвратно. Продолжить?",
            "tr": "Bu gönderim kalıcı olarak silinecek. Devam edilsin mi?",
        },
        "Bu göndərişdə %(count)s xətalı sual var — qəbul etməzdən əvvəl aşağıdakı siyahıda yoxlayın.": {
            "en": "This submission has %(count)s questions with errors — check the list below before accepting.",
            "ru": "В этой отправке вопросов с ошибками: %(count)s — проверьте список ниже перед принятием.",
            "tr": "Bu gönderimde %(count)s hatalı soru var — kabul etmeden önce aşağıdaki listede kontrol edin.",
        },
        "Bu mətn müəllimin göndəriş səhifəsində banner kimi görünəcək.": {
            "en": "This text will be shown to the teacher as a banner on the submission page.",
            "ru": "Этот текст будет показан преподавателю баннером на странице отправки.",
            "tr": "Bu metin öğretmenin gönderim sayfasında banner olarak görünecek.",
        },
        "Dil, fənn və qrup mütləqdir": {
            "en": "Language, subject and group are required",
            "ru": "Язык, предмет и группа обязательны",
            "tr": "Dil, ders ve grup zorunludur",
        },
        "Dili seçin…": {"en": "Select language…", "ru": "Выберите язык…", "tr": "Dil seçin…"},
        "Düzəliş et": {"en": "Edit", "ru": "Внести изменения", "tr": "Düzenle"},
        "Düzəlt və yenidən göndər": {
            "en": "Fix and resubmit",
            "ru": "Исправить и отправить заново",
            "tr": "Düzelt ve yeniden gönder",
        },
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
        "Fənni seçin…": {"en": "Select subject…", "ru": "Выберите предмет…", "tr": "Ders seçin…"},
        "Geri qaytar": {"en": "Return", "ru": "Вернуть", "tr": "İade et"},
        "Geri qaytarılıb": {"en": "Returned", "ru": "Возвращено", "tr": "İade edildi"},
        "Göndərildi": {"en": "Submitted", "ru": "Отправлено", "tr": "Gönderildi"},
        "Göndərilmiş suallar": {"en": "Submitted questions", "ru": "Отправленные вопросы", "tr": "Gönderilen sorular"},
        "Göndəriş məlumatları": {"en": "Submission details", "ru": "Данные отправки", "tr": "Gönderim bilgileri"},
        "Göndəriş qeydlə müəllimə qaytarılacaq — düzəldib yenidən göndərə bilər.": {
            "en": "The submission will be returned to the teacher with a note — they can fix it and resubmit.",
            "ru": "Отправка будет возвращена преподавателю с примечанием — он сможет исправить и отправить заново.",
            "tr": "Gönderim notla öğretmene iade edilecek — düzeltip yeniden gönderebilir.",
        },
        "Göndəriş qəbul edildi": {"en": "Submission accepted", "ru": "Отправка принята", "tr": "Gönderim kabul edildi"},
        "Göndərişi sil": {"en": "Delete submission", "ru": "Удалить отправку", "tr": "Gönderimi sil"},
        "Göndərişin statusu": {"en": "Submission status", "ru": "Статус отправки", "tr": "Gönderim durumu"},
        "Göndərişlərə qayıt": {"en": "Back to submissions", "ru": "К отправкам", "tr": "Gönderimlere dön"},
        "Göndərişə baxış": {"en": "Submission review", "ru": "Просмотр отправки", "tr": "Gönderim incelemesi"},
        "Müəllim nəyi düzəltməlidir?": {
            "en": "What should the teacher fix?",
            "ru": "Что должен исправить преподаватель?",
            "tr": "Öğretmen neyi düzeltmeli?",
        },
        "Müəllimin qeydi": {"en": "Teacher's note", "ru": "Примечание преподавателя", "tr": "Öğretmenin notu"},
        "Müəllimə qeyd": {"en": "Note to the teacher", "ru": "Примечание преподавателю", "tr": "Öğretmene not"},
        "Qeydiniz": {"en": "Your note", "ru": "Ваше примечание", "tr": "Notunuz"},
        "Qrup(lar)": {"en": "Group(s)", "ru": "Группа(ы)", "tr": "Grup(lar)"},
        "Qruplar": {"en": "Groups", "ru": "Группы", "tr": "Gruplar"},
        "Qəbul edildi": {"en": "Accepted", "ru": "Принято", "tr": "Kabul edildi"},
        "Qəbul edilib": {"en": "Accepted", "ru": "Принято", "tr": "Kabul edildi"},
        "Qəbul et": {"en": "Accept", "ru": "Принять", "tr": "Kabul et"},
        "Qəbul et və banka əlavə et": {
            "en": "Accept and add to bank",
            "ru": "Принять и добавить в банк",
            "tr": "Kabul et ve bankaya ekle",
        },
        "Qərar": {"en": "Decision", "ru": "Решение", "tr": "Karar"},
        "Qərar qeydi": {"en": "Decision note", "ru": "Примечание к решению", "tr": "Karar notu"},
        "Qərarınızı seçin": {"en": "Choose your decision", "ru": "Выберите решение", "tr": "Kararınızı seçin"},
        "Sizə hələ fənn təyin olunmayıb — qrupunuza fənn əlavə edilməlidir.": {
            "en": "No subjects are assigned to you yet — a subject must be added to your group.",
            "ru": "Вам ещё не назначены предметы — предмет нужно добавить в вашу группу.",
            "tr": "Size henüz ders atanmadı — grubunuza ders eklenmelidir.",
        },
        "Sizə hələ qrup təyin olunmayıb. Qrup üçün imtahan mərkəzi/administrator ilə əlaqə saxlayın.": {
            "en": "No group is assigned to you yet. Contact the exam centre/administrator for a group.",
            "ru": "Вам ещё не назначена группа. Обратитесь в экзаменационный центр или к администратору.",
            "tr": "Size henüz grup atanmadı. Grup için sınav merkezi/yönetici ile iletişime geçin.",
        },
        "Status": {"en": "Status", "ru": "Статус", "tr": "Durum"},
        "Sual": {"en": "Questions", "ru": "Вопросы", "tr": "Soru"},
        "Sual eyni anda seçilmiş bütün qruplar üçün göndərilir.": {
            "en": "The set is submitted for all selected groups at once.",
            "ru": "Набор отправляется сразу для всех выбранных групп.",
            "tr": "Sorular seçilen tüm gruplar için aynı anda gönderilir.",
        },
        "Sual göndərişi": {"en": "Question submission", "ru": "Отправка вопросов", "tr": "Soru gönderimi"},
        "Suallar": {"en": "Questions", "ru": "Вопросы", "tr": "Sorular"},
        "Suallar hansı banka yazılsın?": {
            "en": "Which bank should the questions go to?",
            "ru": "В какой банк записать вопросы?",
            "tr": "Sorular hangi bankaya yazılsın?",
        },
        "Suallar seçdiyiniz sual bankına yazılacaq və müəllimə bildiriş gedəcək.": {
            "en": "The questions will be written to the selected bank and the teacher will be notified.",
            "ru": "Вопросы будут записаны в выбранный банк, преподаватель получит уведомление.",
            "tr": "Sorular seçtiğiniz soru bankasına yazılacak ve öğretmene bildirim gidecek.",
        },
        "Suallar və xəbərdarlıqlar": {
            "en": "Questions and warnings",
            "ru": "Вопросы и предупреждения",
            "tr": "Sorular ve uyarılar",
        },
        "Sualları yazın və ya fayl yükləyin, önizləyin — xəbərdarlıqları görün, sonra göndərin.": {
            "en": "Type the questions or upload a file, preview them — see the warnings, then submit.",
            "ru": "Введите вопросы или загрузите файл, просмотрите — изучите предупреждения и отправьте.",
            "tr": "Soruları yazın veya dosya yükleyin, önizleyin — uyarıları görün, sonra gönderin.",
        },
        "Sualların yazıldığı dil — mərkəz bankda bu dillə saxlayır.": {
            "en": "The language the questions are written in — the centre stores them in this language.",
            "ru": "Язык, на котором написаны вопросы — центр сохраняет их в банке на этом языке.",
            "tr": "Soruların yazıldığı dil — merkez bankada bu dille saklar.",
        },
        "Xəbərdarlıq": {"en": "Warnings", "ru": "Предупреждения", "tr": "Uyarılar"},
        "Xəbərdarlıqlar": {"en": "Warnings", "ru": "Предупреждения", "tr": "Uyarılar"},
        "Xəta": {"en": "Errors", "ru": "Ошибки", "tr": "Hatalar"},
        "Xətalı": {"en": "With errors", "ru": "С ошибками", "tr": "Hatalı"},
        "Yalnız sizin fənləriniz görünür.": {
            "en": "Only your subjects are shown.",
            "ru": "Показаны только ваши предметы.",
            "tr": "Yalnızca sizin dersleriniz görünür.",
        },
        "Yeni bankın adı": {"en": "New bank name", "ru": "Название нового банка", "tr": "Yeni bankanın adı"},
        "Yenidən göndər": {"en": "Resubmit", "ru": "Отправить заново", "tr": "Yeniden gönder"},
        "Yoxla (preview)": {"en": "Check (preview)", "ru": "Проверить (предпросмотр)", "tr": "Kontrol et (önizleme)"},
        "Yoxlama nəticəsi": {"en": "Check result", "ru": "Результат проверки", "tr": "Kontrol sonucu"},
        "məs. 3-cü sualda düzgün cavab işarələnməyib...": {
            "en": "e.g. the correct answer is not marked in question 3...",
            "ru": "напр., в вопросе 3 не отмечен правильный ответ...",
            "tr": "örn. 3. soruda doğru cevap işaretlenmemiş...",
        },
        "məs. təşəkkürlər, suallar final bankına əlavə olundu…": {
            "en": "e.g. thank you, the questions were added to the final bank…",
            "ru": "напр., спасибо, вопросы добавлены в банк финала…",
            "tr": "örn. teşekkürler, sorular final bankasına eklendi…",
        },
        "%(count)s sual «%(bank)s» bankına yazıldı": {
            "en": "%(count)s questions were written to the “%(bank)s” bank",
            "ru": "Вопросы (%(count)s) записаны в банк «%(bank)s»",
            "tr": "%(count)s soru «%(bank)s» bankasına yazıldı",
        },
        "Ümumi sual sayı": {"en": "Total questions", "ru": "Всего вопросов", "tr": "Toplam soru sayısı"},
        "İmtahan dili": {"en": "Exam language", "ru": "Язык экзамена", "tr": "Sınav dili"},
        "İmtahan mərkəzi": {"en": "Exam centre", "ru": "Экзаменационный центр", "tr": "Sınav merkezi"},
        "İmtahan mərkəzi göndərişi bu məlumatlarla qəbul edəcək.": {
            "en": "The exam centre will receive the submission with these details.",
            "ru": "Экзаменационный центр получит отправку с этими данными.",
            "tr": "Sınav merkezi gönderimi bu bilgilerle alacak.",
        },
        "İmtahan mərkəzi göndərişi geri qaytardı — düzəliş gözlənilir": {
            "en": "The exam centre returned the submission — corrections expected",
            "ru": "Экзаменационный центр вернул отправку — ожидаются исправления",
            "tr": "Sınav merkezi gönderimi iade etti — düzeltme bekleniyor",
        },
        "İmtahan mərkəzindədir": {
            "en": "With the exam centre",
            "ru": "В экзаменационном центре",
            "tr": "Sınav merkezinde",
        },
        "İmtahan mərkəzinə göndər": {
            "en": "Send to the exam centre",
            "ru": "Отправить в экзаменационный центр",
            "tr": "Sınav merkezine gönder",
        },
        "İmtahan mərkəzinə qeyd": {
            "en": "Note to the exam centre",
            "ru": "Примечание экзаменационному центру",
            "tr": "Sınav merkezine not",
        },
        "İmtahan mərkəzinə sual göndər": {
            "en": "Send questions to the exam centre",
            "ru": "Отправить вопросы в экзаменационный центр",
            "tr": "Sınav merkezine soru gönder",
        },
        "Əvvəlcə qərar seçin": {
            "en": "Choose a decision first",
            "ru": "Сначала выберите решение",
            "tr": "Önce karar seçin",
        },
        "— Yeni bank yaradılsın —": {
            "en": "— Create a new bank —",
            "ru": "— Создать новый банк —",
            "tr": "— Yeni banka oluşturulsun —",
        },
    },
    "exams.notification.question_submission": {
        '"{title}" sual göndərişiniz qəbul edildi və sual bankına əlavə olundu.': {
            "en": 'Your question submission "{title}" was accepted and added to the question bank.',
            "ru": "Ваша отправка вопросов «{title}» принята и добавлена в банк вопросов.",
            "tr": '"{title}" soru gönderiminiz kabul edildi ve soru bankasına eklendi.',
        },
        '"{title}" sual göndərişiniz rədd edildi. Qeydə baxıb düzəldərək yenidən göndərə bilərsiniz.': {
            "en": 'Your question submission "{title}" was returned. Read the note, fix the issues and resubmit.',
            "ru": "Ваша отправка вопросов «{title}» возвращена. Прочитайте примечание, исправьте и отправьте заново.",
            "tr": '"{title}" soru gönderiminiz iade edildi. Notu okuyup düzelterek yeniden gönderebilirsiniz.',
        },
        "Sual göndərişinə baxıldı": {
            "en": "Question submission reviewed",
            "ru": "Отправка вопросов рассмотрена",
            "tr": "Soru gönderimi incelendi",
        },
        "Yeni sual göndərişi": {
            "en": "New question submission",
            "ru": "Новая отправка вопросов",
            "tr": "Yeni soru gönderimi",
        },
        '{teacher} "{title}" adlı yeni sual göndərişi etdi ({subject} · {group}, {count} sual).': {
            "en": '{teacher} submitted a new question set "{title}" ({subject} · {group}, {count} questions).',
            "ru": "{teacher} отправил(а) новый набор вопросов «{title}» ({subject} · {group}, вопросов: {count}).",
            "tr": '{teacher} "{title}" adlı yeni soru gönderimi yaptı ({subject} · {group}, {count} soru).',
        },
        '{teacher} "{title}" sual göndərişini düzəldib yenidən göndərdi ({subject} · {group}, {count} sual).': {
            "en": '{teacher} corrected and resubmitted the question set "{title}" ({subject} · {group}, {count} questions).',
            "ru": "{teacher} исправил(а) и заново отправил(а) набор «{title}» ({subject} · {group}, вопросов: {count}).",
            "tr": '{teacher} "{title}" soru gönderimini düzeltip yeniden gönderdi ({subject} · {group}, {count} soru).',
        },
    },
    "exams.service.question_submission.error": {
        "Bank başqa təşkilata aiddir.": {
            "en": "The bank belongs to another organization.",
            "ru": "Банк принадлежит другой организации.",
            "tr": "Banka başka bir kuruluşa ait.",
        },
        "Bu göndəriş artıq yekunlaşıb — dəyişdirilə bilməz.": {
            "en": "This submission is already finalized — it can no longer be changed.",
            "ru": "Эта отправка уже завершена — её нельзя изменить.",
            "tr": "Bu gönderim zaten sonuçlandı — değiştirilemez.",
        },
        "Bu göndərişə artıq baxılıb.": {
            "en": "This submission has already been reviewed.",
            "ru": "Эта отправка уже рассмотрена.",
            "tr": "Bu gönderim zaten incelendi.",
        },
        "Fənn qeyd olunmalıdır.": {
            "en": "Subject is required.",
            "ru": "Укажите предмет.",
            "tr": "Ders belirtilmelidir.",
        },
        "Hansı qrup üçün olduğu qeyd olunmalıdır.": {
            "en": "Specify which group it is for.",
            "ru": "Укажите, для какой группы предназначена отправка.",
            "tr": "Hangi grup için olduğu belirtilmelidir.",
        },
        "Mövzu/başlıq boş ola bilməz.": {
            "en": "Title cannot be empty.",
            "ru": "Название не может быть пустым.",
            "tr": "Başlık boş olamaz.",
        },
        "Mətndən heç bir sual çıxarıla bilmədi.": {
            "en": "No questions could be extracted from the text.",
            "ru": "Из текста не удалось извлечь ни одного вопроса.",
            "tr": "Metinden hiçbir soru çıkarılamadı.",
        },
        "Snapshot-dan heç bir sual banka yazıla bilmədi (A–D variantları natamamdır).": {
            "en": "No questions from the snapshot could be written to the bank (options A–D are incomplete).",
            "ru": "Ни один вопрос из снимка не удалось записать в банк (варианты A–D неполные).",
            "tr": "Anlık görüntüden hiçbir soru bankaya yazılamadı (A–D seçenekleri eksik).",
        },
        "Sual mətni çox qısadır.": {
            "en": "The question text is too short.",
            "ru": "Текст вопросов слишком короткий.",
            "tr": "Soru metni çok kısa.",
        },
    },
    "exams.view.question_submission.ai": {
        "AI sual yaratma alınmadı. Bir az sonra yenidən yoxlayın.": {
            "en": "AI question generation failed. Try again in a moment.",
            "ru": "Не удалось сгенерировать вопросы с помощью ИИ. Повторите попытку позже.",
            "tr": "Yapay zekâ ile soru üretimi başarısız oldu. Az sonra yeniden deneyin.",
        },
        "Sual göndərişi": {"en": "Question submission", "ru": "Отправка вопросов", "tr": "Soru gönderimi"},
    },
    "exams.view.question_submission.error": {
        "Fənni seçin (məcburidir).": {
            "en": "Select a subject (required).",
            "ru": "Выберите предмет (обязательно).",
            "tr": "Ders seçin (zorunlu).",
        },
        "Qəbul olunmuş göndəriş silinə bilməz.": {
            "en": "An accepted submission cannot be deleted.",
            "ru": "Принятую отправку нельзя удалить.",
            "tr": "Kabul edilmiş gönderim silinemez.",
        },
        "Seçilmiş fənn sizin fənləriniz arasında deyil.": {
            "en": "The selected subject is not among your subjects.",
            "ru": "Выбранный предмет не входит в число ваших предметов.",
            "tr": "Seçilen ders sizin dersleriniz arasında değil.",
        },
        "İmtahan dilini seçin (məcburidir).": {
            "en": "Select the exam language (required).",
            "ru": "Выберите язык экзамена (обязательно).",
            "tr": "Sınav dilini seçin (zorunlu).",
        },
        "Ən azı bir qrup seçin (məcburidir).": {
            "en": "Select at least one group (required).",
            "ru": "Выберите хотя бы одну группу (обязательно).",
            "tr": "En az bir grup seçin (zorunlu).",
        },
    },
    "exams.view.question_submission.message": {
        "Fayl oxunmadı: {error}": {
            "en": "Could not read the file: {error}",
            "ru": "Не удалось прочитать файл: {error}",
            "tr": "Dosya okunamadı: {error}",
        },
        "Göndəriş imtahan mərkəzinə çatdırıldı ({count} sual, {groups} qrup).": {
            "en": "The submission was delivered to the exam centre ({count} questions, {groups} groups).",
            "ru": "Отправка доставлена в экзаменационный центр (вопросов: {count}, групп: {groups}).",
            "tr": "Gönderim sınav merkezine iletildi ({count} soru, {groups} grup).",
        },
        'Göndəriş qəbul edildi — {count} sual "{bank}" bankına əlavə olundu.': {
            "en": 'Submission accepted — {count} questions were added to the "{bank}" bank.',
            "ru": "Отправка принята — в банк «{bank}» добавлено вопросов: {count}.",
            "tr": 'Gönderim kabul edildi — {count} soru "{bank}" bankasına eklendi.',
        },
        "Göndəriş rədd edildi və müəllimə bildirildi.": {
            "en": "The submission was returned and the teacher was notified.",
            "ru": "Отправка возвращена, преподаватель уведомлён.",
            "tr": "Gönderim iade edildi ve öğretmene bildirildi.",
        },
        "Göndəriş silindi.": {
            "en": "Submission deleted.",
            "ru": "Отправка удалена.",
            "tr": "Gönderim silindi.",
        },
        "Göndəriş yeniləndi və imtahan mərkəzinə təkrar çatdırıldı.": {
            "en": "The submission was updated and redelivered to the exam centre.",
            "ru": "Отправка обновлена и повторно доставлена в экзаменационный центр.",
            "tr": "Gönderim güncellendi ve sınav merkezine yeniden iletildi.",
        },
        "Rədd üçün müəllimə qeyd yazın — nəyi düzəltməlidir.": {
            "en": "To return it, write a note for the teacher — what needs to be fixed.",
            "ru": "Чтобы вернуть, напишите преподавателю примечание — что нужно исправить.",
            "tr": "İade için öğretmene not yazın — neyi düzeltmesi gerektiğini belirtin.",
        },
        "Yanlış əməliyyat.": {
            "en": "Invalid action.",
            "ru": "Недопустимое действие.",
            "tr": "Geçersiz işlem.",
        },
    },
    "exams.view.question_submission.permission": {
        "Aktiv təşkilat konteksti tapılmadı.": {
            "en": "No active organization context found.",
            "ru": "Активный контекст организации не найден.",
            "tr": "Etkin kuruluş bağlamı bulunamadı.",
        },
        "Bu göndəriş dəyişdirilə bilməz.": {
            "en": "This submission cannot be modified.",
            "ru": "Эту отправку нельзя изменить.",
            "tr": "Bu gönderim değiştirilemez.",
        },
    },
}

# Plural entriləri: ctx -> msgid -> {"plural": msgid_plural, lang: [formalar]}
# (ru: nplurals=4, digərləri: 2)
PLURALS = {
    SECTION_CTX: {
        "%(counter)s sual": {
            "plural": "%(counter)s sual",
            "az": ["%(counter)s sual", "%(counter)s sual"],
            "en": ["%(counter)s question", "%(counter)s questions"],
            "ru": [
                "%(counter)s вопрос",
                "%(counter)s вопроса",
                "%(counter)s вопросов",
                "%(counter)s вопросов",
            ],
            "tr": ["%(counter)s soru", "%(counter)s soru"],
        },
        "İmtahan mərkəzi %(counter)s göndərişi geri qaytarıb.": {
            "plural": "İmtahan mərkəzi %(counter)s göndərişi geri qaytarıb.",
            "az": [
                "İmtahan mərkəzi %(counter)s göndərişi geri qaytarıb.",
                "İmtahan mərkəzi %(counter)s göndərişi geri qaytarıb.",
            ],
            "en": [
                "The exam centre returned %(counter)s submission.",
                "The exam centre returned %(counter)s submissions.",
            ],
            "ru": [
                "Экзаменационный центр вернул %(counter)s отправку.",
                "Экзаменационный центр вернул %(counter)s отправки.",
                "Экзаменационный центр вернул %(counter)s отправок.",
                "Экзаменационный центр вернул %(counter)s отправок.",
            ],
            "tr": [
                "Sınav merkezi %(counter)s gönderimi iade etti.",
                "Sınav merkezi %(counter)s gönderimi iade etti.",
            ],
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations[lang]
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    for ctx, messages in PLURALS.items():
        for msgid, spec in messages.items():
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            forms = spec[lang]
            lines = [
                f'msgctxt "{esc(ctx)}"',
                f'msgid "{esc(msgid)}"',
                f'msgid_plural "{esc(spec["plural"])}"',
            ]
            lines.extend(f'msgstr[{index}] "{esc(form)}"' for index, form in enumerate(forms))
            blocks.append("\n".join(lines) + "\n")
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
