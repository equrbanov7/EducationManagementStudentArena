# AUDIT `access` — Autentifikasiya · RBAC · Multi-tenancy (2026-09-13, ikinci buraxılış)

Develop HEAD: `96016cff`. Auditor READ-ONLY; heç bir tracked fayl dəyişməyib, `git` yazma əmri işlədilməyib.
Sandbox DB: `test_ems_audit_access` (:55432, rol `emsarena_agent` — superuser + BYPASSRLS ⇒ **sandboxda RLS
işləmir**; nəticələr tətbiq qatının ÖZ izolyasiyasını göstərir — bu, prod-a bənzəyir, çünki Codex P0-01-ə görə
prod app rolu da RLS-i yan keçir). QA klon (:55433) yalnız `BEGIN … ROLLBACK` daxilində SELECT (RLS inventarı).

Əvvəlki hesabatlarla münasibət: Codex §12 (24 rol × 665 keçid «səhifə açılır») təkrarlanmadı; bu audit
**yazma matrisi**, **tenant-lararası zondlar** və 2026-09-02 PHASE23-də «re-verify» qalan üç auth maddəsi
(enumerasiya, superadmin rate-limit qaçış yolu, view-as yazma) üzərindədir.

## 0. Metod / artefaktlar (hamısı `scratchpad/audit/access/`)
| Fayl | Məzmun |
|---|---|
| `urls.txt` | 945 URL nümunəsi (ad → yol → view) |
| `all_tables.txt`, `rls_tables.txt`, `rls_query.sql` | cədvəl inventarı (klon + sandbox) |
| `setA.json`/`setA.py` | icazə reyestri (112 açar) + universitet default rolları |
| `setB.json`/`setB.py`/`rawrefs.json` | kodda istinad olunan açarlar (yoxlama sətirləri ayrıca) |
| `lookups/scan.py`, `lookups/hits.json`, `lookups/scan.out` | scope-suz `pk=` lookup skaneri (161 hit / 57 regex-«unscoped») |
| `bypass_sites.txt` | `bypass_rls()` çağırış yerləri (64 fayl / 164 çağırış, test xaric) |
| `probes/test_rbac_tenant_probes.py` → `probe_results_rbac.md` | 26/27 keçdi; 1 «uğursuzluq» = T43 (aşağıda izah) |
| `probes/test_followup_probes.py` → `probe_results_followup.md` | auth A1–A11 + T43/T49/T39 DB-səviyyəli təsdiq; 13/14 (A11 → 500, tapıntı) |
| `probes/test_member_removal_probes.py` → `probe_results_members.md` | üzv uzaqlaşdırma axını — 2 P1 |
| `probes/run1.log`, `run2.log`, `run3.log` | pytest çıxışları |

İşə salma (hamısı üçün): `DATABASE_URL=postgres://emsarena_agent:…@127.0.0.1:55432/ems_audit_access USE_REDIS=False
PYTHONPATH=<probes dir> venv/bin/python -m pytest <fayl> --ds=config.settings.test --rootdir=/Users/elvin/Developer/EMSArena -q --reuse-db -p no:cacheprovider -o addopts="" -s`

Sintetik mühit: 2 təşkilat (A, B), hər birində default universitet rolları — rector, dean(fak1), chair_head(kaf1),
teacher (offering instructor), teacher2, student(fak1 qrup), student2(fak2 qrup), hr, exam_center_head,
exam_center_staff, ikt_rehber, program_coordinator; hər org-da 1 offering + dərs + imtahan + kurs.

