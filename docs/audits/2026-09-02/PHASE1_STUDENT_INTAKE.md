# PHASE 1 §4 — Tələbə idxalı (student intake) · boşluğun bağlanması

**Tarix:** 2026-09-02 · **Branch:** `audit/post-migration-qa-2026-09` · **Commit edilməyib** (sahibin qərarı gözlənilir)

## 1. Tapıntı və qərar

Auditin PHASE 1 §4 tapıntısı (`RECOVERED_SUMMARIES.md`): «tələbə şöbəsi siyahı yükləyir → qeydlər →
əlaqələr → hesablar → tələbə girə bilir» axınının işləyən **yeganə** yolu legacy köçürmə idi.

| Mövcud səth | Vəziyyət |
|---|---|
| `apps/accounts/management/commands/import_users_from_excel.py` | Var, amma `core/management/command_safety.py` (`MANAGEMENT_COMMAND_ENVIRONMENT` default `production`) onu prod-da **söndürür**. Sxemi rol-generikdir (`username, ad_soyad, rol, teskilat_slug, vahid…`), tələbəyə xas deyil: FİN, qrup, qəbul ili, akademik qeyd yoxdur. |
| RİM mərkəzi (`services/rim/`, `views/rim/`) | Yalnız **mövcud** hesabları idarə edir (axtar / parol / blok / soft-delete / bərpa / redaktə). Yaratma-idxal yoxdur. |
| `identity_access.stage_imported_account` | Staged + `AccountActivationEvidence` + PG SECURITY DEFINER keçidi — legacy cutover üçün qurulub, tələbə şöbəsinin gündəlik əməli üçün deyil. |

**Qərar.** Prod kill-switch **zəiflədilmədi** (komanda superadmin server aləti olaraq bağlı qalır).
Boşluq nəzarətli, icazəli və audit olunan **UI səthi** ilə örtüldü: profil kabinetində
`student-intake` bölməsi, kanonik açar **`user.import`**.

## 2. İcazə modeli

`user.import` — `apps/organizations/permissions.py` «users» kateqoriyasına əlavə olundu + AZ etiket
(«Tələbə idxalı (siyahıdan toplu hesab yaratmaq)»).

QƏSDƏN `user.edit` / `user.credentials`-dan **ayrıdır**: RİM mövcud hesabı idarə edir, idxal isə YENİ
kimlik gətirir. «Parolu sıfırla» səlahiyyəti heç bir rola avtomatik «minlərlə hesab yarat» hüququ
verməməlidir (əsasnamə 5.5 səlahiyyət ayrılığı). `user.*` wildcard-ı rol təriflərində işlədilmir.

* Default rollar: `ikt_rehber` (RİM) və `hr` (`default_roles_university.py`); `rector` / `vice_rector` /
  sahib `*` ilə onsuz da əhatələnir. `teacher` / `student` / `exam_center`-də **yoxdur** (testlə qorunur).
* Mövcud tenantlar: `apps/organizations/migrations/0034_seed_user_import_permission.py`
  (0033-dən asılı, idempotent, geri dönüşlü). QA klonunda tətbiq olundu — `ikt_rehber`/`hr` = `t`, `teacher` = `f`.
* Menyu görünürlüyü: `views/_helpers/rbac_sections.py` → `can_import_students`.
  Faktiki əməl `services/intake/policy.py`-da **fail-closed** yenidən yoxlanılır (aktiv təşkilat + AKTİV üzvlük).

## 3. Dizayn və axın

Servis paketi `apps/accounts/services/intake/` (hamısı < 600 sətir):

| Modul | Rolu |
|---|---|
| `policy.py` (77) | `PERM_IMPORT`, `can_import`, `require_import` — fail-closed qapı |
| `spec.py` (158) | 16 sütunun müqaviləsi + `.xlsx` şablon (openpyxl var; CSV geri düşməsi) |
| `parsing.py` (209) | Yüklənmiş faylın oxunması: 5 MB / 2000 sətir / `.xlsx`,`.xlsm`,`.csv` allow-list, başlıq-adına-görə xəritələmə (sütun sırası sərbəst), şablonun izah sətrinin atılması |
| `validate.py` (490) | **Quru icra** — heç nə yazmır; sətir → `RowPlan` (`create`/`skip`/`error` + xəbərdarlıqlar) |
| `apply.py` (279) | Planların icrası: sətir başına `transaction.atomic()` savepoint + audit |

