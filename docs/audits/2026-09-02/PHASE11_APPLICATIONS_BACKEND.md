# FAZA 11 — `apps.applications` («Müraciətlər») backend + API müqaviləsi

Branch `audit/post-migration-qa-2026-09` · 2026-09-02

Bu sənəd **UI agenti üçün müqavilədir**: endpoint-lər, payload formaları, əməl
semantikası, xəta formatı və servis xəritəsi. Ekran profil kabinetinin
bölməsidir (sol sidebar QALIR, sağda AJAX fraqment) — ayrıca tam səhifə YOXDUR.

| | |
|---|---|
| URL prefiksi | `/muracietler/` (`config/urls.py`, namespace `applications`) |
| Bölmə açarı | `my-applications` (`apps.applications.public.PROFILE_SECTION`) |
| Fasad | `apps.applications.public.build_applications_context(request, organization=…)` |
| İcazə açarları | `application.create`, `application.handle`, `application.manage` |
| Nömrə | `MR-000001` — təşkilat üzrə ardıcıl (`ApplicationCounter` + `select_for_update`) |
| SLA | İŞ GÜNÜ (B.e–Cümə): `sla_due_on = add_working_days(submitted_date, kind.sla_days)` |

Bütün endpoint-lər **login + aktiv təşkilat** tələb edir; POST-lar **CSRF** istəyir.

---

## 1. Xəta formatı (bütün endpoint-lərdə eyni)

```json
{ "ok": false, "errors": { "subject": ["Mövzu ən azı 5 simvol olmalıdır."] } }
```

* Sahəyə bağlanmayan xəta → `"__all__"` açarı.
* Keçid xətasında əlavə `"code"` açarı (maşın-oxunaqlı):
  `transition.unknown`, `transition.invalid_source`, `transition.reason_required`,
  `transition.text_too_short`, `permission.denied`, `permission.not_handler`,
  `permission.not_sender`, `sender.no_membership`, `kind.not_allowed`,
  `unit.same`, `unit.unknown`, `assignee.not_handler`.
* HTTP: `400` yoxlama/keçid · `403` giriş və `permission.*` · `404` tapılmayan
  **və ya görünməyən** müraciət (mövcudluq faktı sızmır).

Uğur həmişə `{"ok": true, …}`.

---

## 2. Endpoint-lər

### 2.1 `GET /muracietler/api/list/`
`tab=mine|inbox|watching|archive` · `stat=open|overdue|closed|all` · `kind=<code>` ·
`q=<axtarış>` · `page=<n>` (səhifə 30).
`q` mövzu + nömrə + göndərənin ad/soyad/username üzrə axtarır. `archive` tabı
`stat`-ı nəzərə almır (həmişə bağlı statuslar).

```json
{ "ok": true, "results": [ /* §3.1 */ ], "page": 1, "pages": 1, "total": 1,
  "tab": "mine", "counts": {"mine":1,"inbox":0,"watching":0,"archive":0} }
```

### 2.2 `GET /muracietler/api/<id>/`
**Yan təsir:** cari şöbənin emalçısı İLK dəfə açanda status `submitted → in_review`
olur və `seen` hadisəsi yazılır (dizayn §3.4). Sahib üçün yan təsir yoxdur.
→ `{ "ok": true, "application": { /* §3.2 */ } }`

### 2.3 `GET /muracietler/api/catalog/`
```json
{ "ok": true, "family": "student", "can_create": true, "is_handler": false,
  "can_manage": false, "kinds": [ /* §3.3 — yalnız bu ailəyə açıq növlər */ ],
  "units": [ /* §3.4 */ ], "statuses": [ /* §3.5 */ ],
  "rules": {"min_subject_length":5,"min_body_length":20,"min_note_length":10} }
```

