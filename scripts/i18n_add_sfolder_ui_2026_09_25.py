#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-25: «Fənn qovluğu» kabinet ekranları (müəllim, yoxlama, tələbə).

Üç profil bölməsinin (``subject-folders``, ``subject-folder-review``, ``my-subject-folders``)
şablon və kontekst mətnləri (``subject_folder.ui``), əməl endpoint-lərinin cavab
mesajları və sidebar bəndləri (``profile.sidebar``). Məlumat aşağıdakı cədvəldədir:
hər sətir ``msgid<TAB>en<TAB>ru<TAB>tr``; ``#`` ilə başlayan sətir konteksti dəyişir.

Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_sfolder_ui_2026_09_25.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

DATA = """
# profile.sidebar
Fənn qovluqları	Subject folders	Папки предметов	Ders klasörleri
Fənn qovluqlarım	My subject folders	Мои папки предметов	Ders klasörlerim
Tapşırıq yoxlaması	Assignment review	Проверка заданий	Ödev kontrolü
# subject_folder.ui
%(done)s göndəriş işləndi, %(failed)s göndəriş alınmadı.	%(done)s submissions processed, %(failed)s failed.	Обработано отправок: %(done)s, не удалось: %(failed)s.	%(done)s gönderim işlendi, %(failed)s gönderim başarısız oldu.
%(done)s göndəriş işləndi.	%(done)s submissions processed.	Обработано отправок: %(done)s.	%(done)s gönderim işlendi.
%(name)s — seç	Select %(name)s	Выбрать: %(name)s	%(name)s öğesini seç
AKTİV	ACTIVE	АКТИВНЫЕ	AKTİF
Ad, soyad və ya istifadəçi adı…	Name, surname or username…	Имя, фамилия или логин…	Ad, soyad veya kullanıcı adı…
Aktiv təşkilat konteksti yoxdur.	There is no active organization context.	Нет контекста активной организации.	Etkin kurum bağlamı yok.
Aktiv təşkilat seçilməyib	No active organization selected	Активная организация не выбрана	Etkin kurum seçilmedi
Aktivləşdir	Activate	Активировать	Etkinleştir
Arxivdədir	Archived	В архиве	Arşivde
Arxivdən çıxar	Restore from archive	Вернуть из архива	Arşivden çıkar
Arxivlə	Archive	Архивировать	Arşivle
Axtarış	Search	Поиск	Arama
AÇIQ TAPŞIRIQ	OPEN TASKS	ОТКРЫТЫЕ ЗАДАНИЯ	AÇIK ÖDEVLER
Aç	Open	Открыть	Aç
Açılma vaxtı	Opens at	Время открытия	Açılış zamanı
Açılır	Opens	Открывается	Açılış
Açılır:	Opens:	Открывается:	Açılış:
Açıq tapşırıq: %(n)s	Open tasks: %(n)s	Открытых заданий: %(n)s	Açık ödev: %(n)s
Açıqdır	Open	Открыто	Açık
Bal	Points	Балл	Puan
Bal (maks. %(max)s)	Points (max. %(max)s)	Балл (макс. %(max)s)	Puan (en fazla %(max)s)
Bal yazılmır — tələbə işi düzəldib yenidən göndərir.	No points are recorded — the student revises the work and resubmits.	Балл не выставляется — студент исправит работу и отправит заново.	Puan yazılmaz — öğrenci çalışmayı düzeltip yeniden gönderir.
Bax	View	Просмотр	Görüntüle
Bağlanıb	Closed	Закрыто	Kapandı
Başlanmayıb	Not started	Не начато	Başlanmadı
Başlıq	Title	Заголовок	Başlık
Başqa semestrə köçür	Copy to another semester	Перенести в другой семестр	Başka döneme kopyala
Bir dəfəyə ən çox %(max)s göndəriş seçmək olar.	You can select at most %(max)s submissions at once.	За один раз можно выбрать не более %(max)s отправок.	Tek seferde en fazla %(max)s gönderim seçilebilir.
Boş saxlasanız fənnin adı yazılır	If left empty, the subject name is used	Если оставить пустым, будет использовано название предмета	Boş bırakırsanız ders adı kullanılır
Bu fənn və semestr üçün qovluğunuz artıq var — o açılır.	You already have a folder for this subject and semester — opening it.	У вас уже есть папка для этого предмета и семестра — она открывается.	Bu ders ve dönem için klasörünüz zaten var — açılıyor.
Bu fənn və semestr üçün tədris etdiyiniz qrup tapılmadı.	No groups you teach were found for this subject and semester.	Для этого предмета и семестра не найдено групп, которые вы ведёте.	Bu ders ve dönem için ders verdiğiniz grup bulunamadı.
Bu mövzuda hələ material və tapşırıq yoxdur.	This topic has no materials or tasks yet.	В этой теме пока нет материалов и заданий.	Bu konuda henüz materyal ve ödev yok.
Bu mövzuda hələ məzmun yoxdur.	This topic has no content yet.	В этой теме пока нет содержимого.	Bu konuda henüz içerik yok.
Bu mövzuya material əlavə et	Add material to this topic	Добавить материал в эту тему	Bu konuya materyal ekle
Bu oxşarlıq plagiat deyil kimi qeyd olunsun?	Mark this similarity as not plagiarism?	Отметить это совпадение как не плагиат?	Bu benzerlik intihal değil olarak işaretlensin mi?
Bu qrupun təyinatı ləğv edilsin? Tələbələr qovluğu görməyəcək; göndərişlər saxlanılır.	Cancel this group's assignment? Students will no longer see the folder; submissions are kept.	Отменить назначение этой группе? Студенты не будут видеть папку; отправки сохранятся.	Bu grubun ataması iptal edilsin mi? Öğrenciler klasörü görmeyecek; gönderimler saklanır.
Bütün qruplar üçün son tarix	Deadline for all groups	Срок для всех групп	Tüm gruplar için son tarih
Bütün qruplara son tarix qoy	Set a deadline for all groups	Установить срок для всех групп	Tüm gruplara son tarih koy
Bəli, davam et	Yes, continue	Да, продолжить	Evet, devam et
Bərpa et	Restore	Восстановить	Geri yükle
Cavab	Answer	Ответ	Cevap
Cavab boşdur.	The answer is empty.	Ответ пуст.	Cevap boş.
Cavab forması	Answer format	Форма ответа	Cevap biçimi
Cavab ver	Answer	Ответить	Cevapla
Cavabınız	Your answer	Ваш ответ	Cevabınız
Cəhd %(n)s	Attempt %(n)s	Попытка %(n)s	Deneme %(n)s
Düzəldilmiş cavab	Revised answer	Исправленный ответ	Düzeltilmiş cevap
Düzəlt və göndər	Revise and resubmit	Исправить и отправить	Düzelt ve gönder
Dərc edilib	Published	Опубликовано	Yayımlandı
Dərc et	Publish	Опубликовать	Yayımla
Dərhal dərc et (tələbələr görsün)	Publish now (visible to students)	Опубликовать сразу (увидят студенты)	Hemen yayımla (öğrenciler görsün)
Dərhal dərc et (təyin olunmuş qruplara bildiriş gedir)	Publish now (assigned groups are notified)	Опубликовать сразу (назначенным группам придёт уведомление)	Hemen yayımla (atanan gruplara bildirim gider)
Ev tapşırığı	Homework	Домашнее задание	Ev ödevi
Ev tapşırığı silinsin? Göndərişi olan tapşırıq silinmir — onu arxivləyin.	Delete this homework? Homework with submissions cannot be deleted — archive it instead.	Удалить домашнее задание? Задание с отправками удалить нельзя — архивируйте его.	Ev ödevi silinsin mi? Gönderimi olan ödev silinemez — arşivleyin.
Ev tapşırığı «yoxlanıldı» kimi qeyd olundu.	Homework marked as “checked”.	Домашнее задание отмечено как «проверено».	Ev ödevi “kontrol edildi” olarak işaretlendi.
Ev tapşırığı əlavə et	Add homework	Добавить домашнее задание	Ev ödevi ekle
Ev tapşırığı əlavə olundu.	Homework added.	Домашнее задание добавлено.	Ev ödevi eklendi.
Ev tapşırığına bal verilmir — müəllim işi «yoxlanıldı» qeyd edir və ya rəylə qaytarır.	Homework is not graded — the teacher marks it as “checked” or returns it with feedback.	Домашнее задание не оценивается баллами — преподаватель отмечает его как «проверено» или возвращает с отзывом.	Ev ödevine puan verilmez — öğretmen “kontrol edildi” olarak işaretler veya geri bildirimle iade eder.
Fayl	File	Файл	Dosya
Fayl qaralamadan silindi.	File removed from the draft.	Файл удалён из черновика.	Dosya taslaktan silindi.
Fayl sayı	Number of files	Количество файлов	Dosya sayısı
Fayl yükləmə	File upload	Загрузка файлов	Dosya yükleme
Fayl ölçüsü (MB)	File size (MB)	Размер файла (МБ)	Dosya boyutu (MB)
Fayl, şəkil, keçid, video keçidi, kod nümunəsi və ya qeyd. Dərc edilməyən material tələbələrə görünmür.	A file, image, link, video link, code sample or note. Unpublished materials are not visible to students.	Файл, изображение, ссылка, ссылка на видео, пример кода или заметка. Неопубликованные материалы студенты не видят.	Dosya, görsel, bağlantı, video bağlantısı, kod örneği veya not. Yayımlanmayan materyal öğrencilere görünmez.
Fayllar	Files	Файлы	Dosyalar
Faylı sil	Remove file	Удалить файл	Dosyayı sil
Fənn adı ilə axtar…	Search by subject name…	Поиск по названию предмета…	Ders adına göre ara…
Fənn qovluqları	Subject folders	Папки предметов	Ders klasörleri
Fənn qovluqları təşkilat kontekstində açılır — yuxarıdan təşkilatınızı seçin.	Subject folders open within an organization — select your organization at the top.	Папки предметов открываются в контексте организации — выберите организацию вверху.	Ders klasörleri kurum bağlamında açılır — yukarıdan kurumunuzu seçin.
Fənn qovluqlarım	My subject folders	Мои папки предметов	Ders klasörlerim
Fənn qovluqlarına göndərilən sərbəst iş və ev tapşırıqları. Sərbəst iş bal ilə qəbul olunur və bal avtomatik jurnala düşür; bəyənilməyən iş rəylə qaytarılır — 0 yazılmır.	Independent work and homework submitted to subject folders. Independent work is accepted with points that go to the journal automatically; unsatisfactory work is returned with feedback — no zero is recorded.	Самостоятельные работы и домашние задания, отправленные в папки предметов. Самостоятельная работа принимается с баллом, который автоматически попадает в журнал; неудачная работа возвращается с отзывом — ноль не ставится.	Ders klasörlerine gönderilen bağımsız çalışmalar ve ev ödevleri. Bağımsız çalışma puanla kabul edilir ve puan otomatik olarak deftere geçer; beğenilmeyen çalışma geri bildirimle iade edilir — 0 yazılmaz.
Fənn seçilməyib.	No subject selected.	Предмет не выбран.	Ders seçilmedi.
Fənn və semestr	Subject and semester	Предмет и семестр	Ders ve dönem
Fənn və ya qovluq adı…	Subject or folder name…	Название предмета или папки…	Ders veya klasör adı…
Fənni və semestri seçin. Qovluq qaralama kimi yaranır; qruplara təyin edəndə aktivləşir.	Choose the subject and semester. The folder is created as a draft and becomes active when assigned to groups.	Выберите предмет и семестр. Папка создаётся как черновик и становится активной после назначения группам.	Dersi ve dönemi seçin. Klasör taslak olarak oluşturulur; gruplara atandığında etkinleşir.
Fənnin təsdiqlənmiş sillabusu yoxdursa mövzular gəlmir — mövzuları özünüz əlavə edə və ya sillabus təsdiqlənəndən sonra «Sillabusla uzlaşdır» düyməsini basa bilərsiniz.	Topics are not imported if the subject has no approved syllabus — add topics yourself, or press “Sync with syllabus” once the syllabus is approved.	Если у предмета нет утверждённого силлабуса, темы не подтягиваются — добавьте темы сами или нажмите «Согласовать с силлабусом» после его утверждения.	Dersin onaylı izlencesi yoksa konular gelmez — konuları kendiniz ekleyebilir veya izlence onaylandıktan sonra “İzlenceyle eşitle” düğmesine basabilirsiniz.
Gecikmə	Late	Опоздание	Gecikme
Gecikmə ilə açıqdır	Open with late submission	Открыто с опозданием	Gecikmeli açık
Gizlidir	Hidden	Скрыто	Gizli
Göndər	Submit	Отправить	Gönder
Göndərib	Submitted	Отправили	Gönderen
Göndərilib	Submitted	Отправлено	Gönderildi
Göndəriş	Submission	Отправка	Gönderim
Göndəriş rədd edildi.	Submission rejected.	Отправка отклонена.	Gönderim reddedildi.
Göndərişlər	Submissions	Отправки	Gönderimler
Göndərişlərim	My submissions	Мои отправки	Gönderimlerim
Göstərilməyib	Not specified	Не указано	Belirtilmedi
Hamısı	All	Все	Tümü
Hamısını seç	Select all	Выбрать все	Tümünü seç
Heç bir göndəriş seçilməyib.	No submissions selected.	Не выбрано ни одной отправки.	Hiçbir gönderim seçilmedi.
Hədəf semestr	Target semester	Целевой семестр	Hedef dönem
Hədəf semestrdə qovluq artıq var — o açılır.	A folder already exists in the target semester — opening it.	В целевом семестре папка уже есть — она открывается.	Hedef dönemde klasör zaten var — açılıyor.
Hədəf semestri seçin.	Choose the target semester.	Выберите целевой семестр.	Hedef dönemi seçin.
Həftə	Week	Неделя	Hafta
Həftə %(n)s	Week %(n)s	Неделя %(n)s	Hafta %(n)s
Hələ açılmayıb	Not open yet	Ещё не открыто	Henüz açılmadı
Hələ fənn qovluğu yoxdur	No subject folders yet	Папок предметов пока нет	Henüz ders klasörü yok
Hələ fənn qovluğunuz yoxdur	You have no subject folders yet	У вас пока нет папок предметов	Henüz ders klasörünüz yok
Hər fənn üçün tədris materialları, sərbəst iş və ev tapşırıqları bir qovluqda. Mövzular və sərbəst iş slotları təsdiqlənmiş sillabusdan gəlir.	Teaching materials, independent work and homework for each subject in one folder. Topics and independent work slots come from the approved syllabus.	Учебные материалы, самостоятельные работы и домашние задания по каждому предмету в одной папке. Темы и слоты самостоятельной работы берутся из утверждённого силлабуса.	Her ders için ders materyalleri, bağımsız çalışmalar ve ev ödevleri tek klasörde. Konular ve bağımsız çalışma slotları onaylı izlenceden gelir.
Hər iki sahəni boş saxlasanız tapşırıq həmişə açıq qalır.	If both fields are empty, the task stays open at all times.	Если оба поля пусты, задание всегда открыто.	İki alanı da boş bırakırsanız ödev her zaman açık kalır.
Keçid (https://…)	Link (https://…)	Ссылка (https://…)	Bağlantı (https://…)
Kod	Code	Код	Kod
Kod yalnız mətn kimi göstərilir — heç vaxt icra olunmur.	Code is shown as text only — it is never executed.	Код отображается только как текст — он никогда не выполняется.	Kod yalnızca metin olarak gösterilir — asla çalıştırılmaz.
Kodu göstər	Show code	Показать код	Kodu göster
Köçür	Copy	Перенести	Kopyala
Ləğv et	Cancel	Отменить	İptal et
Material	Material	Материал	Materyal
Material dərc edildi.	Material published.	Материал опубликован.	Materyal yayımlandı.
Material gizlədildi.	Material hidden.	Материал скрыт.	Materyal gizlendi.
Material qaralama kimi əlavə olundu — dərc edəndə tələbələr görəcək.	Material added as a draft — students will see it once you publish it.	Материал добавлен как черновик — студенты увидят его после публикации.	Materyal taslak olarak eklendi — yayımladığınızda öğrenciler görecek.
Material silindi.	Material deleted.	Материал удалён.	Materyal silindi.
Material silinsin? Tələbələr onu artıq görməyəcək.	Delete this material? Students will no longer see it.	Удалить материал? Студенты больше не будут его видеть.	Materyal silinsin mi? Öğrenciler artık görmeyecek.
Material yeniləndi.	Material updated.	Материал обновлён.	Materyal güncellendi.
Material əlavə et	Add material	Добавить материал	Materyal ekle
Material əlavə olundu və tələbələrə görünür.	Material added and visible to students.	Материал добавлен и виден студентам.	Materyal eklendi ve öğrencilere görünüyor.
Materialı redaktə et	Edit material	Редактировать материал	Materyali düzenle
Mövzu	Topic	Тема	Konu
Mövzu adı ilə axtar…	Search by topic name…	Поиск по названию темы…	Konu adına göre ara…
Mövzu gizlədildi.	Topic hidden.	Тема скрыта.	Konu gizlendi.
Mövzu silindi.	Topic deleted.	Тема удалена.	Konu silindi.
Mövzu silinsin?	Delete this topic?	Удалить тему?	Konu silinsin mi?
Mövzu yenidən görünür.	Topic is visible again.	Тема снова видна.	Konu yeniden görünüyor.
Mövzu yeniləndi.	Topic updated.	Тема обновлена.	Konu güncellendi.
Mövzu əlavə et	Add topic	Добавить тему	Konu ekle
Mövzu əlavə olundu.	Topic added.	Тема добавлена.	Konu eklendi.
Mövzular və sərbəst iş slotları təsdiqlənmiş sillabusla uzlaşdırılsın? Göndərişi olan heç nə silinmir.	Sync topics and independent work slots with the approved syllabus? Nothing with submissions is deleted.	Согласовать темы и слоты самостоятельной работы с утверждённым силлабусом? Ничего с отправками не удаляется.	Konular ve bağımsız çalışma slotları onaylı izlenceyle eşitlensin mi? Gönderimi olan hiçbir şey silinmez.
Mövzular, materiallar və ev tapşırıqları yeni semestrin qovluğuna köçürülür. Təyinatlar, son tarixlər və göndərişlər köçürülmür.	Topics, materials and homework are copied to the new semester's folder. Assignments, deadlines and submissions are not copied.	Темы, материалы и домашние задания переносятся в папку нового семестра. Назначения, сроки и отправки не переносятся.	Konular, materyaller ve ev ödevleri yeni dönemin klasörüne kopyalanır. Atamalar, son tarihler ve gönderimler kopyalanmaz.
Mövzunu gizlət	Hide topic	Скрыть тему	Konuyu gizle
Mövzunu göstər	Show topic	Показать тему	Konuyu göster
Mövzunu redaktə et	Edit topic	Редактировать тему	Konuyu düzenle
Mövzunu sil	Delete topic	Удалить тему	Konuyu sil
Mövzunun adı	Topic title	Название темы	Konu başlığı
Müəllim onu gizlədib və ya bu fənndə qeydiyyatınız yoxdur.	The teacher has hidden it, or you are not enrolled in this subject.	Преподаватель скрыл это, или вы не записаны на этот предмет.	Öğretmen bunu gizlemiş veya bu derse kaydınız yok.
Müəllim qovluğu qrupunuza təyin edəndə burada görünəcək və bildiriş alacaqsınız.	It will appear here, and you will be notified, once a teacher assigns a folder to your group.	Папка появится здесь, и вы получите уведомление, когда преподаватель назначит её вашей группе.	Öğretmen klasörü grubunuza atadığında burada görünecek ve bildirim alacaksınız.
Müəllimin rəyi	Teacher's feedback	Отзыв преподавателя	Öğretmenin geri bildirimi
Müəllimlərinizin paylaşdığı tədris materialları, sərbəst iş və ev tapşırıqları. Sərbəst iş qəbul olunanda bal avtomatik jurnala düşür.	Teaching materials, independent work and homework shared by your teachers. When independent work is accepted, the points go to the journal automatically.	Учебные материалы, самостоятельные работы и домашние задания от ваших преподавателей. Когда самостоятельная работа принята, балл автоматически попадает в журнал.	Öğretmenlerinizin paylaştığı ders materyalleri, bağımsız çalışmalar ve ev ödevleri. Bağımsız çalışma kabul edildiğinde puan otomatik olarak deftere geçer.
Mətn cavabı	Text answer	Текстовый ответ	Metin cevabı
Məzmun	Content	Содержимое	İçerik
Məzmunu hazırlayın və «Qruplar və son tarixlər» tabından qruplara təyin edin: ilk təyinatda qovluq avtomatik aktivləşir.	Prepare the content and assign it to groups on the “Groups and deadlines” tab: the folder becomes active automatically on the first assignment.	Подготовьте содержимое и назначьте группам на вкладке «Группы и сроки»: при первом назначении папка активируется автоматически.	İçeriği hazırlayın ve “Gruplar ve son tarihler” sekmesinden gruplara atayın: ilk atamada klasör otomatik etkinleşir.
Naməlum əməl.	Unknown action.	Неизвестное действие.	Bilinmeyen işlem.
Naviqasiya	Navigation	Навигация	Gezinme
Növ	Type	Тип	Tür
Nəticə: %(count)d göndəriş	Results: %(count)d submissions	Результатов: %(count)d отправок	Sonuç: %(count)d gönderim
Nəticə: %(count)d qovluq	Results: %(count)d folders	Результатов: %(count)d папок	Sonuç: %(count)d klasör
Nəyi düzəltməlidir?	What should be fixed?	Что нужно исправить?	Neyi düzeltmeli?
Obyekt tapılmadı və ya artıq mövcud deyil.	The item was not found or no longer exists.	Объект не найден или больше не существует.	Nesne bulunamadı veya artık mevcut değil.
Oxşar göndərişlər	Similar submissions	Похожие отправки	Benzer gönderimler
Oxşarlıq	Similarity	Сходство	Benzerlik
Oxşarlıq qərarı geri alındı.	The similarity decision was reverted.	Решение о сходстве отменено.	Benzerlik kararı geri alındı.
Oxşarlıq «plagiat deyil» kimi qeyd olundu.	The similarity was marked as “not plagiarism”.	Совпадение отмечено как «не плагиат».	Benzerlik “intihal değil” olarak işaretlendi.
Plagiat deyil	Not plagiarism	Не плагиат	İntihal değil
Proqramlaşdırma dili	Programming language	Язык программирования	Programlama dili
Pəncərə	Window	Окно	Pencere
QARALAMA	DRAFT	ЧЕРНОВИКИ	TASLAK
QAYTARILIB	RETURNED	ВОЗВРАЩЕНО	İADE EDİLDİ
QOVLUQLAR	FOLDERS	ПАПКИ	KLASÖRLER
Qaralama	Draft	Черновик	Taslak
Qaralama kimi saxla	Save as draft	Сохранить как черновик	Taslak olarak kaydet
Qaralama saxlanıldı — müəllim hələ görmür.	Draft saved — the teacher cannot see it yet.	Черновик сохранён — преподаватель его пока не видит.	Taslak kaydedildi — öğretmen henüz görmüyor.
Qaralamadakı fayllar	Files in the draft	Файлы в черновике	Taslaktaki dosyalar
Qaytar	Return	Вернуть	İade et
Qaytarma və rədd üçün məcburidir (ən azı 5 simvol)	Required for returning and rejecting (at least 5 characters)	Обязательно для возврата и отклонения (не менее 5 символов)	İade ve ret için zorunludur (en az 5 karakter)
Qaytarılmış işin yenidən göndərilməsi son tarixdən asılı olmayaraq açıqdır.	Returned work can be resubmitted regardless of the deadline.	Возвращённую работу можно отправить повторно независимо от срока.	İade edilen çalışma son tarihten bağımsız olarak yeniden gönderilebilir.
Qaytarılıb: %(n)s	Returned: %(n)s	Возвращено: %(n)s	İade edildi: %(n)s
Qovluq	Folder	Папка	Klasör
Qovluq aktivdir — təyin olunmuş qruplar onu görür.	The folder is active — assigned groups can see it.	Папка активна — назначенные группы её видят.	Klasör etkin — atanan gruplar onu görüyor.
Qovluq arxivdədir — yalnız oxu rejimi.	The folder is archived — read-only mode.	Папка в архиве — только для чтения.	Klasör arşivde — salt okunur mod.
Qovluq arxivləndi — yalnız oxu rejimindədir.	The folder has been archived — it is now read-only.	Папка архивирована — теперь только для чтения.	Klasör arşivlendi — artık salt okunur.
Qovluq arxivlənsin? Tələbələr onu görməyəcək, məzmun yalnız oxu rejimində qalacaq.	Archive the folder? Students will no longer see it and the content will become read-only.	Архивировать папку? Студенты перестанут её видеть, содержимое станет только для чтения.	Klasör arşivlensin mi? Öğrenciler görmeyecek, içerik salt okunur kalacak.
Qovluq boşdur	The folder is empty	Папка пуста	Klasör boş
Qovluq bölmələri	Folder sections	Разделы папки	Klasör bölümleri
Qovluq qaralamadır — tələbələr onu görmür.	The folder is a draft — students cannot see it.	Папка — черновик, студенты её не видят.	Klasör taslak — öğrenciler onu görmüyor.
Qovluq qaralamaya qaytarıldı.	The folder was moved back to draft.	Папка возвращена в черновики.	Klasör taslağa geri alındı.
Qovluq seçilən qruplara təyin olundu.	The folder was assigned to the selected groups.	Папка назначена выбранным группам.	Klasör seçilen gruplara atandı.
Qovluq silinib və ya ona baxmaq hüququnuz yoxdur.	The folder was deleted or you do not have access to it.	Папка удалена или у вас нет к ней доступа.	Klasör silinmiş veya onu görme yetkiniz yok.
Qovluq sillabusla uzlaşdırıldı.	The folder was synced with the syllabus.	Папка согласована с силлабусом.	Klasör izlenceyle eşitlendi.
Qovluq tapılmadı	Folder not found	Папка не найдена	Klasör bulunamadı
Qovluq və ya tapşırıq tapılmadı	Folder or task not found	Папка или задание не найдены	Klasör veya ödev bulunamadı
Qovluq yaradıldı — mövzular və sərbəst iş slotları sillabusdan çəkildi.	Folder created — topics and independent work slots were imported from the syllabus.	Папка создана — темы и слоты самостоятельной работы взяты из силлабуса.	Klasör oluşturuldu — konular ve bağımsız çalışma slotları izlenceden alındı.
Qovluq yaratmaq üçün sizə fənn açılışı (qrup) təyin olunmalıdır.	To create a folder, you must be assigned a course offering (group).	Чтобы создать папку, вам должна быть назначена учебная группа по предмету.	Klasör oluşturmak için size bir ders açılışı (grup) atanmış olmalıdır.
Qovluq yeni semestrə köçürüldü.	The folder was copied to the new semester.	Папка перенесена в новый семестр.	Klasör yeni döneme kopyalandı.
Qovluq yeniləndi.	Folder updated.	Папка обновлена.	Klasör güncellendi.
Qovluqda hələ dərc edilmiş məzmun yoxdur	The folder has no published content yet	В папке пока нет опубликованного содержимого	Klasörde henüz yayımlanmış içerik yok
Qovluqda tapşırıq yoxdur.	The folder has no tasks.	В папке нет заданий.	Klasörde ödev yok.
Qovluqlara qayıt	Back to folders	Вернуться к папкам	Klasörlere dön
Qovluqlarıma qayıt	Back to my folders	Вернуться к моим папкам	Klasörlerime dön
Qovluğu redaktə et	Edit folder	Редактировать папку	Klasörü düzenle
Qovluğu tədris etdiyiniz qruplara təyin edin — tələbələr yalnız təyin olunmuş qovluğu görür. Sərbəst iş balı yalnız bir qovluqdan qəbul edilir.	Assign the folder to the groups you teach — students only see assigned folders. Independent work points are accepted from one folder only.	Назначьте папку группам, которые вы ведёте, — студенты видят только назначенные папки. Баллы за самостоятельную работу принимаются только из одной папки.	Klasörü ders verdiğiniz gruplara atayın — öğrenciler yalnızca atanan klasörü görür. Bağımsız çalışma puanı yalnızca bir klasörden kabul edilir.
Qovluğun adı	Folder name	Название папки	Klasör adı
Qoşma silindi.	Attachment removed.	Вложение удалено.	Ek silindi.
Qoşma silinsin?	Remove this attachment?	Удалить вложение?	Ek silinsin mi?
Qoşma əlavə et	Add attachment	Добавить вложение	Ek ekle
Qoşmanı sil	Remove attachment	Удалить вложение	Eki sil
Qrup	Group	Группа	Grup
Qrupa təyinat	Group assignment	Назначение группам	Gruba atama
Qruplar və son tarixlər	Groups and deadlines	Группы и сроки	Gruplar ve son tarihler
Qrupun təyinatı ləğv edildi — göndərişlər saxlanılır.	The group assignment was cancelled — submissions are kept.	Назначение группе отменено — отправки сохранены.	Grup ataması iptal edildi — gönderimler saklanıyor.
QƏBUL / YOXLANILIB	ACCEPTED / CHECKED	ПРИНЯТО / ПРОВЕРЕНО	KABUL / KONTROL EDİLDİ
Qəbul edildi — bal jurnala düşdü.	Accepted — the points were recorded in the journal.	Принято — балл внесён в журнал.	Kabul edildi — puan deftere geçti.
Qəbul edildi — bal jurnala ötürülmək üçün növbədədir.	Accepted — the points are queued for the journal.	Принято — балл в очереди на передачу в журнал.	Kabul edildi — puan deftere aktarılmak üzere sırada.
Qəbul edildi, amma jurnal balı qəbul etmədi: %(reason)s	Accepted, but the journal did not accept the points: %(reason)s	Принято, но журнал не принял балл: %(reason)s	Kabul edildi, ancak defter puanı kabul etmedi: %(reason)s
Qəbul et və jurnala yaz	Accept and record in journal	Принять и внести в журнал	Kabul et ve deftere yaz
Qəbul et — eyni bal (sərbəst iş)	Accept — same points (independent work)	Принять — одинаковый балл (самостоятельная работа)	Kabul et — aynı puan (bağımsız çalışma)
Qərar	Decision	Решение	Karar
Qərarı geri al	Revert decision	Отменить решение	Kararı geri al
Redaktə et	Edit	Редактировать	Düzenle
Redaktədə yeni fayl seçməsəniz köhnə fayl qalır. Sənəd, təqdimat, arxiv, kod faylı və ya şəkil; icra olunan fayllar qəbul edilmir.	When editing, the old file is kept unless you choose a new one. Documents, presentations, archives, code files or images; executable files are not accepted.	При редактировании старый файл сохраняется, если не выбрать новый. Документы, презентации, архивы, файлы кода или изображения; исполняемые файлы не принимаются.	Düzenlemede yeni dosya seçmezseniz eski dosya kalır. Belge, sunum, arşiv, kod dosyası veya görsel; çalıştırılabilir dosyalar kabul edilmez.
RƏDD EDİLİB	REJECTED	ОТКЛОНЕНО	REDDEDİLDİ
Rədd et	Reject	Отклонить	Reddet
Rədd ləğv edildi — tələbə yenidən göndərə bilər.	Rejection cancelled — the student can resubmit.	Отклонение отменено — студент может отправить заново.	Ret iptal edildi — öğrenci yeniden gönderebilir.
Rədd yekundur — tələbə yenidən göndərə bilməz (rəddi sonra ləğv etmək olar).	Rejection is final — the student cannot resubmit (the rejection can be cancelled later).	Отклонение окончательно — студент не сможет отправить заново (отклонение можно отменить позже).	Ret kesindir — öğrenci yeniden gönderemez (ret daha sonra iptal edilebilir).
Rəddi ləğv et	Cancel rejection	Отменить отклонение	Reddi iptal et
Rəqəm düzgün yazılmayıb.	The number is not valid.	Число указано неверно.	Sayı geçerli değil.
Rəy	Feedback	Отзыв	Geri bildirim
Rəy (istəyə görə)	Feedback (optional)	Отзыв (необязательно)	Geri bildirim (isteğe bağlı)
Rəylə qaytar	Return with feedback	Вернуть с отзывом	Geri bildirimle iade et
Sahibi:	Owner:	Владелец:	Sahibi:
Semestr	Semester	Семестр	Dönem
Semestr tapılmadı.	Semester not found.	Семестр не найден.	Dönem bulunamadı.
Semestrsiz	No semester	Без семестра	Dönemsiz
Seçilib	Selected	Выбрано	Seçildi
Seçilən qruplara təyin et	Assign to selected groups	Назначить выбранным группам	Seçilen gruplara ata
Seçilən qruplardan bəzisini siz tədris etmirsiniz.	You do not teach some of the selected groups.	Некоторые из выбранных групп вы не ведёте.	Seçilen grupların bazılarında ders vermiyorsunuz.
Seçin	Select	Выберите	Seçin
Sil	Delete	Удалить	Sil
Sillabusdan	From syllabus	Из силлабуса	İzlenceden
Sillabusla uzlaşdır	Sync with syllabus	Согласовать с силлабусом	İzlenceyle eşitle
Sillabusla uzlaşdırılıb:	Synced with syllabus:	Согласовано с силлабусом:	İzlenceyle eşitlendi:
Siyahıda yalnız sizin tədris etdiyiniz fənn açılışları var.	Only course offerings you teach are listed.	В списке только группы, которые вы ведёте.	Listede yalnızca ders verdiğiniz ders açılışları var.
Slot %(n)s · maks. %(points)s bal	Slot %(n)s · max. %(points)s points	Слот %(n)s · макс. %(points)s баллов	Slot %(n)s · en fazla %(points)s puan
Son tarix	Deadline	Срок	Son tarih
Son tarix götürüldü — tapşırıq həmişə açıqdır.	Deadline removed — the task is always open.	Срок снят — задание всегда открыто.	Son tarih kaldırıldı — ödev her zaman açık.
Son tarix keçib — göndərsəniz gecikmə qeyd olunacaq.	The deadline has passed — if you submit, it will be marked as late.	Срок истёк — при отправке будет отмечено опоздание.	Son tarih geçti — gönderirseniz gecikme kaydedilecek.
Son tarix saxlanıldı.	Deadline saved.	Срок сохранён.	Son tarih kaydedildi.
Son tarix yoxdur	No deadline	Без срока	Son tarih yok
Son tarix — %(group)s	Deadline — %(group)s	Срок — %(group)s	Son tarih — %(group)s
Son tarix:	Deadline:	Срок:	Son tarih:
Son tarixdən sonra	After the deadline	После срока	Son tarihten sonra
Son tarixdən sonra göndərilib	Submitted after the deadline	Отправлено после срока	Son tarihten sonra gönderildi
Status	Status	Статус	Durum
Süzgəcləri dəyişin və ya axtarış sözünü qısaldın.	Change the filters or shorten the search term.	Измените фильтры или сократите поисковый запрос.	Filtreleri değiştirin veya arama ifadesini kısaltın.
Süzgəcləri dəyişin və ya bütün statusları seçin.	Change the filters or select all statuses.	Измените фильтры или выберите все статусы.	Filtreleri değiştirin veya tüm durumları seçin.
Süzgəcə uyğun göndəriş yoxdur	No submissions match the filters	Нет отправок, подходящих под фильтры	Filtreye uyan gönderim yok
Süzgəcə uyğun qovluq yoxdur	No folders match the filters	Нет папок, подходящих под фильтры	Filtreye uyan klasör yok
Səbəb	Reason	Причина	Neden
Səbəb:	Reason:	Причина:	Neden:
Sərbəst iş	Independent work	Самостоятельная работа	Bağımsız çalışma
Sərbəst iş balı	Independent work points	Баллы за самостоятельную работу	Bağımsız çalışma puanı
Sərbəst iş strukturu %(option)s (cəmi %(total)s bal) sillabusdan gəlir — əlavə sərbəst iş yaradılmır.	The independent work structure %(option)s (%(total)s points in total) comes from the syllabus — no extra independent work can be created.	Структура самостоятельной работы %(option)s (всего %(total)s баллов) задаётся силлабусом — дополнительную самостоятельную работу создать нельзя.	Bağımsız çalışma yapısı %(option)s (toplam %(total)s puan) izlenceden gelir — ek bağımsız çalışma oluşturulamaz.
Sərbəst iş: %(option)s	Independent work: %(option)s	Самостоятельная работа: %(option)s	Bağımsız çalışma: %(option)s
Tapşırıq	Task	Задание	Ödev
Tapşırıq arxivləndi.	Task archived.	Задание архивировано.	Ödev arşivlendi.
Tapşırıq arxivlənsin? Göndərişlər saxlanılır, tələbələr tapşırığı görməyəcək.	Archive this task? Submissions are kept; students will no longer see the task.	Архивировать задание? Отправки сохранятся, студенты не будут видеть задание.	Ödev arşivlensin mi? Gönderimler saklanır, öğrenciler ödevi görmeyecek.
Tapşırıq bərpa olundu.	Task restored.	Задание восстановлено.	Ödev geri yüklendi.
Tapşırıq dərc edildi — tələbələrə bildiriş göndərildi.	Task published — students have been notified.	Задание опубликовано — студентам отправлено уведомление.	Ödev yayımlandı — öğrencilere bildirim gönderildi.
Tapşırıq dərc edilsin? Təyin olunmuş qrupların tələbələrinə bildiriş gedəcək.	Publish this task? Students in the assigned groups will be notified.	Опубликовать задание? Студенты назначенных групп получат уведомление.	Ödev yayımlansın mı? Atanan grupların öğrencilerine bildirim gidecek.
Tapşırıq gizlədildi.	Task hidden.	Задание скрыто.	Ödev gizlendi.
Tapşırıq silindi.	Task deleted.	Задание удалено.	Ödev silindi.
Tapşırıq yeniləndi.	Task updated.	Задание обновлено.	Ödev güncellendi.
Tapşırığa şablon, nümunə və ya məlumat faylı əlavə edə bilərsiniz (ən çox 10).	You can attach a template, a sample or a data file to the task (up to 10).	К заданию можно прикрепить шаблон, пример или файл данных (не более 10).	Ödeve şablon, örnek veya veri dosyası ekleyebilirsiniz (en fazla 10).
Tapşırığı redaktə et	Edit task	Редактировать задание	Ödevi düzenle
Tapşırığın şərti	Task instructions	Условие задания	Ödev yönergesi
Tarix və saat düzgün seçilməyib.	The date and time are not valid.	Дата и время указаны неверно.	Tarih ve saat geçerli değil.
Tarixçə	History	История	Geçmiş
Toplu əməl	Bulk action	Массовое действие	Toplu işlem
Toplu əməl seçilməyib.	No bulk action selected.	Массовое действие не выбрано.	Toplu işlem seçilmedi.
Tələbə	Student	Студент	Öğrenci
Tələbələrdən gizlət	Hide from students	Скрыть от студентов	Öğrencilerden gizle
Tələbənin qalan sərbəst iş limiti: %(remaining)s / %(max_total)s	Student's remaining independent work limit: %(remaining)s / %(max_total)s	Оставшийся лимит самостоятельной работы студента: %(remaining)s / %(max_total)s	Öğrencinin kalan bağımsız çalışma sınırı: %(remaining)s / %(max_total)s
Təsdiq edirsiniz?	Are you sure?	Вы уверены?	Emin misiniz?
Təsdiqlənmiş sillabus tapılmadı — struktur dəyişmədi.	No approved syllabus was found — the structure was not changed.	Утверждённый силлабус не найден — структура не изменена.	Onaylı izlence bulunamadı — yapı değişmedi.
Təsvir	Description	Описание	Açıklama
Təsvir / qeyd	Description / note	Описание / заметка	Açıklama / not
Tətbiq et	Apply	Применить	Uygula
Təyinat bu qovluğa aid deyil.	The assignment does not belong to this folder.	Назначение не относится к этой папке.	Atama bu klasöre ait değil.
Uyğun fənn tapılmadı	No matching subject found	Подходящий предмет не найден	Uygun ders bulunamadı
Uyğun mövzu tapılmadı	No matching topic found	Подходящая тема не найдена	Uygun konu bulunamadı
Uzantıları boş saxlasanız sənəd, kod və şəkil faylları qəbul olunur.	If extensions are left empty, document, code and image files are accepted.	Если расширения не указаны, принимаются документы, файлы кода и изображения.	Uzantıları boş bırakırsanız belge, kod ve görsel dosyaları kabul edilir.
YEKUNLAŞIB	COMPLETED	ЗАВЕРШЕНО	TAMAMLANDI
YOXLAMA GÖZLƏYİR	AWAITING REVIEW	ОЖИДАЕТ ПРОВЕРКИ	KONTROL BEKLİYOR
YOXLANILIR	UNDER REVIEW	НА ПРОВЕРКЕ	KONTROL EDİLİYOR
Yalnız bayraqlananlar	Flagged only	Только отмеченные	Yalnızca işaretlenenler
Yalnız gecikənlər	Late only	Только с опозданием	Yalnızca gecikenler
Yarat	Create	Создать	Oluştur
Yekun	Completed	Итог	Tamamlanan
Yekunlaşıb	Completed	Завершено	Tamamlandı
Yeni ev tapşırığı	New homework	Новое домашнее задание	Yeni ev ödevi
Yeni fənn qovluğu	New subject folder	Новая папка предмета	Yeni ders klasörü
Yeni material	New material	Новый материал	Yeni materyal
Yeni mövzu	New topic	Новая тема	Yeni konu
Yeni qovluq	New folder	Новая папка	Yeni klasör
Yoxlama gözləyir: %(n)s	Awaiting review: %(n)s	Ожидают проверки: %(n)s	Kontrol bekliyor: %(n)s
Yoxlama növbəsi boşdur	The review queue is empty	Очередь проверки пуста	Kontrol kuyruğu boş
Yoxlanıldı	Checked	Проверено	Kontrol edildi
Yoxlanıldı (ev tapşırığı)	Checked (homework)	Проверено (домашнее задание)	Kontrol edildi (ev ödevi)
Yoxlanılır	Under review	На проверке	Kontrol ediliyor
Yüklənir…	Loading…	Загрузка…	Yükleniyor…
Yüksək oxşarlıq	High similarity	Высокое сходство	Yüksek benzerlik
baxış gözləyən iş	work awaiting review	работы, ожидающие проверки	kontrol bekleyen çalışma
gecikib	late	с опозданием	gecikmeli
gecikmə ilə	late allowed	с опозданием	gecikmeli
göndərilmiş, baxılmamış iş	submitted, not yet reviewed	отправлено, ещё не проверено	gönderilmiş, henüz kontrol edilmemiş
göndərilməyi gözləyir	waiting to be submitted	ожидают отправки	gönderilmeyi bekliyor
maks. %(points)s bal	max. %(points)s points	макс. %(points)s баллов	en fazla %(points)s puan
qovluq var	folder exists	папка уже есть	klasör var
rəyə görə yenidən işləyin	revise based on the feedback	доработайте по отзыву	geri bildirime göre yeniden çalışın
sərbəst iş başqa qovluqdan	independent work from another folder	самостоятельная работа из другой папки	bağımsız çalışma başka klasörden
sərbəst iş buradan	independent work from this folder	самостоятельная работа из этой папки	bağımsız çalışma buradan
«Yeni qovluq» ilə tədris etdiyiniz fənn üçün qovluq yaradın — mövzular və sərbəst iş slotları sillabusdan avtomatik çəkiləcək.	Use “New folder” to create a folder for a subject you teach — topics and independent work slots will be imported from the syllabus automatically.	Создайте папку для своего предмета кнопкой «Новая папка» — темы и слоты самостоятельной работы подтянутся из силлабуса автоматически.	“Yeni klasör” ile ders verdiğiniz ders için klasör oluşturun — konular ve bağımsız çalışma slotları izlenceden otomatik alınacak.
Ümumi	General	Общее	Genel
Ümumi (mövzusuz)	General (no topic)	Общее (без темы)	Genel (konusuz)
Ümumi (mövzuya bağlı olmayan)	General (not linked to a topic)	Общее (без привязки к теме)	Genel (konuya bağlı olmayan)
İcazəli uzantılar	Allowed extensions	Разрешённые расширения	İzin verilen uzantılar
İcazəli: %(ext)s	Allowed: %(ext)s	Разрешено: %(ext)s	İzin verilen: %(ext)s
İzah	Explanation	Пояснение	Açıklama
İş göndərildi (son tarixdən sonra — gecikmə qeyd olundu).	Work submitted (after the deadline — marked as late).	Работа отправлена (после срока — отмечено опоздание).	Çalışma gönderildi (son tarihten sonra — gecikme kaydedildi).
İş göndərildi — müəllim yoxlayandan sonra nəticəni görəcəksiniz.	Work submitted — you will see the result after the teacher reviews it.	Работа отправлена — результат появится после проверки преподавателем.	Çalışma gönderildi — öğretmen kontrol ettikten sonra sonucu göreceksiniz.
İş müəllimə göndərilsin? Göndərdikdən sonra müəllim yoxlayana qədər dəyişə bilməzsiniz.	Submit the work to the teacher? After submitting you cannot change it until the teacher reviews it.	Отправить работу преподавателю? После отправки изменить её нельзя до проверки.	Çalışma öğretmene gönderilsin mi? Gönderdikten sonra öğretmen kontrol edene kadar değiştiremezsiniz.
İş rəylə qaytarıldı — tələbə yenidən göndərə bilər.	The work was returned with feedback — the student can resubmit.	Работа возвращена с отзывом — студент может отправить заново.	Çalışma geri bildirimle iade edildi — öğrenci yeniden gönderebilir.
Əlavə şərt yazılmayıb.	No additional instructions.	Дополнительных условий нет.	Ek yönerge yazılmamış.
Əməl alınmadı — bağlantını yoxlayıb yenidən cəhd edin.	The action failed — check your connection and try again.	Действие не выполнено — проверьте соединение и повторите попытку.	İşlem başarısız oldu — bağlantınızı kontrol edip tekrar deneyin.
Əməllər	Actions	Действия	İşlemler
Ən azı bir qrup seçin.	Select at least one group.	Выберите хотя бы одну группу.	En az bir grup seçin.
Ən çox %(count)s fayl, hər biri %(size)s MB-a qədər.	Up to %(count)s files, each up to %(size)s MB.	Не более %(count)s файлов, каждый до %(size)s МБ.	En fazla %(count)s dosya, her biri %(size)s MB'a kadar.
Əvvəlki cəhdlər	Previous attempts	Предыдущие попытки	Önceki denemeler
"""


def rows():
    context = ""
    for line in DATA.strip("\n").split("\n"):
        if not line.strip():
            continue
        if line.startswith("# "):
            context = line[2:].strip()
            continue
        msgid, en, ru, tr = line.split("\t")
        yield (context, msgid), (en, ru, tr)


def main():
    strings = dict(rows())
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in strings.items():
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
