# Tədris Planı modulu — spesifikasiya (dərs yükünün mənbəyi)

> **Nə üçün:** dərs yükü (tapşırıq) boşluqdan yaranmır — o, **tədris planından törəyir**.
> Koordinator/dekan ekranının bütün müqayisə bazası budur; onsuz təsdiq mərhələsi mənasızdır
> (bax `DESIGN_REVIEW_V1.md` §4.9).
> **Normativ baza:** NK №348 (24.12.2013, 2022-yə qədər 7 dəyişikliklə), NK №75, NK №117, NK №215.
> **Real nümunə:** Qərbi Kaspi Universitetinin öz tədris planı (060632, magistr, 13 sütun).

---

## 1. Normativ mənzərə — 5 ayrı sənəd, qarışdırılmamalı

NK 348, b. 3.1.2 beş sənədi ayırır. Bu, modulun arxitekturasını birbaşa diktə edir:

| # | Sənəd | Əhatə | Dövr | Kimə aid |
|---|---|---|---|---|
| 1 | **İxtisasın tədris planı** | bütün təhsil müddəti (4-5 il / 2 il) | statik, qəbul ili ilə bağlı | ixtisas |
| 2 | **İxtisasın tədris qrafiki** | fənlərin illər üzrə bölgüsü | statik | ixtisas |
| 3 | **Tələbənin fərdi tədris planı** | 1 tədris ili | hər il | tələbə |
| 4 | **İxtisas üzrə illik işçi tədris planı** | 1 tədris ili | hər il | ixtisas + kurs |
| 5 | **Müəllimin illik işçi tədris planı** | 1 tədris ili | hər il | müəllim |

**Kritik fərq (b. 2.1.2 vs 2.1.5):** tədris planında **tələbə sayı yoxdur**; illik işçi tədris
planı isə **«tələbələrin sayını özündə əks etdirir»**. Qrup/axın bölgüsünün mənbəyi məhz budur —
yəni **№4 sənəd tədris planı ilə dərs yükü arasındakı itmiş həlqədir**.

### 1.1 Rəsmi törəmə zənciri (NK 348, b. 3.2.12 / 3.2.13 / 3.2.19)

```
Təhsil proqramı (Nazirlik təsdiqi)
        ▼
İxtisasın TƏDRİS PLANI + TƏDRİS QRAFİKİ          ← Elmi Şura, statik
        ▼
Tələbənin FƏRDİ TƏDRİS PLANI                      ← tyutor köməyi ilə
        ▼
İxtisas üzrə İLLİK İŞÇİ TƏDRİS PLANI              ← b. 3.2.12: fənlər + dərs növləri
                                                     + kreditlər + TƏLƏBƏ SAYI
        ▼
MÜƏLLİMİN İLLİK İŞÇİ TƏDRİS PLANI (= DƏRS YÜKÜ)   ← b. 3.2.13
        + FƏNLƏR ÜZRƏ DƏRS CƏDVƏLİ                 ← b. 3.2.19
        ▼
Müəllimin FƏRDİ İŞ PLANI                           ← kafedra müdiri təsdiqləyir
```

### 1.2 Təsdiq zənciri — sənin dediyin axın normativ olaraq təsdiqlənir

```
Kafedra (layihə)
  → Fakültənin Metodiki Komissiyası
  → Fakültənin Elmi Şurası («təsdiqə tövsiyə»)
  → TƏDRİS ŞÖBƏSİ (uzlaşdırma, formatlaşdırma, prorektor imzası)
  → Universitetin ELMİ ŞURASI (protokol №)   ← əsl təsdiq orqanı
  → Rektor («Təsdiq edirəm» + möhür)
```

Sənəddə görünən üç rekvizit: **rektor** imzası (yuxarıda), **tədris işləri üzrə prorektor**
imzası (aşağıda), **Elmi Şura protokolu** (tarix + №). Yəni «dekanlıq hazırlayır → tədris
şöbəsinə gedir» modeli düzgündür; sadəcə zəncirin başında **kafedra**, sonunda isə **Elmi Şura
+ rektor** durur.

---

## 2. Sənədin real strukturu (QKU nümunəsi — 13 sütun)

