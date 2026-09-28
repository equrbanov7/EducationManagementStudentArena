# AUDIT `security_auth` — Authentication · Authorization · OWASP · Uploads · API · Privacy (2026-09-28)

Base: Develop `914a6571` + uncommitted working tree of 2026-09-28 (courses/assignments/labs/projects/registrar
course_groups/profile my-courses/ems_confirm). Auditor: READ-ONLY (no tracked file edited, no git writes, no DB other
than sandbox :55432). Sub-scopes delegated to two helper auditors (same rules): `apps/surveys` and
`apps/subject_folder` + `apps/timetable` (all three apps are new since the 2026-09-13 audit).

## 1. Scope & method (what was actually run)

| Step | Command / artefact | Result |
|---|---|---|
| Sink inventories | grep for `.raw/RawSQL/.extra/cursor.execute`, f-string SQL, `mark_safe/format_html`, `\|safe`, `autoescape off`, `csrf_exempt`, `subprocess/os.system/shell=True`, `pickle/yaml.load/eval/exec`, outbound `requests/urlopen`, `fields="__all__"`, `setattr(obj, key, …)`, `innerHTML/insertAdjacentHTML`, `redirect(<var>)` | see §3 PASS table |
| URL inventory | `scratchpad/audit/security_auth/url_inventory.py` → `urls.json` (978 routes; 509 without an obvious login marker, all triaged: admin, public SEO/blog/live-PIN, auth, custom guards) | no unauthenticated sensitive route found |
| Deploy check | `manage.py check --deploy --settings=config.settings.production` with dummy env + TLS vars | "no issues (0 silenced)"; without TLS vars the boot guard raises `ImproperlyConfigured` (by design) |
| Regression of 2026-09-13 fixes | `pytest apps/accounts/tests/test_audit_2026_09_13_auth.py …_rbac.py test_otp_api.py test_view_as.py` (sandbox `ems_audit_security_auth`) | **95 passed** (`probes/run_regression.log`) |
| Auth probes | `probes/test_auth_probes.py` (5 tests) | all ran; outputs in `probes/run_auth.log`, `run_auth_p1p2.log` |
| Superadmin-role probes | `probes/test_superadmin_role_probes.py` (3 tests) | `probes/run_superadmin_role.log` |
| 2FA/media probe | `probes/test_2fa_media_probe.py` (MEDIA_ROOT overridden to scratch dir) | `probes/run_2fa_media.log` |
| Log-sanitizer probe | `probes/key_in_log.py` (request to 127.0.0.1:1, no external call) | `probes/run_key_in_log.log` |
| Helper: subject_folder/timetable | `security_auth/folder/test_sf_scratch.py` (5 passed), `test_tt_scratch.py` (3 passed), `pptx_bomb.py` | see SF-*/TT-* |
| Helper: surveys | `security_auth/surveys/…` | see SV-* |

Run line used: `DATABASE_URL=postgres://emsarena_agent:…@127.0.0.1:55432/ems_audit_security_auth USE_REDIS=False
PYTHONPATH=<repo> venv/bin/python -m pytest <file> --ds=config.settings.test -q --reuse-db -p no:cacheprovider
--rootdir=<repo> -o addopts="" -s`.

## 2. Status of prior findings (2026-09-13 `access.md` + `security.md`)

