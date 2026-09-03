# Dizayn Mərhələ 4 — Dərs yükü zənciri (ekran 12 · 13 · 14 · 15 · 16 · 17)

**Tarix:** 2026-09-03 · **Budaq:** `audit/post-migration-qa-2026-09` (bu keçiddə commit YOXDUR —
paralel Mərhələ 5/6 agenti işlək ağacı öz commit-lərinə daxil edib, bax §9)
**Mənbə:** `docs/design/HANDOFF_FULL_PLAN.md` §2 (12–17) · `docs/design/handoff_full/README.md` §5 MODUL C + §6.3 + §8 ·
`docs/workload/DERS_YUKU_SPEC.md` §4, §5.3–5.4, §6.1/6.2/6.5, §8 · `docs/audits/2026-09-02/PHASE4_WORKLOAD.md` (F0/F3/F4)
**Əvvəlki mərhələlər:** `DESIGN_STAGE1.md` (qabıq bölgüsü, `ems_ui`, TŞ rolları) · `DESIGN_STAGE2.md`
(təsdiqlənmiş `Curriculum`, `plan.*`/`semester.*`) — hər ikisi TƏKRAR İSTİFADƏ olundu.

**Bu keçid handoff §6.3-ün BÜTÜN zəncirini qapadır:**

```
Tədris şöbəsi (12) yaradır/idxal edir → GÖNDƏRİR
    → hər toxunulan FAKÜLTƏ üçün bir TaskFacultySlice
    → Koordinator (13) sətir-sətir viza / irad
    → Dekanlıq (15) dilimi təsdiqləyir  ya da seçilmiş sətirləri səbəblə qaytarır
    → BÜTÜN dilimlər təsdiqlənəndə sənəd `approved` (aşağıdan yuxarı törəyir)
    → Kafedra müdiri (14) müəllimlərə bölür → təsdiq → offering sinxronu
    → Müəllim (16) yükü TƏSDİQLƏYİR və ya 4 səbəbdən biri ilə ETİRAZ edir
    → Rektorluq (17) yalnız AQREQASİYA görür (sətir redaktəsi YOXDUR)
```

---

## 0. Bölmə açarları və qabıq

Dördü də **kabinet bölməsidir** (`/accounts/profile/?section=…`): sol sidebar qalır, panel sağda,
`<h1>` bölmə şablonunda YAZILMIR (canlıda ölçüldü — hər ekranda `h1` sayı = **1**).

| # | Bölmə açarı | Sidebar etiketi | Qapı |
| --- | --- | --- | --- |
| 12 | `workload-center` | Dərs yükü mərkəzi | `workload.manage` (+ `workload.submit` göndərmə üçün) |
| 13 | `workload-visa` | Yük vizası | `workload.review` |
| 15 | `workload-approval` | Yük təsdiqi | `workload.approve` |
| 17 | `workload-overview` | Yük — ümumi baxış | `workload.report` |
| 14 | `workload-distribution` (mövcud) | Yük bölgüsü | dəyişmədi — **zəncir qapısı əlavə olundu** |
| 16 | `my-workload` (mövcud) | Dərs yüküm | dəyişmədi — **təsdiq/etiraz bloku əlavə olundu** |

Dördü də `AJAX_SAFE_SECTIONS`-dədir və **SERVER-render OXU panelidir**; bütün mutasiyalar TƏK JSON
POST endpoint-inə (`workload:action` → `/ders-yuku/emel/`) gedir. Ona görə AJAX swap təhlükəsizdir.

Sidebar girişləri mövcud «UNİVERSİTET» qrupundadır (`_sidebar_university.html`) — yeni qrup açılmadı.

---

## 1. İcazələr — zəncirin dörd halqası

### 1.1 Yeni açar

`workload.object` (`apps/organizations/permissions.py`, «workload» kateqoriyası + AZ etiket).
Qalan üçü (`submit`/`review`/`approve`) FAZA 3-dən bəri **kataloqda var idi, heç bir rolda yox idi** —
bu keçid onları açır.

### 1.2 Paylanma — `apps/organizations/default_roles_stage4.py`

| Rol | view | manage | submit | review | approve | distribute | object | report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `teaching_office_head` | ✔ | ✔ | ✔ | — | — | — | — | ✔ |
| `teaching_office_staff` | ✔ | ✔ | ✔ | — | — | — | — | — |
| `program_coordinator` | ✔ | — | — | ✔ | — | — | — | — |
| `dean` | ✔ | — | — | — | ✔ | — | — | ✔ |
| `chair_head` (F3-dən) | ✔ | ✔ | — | — | — | ✔ | — | ✔ |
| `teacher`/`assistant`/`lab_assistant` | ✔ | — | — | — | — | — | ✔ | — |
| `rector` (`*`) · `vice_rector`/`ikt_rehber` (`workload.*`) | hamısı | | | | | | | |

