# EMSArena layihəsinin tam texniki və məhsul auditi

Audit tarixi: 2026-06-06  
Audit tipi: statik kod oxusu, arxitektura/security/DevOps/product review  
Əhatə: `apps`, `core`, `config`, `templates`, `static`, `tests`, `docker`, `.github/workflows`, `docs`

Bu hesabat real repo oxusu əsasında hazırlanıb. Yoxlanılan əsas ölçü: `apps/core/config/templates/static/tests` daxilində 1059 `py/html/js/css` faylı və təxminən 268k sətir kod. Tam test suite bu audit zamanı işə salınmadı; test infrastrukturu ayrıca qiymətləndirildi.

## İcraçı xülasə

EMSArena artıq sadə LMS deyil; multi-tenant təşkilat modeli, RLS, RBAC, imtahan mühərriki, live exam, fayl upload, protected media, dashboard/statistika, CI/CD və prod Docker stack olan yetkin EdTech platformasıdır.

Ümumi hazırlıq: **79%**. Bu, “controlled pilot / staging / məhdud production” üçün yaxşı səviyyədir, amma açıq public production üçün aşağıdakı P0/P1 risklər düzəlməlidir:

- Assignment submission faylları `assignments/submissions/` altında saxlanır, amma private media registry-də yoxdur.
- Assignment/project/lab create/edit axınında `students[]` ID-ləri birbaşa `User.objects.filter(id__in=...)` ilə götürülür; course/org membership ilə təsdiqlənmir.
- `QuestionBank.organization` hələ nullable-dır və RLS policy NULL organization bankları bütün tenantlara açıq saxlayır.
- Frontend-də 335 civarında `innerHTML`/HTML injection pattern-i var; bəziləri escape edir, bəziləri server və ya data attribute məzmununa güvənir.
- Production-da practical/coding exam və supervision söndürülüb; bu təhlükəsizdir, amma məhsul və marketinq vədi üçün real boşluqdur.

## 1. Overall Project Architecture - 82%

Güclü tərəflər:

- Django apps ayrımı geniş və məntiqlidir: `accounts`, `organizations`, `courses`, `exams`, `live_exam`, `assignments`, `projects`, `labs`, `notifications`, `appeals`, `audit`, `ai_assistant`, `blog`, `contact`.
- `exams` modulunda domain/service ayrımı görünür: `apps/exams/domain/*`, `apps/exams/services/*`, `apps/exams/views/student/*`, `apps/exams/views/teacher/*`.
- `config/settings/base.py` middleware düzülüşü yaxşıdır: request id, metrics, security headers, CSP, admin security, request queue, org middleware, suspended org middleware (`config/settings/base.py:44-64`).
- ASGI/WebSocket tək entrypoint-lə qurulub və `AllowedHostsOriginValidator(AuthMiddlewareStack(...))` istifadə edir (`config/asgi.py:30-38`).
- `docs/tenant-isolation-checklist.md`, `docs/deployment.md`, `docs/RLS_BYPASS_AUDIT.md` kimi daxili arxitektura sənədləri var.

Zəif tərəflər:

- Bəzi view faylları çox böyüyüb və biznes qaydaları view qatında qalır: `apps/assignments/views/crud.py`, `apps/projects/views/crud.py`, `apps/labs/views/crud.py`, `apps/accounts/services/statistics_selectors.py`.
- Eyni pattern-lər assignment/project/lab arasında təkrarlanır: assigned students, group resolution, notification dispatch.
- `live_exam` geriyə uyğunluq səbəbilə bəzi modellərdə integer/JSON referens saxlayır (`apps/live_exam/models.py:53-63`, `apps/live_exam/models.py:175-181`).

Tövsiyə:

- Assignment/project/lab üçün ortaq `task_assignment_core` service-ləri yaradın.
- Böyük view-ləri form/service/selector qatlarına bölün.
- “tenant-safe assignment resolver” kimi tək utility yazın və bütün create/edit axınlarında istifadə edin.

## 2. Multi-Tenant Architecture - 86%

Güclü tərəflər:

- `OrganizationMiddleware` aktiv təşkilatı session/membership əsasında tapır, request context-ə qoyur və PostgreSQL RLS GUC-lərini set/reset edir (`apps/organizations/middleware.py`, `core/rls.py`).
- `core/tenancy.py` fallback org restore və `scoped_by_organization()` pattern-i ilə fail-closed yanaşma verir.
- RLS policy-ləri genişdir: organization, course, exam, assignment M2M, exam answer, proctoring, notification, question bank, appeals cədvəllərinə qədər gedir (`apps/organizations/migrations/0003_rls_policies.py`, `0004_expand_rls_scope.py`, `0005_notification_org_fk_rls.py`, `0007_rls_question_bank_appeals.py`).
- `FORCE ROW LEVEL SECURITY` tətbiq edilir və app DB user-in superuser olmaması sənədləşdirilib (`apps/organizations/migrations/0003_rls_policies.py:25-31`).
- Course/exam/student list view-lərində tenant-scope helper-lər geniş istifadə olunur: `apps/courses/views/_helpers.py`, `apps/exams/views/shared/tenant.py`, `apps/assignments/views/_helpers.py`, `apps/projects/views/_helpers.py`, `apps/labs/views/_helpers.py`.

