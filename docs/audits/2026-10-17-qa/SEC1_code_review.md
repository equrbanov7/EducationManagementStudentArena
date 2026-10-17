# SEC-1 — code-level security review (2026-10-17)

Scope: code that changed from 2026-10-07 to 2026-10-17 (`git log --since=2026-10-07`, 231 commits), as listed in the SEC-1 brief.
Method: read-only review of the code. Two small scratch tests ran against the sandbox test DB at `:55432`. They live in
`/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/sec1/`, not in the repo.
I did not touch production and did not change repo code.

I did not re-report issues that are already fixed: the 2026-10-07 audit, the WS zone/2FA gate, superadmin LAN-only, and the role-audit decisions.

## Summary

| # | Severity | Area | Title |
|---|----------|------|-------|
| F1 | Medium | profile completion | Unlimited FİN / e-mail «belongs to another account» oracle. Nothing is written, and each probe adds an audit row |
| F2 | Medium | profile completion → intake | A self-asserted (unverified) FİN becomes the identity key. Anyone can squat another person's FİN, and the ATİS/intake row for the real person is then skipped |
| F3 | Medium | `blocked_accounts_report` unblock | The bulk unblock ignores the block reason, so it re-enables accounts blocked for `security`, `employment_ended` or `discipline` |
| F4 | Low | monitoring logs | The Loki log tab is unscoped for non-superadmin viewers (`system.monitoring.view`). Logs are only secret-scrubbed, not PII-scrubbed, and include reset-link paths |
| F5 | Low | password policy | One weak policy for every account, privileged ones included. All-digit/date passwords are accepted and the minimum can be lowered to 6 |
| F6 | Low | profile-completion gate | The allow-list is broader than the stated intent: all of `/exams/` (staff exam management too) is exempt, and the actor in view-as is never gated |
| F7 | Low | `prod-data-ops.yml` | Audit attribution goes to «the oldest active superuser» (a real person). Input validation is line-based grep; there is no injection, because the args are arrays |

Counts: **Critical 0 · High 0 · Medium 3 · Low 4**

---

## F1 — Medium — FİN / e-mail existence oracle on «Məlumatlarınızı tamamlayın» (unlimited, non-destructive)

**Where**
- `apps/accounts/services/profile_completion.py:61-64`: `_fin_taken()` is a global `UserProfile.objects.filter(fin=…)`.
- `apps/accounts/services/profile_completion.py:67-70`: `_email_taken()`.
- `apps/accounts/services/profile_completion.py:100-106` and `:136-142`: conflicts are reported per field even when another field fails validation, and then nothing is written.
- `apps/accounts/services/profile_completion.py:139`: every conflicting attempt writes an `AuditLog` row.
- `apps/accounts/views/auth/profile_completion.py:43-49` and `apps/accounts/urls.py:33`: there is no rate limit on the POST.

**Flow.** Any logged-in student or staff member who still has an empty FİN posts to `/accounts/complete-profile/`.

- If the FİN exists on any other account, the response carries «Bu FİN kod başqa hesabda qeydə alınıb…».
- If the attacker also has an empty phone, they send `phone=x`. Validation then fails, so **nothing is ever saved** and they can probe forever.

E-mail works the same way («Bu e-poçt ünvanı istifadə oluna bilməz»), against the canonical (NFKC/lower) index.

**Exploit.** Any student whose FİN or phone is still empty (the default for new and staged accounts) can do the following:
- confirm whether a known person (FİN from an ID card, or a personal e-mail) has an account in the university system;
- flood `AuditLog` with `profile_completion_conflict` rows, one per request (log/audit DoS).

The «kimə aid olduğu SÖYLƏNMİR» comment is true, but existence alone is still disclosed.

**Proof.** The scratch test `sec1/test_sec1_fin_oracle.py` reuses the fixture from `apps/accounts/tests/test_profile_completion_2026_10_17.py`. A teacher with no FİN and no phone sent 40 POSTs with `fin=OTHER_FIN, phone=x`:

- all 40 returned 200 with the conflict text;
- a free FİN returned no conflict text;
- `profile.fin` stayed empty;
- `SEC1 audit rows added by 40 probes: 40`.

Result: `1 passed`.

**Fix**
1. Rate-limit the POST per user and per IP with `core.rate_limit.record_rate_limit_hit`. Something like `("profile_completion", "10/1h", user.pk)` fits; after the limit, return the form with a generic error.
2. Run the uniqueness checks **only when every field is otherwise valid**. Then a probe must commit a real FİN, which ends the oracle after one try.
3. Write the conflict audit row at most once per user per hour, or count conflicts in a cache key.

