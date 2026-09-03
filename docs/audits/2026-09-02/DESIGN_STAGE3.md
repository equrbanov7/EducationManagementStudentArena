# Dizayn Mərhələ 3 — Tələbə Xidmətləri Mərkəzi (ekran 08–09)

**Tarix:** 2026-09-03 · **Budaq:** `audit/post-migration-qa-2026-09` (commit YOX — sahibin tələbi)
**Mənbə:** `docs/design/HANDOFF_FULL_PLAN.md` §2/08–09, §3 · `docs/design/handoff_full/README.md` §5 (MODUL B), §6.2, §8
**Əhatə:** 08 Tələbə qəbulu — ATİS və qrup təyinatı · 09 Tələbə reyestri və hərəkəti

---

## 1. Rol və icazələr

### 1.1 Yeni rol — `apps/organizations/default_roles_student_services.py`

| Açar | Ad (AZ) | Səviyyə | Scope |
| --- | --- | --- | --- |
| `student_services` | Tələbə Xidmətləri Mərkəzi | **60** | ORGANIZATION |

Fayl AYRIDIR (`default_roles_teaching_office.py` ilə eyni səbəb: `default_roles_university.py`
577/600 idi); siyahı orada `UNIVERSITY_ROLES.extend(...)` ilə birləşir — seed, migration və
testlər TƏK mənbədən oxuyur.

**`ADMIN_ALIAS_EXEMPT_ROLE_NAMES`-ə əlavə LAZIM DEYİL:** səviyyə 60 < 80, yəni implicit
`org_admin` aliası onsuz da verilmir (`teaching_office_head` 85-də olduğu üçün oraya
əlavə edilməli idi). Test bunu kilidləyir + org-admin səthlərinin (`permission-editor`,
`manage-roles`, `role-assignment`, `org-roles`) verilmədiyi ayrıca yoxlanılır.

**Səlahiyyət ayrılığı (əsasnamə 5.5):** rolda `user.import` VAR, RİM-in
`user.credentials` / `user.block` / `user.soft_delete` açarları **YOXDUR** — qəbul
operatoru mövcud hesabın parolunu sıfırlaya bilməməlidir (testlə qorunur).

### 1.2 Yeni icazə ailəsi `student.*`

`apps/organizations/permissions_stage3.py` (Mərhələ 2-nin `permissions_stage2.py` naxışı —
`permissions.py` ölçü büdcəsinə görə DATA ayrı modulda, birləşmə bir sətirdə).

| Açar | Nə açır |
| --- | --- |
| `student.registry_view` | Ekran 09 bölməsi + CSV ixracı + hərəkət tarixçəsi |
| `student.movement` | 6 hərəkət növünün ƏMR yazısı (menyunu AÇMIR) |
| `student.assign_group` | Ekran 08-də qrupa təyinat + yeni qrup yaratma (menyunu AÇMIR) |

**Niyə `people.*`-dan ayrı prefiks:** `people.*` KATALOQ səthidir (dekan, kafedra müdiri,
koordinator da daşıyır), `student.*` isə RƏSMİ REYESTR + ƏMR səthidir. Eyni prefiksdə
olsaydılar, kataloq baxışı verilən hər rol avtomatik XARİC ETMƏ əmri yaza bilərdi.

**İKİQAT QAPI:** əmr yazmaq üçün həm `student.movement`, həm də `people.manage_academic`
tələb olunur — birincisi səlahiyyət, ikincisi mexanizmə (`registrar.transfer`) çıxışdır.

### 1.3 Paylanma

| Rol | `registry_view` | `movement` | `assign_group` | `user.import` |
| --- | --- | --- | --- | --- |
| `student_services` | ✔ | ✔ | ✔ | ✔ |
| `ikt_rehber` (RİM) | ✔ | ✔ | ✔ | ✔ (mövcud) |
| `dean` | ✔ | — | — | — |
| `program_coordinator` | ✔ (scope) | — | — | — |
| `vice_rector` | ✔ | — | — | — |
| `rector` | `*` | `*` | `*` | `*` |
| `teacher` / `student` | — | — | — | — |

