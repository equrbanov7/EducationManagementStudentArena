# EMS Arena — terminologiya lüğəti (az / en / ru / tr)

Bu sənəd tərcümə üçün **məcburi** qarşılıqları müəyyən edir. Məqsəd üslub deyil,
**məna sabitliyi**: eyni anlayış bütün ekranlarda eyni sözlə adlanmalıdır, əks
halda istifadəçi iki fərqli şey olduğunu düşünür.

Lüğət 2026-07-31 tarixli auditdən sonra yazılıb. O auditdə tapılan real
zədələr aşağıda «tələ» kimi qeyd olunub — həmin sözlər çoxmənalıdır və maşın
tərcüməsi ardıcıl olaraq yanlış mənanı seçib.

## Necə istifadə olunur

Yeni sətir əlavə edəndə və ya tərcümə düzəldəndə:

1. Anlayış bu cədvəldədirsə — **məcburi** qarşılığı işlət, sinonim seçmə.
2. Cədvəldə yoxdursa və anlayış təkrarlanandırsa — sətri buraya əlavə et.
3. `pgettext` üçün msgctxt həmişə ver (`app.surface.role`), çünki kontekstsiz
   msgid-lər `makemessages` yeniləmələrində sürüşməyə açıqdır.

CI qapısı: `python scripts/check_i18n_catalogs.py` — placeholder uyğunsuzluğunu
və xam açar sızmasını dayandırır, lakin **məna** yoxlaya bilmir. Məna bu
sənədin və nəzərdən keçirənin öhdəsindədir.

## Akademik struktur

| Anlayış | az | en | ru | tr |
|---|---|---|---|---|
| Fakültə | fakültə | faculty | факультет | fakülte |
| Kafedra | kafedra | department | кафедра | bölüm |
| İxtisas | ixtisas | specialization | специальность | uzmanlık |
| Struktur bölmə | struktur bölmə | organizational unit | структурное подразделение | organizasyon birimi |
| Tədris ili | tədris ili | academic year | учебный год | eğitim yılı |
| Semestr | semestr | semester | семестр | dönem |
| Fənn | fənn | subject | предмет | ders |
| Dərs (offering) | dərs | course offering | курс | ders açılışı |
| Qrup | qrup | group | группа | grup |
| Jurnal | jurnal | journal | журнал | yoklama defteri |

> **Tələ.** `fakültə` və `kafedra` ingilis dilində asanlıqla qarışır. `faculty`
> **yalnız** fakültə deməkdir (müəllim heyəti mənasında İŞLƏDİLMİR); kafedra
> həmişə `department`-dir.

## Qiymətləndirmə

| Anlayış | az | en | ru | tr |
|---|---|---|---|---|
| Bal (rəqəm) | bal | score | балл | puan |
| Qiymət (hərf/yekun) | qiymət | grade | оценка | not |
| Maksimal bal | maks. bal | max score | макс. балл | maks. puan |
| Qiymətləndirmək | qiymətləndirmək | to grade | оценивать | değerlendirmek |
| Kollokvium | kollokvium | colloquium | коллоквиум | ara sınav (kolokyum) |
| Sərbəst iş | sərbəst iş | independent work | самостоятельная работа | bağımsız çalışma |
| Davamiyyət | davamiyyət | attendance | посещаемость | devam durumu |

> **Tələ — «qiymət».** Azərbaycan dilində `qiymət` həm *grade*, həm *price*
> deməkdir. Auditdə assignment app-ının BÜTÜN qiymətləndirmə səthləri RU
> «Цена», TR «Fiyat» (yəni məhsul qiyməti) göstərirdi; bildirişdə tələbə
> «Цена была указана» oxuyurdu. RU `оценка`, TR `not` — başqa variant yoxdur.

> **Tələ — «bal».** RU-da `Мед` (arı balı) və TR-də `Bal` (yenə arı balı)
> kimi tərcümə olunmuşdu; labs app-da TR `Gol` (futbol qolu), RU `Счет`
> (faktura). Düzgün: RU `балл`, TR `puan`.

## İmtahan