Risklər:

- `QuestionBank.organization` nullable-dır (`apps/exams/domain/question_bank.py:72-81`), RLS isə `organization_id IS NULL` bankları global göstərir (`apps/organizations/migrations/0007_rls_question_bank_appeals.py:7-21`, `:50-51`, `:66-79`).
- Assignment/project/lab-da manual POST ilə başqa tenantdan user ID göndərmək mümkündür; M2M RLS tətbiq olunsa da application-level validation səhvdir (`apps/assignments/views/crud.py:82-85`, `:194-196`; `apps/projects/views/crud.py:81-84`, `:193-195`; `apps/labs/views/crud.py:78-80`, `:180-182`).
- Superadmin bypass-lar lazımdır, amma bu axınlar auditlə ciddi izlənməlidir.

Tövsiyə:

- `QuestionBank.organization` backfill edin, sonra `null=False` və fail-closed RLS policy tətbiq edin.
- Bütün student assignment-ləri yalnız `CourseMembership(course=..., role="student")` və active org membership əsasında resolve edilsin.
- Multi-tenant smoke test-lərə “manual POST foreign user id” case-ləri əlavə edin.

## 3. Authentication and Authorization - 78%

Güclü tərəflər:

- OTP-lər plain saxlanmır; `EmailOTP` salted HMAC və `constant_time_compare` istifadə edir (`apps/accounts/models.py`).
- Production admin URL default `/admin/` deyil; `ADMIN_URL_PREFIX` `/admin/` olarsa error atır (`config/settings/production.py:228-241`).
- Admin 2FA production-da məcburidir (`config/settings/production.py:238-241`).
- `organizations.permissions` permission string-ləri və role hierarchy verir; legacy function-based decorators `ImproperlyConfigured` ilə bloklanıb (`apps/organizations/decorators.py`).
- Organization approval/suspension superadmin axını var (`apps/accounts/views/superadmin.py:108-223`).

Zəif tərəflər:

- Hələ də `request.user.is_teacher_or_above`, owner check və course author pattern-ləri permission string-lərin yanında yaşayır (`apps/assignments/views/crud.py`, `apps/projects/views/crud.py`, `apps/labs/views/crud.py`, `apps/exams/services/access_policy.py:7-19`).
- Role cache/legacy `UserProfile.role` konsepti source-of-truth Membership ilə yanaşı qalır; comment bunun denormalized cache olduğunu bildirir, amma tətbiq boyu tam təmizlənməyib.
- Assistant/delegated role kimi incə səlahiyyət modelləri owner-only view-lərdə bloklana bilər.

Tövsiyə:

- View-lərdə `is_teacher_or_above` əvəzinə `request_has_permission(request, "...")` standartını məcburi edin.
- “permission matrix regression tests” yazın: owner, org admin, teacher, assistant, student, cross-tenant, suspended org.
- Denormalized profile role yalnız UI cache kimi qalsın; authorization qərarları Membership/Role üzərindən verilsin.

## 4. Security Analysis - 74%

Güclü tərəflər:

- CSRF middleware aktivdir (`config/settings/base.py:55`), cookie secure flags production-da aktivdir (`config/settings/production.py:262-292`).
- CSP var, `script-src` üçün nonce istifadə olunur, `unsafe-inline` script-də yoxdur (`config/settings/base.py:546-595`).
- Rate limit-lər login, OTP, live exam, WebSocket, AI üçün konfiqurasiya olunub (`config/settings/base.py:174-192`).
- Upload validation güclüdür: `core/upload_security.py` blocked extension/MIME, random filename və ZIP guard verir; submission upload extension/size validation `apps/task_submission_core/uploads.py` içindədir.
- Protected media path traversal-a qarşı `safe_join` istifadə edir və private prefix registry ilə deny-by-default işləyir (`core/media_views.py:313-350`, `:362-402`).
- WebSocket connection host/player token ilə yoxlanır və rate-limit edilir (`apps/live_exam/auth.py:150-176`, `apps/live_exam/consumers.py:109-139`, `:175-213`, `:220-261`).
- `.env` və secret fayllar `.gitignore`-dadır (`.gitignore:4-11`, `:131-146`); `git ls-files` yalnız `.env.example` göstərdi.