**SƏLAHİYYƏT AYRILIĞI testlə kilidlənib** (`test_stage4_chain_is_split_across_roles`): göndərən
təsdiqləmir, viza verən qaytarmır, təsdiqləyən bölmür; `workload.approve` operator rollarından
başqa YALNIZ dekandadır.

> ⚠️ **Mövcud test yeniləndi (plan §2/15 bunu qabaqcadan qeyd etmişdi):**
> `test_permission_catalog.py::test_default_roles_carry_the_expected_split` «`approve` heç kimdə
> yoxdur» iddiasını daşıyırdı (F2 hələ yox idi). İndi o iddia YENİ testlə əvəzlənib — dekanın
> `approve` daşıması artıq DÜZGÜN vəziyyətdir.

### 1.3 Migrasiya

`apps/workload/migrations/0006_seed_stage4_permissions.py` — xəritə `default_roles_stage4`-dən
OXUNUR (seed ↔ migration sürüşə bilmir), idempotent, geri dönüş YALNIZ bu dörd açarı çıxarır
(F3-ün `view/manage/distribute/report` açarlarına toxunmur). Miqrasiya QƏSDƏN `apps/workload`-dadır
(`organizations` nömrələri paralel axınlarda tutulub — `0003_seed_permissions` naxışı).

---

## 2. Model dəyişiklikləri

`apps/workload/models/review.py` (**yeni modul**) + `0004_stage4_review_models` +
`0005_rls_stage4` (RLS + trigger).

| Model | Cədvəl | Açar məqamlar |
| --- | --- | --- |
| `TaskFacultySlice` | `workload_taskfacultyslice` | spec §5.3: task + faculty + **revision**, `pending/approved/returned`, `decided_by/at`, `comment`. UNIQUE `(task, faculty, revision)` — **qaytarma-göndərmə dövrəsində köhnə qərar TARİXÇƏ kimi qalır, silinmir** |
| `TaskRowReview` | `workload_taskrowreview` | spec §5.4: row + coordinator + `reviewed/flagged` + comment. UNIQUE `(row, coordinator)` — viza CARİ vəziyyətdir, tarixçə `core.audit`-dədir |
| `LoadObjection` | `workload_loadobjection` | ekran 16: row + assignment + teacher + `reason_key` (4 hərfi səbəb) + text + `open/accepted/rejected` + qərar sahələri. **APPEND-ONLY** (DB trigger) |
| `TeacherWorkloadProfile` | *(mövcud)* | **+ `load_confirmed_at`** — müəllimin illik yük təsdiqi (ekran 16 §4) |

**DB qorumaları (`0005`, yalnız PostgreSQL):**
1. üç yeni cədvəldə `ENABLE + FORCE ROW LEVEL SECURITY` + `rls_tenant_isolation` (bypass GUC və ya
   `organization_id = app.current_org_id`);
2. `workload_objection_append_only` trigger-i — **MƏTN toxunulmazdır**: `text`/`reason_key`/`row_id`/
   `created_at` dəyişən UPDATE və hər DELETE rədd olunur; qərar sahələri (`status`,
   `resolved_by/at`, `resolution_note`) icazəlidir.

⚠️ Miqrasiyada `params=None` (plpgsql `%` tələsi — `0002_rls_workload` şərhi).

---

## 3. State maşını — `apps/workload/state_machine.py` (SAF modul)

Django modelini import ETMİR (`apps/syllabus/state_machine.py` naxışı), ona görə testdə bazasız
yoxlanılır və qayda İKİ yerdə yazılmır.

```
draft ──submit──> submitted ──dekan qaytardı──> returned ──resubmit(revision++)──> submitted
                     ├── bütün dilimlər təsdiqləndi ──> approved  (pending_final_approval da mümkündür)
approved ──ilk bölgü──> distributing ──müdir təsdiqi──> distributed ──düzəliş──> amended ──> distributed
draft / submitted ──> cancelled
```

* **`approved` HEÇ VAXT əl ilə qoyulmur** — `recompute_task_status` onu dilimlərin yekunundan
  TÖRƏDİR (spec §4.2/5). Qismən təsdiq sənədi `submitted` saxlayır (test var).
