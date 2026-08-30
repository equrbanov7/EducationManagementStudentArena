# İxtisas kodları — sahibin qərar sənədi

**Tarix:** 2026-08-30 · **Vəziyyət:** 5 rəsmi şifr yazıldı · 1 qəsdən boş
qaldı · 37 sətir sahibin qərarını gözləyir

> Bu sənəd **doldurulacaq cədvəldir**. Sahib universitetdə dəqiq ixtisas
> şifrlərini öyrənəndə «**Təsdiqlənmiş şifr**» sütununu doldurur; sonra sətir
> `apps/registrar/management/commands/_program_official_codes.py` faylındakı
> `ASSIGNMENTS` cədvəlinə əlavə olunur və
> `python manage.py set_program_official_codes --apply` ilə yazılır.

---

## 0. Problem və həll — bir səhifədə

MyEdu köçürməsi `registrar_program.code` sütununu sətirlərin çoxunda **yer
tutucu** ilə doldurdu: `MYEDU-<id>` (mənbədə şifr boş idi), `<bakalavr
şifri>-M` (magistr üçün uydurma şəkilçi), `<şifr>-<id>`. Tələbə profilində,
transkriptdə və hesabatlarda ixtisasın yanında məhz bu uydurma görünürdü.

**Struktur səbəb.** Azərbaycan təsnifatı iki səviyyəlidir:

| səviyyə | nümunə | öz şifri var? |
|---|---|---|
| **ixtisas** | 060209 Psixologiya | ✅ 6 rəqəm |
| **ixtisaslaşma** | Klinik / Sosial / Məhkəmə psixologiya | ❌ yoxdur |

WCU-nun magistr «proqram» adlarının çoxu **ixtisaslaşma** adıdır, şifr isə ana
ixtisasa aiddir — yəni bir neçə proqram **qanuni olaraq eyni şifri paylaşır**.
Köçürmə isə `uniq_program_code_per_org UNIQUE (organization_id, code)`
məhdudiyyəti ilə üzləşəndə şifr uydurmağa məcbur oldu.

### Həll: kodu İKİYƏ ayırdıq

| sahə | nədir | unikal? | kim yazır |
|---|---|---|---|
| `Program.code` | **daxili identifikator** (`MYEDU-40` …) | ✅ **bəli, dəyişmir** | yalnız köçürmə xətti |
| `Program.official_code` | **rəsmi dövlət şifri** (`050405`) | ❌ **xeyr** | bu sənədin cədvəli |

Miqrasiya: `apps/registrar/migrations/0055_program_official_code_alter_program_code.py`.

> ⚠️ **Nə üçün `code`-un unikallığı GÖTÜRÜLMƏDİ.** Əvvəlki cəhd bunu təklif
> etmişdi; düşmən baxışı köçürmə xəttinin ÜÇ yerdə sındığını PostgreSQL-də
> təkrar istehsal etdi: `rehearsal_sar_phase.py:155` (`program_pk_index()` kodu
> primary key sayır — təkrar VƏ YA boş kod `…catalog_index_ambiguous` atır),
> `rehearsal_structure_targets.py:169` (`get_or_create(code=…)` →
> `MultipleObjectsReturned`), `rehearsal_catalog_phase.py:104-122` +
> `rehearsal_catalog_targets.py:108` (proqramın `TargetRef.key`-i **elə kodun
> özüdür**). İndiki dizayn `apps/legacy_import/` altında **bir sətri də**
> dəyişmir.

Nəticədə istifadəçi «**Ad · rəsmi şifr**» görür (`Program.display_label`);
şifr bilinməyəndə yalnız ad görünür — **uydurma göstərilmir**.

---

## 1. (a) TƏTBİQ OLUNDU — 5 şifr

Düşmən doğrulayıcısının açıq «TƏTBİQ ET» hökmü olan, hər biri **iki müstəqil
mənbə** ilə təsdiqlənmiş sətirlər. Komanda fail-closed işləyir: sətrin adı və
ya təhsil pilləsi gözlənilənlə uyuşmursa **heç nə yazılmır**.