> **Sapma (sənədləşdirilir):** plan §3-də «xaric etmə üçün ayrıca `people.expel` → dean +
> teaching_office_head» yazılıb. Tapşırığın icazə siyahısında `people.expel` YOXDUR, ona
> görə **xaric etmə `student.movement`-in içindədir** və state maşını onu ayrıca qayda
> kimi saxlayır. Sahib istəsə `RULES["expulsion"]`-a ayrıca açar qapısı bir sətirlə əlavə olunur.

### 1.4 Migration

`apps/organizations/migrations/0039_seed_student_services_role.py` (0038-dən sonra; Mərhələ 2
agenti sonradan 0040/0041-i məhz bunun üstünə zəncirləyib — tək leaf).

Üç iş: (1) hər `org_type="university"` təşkilatda rolu idempotent yaradır; (2) mövcud
rollara `student.*` açarlarını `STUDENT_SERVICES_GRANTS` xəritəsindən paylayır; (3)
**Müraciətlər kataloqunda `telebe` şöbəsinin `handler_role_names` siyahısına
`student_services`-i ƏLAVƏ edir** (`hr` FALLBACK kimi qalır — mövcud tenantda növbə bir
anda sahibsiz qalmamalıdır; `seed_units` mövcud sətri qəsdən yenidən yazmır).
`apps/applications/constants.py::DEFAULT_UNIT_SEED` də `["student_services", "hr"]`-a keçdi
(yeni tenant seed-i ilə köhnə tenant migrasiyası sürüşə bilmir). Geri dönüş yalnız bu
migrasiyanın əlavə etdiyini çıxarır.

---

## 2. Model dəyişiklikləri

`apps/registrar/migrations/0066_student_movement_and_admission_fields.py` +
`0067_rls_student_movement.py`.

### 2.1 `StudentMovement` — append-only əmr jurnalı

`apps/registrar/models/movement.py`. Sahələr: `kind` (6 növ), `order_number`, `order_date`,
`reason`, `document` (opsional, 10 MB, pdf/jpg/png/webp), `from_group|to_group`,
`from_program|to_program`, `from_status|to_status`, **`from_label`/`to_label` (dondurulmuş
mətn)**, `effective_until`, `actor` + `actor_name` (dondurulmuş).

* **APPEND-ONLY iki qatda:** `ImmutableCorrectionEvidence` (tətbiq qatı) + PG trigger
  `student_movement_no_update` / `student_movement_no_delete` (0067). Klonda hər ikisi
  canlı yoxlanıldı — xam SQL UPDATE və DELETE bloklandı.
* **RLS + FORCE RLS** (`rls_tenant_isolation`) — klonda `relrowsecurity=t`, `relforcerowsecurity=t`.
* Etiketlər `core/ui/status_catalog.py::STUDENT_MOVEMENT`-dən gəlir (enum TƏKRAR yazılmır).
* String-ref FK (`"organizations.OrgUnit"`) — `module_deps` gate-i yaşıl.

> ⚠️ **`%` TƏLƏSİ (koordinator bildirişi ilə düzəldildi):** `0067`-də plpgsql
> `RAISE EXCEPTION '... % qadağandır'` psycopg-nin parametr interpolyasiyasına düşürdü və
> **hər test bazasının qurulmasını** çökdürürdü. Düzəliş: `schema_editor.execute(SQL, params=None)`
> (`apps/workload/migrations/0002_rls_workload.py` ilə eyni naxış). Düzəlişdən sonra
> baza qurulması və 447 test yaşıldır.

### 2.2 `StudentAcademicRecord` — qəbul atributları