| Prior ID | Title | Status | Evidence |
|---|---|---|---|
| access F-01 (P1) | superadmin login brute-force escape | **FIXED** | `apps/accounts/views/auth/_shared.py:_superadmin_escape_under_login_limit` — own bucket 3/1h per IP+username, failures recorded; regression tests pass |
| access F-02 (P2) | OTP API account enumeration | **PARTIALLY FIXED** | `password_reset`/`signup` neutral; **`purpose=login` still differs** → new SA-01 |
| access F-03/F-04 (P1) | member removal by level / out-of-scope dean | **FIXED** | `_management_flow/_members.py:23-61` `member.remove` + `get_permission_scope`; `test_audit_2026_09_13_rbac.py` pass |
| access F-05 (P2) | `registrar_guestrosterdocument` without RLS | **FIXED** | `registrar/migrations/0074_rls_guest_roster_document.py` |
| access F-06 (P2) | dead permission keys | **FIXED** | commit `9d92477b`/`b691140d` + drift ratchet test |
| access F-07…F-13 (P3) | struct page shell, first-login foreign e-mail 500, OTP IP limit, grant tenant, suspended org, `assignment.edit`, RLS doc | **FIXED** | `first_login.py:47,151-158`; `_shared.py:_ip_rate_limited_and_recorded`; `organizations/middleware.py:101-184`; commits `432c15b3`, `b691140d`, `e354693f` |
| security F-01 (P2) | LLM output → innerHTML (exam statistics) | **FIXED there, REGRESSED as a sibling** | `teacher_exam_statistics_charts.js:224-226` escapes; **live-exam sibling does not** → SA-05 |
| security F-02 (P2) | unregistered media prefixes | **FIXED** | `core/media_policies.py:522-543` |
| security F-03 (P2) | clone DB passwords in tracked files | **FIXED** | commit `7e565380`; `.claude/*.env` git-ignored (`.gitignore:6,212,213`); current uncommitted `.claude/launch.json` diff sources `.claude/prodcopy.env`, no literal credential |
| security F-04/F-05 (P3) | self-XSS / server message sinks | **FIXED** | `assignment_modal.js:41-46` `renderAlert` uses `textContent` |
| security F-06…F-11 (P3) | upload validator, CSV formula, AI PII, env example, deps, grade audit | **FIXED** (per commit `cfd38f13`/`d1c70764`; upload validator verified in helper audit: magic bytes, markup rejection, Pillow) | — |

## 3. PASS summary (checked, no finding)

- **SQLi**: 31 raw-SQL call sites (27 in 2026-09-13 + `subject_folder/services/locks.py:29`, `surveys/services/gate_snapshot.py:111`, `timetable/tasks.py:28,36`) — all bound params; f-string parts are code constants / `quote_name`. 0 `.raw()/RawSQL/.extra()`.
- **Template XSS**: `mark_safe` 0 (outside admin), `autoescape off` 0, `|safe` only `_bootstrap_select_field.html:24,32,40` with literal/`int` attrs. Today's new/changed templates: no inline `<script>`/`<style>`/`on*=`.
- **DOM XSS in today's JS**: `assignment_modals.js`, `lab_modals.js`, `project_modals.js`, `course_ai_drawer.js` escape every server value; new files (`review_page_ui.js`, `course_panel.js`, `_member_group_picker.js`, `course_card_nav.js`, `ems_confirm.js`) have no HTML sinks.
- **CSRF**: single `@csrf_exempt` (`monitoring/views.py:351`, bearer + `compare_digest`). **CORS**: none. **CSP/headers**: `check --deploy` clean; nginx `nosniff` on static/media.
- **Open redirect**: every `redirect(<var>)` goes through `_resolve_next_url` / `_safe_same_origin_redirect_path` (`url_has_allowed_host_and_scheme` + host equality).
- **SSRF**: outbound calls only to settings-defined bases (Gemini, Piston, ARP agent, Prometheus, Brevo); AI planner links validated `http(s)` only and never fetched server-side.
- **Command injection / deserialization**: `subprocess` only argv lists (coding runtime, legacy repair); `exec` only in settings loader; no pickle/yaml.load.
- **Mass assignment**: no `fields="__all__"` outside admin; all `setattr` loops iterate allow-lists (`profile.py:26`, `academic_profile.py:223`, `workload/services/tasks.py:288`, `timetable/services/*`).
- **Today's IDOR fix confirmed**: `assignments/views/teacher/crud.py:_course_student_users` and `projects/.../crud.py` now restrict `students[]` to course members (previously any `User.id`); labs already intersected (`labs/views/teacher/crud.py:77`). Latent helper `task_submission_core/services.py:178 assign_task_to_students` still unscoped but has **no view callers**.
- **New course endpoints** (`courses/views/teacher/ai.py`, `groups.py`): login + owner-course (`_owner_courses_queryset`, tenant-scoped) + `course.edit`; AI quota reuses `ai_summary` limiter; plan normalised (lengths, counts, http(s) URLs) before write; apply is atomic.
- **Session**: `cached_db`, HttpOnly, SameSite=Lax, Secure enforced by boot guard, prod 24 h absolute / 8 h idle; Django `login()` rotates the key (no fixation); password change invalidates other sessions (regression test).
- **Exam PIN (`/exams/final/`)**: 8-digit `secrets` PIN, hashed, per-IP+username and per-username throttles (10/min), dummy-hash timing equalisation, registered-computer gate. Note only: PIN login creates a full account session (`final_center.py:377`) and the IP allow-list is open when `FINAL_EXAM_ALLOWED_IPS` is empty (`exam_center_gate.py:100-102`) — config-dependent, not scored as a finding.

