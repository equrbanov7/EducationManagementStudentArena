# FAZA 4 — Dərs yükü (`apps/workload`) · F0 + F3 + F4

**Tarix:** 2026-09-02 · **Worktree:** `.claude/worktrees/agent-abbdb0f75634105ee`
(branch `worktree-agent-abbdb0f75634105ee`, baza `260112af`) · **Commit YOXDUR** — sahib əl ilə merge edir.
**Spesifikasiya:** `docs/workload/DERS_YUKU_SPEC.md` (§3 rollar, §5 data modeli, §6.3/§6.4 ekranlar,
§7.1 offering sinxronu, §8 normalar, §10 fazalar).

Bu keçid sahibin hədəf axınını qapadır:
**kafedra müdiri tapşırığı yaradır → sətirləri doldurur → müəllimlərə bölür → təsdiqləyir →
müəllim bildiriş alır və «Dərs yüküm»də görür → elektron jurnal açılışı hazır olur.**

---

## 1. Nə hazırdır (F0 + F3 + F4)

| Faza | Əhatə | Vəziyyət |
|---|---|---|
| **F0** | app skeleti, 5 model + miqrasiyalar, RLS + saat trigger-i + append-only trigger, icazə kataloqu, rol backfill-i | ✅ |
| **F3** | kafedra bölgüsü: sətir CRUD, fəaliyyət-fəaliyyət saat balansı, müəllim hovuzu, vakant, «Bölgünü təsdiqlə», amendment axını | ✅ |
| **F4** | müəllimin «Dərs yüküm» bölməsi (il/fəsil, stat-kartlar, cədvəl, XLSX ixracı, jurnal keçidi) | ✅ |
| **F1** (tədris şöbəsi) | tapşırıq redaktoru, Excel idxal sehrbazı, göndərmə | ⛔ təxirə salınıb |
| **F2** (dekanlıq) | `TaskFacultySlice`, `TaskRowReview`, koordinator vizası, dekan təsdiqi | ⛔ təxirə salınıb |
| **F5** | hesabat paketi, rollover, deadline/eskalasiya, plan-fakt | ⛔ təxirə salınıb (offering sinxronu isə F3-ə çəkildi) |

**İrəli uyğunluq:** `TeachingTask.status` kataloqu SPESİFİKASİYANIN TAM SİYAHISIDIR
(`draft/submitted/returned/pending_final_approval/approved/distributing/distributed/amended/cancelled`),
`revision`, `submitted_by`, `submitted_at` sahələri də indidən var — F1/F2 gələndə
sahə miqrasiyası lazım deyil, yalnız keçid qaydaları əlavə olunur.

---

## 2. Data modeli (`apps/workload/models/`)

Hamısı `UUIDModel + TimeStampedModel`, məcburi `organization` FK, cross-app FK-lər
**string label** ilə (`"organizations.OrgUnit"`, `"organizations.AcademicPeriod"`,
`"registrar.Subject"`) — modul qrafında yeni kənar yaranmır.

| Model | Cədvəl | Açar məqamlar |
|---|---|---|
| `TeachingTask` | `workload_teachingtask` | org + `academic_year` («2026/2027») + `chair` (OrgUnit chair/department); status, revision, `created_by`/`submitted_by`/`distributed_by`; **UNIQUE (organization, academic_year, chair)** |
| `TeachingTaskRow` | `workload_teachingtaskrow` | spec §5.2-nin BÜTÜN sahələri: season, `period` FK (**`organizations.AcademicPeriod`** — registrar-da deyil, yoxlandı), subject FK + `subject_text`, `row_kind`, specialty/faculty FK + mətn fallback, `groups` M2M + `groups_text`, `education_form`, `degree_level`, student/union/subgroup sayları, lecture/seminar/lab plan+total, consult/exam/thesis/postgrad/practice saatları, `total_hours`, `credits` + `credits_value`, `review_status`, `order` |
| `TeacherAssignment` | `workload_teacherassignment` | row + activity + hours (>0 CHECK); `teacher` NULL = **Vakant**; `groups_note`, `is_hourly_paid`, `assigned_by` |
| `TeacherWorkloadProfile` | `workload_teacherworkloadprofile` | org+teacher+year UNIQUE; `position`, `staff_fraction`, `annual_norm_hours` (default 500 = NK №215), `is_external` |
| `WorkloadAmendment` | `workload_workloadamendment` | append-only; `target_kind`/`target_id`, `reason`+`note` (məcburi), old/new JSON snapshot, opsional PDF (`FileUploadValidator`, 10 MB) |