Tədris planı yalnız cədvəl deyil, **üç bölməli sənəddir**:

**I. Tədris prosesinin qrafiki** — sentyabr→avqust həftəlik toru; şərti işarələr:
`□` nəzəri təlim, `::` imtahan sessiyası, `X` təcrübə, `//` yekun dövlət attestasiyası, `=` tətil.

**II. Tədris prosesinin planı** — əsas cədvəl:

| № | Sütun | Qeyd |
|---|---|---|
| 1 | Sıra № | blok daxilində davamlı |
| 2 | **Fənnin şifri** | `MHF–B01`, `MİF-B04.01` |
| 3 | **Fənnin adı** | seçmə blokda alt-siyahı saxlayır |
| 4 | **Kreditin sayı** | AKTS |
| 5 | **Ümumi saatlar** | = kredit × 30 |
| 6 | **Auditoriyadan kənar saatlar** | sərbəst iş |
| 7 | **Auditoriya saatları** | = 5 − 6 |
| 8-10 | *o cümlədən:* **Mühazirə / Seminar / Laboratoriya** | |
| 11 | **Prerekvizit fənlərin şifri** | qraf (DAG) kənarı |
| 12 | **Tədris semestri** | `1-payız`, `2-yaz` |
| 13 | **Həftəlik dərs yükü** | = 7 ÷ 15 |

**III. Təlimə ayrılan müddət** (həftə ilə): nəzəri təlim / imtahan sessiyası / təcrübə /
yekun attestasiya / tətil — tədris illəri üzrə.

**Blok başlıqları aqreqat sətirdir:** `MHF–B00 Humanitar fənlər bölməsi | 14 kredit | 420 | 315 | 105 | 35 | 70`
— yəni cədvəl **iki səviyyəlidir** (blok → fənn), yekunlar blok səviyyəsində də göstərilir.

> **Vahid dövlət şablonu YOXDUR.** İkinci nümunədə (Naxçıvan Müəllimlər İnstitutu) fənn kodu və
> sərbəst iş sütunları ümumiyyətlə yoxdur, seçmə fənlər `S/F:` prefiksi ilə adi sətir kimi
> yazılır. **Model superset olmalı, sütun görünürlüyü tenant-konfiqurasiyalı olmalıdır** — qrup
> sektoru məsələsində olduğu kimi.

---

## 3. Hesablama qaydaları (qanuni + universitet səviyyəli)

### 3.1 Qanunla sabit (NK 348 b. 3.2.2)

| Göstərici | Dəyər |
|---|---|
| **1 AKTS krediti** | **30 saat** (auditoriya + sərbəst iş birlikdə) |
| Tələbənin həftəlik ümumi yükü | 45 saat |
| Tələbənin həftəlik iş həcmi | 1,5 kredit |
| Təcrübə / buraxılış işi / imtahan hazırlığı — 1 həftə | 1,5 kredit |

Yoxlama: 45 ÷ 30 = 1,5 · 20 həftə × 1,5 = 30 kredit · 40 həftə × 1,5 = 60 kredit/il.

### 3.2 Semestr və pillə normaları

| Norma | Dəyər | Bənd |
|---|---|---|
| Əyani, bir semestr | **30 kredit** | 3.2.2 |
| Qiyabi, bir semestr | **24 kredit** | 3.2.3 |
| Parttime | ≤20 kredit | 3.2.2 |
| Bir semestrdə maksimum (əlavə fənlərlə) | 40 kredit | 3.2.5 |
| Yay semestri maksimum | 10 kredit | 3.4.3 |
| **Bakalavriat** | **240–300 kredit** (4-5 il) | 3.2.4 |
| Magistratura | 120 kredit | 3.2.4 |

> ⚠️ **240 sabit deyil** — 4 illik proqram 240, 5 illik 300. Hardcode etmək olmaz.

### 3.3 Həftə sayı — iki fərqli «həftə»

| Anlayış | Əyani | Qiyabi |
|---|---|---|
| Tədris ili | 40 həftə | 32 həftə |
| Semestr (tam) | **20 həftə** | 16 həftə |
| — o cümlədən imtahan sessiyası | 5 həftə | 1 həftə |
| **Nəzəri təlim (dərs) həftəsi** | **15 həftə** | 15 həftə |