### 2.4 `POST /muracietler/api/create/` — `multipart/form-data`
| sahə | tələb | qeyd |
|---|---|---|
| `kind` | ✔ | növün **kodu** (`diger`, `transkript`, …) |
| `subject` | ✔ | ≥ 5 simvol |
| `body` | ✔ | ≥ 20 simvol |
| `files` | — | çoxlu fayl; `.pdf .jpg .jpeg .png .docx`, hər biri ≤ 10 MB, əməl başına ≤ 5 |

**Şöbə göndərilmir və qəbul edilmir** — ünvan serverdə növ + ailə üzrə hesablanır.

### 2.5 `POST /muracietler/api/<id>/action/` — `multipart/form-data`
| `action` | aktor | əlavə sahələr | nəticə status |
|---|---|---|---|
| `mark_seen` | emalçı | — | `in_review` |
| `add_comment` | emalçı / sahib | `text` (≥1), `is_internal` (yalnız emalçı), `files` | dəyişmir |
| `assign` | emalçı | `assignee` (user id), `text` | `assigned` |
| `forward` | emalçı | `target_unit` (şöbə **kodu**), `text` (≥10), `keep_watching` (default `true`) | `forwarded` |
| `request_info` | emalçı | `text` (≥10), `files` | `waiting_info` |
| `provide_info` | sahib | `text` (≥10), `files` | `in_review` |
| `return_for_correction` | emalçı | `reason` (≥10) | `returned` |
| `resubmit` | sahib | `subject` (≥5), `body` (≥20), `files` | `submitted` |
| `resolve` | emalçı | `text` (≥10), `files` | `resolved` |
| `reject` | emalçı | `reason` (≥10) | `rejected` |
| `close` | sahib | `text` | `closed` |
| `cancel` | sahib | `reason` | `cancelled` |

`text` və `reason` bir-birini əvəz edir. Cavab: yenilənmiş detal payload-u.

### 2.6 `GET /muracietler/api/kpis/`
```json
{ "ok": true,
  "sender":  {"open":1,"waiting_info":0,"resolved":0,"avg_response_days":0.0},
  "is_handler": true,
  "counts":  {"mine":1,"inbox":1,"watching":0,"archive":0},
  "handler": {"inbox_open":1,"new_unseen":1,"overdue":0,"watching":0} }
```
`handler` açarı yalnız `is_handler == true` olduqda var. Dizayn §4.3 kartları ilə
birbaşa uyğundur.

### 2.7 `GET /muracietler/api/<id>/attachments/<att_id>/download/`
İcazə qapılı `FileResponse`; görünüş hüququ olmayana `404`. Başlıqlar:
`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`,
`Cache-Control: private, no-store`.
**URL-i özünüz qurmayın** — `attachment.download_url`-dan götürün.

---

## 3. Payload formaları

### 3.1 Siyahı sətri
```json
{ "id":"…", "number":"MR-000001", "subject":"…",
  "kind":   {"code":"diger","label":"Digər","palette":"neutral","bg":"#f1f5f9","fg":"#334155"},
  "status": {"key":"submitted","label":"Yeni","palette":"primary","bg":"#dbeafe","fg":"#1e40af"},
  "current_unit": {"id":"…","code":"koordinator","name":"Proqram koordinatoru","note":"…","resolve_by":"specialty"},
  "requester": {"id":"…","name":"Ad Soyad","username":"qa.student"},
  "requester_scope":"634 ing",
  "submitted_at":"2026-09-02T…", "last_activity_at":"2026-09-02T…",
  "sla_due_on":"2026-09-09", "is_open":true, "is_overdue":false,
  "attachment_count":0, "owner_label":"sizdədir" }
```
`owner_label` dizayn §4.6-nın sağ etiketidir: emalçıya `sizdədir`, digərinə `<şöbə>-də`.