`apps/registrar/models/admission_meta.py` (abstrakt `AdmissionRecordFields`; `academic.py`
ölçü büdcəsinə görə ayrı fayl): `atis_id`, `admission_score`, `admission_exam_type`,
`education_form` (əyani/qiyabi/distant), `funding_type` (dövlət sifarişi/ödənişli).

Niyə profildə deyil, QEYDDƏ: bunlar şəxsin deyil, KONKRET İXTİSASA QƏBULUNUN atributlarıdır
(ikinci ali təhsil başqa balla və başqa formada ola bilər). Ekran 09-un «Forma» və «Təhsil
haqqı» sütunları buradan oxunur; `Program.education_form` isə İXTİSASIN default formasıdır.

Yeni sahələr NULL/default dəyərlidir → köçürülmüş 5 213 hesab üçün **data itkisi YOXDUR**.

`core/ui/status_catalog.py`-a **yeni ailə** `student_status` əlavə olundu (Aktiv / Akademik
məzuniyyət / Xaric edilib / Məzun) — reyestr sətrinin badge-i. Prototipdəki «Təhsil haqqı
borcu» statusu QƏSDƏN daxil deyil: o, maliyyə modulundan törəyir, akademik status deyil.

---

## 3. Ekran 08 — `student-admission` «Tələbə qəbulu»

**Backend TƏKRAR YAZILMADI.** Mövcud `apps/accounts/services/intake/` maşını (şablon,
oxuma, quru icra, tətbiq, audit, 26 test) olduğu kimi qaldı; üstünə ATİS qatı əlavə olundu.

### 3.1 ATİS sütunları (hamısı OPSİONAL)

`intake/spec.py`-a 6 sütun: `atis_id`, `program_code` (rəsmi şifr), `admission_score`,
`exam_type`, `education_form`, `funding` + tez-tez rast gəlinən başlıq sinonimləri.
Köhnə 16 sütunlu fayl **əvvəlki kimi işləyir** (başlıq-adına-görə xəritələmə).

`parsing.py`-da tək qayda dəyişdi: **«qrup» məcburiyyəti «qrup VƏ YA ixtisas kodu»**
oldu — ATİS ixracında qrup sütunu olmur, qrup məhz bu addımda doğulur.

### 3.2 Hədəf həlli və qrupun avtomatik təklifi

`intake/admission.py` (yeni, `validate.py` 490/600 olduğu üçün ayrı):

* `Program` rəsmi şifrlə tapılır (`core.program_codes.program_code_search_q` — cari NK 503
  və köhnə nəsil şifr); tapılmasa sətir **dizaynın hərfi mesajı** ilə bloklanır:
  «İxtisas kodu universitetdə tapılmadı» (`intake_row` status ailəsi).
* Qrup **avtomatik təklif olunur**: ixtisasın altındakı qruplardan dil sektoru uyğun,
  BOŞ YERİ ÇATAN birincisi. Fayl daxilində sayğac saxlanılır — 300 sətir bir qrupa yığılmır.
* Bal / imtahan növü / forma / maliyyələşmə oxunur; tanınmayan dəyər **bloklamır**,
  xəbərdarlıq yazılır və default tətbiq olunur (AZ hərfləri ASCII-yə foldlanır:
  «dövlət sifarişi» = «Dovlet sifarisi»).
* **Bloklayan xətalı sətir qrupa təyin edilə bilmir** (handoff §5/08) — UI həmin xanada
  seçici əvəzinə «—» göstərir.
* Operator təklifi ön baxışda dəyişə bilər: seçim `group_<sətir>` sahəsi ilə **faylla
  BİRLİKDƏ** göndərilir (serverdə state saxlanılmır → «gördüyün nəticə = alacağın nəticə»).