**Kritik:** 30 kredit **20 həftəyə** yayılır, amma auditoriya saatları yalnız **15 həftəyə**
düşür. Deməli: `həftəlik 2 saat mühazirə × 15 = semestrdə 30 auditoriya saatı`.

⚠️ **Praktikada 14-ə enə bilər** — bayram günləri səbəbindən (NMİ planında `56 saat ÷ 4 = 14
həftə` sətirlər var). **Effektiv həftə sayı semestr/fənn səviyyəsində override edilə bilməlidir.**

### 3.4 Auditoriya / sərbəst iş nisbəti — **qanunla sabitlənməyib**

Bu, ən çox səhv bilinən məqamdır:

- Köhnə **«1 saat dərsə ≥1 saat sərbəst iş» (1:1) qaydası LƏĞV EDİLİB** — internetdə hələ
  dolaşır, işlətməyin.
- Nisbəti **universitet özü təyin edir** (b. 3.2.21).
- Qüvvədə qalan yeganə məcburi qayda: **sərbəst işin ≥40%-i müəllimin rəhbərliyi ilə (MRTSİ)**
  həyata keçirilməlidir — və **bu, müəllimin tədris-metodiki işidir**, yəni dərs yükünə aiddir.

Praktikada müşahidə olunan: QKU 25% auditoriya (7,5 saat/kredit), AzTU 31% (9,4), NMİ ~38% (11,3).
Hər üçündə `ümumi = kredit × 30` dəqiq gözlənilir.

**QKU-nun daxili düsturları (tam ardıcıl, planda yoxlanılıb):**
```
ümumi_saat         = kredit × 30
auditoriya_saat    = kredit × 7.5          (= həftəlik_yük × 15)
sərbəst_iş         = ümumi_saat − auditoriya_saat
həftəlik_dərs_yükü = kredit ÷ 2
```

> **Model qərarı:** `sərbəst iş` **tək sahə olmamalıdır** — MRTSİ və TSİ ayrılmalıdır, çünki
> MRTSİ müəllim yükünə düşür.

### 3.5 Blok payları (NK 117)

| Qayda | Dəyər | Bənd |
|---|---|---|
| Humanitar fənlər | 15–20% (tibb: 5–10%) | 2.23 |
| Peşə hazırlığı fənləri | 80–85% | 2.23 |
| **Seçmə fənlər** | **25–30%** (tibb: 10–15%) | 2.24 |

QKU planında yoxlama: seçmə 26/90 kredit = 28,9% ✓.

Məcburi humanitar fənlər: Azərbaycan tarixi, Azərbaycan dili (xarici dildə oxuyanlar üçün),
Xarici dil.

> **Blok adları enum OLMAMALIDIR** — «ümumi/peşə/ixtisas» üçlüyü NK 348-də yoxdur, universitetlər
> öz adlarını işlədir (QKU: Humanitar fənlər bölməsi / İxtisas fənləri / İxtisaslaşmaya ayrılan
> fənlər / Seçmə fənn / Elmi-tədqiqat işləri). Tenant-konfiqurasiyalı lüğət olmalıdır.

---

## 4. Bizdə nə var, nə çatışmır

### 4.1 Mövcuddur (`apps/registrar`)

- **`Curriculum`** — `program`, `admission_year`, `name`, `is_active`; unikal
  `(org, program, admission_year)`.
- **`CurriculumSubject`** — `curriculum`, `subject`, `semester_number`, `is_elective`,
  `elective_group`, `required_choices`, `order`.
- **UI mövcuddur** (admin-səviyyə): `registrar:curriculum_create/edit/detail` +
  `curriculum_subject_delete`, `curriculum_detail.html` (semestr üzrə qruplaşdırılmış siyahı),
  `console.html`-də «Tədris planları» paneli.
- **Servis bağlantıları:** `enroll_mandatory_subjects` (məcburi fənlərə avto-yazılma),
  `get_student_semester_plan` (seçmə blokların oxunuşu), `GroupElectiveChoice`.