**`TaskFacultySlice` və `TaskRowReview` QƏSDƏN yaradılmayıb** — onlar F2-nin öz dövriyyəsidir
və indi yaradılsa boş cədvəl + yanlış «hazırdır» siqnalı olardı.

### Miqrasiyalar
- `0001_initial` — 5 model, indekslər, unikallıqlar.
- `0002_rls_workload` — **üç qat DB qoruması** (yalnız PostgreSQL; sqlite-da no-op):
  1. beş cədvəlin hamısında `ENABLE + FORCE ROW LEVEL SECURITY` + `rls_tenant_isolation`
     siyasəti (bypass GUC və ya `organization_id = app.current_org_id`);
  2. `workload_assignment_balance` trigger-i — `Σ hours ≤` sətrin həmin fəaliyyət cəmi
     (servisi yan keçən admin/shell/idxal yolları da bağlıdır);
  3. `workload_amendment_append_only` trigger-i — UPDATE/DELETE qadağan
     (yeganə istisna: `made_by` istifadəçisi silinəndə FK-nın SET NULL yazısı).
- `0003_seed_permissions` — **mövcud tenantlarda** `workload.*` backfill-i.
  ⚠️ Miqrasiya QƏSDƏN `apps/workload`-dadır (organizations nömrələri paralel axınlar
  tərəfindən tutulub); asılılıq `("organizations", "0032_seed_alumni_role")`.
  `apps/notifications` miqrasiyalarına TOXUNULMAYIB — bildiriş mövcud
  `NotificationType.ASSIGNMENT` + `metadata={"event": "workload_assigned"}` ilə gedir.

---

## 3. İcazələr

Yeni kateqoriya `apps/organizations/permissions.py` → `PERMISSION_CATEGORIES["workload"]`
+ `PERMISSION_CATEGORY_LABELS["workload"] = "Dərs yükü"` + hər açar üçün AZ etiket
(`PERMISSION_LABELS`, `pgettext_lazy`).

```
workload.view        workload.manage      workload.submit    (F1)
workload.review (F2) workload.approve (F2) workload.distribute  workload.report
```

`submit`/`review`/`approve` kataloqda var, amma **heç bir default rola verilmir** —
F1/F2 gələndə açar-açar açılacaq (test bunu qoruyur).

| Rol | Açarlar | Əhatə |
|---|---|---|
| `chair_head` | view, manage, distribute, report | UNIT — **öz kafedrası** |
| `teacher` / `assistant` / `lab_assistant` | view | yalnız ÖZ bölgü sətirləri (sorğu `teacher=request.user`) |
| `dean` | view, report | UNIT — fakültə |
| `program_coordinator` | view (yalnız backfill miqrasiyasında) | UNIT — ixtisas |
| `vice_rector`, `ikt_rehber` (RİM) | `workload.*` | ORG |
| `rector` | `*` | ORG |

`teaching_office_head` / `teaching_office_staff` rolları **BU KEÇİDDƏ ƏLAVƏ EDİLMƏYİB**
(F1 işidir; `ADMIN_ALIAS_EXEMPT_ROLE_NAMES` tələsi ora aiddir — spec §3.2).

**Fail-closed əhatə:** `apps/workload/services/scoping.py` sillabus naxışını təkrarlayır —
`get_permission_scope(user, org, permission)` + `user_scope_covers_unit`. `scope_unit`-i
təyin edilməmiş UNIT rolu HEÇ NƏ görmür (bütün təşkilat AÇILMIR) — test var.

---

## 4. Servislər (`apps/workload/services/`, hamısı < 600 sətir)