### 3.2 Detal (= sətir + aşağıdakılar)
```json
{ "body":"…",
  "assigned_to": {"id":"…","name":"…","username":"…"},        // və ya null
  "current_scope_unit":"Dizayn (Qrafik)",
  "sla": {"tone":"ontime|overdue|closed","days":3,"sla_days":5,"status_label":"Baxılır"},
  "attachments": [{"id":"…","name":"arayis.pdf","size":1234,
                   "content_type":"application/pdf","download_url":"/muracietler/api/…/download/"}],
  "events": [{"id":"…","kind":"forwarded","kind_label":"Başqa şöbəyə yönləndirildi",
              "actor":"Ad Soyad","actor_role":"program_coordinator",
              "from_unit":"Proqram koordinatoru","to_unit":"RİM (Rəqəmsal İnkişaf Mərkəzi)",
              "old_status":"in_review","new_status":"forwarded","text":"…",
              "is_internal":false,"created_at":"…","attachments":[…]}],
  "viewer": {"is_handler":true,"is_sender":false,"is_watcher":false},
  "allowed_actions": ["resolve","request_info","forward","return_for_correction","reject","assign","add_comment"] }
```
* `sla.tone` → dizayn §4.7-nin üç zolağı; `days` HƏMİŞƏ müsbətdir.
* **`is_internal: true` hadisələr sahibə heç vaxt göndərilmir** — süzgəc serverdədir.
* **`allowed_actions` yeganə həqiqətdir**: düymələri buna görə göstərin, rol/statusdan
  özünüz nəticə çıxarmayın. Boş siyahı = yalnız oxuma.

### 3.3 Növ
```json
{ "id":"…","code":"diger","label":"Digər","note":"…","sla_days":5,
  "palette":"neutral","bg":"#f1f5f9","fg":"#334155",
  "families":["student","teacher","staff"],
  "destination":{"id":"…","code":"koordinator","name":"Proqram koordinatoru","note":"…","resolve_by":"specialty"},
  "routing_hint":"Bu müraciət «Proqram koordinatoru»-nə gedəcək · cavab müddəti 5 iş günü." }
```
`routing_hint` dizayn §3.2-nin canlı sətridir — olduğu kimi göstərin.
`qiymet` növündə əlavə `external_link: {"label":…, "url":"/appeals/my/"}` gəlir:
**rəsmi apellyasiya `apps.appeals`-dədir, burada TƏKRARLANMIR.**

### 3.4 Şöbə
`{"id","code","name","note","resolve_by"}` — `note` yönləndirmə dialoqundakı qısa
izahdır. Yönləndirmə siyahısında **cari şöbəni özünüz çıxarın** (server eyni şöbəyə
yönləndirməni `unit.same` ilə rədd edir).

### 3.5 Status kataloqu — `{"key","label","palette","bg","fg"}` × 10
`submitted` Yeni ✔ · `in_review` Baxılır ✔ · `assigned` Təyin edilib ✔ ·
`forwarded` Yönləndirilib ✔ · `waiting_info` Məlumat gözlənilir ✔ ·
`returned` Düzəliş üçün qaytarılıb ✔ · `resolved` Həll olunub ✘ ·
`rejected` Rədd edilib ✘ · `closed` Bağlanıb ✘ · `cancelled` Ləğv edilib ✘
(✔ = açıq).

Hadisə növləri (`events[].kind`): `submitted`, `seen`, `comment`, `assigned`,
`info_requested`, `info_provided`, `forwarded`, `returned`, `resubmitted`,
`resolved`, `rejected`, `closed`, `cancelled`.

Palitralar: `primary` `#dbeafe/#1e40af` · `warning` `#fef3c7/#92400e` ·
`danger` `#fee2e2/#b91c1c` · `neutral` `#f1f5f9/#334155` · `success` `#dcfce7/#15803d`.
Rənglər payload-da hazır gəlir — UI-da təkrar xəritə saxlamayın.

---

## 4. Kataloq (per-tenant, redaktə oluna bilən)

