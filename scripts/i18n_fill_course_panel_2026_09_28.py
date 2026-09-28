#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-28 «Kurslarım» paneli redizaynı (course_panel).

Əlavə olunan / DÜZƏLDİLƏN mətnlər:
  * `courses.dashboard` — hero, tablar, panel izahları, üzvlər/qruplar paneli,
    təsdiq dialoqlarının başlıqları;
  * `courses.ai` — REAL «AI ilə kurs qur» çekməcəsi (əvvəl JS-də sərt kodlanmışdı);
  * `courses.partial.member_modal` — reyestr qrup seçicisi;
  * `courses.view.message`, `exams.service.ai_summary.error`, `courses.course_status`.

Mövcud, lakin SƏHV tərcümələr üstələnir (FORCE): status «Draft»→«Qaralama»,
«Released/Выпущенный/Piyasaya sürülmüş» → «Published/Опубликован/Yayında»,
stat_topics «Subject/Предмет/Ders» → «Topics/Темы/Konu», stat_members «Член» və s.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_course_panel_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

D = "courses.dashboard"
AI = "courses.ai"
MM = "courses.partial.member_modal"
VM = "courses.view.message"
ST = "courses.course_status"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    D: {
        "hint_topics": {
            "az": "Kursun sillabusu və həftəlik strukturu",
            "en": "Course syllabus and weekly structure",
            "ru": "Программа курса и понедельная структура",
            "tr": "Ders izlencesi ve haftalık yapı",
        },
        "hint_assignments": {
            "az": "Tələbələr üçün sərbəst işlər və təqdimatlar",
            "en": "Independent work and submissions for students",
            "ru": "Самостоятельные работы и сдачи студентов",
            "tr": "Öğrenciler için ödevler ve teslimler",
        },
        "hint_labs": {
            "az": "Bloklar və suallarla praktiki laboratoriya işləri",
            "en": "Hands-on lab work with blocks and questions",
            "ru": "Практические лабораторные работы с блоками и вопросами",
            "tr": "Bloklar ve sorularla uygulamalı laboratuvar çalışmaları",
        },
        "hint_exams": {
            "az": "Kursa bağlı test və yazılı imtahanlar",
            "en": "Test and written exams linked to the course",
            "ru": "Тестовые и письменные экзамены курса",
            "tr": "Derse bağlı test ve yazılı sınavlar",
        },
        "hint_projects": {
            "az": "Genişmiqyaslı kurs işləri və layihələr",
            "en": "Larger course projects",
            "ru": "Крупные курсовые работы и проекты",
            "tr": "Kapsamlı dönem projeleri",
        },
        "hint_resources": {
            "az": "Mühazirələr, fayllar, video və linklər",
            "en": "Lectures, files, videos and links",
            "ru": "Лекции, файлы, видео и ссылки",
            "tr": "Ders notları, dosyalar, videolar ve bağlantılar",
        },
        "hint_members": {
            "az": "Kursa yazılmış qruplar və tələbələr",
            "en": "Groups and students enrolled in the course",
            "ru": "Группы и студенты, записанные на курс",
            "tr": "Derse kayıtlı gruplar ve öğrenciler",
        },
        "action_publish": {"az": "Yayımla", "en": "Publish", "ru": "Опубликовать", "tr": "Yayınla"},
        "action_unpublish": {
            "az": "Qaralamaya qaytar",
            "en": "Move back to draft",
            "ru": "Вернуть в черновик",
            "tr": "Taslağa geri al",
        },
        "action_remove": {"az": "Çıxar", "en": "Remove", "ru": "Убрать", "tr": "Çıkar"},
        "action_remove_group": {
            "az": "Qrupu kursdan çıxar",
            "en": "Remove group from course",
            "ru": "Убрать группу из курса",
            "tr": "Grubu dersten çıkar",
        },
        "breadcrumb_label": {"az": "Naviqasiya", "en": "Breadcrumb", "ru": "Навигация", "tr": "Gezinti"},
        "sections_label": {
            "az": "Kurs bölmələri",
            "en": "Course sections",
            "ru": "Разделы курса",
            "tr": "Ders bölümleri",
        },
        "stats_label": {"az": "Kurs göstəriciləri", "en": "Course summary", "ru": "Сводка курса", "tr": "Ders özeti"},
        "stat_topics": {"az": "Mövzu", "en": "Topics", "ru": "Темы", "tr": "Konu"},
        "stat_members": {"az": "Üzv", "en": "Members", "ru": "Участники", "tr": "Üye"},
        "stat_students": {"az": "Tələbə", "en": "Students", "ru": "Студенты", "tr": "Öğrenci"},
        "stat_groups": {"az": "Qrup", "en": "Groups", "ru": "Группы", "tr": "Grup"},
        "stat_tasks": {"az": "Tapşırıq", "en": "Tasks", "ru": "Задания", "tr": "Görev"},
        "stat_resources": {"az": "Resurs", "en": "Resources", "ru": "Ресурсы", "tr": "Kaynak"},
        "status_draft": {"az": "Qaralama", "en": "Draft", "ru": "Черновик", "tr": "Taslak"},
        "status_published": {"az": "Yayımlanıb", "en": "Published", "ru": "Опубликован", "tr": "Yayında"},
        "status_archived": {"az": "Arxivdə", "en": "Archived", "ru": "В архиве", "tr": "Arşivde"},
        "message_draft_hidden_students": {
            "az": "Kurs qaralamadır — tələbələr onu hələ görmür. Hazır olanda «Yayımla» düyməsini basın.",
            "en": "This course is a draft — students can't see it yet. Press “Publish” when it's ready.",
            "ru": "Курс в черновике — студенты его пока не видят. Когда будет готов, нажмите «Опубликовать».",
            "tr": "Ders taslak halinde — öğrenciler henüz göremiyor. Hazır olduğunda “Yayınla”ya basın.",
        },
        "message_published_visible_students": {
            "az": "Kurs yayımdadır — tələbələr onu görür.",
            "en": "The course is published — students can see it.",
            "ru": "Курс опубликован — студенты его видят.",
            "tr": "Ders yayında — öğrenciler görebiliyor.",
        },
        "ai_generate": {"az": "AI ilə yarat", "en": "Generate with AI", "ru": "Создать с ИИ", "tr": "AI ile oluştur"},
        "ai_build_title": {
            "az": "AI ilə kurs qur",
            "en": "Build with AI",
            "ru": "Собрать курс с ИИ",
            "tr": "AI ile ders oluştur",
        },
        "confirm_delete_course": {
            "az": "Kurs bütün mövzu, resurs və üzvlükləri ilə birlikdə silinəcək. Bu əməl geri qaytarılmır.",
            "en": "The course will be deleted together with all its topics, resources and memberships. This cannot be undone.",
            "ru": "Курс будет удалён вместе со всеми темами, ресурсами и участниками. Это действие необратимо.",
            "tr": "Ders tüm konuları, kaynakları ve üyelikleriyle birlikte silinecek. Bu işlem geri alınamaz.",
        },
        "confirm_delete_course_title": {
            "az": "Kurs silinsin?",
            "en": "Delete this course?",
            "ru": "Удалить курс?",
            "tr": "Ders silinsin mi?",
        },
        "confirm_delete_topic_title": {
            "az": "Mövzu silinsin?",
            "en": "Delete this topic?",
            "ru": "Удалить тему?",
            "tr": "Konu silinsin mi?",
        },
        "confirm_delete_resource_title": {
            "az": "Resurs silinsin?",
            "en": "Delete this resource?",
            "ru": "Удалить ресурс?",
            "tr": "Kaynak silinsin mi?",
        },
        "confirm_delete_member_title": {
            "az": "Üzv kursdan çıxarılsın?",
            "en": "Remove this member from the course?",
            "ru": "Убрать участника из курса?",
            "tr": "Üye dersten çıkarılsın mı?",
        },
        "confirm_remove_group_title": {
            "az": "Qrup kursdan çıxarılsın?",
            "en": "Remove the group from the course?",
            "ru": "Убрать группу из курса?",
            "tr": "Grup dersten çıkarılsın mı?",
        },
        "confirm_remove_group_body": {
            "az": "«{group}» qrupunun bütün tələbələri kursdan çıxarılacaq. Onların təqdimatları və qiymətləri silinmir.",
            "en": "All students of “{group}” will be removed from the course. Their submissions and grades are kept.",
            "ru": "Все студенты группы «{group}» будут убраны из курса. Их работы и оценки сохранятся.",
            "tr": "“{group}” grubundaki tüm öğrenciler dersten çıkarılacak. Teslimleri ve notları silinmez.",
        },
        "empty_topic_hint": {
            "az": "Həftəlik mövzuları əlavə edin və ya AI-dən sillabus təklifi alın.",
            "en": "Add weekly topics or let AI suggest a syllabus.",
            "ru": "Добавьте темы по неделям или попросите ИИ предложить программу.",
            "tr": "Haftalık konuları ekleyin ya da AI'dan bir izlence önerisi alın.",
        },
        "empty_resource_hint": {
            "az": "Mühazirə faylları, video və faydalı linkləri bir yerdə toplayın.",
            "en": "Keep lecture files, videos and useful links in one place.",
            "ru": "Соберите файлы лекций, видео и полезные ссылки в одном месте.",
            "tr": "Ders dosyalarını, videoları ve faydalı bağlantıları tek yerde toplayın.",
        },
        "empty_members_hint": {
            "az": "Dərs dediyiniz qrupu bir kliklə əlavə edin — bütün tələbələri kursa düşəcək.",
            "en": "Add a group you teach in one click — all of its students join the course.",
            "ru": "Добавьте свою группу одним нажатием — все её студенты попадут в курс.",
            "tr": "Ders verdiğiniz grubu tek tıkla ekleyin — tüm öğrencileri derse katılır.",
        },
        "groups_title": {"az": "Qruplar", "en": "Groups", "ru": "Группы", "tr": "Gruplar"},
        "members_list_title": {"az": "Üzvlər", "en": "Members", "ru": "Участники", "tr": "Üyeler"},
        "members_search_label": {
            "az": "Üzvlər arasında axtar",
            "en": "Search members",
            "ru": "Поиск участников",
            "tr": "Üyelerde ara",
        },
        "members_search_placeholder": {
            "az": "Ad, istifadəçi adı və ya qrup…",
            "en": "Name, username or group…",
            "ru": "Имя, логин или группа…",
            "tr": "Ad, kullanıcı adı veya grup…",
        },
        "members_no_match": {
            "az": "Axtarışa uyğun üzv tapılmadı.",
            "en": "No members match your search.",
            "ru": "Участники по запросу не найдены.",
            "tr": "Aramanızla eşleşen üye bulunamadı.",
        },
    },
    AI: {
        "ai_drawer_title": {
            "az": "AI kurs köməkçisi",
            "en": "AI course assistant",
            "ru": "ИИ-помощник курса",
            "tr": "AI ders asistanı",
        },
        "ai_drawer_sub": {
            "az": "Təklif edir — siz seçib təsdiqləyirsiniz",
            "en": "It suggests — you choose and confirm",
            "ru": "Он предлагает — вы выбираете и подтверждаете",
            "tr": "O önerir — siz seçip onaylarsınız",
        },
        "prompt_label": {
            "az": "Kurs haqqında qısa yazın",
            "en": "Describe the course briefly",
            "ru": "Кратко опишите курс",
            "tr": "Dersi kısaca anlatın",
        },
        "prompt_placeholder": {
            "az": "Məs: «14 həftəlik, 2-ci kurs, praktiki yönümlü; Python əsaslarından OOP-yə qədər»",
            "en": "E.g. “14 weeks, 2nd year, hands-on; from Python basics to OOP”",
            "ru": "Напр.: «14 недель, 2 курс, практика; от основ Python до ООП»",
            "tr": "Örn.: “14 hafta, 2. sınıf, uygulamalı; Python temellerinden OOP'ye”",
        },
        "examples_label": {"az": "Nümunələr", "en": "Examples", "ru": "Примеры", "tr": "Örnekler"},
        "example_1": {
            "az": "15 həftəlik başlanğıc səviyyə, hər həftə bir mövzu",
            "en": "15-week beginner course, one topic per week",
            "ru": "15-недельный курс для начинающих, одна тема в неделю",
            "tr": "15 haftalık başlangıç dersi, haftada bir konu",
        },
        "example_2": {
            "az": "Praktiki yönümlü, hər mövzuya rəsmi sənədləşmə linkləri",
            "en": "Hands-on, with official documentation links for each topic",
            "ru": "С упором на практику, со ссылками на официальную документацию",
            "tr": "Uygulamalı, her konuya resmi dokümantasyon bağlantıları",
        },
        "example_3": {
            "az": "Mövcud mövzulara davam — qalan həftələri tamamla",
            "en": "Continue the existing topics — fill in the remaining weeks",
            "ru": "Продолжить существующие темы — заполнить оставшиеся недели",
            "tr": "Mevcut konulara devam et — kalan haftaları tamamla",
        },
        "note_nothing_saved": {
            "az": "AI mövzular və hər mövzu üçün açıq resurs linkləri təklif edir. Siz seçib təsdiqləməyincə kursa heç nə yazılmır; linkləri açıb yoxlamağı unutmayın.",
            "en": "AI suggests topics and open resource links for each. Nothing is saved until you select and confirm; please open and check the links.",
            "ru": "ИИ предлагает темы и открытые ссылки на ресурсы. Ничего не сохраняется, пока вы не выберете и не подтвердите; проверьте ссылки перед добавлением.",
            "tr": "AI konular ve her konu için açık kaynak bağlantıları önerir. Siz seçip onaylamadıkça hiçbir şey kaydedilmez; bağlantıları açıp kontrol edin.",
        },
        "action_generate": {"az": "Plan hazırla", "en": "Generate plan", "ru": "Составить план", "tr": "Plan oluştur"},
        "generating_title": {
            "az": "AI planı hazırlayır…",
            "en": "AI is drafting the plan…",
            "ru": "ИИ составляет план…",
            "tr": "AI planı hazırlıyor…",
        },
        "generating_sub": {
            "az": "Bu adətən 10–30 saniyə çəkir",
            "en": "This usually takes 10–30 seconds",
            "ru": "Обычно это занимает 10–30 секунд",
            "tr": "Bu genellikle 10–30 saniye sürer",
        },
        "review_title": {"az": "Plan hazırdır", "en": "The plan is ready", "ru": "План готов", "tr": "Plan hazır"},
        "review_sub": {
            "az": "{count} mövzu təklif olunur — lazım olanları seçin",
            "en": "{count} topics suggested — pick the ones you need",
            "ru": "Предложено тем: {count} — выберите нужные",
            "tr": "{count} konu önerildi — gerekenleri seçin",
        },
        "select_all": {"az": "Hamısı", "en": "All", "ru": "Все", "tr": "Tümü"},
        "resources_label": {"az": "Resurslar", "en": "Resources", "ru": "Ресурсы", "tr": "Kaynaklar"},
        "action_apply_selected": {
            "az": "Seçilənləri əlavə et ({count})",
            "en": "Add selected ({count})",
            "ru": "Добавить выбранное ({count})",
            "tr": "Seçilenleri ekle ({count})",
        },
        "applying": {"az": "Əlavə olunur…", "en": "Adding…", "ru": "Добавляем…", "tr": "Ekleniyor…"},
        "action_back": {"az": "Geri", "en": "Back", "ru": "Назад", "tr": "Geri"},
        "action_regenerate": {
            "az": "Yenidən yarat",
            "en": "Regenerate",
            "ru": "Сгенерировать заново",
            "tr": "Yeniden oluştur",
        },
        "done_title": {
            "az": "Kursa əlavə olundu",
            "en": "Added to the course",
            "ru": "Добавлено в курс",
            "tr": "Derse eklendi",
        },
        "done_action": {"az": "Kursa bax", "en": "View course", "ru": "Открыть курс", "tr": "Derse git"},
        "error_generic": {
            "az": "AI cavab vermədi. Bir az sonra yenidən cəhd edin.",
            "en": "The AI did not respond. Please try again in a moment.",
            "ru": "ИИ не ответил. Попробуйте ещё раз чуть позже.",
            "tr": "AI yanıt vermedi. Biraz sonra tekrar deneyin.",
        },
        "quota_remaining": {
            "az": "Bu saat qalan sorğu: {count}",
            "en": "Requests left this hour: {count}",
            "ru": "Осталось запросов в этот час: {count}",
            "tr": "Bu saat kalan istek: {count}",
        },
        "busy": {
            "az": "Əvvəlki plan hələ hazırlanır — bir az gözləyin.",
            "en": "Your previous plan is still being prepared — please wait a moment.",
            "ru": "Предыдущий план ещё готовится — подождите немного.",
            "tr": "Önceki plan hâlâ hazırlanıyor — lütfen biraz bekleyin.",
        },
        "no_permission": {
            "az": "Bu kursda AI ilə dəyişiklik etməyə icazəniz yoxdur.",
            "en": "You are not allowed to change this course with AI.",
            "ru": "У вас нет прав изменять этот курс с помощью ИИ.",
            "tr": "Bu dersi AI ile değiştirme yetkiniz yok.",
        },
        "prompt_required": {
            "az": "Kurs haqqında bir neçə söz yazın.",
            "en": "Write a few words about the course.",
            "ru": "Напишите несколько слов о курсе.",
            "tr": "Ders hakkında birkaç kelime yazın.",
        },
        "plan_empty": {
            "az": "AI istifadə oluna bilən plan qaytarmadı. Təsviri dəqiqləşdirib yenidən cəhd edin.",
            "en": "The AI returned no usable plan. Refine the description and try again.",
            "ru": "ИИ не вернул пригодный план. Уточните описание и попробуйте снова.",
            "tr": "AI kullanılabilir bir plan döndürmedi. Açıklamayı netleştirip tekrar deneyin.",
        },
        "nothing_selected": {
            "az": "Heç bir mövzu seçilməyib.",
            "en": "No topics selected.",
            "ru": "Не выбрано ни одной темы.",
            "tr": "Hiç konu seçilmedi.",
        },
        "apply_failed": {
            "az": "Təkliflər kursa yazıla bilmədi. Yenidən cəhd edin.",
            "en": "The suggestions could not be saved. Please try again.",
            "ru": "Не удалось сохранить предложения. Попробуйте ещё раз.",
            "tr": "Öneriler kaydedilemedi. Tekrar deneyin.",
        },
        "applied_summary": {
            "az": "{topics} mövzu və {resources} resurs kursa əlavə olundu.",
            "en": "Added {topics} topics and {resources} resources to the course.",
            "ru": "В курс добавлено тем: {topics}, ресурсов: {resources}.",
            "tr": "Derse {topics} konu ve {resources} kaynak eklendi.",
        },
    },
    MM: {
        "groups_mine": {"az": "Mənim qruplarım", "en": "My groups", "ru": "Мои группы", "tr": "Gruplarım"},
        "groups_others": {"az": "Digər qruplar", "en": "Other groups", "ru": "Другие группы", "tr": "Diğer gruplar"},
        "group_in_course": {"az": "Kursdadır", "en": "In course", "ru": "Уже в курсе", "tr": "Derste"},
        "groups_mine_empty": {
            "az": "Bu semestr üçün sizə təyin olunmuş qrup tapılmadı. Yuxarıda axtarın.",
            "en": "No groups are assigned to you this semester. Search above.",
            "ru": "В этом семестре за вами не закреплено групп. Воспользуйтесь поиском выше.",
            "tr": "Bu dönem size atanmış grup bulunamadı. Yukarıdan arayın.",
        },
        "groups_search_hint": {
            "az": "Başqa qrupu tapmaq üçün adını yazın (məs. «234 K»).",
            "en": "Type a name to find another group (e.g. “234 K”).",
            "ru": "Чтобы найти другую группу, введите её название (напр. «234 K»).",
            "tr": "Başka bir grup bulmak için adını yazın (ör. “234 K”).",
        },
        "groups_info_text": {
            "az": "Seçilmiş qrupların aktiv tələbələri kursa əlavə olunacaq.",
            "en": "Active students of the selected groups will be added to the course.",
            "ru": "Активные студенты выбранных групп будут добавлены в курс.",
            "tr": "Seçilen grupların aktif öğrencileri derse eklenecek.",
        },
    },
    "courses.partial.member_accordion": {
        "confirm_delete_user": {
            "az": "Tələbə kursdan çıxarılacaq. Təqdimatları və qiymətləri silinmir.",
            "en": "The student will be removed from the course. Their submissions and grades are kept.",
            "ru": "Студент будет убран из курса. Его работы и оценки сохранятся.",
            "tr": "Öğrenci dersten çıkarılacak. Teslimleri ve notları silinmez.",
        },
    },
    VM: {
        "too_many_groups": {
            "az": "Bir dəfəyə ən çox 20 qrup əlavə etmək olar.",
            "en": "You can add at most 20 groups at a time.",
            "ru": "За один раз можно добавить не более 20 групп.",
            "tr": "Tek seferde en fazla 20 grup eklenebilir.",
        },
        "unexpected_error": {
            "az": "Gözlənilməz xəta baş verdi. Yenidən cəhd edin.",
            "en": "An unexpected error occurred. Please try again.",
            "ru": "Произошла непредвиденная ошибка. Попробуйте ещё раз.",
            "tr": "Beklenmeyen bir hata oluştu. Tekrar deneyin.",
        },
    },
    "exams.service.ai_summary.error": {
        "ai_empty_prompt": {
            "az": "Sorğu mətni boşdur.",
            "en": "The request text is empty.",
            "ru": "Текст запроса пуст.",
            "tr": "İstek metni boş.",
        },
    },
    # Məna pozan köhnə tərcümələr: uğur mesajı «...mümkün olmadı» kimi yazılmışdı.
    "assignments.views.message": {
        "assignment_created": {
            "az": "Sərbəst iş yaradıldı.",
            "en": "Assignment created.",
            "ru": "Задание создано.",
            "tr": "Ödev oluşturuldu.",
        },
        "assignment_updated": {
            "az": "Sərbəst iş yeniləndi.",
            "en": "Assignment updated.",
            "ru": "Задание обновлено.",
            "tr": "Ödev güncellendi.",
        },
        "assignment_deleted": {
            "az": "Sərbəst iş silindi.",
            "en": "Assignment deleted.",
            "ru": "Задание удалено.",
            "tr": "Ödev silindi.",
        },
    },
    # Kontekstsiz «Sil» azərbaycanca «Dil» kimi yazılmışdı — bütün kontekstsiz silmə düymələri
    # (məs. sərbəst iş/layihə cavabları səhifəsi) «Dil» göstərirdi.
    "": {
        "Sil": {"az": "Sil", "en": "Delete", "ru": "Удалить", "tr": "Sil"},
        "Son tarix": {"az": "Son tarix", "en": "End date", "ru": "Конечная дата", "tr": "Bitiş tarihi"},
    },
    "review.page": {
        "breadcrumb": {"az": "Naviqasiya", "en": "Breadcrumb", "ru": "Навигация", "tr": "Gezinti"},
        "subtitle": {
            "az": "Tələbə cavablarını yoxlayın, bal və rəy yazın.",
            "en": "Review student submissions, add grades and feedback.",
            "ru": "Проверяйте ответы студентов, ставьте оценки и пишите отзывы.",
            "tr": "Öğrenci teslimlerini inceleyin, not ve geri bildirim verin.",
        },
        "summary": {"az": "Xülasə", "en": "Summary", "ru": "Сводка", "tr": "Özet"},
        "summary_total": {"az": "Cavab", "en": "Submissions", "ru": "Ответы", "tr": "Teslim"},
        "summary_pending": {"az": "Yoxlanılmalı", "en": "To review", "ru": "На проверке", "tr": "İncelenecek"},
        "summary_graded": {"az": "Qiymətləndirilib", "en": "Graded", "ru": "Оценено", "tr": "Notlandı"},
        "summary_average": {"az": "Orta bal", "en": "Average", "ru": "Средний балл", "tr": "Ortalama"},
        "kind_assignment": {"az": "Sərbəst iş", "en": "Assignment", "ru": "Самостоятельная работа", "tr": "Ödev"},
        "kind_lab": {"az": "Lab işi", "en": "Lab work", "ru": "Лабораторная работа", "tr": "Laboratuvar çalışması"},
        "summary_late": {"az": "Gecikmiş", "en": "Late", "ru": "С опозданием", "tr": "Geç"},
        "action_view": {"az": "Bax", "en": "View", "ru": "Просмотр", "tr": "Görüntüle"},
        "kind_project": {"az": "Kurs işi", "en": "Course project", "ru": "Курсовая работа", "tr": "Dönem projesi"},
        "select_all": {"az": "Hamısını seç", "en": "Select all", "ru": "Выбрать все", "tr": "Tümünü seç"},
        "recheck_window": {
            "az": "Yenidən yoxlama üçün qalan vaxt",
            "en": "Time left to re-check",
            "ru": "Время на повторную проверку",
            "tr": "Yeniden inceleme için kalan süre",
        },
        "empty_hint": {
            "az": "Tələbələr cavab göndərdikcə burada görünəcək.",
            "en": "Submissions will appear here as students send them.",
            "ru": "Ответы появятся здесь, когда студенты их отправят.",
            "tr": "Öğrenciler teslim ettikçe burada görünecek.",
        },
    },
    ST: {
        "draft": {"az": "Qaralama", "en": "Draft", "ru": "Черновик", "tr": "Taslak"},
        "published": {"az": "Yayımlanıb", "en": "Published", "ru": "Опубликован", "tr": "Yayında"},
        "archived": {"az": "Arxivdə", "en": "Archived", "ru": "В архиве", "tr": "Arşivde"},
    },
}

# Mövcud olan, amma yanlış/qarışıq dildə olan tərcümələr — həmişə üstələnir.
FORCE = {
    (D, "status_draft"),
    (D, "status_published"),
    (D, "stat_topics"),
    (D, "stat_members"),
    (D, "message_draft_hidden_students"),
    (D, "message_published_visible_students"),
    (D, "ai_generate"),
    (D, "ai_build_title"),
    (D, "confirm_delete_course"),
    (MM, "groups_info_text"),
    ("assignments.views.message", "assignment_created"),
    ("assignments.views.message", "assignment_updated"),
    ("assignments.views.message", "assignment_deleted"),
    ("courses.partial.member_accordion", "confirm_delete_user"),
    ("", "Sil"),
}


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
