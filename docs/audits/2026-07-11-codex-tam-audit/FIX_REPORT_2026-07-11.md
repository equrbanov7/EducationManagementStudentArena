# Codex tam auditi — düzəliş hesabatı (2026-07-11)

**Audit:** [EMSArena_End_to_End_Audit_AZ_2026-07-11.md](./EMSArena_End_to_End_Audit_AZ_2026-07-11.md)
**Düzəlişlərin icra tarixi:** 2026-07-11 (audit ilə eyni gün)
**Bütün tapıntılar kod üzərində yenidən yoxlanıb təsdiqlənəndən sonra düzəldilib.**

## Yoxlama nəticələri

| Gate | Nəticə |
|---|---|
| SQLite suite (`-m "not postgres"`, e2e xaric) | **2821 passed, 4 skipped** |
| Postgres-marked suite (real Postgres 16 konteynerində) | **60 passed** (yeni 6 RLS gap testi daxil) |
| black / isort / flake8 (məhsul kodu) | Keçdi |
| Modul ölçü / boundary / worker-atomic gate-ləri | Keçdi |
| `makemigrations --check` + fresh Postgres-də tam `migrate` | Keçdi |
| `nginx -t` (yeni konfiq) | Keçdi |
| `docker compose -f docker-compose.prod.yml config -q` | Keçdi |

## Bağlanan tapıntılar

### EXAM-P0-01 — tətbiq superuser DB rolu ilə qoşulurdu → HƏLL EDİLDİ (deploy addımı tələb edir)

- `scripts/provision-app-db-role.sh` — mövcud DB-də `LOGIN NOSUPERUSER NOBYPASSRLS` tətbiq rolu yaradır (idempotent); DML grant-ları + gələcək cədvəllər üçün `ALTER DEFAULT PRIVILEGES`.
- `docker/postgres-init/10-create-app-role.sh` — fresh volume üçün eyni rol (initdb).
- `docker-compose.prod.yml` — `DATABASE_URL` artıq `APP_DATABASE_USER`-dən qurulur (boşdursa köhnə davranışa düşür); miqrasiyalar `MIGRATION_DATABASE_URL` (owner) üzərindən (`docker/release.sh`).
- `apps/organizations/checks.py` — system check `organizations.W011/E011`: qoşulan rol `rolsuper OR rolbypassrls` olduqda xəbərdarlıq/deploy bloku. Sərtlik `EMS_DB_ROLE_ENFORCE=warn|error|off`.
- **Sübut:** throwaway Postgres 16-da rol yaradıldı; app rolu ilə tenant-suz `SELECT count(*) FROM exams_exam` = 0, tenant A ilə yalnız A-nın imtahanı, cross-tenant `UPDATE` = 0 sətir; superuser hamısını görür (köhnə risk). Check hər iki rolla yoxlanıb.
- **Production addımı (operator):** `APP_DATABASE_USER/APP_DATABASE_PASSWORD` təyin et, provision skriptini işə sal, stack-i yenidən qaldır, sonra `EMS_DB_ROLE_ENFORCE=error` et.

### EXAM-P0-02 — 14 exam cədvəli RLS-siz idi → HƏLL EDİLDİ

- `apps/organizations/migrations/0017_rls_exam_gap_tables.py`: coding (4 cədvəl), `examstudentpin`, `studentexamattemptgrant`, `examsupervisionconfig`, `supervisionincident`, `questionsubmission` (+M2M), `exam_excluded_users`, `examroom_invigilators`, `examroomsession_staff`, `studentgroup_subjects` — hamısına `USING + WITH CHECK` + `FORCE RLS`.
- `exams_aiconfiguration` (tenant FK yoxdur) və `trial_exams_trialexamrequest` (public lead) bilərəkdən əhatə edilmir.
- **Testlər:** `apps/organizations/tests/test_rls.py::TestRLSExamGapTables` — 6 yeni test (SELECT izolyasiya, tenant-suz 0 sətir, cross-tenant INSERT rədd).

### EXAM-P0-03 — cavab tarixçəsi dəyişməz deyildi → QİSMƏN HƏLL (seçim dondurma)