* **`returned` bütöv sənədi yox, SEÇİLMİŞ sətirləri işarələyir** (`review_status=returned`);
  yenidən göndəriş həmin işarələri təmizləyir və `revision`-u artırır.
* Statuslar `constants.TaskStatus`-un DOKUZU DA istifadədədir (F0-da yalnız kataloqda idilər).

---

## 4. Servislər (`apps/workload/services/`, hamısı < 600 sətir)

| Fayl | Məsuliyyət |
| --- | --- |
| `workflow.py` | `submit_task` (dilimləri yaradır), `approve_slice`, `return_slice`, `recompute_task_status`, `slice_progress`, `submit_summary`, `ensure_distribution_stage`, `ensure_reason` (≥20), bildirişlər |
| `reviews.py` | koordinator növbəsi + `set_row_review` (**irad `reviewed`-i SİLİR**, atomic), `review_all`, `review_counts`, `row_remarks`, `coordinator_specialty_ids` (fail-closed) |
| `generation.py` | **təsdiqlənmiş plandan sətir törətməsi** — `Curriculum(status=approved)` × ixtisasın qrupları × semestr; İDEMPOTENT |
| `imports.py` | Excel sehrbazı: `parse_workbook` (openpyxl read-only, ≤10 MB / ≤1000 sətir), `build_mapping` (kataloq uyğunluğu), `apply_import` (yalnız ƏLAVƏ edir) |
| `objections.py` | `create_objection` (4 səbəb), `confirm_own_load`, `resolve_objection`, `chair_objections`, `my_objections` |
| `overview.py` | **aşağıdan yuxarı aqreqasiya** (§8/13) + `load_band` |

### Qərar 1 — bölgü YALNIZ zəncirdən sonra (plan §2/14)

`assignments._ensure_assignable` indi ƏVVƏLCƏ `workflow.ensure_distribution_stage`-i çağırır:

* `submitted` / `returned` / `pending_final_approval` → **403 `workload.not_approved_yet`**;
* `draft` **YALNIZ heç vaxt göndərilməmiş** sənəd üçün açıqdır (`submitted_at is None`) — bu, F1-dən
  ƏVVƏL kafedranın öz yaratdığı sənədləri (klondakı real data) işlək saxlayır;
* `approved` `ASSIGNABLE_STATUSES`-ə əlavə olundu və ilk təyinatda `distributing`-ə keçir.

Ekran 14-də bu, sarı lentlə də göstərilir («Tapşırıq dekanlıq təsdiqini gözləyir»).

### Qərar 2 — «dekanın ikinci təsdiqi» AÇIQDIR

`constants.DEAN_SECOND_APPROVAL_ENABLED = True` (handoff §10.2 açıq qərarı — dərs yükü üçün DEFAULT
AÇIQ, sillabus üçün söndürülü). Bayraq ailə-ailə saxlanılır, kodda hardcode şərt yoxdur.

### Qərar 3 — arxiv semantikası

`center_registry.is_archive_year(org, year)`: cari dövrün `academic_year`-ından KİÇİK il = arxiv.
`actions._ensure_writable` hər mutasiyada onu yoxlayır (**403 `workload.archive_readonly`**), UI isə
sarı lent göstərir və yazma düymələrini render ETMİR.

---

## 5. Ekranlar

### 12 · `workload-center` «Dərs yükü mərkəzi» (tədris şöbəsi)

* **Beş görünüş** (dizayn `state.view`): `dashboard` · `tasks` · `import` · `reports` · `settings`.
  Son ikisi QƏSDƏN boş vəziyyətdədir («Bu bölmədə hələ məlumat yoxdur») — handoff onları belə saxlayır.
* **İdarə paneli:** 4 KPI (CƏMİ KAFEDRA / GÖNDƏRİLMİŞ / TƏSDİQLƏNMİŞ / QAYTARILMIŞ) + kafedra
  kartları (status çipi — `workload_task` ailəsinin **9 statusu**, saat, kredit, Payız/Yaz bölgüsü).
* **Tapşırıq redaktoru:** rəsmi TAPŞIRIQ şablonunun **20 sütunu** (sticky birinci sütun, öz
  konteynerində üfüqi sürüşmə), alt yekun zolağı (PAYIZ / YAZ / ÜMUMİ SAAT / CƏMİ KREDİT),
  server səhifələməsi (25/səhifə), göndərmə xəbərdarlıqları (BLOKLAMIR — spec §5.2).