| Fayl | Məsuliyyət |
|---|---|
| `scoping.py` | `WorkloadActor`, `resolve_actor`, `can_manage_chair/can_distribute_chair/can_view_task`, `manageable_chairs`, `WorkloadDenied(code, message)` |
| `people.py` | kafedranın müəllim hovuzu + `ensure_assignable_teacher` (aşağıdakı deqradasiya qaydası) |
| `tasks.py` | `get_or_create_task`, `save_row`, `delete_row`, `row_warnings`, `normalize_academic_year` |
| `assignments.py` | `assign_teacher`, `unassign`, `remaining_hours`, `balance_for_rows` |
| `distribution.py` | `distribution_readiness`, `confirm_distribution`, `sync_offerings`, müəllim bildirişləri |
| `amendments.py` | `open_amendment`, `amendment_history` |
| `curriculum_import.py` | tədris planından sətir təklifləri |
| `queries.py` | bölgü cədvəli, müəllim yük paneli, «Dərs yüküm» sətirləri/xülasəsi |

### Qərar 1 — müəllim hovuzunun DEQRADASİYASI (real datadan doğur)
`teacher` rolu `COURSE` scope-ludur və köçürülmüş tenantlarda `Membership.scope_unit`
**çox vaxt boşdur**. Ona görə hovuz iki dalğalıdır:
1. `scope_unit` kafedranın alt-ağacındadır → `is_chair_member=True` (dəqiq bağlantı);
2. `scope_unit` NULL → universitet hovuzu, UI-da «kafedraya bağlanmamış» qeydi ilə.

**Başqa kafedraya BAĞLI müəllim hovuzda YOXDUR və təyin edilə BİLMƏZ**
(`workload.teacher_not_in_chair` — test var). Bu, köçürülmüş bazada bölgünün ümumiyyətlə
mümkün olmasının yeganə yoludur; `scope_unit` doldurulduqca 2-ci dalğa öz-özünə quruyur.

### Qərar 2 — tədris planı idxalı DEQRADASİYA İLƏ işləyir
`registrar.CurriculumSubject`-də **NƏ kredit, NƏ saat sütunu var** (yoxlanıldı:
`apps/registrar/models/academic.py:175`). Ona görə `curriculum_row_suggestions`:
fənn + semestr nömrəsi + ixtisas + səviyyə qaytarır, krediti `Subject.ects`-dən götürür,
saatı isə **yalnız TƏKLİF** kimi verir (`credits × 30`, spec §7) və sətrə avtomatik
YAZMIR — kafedra mühazirə/seminar/lab bölgüsünü özü doldurur. Plan sətrinə kredit sütunu
əlavə olunanda yalnız `_credits_for()` dəyişir.

### Qərar 3 — `confirm_distribution` (spec §4.3 + §7.1)
1. `ensure_can_distribute` (kafedra əhatəsi) + status yoxlaması;
2. **hazırlıq**: hər sətrin auditoriya fəaliyyətləri (mühazirə/seminar/lab) 100%
   bölünməlidir — «Vakant» da tam sayılır; əks halda `workload.distribution_incomplete`;
3. status → `distributed` (+ `distributed_by`/`distributed_at`);
4. **offering sinxronu**: `row.subject` + `row.period` + qrup dolu olan hər sətir üçün
   qrup-qrup `registrar.CourseOffering` **get_or_create**; `instructor` = mühazirəçi,
   yoxdursa ilk vakant-olmayan təyinat; `lesson_hours` = kontakt saatlarının cəmi.
   **HEÇ NƏ SİLİNMİR**, təkrar çağırış yeni açılış yaratmır (idempotent — test var);
   fənni/semestri/qrupu olmayan sətirlər `skipped` sayılır;
5. hər müəllimə bildiriş: «Dərs yükü təyin edildi: `<fənn>` — `<saat>` saat»
   (`NotificationType.ASSIGNMENT`, `metadata.event = "workload_assigned"`, link
   `/accounts/profile/?section=my-workload`); bildiriş xətası bölgünü DAYANDIRMIR;
6. `core.audit.log_action(AuditAction.UPDATE, reason="workload.distribution_confirmed")`
   — created/updated/notified/vacant rəqəmləri `new_values`-dədir.