Qrup yaratma ayrıca endpoint-dədir (`student.assign_group`) — `apps/accounts/services/student_groups.py`
(tutum/doluluq/təklif/yaratma; **`accounts`-da yaşayır**, çünki qrup `organizations.OrgUnit`,
doluluq isə `registrar` sətirlərindən sayılır və iki modul bir-birini import etməməlidir).
Mərhələ 2-nin qrup reyestri servisi hazır olanda funksiya oraya köçürülüb burada fasadla
əvəz oluna bilər — imza qəsdən sadədir.

### 3.3 UI

`_student_admission.html`: `ems_ui` stepper (4 addım, `intake_steps` kataloqundan),
KPI zolağı (Cəmi sətir · Yoxlamadan keçdi · Bloklayan xəta · Xəbərdarlıq — dəyərləri quru
icradan sonra JS yeniləyir), 3 panel, genişləndirilmiş nəticə cədvəli (ixtisas, bal,
təhsil haqqı, forma/dil, **qrup seçicisi**), «Yeni qrup yarat» form-dialoqu.

**TƏK JS faylı:** `student_intake.js` genişləndirildi (`data-six-atis="1"` olanda ATİS
sətri render edir) — ikinci fayl yazsaydıq «Tətbiq et» məntiqi iki yerdə saxlanılardı.
Köhnə `student-intake` bölməsi **olduğu kimi işləyir** (link, sidebar girişi, 26 test).

---

## 4. Ekran 09 — `student-registry` «Tələbə reyestri və hərəkəti»

### 4.1 Oxu

`apps/accounts/services/people/registry.py`. Sətir = BİR AKADEMİK QEYD (`StudentAcademicRecord`),
`students.py`-dakı `User` bazalı kataloqdan **qəsdən fərqlidir**: iki ixtisasa yazılmış tələbə
kataloqda bir, reyestrdə iki sətirdir və əmr də konkret qeydə yazılır.

Təkrar istifadə (dublikat sorğu YOXDUR): scope → `movements.registry_records_qs`;
axtarış Q → `people.filters.search_q`; struktur adları → `people.rows.resolve_unit_ancestors`
(tək toplu sorğu, N+1 yox); ixtisas şifri → `core.program_codes`; kurs/status etiketi →
`people.academic`.

Server tərəfli filtr (axtarış / fakültə / ixtisas / qrup / qəbul ili / dil bölməsi / forma /
təhsil haqqı / status), sıralama (`aria-sort`, allowlist) və səhifələmə (`partials/_pagination.html`).

KPI: Cəmi tələbə · Əyani · Qiyabi · Xüsusi statuslu · Dövlət sifarişi — **hamısı hesablanır,
heç biri saxlanılmır** (§8/13).

### 4.2 Hərəkət state maşını

`apps/registrar/movements.py` (domen) + `apps/accounts/services/people/movements.py` (aktor).

```
enrolled ──group_transfer────> enrolled        (yeni qrup MƏCBURİ, tutum yoxlanılır)
enrolled ──program_transfer──> enrolled        (yeni ixtisas + həmin ilin planı MƏCBURİ)
enrolled ──form_change───────> enrolled        (yeni forma MƏCBURİ, fərqli olmalıdır)
enrolled ──academic_leave────> academic_leave  (bitmə tarixi MƏCBURİ)
enrolled | academic_leave ──expulsion──> expelled
academic_leave | expelled ──reinstatement──> enrolled  (qrup MƏCBURİ)
```

Hər əmr: **nömrə + tarix + səbəb (≥20 simvol) + opsional sənəd**; qanunsuz keçid 409,
qısa səbəb 400, dolu qrup 409. Mexanizm təkrar yaradılmır — qrup dəyişikliyi
`registrar.transfer.transfer_student_group` (iki fazalı sübut + `Enrollment.superseded_by`),
status isə `registrar.status` state-machine-i. **Sətir ƏVVƏLCƏ deyil, SONRA yazılır** və
hər ikisi eyni atomik blokdadır: uğursuz əməldən sonra tarixçədə «olmuş» əmr qalmır.