| Anlayış | az | en | ru | tr |
|---|---|---|---|---|
| İmtahan | imtahan | exam | экзамен | sınav |
| Yekun imtahan | yekun imtahan | final exam | итоговый экзамен | final sınavı |
| Aralıq imtahan | aralıq imtahan | midterm | промежуточный экзамен | vize |
| Cəhd | cəhd | attempt | попытка | deneme |
| Sual bankı | sual bankı | question bank | банк вопросов | soru bankası |
| Bilet | bilet | ticket | билет | bilet |
| Zal / auditoriya | zal | hall | зал | salon |
| Oturum (sessiya) | sessiya | session | сессия | oturum |
| Nəzarətçi | nəzarətçi | invigilator | наблюдатель | gözetmen |
| İmtahan mərkəzi | imtahan mərkəzi | examination centre | экзаменационный центр | sınav merkezi |
| Apellyasiya | apellyasiya | appeal | апелляция | itiraz |

### Cəhd statusları

| Açar | az | en | ru | tr |
|---|---|---|---|---|
| `draft` | Qaralama | Draft | Черновик | Taslak |
| `in_progress` | Davam edir | In progress | В процессе | Devam ediyor |
| `submitted` | Təqdim edilib | Submitted | Отправлена | Gönderildi |
| `expired` | Müddəti bitib | Expired | Истекла | Süresi doldu |

> **Tələ — `in_progress`.** 4 dildə də «Yoxlanılır / Pending processing /
> Проверка / Kontrol ediliyor» yazılmışdı. Bu status tələbənin imtahanı
> **hazırda yazdığını** bildirir; müəllim və imtahan mərkəzi canlı cəhdi
> bitmiş və yoxlanılan cəhd sanırdı — operativ səhv qərar mənbəyi.

### Nəzarət statusları

| Açar | az | en | ru | tr |
|---|---|---|---|---|
| `active` | Aktiv | Active | Активный | Aktif |
| `warned` | Xəbərdarlıq edilib | Warned | Предупреждён | Uyarıldı |
| `locked` | Bloklanıb | Locked | Заблокирован | Kilitlendi |
| `removed` | Uzaqlaşdırılıb | Removed | Удалён с экзамена | Sınavdan çıkarıldı |
| `resumed` | Davam etdirilib | Resumed | Возобновлён | Devam ettirildi |

> **Tələ.** Bu statuslar əvvəllər **düymə mətnləri** ilə əvəzlənmişdi:
> `removed` → «Sil», `resumed` → «Bərpa et», `locked` → «Bloklanmış tələbə
> yoxdur.» (boş siyahı mesajı). Status etiketi ilə əməliyyat düyməsi eyni
> kataloq girişini paylaşmamalıdır.

## Rollar və istifadəçilər

| Anlayış | az | en | ru | tr |
|---|---|---|---|---|
| Tələbə | tələbə | student | студент | öğrenci |
| Müəllim | müəllim | teacher | преподаватель | öğretmen |
| Dekan | dekan | dean | декан | dekan |
| Kafedra müdiri | kafedra müdiri | head of department | заведующий кафедрой | bölüm başkanı |
| Tyutor | tyutor | tutor | тьютор | danışman |
| İKT rəhbəri | İKT rəhbəri | ICT manager | руководитель ИКТ | BİT yöneticisi |
| Təşkilat | təşkilat | organization | организация | kuruluş |
| Üzvlük | üzvlük | membership | членство | üyelik |

## Ümumi əməliyyatlar

| Anlayış | az | en | ru | tr |
|---|---|---|---|---|
| Sil | sil | delete | удалить | sil |
| Birdəfəlik sil | birdəfəlik sil | delete permanently | удалить навсегда | kalıcı olarak sil |
| Bərpa et | bərpa et | restore | восстановить | geri yükle |
| Zibil qutusu | zibil qutusu | trash | корзина | çöp kutusu |
| Arxivlə | arxivlə | archive | архивировать | arşivle |
| Ləğv et | ləğv et | cancel | отмена | iptal |
| Sıfırla | sıfırla | reset | сбросить | sıfırla |
| Düzəliş (audited) | düzəliş | correction | исправление | düzeltme |

> **Tələ.** `sil` (delete) və `birdəfəlik sil` (permanent delete) fərqli
> əməliyyatlardır: birincisi soft-delete (Zibil qutusu, nəticələr qorunur),
> ikincisi bazadan tam silmə və yalnız cəhdi olmayan obyekt üçün mümkündür.
> Tərcümədə bu fərq itməməlidir.

## Yoxlama əmrləri

```bash
python scripts/check_i18n_catalogs.py --report
```

```bash
python manage.py compilemessages && python scripts/check_i18n_catalogs.py
```
