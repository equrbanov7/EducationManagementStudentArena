# RLS Bypass Audit (FAZA 10)

> Tarix: 2026-05-24 · Sayım yeniləməsi: 2026-09-13 (audit `access` F-13)
> Status: Analiz sənədi — kod dəyişmir. Gələcək təhlükəsizlik audit-i üçün bələdçi.

## Niyə bu sənəd var

`core.rls.bypass_rls()` / `set_rls_bypass()` PostgreSQL Row-Level Security
siyasətlərini **müvəqqəti söndürür** — yəni sorğu bütün tenant-ların sətirlərini
görür. Hər istifadə potensial cross-tenant sızıntı nöqtəsidir. Kod bazasında
**156 çağırış / 65 fayl** var (test faylları xaric; 2026-09-13, skriptlə sayılıb — aşağıya bax). Bu sənəd onları kateqoriyalaşdırır
ki, gələcəkdə hər biri qəsdən və əsaslandırılmış qalsın.

## Sayım (fayl üzrə, test xaric) — 2026-09-13 yeniləməsi

> **Mənbə:** `venv/bin/python scripts/rls_bypass_inventory.py --markdown` — cədvəl
> ƏLLƏ yazılmayıb (audit `access` 2026-09-13, F-13: 2026-05 sayımı «~85» əllə
> aparılmışdı və 164/64-ə qədər köhnəlmişdi). Sayım qaydası skriptin
> docstring-indədir (şərh/`def`/`import` sətirləri sayılmır; `_bypass_rls()`
> alias-ları sayılır). Yeni `bypass_rls` əlavə edəndə skripti yenidən işlədib
> bu bölməni əvəz edin; skript təsnif edilməmiş fayl görsə 1 ilə çıxır.