* **İzləmə:** dilim-dilim matris (fakültə × status), koordinator vizası `X / Y`, dekan qərarı və
  şərh, qaytarılan sətirlərin siyahısı.
* **«Tədris planından gətir»:** Mərhələ 2-nin TƏSDİQLƏNMİŞ planından sətir törədir (ixtisas
  çoxseçimi; planı olmayan ixtisas «plan yoxdur» qeydi ilə göstərilir və sətir vermir).
* **Excel import sehrbazı:** 3 addımlı stepper, multipart yükləmə, kataloq uyğunluğu cədvəli
  («Uyğunlaşdı» / «Mətn kimi qalacaq»), 4 KPI, «İdxal et» / «Ləğv et».
* **«Dekanlıqlara göndər»:** sətir yoxdursa və ya marşrutsuz sətir varsa düymə **disabled**
  (gizlədilmir — §4); server də `workload.no_faculty_slice` / `no_rows` verir.

### 13 · `workload-visa` «Yük vizası» (koordinator)

* İki görünüş: `queue` (default) · `history` («Mənim hərəkətlərim»).
* 4 KPI + faiz progress («{done} sətirdən {n}-i baxılıb»), 4 filtr (il / semestr / viza / axtarış).
* Sətir əməlləri: **«Baxdım»** (dialoqsuz POST) və **«İrad»** (səbəb dialoqu ≥20 simvol, ipucu
  «Şərh yazılmadan irad göndərilə bilməz.»); başlıqda **«Hamısına viza ver»**.
* **Əhatə:** yalnız öz ixtisası; əhatəsiz aktor BOŞ siyahı + «administrator ilə əlaqə saxlayın»
  mətnini alır (§8/4 — «no scope ≠ bütün universitet»).

### 15 · `workload-approval` «Yük təsdiqi» (dekan)

* Üç görünüş: `queue` · `summary` (kafedralar üzrə yekun) · `history` (timeline).
* 4 KPI (dilimin cəmi saatı / cəmi kredit / ixtisas sayı / iradlı sətir), koordinator vizası sütunu.
* **Toplu əməllər:** «Seçilmişləri qaytar» ≥1 sətir seçildikdə aktivləşir (əks halda `disabled`),
  «Dilimi TƏSDİQLƏ» təsdiq dialoqu ilə. Qaytarma səbəbi ≥20 simvol, auditli, bildirişli.
* Fakültə yekunu **SAXLANILMIR** — hər sorğuda kafedra sətirlərindən hesablanır.

### 17 · `workload-overview` «Ümumi baxış» (rektorluq — YALNIZ OXU)

* Dörd görünüş: `overview` · `fac` · `dep` · `rep` (hesabatlar — boş vəziyyət).
* 4 KPI (ümumi tədris yükü / bölünmüş yük + progress / vakant saat / norma aşımı), təsdiq axını
  (status → kafedra sayı), «Diqqət tələb edən kafedralar», fakültə və kafedra cədvəlləri
  (`load_band` 4 bandı, `workload_task` statusu).
* **Sətir səviyyəsində redaktə YOXDUR** — heç bir əməl düyməsi render olunmur.
* **§8/13:** kafedra → fakültə → universitet; yekun rəqəmlər HEÇ BİR CƏDVƏLDƏ saxlanılmır.
  Sorğu büdcəsi **9 sorğu**, kafedra sayından ASILI DEYİL (`assertNumQueries(9)` testi var).

### 14 · `workload-distribution` (mövcud — uyğunlaşdırıldı)

* Zəncir qapısı (yuxarıda Qərar 1) + sarı lent «Tapşırıq dekanlıq təsdiqini gözləyir».
* **Müəllim etirazları paneli:** kafedra müdiri etirazı görür, «Qəbul et» / «Rədd et» ilə bağlayır
  (mətn TOXUNULMUR — append-only), qərar auditə düşür. Etiraz bölgünü DAYANDIRMIR.

### 16 · `my-workload` (mövcud — uyğunlaşdırıldı)

* **«Yükü təsdiqlə»** (təsdiqləndikdən sonra «Yükü təsdiqləmisiniz» qeydi) və **«Etiraz bildir»**
  dialoqu: hədəf sətir seçicisi + **4 hərfi səbəb** (Saat sayı düz deyil · Qrup/tələbə sayı səhvdir ·
  Fənn ixtisasım deyil · Norma həddindən artıqdır) + ≥20 simvol izah.