Yan təsirlər: `core.audit.log_action` (resource `accounts.people.movement`, JSONField-ə
YALNIZ `str()` dəyərlər — lazy-proxy tranzaksiya zəhəri təkrarlanmasın deyə) +
tələbəyə və proqram koordinatoru/dekana bildiriş (best-effort, domen əməlini bloklamır).

### 4.3 UI

`_student_registry.html`: content header + CSV ixracı, KPI (5), filtr paneli (9 sahə),
`_data_table.html` (sticky + zebra + `aria-sort`), pager, **çekmecə** (kart + hərəkət
timeline-ı, JSON-la doldurulur — 25 kartı əvvəlcədən render etmirik), **səbəb dialoqu**
(6 radio kart + şərti hədəf sahələri + sənəd + ≥20 simvol sayğacı).

Hansı hədəf sahəsinin məcburi olduğu **serverdən** gəlir (`movement_kinds()` → `RULES`,
`json_script`) — state maşını kliyentdə təkrarlanmır.

### 4.4 Bilərəkdən edilməyənlər

* **GPA və «borc, fənn» sütunları siyahıda YOXDUR** — hər sətir üçün ayrıca transkript
  aqreqatı tələb olunur (25 sətir = 25 transkript), §8/13 isə denormalizasiyanı da qadağan
  edir. GPA **çekmecədə** (bir tələbə üçün) göstərilir. Dizayndakı «Riskdə olan» KPI-ı da
  bu səbəbdən yoxdur.
* **Əmr layihəsi / təsdiq zənciri** (prototipin «Layihə — göndərilməyib», «Dekanlıq
  təsdiqində» vəziyyətləri) qurulmadı: tapşırıq «əmr + səbəb + audit → status dəyişikliyi»
  müqaviləsini istəyir. Model buna hazırdır (yeni `state` sahəsi + servis qapısı).
* «6 hərəkət növü» kataloqdakı **README-nin siyahısıdır** (köçürmə ×3, məzuniyyət, bərpa,
  xaric). Tapşırıqda yan-yana çəkilən «kurs təkrarı / məzun» variantı seçilmədi —
  `core/ui/status_catalog.py::STUDENT_MOVEMENT` TƏK mənbədir və Mərhələ 0-da kilidlənib.

---

## 5. Testlər

`apps/accounts/tests/test_student_services_sections.py` — **46 test, hamısı yaşıl**:

* fraqment 200: `student_services`, RİM · **403**: müəllim, tələbə (2 bölmə × 2 rol);
  menyuda sızma yoxdur; dekan reyestri görür, ƏMR YAZA BİLMİR (403);
* əhatəsiz koordinator: `has_access=True`, `has_scope=False`, **0 sətir** + «əhatə yoxdur»
  boş vəziyyəti (§8/8 — bütün universitet DEYİL);
* köhnə `student-intake` açarı işləməyə davam edir;
* state maşını: köçürmə, məzuniyyət (+ müddət), xaric, bərpa, forma dəyişikliyi,
  ixtisas dəyişikliyi (plan yoxdursa 409), qanunsuz keçid 409, səbəb <20 → 400,
  əmr nömrəsi/tarixi məcburi, dolu qrup 409;
* **tarixçə append-only**: `save()` və `delete()` `ValidationError` atır;
* audit sətri (kind/order_number/reason) + tələbəyə bildiriş + kart endpoint-i;
* sənəd yüklənməsi + icazə-qapılı endirmə (müəllim 404);
* reyestr sətri/KPI/filtr/sıralama; **CSV ixracı** (müəllim/tələbə 403, filtrə tabe);
* ATİS: kod ilə hədəf həlli + avtomatik qrup təklifi, naməlum kod bloklayır və qrup
  təyin edilmir, fayl daxilində FİN təkrarı, əl ilə seçimin təklifi üstələməsi,
  tətbiqdə qəbul sahələrinin SAR-a yazılması, qrup yaratmanın icazə qapısı və dublikat adı;