| # | Daxili kod (dəyişmir) | Ad | Pillə | **Yazılan rəsmi şifr** | Mənbə 1 (milli / rəsmi) | Mənbə 2 (sayt / MyEdu) |
|---|---|---|---|---|---|---|
| 1 | `050620-M` | Kompüter Mühəndisliyi | magistr | **060631** | milli magistr təsnifatı «060631 Kompüter mühəndisliyi» | WCU rəsmi 2022/23 magistratura cədvəli + `060631 - Kompüter mühəndisliyi.pdf` |
| 2 | `060411-M` | Elektron kommersiya | magistr | **060411** | WCU rəsmi cədvəl «060411 Kommersiya / Elektron kommersiya» | MyEdu `speciality_code = 060411` (id 60) |
| 3 | `MYEDU-40` | İqtisadiyyat | bakalavr | **050405** | milli bakalavriat «050405 İqtisadiyyat» | `050405 İqtisadiyyat 2024 - tədris planı.pdf` |
| 4 | `MYEDU-43` | Maliyyə | bakalavr | **050406** | milli bakalavriat «050406 Maliyyə» | `050406 Maliyyə 2024- tədris planı ingilis.pdf` |
| 5 | `MYEDU-62` | Kompüter elmləri | bakalavr | **050509** | milli bakalavriat «050509 Kompüter elmləri» | `050509 - Kompüter Elmləri.pdf` + `… - QİYABİ.pdf` |

Daxili kodlar (`050620-M`, `MYEDU-40` …) **olduğu kimi qalır** — köçürmə
xəttinin şəxsiyyət açarıdır.

---

## 2. (e) `050624` — YANLIŞ şifr, qəsdən BOŞ qaldı

| Daxili kod | Ad | Pillə | `official_code` | Səbəb |
|---|---|---|---|---|
| `050624` | Cihazqayırma mühəndisliyi | bakalavr | **«» (boş)** | milli bakalavriat təsnifatında **050624 = «Mədən mühəndisliyi»**dir. «Cihazqayırma mühəndisliyi» bakalavriatda ümumiyyətlə yoxdur — yalnız magistratura `060624`. MyEdu-nun «həqiqi görünən» 6-rəqəmli dəyəri korlanmışdır; indiyə qədər tələbəyə **başqa ixtisasın şifri** göstərilirdi. |

**Uydurma əvəz VERİLMƏDİ.** Sətir daxili identifikatorunu (`code = "050624"`)
saxlayır, amma rəsmi şifri boşdur — `--adopt-clean-codes` addımı da onu keçir.

> **Sahibin qərarı lazımdır:**
> ☐ proqram bağlanıb → arxivləşdir
> ☐ davam edir → düzgün bakalavr qarşılığı **050604 «Cihaz mühəndisliyi»**dir,
>   amma o şifr artıq başqa sətirdədir (birləşdirmə lazım)
> ☐ əslində magistratura sətridir → **060624**
> ☐ başqa: ______________

---

## 3. (b) SAHİBİN TƏSDİQİNİ GÖZLƏYƏN NAMİZƏDLƏR

### 3.1 Doğrulayıcı RƏDD etdi / model qüsuru — 8 sətir

Bu sətirlərə şifr **verilə bilməz**, çünki problem şifrdə deyil — **modeldə**dir.

| Daxili kod | Ad | Pillə | Təklif olunmuş şifr | Niyə yazılmadı | Nə lazımdır | **Təsdiqlənmiş şifr** |
|---|---|---|---|---|---|---|
| `050708-M` | Su Bioehtiyyatları və Akvakultura | magistr | 060709 | milli təsnifatda 060709 «Su bioehtiyatları və **akvabitkilər**»dir («akvakultura» BAKALAVR 050708-in adıdır); hədəfdə bu sahə üçün **İKİ** magistr sətri var (`050708-M`, `MYEDU-89-M`); WCU-nun öz rəsmi cədvəlində 060709 **yoxdur** | «bu iki sətir eyni proqramdırmı?» qərarı | ☐ ________ |
| `MYEDU-86-M` | Genetika | magistr | 060505 | 060505 ana ixtisas «Biologiya»dır; HƏM «Genetika», HƏM «Molekulyar biologiya» ixtisaslaşmasına eyni dərəcədə aiddir | `ixtisaslasma` (specialization) sahəsi | ☐ ________ |
| `MYEDU-90-M` | Ətraf mühitin mühafizə və bərpa metodları | magistr | 7005004 | təklif **YENİ nəsil** (NK 503/2024) şifridir və «Ekologiya» deməkdir; qalan şifrlər **köhnə nəsildəndir** | təsnifat nəsli qərarı (§6) | ☐ ________ |
| `MYEDU-67` | Davamlı inkişafın idarə edilməsi | bakalavr | — | MyEdu id 58-in **dublikat** sətridir (ad hərfi eyni, MyEdu şifri «2222» saxta) — ayrıca proqram deyil | `050403` sətri ilə birləşdir, sonra arxivləşdir | ☐ ________ |
| `MYEDU-20` | Tarix (Tədris Ingilis Dilində) | bakalavr | — | şifr müstəqil mənbədən deyil, qardaş «Tarix» sətrindən çıxarılır | `instruction_language` sahəsi | ☐ ________ |
| `MYEDU-15` | Politologiya (Tədris Ingilis Dilində) | bakalavr | (050210) | eyni sinif — tədris dili variantı | `instruction_language` sahəsi | ☐ ________ |
| `MYEDU-17` | Beynəlxalq Münasibətlər (Tədris Ingilis Dilində) | bakalavr | (050201) | eyni sinif | `instruction_language` sahəsi | ☐ ________ |
| `MYEDU-82-M` | Klinik psixologiya (ing) | magistr | (060209) | eyni sinif | `instruction_language` sahəsi | ☐ ________ |