### 4.1 Şöbələr — `ApplicationUnit`
| code | ad | emal edən rol(lar) | `resolve_by` | SLA |
|---|---|---|---|---|
| `telebe` | Tələbə Xidmətləri Mərkəzi | `hr` ⚙ | təşkilat | 3 |
| `tedris` | Tədris Şöbəsi | `vice_rector` | təşkilat | 5 |
| `dekan` | Dekanlıq | `dean` | fakültə | 5 |
| `kafedra` | Kafedra müdirliyi | `chair_head` | kafedra | 5 |
| `koordinator` | Proqram koordinatoru | `program_coordinator` | ixtisas | 3 |
| `maliyye` | Maliyyə Şöbəsi | `hr` ⚙ | təşkilat | 5 |
| `kadrlar` | Kadrlar şöbəsi | `hr` ⚙ | təşkilat | 5 |
| `rim` | RİM (Rəqəmsal İnkişaf Mərkəzi) | `ikt_rehber` | təşkilat | 2 |
| `imtahan` | İmtahan Mərkəzi | `exam_center`, `exam_center_head` | təşkilat | 3 |

⚙ = **konfiqurasiya yeri**: bu kod bazasında tələbə xidmətləri / maliyyə / kadrlar
üçün ayrıca rol YOXDUR, ona görə default `hr`-dir. Tenant öz rolunu yaradanda
`ApplicationUnit.handler_role_names` dəyişdirilir — KOD dəyişmir.
Dizayndakı `ikt` «İKT Şöbəsi» çıxarılıb: adı `rim` / «RİM (Rəqəmsal İnkişaf
Mərkəzi)»-dir (rol açarı `ikt_rehber` qalır).

### 4.2 Növlər — `ApplicationKind`
| code | etiket | ailələr | şöbə | SLA | palitra |
|---|---|---|---|---|---|
| `transkript` | Transkript sorğusu | student | telebe | 3 | primary |
| `arayis` | Arayış sorğusu | student | telebe | 2 | primary |
| `qiymet` | Qiymətə etiraz | student | dekan | 5 | warning |
| `sikayet` | Şikayət | student, teacher | dekan | 10 | danger |
| `hereket` | Tələbə hərəkəti | student | dekan | 7 | neutral |
| `odenis` | Təhsil haqqı | student | maliyye | 5 | neutral |
| `teqdimat` | Təqdimat | teacher | kafedra | 10 | primary |
| `texniki` | Texniki problem | student, teacher, staff | rim | 2 | neutral |
| `cedvel` | Dərs cədvəli | student, teacher | koordinator | 3 | neutral |
| `davamiyyet` | Davamiyyət düzəlişi | student | dekan | 5 | warning |
| `melumat` | Tələbə məlumatının düzəlişi | student | telebe | 3 | primary |
| `senedler` | Sənəd sorğusu | student | telebe | 3 | primary |
| `hr` | Kadr məsələsi | teacher, staff | kadrlar | 5 | neutral |
| `imtahan` | İmtahan məsələsi | student, teacher | imtahan | 3 | warning |
| `diger` | Digər | student, teacher, staff | **ailəyə görə** | 5 | neutral |

`diger` → `route_overrides = {"student":"koordinator","teacher":"kafedra","staff":"rim"}`.

---

## 5. Görünüş və əməl qaydaları (server fail-closed)

| | oxuyur | qərar verir |
|---|---|---|
| müraciət sahibi | ✔ | ✘ (yalnız `provide_info` / `resubmit` / `close` / `cancel`) |
| **cari** şöbənin əhatəli emalçısı | ✔ | ✔ |
| **izləyən** şöbənin emalçısı | ✔ | ✘ |
| `application.manage` (RİM, prorektor, rektor) | ✔ (hamısını) | ✘ |
| superuser / təşkilat sahibi | ✔ | ✔ |
| başqa ixtisasın koordinatoru / rolsuz istifadəçi | ✘ | ✘ |

«Əhatə»: şöbənin `resolve_by`-ı `organization`-dursa rol adı kifayətdir; əks halda
üzvlüyün `scope_unit`-i müraciətin `current_scope_unit`-ini materialized-path
prefiksi ilə örtməlidir. Əcdad tapılmasa `current_scope_unit = NULL` olur —
müraciət İTMİR, həmin rolun bütün daşıyıcılarına açıq olur (fail-open GÖRÜNÜŞ,
fail-closed ƏMƏL deyil).