Təsdiqdən sonra sətir/bölgü **birbaşa dəyişmir** (`workload.task_not_editable`) —
yalnız `WorkloadAmendment` (səbəb + qeyd məcburi, snapshot, audit) → status `amended`
→ yenidən təsdiq.

---

## 5. Kabinet bölmələri

İki bölmə, SCOUT §1-in **dörd yerli müqaviləsi** ilə qeydiyyatdan keçib
(`SECTION_PARTIALS`, `AJAX_SAFE_SECTIONS`, `profile.html` `data-ajax-sections`,
`rbac_sections` → `allowed_sections`) + `DIRECT_PROFILE_SECTION_TEMPLATES` + `_stage2/3/4`
+ `_sidebar_university.html`. Müqavilənin özü testlə qorunur (`test_sections.py`).

| Bölmə | Kim | Nə |
|---|---|---|
| `workload-distribution` «Yük bölgüsü» | `workload.manage`/`distribute` | il + kafedra seçicisi, tapşırıq statusu, sətir kartları + **fəaliyyət-fəaliyyət qalıq zolağı**, sətir modalı (yarat/redaktə/plandan gətir), bölgü modalı (fəaliyyət → müəllim (cari yükü ilə) → saat + qrup qeydi + «Vakant»), sağ **müəllim yük paneli** (saat/norma/doluluq, norma aşımında qırmızı), «Bölgünü təsdiqlə» modalı (nəticələri AÇIQ sadalayır), düzəliş modalı |
| `my-workload` «Dərs yüküm» | `workload.view` | il seçimi + fəsil tabları (Payız/Yaz/Yay/Yekun), 4 stat-kart (illik cəmi, norma, doluluq %, saathesabı), cədvəl (fənn · qrup · fəaliyyət · saat · forma · səviyyə) + CƏMİ sətri, sinxronlaşmış açılışa jurnal keçidi, **XLSX ixracı** (openpyxl `requirements/base.txt:142`-dədir) |

CSS/JS **yalnız xarici fayllarda** (CSP: inline yoxdur), `profile.html`-dən `allowed_sections`
şərti ilə yüklənir; dinamik dəyərlər `data-*` atributları və `#wl-catalog` JSON bloku ilə
ötürülür; JS `EMSReady`/`EMSDelegate`/`EMSCore.fetchJSON` naxışındadır; bütün modallar
`[data-profile-section-panel]` **içindədir** (AJAX swap-da itmir); seçicilər
`bootstrap-single-select` sarğısı ilə; boş vəziyyətlər `.ems-empty` primitivi ilə;
skeleton loader `prefers-reduced-motion`-a hörmət edir. Sidebar nişanı (badge) YOXDUR (tələb deyildi).

### JSON endpoint-lər — `config/urls.py`: `path("ders-yuku/", include((…, "workload"), namespace="workload"))`

| Ad | Metod | Yol |
|---|---|---|
| `workload:rows` | GET | `/ders-yuku/setirler/` — tapşırıq + sətirlər + balans + müəllim paneli + hazırlıq |
| `workload:chairs` | GET | `/ders-yuku/kafedralar/` |
| `workload:teachers` | GET | `/ders-yuku/muellimler/` (hovuz + cari yük) |
| `workload:options` | GET | `/ders-yuku/secimler/` (semestr/ixtisas/qrup/fənn) |
| `workload:curriculum` | GET | `/ders-yuku/tedris-plani/` |
| `workload:task` | POST | `/ders-yuku/tapsiriq/` |
| `workload:row_save` / `row_delete` | POST | `/ders-yuku/setir/yadda-saxla/` · `/setir/sil/` |
| `workload:assign` / `unassign` / `confirm` | POST | `/ders-yuku/bolgu/` · `/bolgu/sil/` · `/bolgu/tesdiq/` |
| `workload:amend` | POST | `/ders-yuku/duzelis/` |
| `workload:my_rows` / `my_export` | GET | `/ders-yuku/mene/setirler/` · `/mene/ixrac/` |