* **«Etirazlarım»** siyahısı (səbəb, mətn, status, kafedra qərarı).
* ⛔ **Fərdi iş planı (4 bölmə, plan/fakt) və ödəniş kalkulyatoru bu keçidə DAXİL DEYİL** — bax §8.

---

## 6. Testlər — `apps/workload/tests/`

| Fayl | Nəyi sübut edir | Say |
| --- | --- | --- |
| `test_stage4_workflow.py` | saf state maşını (qanuni + **qanunsuz** keçidlər); göndərmə (dilim/fakültə, boş sənəd, təkrar göndəriş 409); viza (öz ixtisası, yad ixtisas 403, **irad `reviewed`-i silir**, şərhsiz irad 400, mərhələ bitəndə viza bağlanır); dekan (tam/qismən təsdiq, yad fakültə 403, səbəbsiz qaytarma, qaytarma → sətir işarəsi → yenidən göndəriş + revision + KÖHNƏ dilim tarixçədə); **bölgü qapısı** (təsdiqdən əvvəl 403, sonra açılır, köhnə draft işləyir); etiraz (4 səbəb, yanlış səbəb, yad sətir 403, təsdiq bayrağı, kafedra görür) | 25 |
| `test_stage4_sections.py` | dörd-yerli qeydiyyat müqaviləsi; **rol matrisi** (TŞ→12/17, koordinator→13, dekan→15/17, rektor→17; müəllim/tələbə heç birini görmür; kafedra müdiri 12-ni görür, 13/15-i yox); `workload:action` qapıları (GET 405, naməlum əməl 400, kafedra müdiri göndərə bilmir, koordinator təsdiqləyə bilmir, səbəbsiz qaytarma 400, **korlanmış UUID 500 vermir**); **arxiv read-only**; aqreqasiya (fixture rəqəmləri, vakant roll-up, **sorğu büdcəsi 9**, əhatəsiz aktor boş) | 18 |
| `test_stage4_generation.py` | plandan törətmə (saat/kredit/ixtisas/fakültə/fəsil, **idempotentlik**, qaralama plan mənbə deyil, göndərilmiş sənədə törətmə 409); Excel (parse + uyğunlaşdırma, tapılmayan ad MƏTN kimi qalır, yanlış uzantı); **bildiriş alıcıları** (göndəriş→dekan, qaytarma→TŞ + kafedra rəhbəri, təsdiq→kafedra rəhbəri) | 10 |
| `test_stage4_rls.py` (`postgres`) | üç yeni cədvəlin tenant izolyasiyası, kontekstsiz = 0 sətir, **etiraz mətni append-only** (UPDATE + DELETE rədd), qərar sahələri redaktə oluna bilir | 5 |
| `test_permission_catalog.py` (yeniləndi) | `workload.object` kataloqda; **zəncirin dörd halqası dörd AYRI rolda** | 6 |

**Yekun (öz izolyasiya bazamda `…:55432/ems_ds4_3igj10`):**

```
apps/workload/tests + apps/organizations/tests + apps/accounts/tests
    → 1 793 keçdi, 1 skip, 1 uğursuz  (3 dəq 47 san)
apps/workload/tests/test_stage4_rls.py + test_rls.py  (emsarena_ci_rls rolu ilə)
    → 10 keçdi
```

> ⚠️ **Həmin 1 uğursuzluq MƏNİM DEYİL** —
> `test_account_archive_postgres.py::test_archiving_opens_the_registrar_guard_without_opening_the_login`:
> XAM SQL INSERT `registrar_studentacademicrecord.admission_exam_type` NOT NULL sütununu vermir
> (Mərhələ 3 agentinin `0066` miqrasiyası). `DESIGN_STAGE2.md` §5-də də eyni cür qeyd olunub.

**Qapılar:** `black` ✅ · `isort` ✅ · `flake8` ✅ · `check_module_size --check` ✅ ·
`module_deps --check` ✅ (yeni dövr yoxdur) · `check_worker_atomic_coverage --check` ✅ ·
`makemigrations --check` ✅ («No changes detected»).
`check_i18n_catalogs.py` ⚠️ **QIRMIZI — paylaşılan sayğac:** `django/source_missing 0 → 189`;
içində Mərhələ 4, 5 və 6-nın yeni msgid-ləri var (`.po`-lara TOXUNULMADI — i18n keçidi doldurur).

---

## 7. Canlı yoxlama — QA klonu (`http://127.0.0.1:8100`, real köçürülmüş data)

