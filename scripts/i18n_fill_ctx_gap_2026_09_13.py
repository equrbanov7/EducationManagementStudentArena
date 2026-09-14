#!/usr/bin/env python3
"""EMSArena i18n — modul sabiti ilə verilən kontekstlərin kataloq boşluğu (2026-09-13).

Frontend auditi F4 (P1): Python-da ``pgettext(_CTX, "…")`` çağırışlarında
kontekst modul səviyyəli sabitdir (``_CTX = "audit.section"``). ``xgettext`` bu
formanı çıxara bilmir, ``scripts/i18n_source_scan.py`` də yalnız literal
konteksti qəbul edirdi → bu (ctx, msgid) cütləri heç bir kataloqa düşmədən
``check_i18n_catalogs.py`` qapısı «borc yoxdur» deyirdi. Nəticə: EN/RU/TR
interfeysində audit-log, groups-registry, org-members, struktur reyestri,
müəllim/tələbə intake, imtahan balı importu, semestr açılışı, sillabus və
jurnal bölmələri qarışıq dilli idi (RU UI-da «Səbəbsiz dəyişiklik», «Bütün
icraçılar», «KURATORSUZ» və s.).

Skaner eyni gün düzəldildi (``_module_str_constants`` — ad → string həlli),
ondan sonra ölçülən dəqiq boşluq: **django** domenində 564 cüt (33 kontekst).
Bu skript həmin cütləri dörd kataloqa əlavə edir (az = msgid, en/ru/tr lüğətdən).

Eyni auditin F7 (P2) bəndi: dərs yükü panelinin JS-i (``workload_distribution*.js``,
``workload_my.js``) AZ literalları ``gettext()``-ə keçirildi — onların
``djangojs`` domeni girişləri də buradadır (JS kataloqunda msgctxt yoxdur).

⚠️ ``makemessages`` İŞLƏDİLMİR (əl ilə yazılmış blokları silir). Skript yalnız
əlavə edir, mövcud girişə toxunmur və idempotentdir. TR qarşılıqları QƏSDƏN
AZ mənbədən fərqlidir — qapı ``msgstr == msgid`` sətrini tərcüməsiz sayır.

İstifadə:  python scripts/i18n_fill_ctx_gap_2026_09_13.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ENTRIES[domen][ctx][msgid] = {"en": …, "ru": …, "tr": …}; az = msgid.
ENTRIES = {"django": {}, "djangojs": {}}
D = ENTRIES["django"]

D["accounts.catalog"] = {
    "Kataloqu görmək səlahiyyətiniz yoxdur.": {
        "en": "You do not have permission to view the catalog.",
        "ru": "У вас нет прав на просмотр каталога.",
        "tr": "Kataloğu görüntüleme yetkiniz yok.",
    },
}

D["accounts.curriculum"] = {
    "%(n)d-ci semestr": {"en": "Semester %(n)d", "ru": "%(n)d-й семестр", "tr": "%(n)d. yarıyıl"},
    "AUDİTORİYA SAATI": {"en": "CLASSROOM HOURS", "ru": "АУДИТОРНЫЕ ЧАСЫ", "tr": "DERSLİK SAATİ"},
    "AÇIQ XƏBƏRDARLIQ": {"en": "OPEN WARNINGS", "ru": "ОТКРЫТЫЕ ПРЕДУПРЕЖДЕНИЯ", "tr": "AÇIK UYARI"},
    "CƏMİ KREDİT": {"en": "TOTAL CREDITS", "ru": "ВСЕГО КРЕДИТОВ", "tr": "TOPLAM KREDİ"},
    "Fənnin adı": {"en": "Subject name", "ru": "Название предмета", "tr": "Ders adı"},
    "Həftəlik": {"en": "Weekly", "ru": "В неделю", "tr": "Haftalık"},
    "PLAN SƏTRİ": {"en": "PLAN ROWS", "ru": "СТРОК ПЛАНА", "tr": "PLAN SATIRI"},
    "Plan": {"en": "Study plan", "ru": "План", "tr": "Öğretim planı"},
    "Plan sətri yoxdur": {"en": "No plan rows", "ru": "Нет строк плана", "tr": "Plan satırı yok"},
    "Plan sətri: %(count)d": {
        "en": "Plan rows: %(count)d",
        "ru": "Строк плана: %(count)d",
        "tr": "Plan satırı: %(count)d",
    },
    "Seçilmiş semestr üçün sətir qeydə alınmayıb — «Sətir əlavə et».": {
        "en": "No rows recorded for the selected semester — use “Add row”.",
        "ru": "Для выбранного семестра строк нет — «Добавить строку».",
        "tr": "Seçilen yarıyıl için satır kaydedilmemiş — «Satır ekle».",
    },
    "Təsdiqə göndərməni bloklayır": {
        "en": "Blocks submission for approval",
        "ru": "Блокирует отправку на утверждение",
        "tr": "Onaya göndermeyi engelliyor",
    },
    "Yoxlama": {"en": "Check", "ru": "Проверка", "tr": "Kontrol"},
    "ÜMUMİ SAAT": {"en": "TOTAL HOURS", "ru": "ВСЕГО ЧАСОВ", "tr": "TOPLAM SAAT"},
    "Şifr": {"en": "Code", "ru": "Шифр", "tr": "Kod"},
    "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
}

D["accounts.dashboard"] = {
    "Siyahı ilə əlavə et": {"en": "Add from a list", "ru": "Добавить списком", "tr": "Listeyle ekle"},
    "Tələbə əlavəsi (toplu)": {
        "en": "Student intake (bulk)",
        "ru": "Добавление студентов (массово)",
        "tr": "Öğrenci ekleme (toplu)",
    },
}

D["accounts.exam_score_entry"] = {
    "Bu bölmə yalnız imtahan balı daxil etmə səlahiyyəti olanlar üçündür.": {
        "en": "This section is only for users with exam score entry permission.",
        "ru": "Этот раздел доступен только пользователям с правом ввода экзаменационных баллов.",
        "tr": "Bu bölüm yalnızca sınav puanı girme yetkisi olanlar içindir.",
    },
    "Bu əməliyyat üçün icazəniz yoxdur.": {
        "en": "You do not have permission for this action.",
        "ru": "У вас нет прав на это действие.",
        "tr": "Bu işlem için yetkiniz yok.",
    },
    "Dəyişiklik yoxdur — heç bir bal yenilənmədi.": {
        "en": "No changes — no scores were updated.",
        "ru": "Изменений нет — ни один балл не обновлён.",
        "tr": "Değişiklik yok — hiçbir puan güncellenmedi.",
    },
    "Fənn açılışı tapılmadı.": {
        "en": "Course offering not found.",
        "ru": "Открытие предмета не найдено.",
        "tr": "Ders açılışı bulunamadı.",
    },
    "Naməlum əməliyyat.": {"en": "Unknown action.", "ru": "Неизвестное действие.", "tr": "Bilinmeyen işlem."},
    "Təşkilat konteksti tapılmadı.": {
        "en": "Organization context not found.",
        "ru": "Контекст организации не найден.",
        "tr": "Kurum bağlamı bulunamadı.",
    },
    "Yazılmış balı dəyişən sətirlər var — səbəb, qeyd və skan edilmiş sənəd tələb olunur.": {
        "en": "Some rows change an already recorded score — a reason, a note and a scanned document are required.",
        "ru": "Есть строки, меняющие уже записанный балл — требуются причина, примечание и отсканированный документ.",
        "tr": "Kayıtlı puanı değiştiren satırlar var — gerekçe, not ve taranmış belge gerekli.",
    },
    "bal yazıldı": {"en": "scores recorded", "ru": "баллов записано", "tr": "puan yazıldı"},
    "sətir dəyişmədi": {"en": "rows unchanged", "ru": "строк без изменений", "tr": "satır değişmedi"},
}

D["accounts.first_login"] = {
    "Etibarlı email ünvanı daxil edin.": {
        "en": "Enter a valid email address.",
        "ru": "Введите корректный адрес электронной почты.",
        "tr": "Geçerli bir e-posta adresi girin.",
    },
    "Kod göndərilə bilmədi. Zəhmət olmasa yenidən cəhd edin.": {
        "en": "The code could not be sent. Please try again.",
        "ru": "Не удалось отправить код. Пожалуйста, попробуйте ещё раз.",
        "tr": "Kod gönderilemedi. Lütfen tekrar deneyin.",
    },
    "Kod yanlış və ya vaxtı keçib. Yenidən cəhd edin.": {
        "en": "The code is invalid or has expired. Try again.",
        "ru": "Код неверный или просрочен. Попробуйте ещё раз.",
        "tr": "Kod hatalı veya süresi dolmuş. Tekrar deneyin.",
    },
    "Parollar uyğun gəlmir.": {
        "en": "Passwords do not match.",
        "ru": "Пароли не совпадают.",
        "tr": "Parolalar eşleşmiyor.",
    },
    "Parolunuz təyin olundu. Sistemə xoş gəlmisiniz!": {
        "en": "Your password has been set. Welcome to the system!",
        "ru": "Пароль установлен. Добро пожаловать в систему!",
        "tr": "Parolanız belirlendi. Sisteme hoş geldiniz!",
    },
    "Təsdiq kodu email ünvanınıza göndərildi.": {
        "en": "A verification code has been sent to your email address.",
        "ru": "Код подтверждения отправлен на вашу электронную почту.",
        "tr": "Doğrulama kodu e-posta adresinize gönderildi.",
    },
    "Çox sayda cəhd. Bir az sonra yenidən yoxlayın.": {
        "en": "Too many attempts. Try again a little later.",
        "ru": "Слишком много попыток. Попробуйте чуть позже.",
        "tr": "Çok fazla deneme. Biraz sonra tekrar deneyin.",
    },
    "Əvvəlcə email ünvanınızı təsdiqləyin.": {
        "en": "Verify your email address first.",
        "ru": "Сначала подтвердите адрес электронной почты.",
        "tr": "Önce e-posta adresinizi doğrulayın.",
    },
}

D["accounts.groups"] = {
    "Aktivlər": {"en": "Active", "ru": "Активные", "tr": "Aktif olanlar"},
    "Arxiv": {"en": "Archive", "ru": "Архив", "tr": "Arşiv"},
    "Arxivdəkilər": {"en": "Archived", "ru": "В архиве", "tr": "Arşivdekiler"},
    "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
    "Bu adda qrup artıq mövcuddur — qrup adı unikal olmalıdır.": {
        "en": "A group with this name already exists — the group name must be unique.",
        "ru": "Группа с таким названием уже существует — название группы должно быть уникальным.",
        "tr": "Bu adda bir grup zaten var — grup adı benzersiz olmalıdır.",
    },
    "Bu kodla qrup artıq mövcuddur — qrup kodu unikal olmalıdır.": {
        "en": "A group with this code already exists — the group code must be unique.",
        "ru": "Группа с таким кодом уже существует — код группы должен быть уникальным.",
        "tr": "Bu kodla bir grup zaten var — grup kodu benzersiz olmalıdır.",
    },
    "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
    "Hədəf qrup tapılmadı.": {
        "en": "Target group not found.",
        "ru": "Целевая группа не найдена.",
        "tr": "Hedef grup bulunamadı.",
    },
    "KURATORSUZ": {"en": "WITHOUT TUTOR", "ru": "БЕЗ КУРАТОРА", "tr": "DANIŞMANSIZ"},
    "Kafedra / fakültə": {"en": "Department / faculty", "ru": "Кафедра / факультет", "tr": "Bölüm / fakülte"},
    "Kod": {"en": "Code", "ru": "Код", "tr": "Grup kodu"},
    "Kurator": {"en": "Tutor", "ru": "Куратор", "tr": "Danışman"},
    "Nəticə: %(count)d qrup": {
        "en": "Result: %(count)d groups",
        "ru": "Результат: %(count)d групп",
        "tr": "Sonuç: %(count)d grup",
    },
    "PLAN YOXDUR": {"en": "NO PLAN", "ru": "НЕТ ПЛАНА", "tr": "PLAN YOK"},
    "QRUP": {"en": "GROUPS", "ru": "ГРУПП", "tr": "GRUP"},
    "Qrup adı və ya kodu": {"en": "Group name or code", "ru": "Название или код группы", "tr": "Grup adı veya kodu"},
    "Qrup reyestrindən tələbə əlavə edildi": {
        "en": "Student added from the groups registry",
        "ru": "Студент добавлен из реестра групп",
        "tr": "Öğrenci grup kayıt defterinden eklendi",
    },
    "Qrup tapılmadı": {"en": "No groups found", "ru": "Группы не найдены", "tr": "Grup bulunamadı"},
    "REYESTRDƏ CƏMİ": {"en": "TOTAL IN REGISTRY", "ru": "ВСЕГО В РЕЕСТРЕ", "tr": "KAYITTA TOPLAM"},
    "Seçilmiş tələbələr arasında qrupa əlavə edilə bilən (qrupsuz, qeydiyyatlı) tələbə yoxdur.": {
        "en": "None of the selected students can be added to the group (no group, enrolled).",
        "ru": "Среди выбранных студентов нет тех, кого можно добавить в группу (без группы, зачисленных).",
        "tr": "Seçilen öğrenciler arasında gruba eklenebilecek (grupsuz, kayıtlı) öğrenci yok.",
    },
    "Süzgəcləri dəyişin və ya yeni qrup əlavə edin.": {
        "en": "Change the filters or add a new group.",
        "ru": "Измените фильтры или добавьте новую группу.",
        "tr": "Filtreleri değiştirin veya yeni grup ekleyin.",
    },
    "Səbəb yazılmalıdır (ən azı 3 simvol).": {
        "en": "A reason is required (at least 3 characters).",
        "ru": "Нужно указать причину (не менее 3 символов).",
        "tr": "Gerekçe yazılmalıdır (en az 3 karakter).",
    },
    "TƏLƏBƏ (SƏHİFƏDƏ)": {"en": "STUDENTS (ON PAGE)", "ru": "СТУДЕНТОВ (НА СТРАНИЦЕ)", "tr": "ÖĞRENCİ (SAYFADA)"},
    "Tələbə onsuz da bu qrupdadır.": {
        "en": "The student is already in this group.",
        "ru": "Студент уже в этой группе.",
        "tr": "Öğrenci zaten bu grupta.",
    },
    "Tələbə qeydi tapılmadı.": {
        "en": "Student record not found.",
        "ru": "Запись студента не найдена.",
        "tr": "Öğrenci kaydı bulunamadı.",
    },
    "Tələbə seçilməyib.": {"en": "No student selected.", "ru": "Студент не выбран.", "tr": "Öğrenci seçilmedi."},
    "Tələbənin cari qrupu sizin əhatənizdə deyil.": {
        "en": "The student's current group is outside your scope.",
        "ru": "Текущая группа студента вне вашей зоны ответственности.",
        "tr": "Öğrencinin mevcut grubu kapsamınızda değil.",
    },
    "Vəziyyət": {"en": "Status", "ru": "Состояние", "tr": "Durum"},
    "arxiv qrup: %s": {"en": "archived group: %s", "ru": "архивная группа: %s", "tr": "arşiv grubu: %s"},
    "İxtisas": {"en": "Specialty", "ru": "Специальность", "tr": "Program"},
    "İxtisasın təsdiqlənmiş planı yoxdur": {
        "en": "The specialty has no approved plan",
        "ru": "У специальности нет утверждённого плана",
        "tr": "Programın onaylı planı yok",
    },
    "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
}

D["accounts.journal_close"] = {
    "Bu bölmə yalnız jurnal bağlama səlahiyyəti olanlar üçündür.": {
        "en": "This section is only for users with journal closing permission.",
        "ru": "Этот раздел доступен только пользователям с правом закрытия журнала.",
        "tr": "Bu bölüm yalnızca yoklama defteri kapatma yetkisi olanlar içindir.",
    },
    "Bu dövr və əhatə üçün artıq xəbərdarlıq var.": {
        "en": "A warning already exists for this period and scope.",
        "ru": "Для этого периода и области предупреждение уже существует.",
        "tr": "Bu dönem ve kapsam için zaten bir uyarı var.",
    },
    "Bu əməliyyat üçün icazəniz yoxdur.": {
        "en": "You do not have permission for this action.",
        "ru": "У вас нет прав на это действие.",
        "tr": "Bu işlem için yetkiniz yok.",
    },
    "Form məlumatları düzgün deyil.": {
        "en": "The form data is invalid.",
        "ru": "Данные формы некорректны.",
        "tr": "Form verileri geçersiz.",
    },
    "Naməlum əməliyyat.": {"en": "Unknown action.", "ru": "Неизвестное действие.", "tr": "Bilinmeyen işlem."},
    "Təşkilat konteksti tapılmadı.": {
        "en": "Organization context not found.",
        "ru": "Контекст организации не найден.",
        "tr": "Kurum bağlamı bulunamadı.",
    },
    "Xəbərdarlıq silindi.": {"en": "Warning deleted.", "ru": "Предупреждение удалено.", "tr": "Uyarı silindi."},
    "Xəbərdarlıq yadda saxlanıldı.": {
        "en": "Warning saved.",
        "ru": "Предупреждение сохранено.",
        "tr": "Uyarı kaydedildi.",
    },
    "Xəbərdarlığın statusu dəyişdirildi.": {
        "en": "Warning status changed.",
        "ru": "Статус предупреждения изменён.",
        "tr": "Uyarı durumu değiştirildi.",
    },
    "artıq bağlı idi": {"en": "was already closed", "ru": "уже был закрыт", "tr": "zaten kapalıydı"},
    "jurnal açıldı": {"en": "journal opened", "ru": "журнал открыт", "tr": "defter açıldı"},
    "jurnal bağlandı": {"en": "journal closed", "ru": "журнал закрыт", "tr": "defter kapatıldı"},
    "onsuz da açıq idi": {"en": "was already open", "ru": "уже был открыт", "tr": "zaten açıktı"},
}

D["accounts.lessons_log"] = {
    "Başlanğıc": {"en": "From", "ru": "Начало", "tr": "Başlangıç"},
    "Bütün illər": {"en": "All years", "ru": "Все годы", "tr": "Tüm yıllar"},
    "Bütün semestrlər": {"en": "All semesters", "ru": "Все семестры", "tr": "Tüm yarıyıllar"},
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "Son": {"en": "To", "ru": "Конец", "tr": "Bitiş"},
    "Tarix aralığı": {"en": "Date range", "ru": "Период", "tr": "Tarih aralığı"},
    "Tədris ili": {"en": "Academic year", "ru": "Учебный год", "tr": "Öğretim yılı"},
    "Təhsil forması": {"en": "Study mode", "ru": "Форма обучения", "tr": "Öğretim türü"},
    "Əhatənizdəki müəllimlər hansı dərsi, hansı qrupa, hansı mövzu ilə keçib. Jurnalı vaxtında doldurulmayan dərslər ayrıca işarələnir.": {
        "en": "Which lesson, for which group and on which topic the teachers in your scope taught. Lessons whose journal was not filled in on time are flagged separately.",
        "ru": "Какое занятие, для какой группы и по какой теме провели преподаватели в вашей зоне ответственности. Занятия, журнал которых не заполнен вовремя, отмечаются отдельно.",
        "tr": "Kapsamınızdaki öğretim elemanlarının hangi dersi, hangi gruba, hangi konuyla işlediği. Defteri zamanında doldurulmayan dersler ayrıca işaretlenir.",
    },
}

D["accounts.people.academic"] = {
    "Akademik məzuniyyət": {"en": "Academic leave", "ru": "Академический отпуск", "tr": "Akademik izin"},
    "Məzun olub": {"en": "Graduated", "ru": "Выпустился", "tr": "Mezun oldu"},
    "Təhsilini davam etdirir": {
        "en": "Continuing studies",
        "ru": "Продолжает обучение",
        "tr": "Öğrenimine devam ediyor",
    },
    "Xaric edilib": {"en": "Expelled", "ru": "Отчислен", "tr": "Kaydı silindi"},
}

D["accounts.people.page"] = {
    "100 bal, kredit-çəkili": {
        "en": "out of 100, credit-weighted",
        "ru": "из 100, взвешено по кредитам",
        "tr": "100 puan, kredi ağırlıklı",
    },
    "Açılış": {"en": "Offering", "ru": "Открытие", "tr": "Ders açılışı"},
    "Davamiyyətdən (q/b)": {
        "en": "From attendance (abs/pts)",
        "ru": "За посещаемость (проп./балл)",
        "tr": "Devamdan (dev/puan)",
    },
    "Dövr göstərilməyib": {"en": "Period not specified", "ru": "Период не указан", "tr": "Dönem belirtilmemiş"},
    "Kəsr": {"en": "Failed", "ru": "Незачёт", "tr": "Kalınan"},
    "Nəticə qeyd olunmayıb": {"en": "No result recorded", "ru": "Результат не записан", "tr": "Sonuç kaydedilmemiş"},
    "bütün dövrlər": {"en": "all periods", "ru": "все периоды", "tr": "tüm dönemler"},
    "cari il": {"en": "current year", "ru": "текущий год", "tr": "bu yıl"},
    "fərqli fənn": {"en": "distinct subjects", "ru": "разных предметов", "tr": "farklı ders"},
    "fərqli qrup": {"en": "distinct groups", "ru": "разных групп", "tr": "farklı grup"},
    "keçilmiş: %(n)s": {"en": "passed: %(n)s", "ru": "сдано: %(n)s", "tr": "geçilen: %(n)s"},
    "kəsilmiş fənn": {"en": "failed subjects", "ru": "несданных предметов", "tr": "kalınan ders"},
    "kəsr yoxdur": {"en": "no failures", "ru": "нет незачётов", "tr": "kalınan yok"},
    "qazanılıb / %(total)s qəti": {
        "en": "earned / %(total)s final",
        "ru": "получено / %(total)s итог",
        "tr": "kazanılan / %(total)s kesin",
    },
    "İmtahandan (25% təkrar)": {
        "en": "From exam (25% retake)",
        "ru": "За экзамен (25% пересдача)",
        "tr": "Sınavdan (%25 tekrar)",
    },
    "İş stajı": {"en": "Work experience", "ru": "Стаж работы", "tr": "İş deneyimi"},
}

D["accounts.semester"] = {
    "AÇILIŞ": {"en": "OFFERINGS", "ru": "ОТКРЫТИЙ", "tr": "DERS AÇILIŞI"},
    "Açılış yoxdur": {"en": "No offerings", "ru": "Открытий нет", "tr": "Açılış yok"},
    "Açılışın vəziyyəti": {"en": "Offering status", "ru": "Состояние открытия", "tr": "Açılış durumu"},
    "Dərsi aparan kafedra": {"en": "Teaching department", "ru": "Кафедра, ведущая занятия", "tr": "Dersi veren bölüm"},
    "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
    "Fənn kodu": {"en": "Subject code", "ru": "Код предмета", "tr": "Ders kodu"},
    "Gecikmə hesabatına düşür": {
        "en": "Included in the delay report",
        "ru": "Попадает в отчёт о задержках",
        "tr": "Gecikme raporuna giriyor",
    },
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "JURNALSIZ": {"en": "WITHOUT JOURNAL", "ru": "БЕЗ ЖУРНАЛА", "tr": "DEFTERSİZ"},
    "MÜƏLLİMSİZ": {"en": "WITHOUT TEACHER", "ru": "БЕЗ ПРЕПОДАВАТЕЛЯ", "tr": "ÖĞRETMENSİZ"},
    "Nəticə: %(count)d açılış": {
        "en": "Result: %(count)d offerings",
        "ru": "Результат: %(count)d открытий",
        "tr": "Sonuç: %(count)d açılış",
    },
    "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
    "SEMESTR SAATI": {"en": "SEMESTER HOURS", "ru": "ЧАСОВ В СЕМЕСТРЕ", "tr": "YARIYIL SAATİ"},
    "Semestr saatı": {"en": "Semester hours", "ru": "Часов в семестре", "tr": "Yarıyıl saati"},
    "SİLLABUSSUZ": {"en": "WITHOUT SYLLABUS", "ru": "БЕЗ СИЛЛАБУСА", "tr": "İZLENCESİZ"},
    "Tələbə sayı": {"en": "Students", "ru": "Студентов", "tr": "Öğrenci sayısı"},
    "Təsdiqlənmiş plandan açılış yaradın və ya süzgəci dəyişin.": {
        "en": "Create an offering from an approved plan or change the filter.",
        "ru": "Создайте открытие из утверждённого плана или измените фильтр.",
        "tr": "Onaylı plandan açılış oluşturun veya filtreyi değiştirin.",
    },
    "Təyin olunmuş müəllim": {
        "en": "Assigned teacher",
        "ru": "Назначенный преподаватель",
        "tr": "Atanan öğretim elemanı",
    },
    "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
}

D["audit.section"] = {
    "%(n)d hadisə · %(pct)s": {
        "en": "%(n)d events · %(pct)s",
        "ru": "%(n)d событий · %(pct)s",
        "tr": "%(n)d olay · %(pct)s",
    },
    "Anonim / sistem hadisələri": {
        "en": "Anonymous / system events",
        "ru": "Анонимные / системные события",
        "tr": "Anonim / sistem olayları",
    },
    "Audit jurnalı CSV ixracı: %(n)d sətir": {
        "en": "Audit log CSV export: %(n)d rows",
        "ru": "Экспорт журнала аудита в CSV: %(n)d строк",
        "tr": "Denetim günlüğü CSV dışa aktarımı: %(n)d satır",
    },
    "Audit jurnalına baxış üçün `audit.view` icazəsi və aktiv təşkilat konteksti lazımdır.": {
        "en": "Viewing the audit log requires the `audit.view` permission and an active organization context.",
        "ru": "Для просмотра журнала аудита нужны право `audit.view` и активный контекст организации.",
        "tr": "Denetim günlüğünü görüntülemek için `audit.view` izni ve etkin kurum bağlamı gerekir.",
    },
    "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
    "Axtarışı dəyişin və ya «Sıfırla» ilə son 30 günə qayıdın.": {
        "en": "Change the search or return to the last 30 days with “Reset”.",
        "ru": "Измените поиск или вернитесь к последним 30 дням через «Сбросить».",
        "tr": "Aramayı değiştirin veya «Sıfırla» ile son 30 güne dönün.",
    },
    "Başlanğıc": {"en": "From", "ru": "Начало", "tr": "Başlangıç"},
    "Bu gün": {"en": "Today", "ru": "Сегодня", "tr": "Bugün"},
    "Bütün icraçılar": {"en": "All actors", "ru": "Все исполнители", "tr": "Tüm uygulayıcılar"},
    "Bütün resurslar": {"en": "All resources", "ru": "Все ресурсы", "tr": "Tüm kaynaklar"},
    "Bütün təşkilatlar": {"en": "All organizations", "ru": "Все организации", "tr": "Tüm kurumlar"},
    "Bütün təşkilatların əməliyyat izi: kim, nə vaxt, nəyi dəyişib. Sətrə klik tam qeydi və əvvəl → sonra fərqini açır; cari filtr CSV kimi yüklənir.": {
        "en": "Activity trail of all organizations: who changed what and when. Click a row to open the full record and the before → after diff; the current filter can be downloaded as CSV.",
        "ru": "След действий всех организаций: кто, когда и что изменил. Клик по строке открывает полную запись и разницу «до → после»; текущий фильтр можно скачать как CSV.",
        "tr": "Tüm kurumların işlem izi: kim, ne zaman, neyi değiştirdi. Satıra tıklamak tam kaydı ve önce → sonra farkını açar; geçerli filtre CSV olarak indirilir.",
    },
    "Bütün vaxtlar": {"en": "All time", "ru": "За всё время", "tr": "Tüm zamanlar"},
    "Bütün əməliyyatlar": {"en": "All actions", "ru": "Все действия", "tr": "Tüm işlemler"},
    "Dövr": {"en": "Period", "ru": "Период", "tr": "Dönem"},
    "Dövrü genişləndirin («Bütün vaxtlar») və ya başqa aralıq seçin.": {
        "en": "Widen the period (“All time”) or choose another range.",
        "ru": "Расширьте период («За всё время») или выберите другой диапазон.",
        "tr": "Dönemi genişletin («Tüm zamanlar») veya başka bir aralık seçin.",
    },
    "Dəyişikliklər (JSON)": {"en": "Changes (JSON)", "ru": "Изменения (JSON)", "tr": "Değişiklikler (JSON)"},
    "Filtrə uyğun hadisə yoxdur": {
        "en": "No events match the filter",
        "ru": "Нет событий, соответствующих фильтру",
        "tr": "Filtreye uyan olay yok",
    },
    "Hadisə": {"en": "Event", "ru": "Событие", "tr": "Olay"},
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "IP": {"en": "IP address", "ru": "IP-адрес", "tr": "IP adresi"},
    "Nəticə: %(n)d hadisə": {"en": "Result: %(n)d events", "ru": "Результат: %(n)d событий", "tr": "Sonuç: %(n)d olay"},
    "Resurs ID": {"en": "Resource ID", "ru": "ID ресурса", "tr": "Kaynak kimliği"},
    "Rədd / yoxlama": {"en": "Denied / check", "ru": "Отказ / проверка", "tr": "Ret / kontrol"},
    "Rədd və yoxlama sorğuları": {
        "en": "Denied and check requests",
        "ru": "Отказы и запросы на проверку",
        "tr": "Ret ve kontrol istekleri",
    },
    "Seçilmiş aralıq": {"en": "Selected range", "ru": "Выбранный диапазон", "tr": "Seçilen aralık"},
    "Seçilmiş dövrdə hadisə yoxdur": {
        "en": "No events in the selected period",
        "ru": "В выбранном периоде событий нет",
        "tr": "Seçilen dönemde olay yok",
    },
    "Son": {"en": "To", "ru": "Конец", "tr": "Bitiş"},
    "Son 30 gün": {"en": "Last 30 days", "ru": "Последние 30 дней", "tr": "Geçtiğimiz 30 gün"},
    "Son 7 gün": {"en": "Last 7 days", "ru": "Последние 7 дней", "tr": "Geçtiğimiz 7 gün"},
    "Səbəbsiz dəyişiklik": {
        "en": "Change without reason",
        "ru": "Изменение без причины",
        "tr": "Gerekçesiz değişiklik",
    },
    "Səbəbsiz dəyişikliklər": {
        "en": "Changes without reason",
        "ru": "Изменения без причины",
        "tr": "Gerekçesiz değişiklikler",
    },
    "Səhifədə": {"en": "On page", "ru": "На странице", "tr": "Sayfada"},
    "Təşkilatınızın əməliyyat izi: kim, nə vaxt, nəyi dəyişib. Sətrə klik tam qeydi və əvvəl → sonra fərqini açır; cari filtr CSV kimi yüklənir.": {
        "en": "Activity trail of your organization: who changed what and when. Click a row to open the full record and the before → after diff; the current filter can be downloaded as CSV.",
        "ru": "След действий вашей организации: кто, когда и что изменил. Клик по строке открывает полную запись и разницу «до → после»; текущий фильтр можно скачать как CSV.",
        "tr": "Kurumunuzun işlem izi: kim, ne zaman, neyi değiştirdi. Satıra tıklamak tam kaydı ve önce → sonra farkını açar; geçerli filtre CSV olarak indirilir.",
    },
    "Yalnız": {"en": "Only", "ru": "Только", "tr": "Yalnızca"},
    "dəyişiklik / silinmə səbəbsiz": {
        "en": "changes / deletions without reason",
        "ru": "изменений / удалений без причины",
        "tr": "gerekçesiz değişiklik / silme",
    },
    "fərqli istifadəçi": {"en": "distinct users", "ru": "разных пользователей", "tr": "farklı kullanıcı"},
    "hadisə yoxdur": {"en": "no events", "ru": "событий нет", "tr": "olay yok"},
    "hamısında səbəb var": {"en": "all have a reason", "ru": "у всех указана причина", "tr": "hepsinde gerekçe var"},
    "rədd və yoxlama sorğusu": {
        "en": "denied and check requests",
        "ru": "отказов и запросов на проверку",
        "tr": "ret ve kontrol isteği",
    },
    "uğursuz hadisə yoxdur": {"en": "no failed events", "ru": "неудачных событий нет", "tr": "başarısız olay yok"},
    "İcraçı (ad)": {"en": "Actor (name)", "ru": "Исполнитель (имя)", "tr": "Uygulayıcı (ad)"},
    "İcraçı (istifadəçi adı)": {
        "en": "Actor (username)",
        "ru": "Исполнитель (имя пользователя)",
        "tr": "Uygulayıcı (kullanıcı adı)",
    },
    "İcraçı, resurs, səbəb və ya sorğu ID": {
        "en": "Actor, resource, reason or request ID",
        "ru": "Исполнитель, ресурс, причина или ID запроса",
        "tr": "Uygulayıcı, kaynak, gerekçe veya istek kimliği",
    },
    "Əməliyyat": {"en": "Action", "ru": "Действие", "tr": "İşlem"},
    "Ən çox əməliyyat": {"en": "Most actions", "ru": "Больше всего действий", "tr": "En çok işlem"},
}

D["organizations.members"] = {
    "Ad (A→Z)": {"en": "Name (A→Z)", "ru": "Имя (А→Я)", "tr": "Ada göre (A→Z)"},
    "Ad (Z→A)": {"en": "Name (Z→A)", "ru": "Имя (Я→А)", "tr": "Ada göre (Z→A)"},
    "Ad, e-poçt, istifadəçi adı və ya vəzifə": {
        "en": "Name, email, username or position",
        "ru": "Имя, e-mail, имя пользователя или должность",
        "tr": "Ad, e-posta, kullanıcı adı veya unvan",
    },
    "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
    "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.": {
        "en": "Change the search or return to the full list with “Reset”.",
        "ru": "Измените поиск или вернитесь к полному списку через «Сбросить».",
        "tr": "Aramayı değiştirin veya «Sıfırla» ile tam listeye dönün.",
    },
    "Bölmə": {"en": "Unit", "ru": "Подразделение", "tr": "Birim"},
    "Bölməsiz": {"en": "No unit", "ru": "Без подразделения", "tr": "Birimsiz"},
    "Bütün bölmələr": {"en": "All units", "ru": "Все подразделения", "tr": "Tüm birimler"},
    "Bütün rollar": {"en": "All roles", "ru": "Все роли", "tr": "Tüm roller"},
    "Dekan": {"en": "Dean", "ru": "Декан", "tr": "Fakülte dekanı"},
    "Dekanlıq rəhbəri": {"en": "Dean's office head", "ru": "Руководитель деканата", "tr": "Dekanlık sorumlusu"},
    "Filtrə uyğun üzv yoxdur": {
        "en": "No members match the filter",
        "ru": "Нет участников, соответствующих фильтру",
        "tr": "Filtreye uyan üye yok",
    },
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "Heyət": {"en": "Staff", "ru": "Сотрудники", "tr": "Personel"},
    "Hələ üzv yoxdur": {"en": "No members yet", "ru": "Участников пока нет", "tr": "Henüz üye yok"},
    "Kafedra müdiri": {"en": "Head of department", "ru": "Заведующий кафедрой", "tr": "Bölüm başkanı"},
    "Kurator": {"en": "Tutor", "ru": "Куратор", "tr": "Danışman"},
    "Laboratoriya müdiri": {"en": "Laboratory head", "ru": "Заведующий лабораторией", "tr": "Laboratuvar sorumlusu"},
    "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretim elemanı"},
    "Müəllimlər": {"en": "Teachers", "ru": "Преподаватели", "tr": "Öğretim elemanları"},
    "Mərkəz rəhbəri": {"en": "Center head", "ru": "Руководитель центра", "tr": "Merkez sorumlusu"},
    "Növ": {"en": "Type", "ru": "Тип", "tr": "Tür"},
    "Nəticə: %(n)d üzvlük": {
        "en": "Result: %(n)d memberships",
        "ru": "Результат: %(n)d членств",
        "tr": "Sonuç: %(n)d üyelik",
    },
    "Prorektor": {"en": "Vice-rector", "ru": "Проректор", "tr": "Rektör yardımcısı"},
    "Rektor": {"en": "Rector", "ru": "Ректор", "tr": "Rektör"},
    "Rol": {"en": "Role", "ru": "Роль", "tr": "Üye rolü"},
    "Rol (yuxarıdan aşağı)": {"en": "Role (top to bottom)", "ru": "Роль (сверху вниз)", "tr": "Rol (yukarıdan aşağı)"},
    "Rolunuz bölməyə bağlıdır, amma bölmə (fakültə/kafedra) təyin edilməyib — Tədris şöbəsi və ya HR ilə əlaqə saxlayın.": {
        "en": "Your role is unit-bound, but no unit (faculty/department) is assigned — contact the Academic Office or HR.",
        "ru": "Ваша роль привязана к подразделению, но подразделение (факультет/кафедра) не назначено — обратитесь в учебный отдел или HR.",
        "tr": "Rolünüz birime bağlı, ancak birim (fakülte/bölüm) atanmamış — Öğrenci İşleri veya İK ile iletişime geçin.",
    },
    "Rəhbər": {"en": "Head", "ru": "Руководитель", "tr": "Yönetici"},
    "Rəhbərlik": {"en": "Leadership", "ru": "Руководство", "tr": "Yönetim"},
    "Rəhbərlər": {"en": "Heads", "ru": "Руководители", "tr": "Yöneticiler"},
    "Sıralama": {"en": "Sort", "ru": "Сортировка", "tr": "Sıralama ölçütü"},
    "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
    "Tələbələr": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler"},
    "Təşkilata üzv əlavə olunduqda burada görünəcək.": {
        "en": "Members will appear here once they are added to the organization.",
        "ru": "Участники появятся здесь после добавления в организацию.",
        "tr": "Kuruma üye eklendiğinde burada görünecek.",
    },
    "Təşkilatın üzvləri — rol, vəzifə və bölmə ilə. Rəhbər heyət (rektor, dekan, kafedra müdiri, koordinator) tac nişanı ilə seçilir; «Ətraflı» şəxsin bütün rollarını və rəhbərlik etdiyi bölmələri açır.": {
        "en": "Members of the organization — with role, position and unit. Leadership (rector, dean, head of department, coordinator) is marked with a crown; “Details” opens all roles of the person and the units they lead.",
        "ru": "Участники организации — с ролью, должностью и подразделением. Руководство (ректор, декан, заведующий кафедрой, координатор) отмечено короной; «Подробнее» показывает все роли человека и возглавляемые им подразделения.",
        "tr": "Kurumun üyeleri — rol, unvan ve birimle. Yönetim (rektör, dekan, bölüm başkanı, koordinatör) taç işaretiyle ayrılır; «Ayrıntılar» kişinin tüm rollerini ve yönettiği birimleri açar.",
    },
    "bölmə rolu var, bölmə təyin edilməyib": {
        "en": "has a unit role, no unit assigned",
        "ru": "есть роль подразделения, подразделение не назначено",
        "tr": "birim rolü var, birim atanmamış",
    },
    "dekan, müdir, koordinator, rəhbər rollar": {
        "en": "dean, head, coordinator, leadership roles",
        "ru": "декан, заведующий, координатор, руководящие роли",
        "tr": "dekan, başkan, koordinatör, yönetici rolleri",
    },
    "fərqli şəxs (bir neçə rolu olan bir dəfə sayılır)": {
        "en": "distinct people (someone with several roles is counted once)",
        "ru": "разных людей (имеющий несколько ролей считается один раз)",
        "tr": "farklı kişi (birden çok rolü olan bir kez sayılır)",
    },
    "hər bölmə rolunun bölməsi var": {
        "en": "every unit role has a unit",
        "ru": "у каждой роли подразделения есть подразделение",
        "tr": "her birim rolünün birimi var",
    },
    "tələbə olmayan rollar": {"en": "non-student roles", "ru": "роли, кроме студентов", "tr": "öğrenci olmayan roller"},
    "Üzv": {"en": "Member", "ru": "Участник", "tr": "Üye"},
    "Üzv siyahısına baxış səlahiyyətiniz yoxdur.": {
        "en": "You do not have permission to view the member list.",
        "ru": "У вас нет прав на просмотр списка участников.",
        "tr": "Üye listesini görüntüleme yetkiniz yok.",
    },
    "Üzv siyahısına baxış üçün `member.view` səlahiyyəti (bölmə əhatəsi ilə) və ya idarəetmə rolu lazımdır.": {
        "en": "Viewing the member list requires the `member.view` permission (with a unit scope) or a management role.",
        "ru": "Для просмотра списка участников нужно право `member.view` (с областью подразделения) или управленческая роль.",
        "tr": "Üye listesini görüntülemek için `member.view` yetkisi (birim kapsamıyla) veya yönetim rolü gerekir.",
    },
    "Üzv tapılmadı və ya əhatənizdə deyil.": {
        "en": "Member not found or outside your scope.",
        "ru": "Участник не найден или вне вашей зоны ответственности.",
        "tr": "Üye bulunamadı veya kapsamınızda değil.",
    },
    "İnstitut direktoru": {"en": "Institute director", "ru": "Директор института", "tr": "Enstitü müdürü"},
    "İxtisas rəhbəri": {"en": "Program head", "ru": "Руководитель специальности", "tr": "Program sorumlusu"},
    "Əhatəniz təyin edilməyib": {
        "en": "Your scope is not set",
        "ru": "Ваша зона ответственности не задана",
        "tr": "Kapsamınız tanımlanmamış",
    },
    "Ən köhnə": {"en": "Oldest", "ru": "Сначала старые", "tr": "En eski"},
    "Ən yeni": {"en": "Newest", "ru": "Сначала новые", "tr": "En yeni"},
}

D["organizations.permission.label"] = {
    "Kafedranın keçilmiş dərslərinə baxmaq": {
        "en": "View the department's taught lessons",
        "ru": "Просмотр проведённых занятий кафедры",
        "tr": "Bölümün işlenmiş derslerini görüntülemek",
    },
    "Sərbəst işi redaktə etmək": {
        "en": "Edit independent work",
        "ru": "Редактировать самостоятельную работу",
        "tr": "Bağımsız çalışmayı düzenlemek",
    },
    "Toplu hesab əlavəsi (siyahıdan tələbə/müəllim yaratmaq)": {
        "en": "Bulk account intake (create students/teachers from a list)",
        "ru": "Массовое добавление аккаунтов (создание студентов/преподавателей из списка)",
        "tr": "Toplu hesap ekleme (listeden öğrenci/öğretim elemanı oluşturmak)",
    },
}

D["organizations.registry"] = {
    "%(name)s artıq bu əhatədə «%(role)s» rolundadır.": {
        "en": "%(name)s already holds the “%(role)s” role in this scope.",
        "ru": "%(name)s уже имеет роль «%(role)s» в этой области.",
        "tr": "%(name)s bu kapsamda zaten «%(role)s» rolünde.",
    },
    "%(name)s «%(unit)s» fakültəsinə dekan təyin edildi.": {
        "en": "%(name)s was appointed dean of the “%(unit)s” faculty.",
        "ru": "%(name)s назначен(а) деканом факультета «%(unit)s».",
        "tr": "%(name)s, «%(unit)s» fakültesine dekan olarak atandı.",
    },
    "%(name)s «%(unit)s» kafedrasına müdir təyin edildi.": {
        "en": "%(name)s was appointed head of the “%(unit)s” department.",
        "ru": "%(name)s назначен(а) заведующим кафедрой «%(unit)s».",
        "tr": "%(name)s, «%(unit)s» bölümüne başkan olarak atandı.",
    },
    "%(name)s «%(unit)s» kafedrasına təyin edildi.": {
        "en": "%(name)s was assigned to the “%(unit)s” department.",
        "ru": "%(name)s назначен(а) на кафедру «%(unit)s».",
        "tr": "%(name)s, «%(unit)s» bölümüne atandı.",
    },
    "%(name)s «%(unit)s» üzrə %(role)s təyin edildi.": {
        "en": "%(name)s was assigned as %(role)s for “%(unit)s”.",
        "ru": "%(name)s назначен(а) как %(role)s по «%(unit)s».",
        "tr": "%(name)s, «%(unit)s» için %(role)s olarak atandı.",
    },
    "%(name)s üçün «%(role)s» təyinatı silindi.": {
        "en": "The “%(role)s” assignment for %(name)s was removed.",
        "ru": "Назначение «%(role)s» для %(name)s удалено.",
        "tr": "%(name)s için «%(role)s» ataması kaldırıldı.",
    },
    "Ad (A→Z)": {"en": "Name (A→Z)", "ru": "Название (А→Я)", "tr": "Ada göre (A→Z)"},
    "Ad (Z→A)": {"en": "Name (Z→A)", "ru": "Название (Я→А)", "tr": "Ada göre (Z→A)"},
    "Ad boş ola bilməz.": {
        "en": "The name cannot be empty.",
        "ru": "Название не может быть пустым.",
        "tr": "Ad boş olamaz.",
    },
    "Ad maksimum 255 simvol ola bilər.": {
        "en": "The name can be at most 255 characters.",
        "ru": "Название может содержать не более 255 символов.",
        "tr": "Ad en fazla 255 karakter olabilir.",
    },
    "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama"},
    "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.": {
        "en": "Change the search or return to the full list with “Reset”.",
        "ru": "Измените поиск или вернитесь к полному списку через «Сбросить».",
        "tr": "Aramayı değiştirin veya «Sıfırla» ile tam listeye dönün.",
    },
    "Açılış": {"en": "Offerings", "ru": "Открытия", "tr": "Ders açılışları"},
    "Açılış (cari il)": {"en": "Offerings (current year)", "ru": "Открытия (текущий год)", "tr": "Açılış (bu yıl)"},
    "Bu adda bölmə artıq var.": {
        "en": "A unit with this name already exists.",
        "ru": "Подразделение с таким названием уже существует.",
        "tr": "Bu adda bir birim zaten var.",
    },
    "Bu bölmə üçün belə rol təyin edilmir.": {
        "en": "This role cannot be assigned to this unit.",
        "ru": "Такая роль для этого подразделения не назначается.",
        "tr": "Bu birim için böyle bir rol atanmaz.",
    },
    "Bu bölmədə belə təyinat tapılmadı.": {
        "en": "No such assignment found in this unit.",
        "ru": "Такое назначение в этом подразделении не найдено.",
        "tr": "Bu birimde böyle bir atama bulunamadı.",
    },
    "Bu il aktiv": {"en": "Active this year", "ru": "Активны в этом году", "tr": "Bu yıl aktif"},
    "Bu kodda bölmə artıq var.": {
        "en": "A unit with this code already exists.",
        "ru": "Подразделение с таким кодом уже существует.",
        "tr": "Bu kodla bir birim zaten var.",
    },
    "Bu müəllim artıq həmin kafedradadır.": {
        "en": "This teacher is already in that department.",
        "ru": "Этот преподаватель уже на этой кафедре.",
        "tr": "Bu öğretim elemanı zaten o bölümde.",
    },
    "Bu müəllimin həmin kafedrada eyni rolla üzvlüyü artıq mövcuddur.": {
        "en": "This teacher already has a membership with the same role in that department.",
        "ru": "У этого преподавателя уже есть членство с той же ролью на этой кафедре.",
        "tr": "Bu öğretim elemanının o bölümde aynı rolle üyeliği zaten var.",
    },
    "Bölmə tapılmadı və ya əhatənizdə deyil.": {
        "en": "Unit not found or outside your scope.",
        "ru": "Подразделение не найдено или вне вашей зоны ответственности.",
        "tr": "Birim bulunamadı veya kapsamınızda değil.",
    },
    "Bölməni arxivləmək üçün `unit.delete` səlahiyyəti lazımdır.": {
        "en": "Archiving a unit requires the `unit.delete` permission.",
        "ru": "Для архивации подразделения нужно право `unit.delete`.",
        "tr": "Birimi arşivlemek için `unit.delete` yetkisi gerekir.",
    },
    "Bölməni redaktə etmək üçün `unit.edit` səlahiyyəti lazımdır.": {
        "en": "Editing a unit requires the `unit.edit` permission.",
        "ru": "Для редактирования подразделения нужно право `unit.edit`.",
        "tr": "Birimi düzenlemek için `unit.edit` yetkisi gerekir.",
    },
    "Bütün fakültələr": {"en": "All faculties", "ru": "Все факультеты", "tr": "Tüm fakülteler"},
    "Dekan müavini": {"en": "Vice-dean", "ru": "Заместитель декана", "tr": "Dekan yardımcısı"},
    "Dekanlıq": {"en": "Dean's office", "ru": "Деканат", "tr": "Dekanlık"},
    "Dekansız": {"en": "Without dean", "ru": "Без декана", "tr": "Dekanı olmayan"},
    "Fakültə adı və ya kodu": {
        "en": "Faculty name or code",
        "ru": "Название или код факультета",
        "tr": "Fakülte adı veya kodu",
    },
    "Fakültə yaradıldı.": {"en": "Faculty created.", "ru": "Факультет создан.", "tr": "Fakülte oluşturuldu."},
    "Fakültə yaratmaq üçün bütün təşkilat əhatəsi lazımdır.": {
        "en": "Creating a faculty requires organization-wide scope.",
        "ru": "Для создания факультета нужна область всей организации.",
        "tr": "Fakülte oluşturmak için tüm kurum kapsamı gerekir.",
    },
    "Fakültə yeniləndi.": {"en": "Faculty updated.", "ru": "Факультет обновлён.", "tr": "Fakülte güncellendi."},
    "Fakültələr, dekan və dekanlıq heyəti. Hər sətirdə «Heyət» çekmecəsi tam siyahını açır; dekan, müavin və koordinator təyinatı buradan aparılır.": {
        "en": "Faculties, deans and dean's office staff. The “Staff” drawer in each row opens the full list; dean, vice-dean and coordinator assignments are made here.",
        "ru": "Факультеты, деканы и сотрудники деканата. Панель «Сотрудники» в каждой строке открывает полный список; назначение декана, заместителя и координатора выполняется здесь.",
        "tr": "Fakülteler, dekanlar ve dekanlık personeli. Her satırdaki «Personel» çekmecesi tam listeyi açar; dekan, yardımcı ve koordinatör ataması buradan yapılır.",
    },
    "Filtrə uyğun fakültə yoxdur": {
        "en": "No faculties match the filter",
        "ru": "Нет факультетов, соответствующих фильтру",
        "tr": "Filtreye uyan fakülte yok",
    },
    "Filtrə uyğun kafedra yoxdur": {
        "en": "No departments match the filter",
        "ru": "Нет кафедр, соответствующих фильтру",
        "tr": "Filtreye uyan bölüm yok",
    },
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "Heyət təyinatı üçün `member.edit` səlahiyyəti lazımdır.": {
        "en": "Staff assignment requires the `member.edit` permission.",
        "ru": "Для назначения сотрудника нужно право `member.edit`.",
        "tr": "Personel ataması için `member.edit` yetkisi gerekir.",
    },
    "Heyət təyinatını silmək üçün `member.edit` səlahiyyəti lazımdır.": {
        "en": "Removing a staff assignment requires the `member.edit` permission.",
        "ru": "Для удаления назначения сотрудника нужно право `member.edit`.",
        "tr": "Personel atamasını kaldırmak için `member.edit` yetkisi gerekir.",
    },
    "Hələ fakültə yaradılmayıb": {
        "en": "No faculties created yet",
        "ru": "Факультеты ещё не созданы",
        "tr": "Henüz fakülte oluşturulmamış",
    },
    "Hələ kafedra yaradılmayıb": {
        "en": "No departments created yet",
        "ru": "Кафедры ещё не созданы",
        "tr": "Henüz bölüm oluşturulmamış",
    },
    "Kafedra adı və ya kodu": {
        "en": "Department name or code",
        "ru": "Название или код кафедры",
        "tr": "Bölüm adı veya kodu",
    },
    "Kafedra müdiri": {"en": "Head of department", "ru": "Заведующий кафедрой", "tr": "Bölüm başkanı"},
    "Kafedra tapılmadı və ya əhatənizdə deyil.": {
        "en": "Department not found or outside your scope.",
        "ru": "Кафедра не найдена или вне вашей зоны ответственности.",
        "tr": "Bölüm bulunamadı veya kapsamınızda değil.",
    },
    "Kafedra yaradıldı.": {"en": "Department created.", "ru": "Кафедра создана.", "tr": "Bölüm oluşturuldu."},
    "Kafedra yeniləndi.": {"en": "Department updated.", "ru": "Кафедра обновлена.", "tr": "Bölüm güncellendi."},
    "Kafedra üçün fakültə seçilməlidir.": {
        "en": "A faculty must be selected for the department.",
        "ru": "Для кафедры нужно выбрать факультет.",
        "tr": "Bölüm için fakülte seçilmelidir.",
    },
    "Kafedralar": {"en": "Departments", "ru": "Кафедры", "tr": "Bölümler"},
    "Kafedralar, müdirlər və müəllim heyəti. «Heyət» çekmecəsi tam siyahını açır; müdir və müəllim təyinatı buradan aparılır.": {
        "en": "Departments, heads and teaching staff. The “Staff” drawer opens the full list; head and teacher assignments are made here.",
        "ru": "Кафедры, заведующие и преподавательский состав. Панель «Сотрудники» открывает полный список; назначение заведующего и преподавателей выполняется здесь.",
        "tr": "Bölümler, başkanlar ve öğretim kadrosu. «Personel» çekmecesi tam listeyi açar; başkan ve öğretim elemanı ataması buradan yapılır.",
    },
    "Laboratoriya": {"en": "Laboratory", "ru": "Лаборатория", "tr": "Laboratuvar"},
    "Müavinlər · Koordinatorlar": {
        "en": "Vice-deans · Coordinators",
        "ru": "Заместители · Координаторы",
        "tr": "Yardımcılar · Koordinatörler",
    },
    "Müdirsiz": {"en": "Without head", "ru": "Без заведующего", "tr": "Başkansız"},
    "Müəllim təyinatı üçün `member.edit` səlahiyyəti lazımdır.": {
        "en": "Teacher assignment requires the `member.edit` permission.",
        "ru": "Для назначения преподавателя нужно право `member.edit`.",
        "tr": "Öğretim elemanı ataması için `member.edit` yetkisi gerekir.",
    },
    "Müəllimin kafedrasız eyni rollu üzvlüyü artıq mövcuddur.": {
        "en": "The teacher already has a membership with the same role and no department.",
        "ru": "У преподавателя уже есть членство с той же ролью без кафедры.",
        "tr": "Öğretim elemanının bölümsüz aynı rollü üyeliği zaten var.",
    },
    "Müəllimlər": {"en": "Teachers", "ru": "Преподаватели", "tr": "Öğretim elemanları"},
    "Mərkəz": {"en": "Center", "ru": "Центр", "tr": "Merkez"},
    "Naməlum əməl.": {"en": "Unknown action.", "ru": "Неизвестное действие.", "tr": "Bilinmeyen işlem."},
    "Nəticə: %(n)d fakültə": {
        "en": "Result: %(n)d faculties",
        "ru": "Результат: %(n)d факультетов",
        "tr": "Sonuç: %(n)d fakülte",
    },
    "Nəticə: %(n)d kafedra": {
        "en": "Result: %(n)d departments",
        "ru": "Результат: %(n)d кафедр",
        "tr": "Sonuç: %(n)d bölüm",
    },
    "Proqram koordinatoru": {"en": "Program coordinator", "ru": "Координатор программы", "tr": "Program koordinatörü"},
    "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
    "Rəhbər təyinatı silindi.": {
        "en": "Head assignment removed.",
        "ru": "Назначение руководителя удалено.",
        "tr": "Yönetici ataması kaldırıldı.",
    },
    "Rəhbər təyini üçün `unit.assign_head` və ya `member.edit` lazımdır.": {
        "en": "Assigning a head requires `unit.assign_head` or `member.edit`.",
        "ru": "Для назначения руководителя нужно `unit.assign_head` или `member.edit`.",
        "tr": "Yönetici atamak için `unit.assign_head` veya `member.edit` gerekir.",
    },
    "Rəhbəri var": {"en": "Has head", "ru": "Есть руководитель", "tr": "Yöneticisi var"},
    "Rəhbəri yoxdur": {"en": "No head", "ru": "Нет руководителя", "tr": "Yöneticisi yok"},
    "Seçilmiş fakültə tapılmadı və ya əhatənizdə deyil.": {
        "en": "The selected faculty was not found or is outside your scope.",
        "ru": "Выбранный факультет не найден или вне вашей зоны ответственности.",
        "tr": "Seçilen fakülte bulunamadı veya kapsamınızda değil.",
    },
    "Seçilmiş şəxs bu təşkilatın aktiv müəllim üzvü deyil.": {
        "en": "The selected person is not an active teacher member of this organization.",
        "ru": "Выбранный человек не является активным преподавателем этой организации.",
        "tr": "Seçilen kişi bu kurumun aktif öğretim elemanı üyesi değil.",
    },
    "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil.": {
        "en": "The selected person is not an active member of this organization.",
        "ru": "Выбранный человек не является активным участником этой организации.",
        "tr": "Seçilen kişi bu kurumun aktif üyesi değil.",
    },
    "Seçilmiş əhatə bu bölmənin alt-ağacında deyil.": {
        "en": "The selected scope is not within this unit's subtree.",
        "ru": "Выбранная область не входит в поддерево этого подразделения.",
        "tr": "Seçilen kapsam bu birimin alt ağacında değil.",
    },
    "Struktur bölmələrinə baxış üçün əhatəniz yoxdur. Rolunuza bölmə (fakültə/kafedra) təyin edilməlidir.": {
        "en": "You have no scope to view structural units. A unit (faculty/department) must be assigned to your role.",
        "ru": "У вас нет области для просмотра структурных подразделений. Вашей роли нужно назначить подразделение (факультет/кафедру).",
        "tr": "Yapısal birimleri görüntülemek için kapsamınız yok. Rolünüze bir birim (fakülte/bölüm) atanmalıdır.",
    },
    "Struktur əhatəniz yoxdur.": {
        "en": "You have no structural scope.",
        "ru": "У вас нет структурной области.",
        "tr": "Yapısal kapsamınız yok.",
    },
    "Sıralama": {"en": "Sort", "ru": "Сортировка", "tr": "Sıralama ölçütü"},
    "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil.": {
        "en": "The reason must be at least 20 characters — a short note is not enough for the audit.",
        "ru": "Причина должна содержать не менее 20 символов — короткой заметки для аудита недостаточно.",
        "tr": "Gerekçe en az 20 karakter olmalıdır — kısa not denetim için yeterli değil.",
    },
    "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
    "Tələbə hesabına heyət rolu verilə bilməz.": {
        "en": "A staff role cannot be granted to a student account.",
        "ru": "Учётной записи студента нельзя выдать роль сотрудника.",
        "tr": "Öğrenci hesabına personel rolü verilemez.",
    },
    "Tələbə hesabına müəllim statusu verilə bilməz.": {
        "en": "Teacher status cannot be granted to a student account.",
        "ru": "Учётной записи студента нельзя выдать статус преподавателя.",
        "tr": "Öğrenci hesabına öğretim elemanı statüsü verilemez.",
    },
    "Tələbə hesabına rəhbər rolu verilə bilməz.": {
        "en": "A head role cannot be granted to a student account.",
        "ru": "Учётной записи студента нельзя выдать роль руководителя.",
        "tr": "Öğrenci hesabına yönetici rolü verilemez.",
    },
    "Vahid növü tanınmadı.": {
        "en": "Unit type not recognized.",
        "ru": "Тип подразделения не распознан.",
        "tr": "Birim türü tanınmadı.",
    },
    "Yeni bölmə yaratmaq üçün `unit.create` səlahiyyəti lazımdır.": {
        "en": "Creating a new unit requires the `unit.create` permission.",
        "ru": "Для создания нового подразделения нужно право `unit.create`.",
        "tr": "Yeni birim oluşturmak için `unit.create` yetkisi gerekir.",
    },
    "cari tədris ili": {"en": "current academic year", "ru": "текущий учебный год", "tr": "bu öğretim yılı"},
    "cari tədris ilində dərs deyən": {
        "en": "teaching in the current academic year",
        "ru": "ведут занятия в текущем учебном году",
        "tr": "bu öğretim yılında ders veren",
    },
    "hamısında dekan var": {"en": "all have a dean", "ru": "у всех есть декан", "tr": "hepsinde dekan var"},
    "hamısında müdir var": {"en": "all have a head", "ru": "у всех есть заведующий", "tr": "hepsinde başkan var"},
    "kafedrasız": {"en": "without department", "ru": "без кафедры", "tr": "bölümsüz"},
    "müdir təyin edilməyib": {"en": "no head assigned", "ru": "заведующий не назначен", "tr": "başkan atanmamış"},
    "rəhbər təyin edilməyib": {"en": "no head assigned", "ru": "руководитель не назначен", "tr": "yönetici atanmamış"},
    "«%(name)s» arxivləndi.": {
        "en": "“%(name)s” archived.",
        "ru": "«%(name)s» архивировано.",
        "tr": "«%(name)s» arşivlendi.",
    },
    "«%(name)s» arxivlənə bilməz: %(n)d aktiv alt bölmə var. Əvvəlcə onları köçürün.": {
        "en": "“%(name)s” cannot be archived: it has %(n)d active sub-units. Move them first.",
        "ru": "«%(name)s» нельзя архивировать: есть %(n)d активных дочерних подразделений. Сначала перенесите их.",
        "tr": "«%(name)s» arşivlenemez: %(n)d aktif alt birim var. Önce onları taşıyın.",
    },
    "«%(name)s» arxivlənə bilməz: %(n)d aktiv üzv bu bölməyə təyin olunub.": {
        "en": "“%(name)s” cannot be archived: %(n)d active members are assigned to this unit.",
        "ru": "«%(name)s» нельзя архивировать: к этому подразделению привязано %(n)d активных участников.",
        "tr": "«%(name)s» arşivlenemez: bu birime %(n)d aktif üye atanmış.",
    },
    "«%(role)s» rolu bu təşkilatda yoxdur — default rollar yüklənməlidir.": {
        "en": "The “%(role)s” role does not exist in this organization — default roles must be loaded.",
        "ru": "Роли «%(role)s» нет в этой организации — нужно загрузить роли по умолчанию.",
        "tr": "«%(role)s» rolü bu kurumda yok — varsayılan roller yüklenmelidir.",
    },
    "«Yeni fakültə» ilə ilk fakültəni yaradın; kafedralar ona bağlanacaq.": {
        "en": "Create the first faculty with “New faculty”; departments will be attached to it.",
        "ru": "Создайте первый факультет через «Новый факультет»; кафедры будут привязаны к нему.",
        "tr": "«Yeni fakülte» ile ilk fakülteyi oluşturun; bölümler ona bağlanacak.",
    },
    "«Yeni kafedra» ilə ilk kafedranı yaradın və fakültəyə bağlayın.": {
        "en": "Create the first department with “New department” and attach it to a faculty.",
        "ru": "Создайте первую кафедру через «Новая кафедра» и привяжите её к факультету.",
        "tr": "«Yeni bölüm» ile ilk bölümü oluşturun ve fakülteye bağlayın.",
    },
    "İnstitut": {"en": "Institute", "ru": "Институт", "tr": "Enstitü"},
    "İxtisas": {"en": "Specialty", "ru": "Специальность", "tr": "Program"},
    "İxtisaslar": {"en": "Specialties", "ru": "Специальности", "tr": "Programlar"},
    "Şöbə": {"en": "Division", "ru": "Отдел", "tr": "Şube"},
    "Şəxs seçilməlidir və bu təşkilatın aktiv üzvü olmalıdır.": {
        "en": "A person must be selected and must be an active member of this organization.",
        "ru": "Нужно выбрать человека, и он должен быть активным участником этой организации.",
        "tr": "Bir kişi seçilmeli ve bu kurumun aktif üyesi olmalıdır.",
    },
    "Əməllər": {"en": "Actions", "ru": "Действия", "tr": "İşlemler"},
    "Ən köhnə": {"en": "Oldest", "ru": "Сначала старые", "tr": "En eski"},
    "Ən yeni": {"en": "Newest", "ru": "Сначала новые", "tr": "En yeni"},
}

D["profile.publish_notification"] = {
    "Bütün müəllimlər": {"en": "All teachers", "ru": "Все преподаватели", "tr": "Tüm öğretim elemanları"},
    "Bütün tələbələr": {"en": "All students", "ru": "Все студенты", "tr": "Tüm öğrenciler"},
    "Dekanlar və müavinlər": {
        "en": "Deans and vice-deans",
        "ru": "Деканы и заместители",
        "tr": "Dekanlar ve yardımcıları",
    },
    "Fakültələr": {"en": "Faculties", "ru": "Факультеты", "tr": "Fakülteler"},
    "HR / kadrlar": {"en": "HR / personnel", "ru": "HR / кадры", "tr": "İK / personel"},
    "Kafedra müdirləri": {"en": "Heads of departments", "ru": "Заведующие кафедрами", "tr": "Bölüm başkanları"},
    "Kafedralar": {"en": "Departments", "ru": "Кафедры", "tr": "Bölümler"},
    "Qruplar": {"en": "Groups", "ru": "Группы", "tr": "Gruplar"},
    "RİM mərkəzi": {"en": "RIM center", "ru": "Центр RİM", "tr": "RİM merkezi"},
    "Tədris şöbəsi": {"en": "Academic Office", "ru": "Учебный отдел", "tr": "Öğrenci İşleri"},
    "Təşkilat": {"en": "Organization", "ru": "Организация", "tr": "Kurum"},
    "İmtahan mərkəzi": {"en": "Exam center", "ru": "Экзаменационный центр", "tr": "Sınav merkezi"},
    "İmtahan qrupları": {"en": "Exam groups", "ru": "Экзаменационные группы", "tr": "Sınav grupları"},
    "Şöbələr və heyət": {"en": "Divisions and staff", "ru": "Отделы и сотрудники", "tr": "Şubeler ve personel"},
}

D["profile.rim"] = {
    "Maliyyələşmə növü tanınmadı.": {
        "en": "Funding type not recognized.",
        "ru": "Тип финансирования не распознан.",
        "tr": "Finansman türü tanınmadı.",
    },
    "Təhsil forması tanınmadı.": {
        "en": "Study mode not recognized.",
        "ru": "Форма обучения не распознана.",
        "tr": "Öğretim türü tanınmadı.",
    },
}

D["profile.subjects"] = {
    "%(count)s fənn": {"en": "%(count)s subjects", "ru": "%(count)s предм.", "tr": "%(count)s ders"},
    "%(count)s fənn limitə yaxındır — davamiyyətə diqqət": {
        "en": "%(count)s subjects are close to the limit — watch your attendance",
        "ru": "%(count)s предм. близки к лимиту — следите за посещаемостью",
        "tr": "%(count)s ders sınıra yakın — devama dikkat",
    },
    "Semestr krediti": {"en": "Semester credits", "ru": "Кредиты семестра", "tr": "Yarıyıl kredisi"},
    "Toplanmış bal (orta)": {
        "en": "Accumulated score (average)",
        "ru": "Накопленный балл (средний)",
        "tr": "Toplanan puan (ortalama)",
    },
    "Yekun nəticə": {"en": "Final result", "ru": "Итоговый результат", "tr": "Final sonucu"},
    "bütün fənlərdə imtahana buraxılırsınız": {
        "en": "you are admitted to the exam in all subjects",
        "ru": "вы допущены к экзамену по всем предметам",
        "tr": "tüm derslerde sınava girebilirsiniz",
    },
    "hələ yekun imtahan nəticəsi yoxdur": {
        "en": "no final exam result yet",
        "ru": "итогового результата экзамена пока нет",
        "tr": "henüz final sınavı sonucu yok",
    },
    "icazəli qayıbın 75%-i keçilib — diqqət": {
        "en": "75% of allowed absences exceeded — attention",
        "ru": "превышено 75% допустимых пропусков — внимание",
        "tr": "izin verilen devamsızlığın %75'i aşıldı — dikkat",
    },
    "imtahana qədər toplanan bal (orta)": {
        "en": "score accumulated before the exam (average)",
        "ru": "балл, накопленный до экзамена (средний)",
        "tr": "sınava kadar toplanan puan (ortalama)",
    },
    "keçdi %(passed)s · kəsildi %(failed)s": {
        "en": "passed %(passed)s · failed %(failed)s",
        "ru": "сдано %(passed)s · не сдано %(failed)s",
        "tr": "geçti %(passed)s · kaldı %(failed)s",
    },
    "köhnə sistemdən köçürülmüş, bağlı semestr — status yenidən hesablanmır, faktiki nəticə göstərilir": {
        "en": "migrated from the legacy system, closed semester — the status is not recalculated, the actual result is shown",
        "ru": "перенесено из старой системы, закрытый семестр — статус не пересчитывается, показан фактический результат",
        "tr": "eski sistemden aktarılmış, kapalı yarıyıl — durum yeniden hesaplanmaz, gerçek sonuç gösterilir",
    },
    "qayıb həddi keçilib — dekanlığa müraciət edin": {
        "en": "absence limit exceeded — contact the dean's office",
        "ru": "лимит пропусков превышен — обратитесь в деканат",
        "tr": "devamsızlık sınırı aşıldı — dekanlığa başvurun",
    },
    "qayıb həddi keçilib, yekun imtahana giriş yoxdur": {
        "en": "absence limit exceeded, no admission to the final exam",
        "ru": "лимит пропусков превышен, допуска к итоговому экзамену нет",
        "tr": "devamsızlık sınırı aşıldı, final sınavına giriş yok",
    },
    "qayıb icazəli həddin altındadır": {
        "en": "absences are below the allowed limit",
        "ru": "пропуски ниже допустимого лимита",
        "tr": "devamsızlık izin verilen sınırın altında",
    },
    "yekun imtahanın balı hələ əlavə olunmayıb": {
        "en": "the final exam score has not been added yet",
        "ru": "балл итогового экзамена ещё не добавлен",
        "tr": "final sınavı puanı henüz eklenmedi",
    },
    "İmtahana buraxılmayan": {"en": "Not admitted to exam", "ru": "Не допущены к экзамену", "tr": "Sınava giremeyen"},
}

D["registrar.catalog"] = {
    "Akademik kataloqu idarə etmək üçün icazəniz yoxdur.": {
        "en": "You do not have permission to manage the academic catalog.",
        "ru": "У вас нет прав на управление академическим каталогом.",
        "tr": "Akademik kataloğu yönetme yetkiniz yok.",
    },
}

D["registrar.exam_score_entry"] = {
    "(qrupsuz açılış)": {"en": "(offering without group)", "ru": "(открытие без группы)", "tr": "(grupsuz açılış)"},
    "Bal 0 ilə %(max)s arasında olmalıdır.": {
        "en": "The score must be between 0 and %(max)s.",
        "ru": "Балл должен быть от 0 до %(max)s.",
        "tr": "Puan 0 ile %(max)s arasında olmalıdır.",
    },
    "Bal rəqəm olmalıdır.": {
        "en": "The score must be a number.",
        "ru": "Балл должен быть числом.",
        "tr": "Puan sayı olmalıdır.",
    },
    "Bal tam ədəd olmalıdır.": {
        "en": "The score must be an integer.",
        "ru": "Балл должен быть целым числом.",
        "tr": "Puan tam sayı olmalıdır.",
    },
    "Balı dəyişmək üçün izahat qeydi məcburidir.": {
        "en": "An explanatory note is required to change the score.",
        "ru": "Для изменения балла обязательна пояснительная заметка.",
        "tr": "Puanı değiştirmek için açıklama notu zorunludur.",
    },
    "Balı dəyişmək üçün səbəb seçilməlidir.": {
        "en": "A reason must be selected to change the score.",
        "ru": "Для изменения балла нужно выбрать причину.",
        "tr": "Puanı değiştirmek için gerekçe seçilmelidir.",
    },
    "Balı dəyişmək üçün təsdiqedici sənəd əlavə olunmalıdır.": {
        "en": "A supporting document must be attached to change the score.",
        "ru": "Для изменения балла нужно приложить подтверждающий документ.",
        "tr": "Puanı değiştirmek için destekleyici belge eklenmelidir.",
    },
    "Bu açılış sizin struktur əhatənizdə deyil.": {
        "en": "This offering is outside your structural scope.",
        "ru": "Это открытие вне вашей структурной области.",
        "tr": "Bu açılış yapısal kapsamınızda değil.",
    },
    "Bu qeydiyyat aktiv deyil — bal yazılmadı.": {
        "en": "This enrollment is not active — the score was not recorded.",
        "ru": "Эта запись неактивна — балл не записан.",
        "tr": "Bu kayıt aktif değil — puan yazılmadı.",
    },
    "Dəyişdirilib": {"en": "Changed", "ru": "Изменено", "tr": "Değiştirildi"},
    "Fayldan yüklə (XLSX / CSV)": {
        "en": "Upload from file (XLSX / CSV)",
        "ru": "Загрузить из файла (XLSX / CSV)",
        "tr": "Dosyadan yükle (XLSX / CSV)",
    },
    "Köçürmə vərəqi bu açılışa aid deyil.": {
        "en": "The score sheet does not belong to this offering.",
        "ru": "Ведомость не относится к этому открытию.",
        "tr": "Puan çizelgesi bu açılışa ait değil.",
    },
    "Seç": {"en": "Select", "ru": "Выбрать", "tr": "Seçim"},
    "Yaz": {"en": "Record", "ru": "Записать", "tr": "Kayıt"},
    "Yoxla": {"en": "Check", "ru": "Проверить", "tr": "Kontrol et"},
    "balları yazın və ya faylı yoxlayın": {
        "en": "enter the scores or check the file",
        "ru": "введите баллы или проверьте файл",
        "tr": "puanları yazın veya dosyayı kontrol edin",
    },
    "qrup və fənni seçin": {
        "en": "select the group and subject",
        "ru": "выберите группу и предмет",
        "tr": "grup ve dersi seçin",
    },
    "yadda saxlanmayıb": {"en": "not saved", "ru": "не сохранено", "tr": "kaydedilmedi"},
    "yadda saxlanıldı": {"en": "saved", "ru": "сохранено", "tr": "kaydedildi"},
    "İmtahan tarixi düzgün formatda deyil.": {
        "en": "The exam date is not in a valid format.",
        "ru": "Дата экзамена в неверном формате.",
        "tr": "Sınav tarihi geçerli biçimde değil.",
    },
    "Əl ilə daxil et": {"en": "Enter manually", "ru": "Ввести вручную", "tr": "Elle gir"},
}

D["registrar.exam_score_import"] = {
    "Ad Soyad": {"en": "Full name", "ru": "Имя Фамилия", "tr": "Ad ve soyad"},
    "Bal": {"en": "Score", "ru": "Балл", "tr": "Puan"},
    "Bal 0 ilə maksimum arasında tam ədəd olmalıdır.": {
        "en": "The score must be an integer between 0 and the maximum.",
        "ru": "Балл должен быть целым числом от 0 до максимума.",
        "tr": "Puan 0 ile en yüksek değer arasında tam sayı olmalıdır.",
    },
    "Bal boşdur — toxunulmur.": {
        "en": "Score is empty — left untouched.",
        "ru": "Балл пуст — не изменяется.",
        "tr": "Puan boş — dokunulmaz.",
    },
    "Bu serverdə .xlsx oxunmur — faylı CSV kimi yadda saxlayıb yenidən yükləyin.": {
        "en": ".xlsx cannot be read on this server — save the file as CSV and upload it again.",
        "ru": "На этом сервере .xlsx не читается — сохраните файл как CSV и загрузите снова.",
        "tr": "Bu sunucuda .xlsx okunamıyor — dosyayı CSV olarak kaydedip yeniden yükleyin.",
    },
    "Bu tələbə faylda təkrarlanır.": {
        "en": "This student is duplicated in the file.",
        "ru": "Этот студент повторяется в файле.",
        "tr": "Bu öğrenci dosyada tekrarlanıyor.",
    },
    "CSV faylı oxunmadı.": {
        "en": "The CSV file could not be read.",
        "ru": "Не удалось прочитать CSV-файл.",
        "tr": "CSV dosyası okunamadı.",
    },
    "Cari bal": {"en": "Current score", "ru": "Текущий балл", "tr": "Mevcut puan"},
    "Eyni adlı bir neçə tələbə var — Tələbə № və ya FİN yazın.": {
        "en": "Several students have the same name — enter the Student No. or FIN.",
        "ru": "Несколько студентов с одинаковым именем — укажите № студента или FIN.",
        "tr": "Aynı adlı birden çok öğrenci var — Öğrenci No veya FİN yazın.",
    },
    "Eyni bal artıq yazılıb.": {
        "en": "The same score is already recorded.",
        "ru": "Такой балл уже записан.",
        "tr": "Aynı puan zaten yazılmış.",
    },
    "Fayl boşdur — başlıq sətri tapılmadı.": {
        "en": "The file is empty — no header row found.",
        "ru": "Файл пуст — строка заголовка не найдена.",
        "tr": "Dosya boş — başlık satırı bulunamadı.",
    },
    "Fayl boşdur.": {"en": "The file is empty.", "ru": "Файл пуст.", "tr": "Dosya boş."},
    "Fayl oxunmadı — kodlaşdırma tanınmadı.": {
        "en": "The file could not be read — encoding not recognized.",
        "ru": "Не удалось прочитать файл — кодировка не распознана.",
        "tr": "Dosya okunamadı — kodlama tanınmadı.",
    },
    "Fayl oxunmadı — zədəli və ya dəstəklənməyən Excel faylıdır.": {
        "en": "The file could not be read — corrupted or unsupported Excel file.",
        "ru": "Не удалось прочитать файл — повреждённый или неподдерживаемый файл Excel.",
        "tr": "Dosya okunamadı — bozuk veya desteklenmeyen Excel dosyası.",
    },
    "Fayl seçilməyib.": {"en": "No file selected.", "ru": "Файл не выбран.", "tr": "Dosya seçilmedi."},
    "Fayl çox böyükdür (maksimum 5 MB).": {
        "en": "The file is too large (maximum 5 MB).",
        "ru": "Файл слишком большой (максимум 5 МБ).",
        "tr": "Dosya çok büyük (en fazla 5 MB).",
    },
    "Faylda sütun limiti aşılıb.": {
        "en": "The column limit in the file is exceeded.",
        "ru": "В файле превышен лимит столбцов.",
        "tr": "Dosyada sütun sınırı aşıldı.",
    },
    "Faylda sətir limiti aşılıb.": {
        "en": "The row limit in the file is exceeded.",
        "ru": "В файле превышен лимит строк.",
        "tr": "Dosyada satır sınırı aşıldı.",
    },
    "Faylda tələbə sətri tapılmadı.": {
        "en": "No student rows found in the file.",
        "ru": "В файле не найдено строк студентов.",
        "tr": "Dosyada öğrenci satırı bulunamadı.",
    },
    "Faylın başlıq sətrində «Bal» və «Tələbə №» (və ya FİN / Ad Soyad) sütunları tapılmadı.": {
        "en": "The “Score” and “Student No.” (or FIN / Full name) columns were not found in the file's header row.",
        "ru": "В строке заголовка файла не найдены столбцы «Балл» и «№ студента» (или FIN / Имя Фамилия).",
        "tr": "Dosyanın başlık satırında «Puan» ve «Öğrenci No» (veya FİN / Ad Soyad) sütunları bulunamadı.",
    },
    "FİN": {"en": "FIN", "ru": "FIN", "tr": "FİN kodu"},
    "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
    "Tələbə bu qrupun siyahısında tapılmadı (qeydiyyatı yoxdur).": {
        "en": "The student was not found in this group's list (no enrollment).",
        "ru": "Студент не найден в списке этой группы (нет записи).",
        "tr": "Öğrenci bu grubun listesinde bulunamadı (kaydı yok).",
    },
    "Tələbə №": {"en": "Student No.", "ru": "№ студента", "tr": "Öğrenci No"},
    "Tələbə № və FİN fərqli tələbələrə aiddir.": {
        "en": "The Student No. and FIN belong to different students.",
        "ru": "№ студента и FIN относятся к разным студентам.",
        "tr": "Öğrenci No ve FİN farklı öğrencilere ait.",
    },
    "Yalnız .xlsx və ya .csv faylı qəbul olunur.": {
        "en": "Only .xlsx or .csv files are accepted.",
        "ru": "Принимаются только файлы .xlsx или .csv.",
        "tr": "Yalnızca .xlsx veya .csv dosyası kabul edilir.",
    },
    "Yazıldı.": {"en": "Recorded.", "ru": "Записано.", "tr": "Kaydedildi."},
    "Yazılmış bal dəyişir — səbəb, qeyd və sənəd tələb olunur.": {
        "en": "A recorded score changes — a reason, a note and a document are required.",
        "ru": "Записанный балл меняется — требуются причина, примечание и документ.",
        "tr": "Kayıtlı puan değişiyor — gerekçe, not ve belge gerekli.",
    },
    "ada görə uyğunlaşdırıldı": {"en": "matched by name", "ru": "сопоставлено по имени", "tr": "ada göre eşleştirildi"},
}

D["registrar.guest_roster"] = {
    "Bu semestr bağlıdır — keçmiş dövrün jurnalına tələbə əlavə etmək və ya çıxarmaq olmaz.": {
        "en": "This semester is closed — students cannot be added to or removed from a past period's journal.",
        "ru": "Этот семестр закрыт — в журнал прошлого периода нельзя добавлять или удалять студентов.",
        "tr": "Bu yarıyıl kapalı — geçmiş dönemin defterine öğrenci eklenemez veya çıkarılamaz.",
    },
    "Bu tələbə artıq jurnalda deyil.": {
        "en": "This student is no longer in the journal.",
        "ru": "Этого студента уже нет в журнале.",
        "tr": "Bu öğrenci artık defterde değil.",
    },
    "Bu tələbə artıq jurnaldadır.": {
        "en": "This student is already in the journal.",
        "ru": "Этот студент уже в журнале.",
        "tr": "Bu öğrenci zaten defterde.",
    },
    "Bu tələbə öz qrupunun tələbəsidir — jurnaldan yalnız rəsmi qrup köçürməsi ilə çıxarıla bilər.": {
        "en": "This student belongs to their own group — they can only be removed from the journal by an official group transfer.",
        "ru": "Этот студент — студент своей группы; из журнала его можно убрать только официальным переводом группы.",
        "tr": "Bu öğrenci kendi grubunun öğrencisi — defterden yalnızca resmi grup aktarımıyla çıkarılabilir.",
    },
    "Bu tələbənin burada rəsmi köçürmə tarixçəsi var — inzibati yoxlama tələb olunur.": {
        "en": "This student has an official transfer history here — an administrative check is required.",
        "ru": "У этого студента здесь есть история официальных переводов — требуется административная проверка.",
        "tr": "Bu öğrencinin burada resmi aktarım geçmişi var — idari kontrol gerekli.",
    },
    "Jurnal bağlanıb — siyahısı dəyişdirilə bilməz.": {
        "en": "The journal is closed — its roster cannot be changed.",
        "ru": "Журнал закрыт — его список нельзя изменить.",
        "tr": "Defter kapatılmış — listesi değiştirilemez.",
    },
    "Qeydiyyat tapılmadı.": {"en": "Enrollment not found.", "ru": "Запись не найдена.", "tr": "Kayıt bulunamadı."},
    "Qrup və tələbə seçilməlidir.": {
        "en": "A group and a student must be selected.",
        "ru": "Нужно выбрать группу и студента.",
        "tr": "Grup ve öğrenci seçilmelidir.",
    },
    "Seçilmiş qrup sizin əhatənizdə deyil.": {
        "en": "The selected group is outside your scope.",
        "ru": "Выбранная группа вне вашей зоны ответственности.",
        "tr": "Seçilen grup kapsamınızda değil.",
    },
    "Tələbə jurnala əlavə olundu.": {
        "en": "Student added to the journal.",
        "ru": "Студент добавлен в журнал.",
        "tr": "Öğrenci deftere eklendi.",
    },
    "Tələbə onsuz da bu qrupun tələbəsidir — alt qrupdan əlavə tələb olunmur.": {
        "en": "The student already belongs to this group — no sub-group addition is needed.",
        "ru": "Студент и так является студентом этой группы — добавление из подгруппы не требуется.",
        "tr": "Öğrenci zaten bu grubun öğrencisi — alt gruptan ekleme gerekmiyor.",
    },
    "Tələbə seçilmiş qrupda tapılmadı.": {
        "en": "The student was not found in the selected group.",
        "ru": "Студент не найден в выбранной группе.",
        "tr": "Öğrenci seçilen grupta bulunamadı.",
    },
    "Tələbənin aktiv akademik qeydi (qrupu) yoxdur.": {
        "en": "The student has no active academic record (group).",
        "ru": "У студента нет активной академической записи (группы).",
        "tr": "Öğrencinin aktif akademik kaydı (grubu) yok.",
    },
    "onsuz da bu jurnaldadır": {"en": "already in this journal", "ru": "уже в этом журнале", "tr": "zaten bu defterde"},
    "Əməliyyat üçün icraçı tələb olunur.": {
        "en": "An actor is required for the action.",
        "ru": "Для действия требуется исполнитель.",
        "tr": "İşlem için uygulayıcı gerekli.",
    },
    "Əvvəlki əlavənin mənbə qrupu fərqlidir.": {
        "en": "The source group of the previous addition is different.",
        "ru": "Исходная группа предыдущего добавления отличается.",
        "tr": "Önceki eklemenin kaynak grubu farklı.",
    },
}

D["registrar.journal"] = {
    "%(count)s fənn limitə yaxındır — davamiyyətə diqqət": {
        "en": "%(count)s subjects are close to the limit — watch your attendance",
        "ru": "%(count)s предм. близки к лимиту — следите за посещаемостью",
        "tr": "%(count)s ders sınıra yakın — devama dikkat",
    },
    "%(ects)s ECTS": {"en": "%(ects)s ECTS credits", "ru": "%(ects)s кредитов ECTS", "tr": "%(ects)s AKTS"},
    "%(ects)s ECTS · %(period)s": {
        "en": "%(ects)s ECTS credits · %(period)s",
        "ru": "%(ects)s кредитов ECTS · %(period)s",
        "tr": "%(ects)s AKTS · %(period)s",
    },
    "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
    "Giriş balı (orta)": {
        "en": "Admission score (average)",
        "ru": "Балл допуска (средний)",
        "tr": "Giriş puanı (ortalama)",
    },
    "Qayıb (cəmi)": {"en": "Absences (total)", "ru": "Пропуски (всего)", "tr": "Devamsızlık (toplam)"},
    "bütün fənlərdə imtahana buraxılırsınız": {
        "en": "you are admitted to the exam in all subjects",
        "ru": "вы допущены к экзамену по всем предметам",
        "tr": "tüm derslerde sınava girebilirsiniz",
    },
    "icazəli qayıbın 75%-i keçilib — diqqət": {
        "en": "75% of allowed absences exceeded — attention",
        "ru": "превышено 75% допустимых пропусков — внимание",
        "tr": "izin verilen devamsızlığın %75'i aşıldı — dikkat",
    },
    "imtahana qədər toplanan bal": {
        "en": "score accumulated before the exam",
        "ru": "балл, накопленный до экзамена",
        "tr": "sınava kadar toplanan puan",
    },
    "köhnə sistemdən köçürülmüş, bağlı semestr — status yenidən hesablanmır, faktiki nəticə göstərilir": {
        "en": "migrated from the legacy system, closed semester — the status is not recalculated, the actual result is shown",
        "ru": "перенесено из старой системы, закрытый семестр — статус не пересчитывается, показан фактический результат",
        "tr": "eski sistemden aktarılmış, kapalı yarıyıl — durum yeniden hesaplanmaz, gerçek sonuç gösterilir",
    },
    "qayıb həddi keçilib — dekanlığa müraciət edin": {
        "en": "absence limit exceeded — contact the dean's office",
        "ru": "лимит пропусков превышен — обратитесь в деканат",
        "tr": "devamsızlık sınırı aşıldı — dekanlığa başvurun",
    },
    "qayıb həddi keçilib, yekun imtahana giriş yoxdur": {
        "en": "absence limit exceeded, no admission to the final exam",
        "ru": "лимит пропусков превышен, допуска к итоговому экзамену нет",
        "tr": "devamsızlık sınırı aşıldı, final sınavına giriş yok",
    },
    "qayıb icazəli həddin altındadır": {
        "en": "absences are below the allowed limit",
        "ru": "пропуски ниже допустимого лимита",
        "tr": "devamsızlık izin verilen sınırın altında",
    },
    "üzrsüz buraxılmış dərs saatı, bütün fənlər üzrə": {
        "en": "unexcused missed lesson hours, across all subjects",
        "ru": "пропущенные без уважительной причины часы, по всем предметам",
        "tr": "mazeretsiz kaçırılan ders saati, tüm dersler için",
    },
    "İmtahana buraxılmayan": {"en": "Not admitted to exam", "ru": "Не допущены к экзамену", "tr": "Sınava giremeyen"},
}

D["registrar.journal_close"] = {
    "Fakültə / kafedra": {"en": "Faculty / department", "ru": "Факультет / кафедра", "tr": "Fakülte / bölüm"},
    "Fakültə əhatəsi üçün fakültə seçilməlidir.": {
        "en": "A faculty must be selected for the faculty scope.",
        "ru": "Для области факультета нужно выбрать факультет.",
        "tr": "Fakülte kapsamı için fakülte seçilmelidir.",
    },
    "Fakültə/kafedra əhatəsi üçün bölmə seçilməlidir.": {
        "en": "A unit must be selected for the faculty/department scope.",
        "ru": "Для области факультета/кафедры нужно выбрать подразделение.",
        "tr": "Fakülte/bölüm kapsamı için birim seçilmelidir.",
    },
    "Jurnalı açmaq üçün səbəb yazılmalıdır.": {
        "en": "A reason is required to open the journal.",
        "ru": "Для открытия журнала нужно указать причину.",
        "tr": "Defteri açmak için gerekçe yazılmalıdır.",
    },
    "Kafedra əhatəsi üçün kafedra seçilməlidir.": {
        "en": "A department must be selected for the department scope.",
        "ru": "Для области кафедры нужно выбрать кафедру.",
        "tr": "Bölüm kapsamı için bölüm seçilmelidir.",
    },
    "Səbəb": {"en": "Reason", "ru": "Причина", "tr": "Gerekçe"},
}

D["registrar.journal_close_notify"] = {
    "Jurnal bağlandı: %(period)s (%(scope)s)": {
        "en": "Journal closed: %(period)s (%(scope)s)",
        "ru": "Журнал закрыт: %(period)s (%(scope)s)",
        "tr": "Defter kapatıldı: %(period)s (%(scope)s)",
    },
    "Jurnal yenidən açıldı: %(period)s (%(scope)s)": {
        "en": "Journal reopened: %(period)s (%(scope)s)",
        "ru": "Журнал снова открыт: %(period)s (%(scope)s)",
        "tr": "Defter yeniden açıldı: %(period)s (%(scope)s)",
    },
}

D["registrar.kollokvium_notify"] = {
    "Kollokvium K%(n)s bal-yazma pəncərəsi açıldı: %(opens)s–%(closes)s": {
        "en": "Colloquium K%(n)s score entry window opened: %(opens)s–%(closes)s",
        "ru": "Окно ввода баллов коллоквиума K%(n)s открыто: %(opens)s–%(closes)s",
        "tr": "Kolokyum K%(n)s puan girişi penceresi açıldı: %(opens)s–%(closes)s",
    },
    "Kollokvium K%(n)s bal-yazma pəncərəsi bağlandı": {
        "en": "Colloquium K%(n)s score entry window closed",
        "ru": "Окно ввода баллов коллоквиума K%(n)s закрыто",
        "tr": "Kolokyum K%(n)s puan girişi penceresi kapandı",
    },
    "Kollokvium K%(n)s bal-yazma pəncərəsinin tarixi dəyişdi: %(opens)s–%(closes)s": {
        "en": "Colloquium K%(n)s score entry window dates changed: %(opens)s–%(closes)s",
        "ru": "Даты окна ввода баллов коллоквиума K%(n)s изменены: %(opens)s–%(closes)s",
        "tr": "Kolokyum K%(n)s puan girişi penceresinin tarihi değişti: %(opens)s–%(closes)s",
    },
}

D["registrar.lessons_log"] = {
    "Payız": {"en": "Autumn", "ru": "Осень", "tr": "Güz"},
    "Yay": {"en": "Summer", "ru": "Лето", "tr": "Yaz"},
    "Yaz": {"en": "Spring", "ru": "Весна", "tr": "Bahar"},
}

D["registrar.schedule_manage"] = {
    "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur.": {
        "en": "You do not have permission to manage the timetable.",
        "ru": "У вас нет прав на управление расписанием.",
        "tr": "Ders programını yönetme yetkiniz yok.",
    },
}

D["registrar.syllabus"] = {
    "Bu fənn üzrə sillabus yazılmayıb": {
        "en": "No syllabus has been written for this subject",
        "ru": "Силлабус по этому предмету не написан",
        "tr": "Bu ders için izlence yazılmamış",
    },
    "Bu fənnin qüvvədə olan sillabusu yoxdur": {
        "en": "This subject has no syllabus in force",
        "ru": "У этого предмета нет действующего силлабуса",
        "tr": "Bu dersin yürürlükte olan izlencesi yok",
    },
    "Dərslər başlayıb, amma fənnin sillabusu hələ yaradılmayıb. Əvvəlcə sillabusunuzu yazıb kafedra müdirinin təsdiqinə göndərin — tələbələr yalnız təsdiqlənmiş sillabusu görür.": {
        "en": "Classes have started, but the subject's syllabus has not been created yet. Write your syllabus first and send it to the head of department for approval — students only see an approved syllabus.",
        "ru": "Занятия начались, но силлабус предмета ещё не создан. Сначала напишите силлабус и отправьте его на утверждение заведующему кафедрой — студенты видят только утверждённый силлабус.",
        "tr": "Dersler başladı, ancak dersin izlencesi henüz oluşturulmamış. Önce izlencenizi yazıp bölüm başkanının onayına gönderin — öğrenciler yalnızca onaylı izlenceyi görür.",
    },
    "Kafedra müdiri versiyanı düzəliş üçün geri qaytarıb. Qeydləri nəzərə alıb yenidən təsdiqə göndərin.": {
        "en": "The head of department returned the version for revision. Take the notes into account and resubmit for approval.",
        "ru": "Заведующий кафедрой вернул версию на доработку. Учтите замечания и отправьте на утверждение снова.",
        "tr": "Bölüm başkanı sürümü düzeltme için geri gönderdi. Notları dikkate alıp yeniden onaya gönderin.",
    },
    "Kafedra müdiri versiyanı rədd edib. Səbəbi oxuyub yeni versiya yaradın.": {
        "en": "The head of department rejected the version. Read the reason and create a new version.",
        "ru": "Заведующий кафедрой отклонил версию. Прочитайте причину и создайте новую версию.",
        "tr": "Bölüm başkanı sürümü reddetti. Gerekçeyi okuyup yeni sürüm oluşturun.",
    },
    "Kafedra müdirinin qeydi": {
        "en": "Head of department's note",
        "ru": "Замечание заведующего кафедрой",
        "tr": "Bölüm başkanının notu",
    },
    "Qaralamanı tamamla": {"en": "Complete the draft", "ru": "Завершить черновик", "tr": "Taslağı tamamla"},
    "Qeydlərə bax və düzəlt": {
        "en": "Review the notes and fix",
        "ru": "Посмотреть замечания и исправить",
        "tr": "Notlara bak ve düzelt",
    },
    "Sillabus hələ qaralamadır": {
        "en": "The syllabus is still a draft",
        "ru": "Силлабус пока черновик",
        "tr": "İzlence henüz taslak",
    },
    "Sillabus versiyası rədd edilib": {
        "en": "Syllabus version rejected",
        "ru": "Версия силлабуса отклонена",
        "tr": "İzlence sürümü reddedildi",
    },
    "Sillabus yaradılıb, amma təsdiqə göndərilməyib. Qaralama tələbələrə görünmür — bölmələri tamamlayıb kafedra müdirinin təsdiqinə göndərin.": {
        "en": "The syllabus has been created but not submitted for approval. A draft is not visible to students — complete the sections and send it to the head of department for approval.",
        "ru": "Силлабус создан, но не отправлен на утверждение. Черновик студентам не виден — заполните разделы и отправьте на утверждение заведующему кафедрой.",
        "tr": "İzlence oluşturuldu, ancak onaya gönderilmedi. Taslak öğrencilere görünmez — bölümleri tamamlayıp bölüm başkanının onayına gönderin.",
    },
    "Sillabus yarat": {"en": "Create syllabus", "ru": "Создать силлабус", "tr": "İzlence oluştur"},
    "Sillabus üzrə düzəliş tələb olunur": {
        "en": "Syllabus revision required",
        "ru": "Требуется доработка силлабуса",
        "tr": "İzlencede düzeltme gerekli",
    },
    "Sillabusunuz kafedra müdirinin baxışındadır": {
        "en": "Your syllabus is under review by the head of department",
        "ru": "Ваш силлабус на рассмотрении у заведующего кафедрой",
        "tr": "İzlenceniz bölüm başkanının incelemesinde",
    },
    "Səbəbi oxu": {"en": "Read the reason", "ru": "Прочитать причину", "tr": "Gerekçeyi oku"},
    "Versiya təsdiq növbəsinə göndərilib və baxış müddətində kilidlidir. Cavab gələnə qədər əməl tələb olunmur.": {
        "en": "The version has been submitted for approval and is locked during review. No action is required until a response arrives.",
        "ru": "Версия отправлена в очередь на утверждение и заблокирована на время рассмотрения. До получения ответа действий не требуется.",
        "tr": "Sürüm onay kuyruğuna gönderildi ve inceleme süresince kilitli. Yanıt gelene kadar işlem gerekmiyor.",
    },
    "Yalnız arxiv nüsxəsi qalıb — cari semestr üçün yeni versiya yaradıb təsdiqə göndərin.": {
        "en": "Only an archived copy remains — create a new version for the current semester and submit it for approval.",
        "ru": "Осталась только архивная копия — создайте новую версию для текущего семестра и отправьте на утверждение.",
        "tr": "Yalnızca arşiv kopyası kaldı — bu yarıyıl için yeni sürüm oluşturup onaya gönderin.",
    },
    "Yeni versiya yarat": {"en": "Create a new version", "ru": "Создать новую версию", "tr": "Yeni sürüm oluştur"},
}

D["student_intake"] = {
    "Boş faylı endirin": {"en": "Download the empty file", "ru": "Скачать пустой файл", "tr": "Boş dosyayı indirin"},
    "Bu təşkilatda aktiv «müəllim» rolu yoxdur — əvvəlcə rol kataloqu qurulmalıdır.": {
        "en": "This organization has no active “teacher” role — the role catalog must be set up first.",
        "ru": "В этой организации нет активной роли «преподаватель» — сначала нужно настроить каталог ролей.",
        "tr": "Bu kurumda aktif «öğretim elemanı» rolü yok — önce rol kataloğu kurulmalıdır.",
    },
    "Fayl": {"en": "File", "ru": "Файл", "tr": "Dosya"},
    "Hesabları əlavə edin": {"en": "Add the accounts", "ru": "Добавьте аккаунты", "tr": "Hesapları ekleyin"},
    "Naməlum hesab növü.": {
        "en": "Unknown account type.",
        "ru": "Неизвестный тип аккаунта.",
        "tr": "Bilinmeyen hesap türü.",
    },
    "Nəticə": {"en": "Result", "ru": "Результат", "tr": "Sonuç"},
    "Qrup yaradıla bilmədi.": {
        "en": "The group could not be created.",
        "ru": "Не удалось создать группу.",
        "tr": "Grup oluşturulamadı.",
    },
    "Toplu tələbə əlavəsi üçün icazəniz yoxdur — bu bölmə yalnız `user.import` açarı olan rollar üçündür.": {
        "en": "You do not have permission for bulk student intake — this section is only for roles with the `user.import` key.",
        "ru": "У вас нет прав на массовое добавление студентов — этот раздел только для ролей с ключом `user.import`.",
        "tr": "Toplu öğrenci ekleme yetkiniz yok — bu bölüm yalnızca `user.import` anahtarı olan roller içindir.",
    },
    "Toplu tələbə əlavəsi üçün icazəniz yoxdur.": {
        "en": "You do not have permission for bulk student intake.",
        "ru": "У вас нет прав на массовое добавление студентов.",
        "tr": "Toplu öğrenci ekleme yetkiniz yok.",
    },
    "Toplu əlavənin mərhələləri": {
        "en": "Steps of the bulk intake",
        "ru": "Этапы массового добавления",
        "tr": "Toplu eklemenin aşamaları",
    },
    "Tələbə siyahısını yükləyin: sistem əvvəlcə QURU İCRA edir (heç nə yazılmır) və sətir-sətir nəyin yaranacağını göstərir; siz təsdiq edəndən sonra hesab + üzvlük + akademik qeyd yaradılır. Tələbə ilk girişdə e-poçtunu təsdiqləyib öz parolunu qoyur.": {
        "en": "Upload the student list: the system first performs a DRY RUN (nothing is written) and shows row by row what will be created; after you confirm, the account + membership + academic record are created. On first login the student verifies their email and sets their own password.",
        "ru": "Загрузите список студентов: система сначала выполняет ПРОБНЫЙ ПРОГОН (ничего не записывается) и построчно показывает, что будет создано; после вашего подтверждения создаются аккаунт + членство + академическая запись. При первом входе студент подтверждает e-mail и задаёт свой пароль.",
        "tr": "Öğrenci listesini yükleyin: sistem önce DENEME ÇALIŞTIRMASI yapar (hiçbir şey yazılmaz) ve satır satır neyin oluşturulacağını gösterir; siz onayladıktan sonra hesap + üyelik + akademik kayıt oluşturulur. Öğrenci ilk girişte e-postasını doğrulayıp kendi parolasını belirler.",
    },
    "Yükləyin və yoxlayın": {"en": "Upload and check", "ru": "Загрузите и проверьте", "tr": "Yükleyin ve kontrol edin"},
    "Şablon": {"en": "Template", "ru": "Шаблон", "tr": "Dosya şablonu"},
}

D["syllabus.document"] = {
    "Bal bölgüsü göstərilməyib": {
        "en": "Score distribution not specified",
        "ru": "Распределение баллов не указано",
        "tr": "Puan dağılımı belirtilmemiş",
    },
    "Fənnin məqsədi": {"en": "Subject objective", "ru": "Цель предмета", "tr": "Dersin amacı"},
    "Fənnin təsviri": {"en": "Subject description", "ru": "Описание предмета", "tr": "Dersin tanımı"},
    "Həftəlik mövzular": {"en": "Weekly topics", "ru": "Темы по неделям", "tr": "Haftalık konular"},
    "Qiymətləndirmə strukturu": {
        "en": "Assessment structure",
        "ru": "Структура оценивания",
        "tr": "Değerlendirme yapısı",
    },
    "Sərbəst iş": {"en": "Independent work", "ru": "Самостоятельная работа", "tr": "Bağımsız çalışma"},
    "Tədris metodları": {"en": "Teaching methods", "ru": "Методы обучения", "tr": "Öğretim yöntemleri"},
    "Təlim nəticələri": {"en": "Learning outcomes", "ru": "Результаты обучения", "tr": "Öğrenme çıktıları"},
    "bal": {"en": "points", "ru": "баллов", "tr": "puan"},
    "laboratoriya": {"en": "laboratory", "ru": "лабораторные", "tr": "laboratuvar"},
    "mühazirə": {"en": "lecture", "ru": "лекции", "tr": "ders anlatımı"},
    "saat": {"en": "hours", "ru": "часов", "tr": "ders saati"},
    "saat yazılmayıb": {"en": "hours not specified", "ru": "часы не указаны", "tr": "saat yazılmamış"},
    "seminar": {"en": "seminars", "ru": "семинары", "tr": "seminer"},
    "İmtahan sualları": {"en": "Exam questions", "ru": "Экзаменационные вопросы", "tr": "Sınav soruları"},
    "Ədəbiyyat": {"en": "Literature", "ru": "Литература", "tr": "Kaynaklar"},
    "— doldurulmayıb —": {"en": "— not filled in —", "ru": "— не заполнено —", "tr": "— doldurulmamış —"},
}

D["syllabus.notify"] = {
    "Sillabus düzəliş üçün qaytarıldı: %(reason)s": {
        "en": "Syllabus returned for revision: %(reason)s",
        "ru": "Силлабус возвращён на доработку: %(reason)s",
        "tr": "İzlence düzeltme için geri gönderildi: %(reason)s",
    },
    "Sillabus geri çağırıldı: %(subject)s": {
        "en": "Syllabus withdrawn: %(subject)s",
        "ru": "Силлабус отозван: %(subject)s",
        "tr": "İzlence geri çekildi: %(subject)s",
    },
    "Sillabus rədd edildi: %(reason)s": {
        "en": "Syllabus rejected: %(reason)s",
        "ru": "Силлабус отклонён: %(reason)s",
        "tr": "İzlence reddedildi: %(reason)s",
    },
    "Sillabus təsdiqləndi": {"en": "Syllabus approved", "ru": "Силлабус утверждён", "tr": "İzlence onaylandı"},
    "Sillabus təsdiqə göndərildi: %(subject)s": {
        "en": "Syllabus submitted for approval: %(subject)s",
        "ru": "Силлабус отправлен на утверждение: %(subject)s",
        "tr": "İzlence onaya gönderildi: %(subject)s",
    },
    "Sillabusunuz baxışa götürüldü": {
        "en": "Your syllabus has been taken under review",
        "ru": "Ваш силлабус взят на рассмотрение",
        "tr": "İzlenceniz incelemeye alındı",
    },
}

D["teacher_intake"] = {
    "7 simvol, A-Z0-9 (məcburi)": {
        "en": "7 characters, A-Z0-9 (required)",
        "ru": "7 символов, A-Z0-9 (обязательно)",
        "tr": "7 karakter, A-Z0-9 (zorunlu)",
    },
    "Ad": {"en": "First name", "ru": "Имя", "tr": "Adı"},
    "Adı və ya kodu (məcburi)": {
        "en": "Name or code (required)",
        "ru": "Название или код (обязательно)",
        "tr": "Adı veya kodu (zorunlu)",
    },
    "Adı və ya kodu (yalnız yoxlama)": {
        "en": "Name or code (check only)",
        "ru": "Название или код (только проверка)",
        "tr": "Adı veya kodu (yalnızca kontrol)",
    },
    "Ata adı": {"en": "Patronymic", "ru": "Отчество", "tr": "Baba adı"},
    "Bir faylda ən çox %d sətir ola bilər.": {
        "en": "A file can contain at most %d rows.",
        "ru": "В одном файле может быть не более %d строк.",
        "tr": "Bir dosyada en fazla %d satır olabilir.",
    },
    "Boş faylı endirin": {"en": "Download the empty file", "ru": "Скачать пустой файл", "tr": "Boş dosyayı indirin"},
    "Boş qala bilər": {"en": "May be left empty", "ru": "Может быть пустым", "tr": "Boş bırakılabilir"},
    "Boşdursa placeholder yazılır": {
        "en": "A placeholder is written if empty",
        "ru": "Если пусто — записывается заглушка",
        "tr": "Boşsa yer tutucu yazılır",
    },
    "Bu adla birdən çox kafedra var — kodla göstərin: %s": {
        "en": "More than one department has this name — specify by code: %s",
        "ru": "С таким названием несколько кафедр — укажите код: %s",
        "tr": "Bu adla birden çok bölüm var — kodla belirtin: %s",
    },
    "Bu işçi kodu artıq istifadə olunub — sətir ötürülür.": {
        "en": "This employee code is already in use — the row is skipped.",
        "ru": "Этот код сотрудника уже используется — строка пропускается.",
        "tr": "Bu personel kodu zaten kullanılmış — satır atlanıyor.",
    },
    "Cins": {"en": "Gender", "ru": "Пол", "tr": "Cinsiyet"},
    "Cins tanınmadı — «təyin edilməyib» qalır.": {
        "en": "Gender not recognized — remains “not set”.",
        "ru": "Пол не распознан — остаётся «не указан».",
        "tr": "Cinsiyet tanınmadı — «belirtilmemiş» kalıyor.",
    },
    "Doğum tarixi": {"en": "Date of birth", "ru": "Дата рождения", "tr": "Doğum tarihi"},
    "Doğum tarixi məntiqsizdir.": {
        "en": "The date of birth is implausible.",
        "ru": "Дата рождения неправдоподобна.",
        "tr": "Doğum tarihi mantıksız.",
    },
    "Doğum tarixi tanınmadı (gg.aa.iiii formatını işlədin).": {
        "en": "Date of birth not recognized (use the dd.mm.yyyy format).",
        "ru": "Дата рождения не распознана (используйте формат дд.мм.гггг).",
        "tr": "Doğum tarihi tanınmadı (gg.aa.yyyy biçimini kullanın).",
    },
    "E-poçt": {"en": "Email", "ru": "E-mail", "tr": "E-posta"},
    "E-poçt artıq istifadə olunur — placeholder yazılır.": {
        "en": "The email is already in use — a placeholder is written.",
        "ru": "E-mail уже используется — записывается заглушка.",
        "tr": "E-posta zaten kullanılıyor — yer tutucu yazılır.",
    },
    "E-poçt formatı yanlışdır.": {
        "en": "The email format is invalid.",
        "ru": "Неверный формат e-mail.",
        "tr": "E-posta biçimi hatalı.",
    },
    "E-poçt yoxdur — placeholder yazılır (ilk girişdə istifadəçi özü yazır).": {
        "en": "No email — a placeholder is written (the user enters it on first login).",
        "ru": "E-mail отсутствует — записывается заглушка (пользователь укажет его при первом входе).",
        "tr": "E-posta yok — yer tutucu yazılır (kullanıcı ilk girişte kendisi yazar).",
    },
    "Elmi ad": {"en": "Academic title", "ru": "Учёное звание", "tr": "Akademik unvan"},
    "Elmi dərəcə": {"en": "Academic degree", "ru": "Учёная степень", "tr": "Akademik derece"},
    "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
    "Fakültə kafedranın strukturuna uyğun gəlmir: %s": {
        "en": "The faculty does not match the department's structure: %s",
        "ru": "Факультет не соответствует структуре кафедры: %s",
        "tr": "Fakülte bölümün yapısıyla uyuşmuyor: %s",
    },
    "Fakültə tapılmadı: %s": {
        "en": "Faculty not found: %s",
        "ru": "Факультет не найден: %s",
        "tr": "Fakülte bulunamadı: %s",
    },
    "Fayl": {"en": "File", "ru": "Файл", "tr": "Dosya"},
    "FİN": {"en": "FIN", "ru": "FIN", "tr": "FİN kodu"},
    "Hesab yaradıldı.": {"en": "Account created.", "ru": "Аккаунт создан.", "tr": "Hesap oluşturuldu."},
    "Hesablar bu təşkilatda yaranır": {
        "en": "Accounts are created in this organization",
        "ru": "Аккаунты создаются в этой организации",
        "tr": "Hesaplar bu kurumda oluşturulur",
    },
    "Hesabları əlavə edin": {"en": "Add the accounts", "ru": "Добавьте аккаунты", "tr": "Hesapları ekleyin"},
    "Kafedra boşdur.": {"en": "Department is empty.", "ru": "Кафедра не указана.", "tr": "Bölüm boş."},
    "Kafedra tapılmadı: %s": {
        "en": "Department not found: %s",
        "ru": "Кафедра не найдена: %s",
        "tr": "Bölüm bulunamadı: %s",
    },
    "Müəllim siyahısını yükləyin: sistem əvvəlcə QURU İCRA edir (heç nə yazılmır) və sətir-sətir nəyin yaranacağını göstərir; siz təsdiq edəndən sonra hesab + kafedraya bağlı müəllim üzvlüyü yaradılır. Müəllim ilk girişdə e-poçtunu təsdiqləyib öz parolunu qoyur.": {
        "en": "Upload the teacher list: the system first performs a DRY RUN (nothing is written) and shows row by row what will be created; after you confirm, the account + department-bound teacher membership are created. On first login the teacher verifies their email and sets their own password.",
        "ru": "Загрузите список преподавателей: система сначала выполняет ПРОБНЫЙ ПРОГОН (ничего не записывается) и построчно показывает, что будет создано; после вашего подтверждения создаются аккаунт + членство преподавателя, привязанное к кафедре. При первом входе преподаватель подтверждает e-mail и задаёт свой пароль.",
        "tr": "Öğretim elemanı listesini yükleyin: sistem önce DENEME ÇALIŞTIRMASI yapar (hiçbir şey yazılmaz) ve satır satır neyin oluşturulacağını gösterir; siz onayladıktan sonra hesap + bölüme bağlı öğretim elemanı üyeliği oluşturulur. Öğretim elemanı ilk girişte e-postasını doğrulayıp kendi parolasını belirler.",
    },
    "Məcburi": {"en": "Required", "ru": "Обязательно", "tr": "Zorunlu"},
    "Məs.: baş müəllim, dosent": {
        "en": "E.g.: senior lecturer, associate professor",
        "ru": "Напр.: старший преподаватель, доцент",
        "tr": "Örn.: öğretim görevlisi, doçent",
    },
    "Məs.: dosent, professor": {
        "en": "E.g.: associate professor, professor",
        "ru": "Напр.: доцент, профессор",
        "tr": "Örn.: doçent, profesör",
    },
    "Məs.: fəlsəfə doktoru": {"en": "E.g.: PhD", "ru": "Напр.: доктор философии (PhD)", "tr": "Örn.: doktora (PhD)"},
    "Nəticə": {"en": "Result", "ru": "Результат", "tr": "Sonuç"},
    "Soyad": {"en": "Last name", "ru": "Фамилия", "tr": "Soyadı"},
    "Sətir yazılmadı: %s": {"en": "Row not written: %s", "ru": "Строка не записана: %s", "tr": "Satır yazılmadı: %s"},
    "Tabel nömrəsi — istifadəçi adı bundan qurulur": {
        "en": "Personnel number — the username is built from it",
        "ru": "Табельный номер — из него формируется имя пользователя",
        "tr": "Sicil numarası — kullanıcı adı bundan oluşturulur",
    },
    "Telefon": {"en": "Phone", "ru": "Телефон", "tr": "Telefon numarası"},
    "Toplu müəllim əlavəsi üçün icazəniz yoxdur — bu bölmə yalnız `user.import` açarı olan rollar üçündür.": {
        "en": "You do not have permission for bulk teacher intake — this section is only for roles with the `user.import` key.",
        "ru": "У вас нет прав на массовое добавление преподавателей — этот раздел только для ролей с ключом `user.import`.",
        "tr": "Toplu öğretim elemanı ekleme yetkiniz yok — bu bölüm yalnızca `user.import` anahtarı olan roller içindir.",
    },
    "Toplu müəllim əlavəsi üçün icazəniz yoxdur.": {
        "en": "You do not have permission for bulk teacher intake.",
        "ru": "У вас нет прав на массовое добавление преподавателей.",
        "tr": "Toplu öğretim elemanı ekleme yetkiniz yok.",
    },
    "Toplu əlavənin mərhələləri": {
        "en": "Steps of the bulk intake",
        "ru": "Этапы массового добавления",
        "tr": "Toplu eklemenin aşamaları",
    },
    "Vəzifə": {"en": "Position", "ru": "Должность", "tr": "Unvan"},
    "Yaradılacaq.": {"en": "Will be created.", "ru": "Будет создан.", "tr": "Oluşturulacak."},
    "Yükləyin və yoxlayın": {"en": "Upload and check", "ru": "Загрузите и проверьте", "tr": "Yükleyin ve kontrol edin"},
    "gg.aa.iiii və ya iiii-aa-gg": {
        "en": "dd.mm.yyyy or yyyy-mm-dd",
        "ru": "дд.мм.гггг или гггг-мм-дд",
        "tr": "gg.aa.yyyy veya yyyy-aa-gg",
    },
    "kişi / qadın": {"en": "male / female", "ru": "мужской / женский", "tr": "erkek / kadın"},
    "sahə uzunluğu həddi keçildi": {
        "en": "field length limit exceeded",
        "ru": "превышен лимит длины поля",
        "tr": "alan uzunluğu sınırı aşıldı",
    },
    "Ünvan": {"en": "Address", "ru": "Адрес", "tr": "Adres"},
    "İşçi kodu": {"en": "Employee code", "ru": "Код сотрудника", "tr": "Personel kodu"},
    "Şablon": {"en": "Template", "ru": "Шаблон", "tr": "Dosya şablonu"},
}

# ── djangojs (F7): dərs yükü paneli — workload_distribution*.js / workload_my.js ──
# JS kataloqunda msgctxt yoxdur (layihə konvensiyası: `gettext("AZ mətn")`).
ENTRIES["djangojs"][""] = {
    "Əməliyyat alınmadı.": {
        "en": "The operation failed.",
        "ru": "Операция не выполнена.",
        "tr": "İşlem gerçekleştirilemedi.",
    },
    "Əvvəlcə tapşırıq yaradılmalıdır.": {
        "en": "A task must be created first.",
        "ru": "Сначала нужно создать задание.",
        "tr": "Önce görev oluşturulmalıdır.",
    },
    "Sətir silinsin?": {"en": "Delete this row?", "ru": "Удалить строку?", "tr": "Satır silinsin mi?"},
    "Bölgü silinsin?": {"en": "Delete this allocation?", "ru": "Удалить распределение?", "tr": "Dağıtım silinsin mi?"},
    "Bölgü təsdiqləndi. Jurnal açılışı: %(created)s yeni, %(updated)s yeniləndi. Bildiriş: %(notified)s": {
        "en": "Allocation confirmed. Journal offerings: %(created)s new, %(updated)s updated. Notified: %(notified)s",
        "ru": "Распределение подтверждено. Открытия журнала: новых %(created)s, обновлено %(updated)s. Уведомлено: %(notified)s",
        "tr": "Dağıtım onaylandı. Defter açılışı: %(created)s yeni, %(updated)s güncellendi. Bildirim: %(notified)s",
    },
    "Bu kafedranın ixtisasları üçün aktiv tədris planı sətri tapılmadı.": {
        "en": "No active curriculum plan rows were found for this department's specialties.",
        "ru": "Для специальностей этой кафедры не найдено активных строк учебного плана.",
        "tr": "Bu bölümün programları için aktif öğretim planı satırı bulunamadı.",
    },
    "Plandan %(count)s təklif tapıldı; birincisi doldurulub. Saatlar tədris planında saxlanmır — əl ilə yazın (təklif: %(hours)s saat).": {
        "en": "%(count)s suggestions found in the plan; the first one has been filled in. Hours are not stored in the curriculum plan — enter them manually (suggested: %(hours)s hours).",
        "ru": "В плане найдено предложений: %(count)s; первое подставлено. Часы в учебном плане не хранятся — введите вручную (предложение: %(hours)s ч.).",
        "tr": "Planda %(count)s öneri bulundu; ilki dolduruldu. Saatler öğretim planında saklanmaz — elle yazın (öneri: %(hours)s saat).",
    },
    "Qalıq: %(remaining)s / %(total)s saat": {
        "en": "Remaining: %(remaining)s / %(total)s hours",
        "ru": "Остаток: %(remaining)s / %(total)s ч.",
        "tr": "Kalan: %(remaining)s / %(total)s saat",
    },
    "Vakant (müəllim təyin edilməyib)": {
        "en": "Vacant (no teacher assigned)",
        "ru": "Вакансия (преподаватель не назначен)",
        "tr": "Boş (öğretim elemanı atanmamış)",
    },
    "(kafedraya bağlanmamış)": {
        "en": "(not attached to the department)",
        "ru": "(не привязан к кафедре)",
        "tr": "(bölüme bağlı değil)",
    },
    "Bu sətirdə bölünəcək saat yoxdur.": {
        "en": "There are no hours to allocate in this row.",
        "ru": "В этой строке нет часов для распределения.",
        "tr": "Bu satırda dağıtılacak saat yok.",
    },
    "Bölüşdür": {"en": "Allocate", "ru": "Распределить", "tr": "Dağıt"},
    "Bölgünü sil": {"en": "Delete allocation", "ru": "Удалить распределение", "tr": "Dağıtımı sil"},
    "Hələ bölgü yoxdur.": {"en": "No allocations yet.", "ru": "Распределений пока нет.", "tr": "Henüz dağıtım yok."},
    "Jurnal açılışı": {"en": "Journal offerings", "ru": "Открытий журнала", "tr": "Defter açılışı"},
    "Yarımçıq sətir": {"en": "Incomplete rows", "ru": "Незавершённых строк", "tr": "Eksik satır"},
    "Aç": {"en": "Open", "ru": "Открыть", "tr": "Görüntüle"},
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _block_key(ctx, msgid):
    head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
    return head + f'msgid "{esc(msgid)}"\n'


def fill(lang, domain):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        print(f"{domain}/{lang}: kataloq yoxdur — ötürüldü")
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            key = _block_key(ctx, msgid)
            # Kontekstsiz giriş üçün `msgctxt`-li təsadüfi uyğunluğu istisna et:
            # sətir əvvəlində `msgid "…"` axtarılır.
            if ("\n" + key) in ("\n" + text):
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(key + f'msgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{domain}/{lang}: +{added} entry")


if __name__ == "__main__":
    for domain in ("django", "djangojs"):
        for locale in LOCALES:
            fill(locale, domain)