* müqavilə: icazə kataloqu + etiketlər, rol şablonu, alias muafiyyəti, org-admin səthləri,
  `login_blocked_access_states` **dəyişməyib**, `telebe` şöbəsinin emalçı rolu,
  bölmə reyestrinin 4 yerdə uzlaşması, hərəkət növlərinin kataloqla eyniliyi.

**Reqressiya:** `test_student_intake` (26) · `test_sidebar_role_matrix` (13) ·
`apps/organizations/tests` · `test_account_archive` (16) · `test_ems_ui_components` (39) ·
`registrar/test_transfer` (11) → **447 keçdi, 0 uğursuz** (1 dəq 40 san).
Əlavə: `test_cabinet_routing`, `test_section_registry_consistency`,
`test_teaching_office_sections`, `apps/applications/tests` → **234 keçdi**.

**Qapılar:** `black` ✅ · `isort` ✅ · `flake8` ✅ · `check_module_size --check` ✅ ·
`module_deps --check` ✅ (yeni dövr yoxdur) · `check_worker_atomic_coverage --check` ✅ ·
`makemigrations --check` ✅ («No changes detected») · `manage.py check` ✅.

---

## 6. Canlı yoxlama (QA klonu, `http://127.0.0.1:8100`)

Klon miqrasiya olundu (0039 + 0066 + 0067 tətbiq edildi; RLS + 2 trigger canlı).
Test hesabı **yalnız klonda**: `qa.student_services` / `QaAudit2026!` (rol `student_services`, 14 açar).

Fikstür (QA-DS3 prefiksli, sonda silindi): ixtisas + 2 qrup (tutum 2 və 25) + `Program`
(rəsmi şifr `9990001`) + 2026 kurikulumu. **Köçürülmüş sətirlərə TOXUNULMADI.**

```
BÖLMƏ FRAQMENTLƏRİ  student-admission 200 · student-registry 200
QURU İCRA           200 · {total 3, create 2, error 1}
                    row2/3 → qrup AVTOMATİK «QA-DS3 102», bal 543.5/498.2,
                             forma full_time, haqq state/paid, 2 variant
                    row4  → fin_invalid (bloklayıcı; qrup təyin edilmir)
                    DB-də QA FİN sayı: 0   ← quru icra HEÇ NƏ yazmadı
TƏTBİQ              200 · {created 2} · 2 birdəfəlik parol
                    SAR: bal 543.50/498.20 · forma full_time · haqq state/paid · atis ATIS-QA-1/2
REYESTR             fraqment 200 · filtr `sr_group` işlədi · KPI 2/2/0/1/1
HƏRƏKƏT 1           200 · qrup köçürməsi (QA-DS3 102 → QA-DS3 101), əmr QA-DS3/R-101
HƏRƏKƏT 2           200 · akademik məzuniyyət (2027-09-01), status → academic_leave, is_active=False
SƏBƏB <20           400 reason_too_short
QANUNSUZ KEÇİD      409 illegal_transition (məzuniyyətdən təkrar məzuniyyət)
KART                200 · bal 543.50 · ATİS-QA-1 · 2 hərəkət
CSV                 200 · text/csv · sətir: «… QA-DS3 101, I, 2026, Əyani, Dövlət sifarişi, Akademik məzuniyyət»
MÜƏLLİM             fraqment 403 · ixrac 403
TƏLƏBƏ KABİNETİ     yeni qrup görünür (QA-DS3 101); `my-subjects` 302 — ilk-giriş
                    parol dəyişmə tələbi (idxal hesabı, gözlənilən davranış)
BİLDİRİŞ            tələbəyə 2 bildiriş
APPEND-ONLY         xam SQL UPDATE bloklandı · DELETE bloklandı (PG trigger)
```

### Brauzer (`qa.student_services`)