Klon miqrasiya olundu (`workload 0004/0005/0006`). Rol backfill-i klonda ölçüldü:
`program_coordinator → workload.review`, `dean → workload.approve`, `teacher → workload.object`,
`teaching_office_head → workload.submit`.

**Test datası:** tədris ili **2027/2028** (2026/2027 FAZA 4-ün canlı yoxlaması tərəfindən tutulub;
cari dövr 2025/2026 olduğu üçün 2027/2028 arxiv DEYİL). İki QA-DS4 tapşırığı, sətir adları
`QA-DS4 …` prefiksi ilə. Koordinator/dekan əhatəsi üçün **müvəqqəti** `qa_ds4_coordinator` /
`qa_ds4_dean` rolları yaradıldı (mövcud üzvlüklərə TOXUNULMADI) və sonda silindi.

### Ölçülmüş axın

| Addım | Aktor | Nəticə |
| --- | --- | --- |
| Tapşırıq yaradıldı | `qa.teaching_office_head` | `200 {"created": true}` |
| 2 sətir (real fənn + real qrup `229 İT`) | — | 90 saat, 10 kredit |
| **Göndər** | `qa.teaching_office_head` | `200` → `submitted`, **1 fakültə dilimi** |
| **Viza + İrad** | `qa.program_coordinator` | sətir 1 `reviewed`, sətir 2 `flagged` (irad mətni saxlandı) |
| **Dilimi təsdiqlə** | `qa.dean` | `200` → dilim `approved`, **sənəd avtomatik `approved`** |
| Bölgü (4 təyinat) + təsdiq | `qa.chair_head` | `distributed` |
| **Etiraz** (`hours`) + **yük təsdiqi** | `qa.teacher` | `200` — etiraz `open`, `load_confirmed_at` yazıldı |
| Kafedra etirazı görür | `qa.chair_head` | `[('qa.teacher', 'hours', 'open')]` |
| **Ümumi baxış** | `qa.rector` | `planned 270 · assigned 90 · 33% · 6 fakültə · 18 kafedra` |

**BRAUZERDƏ (real UI, 1280×1500):**

* **12 «Dərs yükü mərkəzi»** — KPI `CƏMİ KAFEDRA 18 · GÖNDƏRİLMİŞ 0 · TƏSDİQLƏNMİŞ 1 · QAYTARILMIŞ 0`,
  18 kafedra kartı status çipi ilə; redaktorda 2 sətir, yekun zolağı `PAYIZ 90 / YAZ 0 / ÜMUMİ 90 /
  KREDİT 10`, cədvəl ÖZ konteynerində sürüşür (2004 px → 898 px); izləmə paneli
  «Yüksək texnologiyalar… · Təsdiqlənib · 2 / 2 · QA Dean»; Excel import stepper `1 current / 2,3 todo`.
* **13 «Yük vizası»** — 3 sətir, «Baxdım»/«İrad» düymələri. **İrad dialoqu brauzerdə icra olundu:**
  gizli sahələr (`action=row_review`, `row=…`, `state=flagged`) düzgün doldu, səbəb sayğacı `47 / 20`,
  göndərişdən sonra panel yeniləndi → KPI `İRADLI 1 · 33% baxılıb`, sətir badge-i «İradlı».
* **15 «Yük təsdiqi»** — KPI `180 saat · 18 kredit · 1 ixtisas · 1 iradlı sətir`;
  «Seçilmişləri qaytar» seçim boş ikən **disabled**, 1 sətir seçiləndə aktiv («1 sətir seçilib»).
  **Qaytarma brauzerdə icra olundu** → DB-də: dilim `returned` + səbəb mətni, **YALNIZ seçilmiş sətir**
  `returned`, qalan ikisi `pending`, sənəd `returned`.
* **17 «Ümumi baxış»** — `ÜMUMİ TƏDRİS YÜKÜ 270 saat · BÖLÜNMÜŞ 90 (33%) · VAKANT 0 · NORMA AŞIMI 0`;
  təsdiq axını `Qaytarılıb 1 · Bölüşdürülüb 1 · Tapşırıq yoxdur 16`; fakültə cədvəli 6 sətir.
* **16 «Dərs yüküm»** — «Yükü təsdiqləmisiniz» + «Etiraz bildir»; etiraz siyahısı səbəb etiketi və
  statusla; dialoqda 4 hərfi səbəb və 5 hədəf sətir.

**375×812 (mobil):** `document.scrollWidth == clientWidth == 375` (üfüqi sürüşmə **0**), `h1` sayı **1**,
KPI 1–2 sütuna düşür, filtr sütuna düşür, **20 sütunlu cədvəl öz konteynerində sürüşür** (2004 → 341).

