# EMSArena yenidən-audit hesabatı — 2026-07-11 düzəlişlərinin verifikasiyası

**Tarix:** 2026-07-11  
**Audit hədəfi:** `Develop` — `9867761ffb50460b4f02f5752791222105050919`  
**Əvvəlki audit:** [EMSArena_End_to_End_Audit_AZ_2026-07-11.md](./EMSArena_End_to_End_Audit_AZ_2026-07-11.md)  
**Yoxlanılan düzəliş iddiaları:** [FIX_REPORT_2026-07-11.md](./FIX_REPORT_2026-07-11.md)  
**Tapşırıq:** [REAUDIT_PROMPT.md](./REAUDIT_PROMPT.md)

---

## 1. İcraçı hökmü

Qısa cavab: **işlərin əhəmiyyətli hissəsi görülüb, lakin ümumilikdə tam həll
olunmayıb**. Test sayı və CI keyfiyyəti yaxşılaşıb; seçilmiş variant snapshot-u,
manual grading-də client `max_points` etibarının silinməsi, `q_present` data-loss
guard-ı və live-exam late-join bloklaması real kod və testlə təsdiqlənir. Ancaq
production-readiness-i bloklayan tenant, deployment, proxy və akademik data
bütövlüyü problemləri qalır.

20 düzəliş iddiası qrupu üzrə nəticə:

| Nəticə | Say | İzah |
|---|---:|---|
| **TƏSDİQLƏNDİ** | 2 | Live late-join və `q_present` guard bütöv qəbul meyarı ilə işləyir |
| **Dar iddia təsdiqləndi, əsas tapıntı NATAMAM** | 2 | Manual grading client-tamper və vaxtadək correct-answer gizlətməsi |
| **NATAMAM** | 15 | Kod skeleti/test var, amma bypass, inteqrasiya, DB invariantı və ya deploy yoxdur |
| **REQRESSİYA** | 1 | Nginx “Cloudflare yoxdur” fərziyyəsi faktiki public topologiyaya ziddir |

### 1.1. Yenilənmiş yekun göstəricilər

| Göstərici | Əvvəl | İndi | Hökm |
|---|---:|---:|---|
| **İmtahan sistemi balı** | 43/100 | **54/100** | Müsbət irəliləyiş, amma high-stakes imtahan üçün kifayət deyil |
| **Ümumi çəkili layihə balı** | 58/100 | **66/100** | Kod/test yetkinliyi yaxşıdır, əməliyyat və tenant sərhədi release-i bloklayır |
| **İmtahan production-readiness** | NO-GO | **NO-GO** | P0 tenant/access/history/release/performance gate-ləri açıqdır |
| **Ümumi production-readiness** | NO-GO | **NO-GO** | Public availability, deploy drift, RLS və proxy uyğunsuzluğu var |

Balın daha çox artmamasının səbəbi görülən işi kiçiltmək deyil: bal yalnız mənbə
kodunu yox, **faktiki işləyən rolu, tətbiq edilmiş migration-u, real şəbəkə
topologiyasını, adversarial bypass nəticəsini və ölçülmüş capacity-ni** nəzərə
alır.

### 1.2. Ən kritik beş nəticə