Kritik/zəif tərəflər:

- Assignment upload faylları `assignments/submissions/` altında saxlanır (`apps/assignments/models.py:350-363`), amma `core/media_views.py` private prefix-lərdə bu path yoxdur (`core/media_views.py:58-66`, `:313-321`). Bu, fayl URL-i bilinəndə auth olmadan oxunma riski yaradır.
- `innerHTML` istifadə sayı çoxdur: auditdə 335 HTML injection pattern tapıldı. Nümunələr: exam title data attribute ilə `innerHTML` (`apps/accounts/static/accounts/js/profile.js:1794-1803`), server-returned modal HTML (`apps/courses/static/courses/js/create_course_modal.js:205-264`), assignment modal dynamic list (`apps/assignments/templates/assignments/partials/_assignment_modals.html:258-330`), AI markdown summary (`apps/accounts/static/accounts/js/statistics.js:455-478`, `:536-614`).
- Production `docker-compose.prod.yml` `METRICS_ALLOW_ANONYMOUS` defaultunu true edir (`docker-compose.prod.yml:185`); nginx bunu private network-lə məhdudlaşdırır (`docker/nginx/nginx.conf:132-152`), amma qeyri-standart deploy-da riskdir.
- Public Piston defaultu local/base üçün qalır (`config/settings/base.py:524-531`); production-da disabled olsa da re-enable üçün self-hosted sandbox şərtdir.

Tövsiyə:

- Assignment media prefix-i dərhal protected registry-yə əlavə edin və owner/teacher/org checker yazın.
- DOMPurify və ya Trusted Types planı qurun; `textContent`/DOM API-yə mərhələli keçin.
- Metrics-i app-level superuser/IP token ilə qoruyun; nginx-ə güvəni tək defense etməyin.
- Practical/coding exam üçün public Piston yox, isolated self-hosted runner və resource quota tətbiq edin.

## 5. Exam Module Analysis - 84%

Güclü tərəflər:

- Exam domain çox genişdir: test/written/coding, access policy, attempts, answers, files, proctoring, question bank, appeals.
- Student start/take axınları tenant-scoped exam və `exam.can_user_start()` ilə işləyir (`apps/exams/views/student/attempts.py`).
- Attempt start-da Redis/cache lock və concurrency gate var (`apps/exams/services/attempts.py`).
- Result calculation delivered answers əsasında aparılır; arbitrary POST question IDs-dən qaçılır (`apps/exams/services/result_calculation.py`).
- Written exam review anonymity üçün token/salt yanaşması mövcuddur.
- Answer file upload validation və autosave limitləri var.

Zəif tərəflər:

- Practical/coding exam production-da söndürülüb (`config/settings/production.py:222-226`, `docker-compose.prod.yml:204-210`), yəni feature kodda var, amma prod-ready deyil.
- Attempt uniqueness DB səviyyəsində tam möhkəm deyil: active attempt/attempt_number üçün partial/unique constraint əlavə olunmalıdır.
- `QuestionBlock` order və `ExamQuestion` order kimi sahələrdə duplicate order DB constraint-ləri görünmür.
- `grade_exam_answer` service səviyyəsində score max limitini özü enforce etmir; caller-lərə güvənir.

Tövsiyə:

- `UniqueConstraint(exam, user, attempt_number)` və active-status partial unique constraint əlavə edin.
- Coding runtime üçün Docker/seccomp/cgroup/network-off runner və queue isolation yazılmadan production re-enable etməyin.
- Question bank nullable org debt-ni həll edin.

## 6. Live Exam / Real-Time System - 78%

Güclü tərəflər:

- PIN 10 simvoldur, unambiguous alphabet və yüksək entropy ilə generate olunur (`apps/live_exam/models.py:10-23`).
- Player token Django signing ilə 6 saatlıq max-age və client_id bağlaması saxlayır (`apps/live_exam/auth.py:49-81`, `:119-138`).
- Host/player WebSocket auth ayrıdır; host-only group və players group ayrılıb (`apps/live_exam/consumers.py:204-213`, `apps/live_exam/transport.py:82-95`).
- Player-lərə reveal zamanı per-player full results göndərilmir; host payload və player payload ayrıdır (`apps/live_exam/transport.py:205-283`).
- Answer save `transaction.atomic()` və `select_for_update()` ilə session/player lock edir (`apps/live_exam/scoring.py:134-244`).
- Join, reaction, WS connect/message/answer rate-limit var (`apps/live_exam/views/player.py:381-423`, `:465-480`, `:740-754`; `apps/live_exam/consumers.py:114-127`, `:220-261`).
- Test coverage genişdir: `apps/live_exam/tests/test_consumers.py`, `test_views.py`, `test_round_scenario.py`, `tests/integration/test_live_exam_security.py`.