Hamısı `@login_required` + `@never_cache`; yazma endpoint-ləri `@require_POST` (CSRF);
`WorkloadDenied` → 403 + maşın-oxunaqlı `error` kodu.

---

## 6. Testlər — `apps/workload/tests/`

| Fayl | Nəyi sübut edir |
|---|---|
| `test_permission_catalog.py` | kateqoriya + etiket + validasiya; default rolların bölgüsü (müəllim bölə bilmir, dekan təsdiq etmir, `approve` heç kimdə açıq deyil) |
| `test_scope.py` | başqa kafedra üçün tapşırıq = 403; müəllim redaktə edə bilmir; `scope_unit`-siz UNIT rolu = boş əhatə |
| `test_assignments.py` | qalıq hesabı, saat aşımının bloklanması, `hours>0`, Vakant, `draft→distributing`, yad kafedranın müəllimi, balans xəritəsi, geri götürmə |
| `test_distribution.py` | yarımçıq bölgü təsdiqlənmir; təsdiq → offering + bildiriş + audit; **idempotentlik**; subject/period/qrupsuz sətir `skipped`; müəllim yalnız TƏSDİQLƏNMİŞ öz sətirlərini görür; amendment (qeyd məcburi, snapshot, append-only) |
| `test_rls.py` (`pytest.mark.postgres`) | tenant izolyasiyası (task/row/assignment), kontekstsiz = 0 sətir, **saat trigger-i** servisi yan keçən INSERT-i də bloklayır, amendment cədvəli UPDATE-i rədd edir |
| `test_sections.py` | dörd-yerli qeydiyyat müqaviləsi; fraqment: kafedra müdiri 200, müəllim `my-workload` 200 / `workload-distribution` 403, **tələbə hər ikisində 403**; JSON qapıları (anonim, müəllim hovuza girə bilmir, GET-lə yazma 405) |

**Nəticə: 71 passed** (öz izolyasiya bazamda — `postgres://…:55432/ems_wl_7f2b`):

```
apps/workload/tests                          43 passed   (RLS/trigger daxil)
apps/organizations/tests/test_permissions.py 15 passed
apps/accounts/tests/test_sidebar_role_matrix.py 13 passed
                                             71 passed in 6.12s
```

RLS testləri `SET LOCAL ROLE rls_app_role` ilə işləyir (sillabus naxışı), yəni
mənfi assert-lər `emsarena_agent`-in BYPASSRLS statusundan asılı DEYİL.

### İki REAL tapıntı (testlər üzə çıxardı)

1. **`schema_editor.execute(...)` + plpgsql `%`** → `IndexError: tuple index out of
   range`. `RAISE EXCEPTION 'activity=% cap=%'` format spesifikatorları psycopg-nin
   parametr interpolyasiyasına düşür. Düzəliş: `params=None` (miqrasiyada şərhlə
   qeyd edilib). **Bu tələ hər yeni plpgsql miqrasiyasına aiddir.**
2. **`registrar_guard_active_member` müəllim qapısı** (`registrar/0041`):
   `CourseOffering.instructor` üçün istifadəçi aktiv üzvlükdə **`grade.input`**
   (və ya `grade.*`/`*`) daşımalıdır. Köçürülmüş tenantlarda müəllim rolu bəzən bu
   açarı daşımır — belə halda BÜTÜN bölgü təsdiqi geri qayıdardı. İndi
   `_write_offering` savepoint ilə müəllimsiz yazır və `instructor_blocked` sayır
   (test: `test_instructor_without_grade_input_does_not_break_the_sync`).

---

## 7. Qapılar (gates)

| Qapı | Nəticə |
|---|---|
| `black` / `isort` | ✅ tətbiq olundu |
| `flake8` (setup.cfg) | ✅ təmiz (B042/B014/B017 düzəldildi) |
| `scripts/check_module_size.py --check` | ✅ exit 0 (ən böyük fayl `distribution_api.py` ≈ 400 sətir) |
| `scripts/module_deps.py --check` | ✅ exit 0 — yeni kənarlar: `accounts → workload`, `workload → organizations/notifications`; **dövr yoxdur** (workload accounts-u import ETMİR) |
| `makemigrations --check --dry-run` | ✅ «No changes detected» |
| `scripts/check_i18n_catalogs.py` | ✅ exit 0 — «yeni borc yoxdur»; üstəlik `django/az: source_missing 3 → 2 ✓` |
| pytest (workload + qonşu iki dəst) | ✅ 71 passed |

