#!/usr/bin/env python3
"""EMSArena i18n — Audit 2026-09-28 remediasiyası, iş paketi G (frontend/a11y/i18n).

Bu skript YENİ mətn əlavə etmir — mövcud, lakin SƏHV tərcümələri düzəldir (hamısı FORCE):

  * FQ-I18N-1 — şifrə bərpası səhifələri (`accounts.password_reset_confirm_page` /
    `…complete_page`) və tələbə/müəllim kabinet səhifələri (təyin olunmuş imtahan/kurslar,
    qiymətləndirmə növbəsi, nəticələrim, nəticə təfərrüatı, tələbə paneli) AZ/RU/TR-da
    ingiliscə idi (AZ msgstr-in özü ingiliscə olduğu üçün kataloq qapısı görmürdü);
    `exams.model.proctoring.*` «details» «View answer/details» kimi səhv doldurulmuşdu.
  * FQ-I18N-2 — qeydiyyatda rol seçimləri RU/TR-da təşkilat adına «yığılmışdı»
    (müəllim/işçi = «Школа»/«Okul», kurs işçisi = «Слушатель курса»/«Kurs öğrencisi»).
  * FQ-I18N-3 — `staff.management` tələbə tablarında EN «teacher» yazırdı (6 giriş).
  * FQ-I18N-4 — `profile.groups/student_search_placeholder` RU «…или экзамена»;
    qeydiyyat məxfilik siyasəti və sual bankı axtarışında TR diakritiksiz yazılmışdı
    («Hesabinizi olusturmadan once…»); «Nəticələrim» tablarında sərbəst iş / kurs işi
    terminləri (EN «Free work», RU «Свободные работы»).

Terminologiya (i18n_fix_course_terms_2026_09_28.py ilə eyni): Sərbəst iş → Assignment ·
Самостоятельная работа · Ödev; Kurs işi → Course project · Курсовая работа · Dönem projesi;
Lab işi → Lab work · Лабораторная работа · Laboratuvar çalışması; Kurs → Course · Курс · Ders.

Girişlərdə yalnız düzəldilən dillər verilə bilər (məs. yalnız `tr`); verilməyən dilə
toxunulmur. Kataloqda olmayan (ctx, msgid) keçilir və çap olunur (yeni msgid əlavə ETMİR).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_g_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

PRC = "accounts.password_reset_confirm_page"
PRD = "accounts.password_reset_complete_page"
AE = "accounts.assigned_exams_page"
AC = "accounts.assigned_courses_page"
GQ = "accounts.grading_queue_page"
MR = "accounts.my_results_page"
MRD = "accounts.my_result_detail_page"
MRT = "accounts.my_result_detail.type"
SD = "accounts.student_dashboard"
REG_CHOICE = "accounts.form.register.choice"
REG = "accounts.register"
SM = "staff.management"
QB = "exams.template.teacher_questions_bank"

# ctx → msgid → {lang: msgstr}  (yalnız verilən dillər yazılır)
ENTRIES = {
    # ---- FQ-I18N-1: şifrə bərpası -------------------------------------------------------
    PRC: {
        "title": {"az": "Yeni şifrə", "en": "New password", "ru": "Новый пароль", "tr": "Yeni şifre"},
        "heading_valid": {
            "az": "Yeni şifrə təyin edin",
            "en": "Set a new password",
            "ru": "Задайте новый пароль",
            "tr": "Yeni şifre belirleyin",
        },
        "subheading_valid": {
            "az": "Hesabınız üçün yeni və güclü şifrə daxil edin.",
            "en": "Please enter a new strong password for your account.",
            "ru": "Введите новый надёжный пароль для вашей учётной записи.",
            "tr": "Hesabınız için yeni ve güçlü bir şifre girin.",
        },
        "submit": {"az": "Şifrəni dəyiş", "en": "Change password", "ru": "Сменить пароль", "tr": "Şifreyi değiştir"},
        "heading_invalid": {
            "az": "Keçid etibarsızdır",
            "en": "Invalid link",
            "ru": "Недействительная ссылка",
            "tr": "Geçersiz bağlantı",
        },
        "subheading_invalid": {
            "az": "Bu keçid artıq istifadə olunub və ya vaxtı bitib. Təhlükəsizlik səbəbindən keçidlər birdəfəlikdir.",
            "en": "This link has already been used or has expired. For security reasons links are one-time only.",
            "ru": "Эта ссылка уже использована или срок её действия истёк. В целях безопасности ссылки одноразовые.",
            "tr": "Bu bağlantı zaten kullanılmış veya süresi dolmuş. Güvenlik nedeniyle bağlantılar tek kullanımlıktır.",
        },
        "retry": {
            "az": "Şifrə bərpasını yenidən istəyin",
            "en": "Request password reset again",
            "ru": "Запросить сброс пароля ещё раз",
            "tr": "Şifre sıfırlamayı yeniden isteyin",
        },
    },
    PRD: {
        "title": {"az": "Tamamlandı", "en": "Completed", "ru": "Готово", "tr": "Tamamlandı"},
        "heading": {
            "az": "Şifrə uğurla dəyişdirildi!",
            "en": "Password changed successfully!",
            "ru": "Пароль успешно изменён!",
            "tr": "Şifre başarıyla değiştirildi!",
        },
        "subheading": {
            "az": "Hesabınızın təhlükəsizliyi bərpa olundu. İndi yeni şifrənizlə daxil ola bilərsiniz.",
            "en": "Your account security has been restored. You can now log in with your new password.",
            "ru": "Безопасность вашей учётной записи восстановлена. Теперь вы можете войти с новым паролем.",
            "tr": "Hesabınızın güvenliği yeniden sağlandı. Artık yeni şifrenizle giriş yapabilirsiniz.",
        },
    },
    # ---- FQ-I18N-1: təyin olunmuş imtahan / kurslar ------------------------------------
    AE: {
        "empty_state": {
            "az": "Təyin olunmuş imtahan tapılmadı.",
            "en": "No assigned exams found.",
            "ru": "Назначенные экзамены не найдены.",
            "tr": "Atanmış sınav bulunamadı.",
        },
        "modal_confirm": {"az": "Təsdiqlə", "en": "Confirm", "ru": "Подтвердить", "tr": "Onayla"},
        "modal_prompt_template": {
            "az": "{title} imtahanına daxil olmaq üçün kodu daxil edin.",
            "en": "Enter the code to access the {title} exam.",
            "ru": "Введите код для доступа к экзамену «{title}».",
            "tr": "{title} sınavına erişmek için kodu girin.",
        },
        "modal_text": {
            "az": "İmtahan kodunu daxil edin.",
            "en": "Enter the exam code.",
            "ru": "Введите код экзамена.",
            "tr": "Sınav kodunu girin.",
        },
        "modal_title": {"az": "Giriş kodu", "en": "Access code", "ru": "Код доступа", "tr": "Erişim kodu"},
        "start": {"az": "Başla", "en": "Start", "ru": "Начать", "tr": "Başla"},
        "start_with_code": {
            "az": "Kodla başla",
            "en": "Start with code",
            "ru": "Начать по коду",
            "tr": "Kodla başla",
        },
    },
    AC: {
        "empty_state": {
            "az": "Hələ təyin olunmuş kurs yoxdur.",
            "en": "No courses assigned yet.",
            "ru": "Назначенных курсов пока нет.",
            "tr": "Henüz atanmış ders yok.",
        },
    },
    # ---- FQ-I18N-1: qiymətləndirmə növbəsi (sərbəst işlər) -----------------------------
    GQ: {
        "title": {
            "az": "Qiymətləndirmə növbəsi",
            "en": "Grading queue",
            "ru": "Очередь на оценивание",
            "tr": "Değerlendirme kuyruğu",
        },
        "heading": {
            "az": "Qiymətləndirmə növbəsi",
            "en": "Grading queue",
            "ru": "Очередь на оценивание",
            "tr": "Değerlendirme kuyruğu",
        },
        "empty_title": {"az": "Əla iş!", "en": "Great work!", "ru": "Отличная работа!", "tr": "Harika iş!"},
        "empty_description": {
            "az": "Qiymətləndirmə növbəsi boşdur",
            "en": "The grading queue is empty",
            "ru": "Очередь на оценивание пуста",
            "tr": "Değerlendirme kuyruğu boş",
        },
        "feedback_placeholder": {
            "az": "Rəy (istəyə bağlı)",
            "en": "Feedback (optional)",
            "ru": "Отзыв (необязательно)",
            "tr": "Geri bildirim (isteğe bağlı)",
        },
        "file_download": {"az": "Faylı yüklə", "en": "Download file", "ru": "Скачать файл", "tr": "Dosyayı indir"},
        "file_view": {"az": "Fayla bax", "en": "View file", "ru": "Просмотреть файл", "tr": "Dosyayı görüntüle"},
        "filter_apply": {
            "az": "Filtrləri tətbiq et",
            "en": "Apply filters",
            "ru": "Применить фильтры",
            "tr": "Filtreleri uygula",
        },
        "filter_assignment_all": {
            "az": "Bütün sərbəst işlər",
            "en": "All assignments",
            "ru": "Все самостоятельные работы",
            "tr": "Tüm ödevler",
        },
        "filter_assignment_label": {
            "az": "Sərbəst iş",
            "en": "Assignment",
            "ru": "Самостоятельная работа",
            "tr": "Ödev",
        },
        "filter_course_all": {"az": "Bütün kurslar", "en": "All courses", "ru": "Все курсы", "tr": "Tüm dersler"},
        "filter_course_label": {"az": "Kurs", "en": "Course", "ru": "Курс", "tr": "Ders"},
        "filter_sort_label": {"az": "Sıralama", "en": "Sort", "ru": "Сортировка", "tr": "Sıralama"},
        "loading": {"az": "Yüklənir", "en": "Loading", "ru": "Загрузка", "tr": "Yükleniyor"},
        "score_placeholder": {"az": "Bal", "en": "Score", "ru": "Балл", "tr": "Puan"},
        "sort_newest": {
            "az": "Əvvəlcə yenilər",
            "en": "Newest first",
            "ru": "Сначала новые",
            "tr": "Önce en yeniler",
        },
        "sort_oldest": {
            "az": "Əvvəlcə köhnələr",
            "en": "Oldest first",
            "ru": "Сначала старые",
            "tr": "Önce en eskiler",
        },
        "stat_avg_time": {"az": "Orta vaxt", "en": "Avg. time", "ru": "Среднее время", "tr": "Ort. süre"},
        "stat_graded_today": {
            "az": "Bu gün qiymətləndirilib",
            "en": "Graded today",
            "ru": "Оценено сегодня",
            "tr": "Bugün değerlendirilen",
        },
        "stat_pending": {"az": "Gözləyir", "en": "Pending", "ru": "Ожидают", "tr": "Bekleyen"},
        "table_assignment": {
            "az": "Sərbəst iş",
            "en": "Assignment",
            "ru": "Самостоятельная работа",
            "tr": "Ödev",
        },
        "table_file": {"az": "Fayl", "en": "File", "ru": "Файл", "tr": "Dosya"},
        "table_grading": {"az": "Qiymətləndirmə", "en": "Grading", "ru": "Оценивание", "tr": "Değerlendirme"},
        "table_student": {"az": "Tələbə", "en": "Student", "ru": "Студент", "tr": "Öğrenci"},
        "table_submitted_at": {
            "az": "Göndərilmə vaxtı",
            "en": "Submitted at",
            "ru": "Время отправки",
            "tr": "Gönderilme zamanı",
        },
        "time_ago_suffix": {"az": "əvvəl", "en": "ago", "ru": "назад", "tr": "önce"},
        "toast_error_generic": {
            "az": "Xəta baş verdi!",
            "en": "Something went wrong!",
            "ru": "Что-то пошло не так!",
            "tr": "Bir hata oluştu!",
        },
        "toast_error_prefix": {"az": "Xəta", "en": "Error", "ru": "Ошибка", "tr": "Hata"},
        "toast_success": {
            "az": "Qiymətləndirmə uğurla tamamlandı!",
            "en": "Grading completed successfully!",
            "ru": "Оценивание успешно завершено!",
            "tr": "Değerlendirme başarıyla tamamlandı!",
        },
    },
    # ---- FQ-I18N-1/4: nəticələrim + nəticə təfərrüatı -----------------------------------
    MR: {
        "title": {"az": "Nəticələrim", "en": "My results", "ru": "Мои результаты", "tr": "Sonuçlarım"},
        "heading": {"az": "Nəticələrim", "en": "My results", "ru": "Мои результаты", "tr": "Sonuçlarım"},
        "empty_state": {
            "az": "Heç nə tapılmadı.",
            "en": "No items found.",
            "ru": "Ничего не найдено.",
            "tr": "Hiçbir kayıt bulunamadı.",
        },
        "score_prefix": {"az": "Bal", "en": "Score", "ru": "Балл", "tr": "Puan"},
        "status_graded": {"az": "Qiymətləndirilib", "en": "Graded", "ru": "Оценено", "tr": "Değerlendirildi"},
        "status_pending": {"az": "Gözləyir", "en": "Pending", "ru": "Ожидает", "tr": "Bekliyor"},
        "status_submitted": {"az": "Göndərilib", "en": "Submitted", "ru": "Отправлено", "tr": "Gönderildi"},
        "tab_all": {"az": "Hamısı", "en": "All", "ru": "Все", "tr": "Tümü"},
        "tab_exams": {"az": "İmtahanlar", "en": "Exams", "ru": "Экзамены", "tr": "Sınavlar"},
        "tab_labs": {
            "az": "Laboratoriya işləri",
            "en": "Lab work",
            "ru": "Лабораторные работы",
            "tr": "Laboratuvar çalışmaları",
        },
        # `?type=courses` = sərbəst işlər (Assignment), `?type=independent` = kurs işləri (Project).
        "tab_courses": {"en": "Assignments", "ru": "Самостоятельные работы", "tr": "Ödevler"},
        "tab_independent": {"en": "Course projects", "ru": "Курсовые работы", "tr": "Dönem projeleri"},
        "view_details": {
            "az": "Cavaba və təfərrüatlara bax",
            "en": "View answer and details",
            "ru": "Посмотреть ответ и подробности",
            "tr": "Cevabı ve ayrıntıları görüntüle",
        },
    },
    MRD: {
        "title": {
            "az": "Nəticənin təfərrüatı",
            "en": "Result details",
            "ru": "Подробности результата",
            "tr": "Sonuç ayrıntısı",
        },
        "back_to_results": {"az": "Nəticələrim", "en": "My results", "ru": "Мои результаты", "tr": "Sonuçlarım"},
        "answer_submission_title": {
            "az": "Cavab / təqdimat",
            "en": "Answer / submission",
            "ru": "Ответ / сданная работа",
            "tr": "Cevap / teslim",
        },
        "feedback_missing": {
            "az": "Rəy hələ yoxdur",
            "en": "No feedback yet",
            "ru": "Отзыва пока нет",
            "tr": "Henüz geri bildirim yok",
        },
        "file_name_fallback": {"az": "Fayl", "en": "File", "ru": "Файл", "tr": "Dosya"},
        "label_context": {"az": "Kontekst", "en": "Context", "ru": "Контекст", "tr": "Bağlam"},
        "label_score": {"az": "Bal", "en": "Score", "ru": "Балл", "tr": "Puan"},
        "label_status": {"az": "Status", "en": "Status", "ru": "Статус", "tr": "Durum"},
        "label_submitted_at": {
            "az": "Göndərilmə vaxtı",
            "en": "Submitted at",
            "ru": "Время отправки",
            "tr": "Gönderilme zamanı",
        },
        "label_type": {"az": "Növ", "en": "Type", "ru": "Тип", "tr": "Tür"},
        "no_text_answer": {
            "az": "Mətn cavabı yoxdur",
            "en": "No text answer",
            "ru": "Текстового ответа нет",
            "tr": "Metin cevabı yok",
        },
        "teacher_feedback_title": {
            "az": "Müəllimin rəyi",
            "en": "Teacher feedback",
            "ru": "Отзыв преподавателя",
            "tr": "Öğretmen geri bildirimi",
        },
        "view_file": {"az": "Fayla bax", "en": "View file", "ru": "Просмотреть файл", "tr": "Dosyayı görüntüle"},
        "view_link": {"az": "Keçidi aç", "en": "Open link", "ru": "Открыть ссылку", "tr": "Bağlantıyı aç"},
    },
    MRT: {
        # results.py: "course" = sərbəst iş (Assignment), "independent_work" = kurs işi (Project).
        "course": {"az": "Sərbəst iş", "en": "Assignment", "ru": "Самостоятельная работа", "tr": "Ödev"},
        "independent_work": {
            "az": "Kurs işi",
            "en": "Course project",
            "ru": "Курсовая работа",
            "tr": "Dönem projesi",
        },
        "lab": {
            "az": "Laboratoriya işi",
            "en": "Lab work",
            "ru": "Лабораторная работа",
            "tr": "Laboratuvar çalışması",
        },
    },
    # ---- FQ-I18N-1: tələbə paneli -------------------------------------------------------
    SD: {
        "title": {"az": "Tələbə paneli", "en": "Student dashboard", "ru": "Панель студента", "tr": "Öğrenci paneli"},
        "heading": {
            "az": "Tələbə paneli",
            "en": "Student dashboard",
            "ru": "Панель студента",
            "tr": "Öğrenci paneli",
        },
        "welcome": {"az": "Xoş gəlmisiniz", "en": "Welcome", "ru": "Добро пожаловать", "tr": "Hoş geldiniz"},
        "btn_courses": {"az": "Kurslar", "en": "Courses", "ru": "Курсы", "tr": "Dersler"},
        "btn_exams": {"az": "İmtahanlar", "en": "Exams", "ru": "Экзамены", "tr": "Sınavlar"},
        "widget_courses_title": {"az": "Kurslar", "en": "Courses", "ru": "Курсы", "tr": "Dersler"},
        "widget_assignments_title": {
            "az": "Sərbəst işlər",
            "en": "Assignments",
            "ru": "Самостоятельные работы",
            "tr": "Ödevler",
        },
        # Sayğacdan sonra gələn vahid sözləri («3 kurs», «2 gözləyən» …).
        "course_unit": {"az": "kurs", "en": "courses", "ru": "курс(ов)", "tr": "ders"},
        "pending_unit": {"az": "gözləyən", "en": "pending", "ru": "ожидают", "tr": "bekleyen"},
        "exam_unit": {"az": "imtahan", "en": "exams", "ru": "экзамен(ов)", "tr": "sınav"},
        "answer_unit": {"az": "cavab", "en": "answers", "ru": "ответ(ов)", "tr": "cevap"},
        "start_exam": {"az": "İmtahana başla", "en": "Start exam", "ru": "Начать экзамен", "tr": "Sınava başla"},
        "view_all": {"az": "Hamısına bax", "en": "View all", "ru": "Смотреть все", "tr": "Tümünü gör"},
        "widget_recent_grades_title": {
            "az": "Son qiymətlər",
            "en": "Recent grades",
            "ru": "Последние оценки",
            "tr": "Son notlar",
        },
        "widget_upcoming_exams_title": {
            "az": "Yaxınlaşan imtahanlar",
            "en": "Upcoming exams",
            "ru": "Предстоящие экзамены",
            "tr": "Yaklaşan sınavlar",
        },
    },
    # ---- FQ-I18N-1: proktorinq modelinin «details» sahəsi (admin) ------------------------
    "exams.model.proctoring.field": {
        "details": {"az": "Təfərrüatlar", "en": "Details", "ru": "Подробности", "tr": "Ayrıntılar"},
    },
    "exams.model.proctoring.help": {
        "details": {
            "az": "Hadisəyə aid əlavə məlumat (JSON).",
            "en": "Additional event data (JSON).",
            "ru": "Дополнительные данные события (JSON).",
            "tr": "Olayla ilgili ek veriler (JSON).",
        },
    },
    # ---- FQ-I18N-2: qeydiyyat rol seçimləri (RU/TR yığılmışdı) --------------------------
    REG_CHOICE: {
        "org_type_school_teacher": {"ru": "Учитель школы", "tr": "Okul öğretmeni"},
        "org_type_university_teacher": {"ru": "Преподаватель университета", "tr": "Üniversite öğretim elemanı"},
        "org_type_course_teacher": {"ru": "Преподаватель учебного центра", "tr": "Kurs merkezi öğretmeni"},
        "org_type_school_staff": {"ru": "Сотрудник школы", "tr": "Okul personeli"},
        "org_type_university_staff": {"ru": "Сотрудник университета", "tr": "Üniversite personeli"},
        "org_type_course_staff": {
            "en": "Course center staff",
            "ru": "Сотрудник учебного центра",
            "tr": "Kurs merkezi personeli",
        },
    },
    # ---- FQ-I18N-3: heyət idarəsi — tələbə tabları EN-də «teacher» deyirdi ---------------
    SM: {
        "Students without organization": {"en": "Students without organization"},
        "No student found.": {"en": "No student found."},
        "Search pending students...": {"en": "Search pending students..."},
        "There are no pending students.": {"en": "There are no pending students."},
        "Students who can be invited appear here.": {"en": "Students who can be invited appear here."},
        "No student available for invitation.": {"en": "No student available for invitation."},
    },
    # ---- FQ-I18N-4: RU yanlış məna ------------------------------------------------------
    "profile.groups": {
        "student_search_placeholder": {"ru": "Поиск по имени студента, логину или e-mail"},
    },
    # ---- FQ-I18N-4: TR diakritiksiz mətnlər (məxfilik siyasəti, sual bankı) --------------
    "accounts.form.register.label": {
        "accept_privacy_policy": {"tr": "Gizlilik Politikası'nı okudum ve kabul ediyorum."},
    },
    "accounts.form.register.error": {
        "privacy_policy_required": {"tr": "Devam etmek için Gizlilik Politikası'nı kabul etmelisiniz."},
    },
    REG: {
        "privacy_accept_hint": {
            "tr": "Tam metni pencerede açıp inceledikten sonra kaydınızı tamamlayın.",
        },
        "privacy_card_title": {"tr": "Gizlilik ve veri işleme"},
        "privacy_card_description": {
            "tr": (
                "Hesabınızı oluşturmadan önce EMSArena'nın kayıt ve eğitim sürecinde kişisel verileri "
                "nasıl kullandığını inceleyin."
            ),
        },
        "privacy_modal_eyebrow": {"tr": "EMSArena kayıt politikası"},
        "privacy_modal_title": {"tr": "Gizlilik Politikası"},
        "privacy_open_button": {"tr": "Gizlilik Politikası'nı aç"},
        "privacy_modal_summary_badge": {"tr": "Kısa ve net özet"},
        "privacy_modal_intro": {
            "tr": (
                "Bu politika, hesap oluştururken, bir kuruma katılırken ve EMSArena içindeki ders, sınav, "
                "laboratuvar, ödev ve canlı oturum özelliklerini kullanırken bilgilerinizin nasıl işlendiğini "
                "açıklar."
            ),
        },
        "privacy_modal_summary": {
            "tr": (
                "Verileriniz hesabınızı oluşturmak, girişi güvenli tutmak, kurum üyeliğini yönetmek ve "
                "platformun eğitim özelliklerini çalıştırmak için kullanılır. Verileriniz satılmaz ve yalnızca "
                "hizmet için gerekli olduğunda paylaşılır."
            ),
        },
        "privacy_section_access_title": {"tr": "Kurum içindeki görünürlük"},
        "privacy_section_access_body": {
            "tr": (
                "Bir okula, üniversiteye veya kurs merkezine katıldığınızda, o kurumdaki yetkili yöneticiler "
                "ve eğitmenler temel profil bilgilerinizi, üyelik durumunuzu ve rolünüzle ilgili öğrenme "
                "faaliyetlerini görebilir."
            ),
        },
        "privacy_section_data_body": {
            "tr": (
                "Kayıt sırasında kullanıcı adınızı, adınızı, soyadınızı, e-posta adresinizi, ülkenizi, "
                "seçtiğiniz hesap türünü ve kurum bilgilerinizi toplarız. Platformu kullandıkça dersler, "
                "sınavlar, laboratuvarlar, ödevler, sonuçlar ve üyelik hareketleriyle ilgili operasyonel "
                "kayıtlar da oluşabilir."
            ),
        },
        "privacy_section_use_title": {"tr": "Verileri nasıl kullanıyoruz"},
        "privacy_section_use_body": {
            "tr": (
                "Bu veriler hesabınızı oluşturmak, e-posta OTP doğrulaması göndermek, çalışma alanı ve kurum "
                "erişimini yönetmek, ders ve sınav akışlarını çalıştırmak, sonuçları göstermek ve denetim ile "
                "güvenlik kontrollerini desteklemek için kullanılır."
            ),
        },
        "privacy_section_sharing_title": {"tr": "Veriler kimlerle paylaşılır"},
        "privacy_section_sharing_body": {
            "tr": (
                "Bilgileriniz satılmaz. Verileriniz yalnızca seçtiğiniz kurumun yetkili yöneticileriyle, "
                "e-posta doğrulaması veya barındırma gibi teknik hizmet sağlayıcılarıyla ve yasal zorunluluk "
                "durumunda ilgili taraflarla paylaşılabilir."
            ),
        },
        "privacy_section_retention_title": {"tr": "Saklama ve güvenlik"},
        "privacy_section_retention_body": {
            "tr": (
                "Bilgiler hizmetin çalışması, denetim ve anlaşmazlık incelemeleri için gerekli olduğu sürece "
                "saklanır. OTP doğrulaması gibi hassas akışlar kısa ömürlüdür ve sistem genelinde teknik ve "
                "organizasyonel güvenlik önlemleri uygulanır."
            ),
        },
        "privacy_section_rights_title": {"tr": "Haklarınız"},
        "privacy_section_rights_body": {
            "tr": (
                "Profil bilgilerinizi güncelleyebilir, kurum tercihlerinizi değiştirebilir ve hesap "
                "verilerinizle ilgili açıklama veya silme talebinde bulunabilirsiniz. Bu hakları kullanmak "
                "için platform yöneticisiyle iletişime geçebilirsiniz."
            ),
        },
    },
    QB: {
        "placeholder_search_questions": {"tr": "Soru metni, blok veya cevap seçeneğine göre ara..."},
        "empty_no_results": {"tr": "Aramanıza uygun soru bulunamadı."},
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    changed = 0
    missing = []
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values.get(lang)
            if want is None:
                continue
            entry = index.get((ctx, msgid))
            if entry is None:
                missing.append((ctx, msgid))
                continue
            # Bu skriptdəki hər giriş düzəlişdir (FORCE) — mövcud səhv msgstr üstələnir.
            if entry.msgstr != want or "fuzzy" in entry.flags or entry.obsolete:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: {changed} düzəliş")
    for ctx, msgid in missing:
        print(f"  ! kataloqda yoxdur, keçildi: {ctx!r} / {msgid!r}")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
