# SEC-2 — Live (dynamic) security tests

- **Date:** 2026-10-17
- **Target:** local dev-clone only — `http://127.0.0.1:8011` (launch.json `emsarena-dev-clone`),
  DB `emsarena_rehearsal_a0d170000901` on `127.0.0.1:55433` (container `emsarena-staging-pg`).
- **Scope:** authorised dynamic testing of endpoints added in the last ~10 days (`git log --since=2026-10-07`).
- **Method:** in-process Django test client with `force_login` against the clone settings (full middleware +
  decorator stack exercised), plus `requests` against the live `:8011` server for the login-lockout test.
  **Every state-changing POST was wrapped in `transaction.atomic()` + forced rollback** — nothing was persisted
  even where a gate could have been broken (rollback integrity was verified afterwards: the throwaway gated user's
  profile was still empty, task-row count unchanged at 824).
- **Production:** never touched. No prod URLs, no SSH, no `gh workflow run prod-*`, no load/DoS.
- **Owner rules honoured:** `qa.*` passwords never changed/rotated; authenticated tests used `force_login` or a
  throwaway `sec2.*` account; non-destructive probing only; test objects cleaned up.

## Environment note (affects coverage)
The `emsarena_app` DB role is under **RLS**: a bare `manage.py shell` sees 0 rows for tenant-scoped tables, so
early enumeration looked empty. Through the request path (RLS context set) the clone is fully populated — 9 700
memberships, 28 roles, 938 org units, 5 teaching tasks / 824 rows, 24 exams, 11 293 course offerings. All role-scoped
tests below therefore ran against **real** objects with **real** qa.* role scopes:

| qa account | role | scope |
|---|---|---|
| qa.student | student | group «634 ing» |
| qa.teacher | teacher | (instructor, no chair) |
| qa.chair_head | chair_head | chair «Proqramlaşdırma və informasiya təhlükəsizliyi» (244aec47) |
| qa.dean | dean | faculty «Dizayn» |
| qa.program_coordinator | program_coordinator | «Dizayn (Qrafik)» |
| qa.exam_center_head | exam_center_head | — |
| qa.ikt_rehber | ikt_rehber (RİM) | — |
| qa.rector | rector | **is_superuser** (excluded from escalation probes — it legitimately bypasses) |

---

## Findings

### F-1 (Low) — FİN enumeration oracle on the profile-completion page
- **Endpoint / role:** `POST /accounts/complete-profile/` — any authenticated, gated user (first login).
- **Request:** `{"fin": "<a FİN already registered to another user>", "phone": "0501234567", "email": "x@example.com"}`
- **Response:** `200` with a validation error containing “…artıq istifadə olunub” (already in use). A *fresh* FİN is
  accepted (`302`). The two outcomes are distinguishable, so the page is an oracle that confirms/denies whether a
  given FİN belongs to an existing account (`UserProfile.fin` is `unique=True`).
- **Impact:** Low. Lets an authenticated user confirm a specific person’s FİN (a semi-sensitive national ID). The
  7-char FİN space (~36⁷) makes bulk harvesting impractical, and the window is the narrow first-login state, but
  targeted confirmation is possible and the endpoint showed **no per-user rate limit**.
- **Fix:** return a generic “could not save, check your details” error that does not distinguish “already used” from
  “invalid”, and/or add a write-rate-limit bucket (like `score_write_rate_limited`) to this POST.
- **Likely file:** `apps/accounts/services/profile_completion.py` (duplicate handling) and
  `apps/accounts/views/auth/profile_completion.py`.

### F-2 (Low) — `exams:user_search` returns the whole university directory to any teacher
- **Endpoint / role:** `GET /exams/lookups/users/?q=a` — any **teacher-level** account (qa.teacher, qa.chair_head,
  qa.exam_center_head all returned `200`; qa.student correctly `403`).
- **Response (truncated):** `{"results":[{"id":"5400","text":"1 1"},{"id":"3453","text":"Aaed YA Abumuaileq"},
  {"id":"2397","text":"Aaliyah Jumaday"}, …]}` — real full names of the entire user base, keyed by **sequential
  integer IDs**, with no faculty/group scoping. `exams:subject_search` similarly returns the full subject catalogue;
  `exams:invigilator_search` exposes teacher usernames + kafedra (only to exam_center_head, which is expected).
- **Impact:** Low. Directory enumeration (names + sequential internal IDs) available to every teacher. Likely
  intended for building exam groups (a teacher may enrol any student), but the sequential IDs also aid IDOR probing
  elsewhere.
- **Fix:** confirm product intent; if teachers should only pick from their own faculty/groups, scope the queryset;
  consider opaque IDs; keep the existing `q` minimum-length and the teacher gate.