---

## 8. İcra qeydləri və mühit problemləri (DÜRÜST HESABAT)

1. **Worktree köhnə bazadan başlamışdı.** İş başlayanda worktree `a1214fc9` (2026-08-01)
   üzərində idi — `apps/syllabus`, `apps/legacy_import` və `docs/workload/` orada YOX idi.
   Worktree təmiz olduğu üçün `git reset --hard 260112af` ilə audit qoluna gətirildi.
2. **`~/Desktop` iCloud mount-u iş vaxtı qopdu** (2026-09-02 ~19:47). Repo itməyib —
   fayllar `~/Library/Mobile Documents/com~apple~CloudDocs/Desktop/…` altındadır və işin
   qalanı həmin yoldan icra olundu. `~/Desktop` yenidən qoşulanda heç nə dəyişmir.
   Bu səbəbdən `git` əməliyyatları (status/diff) icra edilə bilmədi.
3. **QA klonuna miqrasiya: YALNIZ `workload` app-ı.** Klonda paralel agentlərin
   miqrasiyaları var (`organizations/0033`, `0034`, `applications` app-ı və s.) və o
   fayllar mənim worktree-mdə YOXDUR. `staging_inspect.sh migrate` (bütün app-lar)
   QƏSDƏN işlədilmədi — bunun əvəzinə yalnız `manage.py migrate workload` icra olundu
   (üç miqrasiya, ADDİTİV: 5 yeni cədvəl + siyasət/trigger + rol backfill-i). Başqa
   app-ın vəziyyətinə toxunulmadı. `SECRET_KEY` worktree-də `.env` olmadığı üçün
   birdəfəlik dəyərlə ötürüldü.
4. **i18n kataloqları TAMAMLANDI.** 89 yeni msgid (`accounts.workload` + `profile.sidebar`
   kontekstləri) dörd `django` kataloquna əlavə olundu: `az` — msgid-in özü,
   `en`/`ru`/`tr` — ƏSL tərcümə (identity borcu yaratmasın deyə; TR-də `Aç`/`Saat`/`saat`
   ayrıca düzəldildi). `compilemessages` işlədilib, `.mo` fayllarının 4-ü də yenilənib.
   Qapı: **exit 0**. `makemessages` QƏSDƏN işlədilmədi (bu mühitdə saatlarla çəkirdi) —
   əvəzinə qapının öz mənbə-skaneri (`scripts/i18n_source_scan.py`) ilə boşluq siyahısı
   çıxarılıb və birdəfəlik doldurma skripti ilə yazılıb. Nəticə eynidir: qapı `source_missing`
   ölçür və indi 3 → 2 (azalıb). ⚠️ Növbəti dəfə kimsə `makemessages` işlədəndə bu girişlərə
   sətir-nömrə şərhləri əlavə olunacaq — məzmun dəyişmir.
5. **iCloud eviction tələsi (yeni, sənədləşdirməyə dəyər):** `.mo`/`.po` faylları
   materiallaşmamış olanda `polib` onları BOŞ oxuyur və qapı ya `struct.error` ilə çökür,
   ya da yalançı «10181 yeni tərcümə borcu» göstərir. Ölçmədən əvvəl faylları
   (`wc -c locale/*/LC_MESSAGES/*.po`) materiallaşdırmaq lazımdır.

---

## 8-A. CANLI YOXLAMA — QA klonu (real köçürülmüş data)

`emsarena_rehearsal_a0d170000901`, org `myedu-univ` (`526cfa63…`), skript
`/private/tmp/wl_live_check.py` (`manage.py shell <`).

**Aktorlar (klondakı vəziyyət — qeyd olunası tapıntı):**