- `Subject.ects` transkript/GPA/kabinetdə işlənir (`transcript.py`, `analytics.py`).

### 4.2 Çatışmır — modul üçün açıq sahələr

| # | Boşluq | Təsir |
|---|---|---|
| 1 | **`CurriculumSubject`-də saat sahələri yoxdur** (mühazirə/seminar/lab/sərbəst iş) | Dərs yükü planla müqayisə oluna bilmir |
| 2 | **Kredit `Subject.ects`-dədir, plan sətrində deyil** | Eyni fənn müxtəlif ixtisaslarda fərqli kredit daşıya bilmir — **Excel-də 421 fənndən 35-i məhz belədir** |
| 3 | **Tədris edən kafedra sahəsi yoxdur** | Xidməti tədris (Proqramlaşdırma kafedrası psixologiya qruplarına dərs deyir) marşrutlana bilmir |
| 4 | **Prerekvizit yoxdur** | Rəsmi sənədin 11-ci sütunu; tələbənin fərdi planı yoxlanıla bilmir |
| 5 | **Blok/bölmə strukturu yoxdur** | Blok başlıqları və blok üzrə yekunlar (kredit payı yoxlaması) mümkün deyil |
| 6 | **Plan sətrinin redaktəsi yoxdur** | Yalnız əlavə/sil |
| 7 | **Plan versiyalaşdırma/klonlama yoxdur** | 2025 planını 2026-ya kopyalamaq mümkün deyil |
| 8 | **ECTS balansı yoxdur** | «Semestr = 30 kredit» — sənədin əsas yoxlaması — heç yerdə hesablanmır |
| 9 | **Seçmə fənn seçimi üçün UI yoxdur** | `choose_group_elective` yalnız seed/testdən çağırılır |
| 10 | **İllik işçi tədris planı ümumiyyətlə yoxdur** | Tədris planı ilə dərs yükü arasındakı normativ həlqə |
| 11 | **Plan → offering körpüsü yoxdur** | Avto-yaranan offering-lərdə `lesson_hours=0` qalır → **qayıb limiti səssizcə söndürülür** |
| 12 | **İmtahan forması, fənn növü, tədris dili sahələri yoxdur** | |

> ⚠️ **Yan tapıntı (mövcud bug):** `services.get_or_create_offering` `lesson_hours` vermir →
> `enroll_mandatory_subjects` / `choose_group_elective` ilə yaranan hər offering-də qayıb limiti
> işləmir (`get_exam_eligibility`: `lesson_hours == 0` → heç vaxt `barred`). Bu, dərs yükü
> modulundan asılı olmayan müstəqil düzəlişdir.

> ⚠️ **İkinci yan tapıntı:** `_can_manage_registrar` xam rol adları ilə işləyir və alias qatını
> keçmir → `vice_dean`, `department_head`/`chair_head` sidebar-da «Registrar (kataloq)» linkini
> **görür, amma view 404 verir**.

---

## 5. Model dəyişiklikləri

### 5.1 `CurriculumSubject` — genişləndirilir

```python
# mövcud: curriculum, subject, semester_number, is_elective, elective_group,
#         required_choices, order

code            = Char(32, blank)      # plan şifri: MİF-B04.01
block           = FK CurriculumBlock   # bölmə (null = blokdan kənar)
credits         = PositiveSmallInteger # ⚠️ Subject.ects-i əvəz edir (ixtisasa görə dəyişir)
total_hours     = PositiveSmallInteger # = credits × 30 (avto, override edilə bilər)
lecture_hours   = PositiveSmallInteger # semestrlik auditoriya saatı
seminar_hours   = PositiveSmallInteger
lab_hours       = PositiveSmallInteger
self_study_mrts = PositiveSmallInteger # müəllim rəhbərliyi ilə sərbəst iş (≥40%)
self_study_own  = PositiveSmallInteger # tələbənin müstəqil işi
weekly_hours    = PositiveSmallInteger # = auditoriya ÷ effektiv həftə
teaching_chair  = FK OrgUnit(chair)    # ⚠️ hansı kafedra tədris edir (xidməti tədris marşrutu)
exam_form       = Char                 # imtahan / hesabat / kurs işi / yoxdur
subject_kind    = Char                 # məcburi-ardıcıl / məcburi / seçmə (NK 348 b.3.2.8)
prerequisites   = M2M self             # DAG; dövr yoxlaması servisdə
language        = Char                 # AZ / EN / RU (sektor)
```

