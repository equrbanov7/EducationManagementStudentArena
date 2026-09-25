#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: «Fənn qovluğu» (apps/subject_folder) nüvəsi — status/növ
kataloqları, domen xətaları, jurnal körpüsü, bildirişlər, model adları.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_sfolder_core_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_C = "subject_folder.choice"
_E = "subject_folder.error"
_J = "subject_folder.journal"
_M = "subject_folder.model"
_N = "subject_folder.notify"

STRINGS = {
    # ── Status / növ kataloqları ─────────────────────────────────────────────
    (_C, "Aktiv"): ("Active", "Активна", "Aktif"),
    (_C, "Arxivlənib"): ("Archived", "В архиве", "Arşivlendi"),
    (_C, "Digər"): ("Other", "Другое", "Diğer"),
    (_C, "Digər səbəb"): ("Other reason", "Другая причина", "Diğer neden"),
    (_C, "Ev tapşırığı"): ("Homework", "Домашнее задание", "Ödev"),
    (_C, "Eyni məzmun"): ("Identical content", "Идентичное содержимое", "Aynı içerik"),
    (_C, "Fayl"): ("File", "Файл", "Dosya"),
    (_C, "Fayl silindi"): ("File removed", "Файл удалён", "Dosya silindi"),
    (_C, "Gecikmə ilə qəbul edilir"): ("Late work accepted", "Принимается с опозданием", "Gecikmeli kabul edilir"),
    (_C, "Göndərildi"): ("Submitted", "Отправлено", "Gönderildi"),
    (_C, "Jurnal qəbul etmədi"): ("Gradebook refused", "Журнал не принял", "Not defteri kabul etmedi"),
    (_C, "Jurnala düşdü"): ("Sent to the gradebook", "Передано в журнал", "Not defterine aktarıldı"),
    (_C, "Jurnala düşüb"): ("Recorded in the gradebook", "Внесено в журнал", "Not defterine işlendi"),
    (_C, "Jurnala ötürülmə gözləyir"): (
        "Gradebook transfer pending",
        "Ожидает передачи в журнал",
        "Not defterine aktarım bekliyor",
    ),
    (_C, "Jurnala ötürülməsi gözlənilir"): (
        "Waiting for gradebook transfer",
        "Ожидается передача в журнал",
        "Not defterine aktarılması bekleniyor",
    ),
    (_C, "Keçid"): ("Link", "Ссылка", "Bağlantı"),
    (_C, "Kod nümunəsi"): ("Code sample", "Пример кода", "Kod örneği"),
    (_C, "Mövzuya uyğun deyil"): ("Off topic", "Не по теме", "Konu dışı"),
    (_C, "Müəllimin mövzusu"): ("Teacher's topic", "Тема преподавателя", "Öğretmenin konusu"),
    (_C, "Mətn oxşarlığı"): ("Text similarity", "Сходство текста", "Metin benzerliği"),
    (_C, "Oxşarlıq aşkarlandı"): ("Similarity detected", "Обнаружено сходство", "Benzerlik tespit edildi"),
    (_C, "Plagiat / köçürülmüş iş"): (
        "Plagiarism / copied work",
        "Плагиат / списанная работа",
        "İntihal / kopya çalışma",
    ),
    (_C, "Qaralama"): ("Draft", "Черновик", "Taslak"),
    (_C, "Qaralama saxlanıldı"): ("Draft saved", "Черновик сохранён", "Taslak kaydedildi"),
    (_C, "Qeyd"): ("Note", "Заметка", "Not"),
    (_C, "Qəbul edildi"): ("Accepted", "Принято", "Kabul edildi"),
    (_C, "Qəbul edilib"): ("Accepted", "Принята", "Kabul edildi"),
    (_C, "Rədd edildi"): ("Rejected", "Отклонено", "Reddedildi"),
    (_C, "Rədd edilib"): ("Rejected", "Отклонена", "Reddedildi"),
    (_C, "Rədd ləğv edildi"): ("Rejection withdrawn", "Отклонение отменено", "Ret geri alındı"),
    (_C, "Rəylə qaytarıldı"): ("Returned with feedback", "Возвращено с отзывом", "Geri bildirimle iade edildi"),
    (_C, "Sillabusdan"): ("From the syllabus", "Из силлабуса", "Ders izlencesinden"),
    (_C, "Son tarixdən sonra göndərilib"): (
        "Submitted after the deadline",
        "Отправлено после срока",
        "Son tarihten sonra gönderildi",
    ),
    (_C, "Son tarixdən sonra qəbul edilmir"): (
        "Not accepted after the deadline",
        "Не принимается после срока",
        "Son tarihten sonra kabul edilmez",
    ),
    (_C, "Sərbəst iş"): ("Independent work", "Самостоятельная работа", "Bağımsız çalışma"),
    (_C, "Tətbiq olunmur"): ("Not applicable", "Не применяется", "Uygulanmaz"),
    (_C, "Video keçidi"): ("Video link", "Ссылка на видео", "Video bağlantısı"),
    (_C, "Yenidən göndərildi"): ("Resubmitted", "Отправлено повторно", "Yeniden gönderildi"),
    (_C, "Yenidən işləməyə qaytarılıb"): (
        "Returned for revision",
        "Возвращена на доработку",
        "Düzeltme için iade edildi",
    ),
    (_C, "Yoxlama alınmadı"): ("Check failed", "Проверка не удалась", "Kontrol başarısız"),
    (_C, "Yoxlama gözlənilir"): ("Check pending", "Ожидает проверки", "Kontrol bekleniyor"),
    (_C, "Yoxlanıla bilən mətn yoxdur"): ("No checkable text", "Нет текста для проверки", "Kontrol edilecek metin yok"),
    (_C, "Yoxlanıldı"): ("Checked", "Проверено", "Kontrol edildi"),
    (_C, "Yoxlanılıb"): ("Check complete", "Проверка завершена", "Kontrol tamamlandı"),
    (_C, "Yoxlanılır"): ("Under review", "На проверке", "İnceleniyor"),
    (_C, "Şəkil"): ("Image", "Изображение", "Görsel"),
    # ── Domen xətaları ───────────────────────────────────────────────────────
    (_E, "Arxivlənmiş qovluq dəyişdirilə bilməz."): (
        "An archived folder cannot be changed.",
        "Архивную папку нельзя изменить.",
        "Arşivlenmiş klasör değiştirilemez.",
    ),
    (_E, "Açılma vaxtı son tarixdən əvvəl olmalıdır."): (
        "The opening time must be before the deadline.",
        "Время открытия должно быть раньше срока сдачи.",
        "Açılış zamanı son tarihten önce olmalıdır.",
    ),
    (_E, "Açılışın fənni qovluğun fənninə uyğun deyil."): (
        "The course offering's subject does not match the folder's subject.",
        "Дисциплина курса не совпадает с дисциплиной папки.",
        "Ders açılışının dersi klasörün dersiyle eşleşmiyor.",
    ),
    (_E, "Açılışın semestri qovluğun semestrinə uyğun deyil."): (
        "The course offering's semester does not match the folder's semester.",
        "Семестр курса не совпадает с семестром папки.",
        "Ders açılışının dönemi klasörün dönemiyle eşleşmiyor.",
    ),
    (_E, "Bal 0-dan böyük olmalı və %(max)s-dən çox olmamalıdır."): (
        "Points must be greater than 0 and no more than %(max)s.",
        "Балл должен быть больше 0 и не больше %(max)s.",
        "Puan 0'dan büyük ve en fazla %(max)s olmalıdır.",
    ),
    (_E, "Başlıq boş ola bilməz."): (
        "The title cannot be empty.",
        "Заголовок не может быть пустым.",
        "Başlık boş olamaz.",
    ),
    (_E, "Bu fənn açılışında aktiv qeydiyyatınız yoxdur."): (
        "You have no active enrollment in this course offering.",
        "У вас нет активной записи на этот курс.",
        "Bu ders açılışında aktif kaydınız yok.",
    ),
    (_E, "Bu fənn açılışını (qrupu) siz tədris etmirsiniz."): (
        "You do not teach this course offering (group).",
        "Вы не ведёте этот курс (группу).",
        "Bu ders açılışını (grubu) siz vermiyorsunuz.",
    ),
    (_E, "Bu fənni tədris etmədiyiniz üçün onun qovluğunu yarada bilməzsiniz."): (
        "You cannot create a folder for a subject you do not teach.",
        "Нельзя создать папку для дисциплины, которую вы не ведёте.",
        "Vermediğiniz bir ders için klasör oluşturamazsınız.",
    ),
    (_E, "Bu göndəriş baxış növbəsində deyil."): (
        "This submission is not in the review queue.",
        "Эта работа не находится в очереди на проверку.",
        "Bu teslim inceleme kuyruğunda değil.",
    ),
    (_E, "Bu qrup üçün qovluq aktiv deyil."): (
        "The folder is not active for this group.",
        "Папка не активна для этой группы.",
        "Klasör bu grup için etkin değil.",
    ),
    (_E, "Bu qrupun göndərişlərini yalnız fənnin müəllimi yoxlaya bilər."): (
        "Only the subject's teacher can review this group's submissions.",
        "Работы этой группы может проверять только преподаватель дисциплины.",
        "Bu grubun teslimlerini yalnızca dersin öğretmeni inceleyebilir.",
    ),
    (
        _E,
        "Bu qrupun sillabusundakı sərbəst iş strukturu (%(offering_option)s) qovluğunkundan (%(folder_option)s) "
        "fərqlidir — sərbəst iş bu qrupda qovluqdan qəbul edilməyəcək.",
    ): (
        "The independent work structure in this group's syllabus (%(offering_option)s) differs from the folder's "
        "(%(folder_option)s) — independent work will not be accepted from the folder for this group.",
        "Структура самостоятельной работы в силлабусе этой группы (%(offering_option)s) отличается от структуры "
        "папки (%(folder_option)s) — самостоятельные работы этой группы через папку приниматься не будут.",
        "Bu grubun ders izlencesindeki bağımsız çalışma yapısı (%(offering_option)s) klasörünkinden "
        "(%(folder_option)s) farklı — bu grupta bağımsız çalışmalar klasörden kabul edilmeyecek.",
    ),
    (_E, "Bu qrupun sərbəst işləri başqa fənn qovluğundan qiymətləndirilir."): (
        "This group's independent work is graded from another subject folder.",
        "Самостоятельные работы этой группы оцениваются из другой папки дисциплины.",
        "Bu grubun bağımsız çalışmaları başka bir ders klasöründen değerlendiriliyor.",
    ),
    (_E, "Bu sərbəst iş üçün bal artıq verilib — ikinci dəfə bal verilmir."): (
        "Points have already been awarded for this independent work — they cannot be awarded twice.",
        "Балл за эту самостоятельную работу уже выставлен — повторно он не выставляется.",
        "Bu bağımsız çalışma için puan zaten verildi — ikinci kez verilmez.",
    ),
    (_E, "Bu tapşırıq arxivlənib."): ("This task has been archived.", "Это задание в архиве.", "Bu görev arşivlendi."),
    (_E, "Bu tapşırıq fayl qəbul etmir — cavabı mətn kimi yazın."): (
        "This task does not accept files — write your answer as text.",
        "Это задание не принимает файлы — напишите ответ текстом.",
        "Bu görev dosya kabul etmiyor — cevabınızı metin olarak yazın.",
    ),
    (_E, "Bu tapşırıq mətn cavabı qəbul etmir — fayl yükləyin."): (
        "This task does not accept text answers — upload a file.",
        "Это задание не принимает текстовые ответы — загрузите файл.",
        "Bu görev metin cevabı kabul etmiyor — dosya yükleyin.",
    ),
    (_E, "Bu tapşırıq üzrə iş artıq yekunlaşıb."): (
        "Work on this task has already been finalized.",
        "Работа по этому заданию уже завершена.",
        "Bu görevdeki çalışma zaten sonuçlandı.",
    ),
    (_E, "Bu əməliyyat üçün səlahiyyətiniz yoxdur."): (
        "You do not have permission for this action.",
        "У вас нет прав на это действие.",
        "Bu işlem için yetkiniz yok.",
    ),
    (_E, "Cavab mətni yazın və ya ən azı bir fayl əlavə edin."): (
        "Write an answer or attach at least one file.",
        "Напишите ответ или прикрепите хотя бы один файл.",
        "Bir cevap yazın veya en az bir dosya ekleyin.",
    ),
    (_E, "Dəstəklənməyən fayl tipi: %(ext)s"): (
        "Unsupported file type: %(ext)s",
        "Неподдерживаемый тип файла: %(ext)s",
        "Desteklenmeyen dosya türü: %(ext)s",
    ),
    (_E, "Ev tapşırığına bal verilmir — yalnız «Yoxlanıldı» qeyd edin."): (
        "Homework is not graded — just mark it as “Checked”.",
        "За домашнее задание баллы не ставятся — отметьте только «Проверено».",
        "Ödeve puan verilmez — yalnızca «Kontrol edildi» olarak işaretleyin.",
    ),
    (_E, "Eyni anda ikinci göndəriş alındı — səhifəni yeniləyib yoxlayın."): (
        "A second submission arrived at the same time — refresh the page and check.",
        "Одновременно получена вторая отправка — обновите страницу и проверьте.",
        "Aynı anda ikinci bir gönderim alındı — sayfayı yenileyip kontrol edin.",
    ),
    (_E, "Fayl qəbul edilmədi."): ("The file was not accepted.", "Файл не принят.", "Dosya kabul edilmedi."),
    (_E, "Fayl sayı 1–%(max_files)s, ölçü 1–%(max_mb)s MB aralığında olmalıdır."): (
        "The number of files must be 1–%(max_files)s and the size 1–%(max_mb)s MB.",
        "Количество файлов — от 1 до %(max_files)s, размер — от 1 до %(max_mb)s МБ.",
        "Dosya sayısı 1–%(max_files)s, boyut 1–%(max_mb)s MB aralığında olmalıdır.",
    ),
    (_E, "Fayl seçilməyib."): ("No file selected.", "Файл не выбран.", "Dosya seçilmedi."),
    (_E, "Göndərişiniz yoxlanılır — müəllimin cavabını gözləyin."): (
        "Your submission is under review — wait for the teacher's response.",
        "Ваша работа на проверке — дождитесь ответа преподавателя.",
        "Teslimiz inceleniyor — öğretmenin yanıtını bekleyin.",
    ),
    (_E, "Keçid http:// və ya https:// ilə başlayan düzgün ünvan olmalıdır."): (
        "The link must be a valid address starting with http:// or https://.",
        "Ссылка должна быть корректным адресом, начинающимся с http:// или https://.",
        "Bağlantı http:// veya https:// ile başlayan geçerli bir adres olmalıdır.",
    ),
    (_E, "Kod mətni boşdur."): ("The code text is empty.", "Текст кода пуст.", "Kod metni boş."),
    (_E, "Material bu qovluğa aid deyil."): (
        "The material does not belong to this folder.",
        "Материал не относится к этой папке.",
        "Materyal bu klasöre ait değil.",
    ),
    (_E, "Material növü tanınmır."): (
        "Unknown material type.",
        "Неизвестный тип материала.",
        "Bilinmeyen materyal türü.",
    ),
    (_E, "Mövzu bu qovluğa aid deyil."): (
        "The topic does not belong to this folder.",
        "Тема не относится к этой папке.",
        "Konu bu klasöre ait değil.",
    ),
    (_E, "Mövzuya bağlı material və ya tapşırıq var — əvvəlcə onları köçürün."): (
        "Materials or tasks are linked to this topic — move them first.",
        "К теме привязаны материалы или задания — сначала перенесите их.",
        "Bu konuya bağlı materyal veya görev var — önce onları taşıyın.",
    ),
    (_E, "Mətn çox uzundur (ən çox %(max)s simvol)."): (
        "The text is too long (at most %(max)s characters).",
        "Текст слишком длинный (не более %(max)s символов).",
        "Metin çok uzun (en fazla %(max)s karakter).",
    ),
    (_E, "Qeyd mətni boşdur."): ("The note text is empty.", "Текст заметки пуст.", "Not metni boş."),
    (_E, "Qovluq hələ aktiv deyil."): (
        "The folder is not active yet.",
        "Папка ещё не активна.",
        "Klasör henüz etkin değil.",
    ),
    (_E, "Qovluğu yalnız onun sahibi olan müəllim redaktə edə bilər."): (
        "Only the teacher who owns the folder can edit it.",
        "Редактировать папку может только её владелец-преподаватель.",
        "Klasörü yalnızca sahibi olan öğretmen düzenleyebilir.",
    ),
    (_E, "Qovluğun statusu yanlışdır."): (
        "Invalid folder status.",
        "Недопустимый статус папки.",
        "Geçersiz klasör durumu.",
    ),
    (_E, "Rədd səbəbi seçilməyib."): (
        "No rejection reason selected.",
        "Не выбрана причина отклонения.",
        "Ret nedeni seçilmedi.",
    ),
    (_E, "Rəy yazın (ən azı %(min)s simvol)."): (
        "Write feedback (at least %(min)s characters).",
        "Напишите отзыв (не менее %(min)s символов).",
        "Geri bildirim yazın (en az %(min)s karakter).",
    ),
    (_E, "Seçilən obyektlər eyni təşkilata aid olmalıdır."): (
        "The selected objects must belong to the same organization.",
        "Выбранные объекты должны принадлежать одной организации.",
        "Seçilen nesneler aynı kuruma ait olmalıdır.",
    ),
    (_E, "Sillabus mövzusu silinmir — onu gizlədə və ya adını dəyişə bilərsiniz."): (
        "A syllabus topic cannot be deleted — you can hide or rename it.",
        "Тему силлабуса нельзя удалить — её можно скрыть или переименовать.",
        "Ders izlencesi konusu silinemez — gizleyebilir veya yeniden adlandırabilirsiniz.",
    ),
    (_E, "Son tarix keçib — bu tapşırıq gecikmə ilə qəbul edilmir."): (
        "The deadline has passed — this task does not accept late work.",
        "Срок истёк — это задание не принимает работы с опозданием.",
        "Son tarih geçti — bu görev gecikmeli teslim kabul etmiyor.",
    ),
    (_E, "Sərbəst iş bal ilə qəbul edilir."): (
        "Independent work is accepted with points.",
        "Самостоятельная работа принимается с баллом.",
        "Bağımsız çalışma puanla kabul edilir.",
    ),
    (
        _E,
        "Sərbəst iş balı cəmi %(max_total)s-i keçə bilməz: tələbənin artıq %(already)s balı var, "
        "ən çox %(remaining)s əlavə etmək olar.",
    ): (
        "Independent work points cannot exceed %(max_total)s in total: the student already has %(already)s, "
        "at most %(remaining)s can be added.",
        "Сумма баллов за самостоятельную работу не может превышать %(max_total)s: у студента уже %(already)s, "
        "можно добавить не более %(remaining)s.",
        "Bağımsız çalışma puanı toplamda %(max_total)s değerini geçemez: öğrencinin zaten %(already)s puanı var, "
        "en fazla %(remaining)s eklenebilir.",
    ),
    (_E, "Sərbəst iş tapşırıqları sillabusun strukturundan yaranır — əlavə sərbəst iş yaratmaq olmaz."): (
        "Independent work tasks come from the syllabus structure — extra independent work cannot be created.",
        "Задания самостоятельной работы создаются по структуре силлабуса — дополнительные создать нельзя.",
        "Bağımsız çalışma görevleri ders izlencesinin yapısından oluşur — ek bağımsız çalışma oluşturulamaz.",
    ),
    (_E, "Tapşırıq bu qovluğa aid deyil."): (
        "The task does not belong to this folder.",
        "Задание не относится к этой папке.",
        "Görev bu klasöre ait değil.",
    ),
    (_E, "Tapşırıq hələ açılmayıb."): ("The task is not open yet.", "Задание ещё не открыто.", "Görev henüz açılmadı."),
    (_E, "Tapşırıq hələ dərc edilməyib."): (
        "The task has not been published yet.",
        "Задание ещё не опубликовано.",
        "Görev henüz yayımlanmadı.",
    ),
    (_E, "Tapşırıq növü tanınmır."): ("Unknown task type.", "Неизвестный тип задания.", "Bilinmeyen görev türü."),
    (_E, "Tapşırıq nə mətn, nə də fayl qəbul edir."): (
        "The task accepts neither text nor files.",
        "Задание не принимает ни текст, ни файлы.",
        "Görev ne metin ne de dosya kabul ediyor.",
    ),
    (_E, "Tapşırığa göndəriş var — silmək olmaz, yalnız arxivləmək olar."): (
        "The task has submissions — it cannot be deleted, only archived.",
        "У задания есть работы — его нельзя удалить, только архивировать.",
        "Görevin teslimleri var — silinemez, yalnızca arşivlenebilir.",
    ),
    (_E, "Tapşırığa ən çox %(max)s qoşma əlavə etmək olar."): (
        "At most %(max)s attachments can be added to a task.",
        "К заданию можно прикрепить не более %(max)s вложений.",
        "Bir göreve en fazla %(max)s ek eklenebilir.",
    ),
    (_E, "Təyinat bu qovluğa aid deyil."): (
        "The assignment does not belong to this folder.",
        "Назначение не относится к этой папке.",
        "Atama bu klasöre ait değil.",
    ),
    (_E, "Yalnız qaralamadakı fayl silinə bilər."): (
        "Only files in a draft can be removed.",
        "Удалять можно только файлы черновика.",
        "Yalnızca taslaktaki dosyalar silinebilir.",
    ),
    (_E, "Yalnız rədd edilmiş göndəriş yenidən açıla bilər."): (
        "Only a rejected submission can be reopened.",
        "Повторно открыть можно только отклонённую работу.",
        "Yalnızca reddedilmiş bir teslim yeniden açılabilir.",
    ),
    (_E, "Ən çox %(max)s fayl əlavə etmək olar."): (
        "At most %(max)s files can be attached.",
        "Можно прикрепить не более %(max)s файлов.",
        "En fazla %(max)s dosya eklenebilir.",
    ),
    # ── Jurnal körpüsü ───────────────────────────────────────────────────────
    (_J, "Jurnal balı qəbul etmədi."): (
        "The gradebook did not accept the points.",
        "Журнал не принял балл.",
        "Not defteri puanı kabul etmedi.",
    ),
    (_J, "Jurnal inteqrasiyası hələ aktiv deyil — bal növbədədir."): (
        "Gradebook integration is not active yet — the points are queued.",
        "Интеграция с журналом ещё не активна — балл в очереди.",
        "Not defteri entegrasyonu henüz etkin değil — puan kuyrukta.",
    ),
    (_J, "Jurnala ötürmə alınmadı, yenidən cəhd ediləcək: %(error)s"): (
        "Transfer to the gradebook failed and will be retried: %(error)s",
        "Не удалось передать в журнал, будет повторная попытка: %(error)s",
        "Not defterine aktarım başarısız, yeniden denenecek: %(error)s",
    ),
    (_J, "Sərbəst iş %(n)s"): ("Independent work %(n)s", "Самостоятельная работа %(n)s", "Bağımsız çalışma %(n)s"),
    ("subject_folder.sync", "Sərbəst iş %(n)s"): (
        "Independent work %(n)s",
        "Самостоятельная работа %(n)s",
        "Bağımsız çalışma %(n)s",
    ),
    (
        "subject_folder.review",
        "Bu bal jurnala düşəcək: %(slot)s · %(points)s/%(max)s (cəmi %(total)s/%(max_total)s)",
    ): (
        "These points will go to the gradebook: %(slot)s · %(points)s/%(max)s (total %(total)s/%(max_total)s)",
        "Этот балл попадёт в журнал: %(slot)s · %(points)s/%(max)s (всего %(total)s/%(max_total)s)",
        "Bu puan not defterine işlenecek: %(slot)s · %(points)s/%(max)s (toplam %(total)s/%(max_total)s)",
    ),
    # ── Model adları ─────────────────────────────────────────────────────────
    (_M, "fənn qovluqları"): ("subject folders", "папки дисциплин", "ders klasörleri"),
    (_M, "fənn qovluğu"): ("subject folder", "папка дисциплины", "ders klasörü"),
    (_M, "göndəriş"): ("submission", "сданная работа", "teslim"),
    (_M, "göndəriş barmaq izi"): ("submission fingerprint", "отпечаток работы", "teslim parmak izi"),
    (_M, "göndəriş barmaq izləri"): ("submission fingerprints", "отпечатки работ", "teslim parmak izleri"),
    (_M, "göndəriş faylları"): ("submission files", "файлы работ", "teslim dosyaları"),
    (_M, "göndəriş faylı"): ("submission file", "файл работы", "teslim dosyası"),
    (_M, "göndəriş hadisələri"): ("submission events", "события работ", "teslim olayları"),
    (_M, "göndəriş hadisəsi"): ("submission event", "событие работы", "teslim olayı"),
    (_M, "göndərişlər"): ("submissions", "сданные работы", "teslimler"),
    (_M, "oxşarlıq uyğunluqları"): ("similarity matches", "совпадения по сходству", "benzerlik eşleşmeleri"),
    (_M, "oxşarlıq uyğunluğu"): ("similarity match", "совпадение по сходству", "benzerlik eşleşmesi"),
    (_M, "qovluq mövzuları"): ("folder topics", "темы папки", "klasör konuları"),
    (_M, "qovluq mövzusu"): ("folder topic", "тема папки", "klasör konusu"),
    (_M, "qovluq təyinatları"): ("folder assignments", "назначения папок", "klasör atamaları"),
    (_M, "qovluq təyinatı"): ("folder assignment", "назначение папки", "klasör ataması"),
    (_M, "tapşırıq"): ("task", "задание", "görev"),
    (_M, "tapşırıq qoşmaları"): ("task attachments", "вложения заданий", "görev ekleri"),
    (_M, "tapşırıq qoşması"): ("task attachment", "вложение задания", "görev eki"),
    (_M, "tapşırıq son tarixi"): ("task deadline", "срок задания", "görev son tarihi"),
    (_M, "tapşırıq son tarixləri"): ("task deadlines", "сроки заданий", "görev son tarihleri"),
    (_M, "tapşırıqlar"): ("tasks", "задания", "görevler"),
    (_M, "tədris materialları"): ("teaching materials", "учебные материалы", "ders materyalleri"),
    (_M, "tədris materialı"): ("teaching material", "учебный материал", "ders materyali"),
    # ── Bildirişlər ──────────────────────────────────────────────────────────
    (_N, "Bal jurnala köçürülür."): (
        "The points are being transferred to the gradebook.",
        "Балл переносится в журнал.",
        "Puan not defterine aktarılıyor.",
    ),
    (_N, "Bal: %(points)s / %(max)s — jurnala köçürülür."): (
        "Points: %(points)s / %(max)s — being transferred to the gradebook.",
        "Балл: %(points)s / %(max)s — переносится в журнал.",
        "Puan: %(points)s / %(max)s — not defterine aktarılıyor.",
    ),
    (_N, "Ev tapşırığı yoxlanıldı: %(task)s"): (
        "Homework checked: %(task)s",
        "Домашнее задание проверено: %(task)s",
        "Ödev kontrol edildi: %(task)s",
    ),
    (_N, "Müəllimin rəyini oxuyun və işi yenidən göndərin."): (
        "Read the teacher's feedback and resubmit your work.",
        "Прочитайте отзыв преподавателя и отправьте работу повторно.",
        "Öğretmenin geri bildirimini okuyun ve çalışmayı yeniden gönderin.",
    ),
    (_N, "Səbəb və rəy tapşırıq səhifəsindədir."): (
        "The reason and feedback are on the task page.",
        "Причина и отзыв — на странице задания.",
        "Neden ve geri bildirim görev sayfasındadır.",
    ),
    (_N, "Sərbəst iş qəbul edildi: %(task)s"): (
        "Independent work accepted: %(task)s",
        "Самостоятельная работа принята: %(task)s",
        "Bağımsız çalışma kabul edildi: %(task)s",
    ),
    (_N, "Yeni ev tapşırığı: %(title)s"): (
        "New homework: %(title)s",
        "Новое домашнее задание: %(title)s",
        "Yeni ödev: %(title)s",
    ),
    (_N, "Yeni fənn qovluğu: %(subject)s"): (
        "New subject folder: %(subject)s",
        "Новая папка дисциплины: %(subject)s",
        "Yeni ders klasörü: %(subject)s",
    ),
    (_N, "Yeni sərbəst iş: %(title)s"): (
        "New independent work: %(title)s",
        "Новая самостоятельная работа: %(title)s",
        "Yeni bağımsız çalışma: %(title)s",
    ),
    (_N, "Yoxlanılmalı yeni işlər: %(count)s"): (
        "New work to review: %(count)s",
        "Новые работы на проверку: %(count)s",
        "İncelenecek yeni çalışmalar: %(count)s",
    ),
    (_N, "«%(folder)s» — tədris materialları və tapşırıqlar sizin üçün açıqdır."): (
        "“%(folder)s” — teaching materials and tasks are now available to you.",
        "«%(folder)s» — учебные материалы и задания теперь доступны вам.",
        "«%(folder)s» — ders materyalleri ve görevler artık size açık.",
    ),
    (_N, "İşiniz rədd edildi: %(task)s"): (
        "Your work was rejected: %(task)s",
        "Ваша работа отклонена: %(task)s",
        "Çalışmanız reddedildi: %(task)s",
    ),
    (_N, "İşiniz yenidən işləməyə qaytarıldı: %(task)s"): (
        "Your work was returned for revision: %(task)s",
        "Ваша работа возвращена на доработку: %(task)s",
        "Çalışmanız düzeltme için iade edildi: %(task)s",
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