## 4. New findings

Count: **P0 0 · P1 1 (SV-1) · P2 10 (SA-01…06, SF-1, TT-1, SV-2, SV-3) · P3 ~13** (SA-07…10, SF-2/3, TT-2…5, SV-4/5).
Helper PLAUSIBLE (not verified): `subject_folder` `lookups.is_org_admin` true for any `is_ikt_rehber` without an org match (media checker not tenant-filtered; RLS + UUID paths mitigate); no explicit self-review guard in `subject_folder/services/review.py:_lock_for_review`; plagiarism matches show names from untaught groups.

### SA-01 `send-otp` (purpose=login) still enumerates registered e-mails and mails the victim
Severity: P2   Category: Authentication / account enumeration   Status: CONFIRMED
Location: `apps/accounts/views/auth/otp_api.py:141-166` — `_send_otp_common`
Evidence:
```
P1 existing: 202 {'success': True, 'detail': 'OTP emailə göndərildi.', 'expires_in': 300}
P1 unknown : 202 {'success': True, 'detail': 'Əgər bu email qeydiyyatdan keçibsə, OTP göndərildi.'}
P1 mails sent: 1
```
How verified: `probes/test_auth_probes.py::test_P1_send_otp_login_enumeration` (run_auth_p1p2.log).
Impact: anyone can test whether an e-mail has an account (body differs; cooldown 429 also only for existing accounts) and trigger OTP mails to real users (5/h per e-mail, 40/10 min per IP). The endpoint is not used by any template/JS (grep for `send-otp`/`send_otp_api` in templates/static = 0 hits).
Root cause: the 2026-09-13 fix neutralised only `password_reset`/`signup`; `login` kept the "sent + expires_in" contract "for the front-end", but no front-end uses it.
Recommended fix: return `_neutral_sent_response()` for `login` too, or remove the three JSON OTP routes (see SA-02).
Effort: Small

### SA-02 Hidden passwordless login: `verify-otp` (purpose=login) logs any account in with e-mail possession only
Severity: P2   Category: Authentication / hidden endpoint   Status: CONFIRMED
Location: `apps/accounts/views/auth/otp_api.py:235-243` — `verify_otp_api_view`
Evidence:
```
P2 verify: 200 {... 'verified': True, 'authenticated': True}     # rector account, no password sent
P2 cabinet after OTP-only login: 302 /accounts/profile/
P2b student authenticated: True                                   # student/staff portal gate not applied
P3 superadmin OTP-login: 200 True -> next request 302 /admin/verify-otp/
P3 mails: [['sa_root@audit.az'], ['sa_root@audit.az']]            # both "factors" go to the same inbox
```
How verified: `test_P2_*`, `test_P3_*` in `probes/test_auth_probes.py`.
Impact: a second, UI-less login path that (a) skips the password entirely, (b) skips the login rate-limit buckets (only per-OTP 5 attempts + 100/10 min IP), (c) skips the student/staff portal gate, and (d) for is_staff superadmins turns "password + e-mail OTP" into "e-mail OTP + e-mail OTP" (single factor). Compromise of a mailbox = silent account takeover without a password change (password reset at least changes the password and is noticed).
Root cause: legacy API kept after the UI moved to password login.
Recommended fix: remove `accounts:send_otp_api/verify_otp_api/resend_otp_api` routes or reject `purpose=login` unless a feature flag is on; if kept, never `login()` users with `is_staff`/superadmin/admin-level roles via this path.
Effort: Small