`Subject.ects` **silinmir** — kataloq default-u kimi qalır, plan sətri onu override edir.
Transkript/GPA hesabı `CurriculumSubject.credits`-ə keçməlidir (`transcript.py:38` `_credit_for`).

### 5.2 `CurriculumBlock` — yeni

```python
curriculum, code (MHF–B00), name, order, kind (tenant lüğəti), min_credits, max_credits
```
Blok üzrə yekunlar və pay yoxlamaları (humanitar 15–20%, seçmə 25–30%) bunun üzərindən işləyir.

### 5.3 `Curriculum` — genişləndirilir

```python
status          # draft / chair_review / faculty_review / office_review / senate / approved / archived
degree_years    # 4 / 5 / 2 (kredit yekunu yoxlaması: 240/300/120)
education_form  # əyani / qiyabi (semestr 30 vs 24 kredit)
weeks_per_term  # default 15 (bayram override-ı üçün)
credit_hour     # default 30
senate_protocol, senate_date, approved_by, approved_at
```

### 5.4 `AnnualWorkingPlan` + `AnnualWorkingPlanRow` — **yeni, itmiş həlqə**

İllik işçi tədris planı (NK 348 b. 3.2.12). Dekanlığın tədris şöbəsinə göndərdiyi sənəd budur.

```python
# AnnualWorkingPlan
organization, academic_year, specialty (OrgUnit), status, submitted_by/at, approved_by/at

# AnnualWorkingPlanRow — plan sətrinin bu ilki icra proyeksiyası
plan, curriculum_subject (FK), season (payız/yaz/yay), course_year (1..5)
groups (M2M OrgUnit), student_count (avto, redaktə edilə bilər)
chosen_subject (FK Subject, null)   # seçmə blok qərarı verilibsə
is_included (bool)                  # ⚠️ b.3.3.3: yetərli tələbə yoxdursa plana daxil edilmir
exclude_reason (Char)
teaching_chair (FK OrgUnit)         # plandan gəlir, dekanlıq dəyişə bilər
```

Bu sətirlər **avtomatik generasiya olunur**: `Curriculum` + qrup reyestri + tələbə sayları.
Dekanlıq yalnız qərar nöqtələrini redaktə edir.

---

## 6. Rollar və axın

| Mərhələ | Kim | Nə edir |
|---|---|---|
| **T1. Plan layihəsi** | Kafedra müdiri | Fənləri, kreditləri, saatları, prerekvizitləri daxil edir (və ya keçən ildən klonlayır) |
| **T2. Fakültə baxışı** | Proqram koordinatoru → Dekan | İxtisas üzrə yoxlama: semestr 30 kredit, seçmə 25–30%, humanitar 15–20%, prerekvizit dövrü yoxdur |
| **T3. Tədris şöbəsi uzlaşdırması** | Tədris şöbəsi | Fənn kataloqu ilə uyğunlaşdırma, şifr sxemi, universitet üzrə dublikat/ziddiyyət yoxlaması, prorektor imzasına hazırlama |
| **T4. Elmi Şura + rektor** | (opsional mərhələ) | Protokol № + tarix qeyd olunur, plan `approved` olur və **kilidlənir** |
| **İ1. İllik işçi plan generasiyası** | Tədris şöbəsi (avto) | Təsdiqli planlardan + qrup reyestrindən bu ilin sətirləri yaradılır |
| **İ2. Dekanlıq təsdiqi** | Dekan + koordinator | Tələbə sayları, qrup birləşmələri, «yetərli tələbə yoxdur» istisnaları, seçmə blok qərarları |
| **Y1. Dərs yükü** | Tədris şöbəsi | İllik işçi plandan **kafedra tapşırıqları** generasiya olunur → mövcud `DERS_YUKU_SPEC.md` axını başlayır |

Rollar mövcuddur: `chair_head` (70), `program_coordinator` (45), `dean` (80),
`teaching_office_head/staff` (yeni), `vice_rector` (90).