- `ExamAnswer.selected_option_ids_snapshot` (miqrasiya exams 0045): seçilmiş variant ID-ləri cavab yazılan anda dondurulur; variant redaktəsi (delete/recreate) M2M through sətirlərini silsə belə bal `question_snapshot` + bu sahədən bərpa olunur.
- Yazma yolu: `apps/exams/views/student/attempts.py::_save_test_answer_if_changed`; oxu: `result_calculation.py` + nəticə səhifəsi verdikti.
- **Test:** `test_frozen_selection_survives_option_delete_recreate` — variantlar silinib yenidən yaradılandan sonra bal byte-for-byte eyni qalır.
- **Qalan iş (Dalğa 2):** sual mətni/media/variant mətni snapshot-u və render-in tarixi vəziyyətdən aparılması.

### EXAM-P0-04 — manual grading client max balına etibar edirdi → HƏLL EDİLDİ

- `teacher_check_attempt` POST artıq `max_points_*` qəbul etmir; maksimum bal cavabın çatdırılma snapshot-undan (yoxdursa canlı sualdan) gəlir; bal `[0, max]`-a clamp olunur; grading POST heç vaxt `ExamQuestion.points`-i dəyişmir.
- `ai_grade_answer` endpoint-i də client `max_points`-i ignor edir.
- UI: max bal inputu readonly; JS "score > max → max-ı qaldır" davranışı tərsinə çevrilib (bal max-a clamp).
- **Testlər:** 4 yeni/yenilənmiş regression testi (ignor, clamp, snapshot-bound, AI-ignor).

### EXAM-P0-05 — nəticə/düzgün cavab erkən açılırdı → HƏLL EDİLDİ

- `_exam_answers_release_locked`: imtahanın `end_datetime`-ı var və hələ keçməyibsə düzgün variantlar, per-sual verdiktlər və yazılı "ideal cavab" GİZLİ qalır (bal görünür — "score only" siyasəti). `end_datetime`-sız (məşq) imtahanlara toxunulmur.
- Tələbəyə izahat banneri (`notice_answers_release_locked`, 4 dildə).
- **Testlər:** `StudentExamResultVisibilityWindowTest` — 4 yeni test.
- **Qeyd:** yoxlanılmamış yazılı cəhdin nəticə səhifəsi qəsdən açıq qalır ("müəllim yoxlaması gözlənilir" statusu ilə öz cavabını görmək) — sızıntı yaradan "ideal cavab" bloku artıq pəncərə bağlanana qədər gizlidir.

### EXAM-P1-02 / P1-03 — archive/delete start guard + public exclusion bypass → HƏLL EDİLDİ

- `can_user_see` / `can_user_start`: arxivlənmiş və soft-silinmiş imtahan görünmür/başladılmır (birbaşa URL daxil); exclusion siyahısı public imtahanlara da şamildir və aktiv cəhdin davamından üstündür.
- **Testlər:** `ExamAccessControlTest` — 4 yeni test.

### PROJ-P0 (proxy/XFF spoof) → HƏLL EDİLDİ

- **Qeyd (2026-07-11, düzəlişin 2-ci iterasiyası):** bu deployment Cloudflare istifadə ETMİR — nginx-dəki bütün CF inteqrasiyası (CF-Connecting-IP rate-limit açarı, X-Forwarded-Proto map-i, cf_ray log sahələri) köhnə sistemin qalığı idi və tamamilə silindi.
- Nginx artıq EDGE kimi konfiqurasiya olunub: client-in göndərdiyi `X-Forwarded-For` / `X-Forwarded-Proto` başlıqları HEÇ VAXT oxunmur — XFF `$remote_addr` ilə **overwrite** edilir, protokol nginx-in öz `$scheme`-indən gəlir (TLS burada terminasiya olunur).
- Rate/connection limit açarı `$binary_remote_addr` (spoof edilə bilməyən TCP peer).
- Django tərəfdəki `get_client_ip` (birinci element) və `exam_center_gate.get_client_ip` (son element) hər ikisi təhlükəsizdir — başlıqda həmişə tək, nginx-ə məxsus dəyər var.
- `csrf_failure` logundan və settings şərhlərindən CF-Ray qalıqları çıxarıldı.
- **Server yoxlaması (növbəti çıxışda):** `remote_deploy.sh`-dakı `EMSARENA-CF-WEB` iptables zənciri serverdə varsa köhnə CF allowlist-idir — CF olmadığı üçün nəzərdən keçirilib silinməlidir (funksiya zəncir yoxdursa no-op-dur, deploy-u pozmur).