Zəif tərəflər:

- `LiveSession.current_question_id`, `LiveAnswer.question_id`, `choice_id`, `choice_ids` integer/JSON kimi saxlanır, FK deyil (`apps/live_exam/models.py:53-63`, `:175-181`). Bu uzunmüddətli referential integrity və cleanup riskidir.
- Lobby/player identity semi-anonimdir; tələbə analytics-i real user ilə bağlanmır.
- High-scale live exam üçün Redis channel layer, Daphne threads, DB row locks və nginx timeout-ları load test-lə təsdiqlənməlidir.

Tövsiyə:

- `LiveQuestionSnapshot` və ya FK-backed snapshot model əlavə edin.
- LivePlayer-i optional authenticated user və ya signed roster ilə bağlama seçimi yaradın.
- 100/500/1000 concurrent player load test nəticələrini release gate edin.

## 7. Course and Learning Management - 80%

Güclü tərəflər:

- `Course` organization FK ilə non-null tenant modeldir və save zamanı org tələb edir.
- Course membership, group, student enrollment view-ləri əsasən tenant-scoped helper-lərdən istifadə edir.
- Course dashboard assignment/project/lab/exam modallarını birləşdirir.
- Assignment, project və lab modulları ayrı apps kimi saxlanıb; notification integration var.
- Course membership add axını profile organization ilə filter edir (`apps/courses/views/membership.py`).

Zəif tərəflər:

- Assignment/project/lab student assignment-ləri manual ID path-də course membership ilə məhdudlaşmır.
- Assignment submission faylları JSON payload kimi saxlanır; file ownership/access check DB query-ləri üçün çətinləşir.
- Assignment/project/lab logic çox oxşardır, amma ayrıca implementasiyalar drift yaradır.

Tövsiyə:

- `CourseStudentResolver` service yaradın və bütün task assignment-ləri ona bağlayın.
- Submission files üçün relational model və ya ən azı protected media checker-lə indexable owner lookup qurun.
- Assignment/project/lab üçün ortaq Task base service və tests.

## 8. Dashboard and Statistics - 72%

Güclü tərəflər:

- `apps/accounts/services/statistics_selectors.py` role-aware aggregate layer kimi yazılıb və N+1-dən qaçmaq üçün aggregation/values istifadə edir (`:1-12`, `:74-283`, `:291-541`, `:549-769`, `:777-944`).
- Student, teacher, org admin, superadmin statistikaları ayrıdır.
- Unsupported metrics açıq sənədləşdirilib (`apps/accounts/services/statistics_selectors.py:979-1016`).
- AI summary payload kəsilir və prompt bloat azaldılır (`apps/accounts/services/statistics_selectors.py:952-972`).

Zəif tərəflər:

- Live exam user-level analytics zəifdir, çünki `LivePlayer` user FK saxlamır (`apps/accounts/services/statistics_selectors.py:182-186`).
- Business metrics yoxdur: aktiv tenant, retention, conversion, paid plan, cohort, churn, org health score.
- Dashboard query-lərində bəzi loop-lar hələ query sayını artıra bilər: teacher dashboard at-risk loop (`apps/accounts/views/dashboard/teacher.py:62-72`), superadmin org comparison loop (`apps/accounts/services/statistics_selectors.py:872-912`).
- AI summary frontend custom markdown renderer ilə `innerHTML` istifadə edir (`apps/accounts/static/accounts/js/statistics.js:477-478`).

Tövsiyə:

- Daily analytics fact table və event tracking əlavə edin.
- Live exam player identity-ni optional user ilə bağlayın.
- Dashboard query-ləri üçün query-count tests və cache layer qurun.

## 9. Database and Models - 76%

Güclü tərəflər:

- Əsas domain modellərində organization FK və indexes var: `Course`, `Exam`, `SupervisionIncident`, `Membership`, `InAppNotification`.
- RLS migration-ları geniş və sənədlidir.
- `EmailOTP` kimi security-sensitive model-lərdə hash/attempt/expiry pattern yaxşıdır.
- `LivePlayer` üçün `UniqueConstraint(session, client_id)` var (`apps/live_exam/models.py:143-145`).
- `ExamAnswer` üçün `(attempt, question)` unique var.

Zəif tərəflər:

- `QuestionBank.organization` nullable və global RLS branch ilə risklidir.
- `Membership.unique_together(user, organization, role, scope_unit)` nullable `scope_unit` ilə PostgreSQL-də duplicate NULL kombinasiyalarına imkan verə bilər.
- `AcademicPeriod.clean()` overlap yoxlayır, amma `save()` `full_clean()` çağırmır; DB-level exclusion/constraint yoxdur.
- Live exam question/choice references FK deyil.
- Assignment submission files JSON-dadır.
- Exam attempt active uniqueness DB səviyyəsində yoxdur.