> ⚠️ `050214-EN` kimi şəkilçi **indiki `-M` uydurmasının eyni səhvidir** —
> tədris dili şifrin bir hissəsi deyil.

### 3.2 Dərin sayt axtarışının 21 namizədi

Doğrulayıcı bunları hərfən «**mən tətbiq etmədim, sahibin təsdiqi üçün**» deyə
qeyd etdi. Əvvəlki iki cəhd məhz bu siyahını yazdı və sındı — burada **heç biri
yazılmayıb**.

**A. Sayt ∩ milli təsnifat (adlar üst-üstə düşür) — 12**

| Daxili kod | Ad | Pillə | Namizəd şifr | Mənbə | **Təsdiqlənmiş şifr** |
|---|---|---|---|---|---|
| `050501-63` | Ekologiya Mühəndisliyi | bakalavr | 050606 | milli təsnifat + sayt (eyni ad) · daxili kod MyEdu-nun 050501 «Biologiya» şifrini İKİ ixtisasa verməsindən doğub | ☐ ________ |
| `MYEDU-14` | Politologiya | bakalavr | 050210 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-18` | Beynəlxalq münasibətlər | bakalavr | 050201 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-42` | Biznesin idarə edilməsi | bakalavr | 050402 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-44` | Menecment | bakalavr | 050408 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-47` | Marketinq | bakalavr | 050407 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-48` | Mühasibat | bakalavr | 050409 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-49` | Turizm işinin təşkili | bakalavr | 050810 | milli təsnifat + `050810 Turizm işinin təşkili -PTN.pdf` (tədris planlarının adında şifr YOXDUR) | ☐ ________ |
| `MYEDU-50` | Dövlət və bələdiyyə idarəetməsi | bakalavr | 050404 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-72-M` | Məhkəmə psixologiyası | magistr | 060209 | milli təsnifat «060209 Psixologiya» + sayt | ☐ ________ |
| `MYEDU-74-M` | Sosial psixologiya | magistr | 060209 | milli təsnifat + sayt | ☐ ________ |
| `MYEDU-81-M` | Klinik psixologiya | magistr | 060209 | milli təsnifat + sayt | ☐ ________ |

> `060209` üç-dörd sətrə birdən yazıla bilir — `official_code` **unikal
> deyil**, məhz buna görə.

**B. Tək mənbəli namizədlər — 9** (bir cümləlik təsdiq kifayətdir)

| Daxili kod | Ad | Pillə | Namizəd şifr | Tək mənbə | **Təsdiqlənmiş şifr** |
|---|---|---|---|---|---|
| `MYEDU-26` | Filologiya (İngilis dili və ədəbiyyatı) | bakalavr | 050205 | YALNIZ sayt | ☐ ________ |
| `MYEDU-27` | Tərcümə | bakalavr | 050215 | YALNIZ sayt | ☐ ________ |
| `MYEDU-75-M` | Qafqaz xalqlarının tarixi | magistr | 060206 | YALNIZ sayt | ☐ ________ |
| `MYEDU-83-M` | İqtisadiyyatın tənzimlənməsi | magistr | 060404 | YALNIZ sayt | ☐ ________ |
| `MYEDU-87-M` | Beynəlxalq turizm | magistr | 060803 | YALNIZ sayt | ☐ ________ |
| `MYEDU-88-M` | Beynəlxalq münasibətlər və diplomatiya | magistr | 060213 | YALNIZ sayt | ☐ ________ |
| `MYEDU-53` | Beynəlxalq ticarət və logistika | bakalavr | 050401 | YALNIZ milli təsnifat | ☐ ________ |
| `MYEDU-68` | Qida mühəndisliyi | bakalavr | 050635 | YALNIZ milli təsnifat | ☐ ________ |
| `MYEDU-41` | Dünya iqtisadiyyatı | **bakalavr?** | 060401 (**magistr** şifri) | YALNIZ milli təsnifat | ☐ sətrin pilləsi səhvdir → magistr · ☐ başqa: ______ |

---

## 4. (d) İXTİSAS OLMAYAN 8 sətir — şifr verilmir, silinmir də

| Daxili kod | Ad | Nədir | **Sahibin qərarı** |
|---|---|---|---|
| `MYEDU-61` | Level | İngilis dili mərkəzinin səviyyə qeydi | ☐ arxivləşdir ☐ saxla |
| `MYEDU-65` | aaa | test sətri | ☐ arxivləşdir ☐ saxla |
| `MYEDU-66` | Dizayn Məktəbi | fakültə adı | ☐ arxivləşdir ☐ saxla |
| `MYEDU-36-M` | Magistratura və doktorantura | struktur bölməsi adı | ☐ arxivləşdir ☐ saxla |
| `MYEDU-91` | Lifelong | davamlı təhsil mərkəzi | ☐ arxivləşdir ☐ saxla |
| `MYEDU-91-M` | Lifelong | eyni mərkəzin magistr dublikatı | ☐ arxivləşdir ☐ saxla |
| `MYEDU-92` | Kollec | struktur bölməsi | ☐ arxivləşdir ☐ saxla |
| `MYEDU-101` | Kollec 2 | struktur bölməsi | ☐ arxivləşdir ☐ saxla |

> ⚠️ Bu sətirlərə **tələbə/qrup bağlantısı ola bilər** — köçürmə skripti onları
> silmir. Arxivləşdirmədən əvvəl bağlantılar yoxlanmalıdır.

---

## 5. (c) MƏNBƏNİN (saytın) öz 3 ziddiyyəti — düzəldilməyib

1. **«Molekulyar Biologiya» (magistr):** sayt mətnində `050509` yazılıb — o,
   **bakalavr** «Kompüter Elmləri»nin şifridir; həmin sətrin PDF-i isə
   `060505`-dir. Bu, **saytın yazı səhvidir**; şifr verilmədi.
2. **Əyani/qiyabi eyni şifr:** `050509`, `050615`, `050616`, `050620`,
   `050706` şifrlərinin hər birində saytda əyani və qiyabi üçün **ayrı PDF,
   eyni şifr** var. Rəsmi şifr tədris formasını **ayırmır** — ona görə
   `official_code` unikal ola bilməz.
3. **«Turizm işinin təşkili» (Biznes məktəbi):** 5 tədris planının fayl adında
   şifr **yoxdur** (`tt1.pdf`, `wcu-87.pdf` …); şifr yalnız ayrıca «PTN»
   sənədinin adından oxunur.

> **Qeyd.** `060505`-in iki magistr planında olması və `060632`-nin iki
> ixtisasa verilməsi **ziddiyyət deyil** — təsnifata görə doğrudur
> (ixtisaslaşmalar).

---

## 6. Bir dəfə verilməli iki qərar

### 6.1 Təsnifat nəsli

NK 503/2024 bütün şifrləri dəyişdi (bakalavr `6xxxxxx`, magistr `7xxxxxx`).
Hədəfdəki dəyərlər **köhnə nəsildədir**; saytın 2025/26 sənədləri **yeni
nəsildədir**.

* ☐ **Köhnə nəsil saxlanılır** (`05xxxx` / `06xxxx`) — indiki 5 şifr və
  komandanın mexaniki yoxlaması bu fərziyyə ilə yazılıb.
* ☐ **Yeni nəslə keçilir** — bu halda **bütün sətirlər** yenidən kodlanmalıdır.

Qarışıq saxlamaq tələbəyə yanlış şifr göstərəcək.

### 6.2 `ixtisaslasma` + `instruction_language` sahələri

Bu iki sahə əlavə olunmadan §3.1-dəki 8 sətrin heç biri düzgün şifr ala bilməz.
Sahələr əlavə olunanda `official_code` **təmiz 6 rəqəm** qalır və uydurma
şəkilçilərə (`-M`, `-EN`) ehtiyac tamamilə itir.

---

## 7. «Təmiz 6 rəqəm» sətirlər — mənimsəmə addımı (opsional)

Hədəfdə 19 sətrin **daxili** kodu MyEdu-dan gələn təmiz 6 rəqəmdir. Doğrulayıcı
hamısının adını milli təsnifatla üzləşdirdi:

* **18-i doğrudur:** `050118`, `050204`, `050211`, `050212`, `050214`,
  `050403`, `050501`, `050504`, `050604`, `050615`, `050616`, `050620`,
  `050628`, `050629`, `050706`, `050708`, `050807`, `050809`.
* **1-i yanlışdır:** `050624` (§2).

Bu 18 sətrin şifri **artıq tələbəyə göstərilirdi**. Kod ikiyə ayrıldığı üçün
`official_code` boş qalır və şifr ekrandan itir. Onu geri qaytarmaq üçün
**ayrıca, könüllü** addım var — yeni iddia deyil, olan dəyərin köçürülməsi:

```bash
python manage.py set_program_official_codes --apply --adopt-clean-codes
```

Mənimsəmə fail-closed işləyir: yalnız `^0[56]\d{4}$` formatına uyğun, pillə
prefiksi düzgün (`05`=bakalavr, `06`=magistr) və **yanlış şifrlər siyahısında
olmayan** dəyərlər götürülür — yəni `050624` avtomatik keçilir.

> **Sahibin qərarı:** ☐ mənimsə (şifrlər ekrana qayıtsın) ·
> ☐ mənimsəmə (yalnız doğrulanmış 5 şifr görünsün)

---

## 8. Qalan sətirlər və tam cədvəlin çıxarılması

Yuxarıdakı bölmələr adı müəyyən edilmiş sətirləri əhatə edir. Hədəfdə adı nə
milli təsnifatda, nə də saytın kodlu sənədlərində tapılmayan sətirlər də var
(«Orta əsrər tarixi», «Maliyyə nəzarəti və auidit» — mənbədəki yazı səhvi ilə,
«Komputer sistemləri və şəbəkələri», «Dizayn (Qrafik)» dublikatları …).
Bunlara **toxunulmayıb**.

**HƏR proqram üçün bir sətirlik, doldurulacaq markdown cədvəli** birbaşa
bazadan çıxarılır — sahib 1-ci gün onu çap edib doldura bilər:

```bash
python manage.py set_program_official_codes --table
```

Sütunlar: `Daxili kod · Ad · Pillə · Hazırkı rəsmi şifr · Namizəd · Mənbə ·
**Təsdiqlənmiş şifr** (boş ☐)`.

---

## 9. Necə tətbiq olunur

```bash
# 1) planı gör — heç nə yazmır (DEFOLT dry-run)
python manage.py set_program_official_codes

