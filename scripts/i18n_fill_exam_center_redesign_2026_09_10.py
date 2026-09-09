#!/usr/bin/env python3
"""EMSArena i18n — «İmtahan Mərkəzi» redizaynının mətnləri (2026-09-10).

Sahib: «ordakı imtahan mərkəzi olan sidebar hissəsində nə varsa hamısının
yenidən dizaynı olsun». Redizayn zamanı yaranan YENİ mətnlər (KPI etiketləri,
alt yazılar, boş vəziyyət izahları) və həmin səthlərdə əvvəldən tərcüməsiz
qalmış sətirlər burada 4 dilə doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir və idempotentdir
(mövcud msgid-ə toxunmur, yalnız kataloqda olmayanı əlavə edir).

İstifadə:  python scripts/i18n_fill_exam_center_redesign_2026_09_10.py
           python manage.py compilemessages
           python scripts/check_i18n_catalogs.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ctx → {msgid: {lang: msgstr}}. Boş ctx («») kontekstsiz msgid deməkdir.
ENTRIES = {
    "": {
        "Aktiv cəhdlər avtomatik təhvil veriləcək. Bu əməliyyat geri qaytarıla bilməz.": {
            "en": "Active attempts will be submitted automatically. This action cannot be undone.",
            "ru": "Активные попытки будут сданы автоматически. Это действие необратимо.",
            "tr": "Aktif denemeler otomatik teslim edilecek. Bu işlem geri alınamaz.",
        },
        # ⚠️ «Bilet» / «Oturum» türkcədə hərfən eynidir → i18n qapısı `identity`
        # borcu sayır. Ona görə türkcədə dəqiqləşdirilmiş forma seçildi.
        "Bilet": {"en": "Ticket", "ru": "Билет", "tr": "Sınav bileti"},
        "Bina / mərtəbə": {"en": "Building / floor", "ru": "Корпус / этаж", "tr": "Bina / kat"},
        "Bu oturuma hələ tələbə qoşulmayıb.": {
            "en": "No student has joined this session yet.",
            "ru": "К этой сессии ещё не присоединился ни один студент.",
            "tr": "Bu oturuma henüz öğrenci katılmadı.",
        },
        "Bu əməliyyat otaqdakı BÜTÜN gözləyən tələbələr üçün imtahanı eyni anda başladır.": {
            "en": "This starts the exam for ALL waiting students in the room at once.",
            "ru": "Это одновременно запускает экзамен для ВСЕХ ожидающих студентов в зале.",
            "tr": "Bu işlem salondaki TÜM bekleyen öğrenciler için sınavı aynı anda başlatır.",
        },
        (
            "Bütün imtahan nəticələri — fənn, qrup, kafedra, müəllim, tip və tədris ili üzrə süzün; "
            "sütun başlığı sıralayır. «Bax» tələbənin tam nəticəsini (apellyasiya düzəlişləri daxil) açır."
        ): {
            "en": (
                "All exam results — filter by subject, group, department, teacher, type and academic "
                "year; a column header sorts. “View” opens the student's full result (including appeal "
                "corrections)."
            ),
            "ru": (
                "Все результаты экзаменов — фильтруйте по предмету, группе, кафедре, преподавателю, "
                "типу и учебному году; заголовок столбца сортирует. «Просмотр» открывает полный "
                "результат студента (включая правки по апелляции)."
            ),
            "tr": (
                "Tüm sınav sonuçları — ders, grup, bölüm, öğretim elemanı, tür ve akademik yıla göre "
                "süzün; sütun başlığı sıralar. “Bak” öğrencinin tam sonucunu (itiraz düzeltmeleri "
                "dâhil) açar."
            ),
        },
        "Canlı zal": {"en": "Live hall", "ru": "Активный зал", "tr": "Canlı salon"},
        "Gedən imtahan": {"en": "Exam in progress", "ru": "Идущий экзамен", "tr": "Süren sınav"},
        "Kompüterin üzərinə klik edərək tələbənin hansı fənndə olduğunu və nə etdiyini görün.": {
            "en": "Click a computer to see which subject the student is in and what they are doing.",
            "ru": "Нажмите на компьютер, чтобы увидеть, по какому предмету студент сдаёт и что делает.",
            "tr": "Öğrencinin hangi derste olduğunu ve ne yaptığını görmek için bilgisayara tıklayın.",
        },
        "Oturum": {"en": "Session", "ru": "Сессия", "tr": "Sınav oturumu"},
        "Oturum başlayanda giriş, yer dəyişmə və pozuntu qeydləri burada görünəcək.": {
            "en": "Entry, seat-change and violation records will appear here once the session starts.",
            "ru": "Записи о входе, смене места и нарушениях появятся здесь после начала сессии.",
            "tr": "Oturum başladığında giriş, yer değiştirme ve ihlal kayıtları burada görünecek.",
        },
        "PIN verilib": {"en": "PIN issued", "ru": "PIN выдан", "tr": "PIN verildi"},
        (
            "Soldan tələbəni tapıb seçin — təyin olunmuş imtahan, PIN və fənn məlumatları sağda "
            "görünür. Nəticələr yazdıqca dərhal gəlir."
        ): {
            "en": (
                "Find and select a student on the left — the assigned exam, PIN and subject details "
                "appear on the right. Results arrive as you type."
            ),
            "ru": (
                "Найдите и выберите студента слева — назначенный экзамен, PIN и данные предмета "
                "появятся справа. Результаты приходят по мере ввода."
            ),
            "tr": (
                "Soldan öğrenciyi bulup seçin — atanan sınav, PIN ve ders bilgileri sağda görünür. "
                "Sonuçlar siz yazdıkça gelir."
            ),
        },
        "Tapılan tələbə": {"en": "Students found", "ru": "Найдено студентов", "tr": "Bulunan öğrenci"},
        "Tarix aralığını genişləndirin və ya zal/imtahan seçimini götürün.": {
            "en": "Widen the date range or clear the hall / exam selection.",
            "ru": "Расширьте диапазон дат или снимите выбор зала / экзамена.",
            "tr": "Tarih aralığını genişletin veya salon / sınav seçimini kaldırın.",
        },
        "Tələbə qeydli kompüterdən PIN ilə girəndə burada görünəcək.": {
            "en": "A student appears here once they sign in with a PIN from a registered computer.",
            "ru": "Студент появится здесь, как только войдёт по PIN с зарегистрированного компьютера.",
            "tr": "Öğrenci kayıtlı bir bilgisayardan PIN ile giriş yaptığında burada görünecek.",
        },
        "Təyin olunmuş imtahan": {"en": "Assigned exams", "ru": "Назначенные экзамены", "tr": "Atanan sınav"},
        "Zal təyinatı imtahan mərkəzi tərəfindən verilir.": {
            "en": "Hall assignments are made by the exam centre.",
            "ru": "Назначение залов выполняет экзаменационный центр.",
            "tr": "Salon ataması sınav merkezi tarafından yapılır.",
        },
        (
            "Zala təyin olunan nəzarətçilər zaldakı bütün imtahanları idarə edə bilər. Ad, soyad və ya "
            "kafedra üzrə axtarın."
        ): {
            "en": (
                "Invigilators assigned to a hall can manage every exam in it. Search by first name, "
                "last name or department."
            ),
            "ru": (
                "Наблюдатели, назначенные на зал, могут управлять всеми экзаменами в нём. Ищите по "
                "имени, фамилии или кафедре."
            ),
            "tr": (
                "Salona atanan gözetmenler salondaki tüm sınavları yönetebilir. Ad, soyad veya bölüme " "göre arayın."
            ),
        },
        "Zallar superadmin bölməsində idarə olunur.": {
            "en": "Halls are managed in the superadmin section.",
            "ru": "Залы управляются в разделе суперадминистратора.",
            "tr": "Salonlar süperadmin bölümünde yönetilir.",
        },
        "Zallar superadmin tərəfindən yaradılır.": {
            "en": "Halls are created by the superadmin.",
            "ru": "Залы создаёт суперадминистратор.",
            "tr": "Salonlar süperadmin tarafından oluşturulur.",
        },
        "cari axtarışda": {"en": "in current search", "ru": "в текущем поиске", "tr": "geçerli aramada"},
        "cəmi qeyd": {"en": "records in total", "ru": "записей всего", "tr": "toplam kayıt"},
        "diqqət tələb edir": {"en": "needs attention", "ru": "требует внимания", "tr": "dikkat gerektirir"},
        "fənn · zal cütü": {"en": "subject · hall pairs", "ru": "пары предмет · зал", "tr": "ders · salon çifti"},
        "giriş hazırdır": {"en": "entry is ready", "ru": "вход готов", "tr": "giriş hazır"},
        "hazırda aktiv": {"en": "active right now", "ru": "активны сейчас", "tr": "şu anda aktif"},
        "hələ yaradılmayıb": {"en": "not created yet", "ru": "ещё не создан", "tr": "henüz oluşturulmadı"},
        "imtahanı tamamlayıb": {"en": "finished the exam", "ru": "завершили экзамен", "tr": "sınavı tamamladı"},
        "oturum gedir": {"en": "session running", "ru": "идёт сессия", "tr": "oturum sürüyor"},
        "seçilən tələbədə": {"en": "for selected student", "ru": "у выбранного студента", "tr": "seçili öğrencide"},
        "sizə görünən": {"en": "visible to you", "ru": "видимые вам", "tr": "size görünen"},
        "Çıxarılıb / gəlməyib": {"en": "Removed / absent", "ru": "Удалён / не явился", "tr": "Çıkarıldı / gelmedi"},
        "İmtahanda tələbə": {"en": "Students in exam", "ru": "Студентов на экзамене", "tr": "Sınavdaki öğrenci"},
    },
    "accounts.exam_chance": {
        "(istifadəçi adı və ya email — vergül/yeni sətirlə; qrupla birlikdə də olar)": {
            "en": "(username or e-mail — comma/new line separated; may be combined with a group)",
            "ru": "(имя пользователя или e-mail — через запятую/с новой строки; можно вместе с группой)",
            "tr": "(kullanıcı adı veya e-posta — virgül/yeni satırla; grupla birlikte de olabilir)",
        },
        "Faydalanan tələbə": {
            "en": "Students benefited",
            "ru": "Студентов охвачено",
            "tr": "Yararlanan öğrenci",
        },
        "Görünən jurnal — tam tarixçə audit jurnalındadır.": {
            "en": "Visible log — the full history is in the audit log.",
            "ru": "Видимый журнал — полная история в журнале аудита.",
            "tr": "Görünen günlük — tam geçmiş denetim günlüğündedir.",
        },
        (
            "Seçilmiş final/kollokvium imtahanı üzrə tələbəyə və ya bütöv qrupa yenidən cəhd hüququ "
            "verin. Sistem avtomatik yeni giriş PIN-i yaradır, finalın köhnə girişini yenidən açır və "
            "imtahan tələbənin təyin olunmuş tapşırıqlarında yenidən görünür."
        ): {
            "en": (
                "Grant a retake right for the selected final/colloquium exam to a student or a whole "
                "group. The system creates a new entry PIN automatically, reopens the old final entry, "
                "and the exam reappears in the student's assigned tasks."
            ),
            "ru": (
                "Предоставьте право на повторную попытку по выбранному финальному/коллоквиумному "
                "экзамену студенту или всей группе. Система автоматически создаёт новый PIN входа, "
                "снова открывает прежний вход в финал, и экзамен снова появляется в назначенных "
                "заданиях студента."
            ),
            "tr": (
                "Seçilen final/kolokyum sınavı için bir öğrenciye veya tüm gruba yeniden giriş hakkı "
                "verin. Sistem otomatik olarak yeni giriş PIN'i oluşturur, finalin eski girişini "
                "yeniden açar ve sınav öğrencinin atanan görevlerinde tekrar görünür."
            ),
        },
        "Süzgəcləri genişləndirin — tədris ilini, semestri və ya fakültəni dəyişin.": {
            "en": "Widen the filters — change the academic year, semester or faculty.",
            "ru": "Расширьте фильтры — измените учебный год, семестр или факультет.",
            "tr": "Süzgeçleri genişletin — akademik yılı, dönemi veya fakülteyi değiştirin.",
        },
        "Uyğun imtahan": {"en": "Matching exams", "ru": "Подходящие экзамены", "tr": "Uygun sınav"},
        "Verilən şans": {"en": "Retakes granted", "ru": "Выдано попыток", "tr": "Verilen hak"},
        "cari süzgəclə": {"en": "with current filter", "ru": "с текущим фильтром", "tr": "geçerli süzgeçle"},
        "cəmi qeyd": {"en": "records in total", "ru": "записей всего", "tr": "toplam kayıt"},
        "cəmi verilib": {"en": "granted in total", "ru": "выдано всего", "tr": "toplam verildi"},
        "fərqli tələbə": {"en": "distinct students", "ru": "уникальных студентов", "tr": "farklı öğrenci"},
        "İmtahanı seçin, sonra qrupu və/və ya tələbələri işarələyin.": {
            "en": "Pick the exam, then tick the group and/or the students.",
            "ru": "Выберите экзамен, затем отметьте группу и/или студентов.",
            "tr": "Sınavı seçin, ardından grubu ve/veya öğrencileri işaretleyin.",
        },
        (
            "Şans veriləndə: cəhd limiti seçilən qədər artır, final/kollokvium üçün YENİ fərdi PIN "
            "yaradılır (kabinetdə dərhal görünür), finalın köhnə giriş bileti sıfırlanır və imtahan "
            "«Təyin olunmuş tapşırıqlar»da yenidən görünür. Bütün əməliyyat audit jurnalına yazılır."
        ): {
            "en": (
                "When a retake is granted: the attempt limit increases by the chosen amount, a NEW "
                "personal PIN is created for the final/colloquium (visible in the cabinet immediately), "
                "the old final entry ticket is reset, and the exam reappears under “Assigned tasks”. "
                "Every operation is written to the audit log."
            ),
            "ru": (
                "При выдаче попытки: лимит попыток увеличивается на выбранное число, для "
                "финала/коллоквиума создаётся НОВЫЙ персональный PIN (сразу виден в кабинете), старый "
                "входной билет финала сбрасывается, а экзамен снова появляется в «Назначенных "
                "заданиях». Каждая операция пишется в журнал аудита."
            ),
            "tr": (
                "Hak verildiğinde: deneme limiti seçilen kadar artar, final/kolokyum için YENİ kişisel "
                "PIN oluşturulur (kabinde hemen görünür), finalin eski giriş bileti sıfırlanır ve sınav "
                "“Atanan görevler”de yeniden görünür. Tüm işlemler denetim günlüğüne yazılır."
            ),
        },
        "Şans vermək üçün əvvəlcə aktiv təşkilat seçilməlidir.": {
            "en": "An active organization must be selected before a retake can be granted.",
            "ru": "Прежде чем выдать попытку, нужно выбрать активную организацию.",
            "tr": "Hak vermek için önce aktif bir kurum seçilmelidir.",
        },
        "Əlavə cəhd": {"en": "Extra attempts", "ru": "Доп. попытки", "tr": "Ek deneme"},
    },
    "accounts.legacy_review": {
        "Baxılıb": {"en": "Reviewed", "ru": "Проверено", "tr": "İncelendi"},
        (
            "Düzəliş canlı imtahan balına yazılır və auditli daxiletmə jurnalına düşür. Köhnə mənbə "
            "sətri olduğu kimi qalır."
        ): {
            "en": (
                "The correction is written to the live exam score and lands in the audited entry log. "
                "The old source row stays untouched."
            ),
            "ru": (
                "Правка записывается в текущий балл экзамена и попадает в аудируемый журнал ввода. "
                "Исходная строка остаётся без изменений."
            ),
            "tr": (
                "Düzeltme canlı sınav puanına yazılır ve denetimli giriş günlüğüne düşer. Eski kaynak "
                "satırı olduğu gibi kalır."
            ),
        },
        (
            "Köhnə sistemdən gətirilmiş imtahan nəticələri arasında yoxlanmalı olanlar burada toplanır. "
            "Siyahı hər dəfə sübut qatından yenidən hesablanır — dondurulmuş fayl deyil. Dəyər "
            "doğrudursa təsdiqləyin; səhvdirsə sənədli düzəliş yazın. Köhnə mənbə sətri heç bir halda "
            "üzərindən yazılmır."
        ): {
            "en": (
                "Exam results migrated from the old system that need checking are collected here. The "
                "list is recomputed from the evidence layer every time — it is not a frozen file. If "
                "the value is correct, confirm it; if it is wrong, write a documented correction. The "
                "old source row is never overwritten."
            ),
            "ru": (
                "Здесь собраны перенесённые из старой системы результаты экзаменов, требующие "
                "проверки. Список каждый раз пересчитывается из слоя доказательств — это не "
                "замороженный файл. Если значение верное, подтвердите его; если нет — оформите "
                "документированную правку. Исходная строка никогда не перезаписывается."
            ),
            "tr": (
                "Eski sistemden aktarılan ve kontrol edilmesi gereken sınav sonuçları burada toplanır. "
                "Liste her seferinde kanıt katmanından yeniden hesaplanır — dondurulmuş bir dosya "
                "değildir. Değer doğruysa onaylayın; yanlışsa belgeli düzeltme yazın. Eski kaynak "
                "satırının üzerine hiçbir zaman yazılmaz."
            ),
        },
        "Növbədə": {"en": "In queue", "ru": "В очереди", "tr": "Sırada"},
        "Qalıb": {"en": "Remaining", "ru": "Осталось", "tr": "Kalan"},
        (
            "Sətir növbədə qalır, amma «baxılmayıb» statusundan çıxır — kağız jurnal yoxlandıqdan sonra "
            "qərar verilə bilər."
        ): {
            "en": (
                "The row stays in the queue but leaves the “not reviewed” state — a decision can be "
                "made after the paper register has been checked."
            ),
            "ru": (
                "Строка остаётся в очереди, но выходит из статуса «не проверено» — решение можно "
                "принять после сверки с бумажным журналом."
            ),
            "tr": (
                "Satır sırada kalır ancak “incelenmedi” durumundan çıkar — kâğıt defter kontrol "
                "edildikten sonra karar verilebilir."
            ),
        },
        "hələ baxılmayıb": {"en": "not reviewed yet", "ru": "ещё не проверено", "tr": "henüz incelenmedi"},
        "qərar verilib": {"en": "decision made", "ru": "решение принято", "tr": "karar verildi"},
        "süzgəcə uyğun sətir": {
            "en": "rows matching the filter",
            "ru": "строк по фильтру",
            "tr": "süzgece uyan satır",
        },
        "İrəliləyiş": {"en": "Progress", "ru": "Прогресс", "tr": "İlerleme"},
    },
    "exams.center.stats": {
        (
            "Filtrə uyğun bütün nəticələri süni intellekt ümumiləşdirir — güclü və zəif sahələr, "
            "meyllər və tövsiyələr. Eyni məlumat üçün cavab keşdən gəlir və limit sərf olunmur."
        ): {
            "en": (
                "AI summarises every result matching the filter — strong and weak areas, trends and "
                "recommendations. For identical data the answer comes from cache and no quota is spent."
            ),
            "ru": (
                "ИИ обобщает все результаты по фильтру — сильные и слабые места, тенденции и "
                "рекомендации. Для одинаковых данных ответ берётся из кеша и лимит не расходуется."
            ),
            "tr": (
                "Yapay zekâ süzgece uyan tüm sonuçları özetler — güçlü ve zayıf alanlar, eğilimler ve "
                "öneriler. Aynı veri için yanıt önbellekten gelir ve kota harcanmaz."
            ),
        },
        (
            "Qrafiklər cədvəl səhifələnməsindən asılı olmayaraq bütün filtrlənmiş nəticələr üzrə "
            "hesablanır. Faiz metrikaları test tipli imtahanlara aiddir."
        ): {
            "en": (
                "Charts are computed over every filtered result, independently of table pagination. "
                "Percentage metrics apply to test-type exams."
            ),
            "ru": (
                "Графики считаются по всем отфильтрованным результатам, независимо от постраничного "
                "вывода таблицы. Процентные метрики относятся к тестовым экзаменам."
            ),
            "tr": (
                "Grafikler tablo sayfalamasından bağımsız olarak süzülmüş tüm sonuçlar üzerinden "
                "hesaplanır. Yüzde ölçütleri test türü sınavlar içindir."
            ),
        },
    },
    "exams.final_center.session_detail": {
        (
            "Zal oturumu imtahandan asılı deyil. Tələbə fərdi PIN-i ilə qeydli kompüterdən girəndə bu "
            "oturuma qoşulur. Nəzarətçi oturumu başladanda hər kəs öz imtahanına başlayır."
        ): {
            "en": (
                "A hall session is not tied to a single exam. A student joins it by signing in with "
                "their personal PIN from a registered computer. When the invigilator starts the "
                "session, everyone begins their own exam."
            ),
            "ru": (
                "Сессия зала не привязана к экзамену. Студент присоединяется к ней, войдя по личному "
                "PIN с зарегистрированного компьютера. Когда наблюдатель запускает сессию, каждый "
                "начинает свой экзамен."
            ),
            "tr": (
                "Salon oturumu sınava bağlı değildir. Öğrenci kayıtlı bir bilgisayardan kişisel PIN'i "
                "ile giriş yaparak bu oturuma katılır. Gözetmen oturumu başlattığında herkes kendi "
                "sınavına başlar."
            ),
        },
    },
    "registrar.exam_score_entry": {
        "Bal yazılıb": {"en": "Scores recorded", "ru": "Баллы внесены", "tr": "Puan girildi"},
        (
            "Bu tələbənin balı ARTIQ yazılıb. Dəyişiklik təqdimatlıdır — səbəb, qeyd və sənəd tələb "
            "olunur. Davam edilsin?"
        ): {
            "en": (
                "This student's score is ALREADY recorded. Changing it requires justification — a "
                "reason, a note and a document. Continue?"
            ),
            "ru": (
                "Балл этого студента УЖЕ внесён. Изменение требует обоснования — причины, примечания "
                "и документа. Продолжить?"
            ),
            "tr": (
                "Bu öğrencinin puanı ZATEN girilmiş. Değişiklik gerekçelidir — sebep, not ve belge "
                "gerekir. Devam edilsin mi?"
            ),
        },
        "Bu təşkilat üçün akademik semestr yoxdur.": {
            "en": "There is no academic semester for this organization.",
            "ru": "Для этой организации нет учебного семестра.",
            "tr": "Bu kurum için akademik dönem yok.",
        },
        "Gözləyir": {"en": "Pending", "ru": "Ожидает", "tr": "Bekliyor"},
        (
            "Jurnal bağlıdır — bu normaldır: imtahan jurnal bağlandıqdan sonra keçir. Giriş balı "
            "kilidli qalır, imtahan (çıxış) balı isə buradan yazıla bilir."
        ): {
            "en": (
                "The register is closed — that is normal: the exam takes place after the register "
                "closes. The entry score stays locked, while the exam (exit) score can still be "
                "recorded here."
            ),
            "ru": (
                "Журнал закрыт — это нормально: экзамен проходит после закрытия журнала. Входной балл "
                "остаётся заблокированным, а экзаменационный (выходной) балл можно внести здесь."
            ),
            "tr": (
                "Defter kapalı — bu normaldir: sınav defter kapandıktan sonra yapılır. Giriş puanı "
                "kilitli kalır, sınav (çıkış) puanı ise buradan girilebilir."
            ),
        },
        "Orta imtahan balı": {"en": "Average exam score", "ru": "Средний балл экзамена", "tr": "Ortalama sınav puanı"},
        (
            "Yazılı və praktiki imtahan kağız üzərində (praktikidə kodda) keçir — nəticəni sistemə "
            "İmtahan Mərkəzi köçürür. Qrupu seçin, hər tələbənin balını formada yazın; istəsəniz "
            "imtahan vərəqinin şəklini/PDF-ini və qeydini əlavə edin."
        ): {
            "en": (
                "Written and practical exams are taken on paper (in code for practical ones) — the "
                "exam centre transfers the result into the system. Choose the group, enter each "
                "student's score in the form; you may attach a photo/PDF of the exam sheet and a note."
            ),
            "ru": (
                "Письменный и практический экзамены проходят на бумаге (в практическом — в коде) — "
                "результат в систему переносит экзаменационный центр. Выберите группу, впишите балл "
                "каждого студента в форму; при желании приложите фото/PDF работы и примечание."
            ),
            "tr": (
                "Yazılı ve uygulamalı sınav kâğıt üzerinde (uygulamalıda kodda) yapılır — sonucu "
                "sisteme Sınav Merkezi aktarır. Grubu seçin, her öğrencinin puanını forma yazın; "
                "isterseniz sınav kâğıdının fotoğrafını/PDF'ini ve notunu ekleyin."
            ),
        },
        "bal yazılmayıb": {"en": "no score recorded", "ru": "балл не внесён", "tr": "puan girilmedi"},
        "qeydiyyatlı": {"en": "enrolled", "ru": "зачислено", "tr": "kayıtlı"},
        "sistemə köçürülüb": {
            "en": "transferred to the system",
            "ru": "перенесено в систему",
            "tr": "sisteme aktarıldı",
        },
        (
            "İlk daxiletmə sərbəstdir — sübut məcburi deyil. ARTIQ yazılmış balı dəyişmək isə "
            "təqdimatlıdır: səbəb, qeyd və sənəd üçü də tələb olunur. Boş buraxılan sahə toxunulmur."
        ): {
            "en": (
                "The first entry is free — no evidence is required. Changing an ALREADY recorded score "
                "is justified: a reason, a note and a document are all required. A field left empty is "
                "left untouched."
            ),
            "ru": (
                "Первый ввод свободный — доказательство не требуется. Изменение УЖЕ внесённого балла "
                "требует обоснования: нужны причина, примечание и документ. Пустое поле не "
                "затрагивается."
            ),
            "tr": (
                "İlk giriş serbesttir — kanıt zorunlu değildir. ZATEN girilmiş puanı değiştirmek ise "
                "gerekçelidir: sebep, not ve belge üçü de gerekir. Boş bırakılan alana dokunulmaz."
            ),
        },
        "Əvvəlcə Akademik təqvimdə semestr yaradın.": {
            "en": "Create a semester in the Academic calendar first.",
            "ru": "Сначала создайте семестр в Академическом календаре.",
            "tr": "Önce Akademik takvimde bir dönem oluşturun.",
        },
    },
    "registrar.kollokvium_window": {
        "Bu pəncərəni aktivləşdirsəniz, aralıq açıq olduqda müəllimlər bal yaza biləcək. Davam edilsin?": {
            "en": "If you activate this window, teachers will be able to enter scores while the range is open. Continue?",
            "ru": "Если активировать это окно, преподаватели смогут вносить баллы, пока период открыт. Продолжить?",
            "tr": "Bu pencereyi etkinleştirirseniz, aralık açıkken öğretim elemanları puan girebilecek. Devam edilsin mi?",
        },
        "Bu pəncərəni deaktiv etsəniz, müəllimlər bu kollokvium üzrə bal yaza bilməyəcək. Davam edilsin?": {
            "en": "If you deactivate this window, teachers will not be able to enter scores for this colloquium. Continue?",
            "ru": "Если деактивировать это окно, преподаватели не смогут вносить баллы по этому коллоквиуму. Продолжить?",
            "tr": "Bu pencereyi devre dışı bırakırsanız, öğretim elemanları bu kolokyum için puan giremeyecek. Devam edilsin mi?",
        },
        (
            "Bu semestr bitib — tarixləri dəyişmək mümkün deyil (yalnız baxış). Redaktə üçün yuxarıdan "
            "cari/gələcək tədris ili və semestri seçin."
        ): {
            "en": (
                "This semester has ended — the dates cannot be changed (view only). To edit, pick a "
                "current/future academic year and semester above."
            ),
            "ru": (
                "Этот семестр завершён — даты изменить нельзя (только просмотр). Для редактирования "
                "выберите выше текущий/будущий учебный год и семестр."
            ),
            "tr": (
                "Bu dönem bitti — tarihler değiştirilemez (yalnızca görüntüleme). Düzenlemek için "
                "yukarıdan güncel/gelecek akademik yıl ve dönemi seçin."
            ),
        },
        "Bu təşkilat üçün akademik semestr yoxdur.": {
            "en": "There is no academic semester for this organization.",
            "ru": "Для этой организации нет учебного семестра.",
            "tr": "Bu kurum için akademik dönem yok.",
        },
        (
            "Bu təşkilat üçün cari və ya gələcək semestr yoxdur — aşağıdakı bitmiş semestr yalnız baxış "
            "üçündür. Tarixləri təyin etmək üçün əvvəlcə Akademik təqvimdə yeni tədris ili/semestr "
            "yaradın."
        ): {
            "en": (
                "There is no current or future semester for this organization — the finished semester "
                "below is view-only. To set dates, first create a new academic year/semester in the "
                "Academic calendar."
            ),
            "ru": (
                "У этой организации нет текущего или будущего семестра — завершённый семестр ниже "
                "доступен только для просмотра. Чтобы задать даты, сначала создайте новый учебный "
                "год/семестр в Академическом календаре."
            ),
            "tr": (
                "Bu kurum için güncel veya gelecek dönem yok — aşağıdaki bitmiş dönem yalnızca "
                "görüntüleme içindir. Tarihleri belirlemek için önce Akademik takvimde yeni akademik "
                "yıl/dönem oluşturun."
            ),
        },
        "Bu əlavə gün silinsin? Müəllimlər üçün son tarix əvvəlki bağlanış tarixinə qayıdacaq.": {
            "en": "Delete these extra days? The deadline for teachers will revert to the previous closing date.",
            "ru": "Удалить эти дополнительные дни? Крайний срок для преподавателей вернётся к прежней дате закрытия.",
            "tr": "Bu ek günler silinsin mi? Öğretim elemanları için son tarih önceki kapanış tarihine dönecek.",
        },
        (
            "K1/K2/K3 üçün müəllimlərin bal yaza biləcəyi tarix aralığını təyin edin və aktivləşdirin. "
            "Rəhbər əlavə gün verə bilər."
        ): {
            "en": (
                "Set and activate the date range in which teachers can enter K1/K2/K3 scores. A "
                "manager can grant extra days."
            ),
            "ru": (
                "Задайте и активируйте период, в котором преподаватели могут вносить баллы K1/K2/K3. "
                "Руководитель может выдать дополнительные дни."
            ),
            "tr": (
                "Öğretim elemanlarının K1/K2/K3 puanı girebileceği tarih aralığını belirleyin ve "
                "etkinleştirin. Yönetici ek gün verebilir."
            ),
        },
        "Pəncərə tarixləri sonradan dəyişdirilə bilməz; yalnız əlavə gün verilə bilər.": {
            "en": "Window dates cannot be changed later; only extra days can be granted.",
            "ru": "Даты окна впоследствии изменить нельзя; можно только выдать дополнительные дни.",
            "tr": "Pencere tarihleri sonradan değiştirilemez; yalnızca ek gün verilebilir.",
        },
        "Yadda saxladıqdan sonra tarixləri dəyişə bilərsiniz; müəllimlərə son tarixi uzatmaq üçün əlavə gün verin.": {
            "en": "After saving you can change the dates; grant extra days to extend the deadline for teachers.",
            "ru": "После сохранения даты можно изменить; чтобы продлить срок для преподавателей, выдайте дополнительные дни.",
            "tr": "Kaydettikten sonra tarihleri değiştirebilirsiniz; öğretim elemanları için son tarihi uzatmak üzere ek gün verin.",
        },
        "aralıq bitib": {"en": "range has ended", "ru": "период завершён", "tr": "aralık bitti"},
        "cəmi verilib": {"en": "granted in total", "ru": "выдано всего", "tr": "toplam verildi"},
        "müəllim bal yaza bilir": {
            "en": "teachers can enter scores",
            "ru": "преподаватели могут вносить баллы",
            "tr": "öğretim elemanı puan girebilir",
        },
        "tarix gözləyir": {"en": "awaiting dates", "ru": "ожидает дат", "tr": "tarih bekliyor"},
        "Əlavə gün": {"en": "Extra days", "ru": "Доп. дни", "tr": "Ek gün"},
        (
            "Əlavə gün müəllimlərin bal yazma son tarixini uzadır. Pəncərə tarixləri dəyişmir — yalnız "
            "son tarix uzanır. Sonradan yenidən əlavə gün verə bilərsiniz."
        ): {
            "en": (
                "Extra days extend the score-entry deadline for teachers. The window dates do not "
                "change — only the deadline moves. You can grant extra days again later."
            ),
            "ru": (
                "Дополнительные дни продлевают срок внесения баллов для преподавателей. Даты окна не "
                "меняются — сдвигается только крайний срок. Позже можно выдать дни ещё раз."
            ),
            "tr": (
                "Ek günler öğretim elemanlarının puan girme son tarihini uzatır. Pencere tarihleri "
                "değişmez — yalnızca son tarih uzar. Daha sonra tekrar ek gün verebilirsiniz."
            ),
        },
        "Əvvəlcə Akademik təqvimdə semestr yaradın.": {
            "en": "Create a semester in the Academic calendar first.",
            "ru": "Сначала создайте семестр в Академическом календаре.",
            "tr": "Önce Akademik takvimde bir dönem oluşturun.",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    """Kataloqa YALNIZ olmayan girişləri əlavə et.

    ⚠️ Mətn axtarışı ilə YOX, `polib` ilə: uzun msgid-lər .po-da bir neçə sətrə
    bükülür (`msgid ""` + davam sətirləri), ona görə xam `in text` yoxlaması
    mövcud girişi tapmır və TƏKRAR giriş yaradır (msgfmt «duplicate message
    definition» ilə çökür). polib bükülmüş girişi də düzgün tanıyır.
    """
    import polib

    path = po_path(lang)
    catalog = polib.pofile(path, wrapwidth=0)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in catalog}

    added = 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            catalog.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr))
            existing.add((ctx, msgid))
            added += 1

    if added:
        catalog.save(path)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