Tövsiyə:

- Nullable tenant sahələrini backfill + `null=False` edin.
- `UniqueConstraint(..., nulls_distinct=False)` və conditional unique constraints əlavə edin.
- Check constraints: max_attempts >= 1, score ranges, date order, question order uniqueness.

## 10. API and Backend Logic - 75%

Güclü tərəflər:

- API v1 route mövcuddur (`config/urls.py:78-82`) və live exam API ayrıca namespace-dədir.
- Views-lərdə tenant helper-lər və services getdikcə artır.
- Error handler-lər custom və stack trace exposure-u azaldır (`core/views.py:168-194`).
- Health/metrics endpoint-ləri var (`core/views.py:22-144`).

Zəif tərəflər:

- Platform hələ əsasən server-rendered HTML view-lərə bağlıdır; public/partner API strategiyası zəifdir.
- DRF/serializer contract çox geniş tətbiq olunmayıb.
- Validation view-lərdə təkrarlanır və bəzi yerlərdə service-level invariant yoxdur.
- Assignment/project/lab create/edit kodu oxşar və riskli təkrardır.

Tövsiyə:

- Core flows üçün service API contract-ları yazın: create assignment, assign students, submit task, grade task, start attempt.
- API v1 üçün explicit serializers, pagination, permissions və OpenAPI schema əlavə edin.
- “No raw User.objects from POST IDs” lint/test qaydası qoyun.

## 11. Frontend / UI / UX - 73%

Güclü tərəflər:

- Multi-language UI var: Azərbaycan dili default, `az/en/ru/tr` pattern-i live exam copy-lərində də görünür (`apps/live_exam/views/player.py:63-183`, `apps/live_exam/session_settings.py:13-15`).
- Student/teacher/admin flows üçün çoxlu template və modal mövcuddur.
- Live exam UX zəngindir: PIN entry, QR, avatar, lobby, reaction, leaderboard, theme/settings.
- Chart/statistics frontend var.

Zəif tərəflər:

- Frontend parçaları böyükdür və template içi JS çoxdur.
- `innerHTML` geniş istifadə olunur; bəzi yerlər escape edir, amma pattern ümumi XSS riskini artırır.
- Accessibility audit görünmür: keyboard navigation, focus trap, aria-live, color contrast test-ləri formal deyil.
- CSS/JS build system və component abstraction zəif görünür; server-rendered partial-lar çoxdur.

Tövsiyə:

- DOMPurify və ya server-trusted partial boundary tətbiq edin.
- Common modal/table/chart komponentləri yaradın.
- Playwright accessibility smoke və keyboard-flow tests əlavə edin.

## 12. Performance - 76%

Güclü tərəflər:

- Redis cache, channels və Celery konfiqurasiya olunub.
- Session engine cached_db və session activity write throttling production-da qurulub (`config/settings/production.py:280-287`).
- RequestQueueMiddleware unsafe methods üçün concurrency limit verir (`config/settings/base.py`).
- Nginx static/media serving və X-Accel-Redirect ilə protected media performanslıdır (`docker/nginx/nginx.conf:79-130`).
- PgBouncer session pooling var və RLS GUC-ləri nəzərə alınıb (`docker-compose.prod.yml:52-82`).

Zəif tərəflər:

- Dashboard və statistics bəzi loop-larda N+1/loop query riskinə malikdir.
- AI, OCR, coding runtime kimi ağır işlər sync request path-ə düşərsə latency artır.
- Live exam row locks və broadcast traffic real load altında sübut edilməlidir.
- DB indexes yaxşıdır, amma bəzi compound indexes org/status/date üçün artırılmalıdır.

Tövsiyə:

- Query count tests əlavə edin.
- Ağır AI/OCR/grading işlərini Celery/queue ilə ayırın.
- K6/Locust live exam scenario-ları release gate olsun.

## 13. DevOps and Deployment - 82%

Güclü tərəflər:

- Production settings environment variable tələb edir: `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS` boş ola bilməz (`config/settings/production.py:211-260`).
- HTTPS, secure cookies, HSTS, Sentry PII off, JSON logging və sensitive masking var (`config/settings/production.py:262-292`, `:373-440`).
- Docker prod image digest-pinned və non-root user ilə işləyir (`docker/Dockerfile.prod:1-7`, `:70-108`).
- Docker stack PostgreSQL, PgBouncer, Redis, app, Celery, nginx ilə ayrılıb (`docker-compose.prod.yml`).
- Nginx direct private media access-i bloklayır və `/internal_media/` internal istifadə edir (`docker/nginx/nginx.conf:88-130`).
- CI orchestrator lint, unit tests, build, security, secret scan, docker build, Trivy, prod smoke, e2e smoke işlədir (`.github/workflows/ci.yml:58-143`).
- Security workflow pip-audit, Bandit və Django deploy check edir (`.github/workflows/_security.yml:64-120`).
- Gitleaks secret scan var (`.github/workflows/_secret-scan.yml:35-46`).