### SA-03 No account-level brute-force protection against distributed guessing
Severity: P2   Category: Authentication / rate limiting   Status: CONFIRMED
Location: `apps/accounts/views/auth/_shared.py:81-114` — `_login_limit_keys`
Evidence:
```
P4 statuses set: [200] 429 count: 0 correct pw after 80 fails: 302 /accounts/kabinet/
```
(80 wrong passwords for one username, each from a different IP without the device cookie; then the correct password logs in.)
How verified: `test_P4_distributed_bruteforce_no_account_lock`.
Impact: all buckets are keyed on device or IP (`(device)`, `(device,user)`, `(ip)`, `(ip,user)`); there is no username-only bucket, so password spraying/credential stuffing from many IPs is unbounded per account. Mitigated in prod for admin accounts by the network-zone gate (LAN-only) — not for students/teachers, who are reachable from the public domain.
Root cause: identity bucket always combined with device/IP to avoid NAT lock-outs.
Recommended fix: add a username-only bucket with a slower/softer policy (e.g. 20/1h → CAPTCHA-free delay or require e-mail OTP step-up) and alert on >N distinct IPs per username; keep existing buckets.
Effort: Small–Medium

### SA-04 Two definitions of "superadmin" → 2FA, view-as and network-zone guards miss `profile.role='superadmin'`
Severity: P2 (becomes P1 if any such account exists in prod — not verified, owner to run the count query)   Category: Authorization / privilege escalation   Status: CONFIRMED (in sandbox)
Location: `apps/accounts/roles.py:222-227` (`is_superadmin` = `is_superuser OR profile.role=='superadmin'`) vs `core/admin_auth.py:50-57` (2FA only if `is_staff`), `apps/accounts/services/view_as.py:339,575` (target exclusion only `is_superuser`), `apps/accounts/network_zone.py:112` (staff only if `is_superuser`)
Evidence:
```
S1 is_superadmin: True is_superuser: False is_staff: False
S1 login: 302 /accounts/kabinet/
S1 superadmin_organizations without any 2FA: 200
S3 control rector (no view-as) superadmin_organizations: 403
S3 view-as state mode/target: full True
S2 superadmin_organizations while viewing-as: 200
```
How verified: `probes/test_superadmin_role_probes.py` (profile-role superadmin holding a teacher membership).
Impact: (1) such an account gets every level-999 privilege without 2FA; (2) a rector / vice-rector / ikt_rehber / org_admin (FULL view-as) can "view as" it and act as a platform superadmin (all tenants); (3) the network-zone gate classifies it as teacher/student → reachable from the public internet.
Root cause: `is_superadmin` property widened to profile role; guards written against `is_superuser`/`is_staff`.
Recommended fix: one predicate `core.permissions.is_superadmin_user` everywhere: `admin_2fa_required_for_user` → `is_staff or is_superadmin_user`; view-as `build_target_queryset`/fast path → `.exclude(Q(is_superuser=True)|Q(profile__role='superadmin'))`; `network_zone.account_kind` → staff for `is_superadmin`. Owner check (read-only): `SELECT count(*) FROM accounts_userprofile p JOIN auth_user u ON u.id=p.user_id WHERE p.role='superadmin' AND NOT u.is_superuser;`
Effort: Small