- **Likely file:** `apps/exams/views/teacher/exams/lookups.py` (`user_search`, `_ensure_teacher`).

### F-3 (Info) — Pages reachable while the profile-completion gate is active
- `GET /live/` (live-exam PIN lobby) and `/jsi18n/` return `200` to a gated user; `/exams/*` is gate-exempt too but
  the exam endpoints enforce their **own** authz (e.g. `/exams/lookups/users/` → `403` for the gated student).
- **Assessment:** by design — the gate intentionally exempts `/exams/`, `/live/…` and static so exam/QR-PIN flows
  are never interrupted (documented in `middleware_profile_completion.py`). No privileged data was reachable. No
  action required; recorded for completeness.

### F-4 (Info) — Soft-deny (200 + `has_access:false`) instead of 403 on three read endpoints
- `GET /accounts/people/academic/groups/`, `/accounts/journal-hygiene/rows/`, `/accounts/legacy-review/groups/`
  return `200 {"has_access": false, "results": []}` to unprivileged users rather than `403`.
- **Assessment:** no data leak (empty payload), but the pattern is inconsistent with the rest of the codebase
  (which returns `403`). Minor hardening/consistency nit.

---

## Not exercised (coverage gaps → defer to SEC-1 code review)
- **LogQL injection in monitoring log filters** (`/api/superadmin/monitoring/logs/`): the whole monitoring surface is
  superadmin-only and returned `401` (anon) / `403` (every test role), so the LogQL filter could not be reached
  dynamically with the available accounts. Recommend SEC-1 verify the LogQL query is built with proper
  label/line-filter escaping server-side.
- **Stored XSS in role-gated write fields** (movement/exemption reason, lesson topic, room text, group names,
  syllabus learning outcome, notification text): because every write probe was rolled back, stored values could not
  be round-tripped to a rendered page. Static signal is reassuring — no `|safe`/`mark_safe` on these fields in the
  relevant templates (only one `escapejs` use, which is correct), and reflected contexts that were testable
  (login `?next=`, contact form redisplay) are auto-escaped. Recommend SEC-1 confirm the detail templates render
  these fields through Django auto-escaping.
- **Oversized inputs:** partially covered — `complete-profile` truncates each field to `spec.max_length` server-side;
  workload/journal IDs go through `core.http_ids.parse_uuid` (bad value → “not found”, no 500). A full fuzz of every
  new form was not done.

---

## Test matrix

### 1. Vertical / horizontal privilege escalation (state-changing POST; rollback-wrapped)
Expectation: `403` (missing key) / `404` (out of scope) / `409` (state conflict) — all **non-destructive**.

| Endpoint | qa.student | qa.teacher | qa.chair_head | qa.dean | Result |
|---|---|---|---|---|---|
| `workload:row_save` (OTHER chair’s task 0a06947c) | 403 | 403 | 403 | 403 | PASS |
| `workload:amend` (OTHER chair’s task) | 403 | 403 | 403 | 403 | PASS |
| `workload:assign` (OTHER chair’s row 349fcb7a) | 403 | 403 | 403 | 403 | PASS |
| `workload:row_delete` (OTHER chair’s task) | 403 | 403 | 403 | 403 | PASS |
| `workload:row_save` (chair_head’s OWN task) | 403 | 403 | **409 (owner reached service)** | 403 | PASS (positive control) |
| `workload:unassign` (chair_head’s OWN assignment) | 403 | 403 | **409 (owner reached service)** | 403 | PASS (positive control) |
| `accounts:system_settings_save` (RİM-only) | 403 | 403 | 403 | 403 | PASS |
| `registrar:journal_subject_exempt` (foreign offering) | 403 | 403 | 403 | 404 | PASS |
| `registrar:journal_subject_exempt_restore` | 403 | 403 | 403 | 404 | PASS |
| `organizations:group_action` (qku) | 403 | 403 | 403 | 403 | PASS |
| `accounts:people_action` (unblock) | 403 | 403 | 403 | 404 | PASS |
| `accounts:schedule_manage_action` | 403 | 403 | 400 | 400 | PASS |
| `accounts:schedule_editor_action` (`action=plan`) | 403 | 403 | 403 | 403 | PASS |

The owner positive-control reaching the service (`409`, not `403`) proves the `403`s are genuine authorisation
denials, not a blanket failure.