| Şəxs | Əvvəl | Sonra |
|---|---|---|
| `qa.chair_head` | `chair_head`, `scope_unit` = **«Proqramlaşdırma və informasiya təhlükəsizliyi»** (ARTIQ TƏYİN EDİLİB) | dəyişməyib |
| `qa.teacher` | `teacher`, **`scope_unit` = NULL** | həmin kafedraya bağlandı |
| `myedu.worker.19` (köçürülmüş müəllim) | `teacher` üzvlüyü var | həmin kafedraya bağlandı |

⚠️ `qa.teacher`-in `scope_unit`-i BOŞ idi — bu, §4 «Qərar 1»-in (NULL scope_unit
hovuza düşür) niyə lazım olduğunun canlı sübutudur.

**Rol backfill-i (miqrasiya `0003`) klonda işlədi:**
`chair_head` → `workload.view/manage/distribute/report`; `teacher` → `workload.view`.

**Axın:** 2026/2027 tapşırığı yaradıldı (`9b1ac360…`, `draft`) → 3 sətir (real fənlər:
`MYEDU-L100`, `MYEDU-L1000`, `MYEDU-L1001`; real qruplar; semestr «Yay 2026/2027»;
hər sətir 45 saat) → **6 bölgü** (qa.teacher 3, myedu.worker.19 1, Vakant 2) →
`confirm_distribution`.

**Nəticə (ölçülmüş):**

```
status                : distributed
sync                  : created=3  updated=0  skipped=0  instructor_blocked=0
CourseOffering delta  : +3   (MYEDU-L100 → qa.teacher, MYEDU-L1000 → myedu.worker.19,
                              MYEDU-L1001 → qa.teacher; hər biri lesson_hours=45)
InAppNotification     : 2   («Dərs yükü təyin edildi: … — 30 saat» / «… + 1 — 60 saat»)
AuditLog              : workload.TeachingTask/distribution_confirmed + 6 × TeacherAssignment/assigned
qa.teacher rows       : 3 sətir, cəmi 60 saat, norma 500, doluluq 12%
                        (hər sətirdə `offering_id` var → jurnal keçidi işləyir)
```

**HTTP səthi (Django test client, klon bazası üzərində):**

| Sorğu | Nəticə |
|---|---|
| `GET /accounts/profile/api/sections/my-workload/` (qa.teacher) | **200**, `data-wlm-root` var |
| `GET /accounts/profile/api/sections/workload-distribution/` (qa.teacher) | **403** |
| `GET /accounts/profile/api/sections/workload-distribution/` (qa.chair_head) | **200**, `data-wl-root` var |
| `GET /ders-yuku/setirler/?chair=…&year=2026/2027` (qa.chair_head) | **200**, 3 sətir, 3 müəllim kartı |

---

## 9. Merge-dən sonra ediləcəklər

1. **`makemigrations --check`** merge olunmuş ağacda TƏKRAR icra edilməlidir (paralel
   agentlərin `organizations/0033`, `notifications/0004`, `registrar/0063`,
   `accounts/0018`, `legacy_import/0007` miqrasiyaları ilə birlikdə). `workload/0003`
   yalnız `organizations/0032`-dən asılıdır, ona görə toqquşma GÖZLƏNİLMİR.
2. **Klonda `qa.teacher` üçün `Membership.scope_unit` təyin edildi** (əvvəl NULL idi) və
   `myedu.worker.19` də test kafedrasına bağlandı. Klon test mühitidir, amma bunu
   bilmək lazımdır: prodda müəllim `scope_unit`-lərinin doldurulması AYRI işdir
   (onsuz hovuz «kafedraya bağlanmamış» dalğasına söykənir).
3. **`workload.report` səthi hələ boşdur** — açar verilib, amma hesabat ekranı F5-dədir.
   Dekan `workload.view` ilə yalnız bölgü panelinə (öz fakültəsinin kafedraları) düşür.
4. **`apps/accounts/tests/test_sidebar_role_matrix.py`** — matris rolları
   `permissions=[]` daşıyır, ona görə gözlənti dəyişmədi; əvəzinə YENİ mənfi test
   əlavə olundu (`test_workload_sections_need_an_explicit_permission`): bölmələr
   heç bir rola «rol bayrağı» ilə sızmır.