* **1280×1500:** sidebar-da «TƏLƏBƏ XİDMƏTLƏRİ» qrupu (Tələbə qəbulu + Tələbə reyestri);
  ekran 08-də 4 addımlı stepper (1-ci «cari», qalanlar «gözləyir»), 4 KPI (bloklayan xəta
  qırmızı, xəbərdarlıq sarı tonda), 2 panel; ekran 09-da 5 KPI, 9 sahəli filtr paneli
  («Nəticə: 2 sətir»), sticky cədvəl, status badge-ləri (Aktiv yaşıl, Akademik məzuniyyət
  sarı), sətir əməlləri. **Çekmecə:** kart faktları + 2 hərəkətli timeline (nədən → nəyə +
  səbəb). **Dialoq:** hədəf adı zolağı, 6 radio kart, əmr nömrəsi/tarixi, şərti «Yeni qrup»
  seçicisi (51 variant yükləndi), sənəd, səbəb sayğacı `0 / 20` və **disabled** «Əmri yaz».
  Növ dəyişəndə sahələr serverdən gələn qaydaya görə açılıb-bağlandı (məzuniyyət → qrup
  gizləndi, «bitmə tarixi» göründü).
* **375×812:** `document.scrollWidth == clientWidth == 375` (üfüqi sürüşmə **0**),
  `h1` sayı **1**, KPI 1 sütun, cədvəl ÖZ konteynerində sürüşür.
* **Konsol/şəbəkə:** bölmə səhifələrində `performance.getEntriesByType('resource')` üzrə
  **≥400 statuslu sorğu 0**. Konsol tarixçəsindəki 2 xəta (405, 404) çıxış üçün əl ilə
  etdiyim `GET /accounts/logout/` və giriş səhifəsinin favicon-udur — bölmələrdən deyil.

> ⚠️ Brauzer paneli Mərhələ 2 agentinin `qa.teaching_office_head` sessiyası ilə açıq idi;
> öz yoxlamam üçün çıxış edib `qa.student_services` ilə girdim (sessiya bərpa oluna bilər).

**Təmizlik:** `QA-DS3*` obyektləri klondan silindi — 0 SAR, 0 hesab, 0 hərəkət, 0 qrup/
ixtisas/proqram/kurikulum. Hərəkət və köçürmə sübutu sətirlərinin silinməsi üçün trigger
**yalnız həmin əməliyyat müddətində** söndürülüb dərhal geri qaytarıldı (miqrasiyanın
sənədləşdirdiyi retention yolu). `audit_auditlog` sətirləri QƏSDƏN saxlanıldı (append-only).
`qa.student_services` hesabı sonrakı mərhələlər üçün klonda QALDI.

---

## 7. i18n

`.po` / `.mo` fayllarına **TOXUNULMADI** (paralel i18n agenti doldurur). Yeni mətnlər
`pgettext` / `{% trans … context %}` ilədir. **134 msgid, 8 kontekst** —
tam siyahı: `docs/audits/2026-09-02/DESIGN_STAGE3_MSGIDS.txt`.

| Kontekst | Say |
| --- | --- |
| `accounts.student_registry` | 62 |
| `accounts.student_admission` | 39 |
| `student_intake` | 19 (ATİS sütunları + validasiya mesajları) |
| `ui.status` | 4 (`student_status` ailəsi) |
| `profile.sidebar` | 3 |
| `organizations.permission.label` | 3 |
| `registrar.funding_type` | 2 |
| `registrar.model.student_movement.meta` | 2 |

`scripts/check_i18n_catalogs.py` hazırda **QIRMIZIDIR** (`django/source_missing` 233) —
sayğac PAYLAŞILANDIR: içində Mərhələ 2-nin `accounts.curriculum` / `organizations.semester_opening`
kontekstləri də var. Bu işin payı yuxarıdakı 134 msgid-dir.

---

## 8. Dəyişən / yaranan fayllar