---

## F2 — Medium — a self-asserted FİN becomes the identity key (squatting blocks ATİS/intake)

**Where**
- `apps/accounts/services/profile_completion.py:112-114`: any well-formed FİN that is not yet taken is stored on the caller's profile, unverified.
- `apps/accounts/services/intake/validate.py:194-196` together with `:312-314`: the ATİS / student and teacher intake treats an existing FİN as «Bu FİN artıq sistemdə var — sətir ötürülür» (`plan.skip("fin_exists")`).
- Module docstring at `validate.py:10`: «FİN kimliyin açarıdır».

**Flow.** FİN used to come only from official sources (ATİS, RİM, intake). The new gate lets **every** account without a FİN type one in, with no check against an official record. `UserProfile.fin` is globally unique, so the first person to write a value owns it.

**Exploit.** A student or staff member with no FİN types the FİN of someone who has no account yet. Examples are an incoming first-year, a new teacher, or a classmate whose ATİS record has not been imported. FİN is printed on the ID card, so people around the target can see it.

On the next ATİS/intake import, the victim's row is **skipped** and their account is never created. RİM sees only «fin_exists». A typo (a valid-format FİN that belongs to someone else) causes the same collateral damage without malice. If it is later «fixed» by merging, the merge may attach the official record to the wrong account.

**Proof.** Code path: `complete_profile()` → `_write()` saves the FİN, then `validate.py:312` skips the real person's row.

**Fix** (pick one or combine):
- mark self-entered FİN as unverified, for example a `fin_source="self"` or `fin_verified_at` field. In intake, an unverified FİN must not block an official row: flag the conflict and let the official row win, or route it to RİM review;
- or do not let the gate write FİN at all for accounts that intake is expected to fill (students). Collect it as a «pending FİN» that RİM confirms.

At minimum, add a «self-entered FİN conflicts with import» report for RİM.

---

## F3 — Medium — `blocked_accounts_report --apply-unblock-teachers-with-load` ignores the block reason

**Where**
- `apps/accounts/services/blocked_accounts.py:298-300`: `_can_unblock()` checks only `status == blocked`, `flag == teacher_with_load` and not-student. It never looks at `block_reason_code` or `block_source`, even though `_block_source()` at `:148-151` already tells apart `teacher_roster` (automatic, the case the owner wanted fixed) from `manual`.
- `apps/accounts/services/account_deletion.py:470-495`: `unblock_account()` sets `is_active=True` and **wipes** `block_reason`, `block_reason_code`, `block_contact_*` and `blocked_*`. Only the audit row keeps the history.
- `.github/workflows/prod-data-ops.yml:795-806`: the `create_missing=true` + `apply=true` path calls it for the whole organisation.

**Flow.** Any blocked account counts as «teacher with current load» if:
- it has a teaching role, **or**
- it has any current-semester `TeacherAssignment`, `CourseOffering.instructor` or slot.

Such an account is re-activated in bulk. The block catalogue (`account_block_reasons.REASONS`) includes:
- `security` («Hesabın təhlükəsizliyi (şübhəli giriş)»);
- `employment_ended`;
- `discipline`.

**Exploit / impact**
- A teacher account blocked because it was **compromised** still has its load rows, so the bulk unblock re-enables it. The attacker's known password still works, because unblock does not reset it.
- A teacher whose contract ended, but whose load was not yet re-assigned, is reactivated and regains journal and grade access.

This is an operator-triggered action. The operator does not choose which reasons it covers, and the workflow summary shows only counts.

**Proof.** Scratch test `sec1/test_sec1_unblock_reason.py`: `Row(status=blocked, roles={"teacher"}, block_reason_code in {"security","employment_ended","discipline"}, block_source="manual", assignments=1)` makes `_can_unblock()` return `True` for all three. Result: `1 passed`.

**Fix.** Restrict `_can_unblock` to `block_source == "teacher_roster"`, the automatic Forma-7 block. Alternatively, use an allow-list of reason codes that excludes `security`, `employment_ended` and `discipline`. Write the other rows to the CSV as `needs_manual_review`. Consider printing a per-reason counter in the workflow summary.

---

## F4 — Low — monitoring «Loglar» tab: platform-wide container logs for org-scoped viewers, secrets-only scrub

