#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-05 QA düzəlişlərinin istifadəçi mətnləri. İdempotent.

Jurnal (registrar/views.py — kontekstsiz `gettext`) və sillabus (`accounts.syllabus`
kontekstli TransitionDenied etiketləri) üçün 4 dil doldurulur.
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
İstifadə:  python scripts/i18n_fill_qa_2026_09_05.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    None: {
        "Akademik qeydiniz hələ yaradılmayıb.": {
            "en": "Your academic record has not been created yet.",
            "ru": "Ваша академическая запись ещё не создана.",
            "tr": "Akademik kaydınız henüz oluşturulmamış.",
        },
        "Jurnal qrupa yazılışdan sonra görünür — tələbə xidmətlərinə müraciət edin.": {
            "en": "The journal appears after enrolment in a group — contact student services.",
            "ru": "Журнал появится после зачисления в группу — обратитесь в студенческую службу.",
            "tr": "Yoklama defteri gruba kayıttan sonra görünür — öğrenci hizmetlerine başvurun.",
        },
        "Seçilmiş müəllim bu təşkilatın tədris heyətində deyil.": {
            "en": "The selected teacher is not on this organisation's teaching staff.",
            "ru": "Выбранный преподаватель не входит в преподавательский состав организации.",
            "tr": "Seçilen öğretim elemanı bu kurumun öğretim kadrosunda değil.",
        },
        "Jurnal bağlıdır — dəyişikliklər yazılmadı.": {
            "en": "The journal is closed — the changes were not saved.",
            "ru": "Журнал закрыт — изменения не сохранены.",
            "tr": "Yoklama defteri kapalı — değişiklikler kaydedilmedi.",
        },
        "Standart format": {
            "en": "Default format",
            "ru": "Формат по умолчанию",
            "tr": "Varsayılan biçim",
        },
        "Standart sual formatı (sual əlavə edərkən dəyişə bilərsiniz).": {
            "en": "Default question format (you can change it when adding a question).",
            "ru": "Формат вопроса по умолчанию (можно изменить при добавлении вопроса).",
            "tr": "Varsayılan soru biçimi (soru eklerken değiştirebilirsiniz).",
        },
        "Dərs tipi düzgün seçilməyib.": {
            "en": "The lesson type is not selected correctly.",
            "ru": "Тип занятия выбран неверно.",
            "tr": "Ders türü doğru seçilmemiş.",
        },
        "Dərs saatı müsbət tam ədəd olmalıdır.": {
            "en": "The lesson hours must be a positive whole number.",
            "ru": "Количество часов занятия должно быть целым положительным числом.",
            "tr": "Ders saati pozitif bir tam sayı olmalıdır.",
        },
        "%(n)s xana yazılmadı — bal 0–10 aralığında TAM ədəd olmalıdır.": {
            "en": "%(n)s cell(s) were not saved — the score must be a whole number between 0 and 10.",
            "ru": "%(n)s ячеек не сохранено — балл должен быть целым числом от 0 до 10.",
            "tr": "%(n)s hücre kaydedilmedi — puan 0–10 arasında tam sayı olmalıdır.",
        },
        "İmtahan/təkrar balını yalnız İmtahan Mərkəzi yaza bilər — bu sahələr yazılmadı.": {
            "en": "Only the Examination Centre may record exam/resit scores — those fields were not saved.",
            "ru": "Экзаменационные/пересдачные баллы вносит только Экзаменационный центр — эти поля не сохранены.",
            "tr": "Sınav/bütünleme puanını yalnızca Sınav Merkezi girebilir — bu alanlar kaydedilmedi.",
        },
        "Heç bir xana yazılmadı — dərs günü qaydası və ya xana kilidi buna imkan vermədi.": {
            "en": "No cell was saved — the lesson-day rule or a cell lock prevented it.",
            "ru": "Ни одна ячейка не сохранена — помешало правило дня занятия или блокировка ячейки.",
            "tr": "Hiçbir hücre kaydedilmedi — ders günü kuralı veya hücre kilidi buna izin vermedi.",
        },
    },
    "roles.display_name": {
        "rim_staff": {
            "en": "RİM staff",
            "ru": "Сотрудник Центра цифрового развития (RİM)",
            "tr": "Dijital Gelişim Merkezi (RİM) çalışanı",
        },
    },
    "ui.confirm_modal": {
        "Bağla": {
            "en": "Close",
            "ru": "Закрыть",
            "tr": "Kapat",
        },
        "Ləğv et": {
            "en": "Cancel",
            "ru": "Отмена",
            "tr": "Vazgeç",
        },
        "Təsdiqlə": {
            "en": "Confirm",
            "ru": "Подтвердить",
            "tr": "Onayla",
        },
    },
    "accounts.people": {
        "səlahiyyət": {
            "en": "permissions",
            "ru": "прав",
            "tr": "yetki",
        },
    },
    "registrar.journal": {
        "Sonrakı dərslər": {
            "en": "Later lessons",
            "ru": "Следующие занятия",
            "tr": "Sonraki dersler",
        },
        "Əvvəlki dərslər": {
            "en": "Earlier lessons",
            "ru": "Предыдущие занятия",
            "tr": "Önceki dersler",
        },
        "Dərs sütunları": {
            "en": "Lesson columns",
            "ru": "Столбцы занятий",
            "tr": "Ders sütunları",
        },
        "Hamısını göstər": {
            "en": "Show all",
            "ru": "Показать все",
            "tr": "Tümünü göster",
        },
        "Son 20 dərs": {
            "en": "Last 20 lessons",
            "ru": "Последние 20 занятий",
            "tr": "Son 20 ders",
        },
        "%(first)s–%(last)s / %(total)s dərs": {
            "en": "%(first)s–%(last)s of %(total)s lessons",
            "ru": "%(first)s–%(last)s из %(total)s занятий",
            "tr": "%(total)s dersten %(first)s–%(last)s",
        },
        "Bütün %(total)s dərs göstərilir": {
            "en": "Showing all %(total)s lessons",
            "ru": "Показаны все %(total)s занятий",
            "tr": "%(total)s dersin tamamı gösteriliyor",
        },
    },
    "accounts.manage_roles.message": {
        "missing_member_management_permission": {
            "en": "You need the `role.assign` or `org.manage_members` permission for this action.",
            "ru": "Для этого действия требуется право `role.assign` или `org.manage_members`.",
            "tr": "Bu işlem için `role.assign` veya `org.manage_members` izni gerekir.",
        },
        "target_outside_structure_scope": {
            "en": "This user is outside your structural scope.",
            "ru": "Этот пользователь вне вашей структурной зоны ответственности.",
            "tr": "Bu kullanıcı yapısal yetki alanınızın dışındadır.",
        },
        "role_not_defined_in_organization": {
            "en": "The selected role is not defined in this organisation: %(roles)s.",
            "ru": "Выбранная роль не определена в этой организации: %(roles)s.",
            "tr": "Seçilen rol bu kurumda tanımlı değil: %(roles)s.",
        },
    },
    "student_intake": {
        "Ad/soyad/ata adı ən çox %(n)s simvol ola bilər.": {
            "en": "First/last/patronymic name may be at most %(n)s characters.",
            "ru": "Имя/фамилия/отчество — не более %(n)s символов.",
            "tr": "Ad/soyad/baba adı en fazla %(n)s karakter olabilir.",
        },
        "sahə uzunluğu həddi keçildi": {
            "en": "field length limit exceeded",
            "ru": "превышена допустимая длина поля",
            "tr": "alan uzunluğu sınırı aşıldı",
        },
    },
    "exams.view.bank.message": {
        "Bank adı ən çox %(n)s simvol ola bilər.": {
            "en": "The bank name may be at most %(n)s characters.",
            "ru": "Название банка — не более %(n)s символов.",
            "tr": "Banka adı en fazla %(n)s karakter olabilir.",
        },
        "Bu adla bankınız artıq var: %(name)s": {
            "en": "You already have a bank with this name: %(name)s",
            "ru": "У вас уже есть банк с таким названием: %(name)s",
            "tr": "Bu adla bir bankanız zaten var: %(name)s",
        },
    },
    "accounts.a11y": {
        "Seç": {
            "en": "Select",
            "ru": "Выбрать",
            "tr": "Seçiniz",
        },
    },
    # ── RİM mərkəzi «Yeni hesab» axını (2026-09-06) ─────────────────────────
    "profile.rim": {
        ".xlsx, .xlsm və ya .csv": {
            "en": ".xlsx, .xlsm or .csv",
            "ru": ".xlsx, .xlsm или .csv",
            "tr": ".xlsx, .xlsm veya .csv",
        },
        "7 simvol, yalnız A–Z və 0–9.": {
            "en": "7 characters, only A–Z and 0–9.",
            "ru": "7 символов, только A–Z и 0–9.",
            "tr": "7 karakter, yalnızca A–Z ve 0–9.",
        },
        "Ad, soyad": {
            "en": "Name and surname",
            "ru": "Имя и фамилия",
            "tr": "Adı ve soyadı",
        },
        "Axtarmaq üçün ən azı 1 simvol yazın.": {
            "en": "Type at least 1 character to search.",
            "ru": "Введите хотя бы 1 символ для поиска.",
            "tr": "Aramak için en az 1 karakter yazın.",
        },
        "Axtarılır…": {
            "en": "Searching…",
            "ru": "Идёт поиск…",
            "tr": "Aranıyor…",
        },
        "Bir müəllim hesabı: kafedra təyinatı ilə (akademik qeyd yaradılmır).": {
            "en": "One teacher account, with a department assignment (no academic record is created).",
            "ru": "Одна учётная запись преподавателя с назначением на кафедру (академическая запись не создаётся).",
            "tr": "Bölüm ataması ile tek bir öğretim elemanı hesabı (akademik kayıt oluşturulmaz).",
        },
        "Bir tələbə hesabı: qrup, qəbul ili və akademik qeyd ilə.": {
            "en": "One student account, with group, admission year and academic record.",
            "ru": "Одна учётная запись студента с группой, годом приёма и академической записью.",
            "tr": "Grup, kayıt yılı ve akademik kayıt ile tek bir öğrenci hesabı.",
        },
        "Birdəfəlik parol": {
            "en": "One-time password",
            "ru": "Одноразовый пароль",
            "tr": "Tek kullanımlık parola",
        },
        "Birdəfəlik parollar YALNIZ indi görünür — nə bazada, nə audit jurnalında saxlanılmır. CSV-ni endirib tələbələrə çatdırın.": {
            "en": "The one-time passwords are shown ONLY now — they are stored neither in the database nor in the audit log. Download the CSV and pass them to the students.",
            "ru": "Одноразовые пароли показываются ТОЛЬКО сейчас — они не хранятся ни в базе, ни в журнале аудита. Скачайте CSV и передайте их студентам.",
            "tr": "Tek kullanımlık parolalar YALNIZCA şimdi görünür — ne veritabanında ne de denetim kaydında saklanır. CSV dosyasını indirip öğrencilere iletin.",
        },
        "Boş qala bilər — bu halda placeholder yazılır və istifadəçi ilk girişdə özü daxil edir.": {
            "en": "May stay empty — a placeholder is written instead and the user enters it at first login.",
            "ru": "Можно оставить пустым — тогда записывается заполнитель, а пользователь укажет адрес при первом входе.",
            "tr": "Boş bırakılabilir — bu durumda yer tutucu yazılır ve kullanıcı ilk girişte kendisi girer.",
        },
        "Boş qala bilər — istifadəçi adı kod və ya FİN əsasında qurulur.": {
            "en": "May stay empty — the username is built from the code or the FIN.",
            "ru": "Можно оставить пустым — имя пользователя формируется из кода или ФИН.",
            "tr": "Boş bırakılabilir — kullanıcı adı koddan veya FIN’den oluşturulur.",
        },
        "Boş qala bilər — kafedra sonradan da təyin edilə bilər.": {
            "en": "May stay empty — the department can be assigned later.",
            "ru": "Можно оставить пустым — кафедру можно назначить позже.",
            "tr": "Boş bırakılabilir — bölüm daha sonra da atanabilir.",
        },
        "Boş şablonu endir": {
            "en": "Download the blank template",
            "ru": "Скачать пустой шаблон",
            "tr": "Boş şablonu indir",
        },
        "Bu parol bir daha göstərilməyəcək və heç bir yerdə saxlanılmır. Pəncərəni bağlamazdan əvvəl istifadəçiyə çatdırın.": {
            "en": "This password will not be shown again and is stored nowhere. Pass it to the user before closing the window.",
            "ru": "Этот пароль больше не будет показан и нигде не хранится. Передайте его пользователю до закрытия окна.",
            "tr": "Bu parola bir daha gösterilmeyecek ve hiçbir yerde saklanmıyor. Pencereyi kapatmadan önce kullanıcıya iletin.",
        },
        "Cins": {
            "en": "Gender",
            "ru": "Пол",
            "tr": "Cinsiyet",
        },
        "Cəmi": {
            "en": "Total",
            "ru": "Всего",
            "tr": "Toplam",
        },
        "Daha bir hesab yarat": {
            "en": "Create another account",
            "ru": "Создать ещё одну запись",
            "tr": "Bir hesap daha oluştur",
        },
        "Daha çox nəticə var — axtarışı dəqiqləşdirin.": {
            "en": "There are more results — refine your search.",
            "ru": "Есть ещё результаты — уточните запрос.",
            "tr": "Daha fazla sonuç var — aramanızı daraltın.",
        },
        "Doğum tarixi": {
            "en": "Date of birth",
            "ru": "Дата рождения",
            "tr": "Doğum tarihi",
        },
        "E-poçt": {
            "en": "E-mail",
            "ru": "Эл. почта",
            "tr": "E-posta",
        },
        "Emal olunur…": {
            "en": "Processing…",
            "ru": "Обработка…",
            "tr": "İşleniyor…",
        },
        "Faylı bura sürüşdürün və ya seçmək üçün klikləyin": {
            "en": "Drag the file here, or click to choose one",
            "ru": "Перетащите файл сюда или нажмите, чтобы выбрать",
            "tr": "Dosyayı buraya sürükleyin ya da seçmek için tıklayın",
        },
        "Hansı hesab növünü yaradırsınız?": {
            "en": "Which kind of account are you creating?",
            "ru": "Какую учётную запись вы создаёте?",
            "tr": "Hangi hesap türünü oluşturuyorsunuz?",
        },
        "Hesab bu təşkilatda yaradılır və hər addım audit jurnalına düşür.": {
            "en": "The account is created in this organisation and every step is written to the audit log.",
            "ru": "Учётная запись создаётся в этой организации, и каждый шаг попадает в журнал аудита.",
            "tr": "Hesap bu kurumda oluşturulur ve her adım denetim kaydına yazılır.",
        },
        "Hesab yaradıldı.": {
            "en": "The account was created.",
            "ru": "Учётная запись создана.",
            "tr": "Hesap oluşturuldu.",
        },
        "Hesabı yarat": {
            "en": "Create the account",
            "ru": "Создать учётную запись",
            "tr": "Hesabı oluştur",
        },
        "Kafedra": {
            "en": "Department",
            "ru": "Кафедра",
            "tr": "Bölüm",
        },
        "Kafedra nəticələri": {
            "en": "Department results",
            "ru": "Результаты по кафедрам",
            "tr": "Bölüm sonuçları",
        },
        "Kafedranın adını yazın": {
            "en": "Type the department name",
            "ru": "Введите название кафедры",
            "tr": "Bölümün adını yazın",
        },
        "Kişi": {
            "en": "Male",
            "ru": "Мужской",
            "tr": "Erkek",
        },
        "Ləğv et": {
            "en": "Cancel",
            "ru": "Отмена",
            "tr": "Vazgeç",
        },
        "Müəllim": {
            "en": "Teacher",
            "ru": "Преподаватель",
            "tr": "Öğretim elemanı",
        },
        "Müəllim hesabı yaradıldı.": {
            "en": "The teacher account was created.",
            "ru": "Учётная запись преподавателя создана.",
            "tr": "Öğretim elemanı hesabı oluşturuldu.",
        },
        "Məsələn: köçürmə ilə gələn tələbə, dekanlıq müraciəti №…": {
            "en": "For example: student arriving by transfer, dean's office request no…",
            "ru": "Например: студент по переводу, обращение деканата №…",
            "tr": "Örneğin: yatay geçişle gelen öğrenci, dekanlık başvurusu no…",
        },
        "Parolları CSV kimi endir": {
            "en": "Download the passwords as CSV",
            "ru": "Скачать пароли в CSV",
            "tr": "Parolaları CSV olarak indir",
        },
        "Qadın": {
            "en": "Female",
            "ru": "Женский",
            "tr": "Kadın",
        },
        "Qeyd (audit üçün)": {
            "en": "Note (for the audit log)",
            "ru": "Примечание (для журнала аудита)",
            "tr": "Not (denetim kaydı için)",
        },
        "Qrup": {
            "en": "Group",
            "ru": "Группа",
            "tr": "Grup",
        },
        "Qrup nəticələri": {
            "en": "Group results",
            "ru": "Результаты по группам",
            "tr": "Grup sonuçları",
        },
        "Qrupun adını və ya kodunu yazın": {
            "en": "Type the group name or code",
            "ru": "Введите название или код группы",
            "tr": "Grubun adını veya kodunu yazın",
        },
        "Quru icra nəticəsi": {
            "en": "Dry-run result",
            "ru": "Результат пробного прогона",
            "tr": "Deneme çalıştırma sonucu",
        },
        "Quru icra nəticəsi (heç nə yazılmadı)": {
            "en": "Dry-run result (nothing was written)",
            "ru": "Результат пробного прогона (ничего не записано)",
            "tr": "Deneme çalıştırma sonucu (hiçbir şey yazılmadı)",
        },
        "Qəbul faylını yükləyin: əvvəlcə quru icra, sonra tətbiq. Bir faylda ən çox %(limit)s sətir.": {
            "en": "Upload the admission file: first a dry run, then the apply step. At most %(limit)s rows per file.",
            "ru": "Загрузите файл приёма: сначала пробный прогон, затем применение. Не более %(limit)s строк в файле.",
            "tr": "Kayıt dosyasını yükleyin: önce deneme çalıştırma, sonra uygulama. Dosya başına en fazla %(limit)s satır.",
        },
        "Qəbul ili": {
            "en": "Admission year",
            "ru": "Год приёма",
            "tr": "Kayıt yılı",
        },
        "Sütunların sırası sərbəstdir. Ən çox %(limit)s sətir, %(size)s MB.": {
            "en": "The column order is free. At most %(limit)s rows, %(size)s MB.",
            "ru": "Порядок столбцов произвольный. Не более %(limit)s строк, %(size)s МБ.",
            "tr": "Sütun sırası serbesttir. En fazla %(limit)s satır, %(size)s MB.",
        },
        "Sətir": {
            "en": "Row",
            "ru": "Строка",
            "tr": "Satır",
        },
        "Toplu idxal (tələbə siyahısı)": {
            "en": "Bulk import (student list)",
            "ru": "Массовый импорт (список студентов)",
            "tr": "Toplu içe aktarma (öğrenci listesi)",
        },
        "Toplu idxal — tələbə siyahısı": {
            "en": "Bulk import — student list",
            "ru": "Массовый импорт — список студентов",
            "tr": "Toplu içe aktarma — öğrenci listesi",
        },
        "Tələbə": {
            "en": "Student",
            "ru": "Студент",
            "tr": "Öğrenci",
        },
        "Tələbə hesabı yaradıldı.": {
            "en": "The student account was created.",
            "ru": "Учётная запись студента создана.",
            "tr": "Öğrenci hesabı oluşturuldu.",
        },
        "Tələbə kodu": {
            "en": "Student code",
            "ru": "Код студента",
            "tr": "Öğrenci numarası",
        },
        "Tətbiq et": {
            "en": "Apply",
            "ru": "Применить",
            "tr": "Uygula",
        },
        "Tətbiq et ({n} hesab)": {
            "en": "Apply ({n} accounts)",
            "ru": "Применить ({n} записей)",
            "tr": "Uygula ({n} hesap)",
        },
        "Tətbiq nəticəsi": {
            "en": "Apply result",
            "ru": "Результат применения",
            "tr": "Uygulama sonucu",
        },
        "Təyin edilməyib": {
            "en": "Not specified",
            "ru": "Не указан",
            "tr": "Belirtilmemiş",
        },
        "Təşkilatdakı yeri": {
            "en": "Place in the organisation",
            "ru": "Место в организации",
            "tr": "Kurumdaki yeri",
        },
        "Vəziyyət": {
            "en": "Status",
            "ru": "Состояние",
            "tr": "Durum",
        },
        "Xəta": {
            "en": "Error",
            "ru": "Ошибка",
            "tr": "Hata",
        },
        "Yaradılacaq": {
            "en": "Will be created",
            "ru": "Будет создан",
            "tr": "Oluşturulacak",
        },
        "Yaradıldı": {
            "en": "Created",
            "ru": "Создан",
            "tr": "Oluşturuldu",
        },
        "Yaradılır…": {
            "en": "Creating…",
            "ru": "Создание…",
            "tr": "Oluşturuluyor…",
        },
        "Yeni hesab": {
            "en": "New account",
            "ru": "Новая учётная запись",
            "tr": "Yeni hesap",
        },
        "Yeni hesab yaradın": {
            "en": "Create a new account",
            "ru": "Создание учётной записи",
            "tr": "Yeni bir hesap oluşturun",
        },
        "Yeni müəllim hesabı": {
            "en": "New teacher account",
            "ru": "Новая учётная запись преподавателя",
            "tr": "Yeni öğretim elemanı hesabı",
        },
        "Yeni tələbə hesabı": {
            "en": "New student account",
            "ru": "Новая учётная запись студента",
            "tr": "Yeni öğrenci hesabı",
        },
        "Yoxla (quru icra)": {
            "en": "Check (dry run)",
            "ru": "Проверить (пробный прогон)",
            "tr": "Denetle (deneme çalıştırma)",
        },
        "Ötürüldü": {
            "en": "Skipped",
            "ru": "Пропущено",
            "tr": "Atlandı",
        },
        "İstifadəçi bu parolla girəndən sonra e-poçt təsdiqi (OTP) və öz parolunu qurmaq addımına yönləndiriləcək.": {
            "en": "After signing in with this password the user is sent to e-mail confirmation (OTP) and to setting their own password.",
            "ru": "После входа с этим паролем пользователь будет направлен к подтверждению почты (OTP) и созданию собственного пароля.",
            "tr": "Kullanıcı bu parolayla giriş yaptıktan sonra e-posta doğrulaması (OTP) ve kendi parolasını belirleme adımına yönlendirilir.",
        },
        "İzah": {
            "en": "Explanation",
            "ru": "Пояснение",
            "tr": "Açıklama",
        },
        "İşçi kodu": {
            "en": "Employee code",
            "ru": "Код сотрудника",
            "tr": "Personel numarası",
        },
        "Şəxsi məlumat": {
            "en": "Personal details",
            "ru": "Личные данные",
            "tr": "Kişisel bilgiler",
        },
        "Əməliyyat alınmadı. Yenidən cəhd edin.": {
            "en": "The operation did not go through. Try again.",
            "ru": "Операция не выполнена. Попробуйте ещё раз.",
            "tr": "İşlem gerçekleşmedi. Yeniden deneyin.",
        },
        "Əvvəlcə QURU İCRA: heç nə yazılmır, nəyin yaranacağı sətir-sətir göstərilir.": {
            "en": "A DRY RUN first: nothing is written, and what would be created is shown row by row.",
            "ru": "Сначала ПРОБНЫЙ ПРОГОН: ничего не записывается, а результат показывается построчно.",
            "tr": "Önce DENEME ÇALIŞTIRMA: hiçbir şey yazılmaz, ne oluşacağı satır satır gösterilir.",
        },
        "Əvvəlcə fayl seçin.": {
            "en": "Choose a file first.",
            "ru": "Сначала выберите файл.",
            "tr": "Önce bir dosya seçin.",
        },
        "Yeni hesab yaratmaq üçün icazəniz yoxdur.": {
            "en": "You do not have permission to create new accounts.",
            "ru": "У вас нет прав на создание учётных записей.",
            "tr": "Yeni hesap oluşturma yetkiniz yok.",
        },
        "Aktiv təşkilat konteksti yoxdur.": {
            "en": "There is no active organisation context.",
            "ru": "Нет активного контекста организации.",
            "tr": "Etkin bir kurum bağlamı yok.",
        },
        "Çox sayda hesab yaradıldı. Bir az sonra yenidən cəhd edin.": {
            "en": "Too many accounts were created. Try again a little later.",
            "ru": "Создано слишком много учётных записей. Повторите чуть позже.",
            "tr": "Çok fazla hesap oluşturuldu. Biraz sonra yeniden deneyin.",
        },
        "Formda düzəliş tələb olunan sahələr var.": {
            "en": "The form has fields that need correcting.",
            "ru": "В форме есть поля, требующие исправления.",
            "tr": "Formda düzeltilmesi gereken alanlar var.",
        },
        "Naməlum hesab növü.": {
            "en": "Unknown account kind.",
            "ru": "Неизвестный тип учётной записи.",
            "tr": "Bilinmeyen hesap türü.",
        },
        "FİN boşdur.": {
            "en": "The FIN is empty.",
            "ru": "ФИН не заполнен.",
            "tr": "FIN boş.",
        },
        "FİN 7 simvolluq [A-Z0-9] formatında olmalıdır.": {
            "en": "The FIN must be 7 characters in [A-Z0-9] format.",
            "ru": "ФИН должен состоять из 7 символов формата [A-Z0-9].",
            "tr": "FIN, [A-Z0-9] biçiminde 7 karakter olmalıdır.",
        },
        "Bu FİN artıq sistemdə var — hesab yaradılmadı.": {
            "en": "This FIN already exists in the system — the account was not created.",
            "ru": "Этот ФИН уже есть в системе — учётная запись не создана.",
            "tr": "Bu FIN sistemde zaten var — hesap oluşturulmadı.",
        },
        "Ad məcburidir.": {
            "en": "The first name is required.",
            "ru": "Имя обязательно.",
            "tr": "Ad zorunludur.",
        },
        "Soyad məcburidir.": {
            "en": "The surname is required.",
            "ru": "Фамилия обязательна.",
            "tr": "Soyadı zorunludur.",
        },
        "Ən çox %(n)s simvol ola bilər.": {
            "en": "At most %(n)s characters are allowed.",
            "ru": "Допускается не более %(n)s символов.",
            "tr": "En fazla %(n)s karakter olabilir.",
        },
        "Doğum tarixi məcburidir.": {
            "en": "The date of birth is required.",
            "ru": "Дата рождения обязательна.",
            "tr": "Doğum tarihi zorunludur.",
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
            "en": "The gender was not recognised — it stays “not specified”.",
            "ru": "Пол не распознан — остаётся «не указан».",
            "tr": "Cinsiyet tanınmadı — “belirtilmemiş” olarak kalıyor.",
        },
        "Qrup seçilməyib və ya tapılmadı.": {
            "en": "No group was chosen, or it was not found.",
            "ru": "Группа не выбрана или не найдена.",
            "tr": "Grup seçilmedi veya bulunamadı.",
        },
        "Bu qrupun ixtisas proqramı (Program) tapılmadı — əvvəlcə struktur qurulmalıdır.": {
            "en": "No specialty programme (Program) was found for this group — build the structure first.",
            "ru": "Для этой группы не найдена образовательная программа (Program) — сначала постройте структуру.",
            "tr": "Bu grup için uzmanlık programı (Program) bulunamadı — önce yapıyı kurun.",
        },
        "Bu qəbul ili üçün kurikulum yoxdur — hesab yaradılarkən boş kurikulum yaradılacaq.": {
            "en": "There is no curriculum for this admission year — an empty curriculum will be created with the account.",
            "ru": "Для этого года приёма нет учебного плана — при создании записи будет создан пустой план.",
            "tr": "Bu kayıt yılı için müfredat yok — hesap oluşturulurken boş bir müfredat oluşturulacak.",
        },
        "Qəbul ili rəqəm olmalıdır.": {
            "en": "The admission year must be a number.",
            "ru": "Год приёма должен быть числом.",
            "tr": "Kayıt yılı bir sayı olmalıdır.",
        },
        "Qəbul ili 1950–%d aralığında olmalıdır.": {
            "en": "The admission year must be between 1950 and %d.",
            "ru": "Год приёма должен быть в диапазоне 1950–%d.",
            "tr": "Kayıt yılı 1950 ile %d arasında olmalıdır.",
        },
        "Kafedra tapılmadı.": {
            "en": "The department was not found.",
            "ru": "Кафедра не найдена.",
            "tr": "Bölüm bulunamadı.",
        },
        "Bu kod artıq istifadə olunub.": {
            "en": "This code is already in use.",
            "ru": "Этот код уже используется.",
            "tr": "Bu kod zaten kullanılıyor.",
        },
        "E-poçt formatı yanlışdır.": {
            "en": "The e-mail format is wrong.",
            "ru": "Неверный формат адреса эл. почты.",
            "tr": "E-posta biçimi hatalı.",
        },
        "E-poçt yoxdur — placeholder yazılır (ilk girişdə istifadəçi özü yazır).": {
            "en": "There is no e-mail — a placeholder is written (the user enters it at first login).",
            "ru": "Адрес эл. почты отсутствует — записывается заполнитель (пользователь укажет его при первом входе).",
            "tr": "E-posta yok — yer tutucu yazılıyor (kullanıcı ilk girişte kendisi girer).",
        },
        "E-poçt artıq istifadə olunur — placeholder yazılır.": {
            "en": "The e-mail is already in use — a placeholder is written.",
            "ru": "Адрес эл. почты уже используется — записывается заполнитель.",
            "tr": "E-posta zaten kullanılıyor — yer tutucu yazılıyor.",
        },
    },
    "accounts.syllabus": {
        "Bu fənn/dövr üçün dosyedə açıq qaralama var (%(version)s) — köçürmək əvəzinə onu redaktə edin.": {
            "en": "This subject/term already has an open draft (%(version)s) — edit it instead of copying.",
            "ru": "Для этого предмета/периода уже есть открытый черновик (%(version)s) — отредактируйте его.",
            "tr": "Bu ders/dönem için zaten açık bir taslak var (%(version)s) — kopyalamak yerine onu düzenleyin.",
        },
        "Bu fənn/dövr üçün təsdiqlənmiş sillabus var — üstünə köçürmək olmaz, yeni versiya açın.": {
            "en": "An approved syllabus exists for this subject/term — open a new version instead of copying over it.",
            "ru": "Для этого предмета/периода есть утверждённый силлабус — откройте новую версию.",
            "tr": "Bu ders/dönem için onaylı bir izlence var — üzerine kopyalamak yerine yeni sürüm açın.",
        },
        "Bölmə məzmununun formatı düzgün deyil (%(field)s).": {
            "en": "The section content has an invalid format (%(field)s).",
            "ru": "Содержимое раздела имеет неверный формат (%(field)s).",
            "tr": "Bölüm içeriğinin biçimi geçersiz (%(field)s).",
        },
        "Məzmun həddindən böyükdür — ən çox %(max)s (%(field)s).": {
            "en": "The content is too large — at most %(max)s (%(field)s).",
            "ru": "Содержимое слишком велико — не более %(max)s (%(field)s).",
            "tr": "İçerik çok büyük — en fazla %(max)s (%(field)s).",
        },
        "Bu açılış üçün sillabus artıq mövcuddur — siyahıdan açın.": {
            "en": "A syllabus already exists for this course offering — open it from the list.",
            "ru": "Для этого курса силлабус уже существует — откройте его из списка.",
            "tr": "Bu ders açılışı için zaten bir izlence var — listeden açın.",
        },
    },
    "registrar.schedule_manage": {
        "Auditoriya adı 64 simvoldan uzun ola bilməz.": {
            "en": "The room name cannot be longer than 64 characters.",
            "ru": "Название аудитории не может превышать 64 символа.",
            "tr": "Derslik adı 64 karakterden uzun olamaz.",
        },
    },
}


#: Açar-tipli msgid-lər üçün AZ mətni (kataloq qapısı xam açar sızmasını rədd edir).
AZ_OVERRIDES = {
    "rim_staff": "Rəqəmsal İnkişaf Mərkəzi (RİM) əməkdaşı",
    "missing_member_management_permission": "Bu əməl üçün `role.assign` və ya `org.manage_members` icazəsi lazımdır.",
    "target_outside_structure_scope": "Bu istifadəçi sizin struktur əhatənizdən kənardadır.",
    "role_not_defined_in_organization": "Seçilmiş rol bu təşkilatda müəyyən edilməyib: %(roles)s.",
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
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            probe = f'{head}msgid "{esc(msgid)}"\nmsgstr'
            if probe in text:
                continue
            msgstr = AZ_OVERRIDES.get(msgid, msgid) if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