Yeni permission-lar: `curriculum.view / manage / review / approve / annual_plan.manage`.

---

## 7. Avtomatik törətmə alqoritmi (modulun əsl dəyəri)

### 7.1 Tədris planı → İllik işçi plan

```
üçün hər (ixtisas, tədris_ili):
    kurslar = aktiv qruplar(ixtisas) qruplaşdır → qəbul ili
    üçün hər kurs:
        curriculum = Curriculum(program, admission_year=kursun qəbul ili)
        semestrlər = kursun bu il oxuyacağı semestrlər      # məs. 3-cü kurs → sem 5 (payız), 6 (yaz)
        üçün hər CurriculumSubject(curriculum, semester_number ∈ semestrlər):
            sətir = AnnualWorkingPlanRow(
                curriculum_subject = cs,
                season             = semestrdən (tək→payız, cüt→yaz),
                groups             = kursun qrupları (dil sektoruna görə ayrı),
                student_count      = Σ aktiv tələbə(qruplar),
                teaching_chair     = cs.teaching_chair,
                is_included        = student_count ≥ min_hədd)     # b. 3.3.3
```

### 7.2 İllik işçi plan → Dərs yükü sətri

Bu düstur **real Excel-in 855 sətri üzərində yoxlanılıb** (uyğunluq: mühazirə 100%,
seminar 99.2%, lab 98.7%, sətir cəmi 100%):

```
üçün hər AnnualWorkingPlanRow (is_included):
    # 1) Mühazirə axını (birləşmə) — İNSAN QƏRARI, sistem təklif edir
    axınlar = birləşdir(qruplar)          # default: eyni ixtisas + eyni dil sektoru → 1 axın
    # 2) Yarımqrup — İNSAN QƏRARI, sistem təklif edir
    yarımqruplar = Σ ceil(qrup.tələbə / yarımqrup_həddi)   # təklif: hədd = 40

    sətir.mühazirə_plan  = cs.lecture_hours
    sətir.mühazirə_cəmi  = cs.lecture_hours × len(axınlar)
    sətir.seminar_plan   = cs.seminar_hours
    sətir.seminar_cəmi   = cs.seminar_hours × yarımqruplar
    sətir.lab_plan       = cs.lab_hours
    sətir.lab_cəmi       = cs.lab_hours × yarımqruplar
    sətir.məsləhət       = norma(cs)       # org-konfiqurasiyalı
    sətir.imtahan        = norma(cs, tələbə_sayı)
    sətir.kredit         = cs.credits
    sətir.cəmi           = Σ bütün cəmi sütunları
```

**Yarımqrup həddinin sübutu (Excel, 775 sətir):** G=1 sətirlərdə tələbə sayı 2–46, G=2-də
39–105, G=3-də 69–110. **Örtüşmə zonası 39–46** — yəni praktik hədd ~40, amma qərar insanındır
(eyni 40 tələbəli qrup bir fənndə 2 yarımqrupa bölünüb, digərində bölünməyib). Sistem
`ceil(tələbə/40)` təklif etməli, istifadəçi override edə bilməlidir.

### 7.3 İnsan qərarı tələb edən nöqtələr

1. **Mühazirə birləşməsi** — hansı qruplar bir axına yığılır (auditoriya tutumu, dil sektoru).
2. **Yarımqrup bölgüsü** — fənnə görə dəyişir (lab-da bölünür, mühazirədə yox).
3. **Tədris edən kafedra** — xidməti fənlərdə plana yazılır, dekanlıq dəyişə bilər.
4. **«Yetərli tələbə» həddi** — b. 3.3.3 (fənn plana daxil edilməsin).
5. **Seçmə blok qərarı** — `GroupElectiveChoice`, qrup səviyyəsində.

---

## 8. Ekranlar

### 8.1 Tədris planı redaktoru (kafedra + dekanlıq)

İki səviyyəli cədvəl (blok → fənn), rəsmi 13 sütun. Sağda **canlı balans paneli** — modulun
əsas dəyəri:

| Yoxlama | Göstərilir |
|---|---|
| Semestr üzrə kredit | `Sem 1: 30/30 ✓`, `Sem 2: 28/30 ⚠` |
| Ümumi kredit | `240/240 ✓` (və ya 300/120) |
| Seçmə fənn payı | `28,9% — 25-30% ✓` |
| Humanitar pay | `17% — 15-20% ✓` |
| Kredit ↔ saat | `ümumi = kredit × 30` pozulan sətirlər |
| Auditoriya bölgüsü | `mühazirə+seminar+lab = auditoriya` |
| Prerekvizit | dövr aşkarlanması + «prerekvizit sonrakı semestrdədir» xətası |
| Tədris edən kafedra | boş qalan sətirlər (marşrutlana bilməz) |

Əməliyyatlar: sətir əlavə/redaktə/sil, blok əlavə, **keçən ildən klonla**, Excel import/export,
prerekvizit qraf görünüşü, «Fakültə şurasına göndər».

### 8.2 İllik işçi plan (dekanlıq)

Generasiya nəticəsi cədvəl kimi: fənn + kredit çipi, kurs, semestr, qruplar (çip), tələbə sayı,
tədris edən kafedra, «daxil edilsin?» keçidi. Filtrlər: ixtisas, kurs, semestr, kafedra.
Stat kartlar: sətir sayı, cəmi kredit (**təkrarsız fənn üzrə**), tələbə sayı, istisna edilən sətir.
Əməliyyat: «Tədris şöbəsinə göndər».

### 8.3 Plan ↔ yük müqayisə paneli (koordinator/dekan ekranına əlavə)

`DESIGN_REVIEW_V1.md` §4.9-da göstərilən boşluğu bağlayır. Dərs yükü cədvəlinə **iki əlavə
sütun**:

| PLAN (norma) | TAPŞIRIQ | FƏRQ |
|---|---|---|
| müh 30 / sem 15 / lab 15 | müh 30 / sem 45 / lab 15 | seminar ×3 (3 yarımqrup) ✓ |
| müh 30 / sem 15 / lab 30 | müh 30 / sem 15 / lab 45 | **lab +15 ⚠ izahsız** |

Uyğunsuz sətirlər sarı işarələnir; koordinatorun iradı avtomatik həmin fərqə bağlanır.
**Bu, koordinator ekranını mənalı edən yeganə şeydir.**

---

## 9. Fazalar

| Faza | Əhatə |
|---|---|
| **T0** | `CurriculumSubject` genişlənməsi + `CurriculumBlock` + migrasiyalar + `Subject.ects` → `credits` köçürməsi |
| **T1** | Tədris planı redaktoru (kafedra) + canlı balans paneli + klonlama |
| **T2** | Təsdiq axını (kafedra → fakültə → tədris şöbəsi → Elmi Şura) + kilidlənmə |
| **T3** | `AnnualWorkingPlan` generasiyası + dekanlıq təsdiqi |
| **T4** | Yük generatoru (İ→Y) + plan↔yük müqayisə paneli |
| **T5** | Prerekvizit qrafı, seçmə blok seçimi UI-ı, `lesson_hours` körpüsü (qayıb limiti bug-ı) |

**T0-T2 `apps/workload`-un F1-indən ƏVVƏL gəlməlidir** — əks halda tədris şöbəsi tapşırığı yenə
əl ilə yazacaq və koordinator/dekan yenə müqayisə edə bilməyəcək.

---

## 10. Açıq suallar

1. Elmi Şura mərhələsi sistemdə izlənsin, yoxsa yalnız protokol № qeyd edilsin?
2. Sərbəst iş MRTSİ/TSİ ayrılığı ilk fazada lazımdırmı (MRTSİ müəllim yükünə düşür)?
3. Auditoriya/kredit əmsalı (QKU-da 7,5) universitet parametri kimi sabitlənsin, yoxsa sətir-sətir
   sərbəst yazılsın?
4. Prerekvizit yoxlaması bloklasın, yoxsa xəbərdarlıq versin?
5. `Subject.ects` → `CurriculumSubject.credits` köçürməsi transkript/GPA-ya təsir edir — köhnə
   qeydlər üçün fallback saxlanılsın?