Göndərən ailəsi AKTİV üzvlükdən çıxır: `student`/`lead_student` → `student`;
müəllim/assistent rolları → `teacher`; qalan hər aktiv üzvlük → `staff`.
**Aktiv üzvlüyü olmayan müraciət yarada bilmir** (`sender.no_membership`).

İCAZƏ yoxlanışı STATUS yoxlanışından ƏVVƏLDİR (`services/workflow._guard`):
əks sıra səlahiyyətsiz istifadəçiyə «bu status bu əməli qəbul etmir» cavabı ilə
müraciətin harada olduğunu sızdırardı.

---

## 6. Servis xəritəsi (view-lar YALNIZ buradan keçir)

| modul | məsuliyyət |
|---|---|
| `services/routing.py` | `sender_family_for`, `sender_scope_unit_for`, `resolve_scope_unit`, `route_for`, `allowed_kinds_for` — ünvan YALNIZ burada hesablanır |
| `services/access.py` | `can_view`, `can_act`, `handles_unit`, `inbox_q`, `watching_q`, `visible_q`, `has_app_permission` |
| `services/submit.py` | `next_number`, `validate_text`, `attach_files`, `submit_application` |
| `services/workflow.py` | 12 keçid + `ACTION_DISPATCH`; hər biri 1 tranzaksiya, 1 hadisə, 1 audit sətri |
| `services/queries.py` | `list_applications`, `sender_kpis`, `handler_kpis`, `tab_counts` |
| `services/catalog.py` | `seed_catalog` (idempotent; miqrasiya + management əmri eyni funksiyanı çağırır) |
| `services/maintenance.py` | `close_stale_resolved` — 5 iş günü sonra avtomatik bağlama |
| `services/notify.py` | bildiriş (`on_commit`, try/except) + `core.audit.log_action` + badge keşi |
| `state_machine.py` | qaydalar (DB-siz): `RULES`, `ensure_allowed`, `available_actions`, `TransitionDenied` |
| `sla.py` | `add_working_days`, `working_days_between`, `sla_banner` |
| `payloads.py` | bu sənədin KOD qarşılığı |
| `public.py` | `build_applications_context`, `endpoints()`, `PROFILE_SECTION`, `open_application_count` |

Model qatı: `ApplicationUnit`, `ApplicationKind`, `ApplicationCounter`,
`Application`, `ApplicationEvent` (append-only — `save()`/`delete()` xəta verir),
`ApplicationWatch`, `ApplicationAttachment`.

Miqrasiyalar: `0001_initial` · `0002_rls_applications` (7 cədvəldə ENABLE+FORCE
RLS, `rls_tenant_isolation` siyasəti) · `0003_seed_permissions_and_catalog`
(mövcud tenantlara icazə + kataloq; idempotent, geri dönüşdə kataloq SİLİNMİR —
`Application.kind` PROTECT-dir).

Əlavə: `apps/notifications/migrations/0004_…` (`NotificationType.APPLICATION`),
`apps/organizations/unit_heads.py` (`resolve_ancestor`, `members_covering_unit`),
`scripts/i18n_fill_applications.py` (4 dil × 47 giriş).

---

## 7. Yoxlama vəziyyəti

**Testlər — 152 keçdi** (private DB `ems_app_714a2e09` @ agent postgres):
`test_state_machine` 52 (hər qanuni/qanunsuz keçid) · `test_sla` 11 ·
`test_routing` 10 · `test_permission_boundaries` 10 · `test_workflow` 20 ·
`test_endpoints` 20 · `test_permission_catalog` 10 · `test_rls` 4
(`pytest.mark.postgres`, `SET LOCAL ROLE rls_app_role`) ·
`apps/organizations/tests/test_permissions.py` 15 — hamısı yaşıl.

