# Şübhəli ballar — rektor üçün qısa siyahı (metodologiya)

**Tarix:** 2026-09-03 · **Rejim:** YALNIZ OXU
**Excel:** `/Users/elvin/Desktop/RIM/Hesabat/SUBHELI_BALLAR_REKTOR_2026-09-03.xlsx`
**Rektor sənədi:** `/Users/elvin/Desktop/RIM/Hesabat/SUBHELI_BALLAR_REKTOR_2026-09-03.docx`
(+ `.pdf`, 31 səhifə) · generator `scratchpad/make_docx.py`
**Skript:** `scripts/legacy_audit/suspicious_grades.py`
**Şaxə:** `docs/suspicious-grades-report` (PR #122) — dəyişikliklər iş ağacındadır, commit EDİLMƏYİB

---

## 0. Bu sənəd nəyi əvəz edir

Əvvəlki `MENTIQ_ZIDDIYYETLERI.xlsx` **24 776 sətir** idi (A 17 107 · B 2 762 · C 4 907)
və sahibin qeyd etdiyi kimi **çox səs-küylü** idi. Bu iş həmin siyahını yenidən
qurmur — onun üzərində işləyir və sualı dəyişir:

> «Bal fərqi var?» → **«Bu bal fiziki olaraq mümkündürmü? Yoxsa kimsə əl ilə yazıb?»**

Nəticə (apellyasiya süzgəcindən sonra):

| Bölmə | Tapıntı | Tələbə | Hara |
|---|---:|---:|---|
| **Tier 1 — 100 % şübhəli** | **48** | **47** | rektor sənədi + Excel |
| **Tier 2 — əsas** (keçid xətti 51–55 · kəsr-ziddiyyəti) | **261** | **238** | rektor sənədi + Excel |
| Əlavə — köməkçi qaydalar (qayıb silinməsi · kütləvi qayıb · ardıcıllıq) | 697 | 461 | **yalnız Excel** |
| **İzahı olan — şübhəli SAYILMIR** | **96** | **78** | ayrıca vərəq |

Rəqəmlər şişirdilməyib; aşağıda **nəyin təmiz çıxdığı da açıq yazılıb**.

---

## 1. Təhlükəsizlik — heç nə yazılmayıb

| Baza | Necə açılıb |
|---|---|
| MyEdu MariaDB (`emsarena-legacy-source-rehearsal`, `127.0.0.1:50200/myedudb`) | `@@GLOBAL.read_only = 1` yoxlanılıb; hər sessiya `SET SESSION TRANSACTION READ ONLY` ilə açılıb |
| Köçürülmüş namizəd Postgres (`127.0.0.1:55433/emsarena_rehearsal_d44526b97cbc`) | `psycopg2` `set_session(readonly=True)` + `SET default_transaction_read_only = on` |
| Real `emsarena_db` | **ümumiyyətlə açılmayıb** |

Yalnız `SELECT` icra olunub; miqrasiya və ya `manage.py` yazı əmri işlədilməyib.

---

## 2. Bal şkalası — kodlaşdırmadan ƏVVƏL təsdiqlənib

`docs/migration/LEGACY_GIRISH_FORMULA.md` §1 və `apps/registrar/grading_scale.py`:

```
giriş = ROUND(davamiyyət + sərbəst_iş + seminar)      maks 50
        davamiyyət 0…10 · sərbəst iş 0…10 · seminar 0…30
çıxış (imtahan)                                        maks 50
yekun = giriş + çıxış                                  maks 100
keçid həddi = 51   (DEFAULT_LETTER_BANDS: E = 51, F < 51)
```

**Xarici dil / «akademik kommunikasiya» / «Level» kursları ayrı sxem işlədir**
(`MENTIQ_ZIDDIYYETLERI.md`, sinif A5L) — orada `çıxış > 50` normaldır və həmin
kurslar şkala qaydalarından **kənarda saxlanılıb**. Bu istisna olmasa idi,
təkcə `yekun` cədvəlində **240 yalançı müsbət** yaranırdı (bax §6).

---

## 3. Mənbələr

| Mənbə | Sətir | Nə verir |
|---|---:|---|
| `balvereqi_logs` (52 386 ixrac, parsinqdən sonra) | **902 602** tələbə sətri | müəllimin imzaladığı çap vərəqi: davamiyyət · sərbəst iş · seminar/lab · giriş · imtahan · güzəşt · **yekun** · təkrar imtahan · «(Kəsr)» bayrağı · **müəllim adı** · ixrac vaxtı |
| `yekun` | 17 194 | 2022/2023 Payız snapshot-u (`girish`, `imtahanda`, `yekun`, `kesr`, `guzest_*`) |
| `imthngrscxsblr` | 12 544 | imtahan giriş/çıxış cəhd tarixçəsi (`added_date` var, jurnal/semestr **yoxdur**) |
| `update_log` | 253 334 | jurnal xanalarının **dəyişmə tarixçəsi** (`old_value → new_value`, vaxt, tələbə, jurnal) |
| `allowed_qb` | 2 964 | sənədləşdirilmiş qayıb icazələri (hamısında fayl var) |

Çap vərəqi sətirlərində tələbə **`<tr class="user_<id>">`** ilə birbaşa göstərilir —
ad uyğunlaşdırmasına ehtiyac yoxdur, bu da `MENTIQ_ZIDDIYYETLERI.md` §1-də
təsvir edilən **şəxsiyyət açarı toqquşmasını** kökündən aradan qaldırır.

**Kim daxil edib?** Köhnə sxemdə `yekun` və `imthngrscxsblr` cədvəllərində
`created_by` / `updated_by` / `updated_at` sütunu **YOXDUR**, `update_log`-da isə
dəyişən istifadəçi qeyd olunmur. Ona görə «kim» sualına yeganə cavab
**çap vərəqinin üstündəki müəllim adı** və `balvereqi_logs.owner_id`-dir —
Excel-in «Müəllim üzrə» vərəqi budur. Bu, **ixracı edən** şəxsdir, mütləq
balı yazan deyil; vərəqdə açıq yazılıb.

---

## 3a. Apellyasiya / rəsmi düzəliş izi — nə axtarıldı, nə tapıldı

Sual: **qiymət dəyişiklikləri qanuni apellyasiya (etiraz) nəticəsi ola bilərmi?**
Cavab tapmaq üçün hər iki baza axtarıldı.

### Köhnə MyEdu bazası — apellyasiya saxlancı YOXDUR

**Cədvəl adları** `apel|appel|apply|etiraz|itiraz|sikay|shikay|complain|review|
correct|duzel|guzest|objection|revis|protest|appeal|muracie|xidmeti` naxışları ilə
axtarıldı. Bazanın **80 cədvəlinin** hamısı yoxlanıldı:

```
alerts_workers, allowed_qb, balvereqi_logs, books, books_order, curricula,
curricula_plan, curricula_plan_patok, curricula_tam, curricula_tasks,
curricula_tasks_content, curricula_tasks_content_teachers, departments,
ders_cedveli, exam_answers, exam_list, exam_questions, exam_question_topics,
exam_students_start, ferdi_plan, groups, holidays, imthngrscxsblr, journals,
journals_dates, journals_dates_added_by_teacher, journals_dates_parsed,
journals_dates_points, journals_dates_points_archive, journals_dates_rooms,
journals_files, journal_exam_joint, lessons, level_exams, level_exams_questions,
level_exams_topics, level_results, niq, notifications, notifications_groups,
notifications_logs, ntg, rooms, room_types, semestr_jurnal, sillabus,
sillabus_certificates, sillabus_dersin_islenme_formasi, sillabus_derslikler,
sillabus_eldeolunacaq_tecrubeler, sillabus_elmi_maraq, sillabus_imtahan_suallari,
sillabus_qarsilama_mesaji, sillabus_sem_muh, sillabus_serbest_is,
sillabus_tesviri_ve_meqsedi, sillabus_yoxlama_formasi, smestr, speciality,
students, students_login_logs, students_telegram, students_tg_reply,
track_student, turnirs, turnirs_joined_students, turnirs_questions,
turnirs_starts, turnir_results, turnir_schedule, turnir_students_answers,
umumi_orta_bal, update_log, workers, workers_login_logs, workers_permits,
xidmeti_muraciet, xidmeti_muraciet_files, yekun, yekun_24_02_2023, yekun_old
```

**Yeganə uyğunluq:** `xidmeti_muraciet` / `xidmeti_muraciet_files` — **2 sətir**,
məzmunu «Yüksək Texnologiyalar Məktəbi» təqdimat mətni və «lorem ipsum diolor
sit amet». Bu, sayt üçün xidməti müraciət/xəbər modulu idi, **apellyasiya deyil**.

**Sütun adları** üzrə axtarış (`reason|sebeb|comment|note|desc|why|izah|qeyd|
correct|duzel|guzest|…`) da apellyasiya sahəsi tapmadı. Xüsusilə:

| Cədvəl | Sütunlar | Səbəb sahəsi |
|---|---|---|
| `update_log` (253 334 dəyişiklik) | id, old_value, new_value, updated_at, sent, student_id, create_date, update_date, j_id | **YOXDUR** |
| `balvereqi_logs` (52 386 ixrac) | id, owner_id, uniqid, data, export_time | **YOXDUR** |
| `journals_dates_points.why` | var, amma **5 135 289 xanadan cəmi 28-i** doludur (0,0005 %) | praktiki olaraq işlədilməyib |
| `yekun_old`, `yekun_24_02_2023` | snapshot cədvəlləri | **0 sətir** |

### Köçürülmüş baza (DB A) — cədvəllər var, sətir yoxdur

Yeni EMSArena-da apellyasiya və düzəliş mexanizmi **mövcuddur**, lakin hamısı boşdur:

| Cədvəl | Sətir |
|---|---:|
| `appeals_appeal`, `appeals_appealitem`, `appeals_scoreadjustment` | **0 / 0 / 0** |
| `registrar_journalcorrection`, `registrar_componentscorecorrection` | **0 / 0** |
| `registrar_lessoncorrection`, `registrar_selfworkcorrection`, `registrar_courseworkcorrection` | **0 / 0 / 0** |
| `registrar_correctionreversal`, `registrar_legacygradereview` | **0 / 0** |

Yəni **köçürüləsi apellyasiya qeydi olmayıb**.

### Rəsmi izin YEGANƏ iki mənbəyi

| Mənbə | Həcm | Nəyi izah edir |
|---|---:|---|
| Çap vərəqinin **«Güzəşt Giriş/imtahan»** sütunu | **716** sətirdə sıfırdan fərqli | **bal güzəşti** — bal dəyişikliyini izah edə bilər |
| **`allowed_qb`** — sənədləşdirilmiş qayıb icazəsi | **2 964** icazə, 1 130 tələbə, **hamısında fayl** | **qayıb** — kəsr/qayıb qaydalarını izah edə bilər |

### Sütunun məntiqi — hansı iz hansı qaydaya AİDdir

Bu ayrım vacibdir və qəsdən dardır:

* **`allowed_qb` qayıb icazəsidir.** Bir günlük qayıb icazəsi nə şkaladan çıxmış
  balı (çıxış 72), nə də qaldırılmış imtahan balını izah edir. Ona görə o, yalnız
  **qayıba əsaslanan** qaydalarda yoxlanılır.
  > ⚠️ İlk keçiddə bu ayrım qoyulmamışdı və icazə bütün qaydalara tətbiq olunurdu —
  > nəticədə **4 Tier 1 sətri səhvən «izahı var»** kimi çıxarılmışdı (məsələn
  > «çıxış 72 · yekun 114» sətri bir günlük qayıb icazəsi ilə «izah» olunurdu).
  > Səhv tapıldı və düzəldildi.
* **Güzəşt sütunu bal güzəştidir** → yalnız bal dəyişikliyi qaydasında.
* **Tier 1 heç vaxt izah olunmur.** Şkaladan kənar bal nə güzəştlə, nə icazə ilə
  mümkün olmur; orada sütun yalnız **məlumat** üçündür və sətir siyahıdan
  **çıxarılmır**.

### Sütunun dəyərləri

| Dəyər | Nə vaxt | Sətir |
|---|---|---:|
| **BƏLİ** | uyğun güzəşt qeydi və ya qayıb icazəsi tapıldı → **«İzahı olan» vərəqinə köçürülür** | **96** |
| **XEYR** | qayıb qaydası üçün icazə tapılmadı / keçid-xətti üçün güzəşt sütunu «0 / 0» | 1 006 |
| **YOXLANA BİLMİR** | mənbədə belə iz ümumiyyətlə saxlanmır (Tier 1 və ardıcıllıq qaydaları) | 48 + 83 |

**İzahı olduğu üçün çıxarılan 96 tapıntı (78 tələbə):**

| Qayda | Çıxarıldı |
|---|---:|
| `T2-QAYIB-SİLİNMƏ` | **85** |
| `T2-KƏSR-ZİDDİYYƏTİ` | **11** |
| `T2-KEÇİD-XƏTTİ` | 0 — **173 keçid-xətti halının HEÇ BİRİNDƏ güzəşt qeydi yoxdur** |

> Sonuncu sətir rektor üçün ən vacib nəticələrdən biridir: keçid həddini keçən
> bal dəyişikliklərinin **heç birinin arxasında sistemdə rəsmi sənəd yoxdur**.

---

## 4. Qaydalar

### Tier 1 — «100 % şübhəli» (heç bir qanuni oxunuş yoxdur)

| Kod | Qayda | Sətir | Tələbə |
|---|---|---:|---:|
| `T1-ŞKALA` | Bal fiziki mümkün olan şkaladan kənardadır: `giriş > 50` və/və ya `çıxış > 50` və/və ya `yekun > 100` və/və ya `giriş + çıxış > 100` (xarici dil kursları istisna) | **43** | **42** |
| `T1-ABSURD` | Bal xanasında üç və daha çox rəqəmli dəyər: 3010, 2437, 411, 303, 181 | **5** | **5** |
| `T1-ARİFMETİKA` | `\|yekun − (giriş + çıxış)\| > 1` və nə təkrar imtahan, nə güzəşt sütunu ilə izah olunmur | **0** | **0** |

### Tier 2 — «yüksək ehtimal» (güclüdür, amma qanuni izah təsəvvür edilə bilər)

Rəqəmlər **apellyasiya süzgəcindən sonrakıdır** (izahı olan sətirlər çıxarılıb).

**Rektor sənədinə DÜŞƏN (əsas) qaydalar:**

| Kod | Qayda | Sətir | Tələbə |
|---|---|---:|---:|
| `T2-KEÇİD-XƏTTİ` | Eyni semestrdə **giriş balı dəyişmədən**, təkrar imtahan sütunu **boş qalaraq** imtahan balı qaldırılıb və yekun 51-i aşıb. **Rektor sənədinə yalnız yekunu 51–55 zolağına düşənlər salınıb (173).** | **202** *(173 əsas + 29 əlavə)* | **190** |
| `T2-KƏSR-ZİDDİYYƏTİ` | Semestrin son vərəqi eyni anda həm «(Kəsr)» yazır, həm ≥ 51 verir; sənədləşdirilmiş qayıb icazəsi yoxdur *(yalnız 2025 render dəyişikliyindən əvvəlki vərəqlər)* | **88** | **75** |

**Yalnız Excel əlavəsində qalan (köməkçi) qaydalar** — bunlar rektor sənədinə
qəsdən salınmayıb, çünki hər birinin inandırıcı qanuni izahı ola bilər
(jurnalın səhv doldurulmasının düzəldilməsi, akademik borcun daşınması,
transfer tələbə):

| Kod | Qayda | Sətir | Tələbə |
|---|---|---:|---:|
| `T2-QAYIB-SİLİNMƏ` | Semestrin ilk vərəqində «(Kəsr)» var, sonrakında yoxdur, tələbə keçib — davamiyyət balı artıb | **547** | **354** |
| `T2-ARDICILLIQ` | Ön şərt fənn (X‑1) açıq kəsilib və **heç bir mənbədə heç vaxt** keçilməyib, ardıcıl fənn (X‑2) keçilib | **76** | **66** |
| `T2-KÜTLƏVİ-QAYIB` | Bir jurnalda tələbənin **10+** qayıb xanası sonradan silinib / iştiraka çevrilib | **38** | **27** |
| `T2-TƏRS-ARDICILLIQ` | X‑2 fənni X‑1-ə ilk cəhddən **ƏVVƏL** bitirilib | **7** | **7** |

### `T2-KEÇİD-XƏTTİ` — ən güclü statistik arqument

202 tapıntının **173-ü (86 %) düz keçid həddinin üstünə (51–55 bal)**,
**76-sı isə DƏQİQ 51 bala** düşür. Təsadüfi düzəlişdə (məsələn müəllimin
səhv rəqəmi düzəltməsi) belə yığılma gözlənilməzdir — düzəlişlər 51–100
arasına yayılmalı idi. İmtahan balı artımının histoqramı da kiçikdir
(31 sətirdə +1, 38-də +2, 30-da +3): **balı qaldırmaq yox, məhz xətti keçirmək**
naxışı.

---

## 5. Təkrar istehsal — istifadə olunan SQL

```sql
-- 0. Yalnız-oxu təsdiqi
SELECT @@GLOBAL.read_only;                 -- 1 gözlənilir
SET SESSION TRANSACTION READ ONLY;

-- 1. Şkala pozuntusu: yekun cədvəli (xarici dil kursları istisna)
SELECT y.id, y.student_id, y.lesson_id, y.girish, y.imtahanda, y.yekun, l.name
  FROM yekun y JOIN lessons l ON l.id = y.lesson_id
 WHERE y.level = 0
   AND l.name NOT REGEXP 'Xarici dil|akademik kommunikasiya|[Ll]evel'
   AND (y.girish > 50 OR y.imtahanda > 50 OR y.yekun > 100
        OR y.girish + y.imtahanda > 100);

-- 2. Şkala pozuntusu: imtahan giriş/çıxış cəhd tarixçəsi
SELECT i.id, i.student_id, i.lesson_id, i.giris_point, i.cixis_point, i.added_date, l.name
  FROM imthngrscxsblr i JOIN lessons l ON l.id = i.lesson_id
 WHERE l.name NOT REGEXP 'Xarici dil|akademik kommunikasiya|[Ll]evel'
   AND (i.giris_point > 50 OR i.cixis_point > 50
        OR i.giris_point + i.cixis_point > 100);

-- 3. Arifmetik uyğunsuzluq — güzəşt sütunları ilə birlikdə
SELECT COUNT(*)                                              AS mismatch_total,
       SUM(ABS(yekun - (girish + imtahanda + guzest_artim))  <= 1) AS expl_artim,
       SUM(ABS(yekun - (girish + imtahanda + guzest_girish)) <= 1) AS expl_girish
  FROM yekun
 WHERE ABS(yekun - (girish + imtahanda)) > 1;
-- → 1 / 1 / 0 : yeganə fərq guzest_artim = 2 ilə tam izah olunur

-- 4. Qayıb silinmələri (update_log jurnal uniqid ilə bağlanır)
SELECT u.student_id, j.id AS journal_id, COUNT(*) AS silinmis_qayib,
       MIN(u.updated_at) AS ilk, MAX(u.updated_at) AS son
  FROM update_log u JOIN journals j ON j.uniqid = u.j_id
 WHERE u.old_value = 'qb' AND u.new_value <> 'qb'
 GROUP BY 1, 2 HAVING COUNT(*) >= 10;

-- 5. Sənədləşdirilmiş qayıb icazələri
SELECT id, student_id, allowed_date_start, allowed_date_end, file FROM allowed_qb;

-- 6. APELLYASİYA SAXLANCININ AXTARIŞI (cədvəl adları)
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'myedudb'
   AND table_name REGEXP 'apel|appel|apply|etiraz|itiraz|sikay|shikay|complain|
                          review|correct|duzel|guzest|objection|revis|protest|
                          appeal|muracie|muraciet|xidmeti';
-- → yalnız xidmeti_muraciet (2 sətir) və xidmeti_muraciet_files

-- 7. APELLYASİYA SAXLANCININ AXTARIŞI (sütun adları)
SELECT table_name, column_name, column_type FROM information_schema.columns
 WHERE table_schema = 'myedudb'
   AND column_name REGEXP 'apel|appel|etiraz|itiraz|sikay|shikay|complain|
                           review|correct|duzel|guzest|objection|reason|sebeb|
                           comment|note|desc|why|izah|qeyd';
-- → update_log və balvereqi_logs-da SƏBƏB sütunu yoxdur

-- 8. `why` (qayıb səbəbi) sahəsi praktiki olaraq işlədilməyib
SELECT COUNT(*) total, SUM(why <> '') with_why, SUM(excusable <> 0) excusable
  FROM journals_dates_points;
-- → 5 135 289 / 28 / 28
```

Köçürülmüş bazada (yalnız oxu):

```sql
SET default_transaction_read_only = on;
SELECT tablename FROM pg_tables
 WHERE schemaname = 'public'
   AND tablename ~* 'appeal|apel|objection|correct|duzel|etiraz|complaint|review';
-- → appeals_appeal, appeals_appealitem, appeals_scoreadjustment,
--   registrar_*correction, registrar_correctionreversal,
--   registrar_legacygradereview  … HAMISI 0 sətir
```

> **Qeyd.** Yuxarıdakı sorğular **xam sətir** qaytarır; Excel isə
> `(tələbə, fənn, qayda)` üzrə **dedublikasiya** edilib. Məsələn 2-ci sorğu
> **28 xam sətir** verir → siyahıda **27 tapıntı** (bir tələbənin eyni fənndə
> iki cəhdi var). 1-ci sorğu **0** qaytarır: `yekun` cədvəlində xarici dil
> kursları çıxıldıqdan sonra şkala pozuntusu qalmır — həmin cədvəlin bütün
> «diapazondan kənar» sətirləri dil kurslarına aiddir.

Çap vərəqləri SQL ilə deyil, `balvereqi_logs.data` sütununun **iki dəfə
HTML-escape olunmuş** cədvəlinin parsinqi ilə açılır (skriptdə
`parse_bal_sheets()`); tələbə `<tr class="user_<id>">` sinfindən, sütunlar
`<td>` sırasından götürülür.

**Şəxsiyyət körpüsü** (Postgres, yalnız oxu):

```sql
SET default_transaction_read_only = on;
SELECT m.legacy_pk, u.username, u.first_name, u.last_name
  FROM legacy_import_legacyentitymap m
  JOIN auth_user u ON u.id::text = m.target_pk
 WHERE m.entity_type = 'student' AND m.state = 'migrated';   -- 7 816 sətir
```

**İşə salmaq:**

```bash
LEGACY_MYSQL_PASSWORD="$(docker exec emsarena-legacy-source-rehearsal \
    sh -c 'echo $MARIADB_ROOT_PASSWORD')" \
BAL_CACHE=/tmp/bal_rows.tsv \
.venv/bin/python scripts/legacy_audit/suspicious_grades.py \
    --out ~/Desktop/RIM/Hesabat/SUBHELI_BALLAR_REKTOR_2026-09-03.xlsx
```

---

## 6. Yoxlanıb — TƏMİZ çıxdı (yaxşı xəbər gizlədilmir)

1. **Giriş balı öz komponentlərinin cəminə bərabərdir.** `giriş` vs
   `davamiyyət + sərbəst iş + seminar + lab`: yoxlanan **898 419 / 898 419**
   sətirdə fərq ±1 yuvarlaqlaşdırma zolağındadır. **Əl ilə üstündən yazılmış
   giriş balı TAPILMADI** — yəni «cəmi 70 olmalı idi, 90 yazılıb» tipli hal
   çap vərəqlərində **mövcud deyil**.
2. **Yekun = giriş + çıxış.** Çap vərəqlərində 12 292 fərqin **hamısı**
   «T. imtahan» (təkrar imtahan) sütunu ilə izah olunur. `yekun` cədvəlindəki
   yeganə fərq (id 8342, +2) `guzest_artim = 2` ilə izah olunur.
   **İzah olunmayan arifmetik uyğunsuzluq: 0.**
3. **Komponent tavanları.** `davamiyyət > 10` və `sərbəst iş > 10` heç bir
   sətirdə yoxdur. `seminar > 30` cəmi **4 tələbə-fənn** cütündə var
   (39 · 47.5 · 66.43 · 76.2) — hər dördü Tier 1-dədir və giriş > 50 olmasının
   birbaşa səbəbidir.
4. **Mənfi giriş balı** (1 844 sətir) çap düsturunun (`10 − qayıb × 10/N`)
   mənfiyə düşməsindən yaranır; **1 844-dən yalnız 4-ündə yekun qiymət var**.
   Manipulyasiya deyil — render qüsurudur, siyahıya salınmayıb.

---

## 7. Ehtiyat qeydləri (bunlar qəsdən siyahıdan kənardadır)

- **2025 render dəyişikliyi.** `QB_KESILENLER.md` §1.1/§1.3-ə görə 2025-dən
  «(Kəsr)» bayrağının məxrəci `fenn_saati` → `fenn_saati ÷ 2` oldu. Ölçdük:
  keçən sətirlərdə bayraq nisbəti **2023-də 1.09 %, 2024-də 0.60 %,
  2025-də 3.06 %, 2026-da 2.27 %**. Bu sıçrayış manipulyasiya deyil, render
  qüsurudur — ona görə `T2-KƏSR-ZİDDİYYƏTİ` **yalnız 2025-dən əvvəlki
  vərəqlərə** tətbiq olunub. Bu məhdudiyyət olmasa qayda **2 627 sətir**
  verirdi (88 əvəzinə); fərq **tamamilə render artefaktıdır**.
- **`imthngrscxsblr`-də jurnal/semestr sütunu yoxdur** — sətir hansı açılışa
  aid olduğunu göstərmir. Şkala qaydası bundan asılı deyil (sətir öz-özlüyündə
  mümkünsüzdür), amma «hansı semestr» sualına cavab verilə bilmir.
- **Ardıcıllıq qaydası Tier 1 DEYİL.** Azərbaycan praktikasında tələbə
  ön şərt fənni «akademik borc» kimi daşıya bilər; `curricula_plan.lesson_before_id`
  sahəsinin **«ön şərt» yoxsa «plan sırası»** olduğu isə
  `MENTIQ_ZIDDIYYETLERI.md` §4-də təsdiqlənməyib. Ona görə ad-ardıcıllığından
  qurulan cütlər **Tier 2**-dədir. «Heç vaxt keçməyib» hökmü **üç mənbənin
  hamısına** (çap vərəqi + `yekun` + `imthngrscxsblr`) baxdıqdan sonra verilir;
  ön şərtdə heç bir rəqəm yoxdursa **hökm verilmir** (bilməmək hökmə çevrilmir).
- **«Kim daxil edib» sütunu ixracı edən müəllimin adıdır**, balı yazanın deyil —
  köhnə sxemdə balı yazan istifadəçi ümumiyyətlə saxlanmır.
- **Dublikat tələbə qeydləri var.** Məsələn `students.id = 1868` və `3388`
  eyni şəxsdir (Zamiq Mirzəyev Zahid, qrup 111, 2022-01 və 2022-10-da yaradılıb).
  Siyahıda hər iki köhnə ID öz sətri ilə görünür — bu, ayrıca təmizlik işidir.
- **Transfer tələbələr.** Ön şərti başqa universitetdə keçmiş tələbə bu
  datadan görünmür; `T2-ARDICILLIQ` sətirlərində bu ehtimal qalır.

---

## 8. Əl ilə nəzarət — 10 Tier 1 sətri xam data ilə üzləşdirildi

| # | Tapıntı | Xam sətir | Nəticə |
|---|---|---|---|
| 1 | `imthngrscxsblr#9417` st 2045 giriş 3010 | `giris_point=3010, cixis_point=6`, İqtisadi hüquq (dil kursu deyil) | ✅ təsdiq |
| 2 | `imthngrscxsblr#5101` st 1458 çıxış 2437 | `giris_point=40, cixis_point=2437` | ✅ təsdiq |
| 3 | `imthngrscxsblr#7437` st 98 giriş 98 | `giris_point=98, cixis_point=48`, Verilənlərin strukturu | ✅ təsdiq |
| 4 | `imthngrscxsblr#9646` st 584 çıxış 60 | `giris_point=22, cixis_point=60`, Ölkəşünaslıq | ✅ təsdiq |
| 5 | `yekun#8342` st 1090 «22+24=46, yekun 48» | xam sətirdə **`guzest_artim = 2`** | ❌ **YALANÇI MÜSBƏT — çıxarıldı** |
| 6 | `balvereqi_logs#3205` st 276 | vərəqdə: dav 9.67 · si 10 · sem 29 · **giriş 49 · imtahan 86 · yekun 135** | ✅ təsdiq |
| 7 | `balvereqi_logs#50854` st 6127 | dav 10 · si 7 · sem 22.5 · **giriş 40 · imtahan 94 · yekun 134** | ✅ təsdiq |
| 8 | `balvereqi_logs#9437` st 3470 giriş 65 | dav 9.6 · si 8 · **sem 47.5 (maks 30)** → giriş 65 | ✅ təsdiq (səbəb: seminar xanası) |
| 9 | `balvereqi_logs#8414` st 326 giriş 86 | dav 9.32 · si 10 · **sem 66.43 (maks 30)** → giriş 86 | ✅ təsdiq (səbəb: seminar xanası) |
| 10 | `balvereqi_logs#31584` st 1742 | dav 10 · si 9 · sem 24 · **giriş 43 · imtahan 74 · yekun 117** | ✅ təsdiq |

**Nəticə: 9/10 təsdiq, 1 yalançı müsbət tapıldı və qayda düzəldildi**
(`T1-ARİFMETİKA` indi güzəşt sütunlarını nəzərə alır → 1 → **0** sətir).
8 və 9-cu sətirlər həm də yeni detal verdi: giriş > 50 olmasının **konkret
səbəbi** «Sem./lab.» xanasına 30-dan böyük dəyər yazılmasıdır — bu indi
Excel-in «Faktiki dəyər» sütununda açıq göstərilir.

Şəxsiyyət körpüsü də nəzarətdən keçdi: 276 / 326 / 3470 / 6127 köhnə ID-ləri
köçürülmüş bazada `myedu.student.<id>` login-lərinə və eyni ad-soyada düşür.

---

## 9. Nəticələrin harada olduğu

### Excel — `SUBHELI_BALLAR_REKTOR_2026-09-03.xlsx` (7 vərəq)

| # | Vərəq | Sətir | Nədir |
|---:|---|---:|---|
| 1 | **Xülasə** | — | nə yoxlanıldı, hər qayda bir cümlə + saylar, yalnız-oxu bəyanatı, mənbə identifikatorları, **«yoxlanıb — təmiz çıxdı»** bölməsi (apellyasiya saxlancı da burada) |
| 2 | **Tier 1 — 100 % şübhəli** | **48** | hər sətir = tələbə × fənn × tapıntı |
| 3 | **Tier 1 — tələbə üzrə** | **47** | tapıntı sayına görə azalan yığcam siyahı |
| 4 | **Tier 2 — əsas** | **261** | rektor sənədinə düşən güclü hallar (keçid xətti 51–55 · kəsr-ziddiyyəti) |
| 5 | **Əlavə — köməkçi qaydalar** | **697** | qayıb silinməsi · kütləvi qayıb · ardıcıllıq — **rektor sənədində YOXDUR** |
| 6 | **İzahı olan** | **96** | rəsmi izi tapılan hallar — **şübhəli SAYILMIR** |
| 7 | **Müəllim üzrə** | 230 | vərəqdə göstərilən müəllim üzrə Tier 1 / Tier 2 / cəmi / fərqli tələbə |

Sütunlar (2, 4, 5, 6-cı vərəqlərdə eyni): Tələbə · İstifadəçi adı (login) ·
Köhnə MyEdu ID · Qrup · İxtisas · Fakültə · Fənn · Tədris dövrü · Qayda kodu ·
Qayda · Faktiki dəyər · Gözlənilən · Kim daxil edib / son dəyişən ·
**Apellyasiya / rəsmi düzəliş izi** · **İzin təfərrüatı** · Mənbə cədvəl + PK · Tarix.

Bütün vərəqlərdə: başlıq qalın + dondurulmuş sətir, avtosüzgəc, sütun enləri
təyin olunub, birləşdirilmiş xana yoxdur, `Köhnə MyEdu ID` rəqəm tipindədir.

### Rektor sənədi — `SUBHELI_BALLAR_REKTOR_2026-09-03.docx` / `.pdf`

Azərbaycan dilində, texniki olmayan dildə, **31 səhifə** (A4 albom):

1. Titul səhifəsi
2. **Qısa icmal** — nə yoxlanıldı, niyə əminik, neçə tələbə, nə tövsiyə olunur
3. **Qaydaların sadə izahı** — hər qayda üçün bir anonim nümunə
4. **Səviyyə 1 cədvəli** (48 sətir) — Tələbə (köhnə ID) · Qrup · Fakültə · Fənn ·
   Dövr · Nə tapılıb · Faktiki · Gözlənilən · Apellyasiya izi
5. **Səviyyə 2 cədvəli** (261 sətir) — eyni sütunlarla
6. **«Bu hesabat NƏYİ sübut etmir»** — kim yazdığını, qəsdi, kağız apellyasiyanı,
   transfer tələbələri, dublikat qeydləri sübut etmir + «təmiz çıxdı» siyahısı
7. **Metodologiya (qısa)**

Hər səhifənin altlığı: **«Yalnız-oxu analiz — heç bir bal dəyişdirilməyib.»**

PDF `soffice --headless --convert-to pdf` ilə yaradılıb (LibreOffice mövcuddur).
Generator: `scratchpad/make_docx.py` (python-docx 1.2.0).

---

## 10. Fayl yolları

| Fayl | Yol |
|---|---|
| Rektor sənədi (Word) | `/Users/elvin/Desktop/RIM/Hesabat/SUBHELI_BALLAR_REKTOR_2026-09-03.docx` |
| Rektor sənədi (PDF) | `/Users/elvin/Desktop/RIM/Hesabat/SUBHELI_BALLAR_REKTOR_2026-09-03.pdf` |
| Tam siyahı (Excel) | `/Users/elvin/Desktop/RIM/Hesabat/SUBHELI_BALLAR_REKTOR_2026-09-03.xlsx` |
| Metodologiya (bu sənəd) | `docs/migration/reports/SUBHELI_BALLAR_2026-09-03.md` |
| Analiz skripti | `scripts/legacy_audit/suspicious_grades.py` |
| Word generatoru | `scratchpad/make_docx.py` |