### SA-05 LLM summary rendered unescaped in the live-exam teacher page (prior F-01 drift)
Severity: P2   Category: XSS / HTML injection (LLM output)   Status: CONFIRMED (sink) / PLAUSIBLE (exploit — LLM-dependent)
Location: `apps/live_exam/static/js/teacher_live_session_detail.js:432,447-458` — `formatMd`; prompt input `apps/live_exam/views/results.py:327`
Evidence:
```js
aiContent.innerHTML = formatMd(data.summary) + quotaHtml;          // :432
function formatMd(text) { var html = text.replace(/### (.*)/g, ...)  // :447, no escapeHtml
aiContent.innerHTML = '...' + (data.error || I18N.ai_error) + '...'; // :434
```
```python
"players": [{"nickname": p.nickname, ...} for p in players],        # results.py:327, nickname = any 32 chars (live_exam/auth.py:24-27)
```
How verified: read; sibling renderers (`teacher_exam_statistics_charts.js:226`, `exam_center_stats_charts.js:31`, `static/js/ai_assistant.js:197`) all `escapeHtml` first.
Impact: a live-quiz player (joins with PIN, nickname unrestricted HTML) can get markup echoed by the model into the teacher's DOM. CSP (`script-src 'self' 'nonce'`, no inline handlers) blocks script execution; HTML/link/form injection and `style=` redress remain (`style-src-attr 'unsafe-inline'`).
Root cause: code moved from an inline template script on 2026-09-21 without the escape the other three renderers have.
Recommended fix: `var html = escapeHtml(text)` at the top of `formatMd`; `textContent` for `data.error`; consolidate into one `static/js/ems_ui/markdown.js`.
Effort: Small

### SA-06 Gemini API key in URL query string leaks through logs (sanitizer misses it)
Severity: P2   Category: Secrets / logging   Status: CONFIRMED
Location: `apps/ai_assistant/gemini_client.py:232-236,311`; `apps/exams/services/ai_grading.py:356-362`; sanitizer `core/logging_filters.py:26-28,36-58`
Evidence:
```python
f"{quote(model, safe='')}:generateContent?key={api_key}"                    # gemini_client.py:234
logger.exception("Gemini assistant network error: model=%s detail=%s", model, exc)   # :311
```
`probes/key_in_log.py` → `key present in sanitized log output: True | occurrences: 4`
How verified: local request to `127.0.0.1:1` with a fake key through `SensitiveDataFilter`.
Impact: any network/TLS/DNS error writes the production Gemini key into app logs (and Sentry if enabled): `_QUERY_VALUE_RE` has no `key=`, exception objects in `args` are not sanitised, and `exc_info` tracebacks bypass the filter.
Root cause: key passed as query parameter; sanitizer only handles strings/known names.
Recommended fix: send the key in the `x-goog-api-key` header in both call sites; add `key|api_key` to `_QUERY_VALUE_RE`/`_KEY_VALUE_RE` and sanitise `str(arg)` for exception args; rotate the key if logs were shipped anywhere.
Effort: Small

### SA-07 Admin-2FA gate exempts `/media/`: password-only superuser can read any private file
Severity: P3   Category: Authentication / 2FA bypass (defense in depth)   Status: CONFIRMED
Location: `core/admin_auth.py:216-220` — `AdminOTPGateMiddleware._exempt_prefixes`; `core/media_views.py:498-500` superadmin allow-all
Evidence:
```
M1 control cabinet (OTP not verified): 302 /admin/verify-otp/
M1 private media without OTP: 200 application/pdf
```
How verified: `probes/test_2fa_media_probe.py` (scratch MEDIA_ROOT).
Impact: with only the superuser password, every private upload (exam answers, correction PDFs, applications) is downloadable; limited because paths are random/UUID and no page can be browsed before OTP.
Recommended fix: exempt only `STATIC_URL`; in `protected_media` require `admin_2fa_verified(request)` for superadmin access. Same idea for `network_zone._ALWAYS_OPEN_PREFIXES` (`/media/` open to admin accounts from the external zone, `network_zone.py:70`).
Effort: Small

### SA-08 High-privilege org roles have no second factor
Severity: P3   Category: Authentication   Status: CONFIRMED (read)
Location: `core/admin_auth.py:50-57` (2FA = `is_staff` only); roles `ikt_rehber` (level 95, `*` wildcard since `organizations/0053`), `rector`, `vice_rector`, `hr`, `org_owner`.
Impact: these accounts can view-as (FULL) most users, assign roles, edit grades; only a password protects them (plus LAN-only zone when `NETWORK_ZONE_ENFORCED`).
Recommended fix: extend the existing admin OTP flow to memberships with level ≥ 80 or `*` wildcard (step-up at login or before view-as/role-assign).
Effort: Medium

