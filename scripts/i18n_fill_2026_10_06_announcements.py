#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-06: «Elanlar» modulu (kabinet bölməsi, popup, idarə səhifələri, icazə).

Kontekstlər: `announcements.{api,apply,cabinet,manage,model,popup}`, `profile.sidebar|Elanlar`,
`organizations.permission.label` (``announcement.manage``). Cəm formalı iki mətn
(«%(n)s elan», «%(n)s gün qaldı») ``msgid_plural`` ilə yazılır.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_06_announcements.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "announcements.api": {
        "Aktiv təşkilat konteksti yoxdur.": (
            "No active organization context.",
            "Нет активного контекста организации.",
            "Etkin kurum bağlamı yok.",
        ),
        "Elan seçilməyib.": ("No announcement selected.", "Объявление не выбрано.", "Duyuru seçilmedi."),
        "Giriş tələb olunur.": ("Login required.", "Требуется вход.", "Giriş gerekli."),
    },
    "announcements.apply": {
        # 2026-10-07: yumşaq silinmiş elana müraciət.
        "Elan silinib — müraciət qəbul olunmur.": (
            "The announcement was deleted — applications are not accepted.",
            "Объявление удалено — заявки не принимаются.",
            "Duyuru silindi — başvuru kabul edilmiyor.",
        ),
        "Baxış rejimində müraciət etmək olmaz.": (
            "You cannot apply in view-as mode.",
            "В режиме просмотра подать заявку нельзя.",
            "Görüntüleme modunda başvuru yapılamaz.",
        ),
        "Bu elan üzrə müraciət nəzərdə tutulmayıb.": (
            "This announcement does not accept applications.",
            "По этому объявлению заявки не предусмотрены.",
            "Bu duyuru için başvuru öngörülmemiş.",
        ),
        "Elan": ("Announcement", "Объявление", "Duyuru"),
        "Elan: %(title)s": ("Announcement: %(title)s", "Объявление: %(title)s", "Duyuru: %(title)s"),
        "Elanın müddəti bitib.": ("The announcement has expired.", "Срок объявления истёк.", "Duyurunun süresi doldu."),
        "Müraciət ünvanı konfiqurasiya olunmayıb — elanın müəllifinə bildirin.": (
            "The application destination is not configured — please tell the announcement's author.",
            "Адресат заявки не настроен — сообщите автору объявления.",
            "Başvuru adresi yapılandırılmamış — duyurunun yazarına bildirin.",
        ),
        "Müraciətin son tarixi keçib.": (
            "The application deadline has passed.",
            "Срок подачи заявок истёк.",
            "Başvurunun son tarihi geçti.",
        ),
        "Qeyd ən çox %(n)s simvol ola bilər.": (
            "The note can be at most %(n)s characters.",
            "Примечание может содержать не более %(n)s символов.",
            "Not en fazla %(n)s karakter olabilir.",
        ),
        "«%(title)s» elanına müraciət.": (
            "Application for the announcement “%(title)s”.",
            "Заявка по объявлению «%(title)s».",
            "“%(title)s” duyurusuna başvuru.",
        ),
    },
    "announcements.cabinet": {
        "%(day)s tarixinədək": ("until %(day)s", "до %(day)s", "%(day)s tarihine kadar"),
        "%(page)s / %(pages)s": ("%(page)s of %(pages)s", "%(page)s из %(pages)s", "Sayfa %(page)s / %(pages)s"),
        "Aktiv": ("Active", "Активные", "Aktif"),
        "Axtarış sözünü dəyişin və ya filtrləri sıfırlayın.": (
            "Change the search term or reset the filters.",
            "Измените запрос или сбросьте фильтры.",
            "Arama terimini değiştirin veya filtreleri sıfırlayın.",
        ),
        "Baxış rejimində müraciət etmək olmaz.": (
            "You cannot apply in view-as mode.",
            "В режиме просмотра подать заявку нельзя.",
            "Görüntüleme modunda başvuru yapılamaz.",
        ),
        "Başlıq və ya mətndə axtar…": (
            "Search title or text…",
            "Поиск по заголовку или тексту…",
            "Başlıkta veya metinde ara…",
        ),
        "Bu gün son gündür": ("Today is the last day", "Сегодня последний день", "Bugün son gün"),
        "Bütün elanlar": ("All announcements", "Все объявления", "Tüm duyurular"),
        "Bütün kateqoriyalar": ("All categories", "Все категории", "Tüm kategoriler"),
        "Dərc: %(day)s": ("Published: %(day)s", "Опубликовано: %(day)s", "Yayın: %(day)s"),
        "Elan filtrləri": ("Announcement filters", "Фильтры объявлений", "Duyuru filtreleri"),
        "Elan silinib, arxivlənib və ya sizə ünvanlanmayıb.": (
            "The announcement was deleted, archived or is not addressed to you.",
            "Объявление удалено, архивировано или адресовано не вам.",
            "Duyuru silinmiş, arşivlenmiş veya size yönelik değil.",
        ),
        "Elan tapılmadı": ("Announcement not found", "Объявление не найдено", "Duyuru bulunamadı"),
        "Elanlar üçün aktiv təşkilat konteksti tapılmadı.": (
            "No active organization context for announcements.",
            "Не найден активный контекст организации для объявлений.",
            "Duyurular için etkin kurum bağlamı bulunamadı.",
        ),
        "Elanlarda axtar": ("Search announcements", "Поиск по объявлениям", "Duyurularda ara"),
        "Elanları idarə et": ("Manage announcements", "Управление объявлениями", "Duyuruları yönet"),
        "Elanları yükləmək alınmadı. Bir az sonra yenidən cəhd edin.": (
            "Could not load announcements. Please try again shortly.",
            "Не удалось загрузить объявления. Повторите попытку позже.",
            "Duyurular yüklenemedi. Biraz sonra tekrar deneyin.",
        ),
        "Filtrə uyğun elan tapılmadı": (
            "No announcements match the filters",
            "Нет объявлений по выбранным фильтрам",
            "Filtreye uyan duyuru bulunamadı",
        ),
        "Hamısı": ("All", "Все", "Tümü"),
        "Hazırda sizə aid aktiv elan yoxdur": (
            "There are no active announcements for you right now",
            "Сейчас для вас нет активных объявлений",
            "Şu anda size ait etkin duyuru yok",
        ),
        "Kateqoriya": ("Category", "Категория", "Kategori"),
        "Keçid %(day)s tarixində açılıb.": (
            "The link was opened on %(day)s.",
            "Ссылка открыта %(day)s.",
            "Bağlantı %(day)s tarihinde açıldı.",
        ),
        "Keçidi yenidən aç": ("Open the link again", "Открыть ссылку снова", "Bağlantıyı yeniden aç"),
        "Müddəti bitib": ("Expired", "Срок истёк", "Süresi doldu"),
        "Müddəti bitmiş": ("Expired", "Истёкшие", "Süresi dolmuş"),
        "Müddəti bitmiş elan yoxdur": (
            "No expired announcements",
            "Нет истёкших объявлений",
            "Süresi dolmuş duyuru yok",
        ),
        "Müraciət": ("Application", "Заявка", "Başvuru"),
        "Müraciət edilib: %(number)s (%(day)s). Statusunu «Müraciətlərim» bölməsində izləyin.": (
            "Applied: %(number)s (%(day)s). Track its status in “My applications”.",
            "Заявка подана: %(number)s (%(day)s). Следите за статусом в разделе «Мои заявки».",
            "Başvuruldu: %(number)s (%(day)s). Durumunu “Başvurularım” bölümünden izleyin.",
        ),
        "Müraciət et": ("Apply", "Подать заявку", "Başvur"),
        "Müraciət göndərilmədi. Bir az sonra yenidən cəhd edin.": (
            "The application was not sent. Please try again shortly.",
            "Заявка не отправлена. Повторите попытку позже.",
            "Başvuru gönderilmedi. Biraz sonra tekrar deneyin.",
        ),
        "Müraciət mümkündür": ("Applications open", "Можно подать заявку", "Başvuru yapılabilir"),
        "Müraciət edilib": ("Applied", "Заявка подана", "Başvuruldu"),
        "Müraciət xarici keçid vasitəsilə qəbul olunur.": (
            "Applications are accepted via an external link.",
            "Заявки принимаются по внешней ссылке.",
            "Başvurular dış bağlantı üzerinden kabul edilir.",
        ),
        "Müraciətiniz göndərildi": (
            "Your application has been sent",
            "Ваша заявка отправлена",
            "Başvurunuz gönderildi",
        ),
        "Müraciətiniz «%(kind)s» növü ilə aidiyyəti şöbəyə göndəriləcək.": (
            "Your application will be sent as “%(kind)s” to the responsible office.",
            "Заявка будет отправлена с типом «%(kind)s» в ответственный отдел.",
            "Başvurunuz “%(kind)s” türüyle ilgili birime gönderilecek.",
        ),
        "Müraciətiniz «%(kind)s» növü ilə «%(unit)s» şöbəsinə göndəriləcək.": (
            "Your application will be sent as “%(kind)s” to “%(unit)s”.",
            "Заявка будет отправлена с типом «%(kind)s» в отдел «%(unit)s».",
            "Başvurunuz “%(kind)s” türüyle “%(unit)s” birimine gönderilecek.",
        ),
        "Növbəti": ("Next", "Далее", "Sonraki"),
        "Oxunmamış": ("Unread", "Непрочитанные", "Okunmamış"),
        "Prioritet": ("Priority", "Приоритет", "Öncelik"),
        "Qeyd (könüllü)": ("Note (optional)", "Примечание (необязательно)", "Not (isteğe bağlı)"),
        "Qüvvədədir: %(day)s tarixinədək": (
            "Valid until %(day)s",
            "Действует до %(day)s",
            "%(day)s tarihine kadar geçerli",
        ),
        "Sancılmış": ("Pinned", "Закреплено", "Sabitlenmiş"),
        "Son tarix": ("Deadline", "Крайний срок", "Son tarih"),
        "Son tarix keçib": ("Deadline passed", "Срок истёк", "Son tarih geçti"),
        "Son tarix yaxın olan": ("Nearest deadline", "Ближайший срок", "Son tarihi yakın olan"),
        "Son tarix: %(day)s": ("Deadline: %(day)s", "Крайний срок: %(day)s", "Son tarih: %(day)s"),
        "Son tarixli": ("With deadline", "Со сроком", "Son tarihli"),
        "Sıralama": ("Sort", "Сортировка", "Sırala"),
        "Səhifələr": ("Pages", "Страницы", "Sayfalar"),
        "Sənədlər": ("Documents", "Документы", "Belgeler"),
        "Universitetin, fakültənizin və kafedranızın sizə ünvanladığı elanlar. Son tarixi olan elanlar ayrıca işarələnir.": (
            "Announcements addressed to you by the university, your faculty and department. Announcements with a deadline are marked.",
            "Объявления университета, вашего факультета и кафедры. Объявления со сроком отмечены отдельно.",
            "Üniversitenin, fakültenizin ve bölümünüzün size yönelik duyuruları. Son tarihli duyurular ayrıca işaretlenir.",
        ),
        "Vəziyyət": ("Status", "Статус", "Durum"),
        "Yeni": ("New", "Новое", "Okunmadı"),
        "Yeni elan dərc olunanda burada görünəcək.": (
            "New announcements will appear here when published.",
            "Новые объявления появятся здесь после публикации.",
            "Yeni duyurular yayınlandığında burada görünecek.",
        ),
        "İstifadəçi burada «Müraciət et» düyməsini görəcək.": (
            "Users will see the “Apply” button here.",
            "Здесь пользователь увидит кнопку «Подать заявку».",
            "Kullanıcı burada “Başvur” düğmesini görecek.",
        ),
        "Əlavə etmək istədiyiniz məlumat…": (
            "Anything you would like to add…",
            "Дополнительная информация…",
            "Eklemek istediğiniz bilgi…",
        ),
        "Ən yeni": ("Newest", "Сначала новые", "En yeni"),
        "Əvvəlki": ("Previous", "Назад", "Önceki"),
    },
    "announcements.manage": {
        "Arxiv": ("Archive", "Архив", "Arşiv"),
        "Arxivdəki elanı əvvəlcə bərpa edin.": (
            "Restore the archived announcement first.",
            "Сначала восстановите объявление из архива.",
            "Arşivdeki duyuruyu önce geri yükleyin.",
        ),
        "Arxivdən qaytar": ("Restore from archive", "Вернуть из архива", "Arşivden geri al"),
        "Arxivlə": ("Archive", "В архив", "Arşivle"),
        "Auditoriya": ("Audience", "Аудитория", "Hedef kitle"),
        "Axtar…": ("Search…", "Поиск…", "Ara…"),
        "Başlıq": ("Title", "Заголовок", "Başlık"),
        "Başlıq ən azı 3 simvol olmalıdır.": (
            "The title must be at least 3 characters.",
            "Заголовок должен содержать не менее 3 символов.",
            "Başlık en az 3 karakter olmalıdır.",
        ),
        "Bir elana ən çox %(n)s sənəd əlavə etmək olar.": (
            "At most %(n)s documents can be attached to an announcement.",
            "К объявлению можно прикрепить не более %(n)s документов.",
            "Bir duyuruya en fazla %(n)s belge eklenebilir.",
        ),
        "Bitmə vaxtı dərc vaxtından sonra olmalıdır.": (
            "The end time must be after the publish time.",
            "Время окончания должно быть позже времени публикации.",
            "Bitiş zamanı yayın zamanından sonra olmalıdır.",
        ),
        "Bitmə vaxtı keçib — əvvəlcə tarixi dəyişin.": (
            "The end time has passed — change the date first.",
            "Время окончания прошло — сначала измените дату.",
            "Bitiş zamanı geçti — önce tarihi değiştirin.",
        ),
        "Boş — dərc düyməsinə basılan an.": (
            "Empty — the moment you press publish.",
            "Пусто — в момент нажатия «Опубликовать».",
            "Boş — yayınla düğmesine basıldığı an.",
        ),
        "Boş — müddətsiz. Bitəndən sonra «Müddəti bitmiş» arxivində qalır.": (
            "Empty — no end. After it ends it stays in the “Expired” archive.",
            "Пусто — бессрочно. После окончания остаётся в архиве «Истёкшие».",
            "Boş — süresiz. Bittikten sonra “Süresi dolmuş” arşivinde kalır.",
        ),
        "Bu bölmələr sizin əhatənizdən kənardadır: %(names)s": (
            "These units are outside your scope: %(names)s",
            "Эти подразделения вне вашей области: %(names)s",
            "Bu birimler yetki alanınızın dışında: %(names)s",
        ),
        "Bu müraciət növü seçilmiş auditoriyanın hamısına açıq deyil.": (
            "This application type is not open to the whole selected audience.",
            "Этот тип заявки доступен не всей выбранной аудитории.",
            "Bu başvuru türü seçilen kitlenin tamamına açık değil.",
        ),
        "Bölmə axtar": ("Search units", "Поиск подразделения", "Birim ara"),
        "Bölmə axtar…": ("Search units…", "Поиск подразделения…", "Birim ara…"),
        "Bölmə seçimi yanlışdır.": (
            "Invalid unit selection.",
            "Неверный выбор подразделения.",
            "Birim seçimi geçersiz.",
        ),
        "Bölmələr (fakültə, kafedra, ixtisas, qrup)": (
            "Units (faculty, department, specialty, group)",
            "Подразделения (факультет, кафедра, специальность, группа)",
            "Birimler (fakülte, bölüm, program, grup)",
        ),
        "Bütün təşkilata elan yalnız təşkilat səviyyəli səlahiyyətlə verilir — öz bölmənizi seçin.": (
            "Organization-wide announcements require organization-level permission — select your unit.",
            "Объявление для всей организации требует полномочий уровня организации — выберите своё подразделение.",
            "Tüm kuruma duyuru yalnızca kurum düzeyinde yetkiyle yapılır — kendi biriminizi seçin.",
        ),
        "Bütün təşkilata və ya seçilmiş fakültə, kafedra, qrup üçün elan yaradın. Popup elan hər istifadəçiyə yalnız bir dəfə göstərilir.": (
            "Create announcements for the whole organization or for selected faculties, departments and groups. A popup announcement is shown to each user only once.",
            "Создавайте объявления для всей организации или для выбранных факультетов, кафедр, групп. Всплывающее объявление показывается каждому пользователю только один раз.",
            "Tüm kurum veya seçilen fakülte, bölüm, grup için duyuru oluşturun. Açılır duyuru her kullanıcıya yalnızca bir kez gösterilir.",
        ),
        "Düymənin mətni (könüllü)": (
            "Button text (optional)",
            "Текст кнопки (необязательно)",
            "Düğme metni (isteğe bağlı)",
        ),
        "Düz mətn: boş sətir — yeni abzas; keçidlər avtomatik link olur.": (
            "Plain text: a blank line starts a new paragraph; links become clickable automatically.",
            "Обычный текст: пустая строка — новый абзац; ссылки становятся активными автоматически.",
            "Düz metin: boş satır yeni paragraf; bağlantılar otomatik tıklanabilir olur.",
        ),
        "Dərc et": ("Publish", "Опубликовать", "Yayınla"),
        "Dərc vaxtı": ("Publish time", "Время публикации", "Yayın zamanı"),
        "Dərc: %(day)s": ("Published: %(day)s", "Опубликовано: %(day)s", "Yayın: %(day)s"),
        "Dərcdən çıxar": ("Unpublish", "Снять с публикации", "Yayından kaldır"),
        "Elan arxivdən qaytarıldı (qaralama).": (
            "The announcement was restored (draft).",
            "Объявление возвращено из архива (черновик).",
            "Duyuru arşivden geri alındı (taslak).",
        ),
        "Elan arxivləndi.": ("The announcement was archived.", "Объявление отправлено в архив.", "Duyuru arşivlendi."),
        "Elan dərc olundu.": ("The announcement was published.", "Объявление опубликовано.", "Duyuru yayınlandı."),
        "Elan qaralamaya qaytarıldı.": (
            "The announcement was returned to draft.",
            "Объявление возвращено в черновики.",
            "Duyuru taslağa döndürüldü.",
        ),
        "Elan yadda saxlanıldı.": ("The announcement was saved.", "Объявление сохранено.", "Duyuru kaydedildi."),
        "Elan yoxdur": ("No announcements", "Нет объявлений", "Duyuru yok"),
        "Elanlarım": ("My announcements", "Мои объявления", "Duyurularım"),
        "Elanların idarəsi": ("Announcement management", "Управление объявлениями", "Duyuru yönetimi"),
        "Elanı redaktə et": ("Edit announcement", "Редактировать объявление", "Duyuruyu düzenle"),
        "Fayl əlavə et": ("Add files", "Добавить файлы", "Dosya ekle"),
        "Forma yadda saxlanmadı — aşağıdakıları düzəldin:": (
            "The form was not saved — fix the following:",
            "Форма не сохранена — исправьте следующее:",
            "Form kaydedilmedi — aşağıdakileri düzeltin:",
        ),
        "Girişdə popup kimi göstər": (
            "Show as a popup on login",
            "Показать всплывающим окном при входе",
            "Girişte açılır pencere olarak göster",
        ),
        "Görünmə bitir": ("Visible until", "Показывать до", "Görünürlük bitişi"),
        "Göstər": ("Show", "Показать", "Göster"),
        "Hara göndərilsin (şöbə)": ("Send to (office)", "Куда отправить (отдел)", "Nereye gönderilsin (birim)"),
        "Heç nə seçilməsə — bütün təşkilat. Seçilmiş bölmə alt bölmələri ilə birlikdə hədəflənir (məs. fakültə → onun bütün qrupları).": (
            "If nothing is selected — the whole organization. A selected unit includes its sub-units (e.g. faculty → all its groups).",
            "Если ничего не выбрано — вся организация. Выбранное подразделение включает дочерние (например, факультет → все его группы).",
            "Hiçbir şey seçilmezse — tüm kurum. Seçilen birim alt birimleriyle birlikte hedeflenir (ör. fakülte → tüm grupları).",
        ),
        "Hədəf auditoriya": ("Target audience", "Целевая аудитория", "Hedef kitle"),
        "Keçid (https://… və ya /daxili/yol)": (
            "Link (https://… or /internal/path)",
            "Ссылка (https://… или /внутренний/путь)",
            "Bağlantı (https://… veya /iç/yol)",
        ),
        "Keçid https:// ilə başlamalı və ya saytın daxili yolu (/…) olmalıdır.": (
            "The link must start with https:// or be an internal site path (/…).",
            "Ссылка должна начинаться с https:// или быть внутренним путём сайта (/…).",
            "Bağlantı https:// ile başlamalı veya sitenin iç yolu (/…) olmalıdır.",
        ),
        "Kimə göstərilsin": ("Who should see it", "Кому показывать", "Kime gösterilsin"),
        "Müraciət": ("Applied", "Заявки", "Başvuru"),
        "Müraciət edib": ("Applied", "Подали заявку", "Başvurdu"),
        "Müraciət növü": ("Application type", "Тип заявки", "Başvuru türü"),
        "Müraciət növünü seçin.": ("Select the application type.", "Выберите тип заявки.", "Başvuru türünü seçin."),
        "Müraciət rejimi": ("Application mode", "Режим заявки", "Başvuru modu"),
        "Mətn": ("Text", "Текст", "Metin"),
        "Məzmun": ("Content", "Содержание", "İçerik"),
        "Naməlum əməliyyat.": ("Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
        "Naviqasiya": ("Navigation", "Навигация", "Gezinme"),
        "Növ seçilmiş auditoriyanın hamısına açıq olmalıdır (məs. tələbə növü).": (
            "The type must be open to the whole selected audience (e.g. a student type).",
            "Тип должен быть доступен всей выбранной аудитории (например, студенческий тип).",
            "Tür, seçilen kitlenin tamamına açık olmalıdır (ör. öğrenci türü).",
        ),
        "Növün öz marşrutu ilə": ("Using the type's own routing", "По маршруту типа", "Türün kendi yönlendirmesiyle"),
        "Oxuyub": ("Read", "Прочитали", "Okudu"),
        "PDF, şəkil, Word/Excel/PowerPoint · hər biri 10 MB-a qədər · ən çox 5 fayl.": (
            "PDF, images, Word/Excel/PowerPoint · up to 10 MB each · at most 5 files.",
            "PDF, изображения, Word/Excel/PowerPoint · до 10 МБ каждый · не более 5 файлов.",
            "PDF, görsel, Word/Excel/PowerPoint · her biri 10 MB'a kadar · en fazla 5 dosya.",
        ),
        "Planlaşdırılıb": ("Scheduled", "Запланировано", "Planlandı"),
        "Popup": ("Pop-up", "Всплывающее", "Açılır pencere"),
        "Popup görüb": ("Saw popup", "Видели окно", "Açılır pencereyi gördü"),
        "Qalan gün göstərilir; keçəndən sonra «Müraciət et» bağlanır.": (
            "Days left are shown; after it passes, “Apply” is closed.",
            "Показывается число оставшихся дней; после срока кнопка «Подать заявку» закрывается.",
            "Kalan gün gösterilir; geçtikten sonra “Başvur” kapanır.",
        ),
        "Qaralama": ("Draft", "Черновик", "Taslak"),
        "Qaralama birdəfəlik silinsin?": (
            "Delete the draft permanently?",
            "Удалить черновик навсегда?",
            "Taslak kalıcı olarak silinsin mi?",
        ),
        "Qaralama silindi.": ("The draft was deleted.", "Черновик удалён.", "Taslak silindi."),
        "Qısa xülasə": ("Short summary", "Краткое описание", "Kısa özet"),
        "Redaktəyə qayıt": ("Back to editing", "Вернуться к редактированию", "Düzenlemeye dön"),
        "Saxla və dərc et": ("Save and publish", "Сохранить и опубликовать", "Kaydet ve yayınla"),
        "Seçilib": ("Selected", "Выбрано", "Seçildi"),
        "Seçilmiş bölmələrdən biri tapılmadı.": (
            "One of the selected units was not found.",
            "Одно из выбранных подразделений не найдено.",
            "Seçilen birimlerden biri bulunamadı.",
        ),
        "Seçilmiş şöbə tapılmadı.": (
            "The selected office was not found.",
            "Выбранный отдел не найден.",
            "Seçilen birim bulunamadı.",
        ),
        "Seçiləcək bölmə yoxdur.": (
            "There are no units to select.",
            "Нет подразделений для выбора.",
            "Seçilecek birim yok.",
        ),
        "Sil": ("Delete", "Удалить", "Kaldır"),
        "Siyahıda və popup-da göstərilir (300 simvola qədər).": (
            "Shown in the list and the popup (up to 300 characters).",
            "Показывается в списке и во всплывающем окне (до 300 символов).",
            "Listede ve açılır pencerede gösterilir (300 karaktere kadar).",
        ),
        "Siyahının başına sanc": ("Pin to the top of the list", "Закрепить вверху списка", "Listenin başına sabitle"),
        "Son tarix (nə vaxta qədər)": (
            "Deadline (until when)",
            "Крайний срок (до какого времени)",
            "Son tarih (ne zamana kadar)",
        ),
        "Son tarix dərc vaxtından sonra olmalıdır.": (
            "The deadline must be after the publish time.",
            "Крайний срок должен быть позже времени публикации.",
            "Son tarih yayın zamanından sonra olmalıdır.",
        ),
        "Statistika": ("Statistics", "Статистика", "İstatistik"),
        "Səlahiyyət yoxdur.": ("Permission denied.", "Нет полномочий.", "Yetki yok."),
        "Sənəd silindi.": ("The document was deleted.", "Документ удалён.", "Belge silindi."),
        "Uyğun nəticə yoxdur": ("No matching results", "Нет совпадений", "Eşleşen sonuç yok"),
        "Vaxt və son tarix": ("Timing and deadline", "Сроки", "Zaman ve son tarih"),
        "Yadda saxla": ("Save", "Сохранить", "Kaydet"),
        "Yalnız heç kimin görmədiyi qaralama silinə bilər; digərlərini arxivləyin.": (
            "Only a draft nobody has seen can be deleted; archive the others.",
            "Удалить можно только черновик, который никто не видел; остальные отправьте в архив.",
            "Yalnızca kimsenin görmediği taslak silinebilir; diğerlerini arşivleyin.",
        ),
        "Yalnız öz bölmənizə (və onun alt bölmələrinə) elan verə bilərsiniz. Popup elan hər istifadəçiyə yalnız bir dəfə göstərilir.": (
            "You can only announce to your own unit (and its sub-units). A popup announcement is shown to each user only once.",
            "Вы можете публиковать объявления только для своего подразделения (и дочерних). Всплывающее объявление показывается каждому пользователю один раз.",
            "Yalnızca kendi biriminize (ve alt birimlerine) duyuru yapabilirsiniz. Açılır duyuru her kullanıcıya yalnızca bir kez gösterilir.",
        ),
        "Yeni elan": ("New announcement", "Новое объявление", "Yeni duyuru"),
        "bitir: %(day)s": ("ends: %(day)s", "до: %(day)s", "bitiş: %(day)s"),
        "hər istifadəçiyə yalnız BİR dəfə; bağlayandan sonra bir daha çıxmır. İmtahan səhifələrində göstərilmir.": (
            "only ONCE per user; after closing it never appears again. Not shown on exam pages.",
            "каждому пользователю только ОДИН раз; после закрытия больше не появляется. Не показывается на страницах экзаменов.",
            "her kullanıcıya yalnızca BİR kez; kapatıldıktan sonra bir daha çıkmaz. Sınav sayfalarında gösterilmez.",
        ),
        "son tarix: %(day)s": ("deadline: %(day)s", "срок: %(day)s", "son tarih: %(day)s"),
        "«%(name)s» faylını sil": ("Delete file “%(name)s”", "Удалить файл «%(name)s»", "“%(name)s” dosyasını sil"),
        "«Müraciət et» düyməsi": ("“Apply” button", "Кнопка «Подать заявку»", "“Başvur” düğmesi"),
        "«Yeni elan» düyməsi ilə ilk elanı yaradın.": (
            "Create the first announcement with “New announcement”.",
            "Создайте первое объявление кнопкой «Новое объявление».",
            "İlk duyuruyu “Yeni duyuru” düğmesiyle oluşturun.",
        ),
        "Önizləmə": ("Preview", "Предпросмотр", "Önizleme"),
        "Önizləmə — istifadəçi belə görəcək": (
            "Preview — this is what users will see",
            "Предпросмотр — так увидит пользователь",
            "Önizleme — kullanıcı böyle görecek",
        ),
        "Ən azı bir auditoriya seçin.": (
            "Select at least one audience.",
            "Выберите хотя бы одну аудиторию.",
            "En az bir hedef kitle seçin.",
        ),
        "Ən azı bir bölmə seçin — yalnız öz əhatənizdəki bölmələr göstərilir.": (
            "Select at least one unit — only units within your scope are listed.",
            "Выберите хотя бы одно подразделение — показаны только подразделения вашей области.",
            "En az bir birim seçin — yalnızca yetki alanınızdaki birimler gösterilir.",
        ),
        "Ən çox %(n)s bölmə seçmək olar.": (
            "At most %(n)s units can be selected.",
            "Можно выбрать не более %(n)s подразделений.",
            "En fazla %(n)s birim seçilebilir.",
        ),
        "— seçin —": ("— select —", "— выберите —", "— seçiniz —"),
        # 2026-10-07: istənilən elanın silinməsi (qəbzsiz qaralama → birdəfəlik, qalanı yumşaq) və bərpa.
        "Alıcılar onu görmür (siyahı, popup, sayğac, müraciət). Statistika, sənədlər və yaradılmış müraciətlər saxlanılır. Bərpa etsəniz elan qaralama kimi qayıdır.": (
            "Recipients no longer see it (list, popup, counter, applications). Statistics, documents and submitted applications are kept. If you restore it, it returns as a draft.",
            "Получатели его больше не видят (список, всплывающее окно, счётчик, заявки). Статистика, документы и поданные заявки сохраняются. После восстановления объявление вернётся как черновик.",
            "Alıcılar artık görmüyor (liste, açılır pencere, sayaç, başvuru). İstatistikler, belgeler ve oluşturulan başvurular korunur. Geri yüklerseniz duyuru taslak olarak döner.",
        ),
        "Bu elan silinib": (
            "This announcement has been deleted",
            "Это объявление удалено",
            "Bu duyuru silindi",
        ),
        "Bərpa et": ("Restore", "Восстановить", "Geri yükle"),
        "Elan bərpa olundu (qaralama).": (
            "The announcement was restored (draft).",
            "Объявление восстановлено (черновик).",
            "Duyuru geri yüklendi (taslak).",
        ),
        "Elan silindi — alıcılar onu artıq görmür. «Silinmişlər» filtrindən bərpa edə bilərsiniz.": (
            "The announcement was deleted — recipients no longer see it. You can restore it from the “Deleted” filter.",
            "Объявление удалено — получатели его больше не видят. Его можно восстановить из фильтра «Удалённые».",
            "Duyuru silindi — alıcılar artık görmüyor. “Silinenler” filtresinden geri yükleyebilirsiniz.",
        ),
        "Elan silinib — əvvəlcə onu bərpa edin.": (
            "The announcement was deleted — restore it first.",
            "Объявление удалено — сначала восстановите его.",
            "Duyuru silindi — önce geri yükleyin.",
        ),
        "Elan silinməyib.": (
            "The announcement is not deleted.",
            "Объявление не удалено.",
            "Duyuru silinmemiş.",
        ),
        "Elan silinsin? O, bütün alıcılar üçün dərhal yox olacaq (siyahı, popup, sayğac, müraciət). Statistika, sənədlər və yaradılmış müraciətlər saxlanılır; «Silinmişlər» filtrindən bərpa edə bilərsiniz.": (
            "Delete the announcement? It will disappear for all recipients immediately (list, popup, counter, applications). Statistics, documents and submitted applications are kept; you can restore it from the “Deleted” filter.",
            "Удалить объявление? Оно сразу исчезнет у всех получателей (список, всплывающее окно, счётчик, заявки). Статистика, документы и поданные заявки сохранятся; восстановить можно из фильтра «Удалённые».",
            "Duyuru silinsin mi? Tüm alıcılar için hemen kaybolacak (liste, açılır pencere, sayaç, başvuru). İstatistikler, belgeler ve oluşturulan başvurular korunur; “Silinenler” filtresinden geri yükleyebilirsiniz.",
        ),
        "Qaralama birdəfəlik silinsin? Onu heç kim görməyib — bu əməliyyat geri qaytarılmır.": (
            "Delete the draft permanently? Nobody has seen it — this cannot be undone.",
            "Удалить черновик навсегда? Его никто не видел — это действие нельзя отменить.",
            "Taslak kalıcı olarak silinsin mi? Kimse görmedi — bu işlem geri alınamaz.",
        ),
        "Qaralamanı heç kim görməyib — «Sil» onu birdəfəlik silir.": (
            "Nobody has seen this draft — “Delete” removes it permanently.",
            "Этот черновик никто не видел — «Удалить» удалит его навсегда.",
            "Bu taslağı kimse görmedi — “Kaldır” onu kalıcı olarak siler.",
        ),
        "Silinib": ("Deleted", "Удалено", "Silindi"),
        "Silinib: %(day)s": ("Deleted: %(day)s", "Удалено: %(day)s", "Silindi: %(day)s"),
        "Silinmiş elan yoxdur": ("No deleted announcements", "Нет удалённых объявлений", "Silinmiş duyuru yok"),
        "Silinmişlər": ("Deleted", "Удалённые", "Silinenler"),
        "Silinən elanlar burada görünür və bərpa oluna bilər.": (
            "Deleted announcements appear here and can be restored.",
            "Удалённые объявления отображаются здесь, их можно восстановить.",
            "Silinen duyurular burada görünür ve geri yüklenebilir.",
        ),
        "«Sil» elanı bütün alıcılardan gizlədir; statistika və müraciətlər saxlanılır, «Silinmişlər» filtrindən bərpa olunur.": (
            "“Delete” hides the announcement from all recipients; statistics and applications are kept, and it can be restored from the “Deleted” filter.",
            "«Удалить» скрывает объявление от всех получателей; статистика и заявки сохраняются, восстановить можно из фильтра «Удалённые».",
            "“Kaldır” duyuruyu tüm alıcılardan gizler; istatistikler ve başvurular korunur, “Silinenler” filtresinden geri yüklenebilir.",
        ),
    },
    "announcements.model": {
        "Adi": ("Normal", "Обычный", "Normal"),
        "Arxiv": ("Archived", "Архив", "Arşiv"),
        "Daxili müraciət (Müraciətlər modulu)": (
            "Internal application (Applications module)",
            "Внутренняя заявка (модуль «Заявки»)",
            "İç başvuru (Başvurular modülü)",
        ),
        "Dərc olunub": ("Published", "Опубликовано", "Yayınlandı"),
        "Fakültə": ("Faculty", "Факультет", "Fakülte"),
        "Kafedra": ("Department", "Кафедра", "Bölüm"),
        "Keçid (link)": ("Link", "Ссылка", "Bağlantı"),
        "Kritik": ("Critical", "Критический", "Çok önemli"),
        "Müraciət yoxdur": ("No application", "Без заявки", "Başvuru yok"),
        "Müəllimlər": ("Teachers", "Преподаватели", "Öğretmenler"),
        "Qaralama": ("Draft", "Черновик", "Taslak"),
        "Qrup": ("Group", "Группа", "Grup"),
        "Təcili": ("Urgent", "Срочно", "Acil"),
        "Tədbir": ("Event", "Мероприятие", "Etkinlik"),
        "Tədris": ("Academic", "Учебный процесс", "Eğitim"),
        "Tələbələr": ("Students", "Студенты", "Öğrenciler"),
        "Yüksək": ("High", "Высокий", "Yüksek"),
        "elan": ("announcement", "объявление", "duyuru"),
        "elan qəbzi": ("announcement receipt", "отметка объявления", "duyuru kaydı"),
        "elan qəbzləri": ("announcement receipts", "отметки объявлений", "duyuru kayıtları"),
        "elan sənədi": ("announcement document", "документ объявления", "duyuru belgesi"),
        "elan sənədləri": ("announcement documents", "документы объявлений", "duyuru belgeleri"),
        "elanlar": ("announcements", "объявления", "duyurular"),
        "Ümumi": ("General", "Общее", "Genel"),
        "İmtahan": ("Exam", "Экзамен", "Sınav"),
        "İxtisas": ("Specialty", "Специальность", "Program"),
        "Şöbə": ("Office", "Отдел", "Birim"),
        "Əməkdaşlar": ("Staff", "Сотрудники", "Personel"),
    },
    "announcements.popup": {
        "%(day)s tarixinədək": ("until %(day)s", "до %(day)s", "%(day)s tarihine kadar"),
        "Bağla": ("Close", "Закрыть", "Kapat"),
        "Dərc": ("Published", "Опубликовано", "Yayın"),
        "Növbəti elan": ("Next announcement", "Следующее объявление", "Sonraki duyuru"),
        "Qüvvədədir": ("Valid", "Действует", "Geçerli"),
        "Son tarix": ("Deadline", "Крайний срок", "Son tarih"),
        "Yeni elan": ("New announcement", "Новое объявление", "Yeni duyuru"),
        "Yeni elanlar": ("New announcements", "Новые объявления", "Yeni duyurular"),
        "Ətraflı bax": ("View details", "Подробнее", "Ayrıntılar"),
        "Əvvəlki elan": ("Previous announcement", "Предыдущее объявление", "Önceki duyuru"),
    },
    "organizations.permission.label": {
        "Elan yaratmaq və dərc etmək (öz əhatəsində)": (
            "Create and publish announcements (within own scope)",
            "Создавать и публиковать объявления (в своей области)",
            "Duyuru oluşturmak ve yayınlamak (kendi yetki alanında)",
        ),
    },
    "profile.sidebar": {
        "Elanlar": ("Announcements", "Объявления", "Duyurular"),
    },
}