**Where**
- `apps/monitoring/views.py:119-133`: `logs_api` is behind `monitoring_view_required` (superadmin **or** `system.monitoring.view`, granted to RİM rəhbəri).
- `apps/monitoring/logs.py:29,34-45`: the default selector is `{job="docker"}` (every container), and `container` accepts any label value.
- `apps/monitoring/logs.py:90`: lines go only through `redact_secrets`. The PII scrubber `scrub_personal` exists, but only the AI summary uses it.
- `docker/nginx/nginx.conf:26`: the access log records `$uri`, which includes `/accounts/reset/<uidb64>/<token>/`. The reset e-mail contains that link (`apps/accounts/forms/auth/login.py:166-168`).

**Flow and impact.** Every other tenant-row endpoint in this module filters by `scope.organization_id`. Logs do not: a non-superadmin viewer sees every container (nginx, app, postgres, celery), including client IPs, usernames in paths, user agents, and password-reset link paths.

The reset-link token alone is **not** enough to take an account over. `OTPPasswordResetConfirmForm` (`apps/accounts/forms/otp.py:80-114`) also requires the e-mailed OTP, which allows 5 attempts. That is why this is Low.

LogQL injection: none found. `search` sits inside a backtick raw string and backticks are stripped. `container` is JSON-quoted. `level` comes from an allow-list.
One functional bug: in raw backtick strings the `\` → `\\` doubling makes a search for a backslash miss.

**Fix.**
- For a non-platform scope, either restrict `container` to an allow-list of app containers, or run `scrub_personal` (or at least mask `/accounts/reset/[^/]+/[^/]+/`) on the lines.
- Mask reset paths in nginx with a `map $uri $loggable_uri`.
- Drop the backslash doubling.

---

## F5 — Low (design risk, owner decision 2026-10-15) — single weak password policy for every role

**Where**
- `apps/accounts/password_policy.py:30-64,73-100`: length plus a 13-entry deny-list plus the username; no other rule.
- `core/runtime_settings.py:202-210`: `password.min_length` can go down to **6**.
- `config/settings/components/security.py:16-19`.

**Risk.** Superadmin, RİM, exam-centre heads and HR get the same rule as students. Passwords like 8-digit dates, `qwerty123` or `Bakı2026` are accepted. The only defence is the login buckets:
- account bucket defaults to `20/1h` and can be raised to 200;
- the IP bucket can be 5000.

That gives a targeted dictionary attack roughly 480 guesses per day per account, spread across IPs. Superadmin is LAN-only and `/manage` has admin 2FA, which mitigates the top tier. RİM and exam-centre heads have no second factor on the main site.

**Fix** (keeps the owner's «simple for teachers» intent):
- keep the simple rule for `student`/`teacher`;
- for privileged role families (`role.assign`, `journal.correct` org-wide, `exam_center.decide`, `system.*`), require at least 10 characters plus Django's `CommonPasswordValidator`, or the existing OTP as a second factor.

Also lift the runtime minimum's floor to 8.

---

## F6 — Low — profile-completion gate allow-list is wider than intended

**Where:** `apps/accounts/middleware_profile_completion.py:69,113-118` (`EXAM_PREFIXES = ("/exams/",)`) and `:80` (view-as).

**Flow.** The stated intent is that students must never be stopped on exam day. In practice:
- every `/exams/` route is exempt for **every** role: teacher exam management, exam-centre/PIN lookup, appeals and so on;
- `request.is_view_as` turns the gate off for the **actor** too, so an actor with missing fields who enters view-as browses without completing.

`/i18n/`, `/live/…`, admin and the reset paths are fine. `next` is safe: `_safe_same_origin_redirect_path` rejects `//` and `/\`. Mass assignment is prevented, because only fields reported as missing are written.

This is a data-quality control, not a security boundary, hence Low.

**Fix.**
- Exempt only the student attempt and final-waiting routes, for example `/exams/<id>/take/`, `/exams/final/…` and the attempt APIs, or exempt only the student role family under `/exams/`.
- For view-as, check the actor (`request.view_as_actor`) instead of skipping the gate.

---

## F7 — Low — `prod-data-ops.yml`: audit attribution and line-based validation

**Where**
- `.github/workflows/prod-data-ops.yml:322-324,621-623,721-723,801-803`: `--actor` is «the oldest active superuser» (`order_by('date_joined').first()`).
- `:427,445,404,638`: the `printf '%s' "$v" | grep -Eq '^…$'` validations.
- `:492`: `echo "::group::▶ $COMMAND ${args[*]}"`.