Axın: **şablonu endir → doldur → yüklə → quru icra (ön baxış) → «Tətbiq et» → nəticə + parol CSV-si.**

Ön baxış və tətbiq **eyni plan qurucusundan** keçir → «gördüyün nəticə = alacağın nəticə».
Server heç bir faylı, sətri və ya parolu **saxlamır**: «Tətbiq et» eyni faylı yenidən göndərir
(sessiyada/kəşdə PII və parol qalmır).

### Validasiya qaydaları

| Hal | Nəticə |
|---|---|
| FİN boş / format səhv | `error` (`fin_required`, `fin_invalid`) |
| Ad və ya soyad boş | `error` (`name_required`) |
| FİN faylda təkrar | `error` (`fin_duplicate_in_file`) |
| FİN bazada var | `skip` (`fin_exists`) — **üzərinə yazılmır** |
| Tələbə kodu bazada var | `skip` (`student_code_exists`) |
| Qrup tapılmadı / ikimənalı | `error` (`group_unknown`, `group_ambiguous`) |
| Fakültə/ixtisas tapılmadı və ya qrupun əcdadı deyil | `error` |
| Qrupun ixtisasında `Program` yoxdur | `error` (`program_missing`) |
| Doğum tarixi / qəbul ili pozuq | `error` |
| Kurikulum (proqram + qəbul ili) yoxdur | `warning` → tətbiqdə boş kurikulum yaradılır (legacy `_bind_curriculum` naxışı) |
| E-poçt boş / toqquşur | `warning` → `intake.<fin>@placeholder.invalid` |
| Cins tanınmadı, təhsil səviyyəsi proqramla uyğun deyil | `warning` (sətir keçir) |

### Yaradılan zəncir (sətir başına)

`User` (aktiv, təsadüfi parol) → `UserProfile` (FİN, ata adı, cins, doğum tarixi, telefon, tələbə kodu →
`institutional_identifier`, `access_state=ACTIVE`, **`password_change_required=True`**,
**`email_verified=False`**) → `Membership` (`student`, aktiv, primary) → `StudentAcademicRecord`
(qrup + proqram + kurikulum + qəbul ili, `enrolled`).

**İstifadəçi adı siyasəti:** `st.<tələbə kodu>`, kod yoxdursa `st.fin.<fin>`; toqquşmada `.2`, `.3`…
(köçürülmüş `myedu.student.<id>` ilə eyni məntiq — mənbə addan görünür, saf rəqəmli username yaranmır).

**Parol modeli:** mövcud `provision_student_credentials` çap-parol modeli ilə eynidir. Parol **audit-ə
yazılmır**, DB-də açıq saxlanılmır; yalnız tətbiq cavabında qayıdır və operator onu brauzerdə CSV kimi
endirir (`username,password,full_name,fin,group`). Parol siyasəti (`generate_initial_password`) artıq
**tək mənbədədir** — `import_users_from_excel` komandası da onu çağırır.

**Audit:** hər hesab üçün `AuditAction.CREATE` + `reason="student_intake_created"` (username, FİN, qrup,
proqram, qəbul ili, placeholder bayrağı — parol YOX), faylın sonunda bir yekun sətri
(`reason="student_intake_batch"`, created/skipped/failed/total).

## 4. Toxunulmayanlar (qəsdən)

* `core/management/command_safety.py` — **dəyişmədi**; komanda prod-da bağlı qalır (test ilə qorunur).
* `login_blocked_access_states()` = `{STAGED, ARCHIVED}` — **dəyişmədi** (test ilə qorunur).
* `alumni` / arxiv qaydaları: idxal yalnız YENİ kimlik yaradır, mövcud hesabın `access_state`-inə heç
  vaxt yazmır.
* `identity_access` / `identity_archive` staged-activation axını — toxunulmadı.

## 5. Fayllar

**Yeni**
```
apps/accounts/services/intake/{__init__,policy,spec,parsing,validate,apply}.py
apps/accounts/views/student_intake.py                      (JSON/fayl endpoint-ləri)
apps/accounts/views/profile/_sections/student_intake.py    (bölmə context-i)
apps/accounts/templates/accounts/profile/sections/_student_intake.html
apps/accounts/static/accounts/css/profile/student_intake.css
apps/accounts/static/accounts/js/profile/student_intake.js
apps/accounts/tests/test_student_intake.py
apps/organizations/migrations/0034_seed_user_import_permission.py
scripts/i18n_fill_student_intake.py
```