### SF-1 (helper) Office-file decompression bomb in plagiarism extraction
Severity: P2   Category: Upload / DoS   Status: CONFIRMED (helper test `folder/pptx_bomb.py`: 1.6 MB .pptx → 2.34 GB peak RSS)
Location: `apps/subject_folder/services/plagiarism/extract.py:132-152` (`_zip_member`, `_office_text`); zip checks only for `.zip` at `services/uploads.py:118-119`
Impact: any enrolled student can OOM the Celery worker (or a web worker when the broker is down, `dispatch.py:39-41`).
Recommended fix: running total of decompressed bytes/characters across members with early stop at `MAX_TEXT_CHARS`; per-member cap ~2 MB; run `validate_zip_archive` for OOXML/ODF uploads.
Effort: Small

### TT-1 (helper) Unit-scoped coordinator edits org-wide timetable level policy
Severity: P2 (owner decision — existing test `timetable/tests/test_views.py:99` does exactly this)   Category: Authorization   Status: CONFIRMED (`folder/test_tt_scratch.py`)
Location: `apps/timetable/views/api.py:80-87` → `services/policy.py:98-112` `save_level` (no org-wide scope check)
Recommended fix: require `actor_scope(...).is_org_wide` (or owner/superadmin) in `save_level`.
Effort: Small

### TT-2 (helper) One shared group grants view/discard/lock/move of another coordinator's whole run
Severity: P3   Category: Authorization   Status: CONFIRMED — publish re-checks scope (`registrar/schedule_publish.py:232-243`), so the live timetable is safe
Location: `apps/timetable/services/access.py:101-110`; used by `views/api.py:194-221`
Fix: view only if scope covers all run groups or creator; mutate only creator/org-wide. Effort: Small

### TT-3/TT-4/TT-5 (helper) Timetable API hygiene
Severity: P3   Status: CONFIRMED (TT-3 test; TT-4/5 read)
- TT-3: malformed UUID in `unit_ids`/`group` → 500 (`timetable/sources/scope.py:100-101`, `api.py:76`) — use `core.http_ids.parse_uuid`.
- TT-4: `runs.py:275-281,331` stores `str(exc)` and returns it to the browser (`"error": run.error`) — DB/engine error text exposure.
- TT-5: active-run cap ignores "stale" queued runs (`api.py:130-131`) and no rate limit on `run_start/precheck/run_action` — heavy-queue flooding by `schedule.manage` holders.
Effort: Small each

### SF-2 / SF-3 (helper) Subject folder minor issues
Severity: P3   Status: CONFIRMED (`folder/test_sf_scratch.py`)
- SF-2: teacher can open/download a student's **draft** submission by id (`subject_folder/services/access.py:171-181` no status check) — UI promises drafts are private.
- SF-3: client-declared MIME stored and echoed on download (`uploads.py:126`, `media.py:67`; `text/html` accepted for `.txt`) — safe today due to `attachment` + `nosniff`; derive type from extension.
Effort: Trivial each

### SA-09 Teachers can pull any organisation group into their course (roster exposure)
Severity: P3   Category: Authorization / privacy (design)   Status: CONFIRMED (read, uncommitted today)
Location: `apps/courses/views/teacher/groups.py:96-136` + `apps/registrar/course_groups.py:118-151,170-185`
Evidence: `resolve_groups(organization=…, group_ids=…)` accepts any active org group; previously `StudentGroup.objects.filter(..., teacher=request.user)`.
Impact: any course owner with `course.edit` can enumerate all groups (`AvailableGroupsView` `q=`) and enrol their students (names, notifications sent to them). Intended per module docstring ("digər aktiv qruplar axtarışla"), but it widens who sees whom.
Recommended fix: owner decision; at minimum audit-log group bulk-adds of non-taught groups, or restrict "others" to the teacher's chair/faculty scope.
Effort: Small

### SA-10 Minor API/error-handling items
Severity: P3   Status: CONFIRMED (read)
- `assignments/views/teacher/crud.py` (today): `max_attempts`/`max_score` taken raw from POST (`request.POST.get("max_attempts") or …`) — non-numeric → `ValueError` → 500; use int parsing with 400.
- `exams/views/exam_center/monitor.py:114` returns `str(exc)` of a generic `ValueError` from `teacher_resume_attempt` (other `str(exc)` sites use domain exceptions — fine).
- PII in logs: usernames (real names, `ad.soyad`) logged unmasked, e.g. `exams/views/student/final_center.py:311`; `SensitiveDataFilter` masks only e-mail/phone.
- `courses/views/teacher/groups.py:144` broad `except Exception` → 500 with generic text (logged) — acceptable.
Effort: Small