Zəif tərəflər:

- CI-də Docker-dependent jobs final gate-də advisory kimi qalır; core merge block etmir (`.github/workflows/ci.yml:187-207`).
- Deploy workflow root SSH və hardcoded host ilə gedir (`.github/workflows/ci.yml:210-228`).
- `docker-compose.prod.yml` default `METRICS_ALLOW_ANONYMOUS=true` verir; nginx internal allowlist-dən asılıdır.
- Backup/restore, migration rollback, disaster recovery, IaC və secrets manager strategiyası tam görünmür.

Tövsiyə:

- Root SSH əvəzinə dedicated deploy user + forced command + least privilege.
- Docker smoke/container scan production branch-də blocking olsun.
- Managed secrets, DB backup restore drill və release checklist əlavə edin.

## 14. Code Quality - 76%

Güclü tərəflər:

- Naming ümumən oxunaqlıdır.
- Security-sensitive yerlərdə comment-lər niyyəti izah edir.
- Domain/service ayrımı xüsusən exams/live_exam tərəfdə inkişaf edib.
- Characterization tests refactor zamanı davranışı qorumaq üçün yaxşı işarədir.

Zəif tərəflər:

- Böyük fayllar çoxdur: `statistics_selectors.py`, `apps/exams/tests/test_views.py`, live exam tests/views, profile JS.
- Legacy role compatibility kodu hələ çox yerdə qalır.
- Assignment/project/lab duplication real bug-lara səbəb olur.
- JSON field-lar sürətli inkişaf üçün rahatdır, amma invariant və query-ləri zəiflədir.

Tövsiyə:

- Refactor planı: əvvəl service extraction, sonra view slim-down, sonra model constraints.
- Security-critical helper-lərə unit tests + property tests.
- `rg` qaydaları və pre-commit: raw `User.objects.filter(id__in=request.POST...)`, unsafe `innerHTML`, missing tenant filters.

## 15. Testing and QA - 80%

Güclü tərəflər:

- Test faylları çoxdur: auditdə 488 test/init faylı göründü; əsas test faylları 80+ civarındadır.
- Unit/integration/e2e/load test qatları var: `apps/*/tests`, `tests/integration`, `tests/e2e`, `tests/load/locustfile.py`.
- Tenant isolation, RLS, media access, upload security, live exam security, RBAC testləri mövcuddur.
- CI pytest-i PostgreSQL və Redis ilə işlədir, coverage report yaradır və `--cov-fail-under=60` qoyur (`.github/workflows/_unit-tests.yml:105-124`).

Zəif tərəflər:

- Coverage threshold 60% aşağıdır.
- Frontend unit/a11y tests görünmür.
- Assignment media private prefix bug üçün test yoxdur; `core/tests/test_media_views.py` private prefixes assignment-i əhatə etmir.
- Cross-tenant manual POST foreign user ID case-ləri assignment/project/lab create/edit üçün görünmür.
- Docker-dependent smoke/e2e advisory qalır.

Tövsiyə:

- Security-critical coverage threshold-u ayrıca yüksək edin.
- Yeni P0 testlər: assignment media unauthorized, foreign student ID assignment blocked, nullable question bank leak blocked.
- Playwright ilə modal, keyboard və XSS regression tests.

## 16. Product and Business Potential - 78%

Güclü tərəflər:

- Azərbaycan bazarı üçün localization güclüdür: default dil Azərbaycan dilidir, live exam copy-ləri `az/en/ru/tr` saxlayır.
- Universitet, məktəb, kurs mərkəzi və fərdi müəllim multi-tenant modeli bazara uyğundur.
- Canlı imtahan, dashboard, AI summary/grading, upload/proctoring ideyaları rəqabət üstünlüyü yaradır.
- Organization approval/suspension və role hierarchy B2B idarəetmə üçün lazımlıdır.

Zəif tərəflər:

- Billing/subscription/plan limits yoxdur.
- Tenant onboarding, invoice, trial, quota, payment, usage dashboard görünmür.
- Enterprise features: SSO/SAML/OIDC, audit export, data retention policy, DPA/privacy consent, admin activity export yetərli deyil.
- Practical/coding exam production-da söndürülüb; STEM/code education satış vədi üçün limitdir.

