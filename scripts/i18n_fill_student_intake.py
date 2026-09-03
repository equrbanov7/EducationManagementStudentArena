#!/usr/bin/env python3
"""EMSArena i18n — «Tələbə idxalı» bölməsinin sətirləri (4 dil). İdempotent.

Yeni bölmənin (student-intake) UI mətnləri, `user.import` icazə etiketi, sidebar
adı, fayl/validasiya xəta mesajları və nəticə cədvəlinin başlıqları doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur (bax i18n_fill_schedule_manage.py).

İstifadə:  python scripts/i18n_fill_student_intake.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_C = "student_intake"

ENTRIES = {
    # ── İcazə etiketi (permission-editor + «səlahiyyətləriniz» paneli) ───────
    "organizations.permission.label": {
        "Tələbə idxalı (siyahıdan toplu hesab yaratmaq)": {
            "en": "Student intake (bulk account creation from a list)",
            "ru": "Импорт студентов (массовое создание учётных записей из списка)",
            "tr": "Öğrenci alımı (listeden toplu hesap oluşturma)",
        },
    },
    # ── Sidebar ─────────────────────────────────────────────────────────────
    "profile.sidebar": {
        "Tələbə idxalı": {
            "en": "Student intake",
            "ru": "Импорт студентов",
            "tr": "Öğrenci alımı",
        },
    },
    # ── Bölmənin öz mətnləri ────────────────────────────────────────────────
    _C: {
        # Fayl qatı
        "Faylın başlıq sətrində məcburi sütunlar tapılmadı: %s": {
            "en": "The file's header row is missing required columns: %s",
            "ru": "В строке заголовков файла нет обязательных столбцов: %s",
            "tr": "Dosyanın başlık satırında zorunlu sütunlar yok: %s",
        },
        "Bu serverdə .xlsx oxunmur — faylı CSV kimi yadda saxlayıb yenidən yükləyin.": {
            "en": "This server cannot read .xlsx — save the file as CSV and upload it again.",
            "ru": "Этот сервер не читает .xlsx — сохраните файл как CSV и загрузите снова.",
            "tr": "Bu sunucu .xlsx okuyamıyor — dosyayı CSV olarak kaydedip yeniden yükleyin.",
        },
        "Fayl oxunmadı — zədəli və ya dəstəklənməyən Excel faylıdır.": {
            "en": "The file could not be read — it is damaged or an unsupported Excel file.",
            "ru": "Файл не прочитан — он повреждён или это неподдерживаемый файл Excel.",
            "tr": "Dosya okunamadı — bozuk veya desteklenmeyen bir Excel dosyası.",
        },
        "Fayl boşdur — başlıq sətri tapılmadı.": {
            "en": "The file is empty — no header row was found.",
            "ru": "Файл пуст — строка заголовков не найдена.",
            "tr": "Dosya boş — başlık satırı bulunamadı.",
        },
        "Fayl oxunmadı — kodlaşdırma tanınmadı.": {
            "en": "The file could not be read — the encoding was not recognised.",
            "ru": "Файл не прочитан — кодировка не распознана.",
            "tr": "Dosya okunamadı — kodlama tanınmadı.",
        },
        "Fayl seçilməyib.": {"en": "No file selected.", "ru": "Файл не выбран.", "tr": "Dosya seçilmedi."},
        "Fayl çox böyükdür (maksimum 5 MB).": {
            "en": "The file is too large (maximum 5 MB).",
            "ru": "Файл слишком большой (максимум 5 МБ).",
            "tr": "Dosya çok büyük (en fazla 5 MB).",
        },
        "Yalnız .xlsx və ya .csv faylı qəbul olunur.": {
            "en": "Only .xlsx or .csv files are accepted.",
            "ru": "Принимаются только файлы .xlsx или .csv.",
            "tr": "Yalnızca .xlsx veya .csv dosyaları kabul edilir.",
        },
        "Fayl boşdur.": {"en": "The file is empty.", "ru": "Файл пуст.", "tr": "Dosya boş."},
        "Faylda tələbə sətri tapılmadı.": {
            "en": "No student rows were found in the file.",
            "ru": "В файле не найдено ни одной строки со студентом.",
            "tr": "Dosyada öğrenci satırı bulunamadı.",
        },
        # Sütun başlıqları
        "FİN": {"en": "PIN (FİN)", "ru": "ПИН (FİN)", "tr": "Kimlik No (FİN)"},
        "Ad": {"en": "First name", "ru": "Имя", "tr": "Ad"},
        "Soyad": {"en": "Last name", "ru": "Фамилия", "tr": "Soyad"},
        "Ata adı": {"en": "Patronymic", "ru": "Отчество", "tr": "Baba adı"},
        "Doğum tarixi": {"en": "Date of birth", "ru": "Дата рождения", "tr": "Doğum tarihi"},
        "Cins": {"en": "Gender", "ru": "Пол", "tr": "Cinsiyet"},
        "E-poçt": {"en": "Email", "ru": "Эл. почта", "tr": "E-posta"},
        "Telefon": {"en": "Phone", "ru": "Телефон", "tr": "Telefon"},
        "Tələbə kodu": {"en": "Student code", "ru": "Код студента", "tr": "Öğrenci kodu"},
        "Fakültə": {"en": "Faculty", "ru": "Факультет", "tr": "Fakülte"},
        "İxtisas": {"en": "Speciality", "ru": "Специальность", "tr": "Bölüm"},
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
        "Qəbul ili": {"en": "Admission year", "ru": "Год поступления", "tr": "Kayıt yılı"},
        "Kurs": {"en": "Year of study", "ru": "Курс", "tr": "Sınıf"},
        "Dil bölməsi": {"en": "Language sector", "ru": "Языковой сектор", "tr": "Dil bölümü"},
        "Təhsil səviyyəsi": {"en": "Degree level", "ru": "Уровень образования", "tr": "Öğrenim düzeyi"},
        # Sütun izahları
        "7 simvol, A-Z0-9 (məcburi)": {
            "en": "7 characters, A-Z0-9 (required)",
            "ru": "7 символов, A-Z0-9 (обязательно)",
            "tr": "7 karakter, A-Z0-9 (zorunlu)",
        },
        "Məcburi": {"en": "Required", "ru": "Обязательно", "tr": "Zorunlu"},
        "Boş qala bilər": {"en": "May be left empty", "ru": "Может быть пустым", "tr": "Boş bırakılabilir"},
        "gg.aa.iiii və ya iiii-aa-gg": {
            "en": "dd.mm.yyyy or yyyy-mm-dd",
            "ru": "дд.мм.гггг или гггг-мм-дд",
            "tr": "gg.aa.yyyy veya yyyy-aa-gg",
        },
        "kişi / qadın": {"en": "male / female", "ru": "мужской / женский", "tr": "erkek / kadın"},
        "Boşdursa placeholder yazılır": {
            "en": "A placeholder is written when empty",
            "ru": "Если пусто, записывается заглушка",
            "tr": "Boşsa yer tutucu yazılır",
        },
        "İstifadəçi adı bundan qurulur": {
            "en": "The username is built from this",
            "ru": "Из него формируется имя пользователя",
            "tr": "Kullanıcı adı bundan oluşturulur",
        },
        "Adı və ya kodu (yoxlama üçün)": {
            "en": "Name or code (for verification)",
            "ru": "Название или код (для проверки)",
            "tr": "Adı veya kodu (doğrulama için)",
        },
        "Adı və ya kodu (məcburi)": {
            "en": "Name or code (required)",
            "ru": "Название или код (обязательно)",
            "tr": "Adı veya kodu (zorunlu)",
        },
        "Məsələn 2025 (məcburi)": {
            "en": "For example 2025 (required)",
            "ru": "Например 2025 (обязательно)",
            "tr": "Örneğin 2025 (zorunlu)",
        },
        "1–6 (yalnız yoxlama)": {
            "en": "1–6 (verification only)",
            "ru": "1–6 (только для проверки)",
            "tr": "1–6 (yalnızca doğrulama)",
        },
        "az / en / ru (yalnız yoxlama)": {
            "en": "az / en / ru (verification only)",
            "ru": "az / en / ru (только для проверки)",
            "tr": "az / en / ru (yalnızca doğrulama)",
        },
        "bakalavr / magistr (yoxlama)": {
            "en": "bachelor / master (verification)",
            "ru": "бакалавр / магистр (проверка)",
            "tr": "lisans / yüksek lisans (doğrulama)",
        },
        # Sətir validasiyası
        "FİN boşdur.": {"en": "The PIN is empty.", "ru": "ПИН пуст.", "tr": "Kimlik No boş."},
        "FİN 7 simvolluq [A-Z0-9] formatında olmalıdır.": {
            "en": "The PIN must be 7 characters in [A-Z0-9] format.",
            "ru": "ПИН должен состоять из 7 символов формата [A-Z0-9].",
            "tr": "Kimlik No 7 karakterli [A-Z0-9] biçiminde olmalıdır.",
        },
        "Ad və soyad məcburidir.": {
            "en": "First name and last name are required.",
            "ru": "Имя и фамилия обязательны.",
            "tr": "Ad ve soyad zorunludur.",
        },
        "Bu FİN faylda təkrarlanır.": {
            "en": "This PIN is repeated in the file.",
            "ru": "Этот ПИН повторяется в файле.",
            "tr": "Bu Kimlik No dosyada tekrarlanıyor.",
        },
        "Bu FİN artıq sistemdə var — sətir ötürülür.": {
            "en": "This PIN already exists in the system — the row is skipped.",
            "ru": "Этот ПИН уже есть в системе — строка пропускается.",
            "tr": "Bu Kimlik No sistemde zaten var — satır atlanıyor.",
        },
        "Qrup tapılmadı: %s": {"en": "Group not found: %s", "ru": "Группа не найдена: %s", "tr": "Grup bulunamadı: %s"},
        "(boş)": {"en": "(empty)", "ru": "(пусто)", "tr": "(boş)"},
        "Bu adla birdən çox qrup var — kodla göstərin: %s": {
            "en": "More than one group has this name — specify it by code: %s",
            "ru": "Групп с таким названием несколько — укажите код: %s",
            "tr": "Bu adda birden fazla grup var — kodla belirtin: %s",
        },
        "%(label)s tapılmadı: %(value)s": {
            "en": "%(label)s not found: %(value)s",
            "ru": "%(label)s не найдено: %(value)s",
            "tr": "%(label)s bulunamadı: %(value)s",
        },
        "%(label)s qrupun strukturuna uyğun gəlmir: %(value)s": {
            "en": "%(label)s does not match the group's structure: %(value)s",
            "ru": "%(label)s не соответствует структуре группы: %(value)s",
            "tr": "%(label)s grubun yapısına uymuyor: %(value)s",
        },
        "Bu qrupun ixtisas proqramı (Program) tapılmadı — əvvəlcə struktur qurulmalıdır.": {
            "en": "No academic programme was found for this group — the structure must be set up first.",
            "ru": "Для этой группы не найдена программа — сначала нужно выстроить структуру.",
            "tr": "Bu grup için akademik program bulunamadı — önce yapı kurulmalıdır.",
        },
        "Təhsil səviyyəsi proqramla üst-üstə düşmür — proqramın səviyyəsi tətbiq olunur.": {
            "en": "The degree level does not match the programme — the programme's level is applied.",
            "ru": "Уровень образования не совпадает с программой — применяется уровень программы.",
            "tr": "Öğrenim düzeyi programla uyuşmuyor — programın düzeyi uygulanır.",
        },
        "Qəbul ili rəqəm olmalıdır.": {
            "en": "The admission year must be a number.",
            "ru": "Год поступления должен быть числом.",
            "tr": "Kayıt yılı sayı olmalıdır.",
        },
        "Qəbul ili 1950–%d aralığında olmalıdır.": {
            "en": "The admission year must be between 1950 and %d.",
            "ru": "Год поступления должен быть между 1950 и %d.",
            "tr": "Kayıt yılı 1950 ile %d arasında olmalıdır.",
        },
        "Doğum tarixi tanınmadı (gg.aa.iiii formatını işlədin).": {
            "en": "The date of birth was not recognised (use the dd.mm.yyyy format).",
            "ru": "Дата рождения не распознана (используйте формат дд.мм.гггг).",
            "tr": "Doğum tarihi tanınmadı (gg.aa.yyyy biçimini kullanın).",
        },
        "Doğum tarixi məntiqsizdir.": {
            "en": "The date of birth is implausible.",
            "ru": "Дата рождения неправдоподобна.",
            "tr": "Doğum tarihi mantıksız.",
        },
        "Cins tanınmadı — «təyin edilməyib» qalır.": {
            "en": "The gender was not recognised — it stays “unspecified”.",
            "ru": "Пол не распознан — остаётся «не указан».",
            "tr": "Cinsiyet tanınmadı — “belirtilmemiş” kalıyor.",
        },
        "Bu qəbul ili üçün kurikulum yoxdur — tətbiqdə boş kurikulum yaradılacaq.": {
            "en": "There is no curriculum for this admission year — an empty one will be created on apply.",
            "ru": "Для этого года поступления нет учебного плана — при применении будет создан пустой.",
            "tr": "Bu kayıt yılı için müfredat yok — uygulamada boş bir müfredat oluşturulacak.",
        },
        "Bu tələbə kodu artıq istifadə olunub — sətir ötürülür.": {
            "en": "This student code is already in use — the row is skipped.",
            "ru": "Этот код студента уже используется — строка пропускается.",
            "tr": "Bu öğrenci kodu zaten kullanılıyor — satır atlanıyor.",
        },
        "E-poçt yoxdur — placeholder yazılır (ilk girişdə istifadəçi özü yazır).": {
            "en": "There is no email — a placeholder is written (the user enters their own at first login).",
            "ru": "Эл. почты нет — записывается заглушка (пользователь укажет свою при первом входе).",
            "tr": "E-posta yok — yer tutucu yazılır (kullanıcı ilk girişte kendisi girer).",
        },
        "E-poçt formatı yanlışdır.": {
            "en": "The email format is invalid.",
            "ru": "Неверный формат эл. почты.",
            "tr": "E-posta biçimi geçersiz.",
        },
        "E-poçt artıq istifadə olunur — placeholder yazılır.": {
            "en": "The email is already in use — a placeholder is written.",
            "ru": "Эл. почта уже используется — записывается заглушка.",
            "tr": "E-posta zaten kullanılıyor — yer tutucu yazılır.",
        },
        "Yaradılacaq.": {"en": "Will be created.", "ru": "Будет создан.", "tr": "Oluşturulacak."},
        # Tətbiq qatı
        "Bu təşkilatda aktiv «student» rolu yoxdur — əvvəlcə rol kataloqu qurulmalıdır.": {
            "en": "This organization has no active “student” role — the role catalogue must be set up first.",
            "ru": "В этой организации нет активной роли «student» — сначала нужно настроить каталог ролей.",
            "tr": "Bu kurumda etkin “student” rolü yok — önce rol kataloğu kurulmalıdır.",
        },
        "Sətir yazılmadı: %s": {
            "en": "The row was not written: %s",
            "ru": "Строка не записана: %s",
            "tr": "Satır yazılmadı: %s",
        },
        "Hesab yaradıldı.": {
            "en": "The account was created.",
            "ru": "Учётная запись создана.",
            "tr": "Hesap oluşturuldu.",
        },
        # İcazə
        "Tələbə idxalı üçün icazəniz yoxdur.": {
            "en": "You do not have permission for student intake.",
            "ru": "У вас нет прав на импорт студентов.",
            "tr": "Öğrenci alımı için izniniz yok.",
        },
        "Tələbə idxalı üçün icazəniz yoxdur — bu bölmə yalnız `user.import` açarı olan rollar üçündür.": {
            "en": "You do not have permission for student intake — this section is only for roles holding `user.import`.",
            "ru": "У вас нет прав на импорт студентов — раздел доступен только ролям с ключом `user.import`.",
            "tr": "Öğrenci alımı için izniniz yok — bu bölüm yalnızca `user.import` anahtarına sahip roller içindir.",
        },
        # Panel
        "Tələbə idxalı": {"en": "Student intake", "ru": "Импорт студентов", "tr": "Öğrenci alımı"},
        (
            "Qəbul siyahısını yükləyin: sistem əvvəlcə QURU İCRA edir (heç nə yazılmır), sətir-sətir nəyin "
            "yaranacağını göstərir, siz təsdiq edəndən sonra hesab + üzvlük + akademik qeyd yaradılır. Tələbə "
            "ilk girişdə e-poçtunu təsdiqləyib öz parolunu qoyur."
        ): {
            "en": (
                "Upload the admission list: the system first does a DRY RUN (nothing is written), shows row by "
                "row what will be created, and only after your confirmation creates the account, membership and "
                "academic record. At first login the student verifies their email and sets their own password."
            ),
            "ru": (
                "Загрузите список зачисления: система сначала выполняет СУХОЙ ПРОГОН (ничего не записывается), "
                "построчно показывает, что будет создано, и только после подтверждения создаёт учётную запись, "
                "членство и академическую запись. При первом входе студент подтверждает почту и задаёт пароль."
            ),
            "tr": (
                "Kayıt listesini yükleyin: sistem önce KURU ÇALIŞMA yapar (hiçbir şey yazılmaz), satır satır "
                "nelerin oluşacağını gösterir ve ancak onayınızdan sonra hesap, üyelik ve akademik kaydı "
                "oluşturur. Öğrenci ilk girişte e-postasını doğrulayıp kendi parolasını belirler."
            ),
        },
        "Hesablar bu təşkilatda yaranır": {
            "en": "Accounts are created in this organization",
            "ru": "Учётные записи создаются в этой организации",
            "tr": "Hesaplar bu kurumda oluşturulur",
        },
        "Şablonu endirin": {"en": "Download the template", "ru": "Скачайте шаблон", "tr": "Şablonu indirin"},
        (
            "Sütunların sırası sərbəstdir — başlıq adına görə tanınır. Bir faylda ən çox %(limit)s sətir, "
            "ölçü limiti %(size)s MB."
        ): {
            "en": (
                "The column order is free — columns are recognised by their header. At most %(limit)s rows per "
                "file, size limit %(size)s MB."
            ),
            "ru": (
                "Порядок столбцов свободный — они распознаются по заголовку. Не более %(limit)s строк в файле, "
                "лимит размера %(size)s МБ."
            ),
            "tr": (
                "Sütun sırası serbesttir — başlığa göre tanınır. Dosya başına en fazla %(limit)s satır, boyut "
                "sınırı %(size)s MB."
            ),
        },
        "Boş şablonu endir": {
            "en": "Download the empty template",
            "ru": "Скачать пустой шаблон",
            "tr": "Boş şablonu indir",
        },
        "Sütunlar": {"en": "Columns", "ru": "Столбцы", "tr": "Sütunlar"},
        "Sütun": {"en": "Column", "ru": "Столбец", "tr": "Sütun"},
        "İzah": {"en": "Note", "ru": "Пояснение", "tr": "Açıklama"},
        "Faylı yükləyin": {"en": "Upload the file", "ru": "Загрузите файл", "tr": "Dosyayı yükleyin"},
        "Fayl seçilməyib": {"en": "No file selected", "ru": "Файл не выбран", "tr": "Dosya seçilmedi"},
        "Yoxla (quru icra)": {
            "en": "Check (dry run)",
            "ru": "Проверить (сухой прогон)",
            "tr": "Kontrol et (kuru çalışma)",
        },
        "Sətir": {"en": "Row", "ru": "Строка", "tr": "Satır"},
        "Vəziyyət": {"en": "Status", "ru": "Статус", "tr": "Durum"},
        "Ad Soyad": {"en": "Full name", "ru": "ФИО", "tr": "Ad Soyad"},
        "İstifadəçi adı": {"en": "Username", "ru": "Имя пользователя", "tr": "Kullanıcı adı"},
        "Tətbiq et": {"en": "Apply", "ru": "Применить", "tr": "Uygula"},
        "Parolları CSV kimi endir": {
            "en": "Download the passwords as CSV",
            "ru": "Скачать пароли в CSV",
            "tr": "Parolaları CSV olarak indir",
        },
        (
            "Birdəfəlik parollar YALNIZ indi görünür — nə bazada, nə də audit jurnalında saxlanılmır. CSV-ni "
            "endirib tələbələrə çatdırın; ilk girişdə hər tələbə e-poçt təsdiqi (OTP) və yeni parol tələb "
            "olunacaq."
        ): {
            "en": (
                "The one-time passwords are visible ONLY now — they are stored neither in the database nor in "
                "the audit log. Download the CSV and hand it to the students; at first login every student is "
                "asked for email verification (OTP) and a new password."
            ),
            "ru": (
                "Одноразовые пароли видны ТОЛЬКО сейчас — они не хранятся ни в базе, ни в журнале аудита. "
                "Скачайте CSV и передайте студентам; при первом входе у каждого запрашивается подтверждение "
                "почты (OTP) и новый пароль."
            ),
            "tr": (
                "Tek kullanımlık parolalar YALNIZCA şimdi görünür — ne veritabanında ne de denetim günlüğünde "
                "saklanır. CSV'yi indirip öğrencilere iletin; ilk girişte her öğrenciden e-posta doğrulaması "
                "(OTP) ve yeni parola istenir."
            ),
        },
        # JS mətnləri
        "Əvvəlcə fayl seçin.": {
            "en": "Select a file first.",
            "ru": "Сначала выберите файл.",
            "tr": "Önce bir dosya seçin.",
        },
        "Əməliyyat alınmadı. Yenidən cəhd edin.": {
            "en": "The operation failed. Try again.",
            "ru": "Операция не удалась. Попробуйте снова.",
            "tr": "İşlem başarısız oldu. Yeniden deneyin.",
        },
        "Quru icra nəticəsi (heç nə yazılmadı)": {
            "en": "Dry-run result (nothing was written)",
            "ru": "Результат сухого прогона (ничего не записано)",
            "tr": "Kuru çalışma sonucu (hiçbir şey yazılmadı)",
        },
        "Tətbiq nəticəsi": {"en": "Apply result", "ru": "Результат применения", "tr": "Uygulama sonucu"},
        "Seçilmiş sətirlər üçün hesab yaradılacaq. Davam edilsin?": {
            "en": "Accounts will be created for the selected rows. Continue?",
            "ru": "Для выбранных строк будут созданы учётные записи. Продолжить?",
            "tr": "Seçili satırlar için hesap oluşturulacak. Devam edilsin mi?",
        },
        "Yaradılacaq": {"en": "Will be created", "ru": "Будет создан", "tr": "Oluşturulacak"},
        "Yaradıldı": {"en": "Created", "ru": "Создан", "tr": "Oluşturuldu"},
        "Ötürüldü": {"en": "Skipped", "ru": "Пропущено", "tr": "Atlandı"},
        "Xəta": {"en": "Error", "ru": "Ошибка", "tr": "Hata"},
        "Cəmi": {"en": "Total", "ru": "Всего", "tr": "Toplam"},
        "Emal olunur…": {"en": "Processing…", "ru": "Обработка…", "tr": "İşleniyor…"},
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
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