(SV-* surveys findings: see §4b.)

## 4b. Surveys app (helper audit; scratch tests `security_auth/surveys/test_audit_surveys.py`, `test_audit_unit_diff.py`, `test_audit_dblink.py` — 7 passed, sandbox)

Authorization of `apps/surveys` is sound (students/plain teachers 403, other chair 404, other tenant filtered, manage requires org-wide `survey.manage`, `fmt` whitelisted, formula neutralisation, `next` validated, no `csrf_exempt`). The weaknesses are in the **anonymity / disclosure-control** layer.

### SV-1 Differencing a department view against its parent reveals a sub-k department's answers
Severity: P1 (privacy/anonymity; same tenant; requires a results-viewer role spanning >1 unit)   Category: Privacy / k-anonymity bypass   Status: CONFIRMED
Location: `apps/surveys/services/filters.py:48-49` (`NARROWING = ("subject_id","group_id","program_id","course_year")` — faculty/department filters absent); `apps/surveys/services/analytics_extra.py:143-149` (complement check only when `is_narrowed`)
Evidence (test `test_org_minus_department_reveals_hidden_department`, rector, k=3): university Q1 `[25,0,0,0,75]` avg 4.0; `er_department=A` (6 answers) `[0,0,0,0,100]` avg 5.0; chair B (2 answers) suppressed in its own view and in the teacher drawer → difference proves both B respondents answered 1.
Impact: rector / quality-control / teaching office / RİM head can read answers of groups below k with two filter clicks; panel views are not audit-logged (only exports).
Fix: treat faculty/department filters as narrowing and require parent−child = 0 or ≥ k; or suppress a unit summary when parent minus published siblings leaves 1…k−1.
Effort: Medium

### SV-2 Close → reopen → close isolates a single new response
Severity: P2   Category: Privacy   Status: CONFIRMED (through real POST `/sorgu/idare/` + student form)
Location: `apps/surveys/services/campaigns.py:163-179` `reopen_campaign` (no "already published" state); `apps/surveys/views/manage.py:96-114`
Evidence: after first close avg 5.0 (n=5 by panel); reopen, one student submits 1s, close → avg 4.33, panel shows 6 → 6×4.33−5×5.0 = 1. Variant (read only): `update` can move `closes_on` into the past and back.
Fix: freeze published results to the first-close set, or withhold after reopen until ≥ k new responses. Effort: S–M

### SV-3 Response ↔ receipt (student) linkable at DB/backup level by physical order / xmin
Severity: P2   Category: Privacy (DB/backup)   Status: CONFIRMED (18/18 receipts matched by `ORDER BY ctid` in sandbox; shared `xmin` by construction — read, not queried)
Location: `apps/surveys/services/submit.py:47-86` (receipt + response inserted back-to-back in one transaction); residual risk documented only for DB admins in `models/responses.py:22-26`, not for dumps.
Impact: every response is re-identifiable from any `pg_dump` (backups, prod copies, QA clone).
Fix: write responses via a delayed, shuffled, batch (≥ k) flush in a separate transaction; interim: periodic random-order rewrite of the responses table; classify survey backups as sensitive. Effort: Medium

### SV-4 Exact counts leak (enables SV-1/SV-2 precision)
Severity: P3   Status: CONFIRMED — `surveys/views/results_overview.py:23-24` integer percentages (17/83 ⇒ n=6); `templates/surveys/cabinet/_campaigns_panel.html:50-54` exact `responses`/`receipts` for live campaigns. Fix: bucket/round as in results panel. Effort: S

### SV-5 Mandatory-survey gate covers only `/accounts/profile/`
Severity: P3 (policy)   Status: CONFIRMED (read; test asserts it deliberately) — `apps/surveys/middleware.py:31,41`. Effort: S (product decision)