Tövsiyə:

- “School/Course Center/University/Individual” planları və quota modeli qurun.
- Azərbaycan bazarı üçün sertifikat, attendance, parent access, offline/low-bandwidth mode və WhatsApp/Telegram notification inteqrasiyası düşünülə bilər.
- Ən əvvəl security P0-ları düzəldib 3-5 pilot təşkilatda ölçülən rollout edin.

## 17. Critical Issues

### 1. Assignment submission files private deyil

- Risk level: **Critical**
- Affected files/modules: `apps/assignments/models.py:350-363`, `core/media_views.py:58-66`, `core/media_views.py:313-321`, `docker/nginx/nginx.conf:106-121`
- Why it matters: Student submission faylları şəxsi/tədris məlumatıdır. `assignments/submissions/` protected media registry-də olmadığından URL bilinəndə auth/ownership yoxlaması tətbiq olunmur.
- Recommended fix: `assignments/submissions/` prefix-ni `_PRIVATE_PREFIXES` və `_ACCESS_CHECKERS`-ə əlavə edin. `Submission` owner, assignment course owner və teacher-level org membership üçün checker yazın. Anonymous/cross-org/owner/teacher testləri əlavə edin.

### 2. POST ilə cross-tenant student assignment riski

- Risk level: **High**
- Affected files/modules: `apps/assignments/views/crud.py:82-85`, `:194-196`; `apps/projects/views/crud.py:81-84`, `:193-195`; `apps/labs/views/crud.py:78-80`, `:180-182`
- Why it matters: Teacher manual POST ilə başqa tenantdan user ID göndərə bilər. UI search endpoint-ləri scoped olsa da server-side create/edit path raw user IDs-ə güvənir.
- Recommended fix: `students[]` yalnız `CourseMembership.objects.filter(course=course, role="student", user_id__in=...)` üzərindən resolve edilsin. Mismatch varsa 400/403 verilsin və audit log yazılsın.

### 3. Nullable QuestionBank tenant leak

- Risk level: **High**
- Affected files/modules: `apps/exams/domain/question_bank.py:72-81`, `apps/organizations/migrations/0007_rls_question_bank_appeals.py:7-21`, `:50-79`
- Why it matters: NULL organization question bank-lar RLS-də bütün tenantlara görünə bilər. Bu exam content/IP leak riskidir.
- Recommended fix: Backfill organization, `organization=null=False`, indexes `organization,is_active,is_shared`, RLS `organization_id IS NULL` branch-ni silin.

### 4. DOM XSS və HTML injection borcu

- Risk level: **High**
- Affected files/modules: 335 `innerHTML`/HTML injection pattern; nümunələr `apps/accounts/static/accounts/js/profile.js:1802`, `apps/courses/static/courses/js/create_course_modal.js:205-264`, `apps/accounts/static/accounts/js/statistics.js:477-478`, `apps/assignments/templates/assignments/partials/_assignment_modals.html:258-330`
- Why it matters: CSP kömək edir, amma DOM-based XSS CSP-ni bypass edə bilər, xüsusən server-returned HTML, data attribute və AI markdown render-də.
- Recommended fix: `textContent`/DOM API, sanitized HTML boundary, DOMPurify, Trusted Types planı və XSS regression tests.

### 5. Practical/coding exam production-ready deyil

- Risk level: **High**
- Affected files/modules: `config/settings/production.py:222-226`, `docker-compose.prod.yml:204-210`, `config/settings/base.py:522-531`, `apps/exams/services/coding_runtime.py`
- Why it matters: Feature kodda var, amma production-da disabled. Re-enable edilsə public Piston/privacy/resource exhaustion riski yarana bilər.
- Recommended fix: Self-hosted sandbox, network isolation, CPU/memory/time/file limits, queue, per-user concurrency və audit logging.

### 6. RBAC consistency debt

- Risk level: **Medium**
- Affected files/modules: `apps/assignments/views/crud.py`, `apps/projects/views/crud.py`, `apps/labs/views/crud.py`, `apps/exams/services/access_policy.py:7-19`
- Why it matters: Permission string sistemi var, amma legacy/global role checks behavior drift və delegated role bloklanması yaradır.
- Recommended fix: Canonical `request_has_permission()` standardı və permission matrix tests.

### 7. Live exam referential integrity debt

- Risk level: **Medium**
- Affected files/modules: `apps/live_exam/models.py:53-63`, `:175-181`
- Why it matters: Question/choice ID-ləri FK olmadığından deleted/changed questions üçün stale data, cleanup və analytics problemi yarana bilər.
- Recommended fix: Snapshot/FK model və migration plan.

### 8. Deploy/security operations hardening