### 2. Vertical escalation (read / GET)
| Endpoint group | anonymous | role-less authed (qa.student) | Result |
|---|---|---|---|
| `monitoring:*` (summary/server/logs/security-events/incidents/…11) | 401 | 403 | PASS |
| `accounts:people_list / options / analytics` | 302→login | 404 | PASS |
| `workload:teachers / options / curriculum / my_rows` | 302→login | 403 | PASS |
| `timetable:home / availability / policies` | 302→login | 403 | PASS |
| `exams:*_search` (subjects/users/groups/invigilators) | 302→login | 403 (student) | PASS (see F-2 for teacher) |
| `organizations:settings` (qku) | 302→login | 302→profile | PASS |
| `accounts:people_academic_groups / journal_hygiene_rows / legacy_review_groups` | 302→login | 200 `has_access:false` | PASS (see F-4) |

### 3. Profile-completion gate bypass (user: `sec2.gate`, student membership, empty FİN/phone/email)
| Vector | Result |
|---|---|
| `/`, `/jurnal/`, `/accounts/profile/`, `/elanlar/` | 302 → `/accounts/complete-profile/` (gate fires) — PASS |
| `/exams/lookups/users/` (gate-exempt prefix) | 403 by endpoint’s own authz — PASS |
| `/live/`, `/jsi18n/` (gate-exempt) | 200, non-privileged lobby/catalogue — PASS (F-3) |
| `//jurnal/`, `/exams/../jurnal/`, `/jurnal/%2e/`, `/jurnal/.` | 302→gate / 404 (no normalisation bypass) — PASS |
| AJAX / `HX-Request` / `Accept: application/json` | 403 JSON `profile_completion_required` (no data) — PASS |
| Open redirect `?next=https://evil.example`, `//evil`, `/\evil`, `https:evil` | sanitised to empty (`_safe_same_origin_redirect_path`) — PASS |

### 4. Open redirect / reflected XSS on login
| Vector | Result |
|---|---|
| `POST /accounts/login/telebe/?next=https://evil.example/` (valid creds) | 302 → `/accounts/kabinet/` (external next ignored) — PASS |
| `?next=//evil.example/` | 302 → `/accounts/kabinet/` — PASS |
| reflected `next="/><script>alert(1)</script>` | escaped (`&lt;script&gt;`), no raw script — PASS |

### 5. CSRF (user: gate-exempt qa.ikt_rehber)
| Request | Result |
|---|---|
| `POST system_settings_save` no token | 403 — PASS |
| `POST people_action` no token | 403 — PASS |
| `POST organizations group_action` no token | 403 — PASS |
| `POST login` no token | 403 — PASS |
| `POST system_settings_save` **with** valid token | 200 (CSRF passes; unknown key ignored, nothing persisted) — PASS |
| `GET /accounts/logout/` (side-effect via GET?) | 405 (POST-only) — PASS |

### 6. Password policy (server-side `validate_password`, the single source all flows use)
| Password | Result | Expected |
|---|---|---|
| `abc`, `1234567` | REJECTED (min 8) | PASS |
| `12345678`, `password` | REJECTED (blocklist) | PASS |
| `sec2.lock` (= username) | REJECTED | PASS |
| `hello123`, `19850412` | ACCEPTED | PASS (intentionally-simple owner policy, 2026-10-15) |

Validators active: `apps.accounts.password_policy.MinimumLengthValidator`, `TrivialPasswordValidator`.

### 7. Login lockout / rate limit (live `:8011`, user `sec2.lock`, one burst)
| Attempt | Status |
|---|---|
| 1–9 (wrong) | 200 (login re-rendered) |
| 10 (wrong) | 200 with countdown text («cəhd», «gözlə») |
| 11–12 (wrong) | **429** lockout/countdown page |

Device-scoped lockout fires at ~10 attempts, matching `login.device_rate = 10/10m`. PASS.

---

## Test users / objects created and cleaned up
| Object | Purpose | Cleanup |
|---|---|---|
| `sec2.gate` (user 9677) + student Membership + UserProfile | profile-gate / redirect / FİN-enum tests | **deleted** |
| `sec2.lock` (user 9678) + student Membership + UserProfile | password-policy / CSRF / lockout tests | **deleted** |

Verified post-cleanup: 0 `sec2.*` users remain; `RuntimeSetting` = 10 rows (unchanged); `TeachingTaskRow` = 824
(unchanged); no junk runtime setting written. Residual: a `sec2.lock` device/account rate-limit bucket on the live
`:8011` process will expire on its own (~10 min, device/account-scoped to the deleted throwaway account; localhost IP
bucket is 300/10m and unaffected). All write probes were rolled back — no real rows were modified.

Scripts: `/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/sec2/`
(`probe_authz.py`, `inspect_200s.py`, `probe_writes.py`, `probe_gate.py`, `probe_misc.py`, `probe_csrf_xss.py`,
`probe_lockout.py`).