**Notes**
- Injection: **none**. Every `${{ }}` sits in `env:`, never in `run:`. Arguments are passed as bash arrays (`"${args[@]}"`). Tags and dates are regex-checked. `STAFF_PLAN_KEY` is used through `-pass env:`. Reports are encrypted, `umask 077` is set, and temp files are removed with `always()`.
- Attribution: the destructive commands record a real person as the actor even though a workflow ran them. This affects non-repudiation, and is now also true for `blocked_accounts_report` unblock, `backfill_teacher_lessons` and `assign_task_rows_from_timetable`. Recommendation: use a dedicated service account (`ops.workflow`, `is_active`, unusable password) or pass `github.actor` as reason metadata.
- `grep -Eq` checks lines one at a time. A value with an embedded newline (possible through the API dispatch) passes if *any* line matches. Arrays keep it harmless, but use `[[ "$v" =~ ^…$ ]]` for real whole-string checks.
- `:492` prints all args to the job log. For `teacher_map`, these are teacher names mapped to usernames (PII in logs; the repo is private). Consider masking the arguments of `--teacher`.

---

## Reviewed and found OK (no finding)

- **Subject exemption** (`apps/registrar/subject_exempt*.py`):
  - the order is tenant (`offering_or_404`) → key (403) → scope (404) → roster lock (409);
  - enrollments and decisions are fetched with `organization=…, offering=…`;
  - POST only, CSRF protected; view-as POST is blocked by middleware.
- **Group drawer «Bərpa et»** (`apps/organizations/group_students.py`, `registrar/movements.py`):
  - `removed_rows` is read-only and scoped through `_visible_group`;
  - reinstatement goes through `student_registry_action` (rate-limited, `people.resolve_actor`) and `create_movement`;
  - the reason being optional is fine, since the order number and date are still mandatory.
- **Workload amendment API** (`apps/workload/services/row_edit.py`, `views/distribution_api.py`):
  - every write path calls `ensure_can_manage` / `ensure_can_distribute` before `open_amendment`;
  - rows and assignments are fetched with `task=instance` and UUIDs are parsed;
  - `row.task_id != task.pk` is checked; `_ensure_editable` still gates the status.
- **Schedule editor `action=plan` + room select** (`accounts/views/schedule_editor.py`, `registrar/schedule_suggest.py`, `schedule_rooms.py`):
  - groups come from `scoped_groups` (403) and periods are org-filtered (404);
  - clashes are masked by `scope_visible`;
  - the room is posted as text only, so there are no room-id IDORs;
  - save validates the instructor with `authorized_teacher_ids`.
- **Journal lesson room prefill** (`journal_lesson_prefill.py`, `lesson_rooms.py`): `resolve_lesson_room` is org-plus-active scoped, so a foreign or invalid id becomes `None`.
- **Contact / trial reply sender** (`core/mailing.py`, `apps/contact`, `apps/trial_exams`):
  - IP, e-mail and user rate limits are still in place;
  - the sender is fixed (`sender_address()`), so «from» can no longer be chosen;
  - e-mail HTML templates have no `|safe`; `autoescape off` appears only in the `.txt` base.
- **dedupe_notifications**: marks rows read only (no delete), defaults to dry-run, filters by type and date, outputs counts only.
- **ensure_parent_groups**: dry-run rollback, idempotent, outputs counts only.
- **New JS in the window** (monitoring renderers, `teaching_office_groups.js`, `workload_my.js`, `workload_distribution_*`, schedule planner/room): every server string reaching `innerHTML` goes through `esc`/`escapeHtml`.
- **New `mark_safe`/`format_html`** (`exam_score_cells.py`): values pass through `format_html`.
- **Other new endpoints in the window**: exam-centre duty create/revoke/note, final device-change, key-correction apply/revoke, group lead, HR analytics export. Each does an object-level org/room check, POST + CSRF, and the export uses formula-safe `sheet_append`.
- **New `bypass_rls()`** in request paths: ws_gate, device_binding, live join roster prefetch, block notice. Each is keyed to the caller's own identity or session, or happens before tenant context exists. No over-broad use was found.

## Scratch tests

```
DATABASE_URL=postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432/emsarena_agent \
venv/bin/pytest --ds=config.settings.test -p no:cacheprovider -s --rootdir=. \
  /private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/sec1/test_sec1_fin_oracle.py::FinOracle::test_oracle_unlimited_and_non_destructive \
  /private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/sec1/test_sec1_unblock_reason.py
```

Both passed: F1 showed `40 probes → 40 audit rows, nothing saved`, and F3 showed `_can_unblock=True` for the security, employment_ended and discipline reasons.