- Risk level: **Medium**
- Affected files/modules: `.github/workflows/ci.yml:187-228`, `docker-compose.prod.yml:185`, `docker/nginx/nginx.conf:132-152`
- Why it matters: Docker-dependent jobs advisory qalır, deploy root SSH ilədir, metrics protection nginx topology-dən asılıdır.
- Recommended fix: Dedicated deploy user, blocking smoke/container scan, app-level metrics auth/IP allowlist.

## 18. Improvement Roadmap

### Immediate fixes: 1-2 həftə

- Assignment media privacy bug-ını düzəlt: prefix + checker + tests.
- Assignment/project/lab raw student ID assignment bug-ını düzəlt.
- QuestionBank NULL org audit: neçə row var, hansı user/org-a aiddir, backfill planı.
- XSS hot spots: `profile.js:1802`, AI summary markdown, server-returned modal HTML üçün sanitizer.
- Metrics defaultunu production compose-da false edin və Prometheus üçün explicit internal env qoyun.
- Security tests: unauthorized assignment media, cross-tenant manual POST, question bank leak.

### Short-term improvements: 1 ay

- Permission string standardization: assignment/project/lab/exam host flows.
- DB constraints: attempt uniqueness, date/order/check constraints, Membership NULL uniqueness.
- Query-count tests dashboard/statistics üçün.
- Frontend safe HTML helper və lint rule.
- Release checklist: migrations, backup, rollback, smoke, security scan.

### Medium-term improvements: 3 ay

- Practical/coding exam self-hosted sandbox və Celery queue.
- Live exam snapshot model və user-linked player option.
- Analytics event model: daily active users, org activity, retention, course/exam engagement.
- API v1 contract: serializers, OpenAPI, versioning, token/auth strategy.
- Accessibility and mobile UX audit.

### Long-term improvements: 6+ ay

- SaaS billing, plans, quotas, trial, invoices, usage limits.
- Enterprise SSO/SAML/OIDC, audit export, data retention controls.
- Multi-region/object storage strategy, disaster recovery drills.
- Advanced market features: certificates, attendance, parent portal, low-bandwidth/offline mode.
- AI governance: consent, redaction, cost budget enforcement, model audit logs.

## 19. Final Percentage Summary Table

| Section | Score % |
|---|---:|
| Architecture | 82% |
| Multi-Tenant System | 86% |
| Authentication / Authorization | 78% |
| Security | 74% |
| Exam Module | 84% |
| Live Exam | 78% |
| Course / LMS | 80% |
| Dashboard / Statistics | 72% |
| Database / Models | 76% |
| API / Backend Logic | 75% |
| UI/UX | 73% |
| Performance | 76% |
| DevOps | 82% |
| Code Quality | 76% |
| Testing | 80% |
| Business Readiness | 78% |

## 20. Final Overall Score

**Overall EMSArena readiness: 79%**

Bu rəqəm “platform ciddi formalaşıb, amma public production üçün P0/P1 security və data isolation borcları var” deməkdir. Kod bazası yetkinliyə yaxındır; problem əsasən son 20%-lik hardening, consistency və productization mərhələsindədir.

## 21. Final Conclusion

EMSArena production-a yaxındır, amma bu gün açıq public production üçün “tam hazırdır” deməzdim. **Controlled pilot** üçün uyğundur; **geniş production** üçün əvvəlcə assignment media access, cross-tenant student assignment, nullable question bank RLS və DOM XSS borcu düzəlməlidir.

Ən güclü hissələr:

- Multi-tenant düşüncə və RLS tətbiqi.
- Exam və live exam feature dərinliyi.
- Production settings, Docker/Nginx/CI/security scanning səviyyəsi.
- Azərbaycan bazarı üçün dil və təhsil axınlarına uyğun məhsul istiqaməti.

Ən zəif hissələr:

- Bəzi security-critical path-lərdə application-level validation boşluğu.
- Frontend safe HTML discipline.
- Legacy RBAC qarışığı.
- SaaS/business operations: billing, plan, quota, onboarding, enterprise compliance.

İlk düzəldilməli olanlar:

1. `assignments/submissions/` private media access.
2. Assignment/project/lab `students[]` server-side scoping.
3. QuestionBank organization backfill və fail-closed RLS.
4. High-risk `innerHTML` nöqtələri.
5. Practical/coding exam üçün production sandbox planı.

Azərbaycan bazarında uğur üçün EMSArena-nın ən böyük üstünlüyü lokal dil, təşkilat əsaslı model və real classroom/live exam təcrübəsidir. Bunu daha güclü etmək üçün təhlükəsiz pilotlar, sadə onboarding, yerli ödəniş/billing, sertifikat/attendance və aşağı internet şəraitində işləyən mobil-first təcrübə əlavə olunmalıdır.