## 1. Autentifikasiya checklist
| # | Yoxlama | Status | Sübut |
|---|---|---|---|
| A1 | Login/logout, portal qapısı (tələbə↔əməkdaş) | **PASS** | `A1-staff-ok` 302 + sessiya; `A1-logout` sessiya silinir; `A1-student-on-staff` 200 (giriş yox); `A1-student-ok` 302. `login.py:effective_audience` fail-closed. |
| A2 | OTP: təkrar istifadə / vaxt / cəhd sayı / proqnozlaşdırma | **PASS** | 6 rəqəm, `generate_otp` (`services/auth.py`); `A2-attempts` 5 səhv → `missing` (OTP yandırılır), `A2-correct-after-burn` 400, `A2-otp-reuse` 400, `A2-expired` 400; DB-də yalnız HMAC hash (`otp_models.py:build_otp_hash`). Saatlıq göndərmə həddi 5 (`A2-send-otp-hourly-cap` [202×4,429×3]). |
| A3 | Throttle (cihaz / İP / kimlik) | **PARTIAL** | Cihaz qatı: 6-cı cəhd 429 (`A3-device-limit` [200×5,429]); İP qatı: 61-ci cəhd 429 (`A3-ip-limit first429_at=61`); limit altında düzgün parol da 429 (`A3-limited-correct-pw`). **AMMA** superadmin üçün limit yoxdur — bax F-01. OTP verify JSON endpoint-ində İP limiti yoxdur (per-OTP 5 cəhd kifayətdir; bax F-09). |
| A4 | Hesab enumerasiyası | **FAIL (P2)** | `send-otp` `purpose=login` neytral (202 hər halda) ✅; `purpose=signup`: mövcud→**409**, naməlum→**404**, `is_active=False`→202; `purpose=password_reset`: mövcud→**202**, naməlum→**404** → aydın orakul (F-02). Parol-bərpa səhifəsi/`done` səhifəsi hər iki halda eyni görünür ✅ (`A4-pwreset-done-* otp_form_shown=True`). |
| A5 | Şifrə siyasəti | **PASS (min.)** | `security.py:13` 4 standart validator (min 8, oxşarlıq, ümumi, rəqəm); `first_login.py:106` və OTP bərpa forması `validate_password` çağırır. Uzunluq/kompleks tələb yoxdur — siyasət qərarı. |
| A6 | inactive / blocked / `access_state` | **PASS** | `A6-inactive` giriş yox; `A6-archived` (is_active=True, access_state=archived) giriş yox (`backends.py:user_can_authenticate`); mövcud sessiyalı arxiv hesab `A6-archived-session` 302→login (ModelBackend.get_user süzür). |
| A7 | Təşkilat status suspended/pending | **PARTIAL (P3)** | Aktiv org sessiyada olanda `A7-suspended` → logout+302 ✅. **Amma** yeganə təşkilatı suspended olan istifadəçi login edə bilir və kabinet 200 verir (`A7-suspended-login-follow auth=True`): `organizations/middleware.py:81` `_fetch_active_memberships` status≠active üzvlükləri süzür → org konteksti yoxdur → `SuspendedOrganizationMiddleware` heç işə düşmür. Tenant datasına çıxış yoxdur, amma sənədləşdirilmiş «hard logout» müqaviləsi (`accounts/middleware.py:138`) yerinə yetmir. `pending` org: `request.org_pending_approval` bayrağını HEÇ BİR view oxumur (grep: yalnız 2 template) — praktikada pending org seçilə bilmədiyi üçün (`A7-pending-write` 302→select, written=False) təsiri yoxdur. |
| A8 | Şifrə dəyişəndə digər sessiyaların ləğvi | **PASS** | `A8-c1-after` 200 (cari sessiya `update_session_auth_hash`), `A8-c2-after` 302→login, auth=False. |
| A9 | CSRF / cookie bayraqları | **PASS** | `A9-csrf-login`/`A9-csrf-json` 403. `production.py:331-360`: `SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE/SSL_REDIRECT` default True, `INSECURE_TRANSPORT_OK` olmadan boot ImproperlyConfigured (Codex P1-08-ə cavab); HttpOnly, SameSite=Lax, HSTS 1 il. Tək `@csrf_exempt` (Alertmanager) token-qapılı. |
| A10 | Open-redirect | **PASS** | `A10-next` 7 variant (`https://evil`, `//evil`, `/\evil`, `http://testserver@evil`, `javascript:`, `/exams/final/`) → hamısı `/accounts/kabinet/`; daxili `next` qorunur. `_sanitize_auth_redirect_target` + `url_has_allowed_host_and_scheme`. |
| A11 | İlk giriş şifrə axını | **PARTIAL (P3)** | `A11-profile-redirect` 302→set-password (middleware kilidi); OTP-siz parol təyini rədd (`A11-set-no-otp`, parol dəyişməyib). **Amma** istifadəçi BAŞQA istifadəçinin qeydiyyatlı e-poçtuna OTP göndərə bilir (`A11-send-otp-foreign-email mails=1 to=auth_teacher@audit.az`) və kod ilə `user.email=…` yazılanda `accounts_auth_email_canon_uniq` → **IntegrityError 500** (`run2.log:106`). Bax F-08. |
| A12 | Rate-limit fail-closed (PHASE23 P2-5) | **PASS** | `core/rate_limit.py:_parse_or_fail_closed` + `validate_rate_limit_settings` boot-da çökür. |
| A13 | OTP ilə parolsuz giriş | **PASS (dizayn)** | `verify_otp_api_view purpose=login` parolsuz sessiya açır (`A2-otp-login` authenticated=true) — e-poçt sahibliyi = kimlik; blocked/archived süzülür. Portal (tələbə/əməkdaş) qapısı bu yolda tətbiq olunmur (`A2-otp-login-student` 200) — qapı təhlükəsizlik sərhədi deyil (login.py şərhi), qeyd. |

## 2. RBAC yazma matrisi — zond nəticələri (eyni tenant, yanlış rol)
Legend: ✅ = bloklandı və DB dəyişmədi; ❌ = yazı baş verdi. Status kodları `probe_results_*.md`-dədir.