# 2) yalnız buraxılanların siyahısı (baza sorğusu yoxdur)
python manage.py set_program_official_codes --holds

# 3) sahibin doldurulacaq cədvəli
python manage.py set_program_official_codes --table

# 4) yaz
python manage.py set_program_official_codes --apply

# 5) təmiz daxili şifrləri də mənimsə (§7)
python manage.py set_program_official_codes --apply --adopt-clean-codes

# 6) tək tenant
python manage.py set_program_official_codes --apply --organization <organization-id>
```

* **Defolt dry-run** — `--apply` verilmədən heç nə yazılmır.
* **İdempotent** — ikinci icra heç nə yazmır.
* **Fail-closed** — ad, təhsil pilləsi uyuşmursa VƏ YA sətirdə artıq **fərqli**
  rəsmi şifr varsa HEÇ NƏ yazılmır (səssiz üstünə yazma yoxdur).
* **Mexaniki sağlamlıq yoxlaması** — cədvəlin özü hər icrada `05`=bakalavr /
  `06`=magistr qaydasından keçir; pozulsa komanda dayanır. `050624` səhvini
  məhz bu sinif yoxlama tutdu.
* **`code` heç vaxt dəyişdirilmir** — audit qeydində `internal_code_unchanged`
  sahəsi bunu sənədləşdirir.
* Hər yazı `core.audit.log_action` ilə audit izinə düşür: köhnə → yeni, **sübut
  səviyyəsi** (`doğrulanmış` / `mənimsənilmiş`) və hər iki mənbə.

**Yeni sətir necə əlavə olunur:** `_program_official_codes.py` faylındakı
`ASSIGNMENTS` cədvəlinə `CodeAssignment(...)` əlavə et — `source_primary` və
`source_secondary` **iki fərqli mənbə** olmalıdır, əks halda
`apps/registrar/tests/test_program_official_codes.py` qırmızı olur. Həmin test
həm də tətbiq olunanların sayını və rədd edilmiş sətirlərin cədvəldən
KƏNARDA qalmasını kilidləyir.