**Konsol / şəbəkə:** `performance.getEntriesByType('resource')` üzrə **≥400 statuslu sorğu 0**
(hər dörd ekranda ayrıca ölçüldü).

### Canlı QA-da tapılan və düzəldilən 3 defekt

1. **`KeyError: 'faculty'`** — `_task_view` qaytardığı `filters` açarı dashboard filtrlərini ƏZİRDİ
   (`wc_faculty`/`wc_status` itirdi). Həll: sətir filtrləri `row_filters` açarına köçdü.
2. **`TemplateSyntaxError`** — `_center_editor.html`-də `banner_title=…banner_action_include=`
   yapışıq qalmışdı (skriptlə redaktə tələsi).
3. **Dilim badge-i «pending» xam açar kimi görünürdü** — `workload_line` ailəsi dizayn üzrə ÜÇ pill
   saxlayır (`sent/returned/approved`), `SliceStatus.PENDING` isə `pending`-dir. Həll: glue qatında
   `status_key` («pending» → «sent»); status kataloquna açar ƏLAVƏ EDİLMƏDİ (Mərhələ 0 testləri
   ailənin dəqiq tərkibini kilidləyir).

**Təmizlik:** hər iki QA-DS4 tapşırığı (5 sətir, 2 dilim, 4 viza, 1 etiraz, 4 təyinat), müəllim yük
profili və iki müvəqqəti rol/üzvlük klondan silindi; köçürülmüş datadan HEÇ NƏ dəyişmədi
(`CourseOffering` yaranmayıb — sətirlərin `period`-u yox idi, sinxron onları atlayır).

> 📌 **Qeyd olunası tapıntı:** etirazı olan tapşırığın CASCADE DELETE-i **append-only trigger-i
> tərəfindən bloklandı** (`workload_loadobjection append-only: DELETE qadagandir`). Bu, qorumanın
> düzgün işlədiyinin sübutudur — məhsulda tapşırıq SİLİNMİR, `cancelled` olur. QA təmizliyi üçün
> trigger bir əməliyyatlıq söndürülüb və dərhal geri qaytarılıb.

---

## 8. Təxirə salınanlar / sahib qərarı gözləyənlər

1. **Fərdi iş planı (ekran 16, `PLAN`)** — 4 bölmə (tədris / metodiki / elmi-tədqiqat / inzibati),
   plan-fakt saatı, KQ-12 sənədi. `IndividualPlan` + `PlanItem` modelləri YARADILMADI: bölmələrin
   siyahısı və norma cədvəli tenant-konfiqurasiyalı olmalıdır (spec §8) və sahib qərarı tələb edir.
2. **Ödəniş kalkulyatoru və aylıq saathesabı cədvəli (ekran 16, `PAID`)** — tarif dəyəri
   (`12,50 ₼/saat`) universitet-daxili qərardır; `WorkloadSettings` modeli açılana qədər
   uydurulmadı.
3. **Ekran 12 `reports` / `settings` və ekran 17 `rep`** — handoff onları QƏSDƏN boş vəziyyətdə
   saxlayır; F5 hesabat paketi ilə gələcək.
4. **Sətir-içi (inline) grid redaktəsi (ekran 12/2 «jd2 üslubu»)** — tapşırıq redaktoru bu keçiddə
   OXU cədvəlidir; sətir mənbələri PLAN və EXCEL-dir. Sətir-sətir əl redaktəsi mövcud kafedra
   modalı ilə (ekran 14) edilir; ikinci redaktə modeli qəsdən açılmadı.
5. **`pending_final_approval` (prorektor mərhələsi)** — state maşınında var və keçidləri
   yoxlanılır, LAKİN heç bir səth onu qurmur: mərhələnin aktivliyi org-konfiqurasiyasıdır
   (spec §8) və `WorkloadSettings` ilə birlikdə gəlməlidir.
6. **`workload_task` badge ailəsi** — `core/ui/status_catalog.py`-a YENİ ailə kimi əlavə olundu
   (9 status + `none`). `workload_line` və `workload_visa` ailələrinə açar ƏLAVƏ EDİLMƏDİ: Mərhələ 0
   testləri onların dəqiq tərkibini kilidləyir, uyğunlaşma glue qatındadır.