| Əməl (endpoint) | Kim edə bilməli (kataloq/ROL_MATRISI) | Zondlanan yanlış rollar → nəticə | Verdikt |
|---|---|---|---|
| Jurnal bağlama `accounts:journal_close` | ikt_rehber, rector (`journal.close`) | student/teacher/dean/hr/exam_center_head → 403 | ✅ |
| Dərs/bal yazısı `registrar:journal_lesson_action` | offering müəllimi (+ikt view-as) | student/teacher2/dean/chair_head/hr/ech/pc → 404 | ✅ |
| İmtahan aktivləşdirmə `exams:toggle_exam_active` | imtahan müəllifi | student 403; teacher2/ech/rector 404; `is_active` dəyişmədi | ✅ |
| Rol təyini `accounts:role_assignment` (student→rector) | `role.assign` + səviyyə | teacher/hr/ech/chair_head 403; student/pc 302→profile (bölmə icazəsi yox); rol dəyişmədi | ✅ |
| İcazə redaktoru `accounts:permission_editor` (student←`*`) | səviyyə < aktor | hamısı 302; `*` əlavə olunmadı (hr → öz redaktoruna yönlənir, amma yazmadı) | ✅ |
| İmtahan balı `accounts:exam_score_entry` (`save_scores`) | `final_score.entry` (ech, rector) | student/teacher/dean/hr/ecs/ikt/chair_head → 403; kontrol ech_a → 1 vərəq yaradıldı | ✅ |
| Cədvəl `accounts:schedule_manage_action` | `schedule.manage` | student/teacher/hr/ech → 403 JSON | ✅ |
| Düzəliş `registrar:correction_apply` | `journal.correct` | 5 rol → 404 | ✅ |
| Org parametrləri `organizations:settings` POST | owner/org_admin | 5 rol → 302; description dəyişmədi | ✅ |
| Struktur `organizations:structure_tree_action` create_child | `unit.tree_manage`+org-wide | 6 rol → 403 JSON | ✅ |
| Şəxs blok `accounts:people_action` block | `people.manage_status` | 4 rol → 403; is_active qaldı | ✅ |
| RİM parol `accounts:rim_action` set_password | `user.credentials` + rütbə | 6 rol → 403 (student: `target_rank_too_high`); parollar qaldı | ✅ |
| Kollokvium pəncərəsi `accounts:kollokvium_windows` | ikt/ech/ecs | student/teacher/dean/hr → 403 | ✅ |
| Tələbə hərəkəti `accounts:student_registry_action` group_transfer | `student.movement` | student/teacher/ech/chair_head → 403; dean(fak1)→record(fak2) 403 (`T66c`); qrup dəyişmədi | ✅ |
| Kurs üzv/silmə `courses:add_member`/`delete_course` | kurs sahibi | student/teacher2 → 403; kurs qaldı | ✅ |
| Cəhd silmə `exams:delete_exam_attempts` | müəllif | student 403; teacher2/ech 404 | ✅ |
| **Üzv uzaqlaşdırma** `accounts:student_organization_management` remove_org_member | `member.remove` (HR, ikt, rector); ROL_MATRISI §109: exam_center **·** | **exam_center_head → 302, teacher_a üzvlüyü deaktiv (`M01-db active=False`); hr_a da (`M02`)** | ❌ **P1 (F-03)** |
| **Üzv uzaqlaşdırma** remove_student (dekan, başqa fakültə) | dekan yalnız öz alt-ağacı | **dean(fak1) → student2(fak2) üzvlüyü deaktiv (`M03-db active=False`)** | ❌ **P1 (F-04)** |
| Üzv uzaqlaşdırma (pc/teacher/ecs) | — | 302→profile, üzvlük qaldı | ✅ |
| Apellyasiya qərarı `appeals:review_appeal` | imtahan mərkəzi | kod: `appeals/services/permissions.py:41` `_same_tenant` + `is_exam_center_user` (rol-əsaslı; `appeal.decide` açarı yoxlanmır — drift, §7) | kod-yoxlama, NOT PROBED |
| Sillabus qərarı `accounts:syllabus_decision` | kafedra scope | kod: `review_api.py:154-157` org + `_scoped_version`; kafedra-səviyyə qaydası `syllabus/services/units.py:135` | kod-yoxlama, NOT PROBED |
| Dərs yükü təsdiqi `workload:action` | `workload.approve` slice | kod: `services/scoping.py` `workload.*_denied`; cross-tenant `T60` chair_not_found 403 (`rows` 200 boş) | PARTIAL (yazı NOT PROBED) |
| Payload-da `organization_id` (jurnal bağlama) | yalnız superadmin oxuyur | rector_a/rector_b → 302, org B/A dəyişmədi (`F39-db unchanged`) | ✅ |