| Fayl | Çağırış | Kateqoriya |
|---|---:|---|
| `apps/exams/tasks.py` | 11 | D — Celery (sorğu konteksti yoxdur; job sətri org FK-lıdır) |
| `apps/blog/services.py` | 9 | A — qlobal blog (tenant-suz) |
| `apps/blog/views/moderator/post_management.py` | 7 | A — qlobal blog (tenant-suz) |
| `apps/exams/services/final_center/entry.py` | 7 | B — final mərkəzi PIN axını |
| `apps/notifications/services/read_state.py` | 7 | A — recipient-scoped bildiriş |
| `apps/accounts/services/view_as.py` | 5 | C — view-as (hədəf yoxlaması ilə) |
| `apps/live_exam/views/player/wait.py` | 5 | B — public PIN/token girişi |
| `apps/accounts/services/organization_requests.py` | 4 | C — üzvlük sorğusu axını |
| `apps/accounts/views/_helpers/org_sections/request_section.py` | 4 | C — superadmin / admin cross-org əməliyyatı |
| `apps/blog/signals.py` | 4 | A — qlobal blog (tenant-suz) |
| `apps/notifications/services/crud.py` | 4 | A — recipient-scoped bildiriş |
| `apps/organizations/middleware.py` | 4 | D — tenant kontekst qurma |
| `core/rls.py` | 4 | D — RLS infrastrukturunun özü (kontekst menecerləri) |
| `core/tenancy.py` | 4 | D — tenant kontekst qurma |
| `apps/accounts/views/organization/_management_flow/_invites.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/_management_flow/flow.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/requests.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/profile/view_as.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/exams/services/exam_center_gate.py` | 3 | B — imtahan mərkəzi qapısı |
| `apps/live_exam/consumers.py` | 3 | B — public PIN/token girişi |
| `apps/live_exam/scoring.py` | 3 | B — public PIN/token girişi |
| `apps/live_exam/views/player/_shared.py` | 3 | B — public PIN/token girişi |
| `apps/notifications/views.py` | 3 | A — recipient-scoped bildiriş |
| `apps/accounts/views/_helpers/org_sections/_members_registry.py` | 2 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/_management_flow/_members.py` | 2 | C — superadmin / admin cross-org əməliyyatı |
| `apps/exams/views/student/final_center.py` | 2 | B — final mərkəzi PIN axını |
| `apps/live_exam/auth.py` | 2 | B — public PIN/token girişi |
| `apps/live_exam/views/api.py` | 2 | B — public PIN/token girişi |
| `apps/live_exam/views/player/join.py` | 2 | B — public PIN/token girişi |
| `apps/notifications/management/commands/purge_notifications.py` | 2 | A — recipient-scoped bildiriş |
| `apps/registrar/management/commands/set_program_official_codes.py` | 2 | C — idarə əmrləri |
| `apps/accounts/management/commands/import_legacy_staff_positions.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/import_users_from_excel.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/provision_student_credentials.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/middleware.py` | 1 | D — ilk-giriş / sessiya qapısı |
| `apps/accounts/services/registration.py` | 1 | C — qeydiyyat (org seçimi öncəsi) |
| `apps/accounts/views/_helpers/superadmin_inspector.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/auth/login.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/invitations.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/profile/_sections/exam_rooms.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/profile/_sections/notifications.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/superadmin/exam_rooms.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/audit/views.py` | 1 | C — superadmin audit görünüşü |
| `apps/exams/consumers.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_group_demo_data.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_room_monitor_demo.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_stress_exam_journal.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_stress_test.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/student_pins.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/live_exam/cache.py` | 1 | B — public PIN/token girişi |
| `apps/monitoring/permissions.py` | 1 | C — superadmin monitorinq |
| `apps/notifications/services/profile_state.py` | 1 | A — recipient-scoped bildiriş |
| `apps/notifications/services/queries.py` | 1 | A — recipient-scoped bildiriş |
| `apps/organizations/management/commands/backfill_admin_memberships.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/create_sample_orgs.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/seed_ci_e2e_scenario.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/seed_ci_e2e_user.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/services.py` | 1 | C — təşkilat idarəetməsi |
| `apps/registrar/management/commands/archive_non_program_rows.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/seed_western_caspian.py` | 1 | C — idarə əmrləri |
| `apps/registrar/page_contexts.py` | 1 | D — tenant konteksti itmiş səhifə fallback-i (şərhli) |
| `apps/syllabus/management/commands/syllabus_repair_chair_units.py` | 1 | C — idarə əmrləri |
| `core/rls_pooling.py` | 1 | D — infrastruktur |

**Cəmi:** 156 çağırış / 65 fayl · kateqoriya üzrə — A: 38, B: 33, C: 59, D: 26.

Yeni böyük istifadəçilər (2026-05-dən sonra): `apps/exams/tasks.py` (Celery —
sorğu konteksti yoxdur, job sətirləri `ExamExportJob`/`AIGenerationJob` org FK ilə
işləyir, D), `apps/exams/services/final_center/entry.py` + `views/student/final_center.py`
(public PIN axını, B), `apps/audit/views.py` (`_run_scoped` yalnız superadmin, C, şərhli),
`apps/monitoring/permissions.py` (superadmin, C), `apps/accounts/services/view_as.py`
(hədəf yoxlaması, C), `apps/notifications/services/read_state.py` (recipient-scoped, A).
Nümunə yoxlaması (audit `access` §5): hər yeni yerdə çağırışdan əvvəl
superadmin/credential/recipient yoxlaması var.

**RLS əhatəsi (CI):** `core/tests/test_audit_2026_09_13_rls_coverage.py` hər
`organization_id` sütunlu cədvəlin RLS siyasəti olduğunu yoxlayır (istisna:
`accounts_userprofile`, açıq siyahı ilə). `registrar_guestrosterdocument` (0069)
məhz belə test olmadığı üçün siyasətsiz qalmışdı — 0074 ilə bağlandı (F-05).

## Kateqoriyalar və risk dərəcəsi

### A — recipient/owner-scoped yazma və qlobal məzmun  → RİSK: AŞAĞI
Sorğu onsuz da `recipient=user` / `owner=user` kimi güclü, atlanmaz bir filtrlə
məhdudlaşdırılıb, VƏ YA məlumat qəsdən qlobaldır (blog).
- `notifications/services.py`, `notifications/views.py` — bildiriş həmişə bir
  konkret `recipient`-ə bağlıdır; bypass yalnız istifadəçinin öz inbox-unu
  bütün org-lar üzrə görməsi üçündür (FAZA 4-də sənədləşdirildi).
- `blog/services.py`, `post_management.py` — blog qəsdən qlobaldır, RLS-dən
  kənardadır (FAZA 3-də sənədləşdirildi).
- **Tövsiyə:** saxla. Bu nümunələr təhlükəsizdir, çünki `recipient`/`owner`
  yoxlaması RLS-dən asılı deyil.

### B — public canlı imtahan (PIN/token girişi)  → RİSK: AŞAĞI-ORTA
Canlı imtahana PIN/token ilə qoşulan istifadəçinin hələ tenant konteksti yoxdur
(login olmaya bilər). PIN/token özü kriptoqrafik giriş yoxlamasıdır.
- `live_exam/views/player.py`, `scoring.py`, `consumers.py`, `auth.py`.
- **Tövsiyə:** saxla, amma hər çağırışda yoxla ki, PIN/token doğrulaması
  bypass-dan ƏVVƏL baş verir. Şərh əlavə et: niyə bypass lazımdır.

### C — cross-org superadmin / admin əməliyyatı  → RİSK: ORTA
Superadmin və ya org-admin bilərəkdən tenant sərhədini keçir (idarəetmə paneli,
üzvlük sorğuları).
- `accounts/views/organization.py`, `_helpers.py`, `services/organization_requests.py`.
- **Tövsiyə:** hər çağırışda təsdiqlə ki, çağırışdan ƏVVƏL `is_superadmin` /
  rol-səviyyə yoxlaması var. Bypass-dan sonra sorğu nəticələri istifadəçiyə
  qaytarılmazdan əvvəl yenidən filtrlənməlidir.

### D — tenant kontekst qurma (middleware infrastrukturu)  → RİSK: AŞAĞI
`OrganizationMiddleware` və `core/tenancy.py` hələ tenant kontekst təyin
olunmamış mərhələdə istifadəçinin hansı org-lara aid olduğunu öyrənir.
- **Tövsiyə:** saxla. Bu, RLS sisteminin özünü qurması üçün zəruridir
  (yumurta-toyuq problemi).

## Ümumi tövsiyələr

1. **Hər `bypass_rls()` çağırışına bir sətirlik şərh əlavə et** — niyə lazımdır,
   hansı yoxlama onu təhlükəsiz edir. Hazırda əksəriyyətində şərh yoxdur.
2. **Yeni `bypass_rls` əlavə edəndə** bu sənədi yenilə və kateqoriyasını seç.
3. **Kateqoriya C-dəki çağırışlar** ən diqqətlə nəzərdən keçirilməlidir —
   FAZA 11 (test) onlar üçün cross-tenant sızıntı testləri əlavə etməlidir.
4. **Mümkün olan yerlərdə** `bypass_rls`-i daha dar `set_rls_tenant(other_org)`
   ilə əvəz et — bütün tenant-ları açmaqdansa konkret hədəf org-a keç.

## Nəticə

156 çağırışın (2026-09-13) 64-ü (kateqoriya A və D — ~41%) **təhlükəsizdir** —
recipient-scoped, qlobal məzmun, və ya infrastruktur. Əsas diqqət kateqoriya
C-dədir (59 çağırış, ~38%; B — public PIN/token — 33): superadmin/admin cross-org əməliyyatları. Onların hamısının
çağırışdan əvvəl rol yoxlaması olduğu FAZA 11 testləri ilə təsdiqlənməlidir.