# Cəm formaları: (kontekst, tək, cəm) → dil → [forma0, forma1, ...]
PLURALS = {
    ("announcements.cabinet", "%(n)s elan", "%(n)s elan"): {
        "az": ["%(n)s elan", "%(n)s elan"],
        "en": ["%(n)s announcement", "%(n)s announcements"],
        "ru": ["%(n)s объявление", "%(n)s объявления", "%(n)s объявлений", "%(n)s объявления"],
        "tr": ["%(n)s duyuru", "%(n)s duyuru"],
    },
    ("announcements.cabinet", "%(n)s gün qaldı", "%(n)s gün qaldı"): {
        "az": ["%(n)s gün qaldı", "%(n)s gün qaldı"],
        "en": ["%(n)s day left", "%(n)s days left"],
        "ru": ["остался %(n)s день", "осталось %(n)s дня", "осталось %(n)s дней", "осталось %(n)s дня"],
        "tr": ["%(n)s gün kaldı", "%(n)s gün kaldı"],
    },
}


#: Bu modulun öz kontekstləri — dəyər həmişə buradakı ilə sinxronlanır (identity düzəlişləri).
FORCE = {"announcements.cabinet", "announcements.manage", "announcements.model", "announcements.popup"}


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete or ctx in FORCE
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                changed += 1
    for (ctx, singular, plural), forms in PLURALS.items():
        entry = index.get((ctx, singular))
        values = {i: form for i, form in enumerate(forms[lang])}
        if entry is None:
            po.append(polib.POEntry(msgctxt=ctx, msgid=singular, msgid_plural=plural, msgstr_plural=values))
            added += 1
        elif entry.msgstr_plural != values:
            entry.msgstr_plural = values
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