## 3. Tenant izolyasiyası — resurs cədvəli (B tenantının rektoru/müəllimi → A obyektləri)
| Resurs | Endpoint(lər) | Nəticə | Verdikt |
|---|---|---|---|
| Jurnal / düzəliş / xlsx ixrac | `registrar:journal_detail`, `journal_lesson_action`, `journal_kollokvium_save`, `journal_xlsx`, `correction_apply`, `correction_journal` | hamısı 404 (`T40`) | ✅ |
| İmtahanlar | `toggle_exam_active`, `teacher_exam_results`, `delete_exam_attempts`, `edit_exam` | 404 (`T42`), `is_active` qaldı | ✅ |
| Org slug səhifələri | `settings` POST, `members`, `roles`, `dashboard` | 302→select (`T43`, `F43-dashboard`) | ✅ |
| Struktur (slug) | `structure_faculties`, `structure_kafedras` GET | **200** (boş qabıq; A-nın bölmə adları HTML-də yoxdur — `F43 org_A_unit_names_in_html=False`); POST create → 200 forma xətası, yaradılmadı; `tree_action` 403; `unit_detail` 404; `member_detail` 403 | PARTIAL **P3 (F-07)** |
| İstifadəçilər/şəxslər | `people_action` block/grant_teacher, `rim_action` set_password, `rim_user_detail`, `people_detail`, `people_person_page`, `people_student_card` | 404 `target_outside_scope`/`target_not_found` (`T45/T46/T50/T58`) | ✅ |
| Tələbə qeydi | `student_registry_action`, `student_registry_card` | 404 `record_not_found` (`T47/T57`) | ✅ |
| Cədvəl | `schedule_manage_action` add (A offering) | 403 (`T48`) | ✅ |
| İmtahan balı | `exam_score_entry save_scores` (A offering) | 302 + `ExamScoreSheet by_rector_b=0` (`F49-db`); `CourseOffering.objects.filter(organization=…)` (`exam_score_entry.py:128`) | ✅ |
| Jurnal bağlama | `journal_close organization_id=A` | 302; A dəyişmədi (`F39`) | ✅ |
| Kurslar | `courses:add_member` | 403 (`T53`) | ✅ |
| Rollar | `role_assignment membership_a→rector_a` | 403 (`T54`); `_resolvers.py:96` `target_role.organization_id != org.id` | ✅ |
| Dərs yükü | `workload:teachers/options/rows?chair=A` | 403/403/**200 boş** (`T60`) — sızma yoxdur, cavab uyğunsuzluğu | ✅ (P3 qeyd) |
| View-as | `view_as_start user_id=student_a` (B rektoru) | 302, `view_as_state` yoxdur (`T61`) | ✅ |
| Üzv uzaqlaşdırma | `student_organization_management remove_org_member teacher_a` | 302, üzvlük qaldı (`M05`) | ✅ |
| Tələbə→tələbə / müəllim→yad jurnal (eyni org) | `people_student_card`, `student_registry_card`, `journal_detail`, `journal_xlsx` | 404 (`F70`); kontrol instructor 200 | ✅ |
| Keş açarları | `registrar/analytics_cache.py:36` (org pk), `core/cache.py:236` statistika (Codex P1-06 scope id-ləri), `academic_records_cache.py`, `live_exam/cache.py` (session) | açarlarda org/user/session var; qlobal olanlar tenant-suz məzmundur (blog, monitoring, AI config) | ✅ (grep) |
| WebSocket qrupları | `exams/consumers.py:57,131,205`, `live_exam/consumers.py:141,216` | `group_add`-dan əvvəl icazə yoxlaması (4403 close); qrup adı attempt/session/ticket id | ✅ (kod) |
| Media prefiksləri | `core/media_policies.py:426-455` 11 privat prefiks + checker (o cümlədən `guest_roster_documents/`, `student_movement`, `workload_amendment`) | deny-by-default (2026-09-10) | ✅ (kod) |
| Celery tapşırıqları | `apps/exams/tasks.py` 11 `bypass_rls()` | job-lar `ExamExportJob`/`AIGenerationJob` sətirləri ilə (org FK) işləyir | NOT TESTED (kod baxışı) |
| Bildirişlər | `notifications/services/read_state.py`, `crud.py` | recipient-scoped (RLS_BYPASS_AUDIT kateqoriya A) | ✅ (kod) |
| Fayl ixracı | `exams/export_registry.py`, `workload:my_export` | — | NOT TESTED |
| Appeals / statistika | `appeals` `_same_tenant`; statistika keşi scope-id | ✅ (kod) | — |

## 4. Scope-suz lookup-lar — verdiktlər (`lookups/scan.out`, 57 regex hit)
| Sinif | Nümunə | Verdikt |
|---|---|---|
| Valideyn-scoped (offering/exam/course/task/room/session artıq scope-ludur) | `registrar/views.py:288 (offering=)`, `exams/…/_attempt_views.py:116 (exam=)`, `courses/…/topics.py:142 (course=)`, `workload/views/distribution_api.py:255 (task=)`, `superadmin/exam_rooms.py:175 (room=)`, `live_exam (session=)` | **SAFE** (41 hit) |
| Post-yoxlama var | `roles/_assignment_flow/_resolvers.py:90` (sonra `organization_id != org.id` → deny); `profile/_sections/schedule_manage.py:229` (`known` id çoxluğundan); `services/profile_actions.py:130` (`group.teacher_id != user.pk`); `syllabus/services/units.py:135` (sillabusun öz kafedra id-si) | **SAFE** |
| Qlobal/tenant-suz məzmun | blog `Post/Category` (6+3), `Country`, `ContactMessage/TrialExamRequest` (superadmin-only bölmə, `contact_inbox.py:42`), `monitoring Incident`, `exams/services/difficulty.py:194` (daxili) | **SAFE** |
| Superadmin seçimi | `Organization.objects.filter(pk=requested)` ×7 (`exam_score_entry.py:39`, `journal_close.py:27` …) — yalnız `is_superadmin` budağında | **SAFE** |
| **Zəif** | `exams/views/teacher/exams/attempt_grants.py:61` — `User.objects.filter(id=raw_student_id, is_active=True)` — imtahan org-una üzvlük yoxlanmır → başqa tenantın istifadəçisi üçün `StudentExamAttemptGrant` sətri yazıla bilər (istifadəçi imtahana yenə çata bilmir) | **P3 (F-10)** |
| **Zəif** | `accounts/services/statistics_selectors/teacher.py:45` — `StudentGroup.objects.get(id=group_id)` org/sahib filtri yox; nəticə müəllimin öz cəhdləri ilə kəsişir → sızma yalnız «bu qrupun tələbələri mənim imtahanımı verib?» | **P3 (qeyd)** |

Regex-«scoped» sayılan 104 hit-in nümunə yoxlaması (`exam_score_entry.py:128`, `people/*`, `student_registry`) zondlarla təsdiqləndi (§3).

## 5. RLS əhatəsi + `bypass_rls()` yerləri
QA klon (171 cədvəl) və sandbox HEAD (172): **RLS on = 141/142, FORCE = 139/140, `organization_id` daşıyan = 90/91.**
Siyasətsiz RLS-cədvəl: **0**. `organization_id` daşıyıb RLS-siz:

| Cədvəl | Status | Qeyd |
|---|---|---|
| `accounts_userprofile` | RLS yox | 2026-09-02-dən bilinən, qəsdən (`organizations/migrations/0018` şərhi, `core/tests/test_rls_platform_logs.py:11`); login-öncəsi oxunur. Hələ də açıq qərar — klonda 8 451 sətir FİN/telefon/ünvan. |
| **`registrar_guestrosterdocument`** | **RLS yox** | **YENİ** (`registrar/migrations/0069`), digər düzəliş-sübut cədvəlləri (0028/0031/0033/0035/0072) siyasətlidir; media prefiksi `guest_roster_documents/` checker-lidir, ORM oxusu yalnız `guest_roster.py:442` (enrollment id-lərlə). Müdafiə dərinliyi boşluğu — **P2 (F-05)** |
| `accounts_accountactivationevidence`, `accounts_accountrestoreevidence` | RLS on, FORCE off | cədvəl sahibi üçün yalnız; app rolu onsuz da superuser (Codex P0-01) — P3 qeyd |

Tenant-bağlı olub `organization_id`-siz 28 cədvəl: `auth_*`, `django_*`, blog, `accounts_emailotp` (e-poçt açarlı),
`accounts_academicprofileitem` (user FK), `workload_teachingtaskrow_groups` (M2M) — hamısı ya qlobal, ya user-scoped.
`exams_examattempt` və s. FK-lı cədvəllər RLS-lidir (53 cədvəl siyasəti FK vasitəsilə alır).

`bypass_rls()` — **164 çağırış / 64 fayl** (RLS_BYPASS_AUDIT.md 2026-05: ~85). Yeni böyük istifadəçilər:
`exams/tasks.py` 11 (Celery, sorğu konteksti yoxdur — D kateqoriyası), `exams/services/final_center/entry.py` 7 və
`exams/views/student/final_center.py` 2 (public PIN axını — B), `audit/views.py` 3 (`_run_scoped` yalnız superadmin — C, şərhli),
`monitoring/permissions.py` 2 (superadmin, şərhli), `accounts/views/_helpers/org_sections/_members_registry.py` 2
(org filtrli, şərhli), `notifications/services/read_state.py` 7 (recipient-scoped — A), `view_as.py` 5 (hədəf yoxlaması).
Nümunə yoxlaması: hər yeni yerdə çağırışdan əvvəl superadmin/credential/recipient yoxlaması var. Sənəd köhnəlib — **P3 (F-13)**:
`docs/audits/RLS_BYPASS_AUDIT.md` sayımı yenilənməli və «hər org-sütunlu cədvəlin siyasəti var» CI testi əlavə olunmalıdır
(hazırda belə test yoxdur; ona görə 0069 sürüşdü).

## 6. View-as / impersonation (2026-09-12 düzəlişindən sonra yenidən yoxlanıldı)
| Yoxlama | Nəticə |
|---|---|
| B rektoru → A tələbəsi | 302, sessiyada `view_as_state` yoxdur (`T61`) ✅ |
| Dekan(fak1) → tələbə(fak2) | rədd (`T62`); öz fakültəsi → qəbul (`T62b`) ✅ (`_unit_scope_user_ids`) |
| İmtahan mərkəzi rəhbəri → rector / HR | rədd (`T63/T63b`, `LIMITED_FORBIDDEN_TARGET_ROLES` törəmə siyahı) ✅ |
| HR (READONLY) → tələbə; sonra `change-password` POST və `set_initial_password` POST | 302, parol dəyişmədi (`T64b/T64c`) ✅ |
| ECH (LIMITED) → müəllim; `journal_lesson_action` (siyahıda yox) | 302 geri, blok (`T65b`) ✅; `toggle_exam_active` (allowlist) 302 — dizayn üzrə icazəli, audit sətri yazılır |
| Admin `/admin/` view-as altında | kod: `accounts/middleware.py:483` GET daxil blok ✅ |
| Mutasiya edən GET (`liveExam:create_session_slug`) | `MUTATING_GET_URL_NAMES` + skan testi ✅ |
| 60 s yenidən-yoxlama, sessiya bitəndə əsl istifadəçi kimi davam etməmək | `_after_session_ended` (9c12b9c8) ✅ |
Qeyd: FULL rejimdə (owner/org_admin) `accounts:change_password_otp_request` bloklanmır — OTP hədəfin e-poçtuna gedir, ona görə ələ keçirmə yoxdur.

## 7. İcazə kataloqu drift-i (`setA.json` vs `setB.json`)
* Reyestr 112 açar; universitet default rollarında `*`-lı 9 wildcard (`course.*`, `exam.*`, …) — reyestrdə yoxdur, amma `has_permission` wildcard-ı dəstəkləyir (norma).
* Kodda yoxlanıb reyestrdə OLMAYAN: **`assignment.edit`** (`apps/assignments/views/shared/api.py:198`) — heç bir default rol daşımır; kurs sahibi + `is_teacher_or_above` şərti ilə birgə tələb olunduğundan endpoint faktiki **yalnız `*`/`course.*`-lı rollara** açıqdır (kod-yoxlama, NOT PROBED) — **P3 (F-12)**.
* Reyestrdə olub kodda HEÇ YOXLANMAYAN 16 açar: `org.edit, org.settings, org.delete, org.admin.assign, org.owner.assign, member.remove, role.create, role.edit, role.delete, grade.override, journal.view, audit.export, qa.view, qa.review, qa.flag, analytics.view_own`. Yəni icazə redaktorunda bu açarları vermək/almaq **heç nəyi dəyişmir**; real qapılar səviyyə/alias-dır (`flow.py:67 user_level ≥ 65`, `_can_manage_organization`). Bu, §2-dəki F-03/F-04-ün kök səbəbidir — **P2 (F-06)**.
* Kataloq-səviyyə qapıları: `default_roles.py` ilə `ROL_MATRISI.md` uyğun (setA: exam_center_head-də `member.*` yoxdur), amma kod matrisə deyil səviyyəyə baxır.
* Digər «naməlum açar» hit-ləri (`workload.*`, `syllabus.*`, `people.*`) xəta/hadisə kodlarıdır, icazə deyil.

## 8. Tapıntılar (P0–P3) və minimal düzəlişlər
| ID | Sev. | Tapıntı | Sübut | Minimal düzəliş |
|---|---|---|---|---|
| **F-01** | **P1** | **Superadmin hesabı üçün login rate-limit yoxdur.** Limit dolanda hər cəhd yenə `authenticate()`-dən keçir və superadmin parolu düz olsa limit təmizlənib 302 verilir → superadmin (ən dəyərli hesab) üçün brute-force sərhədsizdir (hücumçu yalnız 429 alır, düz parolda daxil olur). PHASE23-də «re-verify» qalan maddə — təsdiqləndi. | `accounts/views/auth/login.py:222-236`, `_shared.py:_authenticate_superadmin_for_rate_limit_reset`; `A3-superadmin-correct-under-limit` **302 + sessiya** 6 səhv cəhddən sonra | `CustomLoginView.post`: qaçış yolunu ayrıca çox dar vedrəyə bağla (məs. `accounts.login.superadmin_escape` 3/1h per İP+username) və ya tamamilə sil (superadmin kilidini parol-bərpa/`clear_rate_limit` idarə əmri ilə aç); ən azı uğursuz superadmin cəhdlərini `record_rate_limit_hit` ilə say. |
| **F-02** | **P2** | **Hesab enumerasiyası** — `send-otp` JSON API `purpose=password_reset` mövcud→202 / naməlum→404; `purpose=signup` mövcud→409 / naməlum→404. `login` məqsədi düzgün neytraldır. | `otp_api.py:79-88`; `A4-send_otp[password_reset]-existing 202` vs `-unknown 404`; `[signup] 409/404` | `send_otp_api_view`/`resend_otp_api_view`: `password_reset` məqsədini `login` budağı kimi neytral 202 ilə cavabla (və ya `_resolve_otp_purpose`-dan `PASSWORD_RESET`-i çıxar — bərpa üçün ayrıca form var); `signup` üçün 404/409-u `PUBLIC_SIGNUP_ENABLED=False` olanda 202-yə çevir. |
| **F-03** | **P1** | **İmtahan mərkəzi rəhbəri (85, `member.remove` YOX) üzv uzaqlaşdırır** — `student_organization_management` axını `member.remove`-ə deyil `user_level ≥ 65`-ə baxır; hədəf müəllim və HR üzvlükləri deaktiv edildi. ROL_MATRISI §109 exam_center üçün «·». | `accounts/views/organization/_management_flow/flow.py:63-67`, `_members.py:51`; `M01-db active=False`, `M02-db active=False` | `flow.py:run`: `remove_*` əməlləri üçün `_has_org_permission(actor_perms, "member.remove")` tələb et (superadmin/owner istisna) və `ADMIN_ALIAS_EXEMPT_ROLE_NAMES` rollarını qapıdan çıxar (`_can_manage_organization` ilə eyni qayda). |
| **F-04** | **P1** | **Dekan öz fakültəsindən kənar tələbəni uzaqlaşdırır** — unit scope yoxlanmır (yalnız səviyyə iyerarxiyası). | `_members.py:31-33`; `M03-db active=False` (student2 fak2) | `_remove_org_member`: `get_permission_scope(actor, org, "member.remove")` ilə hədəfin bütün aktiv `scope_unit`-lərinin aktor alt-ağacında olduğunu yoxla (`user_scope_covers_unit`); scope EMPTY → rədd. |
| **F-05** | **P2** | `registrar_guestrosterdocument` (`organization_id` var, 0069) RLS siyasətsiz — yeganə yeni tenant cədvəli siyasətsiz. | klon+sandbox `rls_query.sql` çıxışı | `registrar/migrations/00xx_rls_guest_roster_document.py` (0028 naxışı ilə ENABLE/FORCE RLS + tenant siyasəti); `core/tests`-ə «bütün org-sütunlu cədvəllər RLS-lidir (istisna: userprofile)» testi. |
| **F-06** | **P2** | Kataloq drift-i: 16 reyestr açarı (o cümlədən `member.remove`, `org.settings`, `role.edit`, `grade.override`) kodda heç yerdə yoxlanmır — icazə redaktoru «yalançı» düymələr göstərir; real qapı səviyyədir. | §7, `setB.json` | Ya açarları qapılara bağla (F-03 ilə başlayaraq), ya `PERMISSION_CATEGORIES`-dən çıxar/«planlaşdırılıb» işarələ; `core/permissions.py`-də «reyestr ↔ kod» testi (setB skriptinin CI versiyası). |
| **F-07** | **P3** | Slug-lu struktur səhifələri aktiv-org icazəsi ilə qapılanır: B rektoru `/organizations/audit-a/structure/faculties/` → 200 boş qabıq (scope EMPTY olduğundan data yoxdur, yazı bloklu). | `organizations/views/shared/_helpers.py:143 _can_view_structure` `request.org_permissions` (aktiv org=B) | `_get_org_or_redirect`: `organization != _get_active_organization(request)` və həmin org-da aktiv üzvlük yoxdursa → `organizations:select` (dashboard/members ilə eyni). |
| **F-08** | **P3** | İlk-giriş axını: istifadəçi başqa istifadəçinin qeydiyyatlı e-poçtuna OTP göndərə bilir (spam), OTP təsdiqi ilə `user.email` yazılanda unikal indeks → **500**. | `first_login.py:76-95, 121-123`; `run2.log:106 UniqueViolation accounts_auth_email_canon_uniq`; `A11-send-otp-foreign-email mails=1` | `_handle_send_otp`: göndərmədən əvvəl `canonical_identity_queryset(User, "email", email).exclude(pk=user.pk).exists()` → generik xəta; `_handle_set_password`: `IntegrityError`-u tut → mesaj. |
| **F-09** | **P3** | `verify_otp_api_view` / `send_otp_api_view` / `password_reset` üçün İP-əsaslı limit yoxdur (yalnız per-OTP 5 cəhd, per-email 5/saat). | `A2-send-otp-ip-spray` 12 fərqli e-poçt → hamısı 202; `otp_api.py`-də `OTP_VERIFY_LIMIT_SCOPE` istifadəsi yoxdur (yalnız `register.py`) | `send/verify/resend_otp_api_view`-a `is_rate_limited("accounts.otp.api", settings.OTP_RESEND_RATE_LIMIT, client_ip)` əlavə et. |
| **F-10** | **P3** | `attempt_grants.py:61` — əlavə cəhd istənilən `User.id`-yə (başqa tenant daxil) yazılır. | `lookups/scan.out` | `User.objects.filter(id=…, memberships__organization=exam.organization, memberships__is_active=True)`. |
| **F-11** | **P3** | Suspended org: yeganə org-u dayandırılan istifadəçi login edib org-suz kabinetdə qalır (sənəd «hard logout» deyir). `org_pending_approval` bayrağı heç bir view-da oxunmur. | `A7-suspended-login-follow 200 auth=True`; grep | `organizations/middleware.py` Step 2: suspended üzvlüyü də oxu və `request.blocked_organization` təyin et; `org_pending_approval`-ı ya tətbiq et, ya sənəddən sil. |
| **F-12** | **P3** | `assignment.edit` açarı reyestrdə/default rollarda yoxdur, amma `assignments/views/shared/api.py:198` tələb edir → adi müəllim öz tapşırığını bu endpoint-dən dəyişə bilməz (funksional, təhlükəsizlik deyil). | `setB.json direct["assignment.edit"]` | Açarı reyestrə + `teacher` roluna əlavə et və ya yoxlamanı `course.edit`-ə çevir. |
| F-13 | P3 | `bypass_rls()` sənədi köhnəlib (85 → 164); `workload:rows?chair=<yad>` 200 boş (digər iki endpoint 403). | `bypass_sites.txt`; `T60` | `RLS_BYPASS_AUDIT.md`-i yenilə; `rows` üçün də `chair_not_found` 403. |

Təsdiqlənmiş PASS-lar: §1 A1/A2/A5/A6/A8/A9/A10/A12; §2-də 17 əməl; §3-də 14 resurs; view-as 8 yoxlama;
PHASE23 P2-5 (fail-closed) və Codex P1-06 (scope keş açarı) düzəlişləri yerindədir.

## 9. Xülasə və ballar
1. Autentifikasiya nüvəsi möhkəmdir: portal qapısı, OTP həyat dövrü (hash, 5 cəhd, vaxt, təkrar), CSRF, cookie bayraqları (boot-qapılı), open-redirect, sessiya ləğvi — hamısı sübutla PASS.
2. **P1 F-01:** superadmin üçün login brute-force həddi faktiki yoxdur (qaçış yolu hər cəhddə parolu yoxlayır).
3. **P2 F-02:** `send-otp` API `signup`/`password_reset` məqsədləri ilə hesab mövcudluğunu sızdırır (login məqsədi düzgündür).
4. RBAC yazma matrisi: 17 yüksək riskli əməl × 4–7 yanlış rol → hamısı bloklandı və DB dəyişmədi; obyekt-id/`organization_id` manipulyasiyası nəticəsiz.
5. **P1 F-03/F-04:** üzv uzaqlaşdırma axını səviyyə ilə qapılanır — imtahan mərkəzi rəhbəri müəllim/HR üzvlüyünü, dekan başqa fakültənin tələbəsini deaktiv edə bildi (gizli düymə, birbaşa POST).
6. Kök səbəb **P2 F-06:** 16 reyestr açarı (o cümlədən `member.remove`) kodda heç yerdə yoxlanmır — icazə redaktoru effektsiz açarlar göstərir.
7. Tenant izolyasiyası (RLS söndürülmüş halda belə) tətbiq qatında saxlanır: 14 resurs sinfi, 40+ cross-tenant zond → 403/404; yalnız struktur slug səhifələri boş qabıq verir (P3).
8. RLS: 141/171 cədvəl, siyasətsiz RLS-cədvəl 0; org-sütunlu siyasətsiz **2** — bilinən `userprofile` və yeni **`guestrosterdocument` (P2 F-05)**; CI-də əhatə testi yoxdur.
9. View-as sərhədləri 2026-09-12 düzəlişindən sonra bütün zondlarda tutdu (cross-tenant, cross-fakültə, LIMITED→admin/HR, READONLY yazı, ilk-giriş ələ keçirmə).
10. Prod-un RLS-siz app rolu (Codex P0-01) hələ də ən böyük sistem riski olaraq qalır — bu auditin bütün «tenant PASS»-ları məhz tətbiq qatına aiddir.

**Say:** P0 — 0 · P1 — 3 (F-01, F-03, F-04) · P2 — 3 (F-02, F-05, F-06) · P3 — 7 (F-07…F-13).

**Ballar (0–100):**
* **Authentication — 72.** Bütün əsas mexanizmlər sübutla işləyir; −20 superadmin brute-force qaçışı (P1), −5 enumerasiya orakulu, −3 ilk-giriş 500 / İP limitsiz OTP API / suspended-org müqaviləsi.
* **Authorization / RBAC — 66.** 17/19 yüksək riskli əməl düzgün qapılıdır və obyekt-id manipulyasiyası nəticəsizdir; −24 iki real yazı dəliyi (üzv uzaqlaşdırma: rol və scope), −10 kataloq drift-i (16 «ölü» açar, `assignment.edit`).
* **Multi-Tenancy — 78.** Tətbiq qatında cross-tenant zondlar 100% bloklandı, keş/WS/media scope-lu; −12 yeni RLS-siz tenant cədvəli + CI əhatə testinin olmaması, −5 slug səhifə qabıqları/`rows` uyğunsuzluğu, −5 prod app rolunun RLS-i yan keçməsi (Codex P0-01, dəyişməyib) səbəbilə RLS-in müdafiə kimi sayıla bilməməsi.