**Dəyişdirilən**
```
apps/organizations/permissions.py                (user.import + etiket)
apps/organizations/default_roles_university.py   (ikt_rehber, hr)
apps/accounts/views/_helpers/rbac_sections.py    (can_import_students qapısı)
apps/accounts/views/profile/sections_api.py      (SECTION_PARTIALS + AJAX_SAFE_SECTIONS)
apps/accounts/views/profile/_sections/labels.py  (partial + sidebar adı)
apps/accounts/views/profile/context_builder/_stage2,_stage3,_stage4.py
apps/accounts/templates/accounts/profile.html    (CSS/JS include, data-ajax-sections, dispatch)
apps/accounts/templates/accounts/profile/sidebar/_org_menu_group.html  (RİM mərkəzinin yanında)
apps/accounts/urls.py, apps/accounts/views/__init__.py
apps/accounts/management/commands/import_users_from_excel.py (parol siyasətini paylaşır)
locale/{az,en,ru,tr}/LC_MESSAGES/django.{po,mo}
```

**Frontend qaydaları:** inline CSS/JS **yoxdur** — xarici fayllar `profile.html`-dən yüklənir, dinamik
dəyərlər `data-*` atributları ilə ötürülür; JS `EMSDelegate` + `EMSCore.fetchJSON` ilə AJAX-safe-dir
(`[data-six-root]` yoxdursa heç nə etmir). Rənglər yalnız `--ems-*` tokenlərindən (light-only).

## 6. Testlər — `apps/accounts/tests/test_student_intake.py` (26/26 yaşıl)

| Sinif | Əhatə |
|---|---|
| `IntakePermissionGateTest` (6) | default rollarda açar; tələbə/müəllim 403 (şablon + preview + apply); RİM 200; bölmə `allowed_sections`-da yalnız idxalçılarda; AJAX fraqment qapısı; **deaktiv üzvlük → qapı bağlı** |
| `IntakeDryRunTest` (7) | plan qurulur, **DB-yə yazılmır**; FİN boş/format/ad-soyad; faylda təkrar FİN; bazada FİN → skip və mövcud hesab **dəyişmir**; naməlum qrup/ixtisas/proqramsız qrup; pozuq tarix və qəbul ili; e-poçt toqquşması → placeholder; dəstəklənməyən fayl → 400 |
| `IntakeApplyTest` (7) | tam zəncir (User+Profile+Membership+SAR sahə-sahə); username FİN-ə düşməsi; **username toqquşmasında `.2` suffiksi** (kənar hesab əzilmir); dublikat tələbə kodu skip; **qismən uğursuzluq yaxşı sətirləri saxlayır**; placeholder e-poçtun tətbiqi; audit sətirləri (2 create + 1 batch, parol yoxdur); çatmayan kurikulumun yaradılması |
| `IntakeLoginFlowTest` (2) | ilk-giriş tələbi (`password_change_required`, `email_verified=False`, bloklu vəziyyət deyil); **parol qoyulandan sonra portal girişi + `my-subjects` fraqmenti 200** |
| `IntakeSafetyContractTest` (2) | prod kill-switch hələ də `CommandError` atır; `login_blocked_access_states` dəyişməyib |

Regressiya: `test_permissions.py` + `test_cabinet_routing.py` + `test_rim_center.py` = **96/96 yaşıl**.

## 7. Canlı yoxlama — QA klonu (`emsarena_rehearsal_a0d170000901`)

Aktor `qa.ikt_rehber`, təşkilat `myedu-univ`, real qrup **709/5 Sbio** (ixtisas «Akvabioresurslar»,
proqram `MYEDU-89-M`). 3 sətirlik fayl (2 düzgün, 1 pozuq FİN).

```
ŞABLON      200 · application/vnd.openxmlformats-…spreadsheetml.sheet · 5562 bayt
QURU İCRA   200 · {total: 3, create: 2, skip: 0, error: 1}
            row2/3 create → st.qa-intake-001/002, intake.qa*@placeholder.invalid
            row4  error  → fin_invalid
            DB-də QA FİN sayı: 0   ← quru icra HEÇ NƏ yazmadı
TƏTBİQ      200 · {total: 3, created: 2, skip: 0, error: 1}
            st.qa-intake-001 | state active | pwd_req True | email_ver False
                             | rol student(aktiv) | SAR 709/5 Sbio · MYEDU-89-M · 2025
            credentials: 2 × 10 simvolluq birdəfəlik parol
GİRİŞ       parol klonda qoyuldu → login True
            my-subjects fraqmenti 200 (ok=True) · profil səhifəsi 200
AUDİT       created: 2 · batch: 1
```