## 10. F1/F2/F5-ə təxirə salınanlar

- **F1:** tədris şöbəsi rolları (`teaching_office_head` + `ADMIN_ALIAS_EXEMPT` tələsi),
  Excel idxal sehrbazı, grid redaktoru, `submit` axını, izləmə paneli.
- **F2:** `TaskFacultySlice` + `TaskRowReview` modelləri, koordinator vizası,
  dekan təsdiq/qaytarma, dilim bildirişləri, `returned` sətir işarələri.
- **F5:** rəsmi TAPŞIRIQ formatında Excel hesabatı, fərdi iş planı PDF-i, il rollover-i,
  deadline + eskalasiya, plan-fakt (jurnal `Lesson.hours` ilə tutuşdurma), vakant fond
  hesabatı, `WorkloadSettings` (norma/tavan/avto-sinxron konfiqurasiyası — hazırda
  sabitlər `constants.py`-dədir və `TeacherWorkloadProfile` ilə override olunur).

---

## 11. `apps/workload/` XARİCİNDƏ dəyişən fayllar (merge üçün)

**Dəyişdirilib:**

| Fayl | Nə dəyişib |
|---|---|
| `apps/accounts/templates/accounts/profile.html` | CSS/JS include blokları + dispatch `elif`-ləri + `data-ajax-sections` |
| `apps/accounts/templates/accounts/profile/_sidebar_university.html` | iki menyu girişi + «Universitet» qrup başlığının şərti |
| `apps/accounts/tests/test_sidebar_role_matrix.py` | YENİ mənfi test (bölmə rol bayrağı ilə açılmır) |
| `apps/accounts/views/_helpers/rbac_sections.py` | icazə qapıları + 3 yeni bayraq |
| `apps/accounts/views/profile/_sections/labels.py` | `DIRECT_PROFILE_SECTION_TEMPLATES` + başlıqlar |
| `apps/accounts/views/profile/context_builder/_stage2.py` | iki boş bölmə dict-i |
| `apps/accounts/views/profile/context_builder/_stage3.py` | iki context qurucusu çağırışı |
| `apps/accounts/views/profile/context_builder/_stage4.py` | iki açar şablon kontekstinə |
| `apps/accounts/views/profile/sections_api.py` | `SECTION_PARTIALS` + `AJAX_SAFE_SECTIONS` |
| `apps/organizations/permissions.py` | «workload» kateqoriyası + 7 açar + etiketlər |
| `apps/organizations/default_roles_university.py` | 5 rola workload açarları |
| `config/settings/components/apps.py` | `INSTALLED_APPS` |
| `config/urls.py` | `ders-yuku/` include |
| `locale/{az,en,ru,tr}/LC_MESSAGES/django.po` + `.mo` | 89 yeni msgid + kompilyasiya |

**Yeni fayllar (accounts tərəfində):**

```
apps/accounts/views/profile/_sections/workload.py
apps/accounts/templates/accounts/profile/sections/_workload_distribution.html
apps/accounts/templates/accounts/profile/sections/_my_workload.html
apps/accounts/static/accounts/css/profile/sections/workload_base.css
apps/accounts/static/accounts/css/profile/sections/workload_dialog.css
apps/accounts/static/accounts/js/profile/workload_distribution_render.js
apps/accounts/static/accounts/js/profile/workload_distribution.js
apps/accounts/static/accounts/js/profile/workload_my.js
docs/audits/2026-09-02/PHASE4_WORKLOAD.md   (bu sənəd)
```

⚠️ **Toqquşma riski:** `sections_api.py`, `labels.py`, `rbac_sections.py`,
`_stage2/3/4.py`, `profile.html`, `_sidebar_university.html`, `permissions.py`,
`config/urls.py`, `config/settings/components/apps.py` və 8 locale faylına paralel
agentlər də toxunur. Hər dəyişikliyim AYRI blokdur (mövcud sətirlərin arasına əlavə),
ona görə konflikt olsa da həlli mexanikidir.