PLAUSIBLE (not verified): Clarity not excluded from the cabinet survey-results section if `MICROSOFT_CLARITY_AUTHENTICATED=true` (`core/context_processors.py:176-183`); Sentry request bodies on `/sorgu/` errors; k minimum 3 allows 2-colluder inference (design).

## 5. Scores (0–100)

| Area | Score | Justification |
|---|---|---|
| **Security (OWASP app)** | **80** | Injection/CSRF/CORS/redirect/SSRF/deserialization clean, CSP nonce-only, today's IDOR fixed; minus SA-05 (LLM→innerHTML regression), SA-06 (API key in logs), SF-1 (decompression DoS). |
| **Authentication** | **73** | 2026-09-13 fixes hold (95 regression tests); minus SA-02 hidden passwordless login, SA-01 enumeration, SA-03 no per-account limit, 2FA only for `is_staff` and same-inbox factor (SA-08, SA-07). |
| **Authorization** | **76** | Member-removal/drift/grant holes closed and verified; new endpoints owner+tenant+permission gated; minus SA-04 (latent superadmin escalation via view-as), TT-1/TT-2 scope gaps, SA-09 roster breadth, SF-2. |
| **API** | **79** | Consistent JSON 403/404 bodies, tenant-scoped lookups, rate limits on score/import/AI; minus unvalidated numeric fields → 500, malformed UUID → 500 (TT-3), unused legacy OTP API still routed. |
| **Error handling** | **76** | DEBUG off, custom 403/404/500/CSRF views, domain exceptions mapped; 483 broad `except Exception` (80 in views, 6 silent — all benign); minus `str(exc)` persisted/returned (TT-4, monitor.py). |
| **Privacy** | **68** | Media private-by-default, exports neutralised, e-mail masking in logs, Sentry PII off, AI e-mail masking (prior F-08 fixed); minus survey anonymity breaks (SV-1 differencing, SV-2 reopen, SV-3 DB/backup linkage, SV-4 exact counts), API key in logs (SA-06), unmasked usernames in logs, org-wide roster pull into courses (SA-09), plagiarism names across groups (helper note). |

## 6. Prioritised remediation (security_auth area)

| # | Priority | Action | Dependency | Risk of change | Effort | Benefit |
|---|---|---|---|---|---|---|
| 0 | P1 | SV-1: complement (parent−child ≥ k) check for faculty/department filters + unit-level publish rule; SV-4 rounding in same change | none | low (analytics only) | M | restores the survey anonymity promise |
| 0b | P2 | SV-2 freeze results after first close; SV-3 delayed shuffled response flush + treat dumps as sensitive | SV-1 | medium (data flow change) | M | anonymity vs admins/backups |
| 1 | P1-ish | SA-04: unify superadmin predicate in 2FA gate, view-as target filters, network zone; run owner count query | none | low (tests exist for view-as/2FA) | S | closes latent tenant-wide escalation |
| 2 | P2 | SA-02 + SA-01: drop JSON OTP routes (or neutral `login` + no login for admin-level) | confirm no mobile/API client uses them | low | S | removes password-less side door + oracle |
| 3 | P2 | SA-06: Gemini key → `x-goog-api-key` header, extend sanitizer; rotate key if logs left the host | none | low | S | stops secret leakage |
| 4 | P2 | SA-05: escape in live-exam `formatMd`; shared markdown helper | none | none | S | closes LLM HTML injection |
| 5 | P2 | SF-1: cumulative decompression cap in plagiarism extractor | none | low | S | worker DoS by students |
| 6 | P2 | SA-03: username-only soft bucket + alerting | rate-limit settings | medium (NAT lock-outs) — keep soft | S–M | slows distributed spraying on student/teacher accounts |
| 7 | P2 | TT-1 (owner decision), TT-2 run ownership | owner | low | S | coordinator isolation |
| 8 | P3 | SA-07 media behind 2FA; SA-08 step-up OTP for level ≥ 80 roles | SA-04 | medium (UX) | M | real MFA for administrators |
| 9 | P3 | TT-3/4/5, SF-2/3, SA-09, SA-10 hygiene | none | none | S each | robustness/privacy |