7. **Excel şablonunun yüklənməsi («Nümunə şablonu buradan yükləyin»)** — idxal başlıq adına görə
   xəritələnir, ona görə şablon faylı bloklayıcı deyil; hazır `.xlsx` şablonu F5-ə qaldı.

---

## 9. Dəyişən / yaranan fayllar

**Yeni:**
`apps/workload/state_machine.py` · `apps/workload/actions.py` ·
`apps/workload/{center,review,approval,overview}_registry.py` ·
`apps/workload/models/review.py` ·
`apps/workload/services/{workflow,reviews,generation,imports,objections,overview}.py` ·
`apps/workload/migrations/{0004_stage4_review_models,0005_rls_stage4,0006_seed_stage4_permissions}.py` ·
`apps/workload/tests/{test_stage4_workflow,test_stage4_sections,test_stage4_generation,test_stage4_rls}.py` ·
`apps/organizations/default_roles_stage4.py` ·
`apps/accounts/views/profile/_sections/{workload_center,workload_chain}.py` ·
`apps/accounts/templates/accounts/profile/sections/{_workload_center,_workload_visa,_workload_approval,_workload_overview}.html` ·
`…/sections/workload/{_center_header_actions,_center_editor,_center_tracking,_center_import,_center_warnings,_task_fields,_generate_fields,_visa_header_actions,_visa_row_actions,_approval_header_actions,_approval_row_actions,_objection_fields}.html` ·
`apps/accounts/static/accounts/css/profile/sections/workload_chain.css` ·
`apps/accounts/static/accounts/js/profile/workload_chain.js` ·
`docs/audits/2026-09-02/{DESIGN_STAGE4.md,DESIGN_STAGE4_MSGIDS.txt}`

**Dəyişən:**
`apps/workload/{constants,public,urls}.py` · `apps/workload/models/{__init__,assignment}.py` ·
`apps/workload/services/{__init__,assignments,distribution,tasks}.py` ·
`apps/workload/tests/test_permission_catalog.py` ·
`apps/organizations/{permissions,default_roles_university}.py` ·
`apps/accounts/views/_helpers/rbac_sections.py` ·
`apps/accounts/views/profile/sections_api.py` · `…/_sections/labels.py` ·
`…/context_builder/{_stage2,_stage4,_teaching_office}.py` ·
`apps/accounts/templates/accounts/profile.html` ·
`…/profile/{_section_assets,_section_dispatch,_sidebar_university}.html` ·
`…/sections/{_my_workload,_workload_distribution}.html` · `core/ui/status_catalog.py`

⚠️ **Commit vəziyyəti:** bu keçiddə commit edilməyib, LAKİN paralel işləyən Mərhələ 5/6 agenti
`ce626464` / `fbb629cd` commit-lərində işlək ağacı bütövlükdə commit etdiyi üçün bu keçidin bir
hissəsi (`labels.py`, `sections_api.py`, `rbac_sections.py`, `status_catalog.py`, `permissions.py`,
`_section_assets.html`, `_section_dispatch.html` və s.) həmin commit-lərin içinə düşüb. Kod itməyib;
sahib ayrıca commit istəyirsə qalan işlək ağac (`git status`) hələ də ayrıca commit edilə bilər.

**Toqquşma riski:** `sections_api.py`, `labels.py`, `rbac_sections.py`, `_stage2/_stage4/_teaching_office.py`,
`profile.html`, `_section_assets.html`, `_section_dispatch.html`, `_sidebar_university.html`,
`permissions.py`, `default_roles_university.py`, `status_catalog.py` — paralel agentlər də toxunur.
Hər dəyişiklik AYRI blokdur (mövcud sətirlərin arasına əlavə).

---

## 10. i18n — yeni msgid-lər (kataloqları BAŞQA keçid doldurur)

`.po` fayllarına **TOXUNULMADI**. **282 msgid, 10 kontekst.**
Tam siyahı: `docs/audits/2026-09-02/DESIGN_STAGE4_MSGIDS.txt`.

| Kontekst | Say |
| --- | --- |
| `accounts.workload_center` | 113 |
| `accounts.workload_approval` | 44 |
| `accounts.workload_visa` | 40 |
| `accounts.workload_overview` | 35 |
| `accounts.workload` (ekran 14/16 əlavələri) | 19 |
| `workload` (constants: `SliceStatus`, `ObjectionReason`, `ObjectionStatus`) | 10 |
| `ui.status` (yeni `workload_task` ailəsi) | 10 |
| `workload.model` (üç yeni model) | 6 |
| `profile.sidebar` | 4 |
| `organizations.permission.label` | 1 |