1. `Develop` düzəlişləri `main`-də deyil. `origin/main...origin/Develop` fərqi
   `15 5`, məzmun fərqi isə `130 files changed, 10865 insertions, 214 deletions`-dir.
   Cari uğurlu [Develop CI run-u](https://github.com/equrbanov7/EducationManagementStudentArena/actions/runs/29156491754)
   deploy etməyib; son [main deploy run-u](https://github.com/equrbanov7/EducationManagementStudentArena/actions/runs/29144387323)
   bu düzəlişlərdən əvvəlki məzmunu deploy edib.
2. Lokal `docker-compose.prod.yml` runtime-ında app rolu hələ
   `rolsuper=True`, `rolbypassrls=True`-dir; DB `exams=0043`,
   `organizations=0016` səviyyəsindədir. Host mənbəsi müvafiq olaraq `0047` və
   `0019`, işləyən image inventory-si isə daha köhnə `0029` və `0014`-dür.
3. Fresh Postgres-də yeni RLS migration-ları cədvəl səviyyəsində işləyir, amma
   cross-tenant M2M əlaqə INSERT bypass-ı var: tenant A submission-u tenant B
   student group-u ilə bağlana bilir.
4. `take_exam` endpoint-i aktiv cəhd üçün vahid access policy-ni yenidən
   yoxlamır. Arxivlənmiş imtahan və sonradan exclusion siyahısına salınmış
   tələbə direct URL ilə HTTP 200 alır.
5. 2026-07-11 19:12 `+04` müşahidəsində
   [public health endpoint](https://emsarena.com/health/) Cloudflare-dən
   `HTTP 522` qaytardı. Eyni zamanda branch Nginx konfiqurasiyası “Cloudflare
   yoxdur, Nginx birbaşa edge-dir” fərziyyəsi ilə yazılıb. Bu həm availability,
   həm də real client IP/rate-limit/exam-center allowlist üçün release-bloklayıcı
   topologiya ziddiyyətidir.

---

## 2. Audit metodu və sübut sərhədi

Nəticələr üç ayrı qat üzrə qiymətləndirilib; bunlar bir-biri ilə qarışdırılmır:

1. **Mənbə kodu:** `Develop` HEAD `9867761f`.
2. **Lokal production-compose runtime:** bu workstation-da hazırda işləyən
   compose stack. Bu, remote production serverinin özü kimi təqdim edilmir.
3. **İctimai endpoint:** yalnız HTTPS/DNS/HTTP səviyyəsində müşahidə; remote
   serverə SSH girişi edilməyib.

Statusların mənası:

- **TƏSDİQLƏNDİ:** kod, test və bypass sınağı qəbul meyarını bütöv keçir.
- **NATAMAM:** müsbət dəyişiklik var, amma bypass, wiring, DB invariantı,
  migration/deploy və ya əməliyyat sübutu çatmır.
- **REQRESSİYA:** düzəliş əvvəlki riskdən fərqli yeni risk yaradır və ya real
  topologiya ilə uyğun deyil.

Təhlükəsizlik yoxlaması Django/Python və browser JavaScript trust-boundary
prinsipləri ilə aparıldı: tenant konteksti, raw DB rolu, çox-FK-li RLS policy,
proxy header-ləri, DOM sink-ləri, localStorage, CSP və server-authoritative
imtahan invariantları ayrıca yoxlanıldı.

---

## 3. İcra edilmiş yoxlamalar

### 3.1. Lokal regressiya və keyfiyyət gate-ləri

| Yoxlama | Faktiki nəticə |
|---|---|
| SQLite, E2E xaric, `-m "not postgres"` | **2858 passed, 4 skipped, 68 deselected — 74.27s** |
| Exam hədəfli düzəliş testləri | **46 passed — 1.36s** |
| `manage.py check` | **0 issue** |
| `makemigrations --check --dry-run` | **No changes detected** |
| Module size ratchet | **Keçdi** |
| Module dependency boundary | **Keçdi** |
| `black --check .` | **1832 files unchanged** |
| `isort --check-only --profile black .` | **Keçdi** |
| `flake8 .` | **Keçdi** |
| `nginx -t` | **Keçdi** |

Bu nəticələr ciddi müsbət göstəricidir, lakin aşağıdakı adversarial bypass-lar
göstərir ki, yaşıl suite “bütün invariantlar bağlandı” demək deyil.

### 3.2. Postgres/RLS və CI

| Yoxlama | Faktiki nəticə |
|---|---|
| Fresh Postgres 16 hədəfli RLS/audit yoxlaması | **14/14 passed** |
| GitHub RLS transaction-pool job | **68 passed, 2862 deselected — 36.32s** |
| Develop CI | Lint, build, py3.11/3.12, RLS, Docker build, Gitleaks, security, Trivy, prod-smoke, E2E hamısı success |
| CodeQL | [Run 29156491609](https://github.com/equrbanov7/EducationManagementStudentArena/actions/runs/29156491609) success |

### 3.3. Adversarial bypass nəticələri

```text
BYPASS_PROBE excluded_direct_take=200 archived_direct_take=200
SUPERVISION_ROOT_PROBE status=500
PIN_LIFECYCLE_PROBE expires_at=None revoked_at=None first=True second=True
cross_tenant_m2m_insert_succeeded=True
audit rows_updated=1 old_user=58 new_user=59 tamper_succeeded=True
lab max=100, grade_lab_submission(..., 150) -> score=150
lab question points=10, grade_lab_answer(..., 99) -> score=99
```

Bu probe-lar test fixture-lərində yaradılmış lokal/fresh DB datasında işlədilib;
real istifadəçi datası dəyişdirilməyib.

---

## 4. “HƏLL EDİLDİ” iddialarının status matrisi

| ID | Dar düzəlişin statusu | Əsas tapıntının statusu | Kod/test sübutu | Bypass və qalan boşluq |
|---|---|---|---|---|
| **EXAM-P0-01** non-superuser app rolu | Mexanizm işləyir | **NATAMAM** | `apps/organizations/checks.py:35-69`; `scripts/provision-app-db-role.sh:22-55`; `docker-compose.prod.yml:57-70`; throwaway rol `rolsuper=f, rolbypassrls=f` | Lokal prod-compose rolu `rolsuper=True, rolbypassrls=True`; image köhnə; check default `warn`, exception-u fail-open udur; smoke-lar superuser fallback-i test edir |
| **EXAM-P0-02** 14 exam gap cədvəli | Table-level ENABLE+FORCE RLS fresh DB-də təsdiqləndi | **NATAMAM** | `apps/organizations/migrations/0017_rls_exam_gap_tables.py`; 14 hədəfli PG testi keçdi | `exams_questionsubmission_student_groups` policy-si yalnız submission tərəfini yoxlayır; A parent + B group INSERT uğurludur. Lokal runtime-da migration tətbiq edilməyib |
| **EXAM-P0-03** seçim snapshot-u | Seçilmiş ID və bal dondurması təsdiqləndi | **NATAMAM** | `apps/exams/domain/attempts.py:369-382`; `services/result_calculation.py:101-126`; `test_answer_snapshot.py:107+` | Sual mətni, media hash-i, variant mətni/sırası snapshot deyil; result canlı `q.text`, `q.options` və M2M render edir: `templates/exams/student/exam_result.html:219-268` |
| **EXAM-P0-04** client max-points trust | **TƏSDİQLƏNDİ** | **NATAMAM** | `_answer_max_points` `views/teacher/results/_helpers.py:78-91`; POST clamp `_attempt_views.py:275-300`; AI clamp `:360-369`; tamper testləri keçir | Row lock/atomic grade event/grader identity/DB upper-bound yoxdur; birbaşa ORM və gələcək yol invariantı poza bilər |
| **EXAM-P0-05** vaxtadək correct-answer gizlətməsi | **TƏSDİQLƏNDİ** | **NATAMAM** | `views/student/results.py:54-63,148-151,215-240`; `exam_result.html:155,428`; 4 visibility testi keçir | Formal `sealed/provisional/published` state və atomik publish yoxdur; score həmişə görünür, bir-sual imtahanda cavab infer oluna bilər; `end_datetime=None` dərhal açır |
| **EXAM-P1-02/03** archive/delete/exclusion | Policy metodunda təsdiqləndi | **NATAMAM** | `domain/access_policy.py:150-203`; policy testləri keçir | `views/student/attempts.py:436-453` aktiv attempt açarkən policy-ni çağırmır; archived və excluded direct `take_exam` HTTP 200 |
| **EXAM-P1-10** supervision payload | Allowlist/sanitization/throttle əsas testləri keçir | **NATAMAM** | `views/teacher/supervision/monitor.py:36-102`; 5 API testi keçir | JSON root `[]` üçün `body.get` 500; body-size/schema tam deyil; `services/supervision/incidents.py:39-44` read-increment-save yarışı var |
| **EXAM-P1-12** live late-join | **TƏSDİQLƏNDİ** | **TƏSDİQLƏNDİ** | `apps/live_exam/views/player/join.py:215-233`; 3 regression testi: yeni player 403, reconnect 200, finished 403 | Bu qəbul meyarı üzrə bypass tapılmadı |
| **EXAM-P1-13** coding final idempotency | Partial unique + row lock dizaynı təsdiqləndi | **NATAMAM** | migration `exams/0046`; `views/student/coding.py:493-507`; `services/coding_runtime/submission.py:56-79` | Real paralel Postgres request testi yoxdur; migration köhnə duplicate final sətirlərini təmizləmir. Lokal preflight 0 duplicate göstərdi, amma prod data ayrıca yoxlanmalıdır |
| **PROXY-P0** XFF hardening | Təkbaşına edge Nginx üçün syntax/doğruluq təsdiqləndi | **REQRESSİYA** | `docker/nginx/nginx.conf:4-7,18-19,118-123,175-179`; `nginx -t` keçir | Public DNS/HTTP Cloudflare göstərir. Deploy olunsa `$remote_addr` CF edge IP olar; client-lər eyni rate-limit/IP allowlist bucket-inə düşər. `remote_deploy.sh:159-187` CF chain-i silmir, yenidən qoşur |
| **CI-P1** blocking CI | Cari real run-da bütün job-lar success | **NATAMAM** | `.github/workflows/ci.yml:139-153` bütün əsas job-ları `needs` edir | `:203-227` yalnız `failure`-ı bloklayır; `cancelled/skipped` fail-open keçir. Branch protection API-də `main/Staging/Develop` üçün qoruma yoxdur; Develop deploy edilməyib |
| **RLS labs/projects** | 8 əsas cədvəl fresh DB-də qorunur | **NATAMAM** | `organizations/0018`; 4 RLS testi keçir | `labs_lab_allowed_students`, `labs_labassignment_assigned_questions`, `projects_project_assigned_students` RLS-sizdir; tenant kontekstsiz iki join row görünür |
| **Audit append-only** | DELETE və məzmun UPDATE-i bloklanır | **NATAMAM** | `organizations/0019`; hədəfli PG testləri keçir | Trigger `user_id`, `organization_id`, `content_type_id` dəyişməsini müqayisə etmir; `user_id` başqa user-ə UPDATE olundu. Hash-chain/WORM yoxdur; runtime-da trigger tətbiq edilməyib |
| **Grade clamp project-wide** | Assignment/project service yolu təsdiqləndi | **NATAMAM** | `apps/task_submission_core/services.py:98-153`; 36 test keçir | Lab ayrı `apps/labs/lab_grading_service.py:30-53` yoludur və clamp etmir: 150/100 və 99/10 saxlandı; DB constraint yoxdur |
| **EXAM-P1-08** PIN lifecycle | Revoked/expired verify rəddi təsdiqləndi | **NATAMAM** | `domain/student_access.py:37-72`; `services/student_pins.py:116-134`; iki test keçir | Provision `:82-96` default expiry qoymur; one-use/rotation/revoke əməliyyat axını yoxdur; eyni PIN iki dəfə qəbul edildi; revoked/expired PIN UI-də görünə bilər |
| **EXAM-P1-05** `q_present` | **TƏSDİQLƏNDİ** | **TƏSDİQLƏNDİ** | `take_exam.html:185-189`; `timers.js`; `views/student/_helpers.py:73+`; finish regression testi keçir | Disabled/absent field artıq saxlanmış cavabı silmir. Server-side per-question deadline ayrıca açıqdır |
| **EXAM-P1-17** language parity | Validator unit səviyyəsində işləyir | **NATAMAM** | `services/language_parity.py:20+`; 4 parity testi keçir | Tests-dən başqa production çağıranı yoxdur; publish/start gate-ə wire edilməyib; semantik correctness/mapping parity-si yoxdur |
| **EXAM-P1-18** appeal independence | Exam author conflict guard təsdiqləndi | **NATAMAM** | `apps/appeals/services/permissions.py:27-66`; 6 test keçir | İlkin manual grader identity Attempt-də saxlanmır; author olmayan grader öz qiymətinə baxa bilər; assignment/two-person override yoxdur |
| **EXAM-P1-15** import reaper | Stale PROCESSING -> FAILED təsdiqləndi | **NATAMAM** | `apps/exams/tasks.py:44-75`; Beat `config/settings/components/celery_cache.py:63-68`; 2 test keçir | Lease owner/token, heartbeat, retry/backoff yoxdur; köhnə worker sonradan statusu yaza bilər; upload cleanup yoxdur |
| **EXAM-P1-20** business SLI | Counter skeleti və 3 hook mövcuddur | **NATAMAM** | `apps/exams/metrics.py:17-45`; PIN, supervision, result-toggle hook-ları | `record_attempt_started/submitted/autosave` production-da çağırılmır; test yalnız no-exception yoxlayır; Prometheus exam alert-ləri yoxdur |

---

## 5. Yeni və ya əvvəlkindən daha aydın kritik tapıntılar

### 5.1. P0 — cross-FK tenant bütövlüyü RLS policy-lərində yoxlanmır

RLS-in yalnız “bu sətir hansı tenantın parent-inə bağlıdır?” sualını yoxlaması
kifayət deyil. Bir cədvəldə iki və ya daha çox tenant-daşıyan FK varsa, bütün
FK-lərin eyni tenantda olması da `WITH CHECK` ilə məcbur edilməlidir.

Faktiki bypass:

```text
tenant context = A
questionsubmission_id = A
studentgroup_id = B
raw INSERT = success
```

Əsas mənbə `organizations/0017` migration-ında M2M policy-si yalnız
`questionsubmission_id`-ni yoxlayır. Eyni pattern `studentgroup_subjects`,
`CodingSubmission` və `SupervisionIncident` üçün də audit edilməlidir.

**Risk:** cross-tenant relation corruption, yanlış auditoriya, gələcək join
sorğularında məlumat sızması və nəticə hesablamasının çirklənməsi.

**Qəbul meyarı:** hər çox-FK-li tenant cədvəli üçün A-parent/B-child INSERT və
UPDATE adversarial PG testi; həm `USING`, həm `WITH CHECK`; mümkün olduqda eyni
tenantı doğrulayan DB constraint/trigger.

### 5.2. P0 — aktiv attempt access policy bypass

Policy obyektinin düzgün olması endpoint-in düzgün olması demək deyil.
`views/student/attempts.py:436-453` attempt-i tenant queryset-dən götürür, amma
exam arxiv/exclusion siyasətini yenidən qiymətləndirmir.

**Faktiki nəticə:** excluded və archived aktiv attempt üçün HTTP 200.

**Qəbul meyarı:** `take_exam`, autosave, finish, coding autosave/submit və media
endpoint-lərində eyni server-side `assert_attempt_access()` guard; status
dəyişəndən sonra bütün direct URL-lər 403/404; Postgres və browser E2E.

### 5.3. P0 — proxy topologiyası kodla infrastruktur arasında ziddir

Branch Nginx config-i TCP peer-i həqiqi client sayır. Public domen isə
Cloudflare arxasındadır (`server: cloudflare`, `cf-ray`, `522`). Repo daxilində
də ziddiyyət var:

- `docker-compose.prod.yml:12-15` Cloudflare qeyd edir;
- deployment sənədləri origin lockdown-u təsvir edir;
- `remote_deploy.sh:159-187` `EMSARENA-CF-WEB` zəncirini saxlayır;
- yeni `nginx.conf:4-7` isə Cloudflare olmadığını qəbul edir.

**Risk:** rate-limit bütün CF edge istifadəçilərini birləşdirə bilər;
exam-center IP/MAC/ARP allowlist yanlış IP görər; incident/audit attribution
dəqiqliyini itirər.

**Qəbul meyarı:** əvvəl topologiya qərarı. Cloudflare qalırsa yalnız rəsmi CF IP
range-lərindən gələn origin trafiki qəbul et, `real_ip_header CF-Connecting-IP`
və `set_real_ip_from` allowlist tətbiq et; origin birbaşa açıq olmamalıdır.
Cloudflare çıxarılırsa DNS/TLS/firewall və health müşahidəsi ilə bunu faktiki
təsdiqlə. Hər iki halda spoof testi və real client IP smoke tələb olunur.

### 5.4. P0 — tarixi imtahan nəticəsi hələ canlı müəllif datasından asılıdır

Yeni `selected_option_ids_snapshot` balın bəzi redaktələrdən qorunmasına kömək
edir. Lakin hüquqi/akademik audit üçün “tələbəyə həmin anda nə göstərilmişdi?”
sualının cavabı tam dondurulmayıb. Result səhifəsi canlı sual mətni, media və
variantları render edir.

**Qəbul meyarı:** delivered question text, locale, points, answer mode, option
ID+text+order+correctness, media object/hash, randomization order və rubric
snapshot-u; result/appeal yalnız snapshot-dan render; müəllif redaktəsi keçmiş
attempt-i dəyişməməlidir.

### 5.5. P1 — audit log “append-only” olsa da attribution dəyişdirilə bilir

`organizations/0019` trigger-i FK `SET NULL` üçün istisna vermək məqsədi ilə
`user_id`, `organization_id`, `content_type_id` dəyişikliklərini bütövlükdə
müqayisədən çıxarıb. Nəticədə user A attribution-u user B-yə dəyişdirildi.

**Qəbul meyarı:** yalnız `OLD.fk IS NOT NULL AND NEW.fk IS NULL` olan real FK
delete vəziyyətinə icazə; başqa bütün dəyişikliklər reject; old/new row hash,
external append-only sink və retention/restore sübutu.

### 5.6. P1 — lab grading public service DB maksimumunu poza bilir

Teacher view clamp etsə də domain servis birbaşa çağırıldıqda `score=150` / max
100 və answer `score=99` / points 10 saxlanır. Bu, UI validasiyasının sistem
invariantı olmadığını göstərir.

**Qəbul meyarı:** bütün giriş yolları ortaq grading service; transaction və row
lock; `[0,max]` server clamp; model/DB invariantı; service və adversarial ORM
testləri.

### 5.7. P1 — browser DOM injection sink-i

`apps/accounts/templates/accounts/profile/sections/_assigned_exams.html:84`
teacher-controlled exam title-ni `data-exam-title` atributuna verir. Browser
atribut entity-lərini decode etdikdən sonra
`apps/accounts/static/accounts/js/profile/ui.js:309-316` həmin dəyəri string
concatenation ilə `innerHTML`-ə yazır.

Mövcud nonce-based CSP (`config/settings/components/csp.py:15-64`) inline script
və event-handler istismarını ciddi məhdudlaşdırır; buna görə bu auditdə risk
**P1/Medium** qiymətləndirilir, birbaşa code-execution sübutu kimi təqdim
edilmir. Buna baxmayaraq HTML/DOM injection və gələcək CSP zəifləməsinə bağlı
stored-XSS riski qalır.

**Düzəliş:** `<strong>` node-u DOM API ilə yarat, title üçün yalnız
`textContent` istifadə et; regression browser testi əlavə et.

Müsbət qeyd: coding preview `postMessage('*')` istifadə etsə də receiver
`event.source === previewFrame.contentWindow` və `runId` yoxlayır
(`coding_exam/preview.js:226-235`); bu auditdə həmin yol üçün origin-spoof
tapıntısı açılmadı.

---

## 6. Bilərəkdən açıq qalan imtahan riskləri

| ID/sahə | Cari risk | Prioritet | Sübut |
|---|---|---|---|
| Formal lifecycle/state machine | `lifecycle_status` draft/scheduled/active/archived ilə məhduddur; review/approved/sealed/published/appeal_closed yoxdur | P0 | `apps/exams/domain/exam_definition.py:303-321` |
| Server per-question timer | Client timer reload/clock manipulation qarşısında authoritative deyil | P0 high-stakes | `take_exam` JS timer yolu; server deadline modeli yoxdur |
| Autosave OCC | İki tab/stale request son yazanı qalib edir; server revision/ETag/409 yoxdur | P0/P1 | yalnız in-tab `answerRevision`; server müqayisəsi yoxdur |
| Plaintext draft | Cavab draft-ı browser `localStorage`-də plaintext qalır | P1 | `static/exams/js/take_exam/draft.js:144,180` |
| Ümumi access code plaintext | Exam access code modeldə plaintext saxlanır və birbaşa müqayisə olunur | P1 | `domain/exam_definition.py:199-204`; `access_policy.py:241-244` |
| Client proctor telemetry | Client event-ləri spoof/suppress edilə bilər; sübut kimi güclü deyil | P1 | supervision client->API modeli |
| Sync OCR fallback | Worker gecikəndə request thread ağır OCR/AI işini inline görə bilər | P1 reliability | `views/teacher/extract_jobs.py:39-70` |
| Hard delete CASCADE | Exam hard delete tarixi əlaqələri silə bilər | P1 | `views/teacher/exams/actions.py:330-357` |
| Coding sandbox backpressure | Prod-da disabled; aktivləşəndə semaphore/queue/memory limiti sübutu yoxdur | P1 before enable | `coding_runtime/execution.py:243-268`; `subprocess.run(capture_output=True)` tam output-u əvvəl memory-yə yığır |
| Result release | `end_datetime`-a bağlı görünüş guard-ı var, formal publication transaction-u yoxdur | P0 | `views/student/results.py:54-63` |

---

## 7. Layihə-wide açıq risklər

### 7.1. Tenant/RLS

- `labs_lab_allowed_students`, `labs_labassignment_assigned_questions`,
  `projects_project_assigned_students` join cədvəlləri RLS-sizdir.
- `accounts_userprofile`, `ai_assistant_aiassistantlog`, `audit_auditlog`
  bilərəkdən `0018` scope-dan kənarda qalıb.
- Model/cədvəl inventarı ilə policy coverage-i avtomatik diff edən fail-closed CI
  gate yoxdur.
- Lokal runtime app rolu superuser/BYPASSRLS olduğu üçün mövcud policy-lər belə
  faktiki enforcement yaratmır.

### 7.2. Release və deployment

- `Develop` fix-ləri `main` və public deployment-da deyil.
- CI `cancelled/skipped` nəticələrini uğursuz saymır.
- Branch protection yoxdur.
- Test edilən image digest-i staging-dən prod-a immutable promote edilmir;
  serverdə source rsync + rebuild edilir.
- Migration backward-compat/rollback və preflight data cleanup gate-i tam deyil.
- Public health 2026-07-11 19:12 `+04` zamanı `522` idi.

### 7.3. Data integrity və audit

- Assignment/project clamp yolu yaxşılaşıb, lab clamp/concurrency açıqdır.
- Grade event, original grader identity və DB-level upper bound universal deyil.
- Audit log attribution dəyişdirilə bilir və cryptographic tamper-evidence/WORM
  yoxdur.
- Off-site backup, media+DB consistent restore drill, ölçülmüş RPO/RTO yoxdur.

### 7.4. Frontend, privacy və keyfiyyət gate-ləri

- Plaintext exam draft localStorage-dədir.
- Yuxarıda qeyd edilən `innerHTML` exam-title sink-i qalır.
- JS lint/unit/type gate-i və sistemli a11y `axe/pa11y` gate-i yoxdur.
- Privacy/retention schedule və silinmə siyasətinin icra sübutu yoxdur.
- CSP güclü müsbət tərəfdir: `script-src` nonce-based, `unsafe-inline/eval`
  yoxdur; `object-src none`, `frame-ancestors none` tətbiq edilir.

---

## 8. Performans — yalnız faktiki ölçülmüş nəticə

### 8.1. İcra edilən bounded liveness smoke

**Alət:** k6 v2.0.0, Apple M3 Pro 11 CPU / 19.3 GB host RAM, Docker Desktop
11 CPU / 8.22 GB limit.  
**Hədəf:** lokal `http://127.0.0.1` -> Nginx -> tək Daphne.  
**Profil:** 100 sabit VU x 10 saniyə; hər iterasiya `GET /ping/`,
`GET /health/`, `sleep(1)`.  
**Vacib:** bu, PIN/start/autosave/submit/result/WebSocket axını deyil.

| Metrik | Faktiki nəticə |
|---|---:|
| HTTP request | 1,872 |
| Throughput | 169.421 req/s |
| Error rate | 0.00% |
| Ümumi HTTP median / p95 / p99 / max | 43.41ms / 135.74ms / 1.07s / 1.08s |
| `/ping/` median / p95 / p99 | 45.85ms / 136.35ms / 1.07s |
| `/health/` median / p95 / p99 | 42.37ms / 131.57ms / 145.5ms |

`/health/` DB+Redis yoxlayır. Bununla yalnız lokal liveness/toolchain-in qısa
yükdə cavab verdiyi sübut olunur. Stale image, superuser DB rolu, qısa müddət
və exam flow-un olmaması səbəbindən bu nəticə **capacity və ya production
readiness sübutu deyil**.

Tam command və xam summary
[FAZA4_BASELINE_RESULTS.md](../../performance/FAZA4_BASELINE_RESULTS.md)-də
saxlanılıb.

### 8.2. Ölçülməyən və buna görə açıq qalan gate-lər

| Tələb | Status | Niyə nəticə verilmədi |
|---|---|---|
| Real exam HTTP 100 VU x 30 dəq | **ÖLÇÜLMƏYİB** | Representative staging və unikal credential datası yoxdur; lokal image yeni düzəliş deyil |
| 500 VU x 15 dəq | **ÖLÇÜLMƏYİB** | Eyni səbəb; yanlış stack rəqəmi baseline kimi qəbul edilə bilməz |
| 1000 VU spike | **ÖLÇÜLMƏYİB** | Public production-a icazəsiz stress tətbiq edilmədi; təhlükəsiz staging yoxdur |
| 1 saat soak | **ÖLÇÜLMƏYİB** | Telemetriya və representative stack hazır deyil |
| 1000 WebSocket + reconnect storm | **ÖLÇÜLMƏYİB** | Repo-da həqiqi WS harness yoxdur; Locust HTTP approximation-dır |
| DB/PgBouncer/Redis/Celery telemetry | **ÖLÇÜLMƏYİB** | PgBouncer/Redis/Celery exporter və queue-lag metrikası yoxdur |
| RLS `EXPLAIN ANALYZE` | **ÖLÇÜLMƏYİB** | Representative cardinality dataset və saxlanmış plan artefaktı yoxdur |
| Coding sandbox backpressure | **ÖLÇÜLMƏYİB** | Prod profile-da coding disabled, Piston işləmir, semaphore/queue metric yoxdur |

### 8.3. Harness və query-budget boşluqları

- `k6/student-exam-flow-test.js:21-29` default 1 VU/1 iteration-dır; coding
  branch yalnız autosave edir və çıxır (`:64-90`); normal branch-də submit
  optional-dır, PIN/result GET tam deyil (`:93-118`).
- `k6/final-exam-center-test.js:5-17` PIN -> gate -> waiting -> begin ilə
  dayanır və HTTP-only olduğunu açıq deyir.
- Credential-lər modulo ilə təkrar istifadə olunur; 500/1000 unikal user
  datası yoxdur.
- `docs/operations/FAZA4_STAGING_RUNBOOK.md:71-82,97-100` env prefix-i yalnız
  ilk shell command-a tətbiq edir; sonrakı script-lər default 1 VU-ya düşə
  bilər.
- `tests/load/locustfile.py:241-247` WebSocket-i HTTP ilə approximation edir,
  bəzi 429/400 cavabları success sayır və eyni username-i paylaşır.
- Yalnız attach-summary query budget testi aşkarlandı və keçir:
  `apps/exams/tests/test_services.py:1985-2045` — **1 passed**. `exam_result`,
  teacher grading, registrar list və accounts hub üçün budget yoxdur.
- `apps/registrar/finals.py:292-303` enrollment başına
  `compute_final_result` çağırır; N+1 şübhəsi ölçülmüş gate olmayana qədər
  açıqdır.
- `docs/performance/FAZA2_3B_TRANSACTION_POOLING.md`-dəki “500 VU p95~60s,
  29% error” iddiası üçün xam log/environment artefaktı tapılmadı; hazırda
  authoritative baseline sayıla bilməz.

---

## 9. Yenilənmiş imtahan sistemi balı — 54/100

| Meyar | Çəki | Qazanılan | Əsas səbəb |
|---|---:|---:|---|
| Arxitektura və modul sərhədi | 5 | 4 | Paket/fasad və ratchet gate-ləri güclüdür |
| Data modeli və tarixçə | 7 | 4 | Selection/score snapshot yaxşılaşıb, delivered history yarımçıqdır |
| Business lifecycle | 6 | 2 | Formal review/publish/close state machine yoxdur |
| Tətbiq təhlükəsizliyi | 7 | 3 | Client grading trust və dar release leak bağlanıb; access/proxy açıqdır |
| Tenant izolyasiyası | 7 | 3 | RLS migration irəliləyişdir; cross-FK bypass və runtime superuser qalır |
| RBAC | 5 | 3 | Mərkəzi model yaxşı, duty separation/original grader zəifdir |
| PIN/access control | 4 | 2 | Hash/throttle/revoke check var, real lifecycle yoxdur |
| Attempt etibarlılığı | 6 | 5 | Row lock/constraint və q_present yaxşılaşıb; active-access bypass qalır |
| Timer | 5 | 1 | Total timer yaxşı, per-question server deadline yoxdur |
| Autosave/recovery | 4 | 2 | Lokal recovery var, server OCC yoxdur |
| Submission | 4 | 3 | q_present və coding guard irəliləyişdir; real concurrency sübutu çatmır |
| Grading/integrity | 6 | 3 | Client clamp var; DB bound, grade event və full snapshot yoxdur |
| Çoxdillilik | 3 | 2 | Validator var, publish gate-ə qoşulmayıb |
| Apellyasiya | 4 | 3 | Author conflict var, original grader/two-person rule yoxdur |
| Performans | 4 | 1 | Yalnız bounded liveness smoke ölçülüb |
| Scalability | 4 | 1 | Topologiya var, real HTTP/WS capacity sübutu yoxdur |
| UX | 4 | 3 | Əsas flow-lar yaxşıdır; PIN/release davranış boşluqları qalır |
| Accessibility | 3 | 2 | Base pattern yaxşı, avtomatik dərin gate yoxdur |
| Test keyfiyyəti | 6 | 5 | 2858 test + PG/CI güclüdür; adversarial boşluqlar tapıldı |
| Observability | 3 | 2 | Counter skeleti var, wiring/dashboard/alert yarımçıqdır |
| Production readiness | 3 | 0 | P0 və deploy/capacity gate-ləri açıqdır |
| **Cəmi** | **100** | **54** | |

---

## 10. Yenilənmiş ümumi çəkili layihə balı — 66/100

| Kateqoriya | Çəki | Alt bal | Çəkili töhfə |
|---|---:|---:|---:|
| Arxitektura və maintainability | 12% | 86/100 | 10.32 |
| DB və tenant izolyasiyası | 14% | 58/100 | 8.12 |
| Auth və RBAC | 10% | 78/100 | 7.80 |
| Təhlükəsizlik və privacy | 12% | 52/100 | 6.24 |
| Business/data integrity | 12% | 67/100 | 8.04 |
| Performans və scalability | 10% | 32/100 | 3.20 |
| Frontend/UX/accessibility | 8% | 69/100 | 5.52 |
| Test və QA | 10% | 91/100 | 9.10 |
| DevOps və release | 7% | 65/100 | 4.55 |
| Observability/BCP/sənədlər | 5% | 56/100 | 2.80 |
| **Cəmi** | **100%** |  | **65.69 -> 66/100** |

Ən böyük real artım test/QA, RLS skeleti, client grading trust, live join,
coding idempotency və CI job əhatəsindədir. Ən zəif sahələr hələ də ölçülmüş
performans, production deployment attestasiya, full tenant coverage,
immutable academic history və BCP-dir.

---

## 11. Production-readiness qərarları

### 11.1. İmtahan sistemi

**Qərar: NO-GO.**

Real final, sertifikasiya, yüksək çəkili summativ imtahan və sərt multi-tenant
mühit üçün buraxılmamalıdır. Hazırkı kod yalnız aşağı-risk daxili demo və
synthetic pilot üçün uyğundur; o da public availability və Faza 0 deploy
problemi aradan qaldırıldıqdan sonra.

Minimum GO gate-ləri:

1. non-superuser/NOBYPASSRLS runtime attestasiya;
2. cross-FK və bütün join-table RLS adversarial testləri;
3. aktiv attempt üçün vahid access guard;
4. full delivered snapshot və formal result publication state;
5. server timer + autosave OCC;
6. grading DB invariantı, grader identity və append-only grade event;
7. 100/500/1000 HTTP, 1000 WS, soak və data-loss nəticələri;
8. backup restore drill və rollback rehearsal.

### 11.2. Ümumi layihə

**Qərar: NO-GO for unrestricted production.**

2026-07-11 19:12 `+04` public `522`, branch/deploy drift və real proxy
topologiyasının qeyri-müəyyənliyi ayrıca NO-GO üçün kifayətdir. Bunlar düzəlsə
belə tenant/audit/performance gate-ləri tamamlanmadan yalnız məhdud, aşağı-risk
pilot nəzərdən keçirilə bilər.

---

## 12. Faza-faza icra planı

### Faza 0 — availability və release həqiqəti

**Məqsəd:** hansı commit/image/schema/topologiyanın işlədiyini dəqiq və təkrar
oluna bilən etmək.

- Public `522` səbəbini aradan qaldır.
- Cloudflare qalır/çıxır qərarını sənədləşdir və Nginx/firewall/DNS-i eyni
  modelə gətir.
- `Develop`-dən seçilmiş düzəlişləri review ilə `main`-ə gətir; birbaşa bütün
  branch-i kor-koranə promote etmə, çünki `main` və `Develop` diverged-dir.
- Registry digest build/scan/promote et; runtime image digest, Git SHA və
  migration head-i health/admin endpoint və deploy logunda göstər.
- DB backup və migration preflight et.

**Exit gate:** public health 200; real client IP spoof testi; deployed SHA =
approved SHA; image digest eyni; schema heads gözlənilən; rollback command
rehearsal keçib.

### Faza 1 — tenant və DB P0 sərhədi

- Cross-FK RLS policy-lərini düzəlt.
- Üç labs/projects M2M və qalan profile/AI/audit cədvəlləri üçün explicit
  policy/əsaslandırma əlavə et.
- App rolunu provision et; `EMS_DB_ROLE_ENFORCE=error`; web/worker/beat/PgBouncer
  daxilində `current_user, rolsuper, rolbypassrls` attestasiya et.
- Audit trigger FK tamper bypass-ını bağla.
- CI prod/E2E smoke-u non-superuser app-role ilə işlətsin.

**Exit gate:** tenant context-siz 0 row; A/B SELECT/INSERT/UPDATE/DELETE bütün
həssas cədvəllərdə keçmir; multi-FK qarışdırma rədd edilir; runtime rol
`NOSUPERUSER NOBYPASSRLS`.

### Faza 2 — imtahan akademik bütövlüyü

- Vahid active-attempt access guard.
- Full delivered snapshot və snapshot-only result/appeal render.
- Formal lifecycle + `sealed/provisional/published/appeal_closed` state.
- Grading row lock, DB upper bound, original grader, grade-event ledger.
- Server-authoritative per-question deadline və autosave OCC/409 UX.

**Exit gate:** müəllif redaktəsi keçmiş nəticəni dəyişmir; excluded/archived
attempt bütün endpoint-lərdə bloklanır; iki tab stale save data itirmir;
publication active peer attempt varkən açıla bilmir.

### Faza 3 — access, background və supervision etibarlılığı

- PIN default expiry, one-use və ya siyasətlə məhdud reuse, rotation/revoke
  əməliyyat axını və UI görünürlük qaydası.
- Ümumi access code-u at-rest qoruma.
- Supervision body size + JSON schema + atomik counter.
- Coding duplicate preflight/data migration + paralel PG testi.
- Extraction lease token/owner, heartbeat, retry/backoff və file cleanup.
- Language parity publish gate; reviewer assignment/two-person override.

**Exit gate:** abuse/regression suite və browser E2E; stuck worker ownership
yarışı; PIN lifecycle audit trail; parity-siz variant publish olunmur.

### Faza 4 — performans və observability

- Representative staging: current HEAD image, current migrations,
  non-superuser app role, 1000 unikal synthetic user və real cardinality data.
- Full PIN -> start -> question -> autosave -> submit -> result k6 axını.
- 100 VU x 30 dəq, 500 VU x 15 dəq, 1000 spike, 1 saat soak.
- 1000 real WebSocket + reconnect storm.
- Exam result/grading/registrar/accounts query budget və RLS `EXPLAIN ANALYZE`.
- PgBouncer/Redis/Celery exporter, queue lag, exam business SLI dashboard/alert.

**Exit gate:** əvvəlcədən təsdiqlənmiş p95/p99/error/data-loss limitləri;
autosave/submit itkisi 0; raw k6/WS/EXPLAIN/telemetry artefaktları repoda və ya
artefakt store-da saxlanır.

### Faza 5 — BCP, release rehearsal və controlled rollout

- Off-site encrypted backup və media+DB restore drill; RPO/RTO ölç.
- Immutable rollback rehearsal; migration compatibility sınağı.
- Canary rollout, exam SLI alert-ləri və operator runbook.
- 24-72 saatlıq müşahidə, sonra məhdud pilot; yalnız pilot gate-ləri keçəndən
  sonra high-stakes qərarı.

**Exit gate:** restore və rollback faktiki keçib; alert delivery test olunub;
canary-də SLO və data-integrity invariantı pozulmayıb.

### Faza 6 — project-wide keyfiyyət və governance

- JS lint/unit/type və a11y gate.
- `innerHTML` sink-lərinin DOM-safe API-yə keçirilməsi.
- Privacy/retention/data-deletion siyasəti və hüquqi sənədlər.
- RLS coverage, query budget və model invariantı üçün ratchet gate-lər.

---

## 13. Top 10 kritik imtahan sistemi əməli

1. Aktiv attempt üçün `take/autosave/finish/coding/media` üzrə vahid server
   access guard yaradıb archived/excluded bypass-ı bağlamaq.
2. Bütün delivered sual, variant, media, sıra, rubric və locale məlumatını
   immutable snapshot etmək; result/appeal-i yalnız snapshot-dan render etmək.
3. Formal exam/result state machine və atomik publish gate qurmaq.
4. Manual grading-i transaction+row lock, DB upper-bound, original grader və
   append-only grade event ilə qorumaq.
5. Exam çox-FK/M2M cədvəllərində same-tenant `WITH CHECK` və adversarial PG
   testləri əlavə etmək.
6. Server-authoritative per-question deadline və multi-tab autosave OCC/409
   conflict UX qurmaq.
7. PIN üçün default expiry, rotation/revoke, audit və məqsədə uyğun one-use/reuse
   siyasəti; ümumi access code-u at-rest qorumaq.
8. Supervision JSON schema/body limit/atomik counter və proctor telemetry-nin
   sübut gücünü düzgün sərhədləmək.
9. Coding final duplicate preflight + real paralel Postgres testi və sandbox
   semaphore/queue/output-memory backpressure əlavə etmək.
10. Language parity-ni publish gate-ə, appeal-i original-grader/two-person
    qaydasına, business metric-ləri bütün start/submit/autosave yollarına qoşmaq.

---

## 14. Top 10 kritik layihə-wide əməli

1. Public `522` və Cloudflare/Nginx/firewall topologiya ziddiyyətini həll etmək.
2. Non-superuser app DB rolunu faktiki deploy edib web/worker/beat/PgBouncer-da
   attestasiya etmək.
3. Bütün tenant-həssas cədvəl və join-table-lər üçün fail-closed RLS coverage
   gate qurmaq.
4. `Develop`/`main` drift-i review ilə həll edib immutable image digest
   promotion və rollback yaratmaq.
5. CI-də hər required job üçün yalnız `result == success` qəbul etmək, branch
   protection və required checks aktivləşdirmək.
6. Audit attribution tamper-i bağlamaq və external tamper-evident/WORM trail
   yaratmaq.
7. Assignment/project/lab grade və attempt concurrency invariantlarını ortaq
   service + DB səviyyəsində qorumaq.
8. Off-site encrypted backup, consistent media+DB restore drill və ölçülmüş
   RPO/RTO təmin etmək.
9. Representative 100/500/1000 HTTP, 1000 WS və 1 saat soak testini raw
   artefaktlarla icra etmək.
10. PgBouncer/Redis/Celery/exam SLI observability, privacy/retention və
    JS/a11y/query-budget CI gate-lərini tamamlamaq.

---

## 15. Tövsiyə olunan dəqiq icra ardıcıllığı

1. Availability incident (`522`) və topologiya qərarı.
2. Cross-FK/M2M RLS və audit-trigger bypass kod düzəlişi.
3. Fresh PG adversarial suite + migration duplicate/preflight yoxlaması.
4. Reviewed merge/promotion; non-superuser rol və migration deploy-u.
5. Runtime DB role/schema/image/SHA/proxy attestasiya.
6. Active-attempt guard, full snapshot və grading ledger/DB invariantı.
7. Lifecycle/result publish, server timer və autosave OCC.
8. PIN/supervision/coding/reaper/parity/appeal tamamlanması.
9. Observability və representative performance mərhələsi.
10. Restore/rollback/canary rehearsal, məhdud pilot və yalnız sonra high-stakes
    production qərarı.

Bu sıra qəsdən “əvvəl deploy, sonra düzəlt” deyil: mövcud branch-də yeni RLS və
proxy riskləri tapıldığı üçün əvvəl onların kod və test gate-i bağlanmalıdır;
sonra kontrollu promotion edilməlidir.

---

## 16. Roadmap-dan sonrakı gözlənilən ballar

| Göstərici | Cari | Kritik roadmap tam və sübutla bitdikdən sonra gözlənilən |
|---|---:|---:|
| İmtahan sistemi | **54/100** | **88/100** |
| Ümumi layihə | **66/100** | **86/100** |

Bu rəqəmlər zəmanət deyil. Artım yalnız hər fazanın exit gate-i real Postgres,
browser E2E, load/WS, restore və deployed-runtime attestasiya ilə keçərsə
etibarlıdır. Təkcə yeni kod və unit test əlavə edilməsi bu gözlənilən balı
verməyəcək.

---

## 17. Son nəticə

Görülən düzəlişlər realdır və əvvəlki 43/58 vəziyyətindən daha yaxşı mühəndislik
bazası yaradıb. Xüsusən böyük yaşıl suite, RLS migration skeleti, selected
option snapshot-u, client grading tamper fix-i, live join və q_present guard
dəyərlidir.

Amma “tam həll olundu” hökmü verilə bilməz. Hazırkı release üçün dörd ayrı
bloklayıcı sinif var:

1. **faktiki deployment drift və public availability;**
2. **tenant/RLS və audit bypass-ları;**
3. **akademik history/lifecycle/access invariantlarının yarımçıq olması;**
4. **real exam/WS capacity və recovery sübutunun olmaması.**

Bu səbəbdən həm imtahan sistemi, həm də ümumi layihə üçün yekun qərar
**NO-GO** olaraq qalır.