**Yeni:**
`apps/organizations/default_roles_student_services.py` · `apps/organizations/permissions_stage3.py` ·
`apps/organizations/migrations/0039_seed_student_services_role.py` ·
`apps/registrar/models/{movement,admission_meta}.py` · `apps/registrar/movements.py` ·
`apps/registrar/migrations/{0066_student_movement_and_admission_fields,0067_rls_student_movement}.py` ·
`apps/accounts/services/student_groups.py` ·
`apps/accounts/services/people/{movements,registry}.py` ·
`apps/accounts/services/intake/admission.py` ·
`apps/accounts/views/student_registry.py` ·
`apps/accounts/views/profile/_sections/{student_registry,student_admission}.py` ·
`apps/accounts/templates/accounts/profile/sections/{_student_registry,_student_admission}.html` ·
`…/sections/student_services/{_registry_actions,_registry_header_actions,_registry_drawer,_movement_fields,_new_group_fields}.html` ·
`…/profile/sidebar/_student_services_group.html` ·
`apps/accounts/static/accounts/css/profile/sections/student_services.css` ·
`apps/accounts/static/accounts/js/profile/student_registry.js` ·
`apps/accounts/tests/test_student_services_sections.py`

**Dəyişən:**
`apps/organizations/{permissions,default_roles_university}.py` · `apps/applications/constants.py` ·
`apps/registrar/models/{__init__,academic}.py` · `core/ui/status_catalog.py` ·
`apps/accounts/services/intake/{spec,parsing,validate,apply}.py` ·
`apps/accounts/services/people/permissions.py` · `apps/accounts/views/student_intake.py` ·
`apps/accounts/views/_helpers/rbac_sections.py` · `apps/accounts/views/profile/sections_api.py` ·
`apps/accounts/views/profile/_sections/labels.py` ·
`apps/accounts/views/profile/context_builder/{_teaching_office,_stage2,_stage4}.py` ·
`apps/accounts/urls.py` · `apps/accounts/views/__init__.py` ·
`apps/accounts/templates/accounts/profile.html` · `…/profile/{_sidebar,_section_dispatch,_section_assets}.html` ·
`apps/accounts/static/accounts/js/profile/student_intake.js` · `templates/partials/ems_ui/_kpi_tile.html`

---

## 9. Təxirə salınanlar / sahib qərarı gözləyənlər

1. **ATİS konnektoru** — rəsmi API/format müqaviləsi yoxdur; hazırda XLSX/CSV ixracının
   başlıqları qəbul olunur (plan §7/1 ilə eyni mövqe).
2. **Əmr layihəsi + təsdiq zənciri** (prototipin 4 vəziyyəti) — bax §4.4.
3. **`people.expel` ayrıca açarı** — bax §1.3.
4. **GPA/borc sütunları siyahıda** — performans səbəbi ilə çekmecədə (§4.4). Sahib istəsə
   ayrıca materiallaşdırılmış göstərici lazımdır (bu, §8/13-ə ziddir).
5. **Sektor filtri JSON sahəsi üzərindədir** (`OrgUnit.settings["language_sector"]`) —
   indeks yoxdur, uyğun qrup id-ləri bir sorğu ilə Python-da seçilir. Sektor STRUKTUR
   sahəyə çevriləndə filtr bir sətirlə DB-yə keçir.
6. **Qrup adı şablonu** — «yeni qrup» dialoqunda yalnız TƏKLİF verilir (`<il> <ixtisas kodu>`);
   universitetin öz adlandırma qaydası operator tərəfindən yazılır.
7. **Doğum tarixi məcburiliyi** — mövcud `validate.py` boş doğum tarixini XƏTA sayır
   (bu mərhələdə DƏYİŞDİRİLMƏDİ). ATİS ixracında sütun yoxdursa bütün sətirlər bloklanır;
   sahib «boş qala bilər» desə, bir sətirlik dəyişiklikdir.