## Əlavə təmizlik

- 924 macOS "keep both" duplikatı (` 2` suffiksli fayl/qovluq, hamısı byte-identik təsdiqlənib) silindi — bunlar lokal `makemigrations --check`-i "Conflicting migrations" ilə sındırırdı.
- `docs/` qovluğu kateqoriyalara bölündü; audit reyestri yaradıldı (bax [docs/audits/README.md](../README.md)).

## İkinci dalğa düzəlişləri (2026-07-11, davam)

### PROJ-P1 #5 — CI-də docker/scan/smoke/E2E advisory idi → BLOCKING edildi

- `.github/workflows/ci.yml` (ci-success): `docker-build`, `container-scan` (Trivy), `prod-smoke`, `e2e-smoke` job-larının uğursuzluğu artıq `ci-success`-i və deməli `deploy-production`-u bloklayır (əvvəl yalnız `::warning`). Docker Hub keçici problemləri üçün həll — job-u yenidən işə salmaq.

### EXAM-P1-10 — supervision incident payload etibarsız idi → HƏLL EDİLDİ

- `apps/exams/views/teacher/supervision/monitor.py::log_incident_api`: `event_type` allowlist-i, `metadata` sərt sanitizasiyası (`_sanitize_incident_metadata` — açar sayı ≤20, dəyər uzunluğu ≤500, yalnız yastı primitivlər, nested dict string-ə endirilir) və per-attempt rate limit (`60/1m`, 429 + Retry-After).
- **Testlər:** `apps/exams/tests/test_supervision_incident_api.py` — 5 test (invalid event, nested/oversize sanitizasiya, key cap, rate limit, non-dict).

### EXAM-P1-13 — coding final submit idempotent deyildi → HƏLL EDİLDİ

- `CodingSubmission` üzərində partial unique constraint (miqrasiya exams 0046): `(attempt, question)` üçün `is_final=True AND attempt IS NOT NULL` — bir final-dan çoxu ola bilməz.
- `create_final_submission` yenidən finalizasiyada köhnə finalı demote edir (constraint retry-də pozulmur).
- `coding_submit` `select_for_update` ilə attempt sətrini kilidləyir və `is_finished`-i kilid daxilində yenidən yoxlayır — paralel ikinci submit idempotent qayıdır.
- **Testlər:** `test_coding_exam.py` — `test_submit_after_finish_is_idempotent`, `test_create_final_submission_demotes_prior_final`.

### EXAM-P1-12 — live exam late-join → HƏLL EDİLDİ

- **Boşluq təsdiqləndi:** `apps/live_exam/views/player/join.py::live_join_enter` yalnız `is_locked` yoxlayırdı, `state`-i yox — oyun `question`/`reveal`/`finished` vəziyyətində belə yeni oyunçu qoşula bilirdi.
- Row-lock daxilində state guard əlavə edildi: `STATE_FINISHED`-də heç kim qoşula bilmir; lobby-dən çıxdıqda yalnız artıq qəbul edilmiş oyunçu (reconnect) davam edə bilir, yeni oyunçu yox. `session_finished` mesajı 4 dildə.
- **Testlər:** `test_views.py` — 3 yeni test (late new-join blok, finished blok, mid-game reconnect icazəli).

### İkinci dalğa yoxlama nəticəsi

- SQLite suite: **2831 passed, 4 skipped** (birinci dalğadan +10 test).
- Postgres-marked suite: **40 passed** (real Postgres 16); yeni `exams 0046` partial unique index və `exams 0045` snapshot sütunu fresh migrate-də təsdiqləndi.
- black/isort/flake8, module-size gate, `makemigrations --check`, `manage.py check` — hamısı təmiz.

## Açıq qalan (auditdən növbəti prioritetlər)

Qalan bəndlər üçün auditin III hissəsinə bax: server-side per-question timer (P1-04), autosave OCC/idempotency (P1-06), PIN lifecycle (P1-08), immutable image promotion + rollback, off-site backup + restore drill, load/WS capacity sübutu, business observability/SLO.