**Təmizlik:** `st.qa-intake-*` hesabları (User + Profile + Membership + SAR) silindi — klonda 0 qalıq,
orfan SAR yoxdur, idxal yeni kurikulum yaratmadı (0 sətir). Audit sətirləri qaldı: `audit_auditlog`
append-only trigger-lidir (`emsarena_audit_log_no_delete`) — **qəsdən** silinmədi.

## 8. Gate-lər

| Gate | Nəticə |
|---|---|
| `black --check` / `isort --check-only` / `flake8` (22 fayl) | ✅ təmiz |
| `scripts/check_module_size.py --check` | ✅ mənim fayllarım (ən böyüyü `validate.py` 490). ⚠️ Dəstdə **başqa agentlərin** iki köhnə çatışmazlığı var: `apps/legacy_import/models.py` 604, `apps/registrar/models/grading.py` 602 |
| `scripts/module_deps.py --check` | ✅ yeni dövr yoxdur |
| `makemigrations --check` (sqlite) | ✅ «No changes detected» |
| `manage.py check` | ✅ 0 issue |
| pytest (postgres, `ems_imp_c9cd470d`) | ✅ 26/26 + 96/96 regressiya |

### i18n sayğacları (baseline **`--update` edilmədi**)

`scripts/i18n_fill_student_intake.py` → hər kataloqa **+99 giriş** (az/en/ru/tr), sonra
`compilemessages`. `scripts/check_i18n_catalogs.py` iki qalıq fərq göstərir:

1. **`django/tr: identity 270 → 287` (+17)** — bunun **7-si mənimdir** və leqitimdir: azərbaycanca ilə
   türkcədə eyni yazılan sözlər (`Ad`, `Soyad`, `Telefon`, `Sütun`, `Sütunlar`, `Ad Soyad`, `(boş)`).
   Süni fərq yaratmaq tərcüməni pisləşdirərdi. Qalan **10-u başqa agentlərin** eyni vaxtda etdiyi
   locale dəyişikliklərindəndir.
2. **`django: source_missing 3 → 4`** — sadalanan msgid-lər mənim deyil
   (`registrar.journal|Otaq`, `exams.final_center.permission|…`, iki PDF sətri) — paralel işləyən
   agentlərin kodundandır.

Qapı bu iki sayğaca görə qırmızıdır; baseline QƏSDƏN yenilənmədi (tapşırığın tələbi) — sahibin/CI-nin
qərarı gözlənilir.

## 9. Təxirə salınanlar (deferred)

* **`Kurs` və `Dil bölməsi` sütunları yalnız yoxlama üçündür** — heç bir modelə yazılmır. Kurs qəbul
  ilindən hesablanır; dil sektoru üçün `OrgUnit`-də struktur sahə yoxdur (qrupun adında kodlaşdırılır).
  Sahə əlavə olunanda idxal bir sətirlə bağlanır.
* **Müəllim/işçi idxalı** əhatədə deyil — bu səth yalnız `student` rolunu yaradır. Kadr idxalı üçün
  rol-generik komanda (prod-da bağlı) və ya ayrıca səth lazımdır.
* **Mövcud tələbənin yenilənməsi yoxdur** (upsert deyil): mövcud FİN həmişə `skip`. Kütləvi yeniləmə
  ayrıca, sənədli axın olmalıdır — akademik tarixçəni səssiz üzərinə yazma riski.
* **`AcademicPeriod`-a yazılış (Enrollment) yaradılmır** — idxal yalnız SAR-a qədər gedir; fənn
  yazılışı mövcud registrar axınındadır (kurikulum + açılış).
* **Fon icrası yoxdur**: 2000 sətir sinxron emal olunur. Daha böyük fayllar üçün Celery tapşırığı +
  irəliləyiş göstəricisi lazımdır.
* **Şablon `.xlsx`-də data-validation (dropdown) yoxdur** — cins/səviyyə üçün açılan siyahı sonrakı
  təkmilləşdirmədir.
* Bölmə **UI-da brauzerdə** yoxlanılmadı (canlı UI-QA agenti brauzer panelini tutur) — bütün sübut
  Django test client ilədir.