**Gate-lər:** black ✓ · isort ✓ · flake8 ✓ · `check_module_size.py --check` ✓ ·
`module_deps.py --check` ✓ (yeni dövr yoxdur) · `makemigrations --check` ✓ ·
`check_worker_atomic_coverage.py --check` ✓.
`check_i18n_catalogs.py` — bizim regressiya YOXDUR (`django/az source_missing`
baseline 3-ə qaytarıldı); qapı yalnız `django/tr identity 270 → 278` ucbatından
qırmızıdır və onun 7-si cədvəl agentinin (`accounts.schedule_manage`), 1-i bizim
`applications|Yeni` → «Yeni» (düzgün türkcə) girişidir. İnteqrasiyada bir dəfəlik
`--update` lazımdır.

### Canlı ssenari — QA klonu `emsarena_rehearsal_a0d170000901`, org `myedu-univ`
Miqrasiyalar tətbiq olundu (0001/0002/0003 — `django_migrations`-da 07:16),
kataloq **9 şöbə / 15 növ** ilə seed olundu; icazələr 15 rola yazıldı.

1. `qa.student` → `GET catalog/`: ailə `student`, **13 növ**, «Digər» ünvanı
   *Proqram koordinatoru*, hint «…cavab müddəti 5 iş günü.»
2. `POST create/` → `MR-000001`, status `submitted`, şöbə `koordinator`,
   aidiyyət **Dizayn (Qrafik)**, `sla_due_on = 2026-09-09` (5 iş günü).
3. `qa.program_coordinator` → `inbox` total **1**; `GET <id>/` statusu
   `in_review`-ə keçirdi; `allowed_actions` 7 əməl.
4. `POST action=forward target_unit=rim keep_watching=true` → status `forwarded`,
   şöbə `rim`.
5. `qa.ikt_rehber` → `inbox` total **1**; `add_comment` + `resolve` → `resolved`.
6. `qa.student` detalında zaman xətti tam: `submitted → seen → forwarded →
   comment → resolved`; `allowed_actions = ["close"]`; `sla.tone = "closed"`.
7. `qa.program_coordinator`: `watching` total **1**, `inbox` total **0**.
8. Bildirişlər: `qa.student` 4 · `qa.program_coordinator` 2 (gələn + izləyici
   «həll olundu») · `qa.ikt_rehber` 1 · `qa.sec.ikt_rehber_b` 1.
   Audit: **5 sətir** (`create` submitted, `update` seen/forwarded/comment/resolved).

**Klonda edilmiş düzəliş:** `qa.student` üzvlüyünün `scope_unit`-i BOŞ idi —
ssenari onu `634 ing` qrupuna bağladı (qrup → **Dizayn (Qrafik)** ixtisasına
qalxır, koordinatorun scope-u ilə üst-üstə düşür). `qa.program_coordinator`
onsuz da həmin ixtisasa bağlı idi. **Yalnız klonda**; real bazaya toxunulmayıb.

---

## 8. UI agenti üçün qeydlər

1. **Ünvanı klientdə hesablamayın** — `catalog/` cavabındakı `destination` +
   `routing_hint` hazırdır; `create/`-ə şöbə göndərməyin.
2. **Düymələri `allowed_actions`-a görə göstərin** — rol/status məntiqini UI-da
   təkrarlamayın.
3. **Uzunluq qaydalarını `rules` obyektindən oxuyun** (5/20/10), sabit yazmayın.
4. **Yönləndirmə dialoqunda cari şöbəni siyahıdan çıxarın.**
5. **Fayl linki yalnız `download_url`-dandır**; `MEDIA_URL` ilə qurulan link işləmir.
6. **CSS/JS xarici fayla** (CSP `SELF`+NONCE) — dinamik dəyər `data-*` /
   `json_script` ilə; JS `window.EMSReady` / `EMSDelegate` ilə AJAX-safe olsun.
7. Bölmə paneli `[data-profile-section-panel]` içindədir — modallar və
   `<script src>` həmin panelin İÇİNDƏ olmalıdır.
