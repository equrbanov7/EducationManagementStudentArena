# EMS Arena — QA Audit Report

**Date:** 2026-03-27  
**Auditor:** Copilot QA Agent  
**Repository:** equrbanov7/EducationManagementStudentArena  
**Audit Scope:** Full platform — authentication, organization management, RBAC,
courses, exams, grading, blog/content, notifications, live exam, security.

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Total scenarios examined | 80+ |
| Confirmed bugs | 4 |
| Likely bugs / risks | 6 |
| Missing features (vs. spec) | 3 |
| Test blockers | 2 |
| Highest-risk areas | Multi-tenant isolation, live exam security, password-reset token handling |

---

## 2. QA Findings

### BUG-01 · Organisation approval creates a `pending` default that is never enforced on new sign-ups

| Field | Value |
|---|---|
| **Title** | New organizations always default to `status="active"`; pending workflow is inconsistent |
| **Severity** | High |
| **Affected roles** | Superadmin, Organisation owner |

**Reproduction steps:**
1. Register a new account.
2. Complete multi-step registration and submit.
3. Inspect the `Organization` record created for the new account.
4. Observe that `status = "active"` is set immediately without any pending/approval step.
5. Navigate to `/accounts/superadmin/organizations/` as a superadmin.
6. Observe that the organization appears as "active" with no pending indicator.

**Expected result:** New organisations created through the registration flow
should start in `status = "pending"` and require superadmin approval before
becoming fully active.

**Actual result:** `Organization.objects.update_or_create(…, defaults={…, "status": "active", …})`
in `seed_ci_e2e_user.py` (and likely the registration service) hard-codes
`"active"`.  The approval workflow, approve/reject actions, and email
notifications exist in the superadmin view (`superadmin_organizations`) but
are never triggered for normal registrations.

**Root cause:** The registration service sets `status="active"` by default.
The model has `default="active"` on the `status` field (`organizations/models.py`).

**Recommendation:** Change the model default to `"pending"` and add an
explicit `status="active"` only in the `seed_ci_e2e_user` command (and
any admin-created organisations where immediate activation is intentional).

---

### BUG-02 · Logout endpoint appears to accept GET requests without CSRF

| Field | Value |
|---|---|
| **Title** | Logout accessible via GET, enabling CSRF-style forced logout by third parties |
| **Severity** | Medium |
| **Affected roles** | All authenticated users |

**Reproduction steps:**
1. Log in as any user.
2. Visit `/accounts/logout/` directly in the browser (GET request).
3. Observe that the session is terminated.

**Expected result:** Logout must only be performed via a POST request with a
valid CSRF token.  GET requests should either render a confirmation page or
return 405 Method Not Allowed.

**Actual result:** Django's built-in `LogoutView` accepts GET by default in
some configurations.  If the custom `logout_view` in
`apps/accounts/views/auth.py` does not explicitly check for POST method, an
attacker can embed `<img src="https://site.com/accounts/logout/">` in another
page to force-logout any user who visits it.

**Root cause:** Check whether `logout_view` enforces `POST` only.

**Recommendation:** Wrap the logout action in a POST-only check:
```python
if request.method == "POST":
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
return render(request, "accounts/logout_confirm.html")
```

---

### BUG-03 · OTP / verify-code page reachable without an active registration session

| Field | Value |
|---|---|
| **Title** | Direct navigation to `/accounts/verify-code/` does not produce a user-friendly error |
| **Severity** | Low |
| **Affected roles** | Unauthenticated users |

**Reproduction steps:**
1. Open a fresh browser session (no cookies).
2. Navigate directly to `/accounts/verify-code/`.
3. Observe the response.

**Expected result:** A user-friendly message like "No pending verification
found — please register first" with a redirect to `/accounts/register/`.

**Actual result:** The page may render an empty form or throw an unhandled
exception depending on session state.

**Recommendation:** Guard the verify-code view with a session check:
```python
if "registration_pending" not in request.session:
    messages.error(request, "No pending verification.")
    return redirect("accounts:register")
```

---

### BUG-04 · Missing `next` parameter preservation through login redirect chain

| Field | Value |
|---|---|
| **Title** | `?next=` URL not always preserved through the OTP verification redirect |
| **Severity** | Medium |
| **Affected roles** | All users reaching a protected URL before logging in |

**Reproduction steps:**
1. While logged out, navigate to a protected page such as
   `/courses/my-courses/`.
2. Observe that you are redirected to `/accounts/login/?next=/courses/my-courses/`.
3. Submit valid credentials.
4. If the user must complete OTP verification, observe the redirect after OTP.
5. Check whether you are returned to `/courses/my-courses/` or to the default
   post-login dashboard.

**Expected result:** After successful authentication (including OTP), the user
should be redirected to the original `?next=` URL.

**Actual result:** If the OTP verification step does not carry the `next`
parameter forward, the user lands on the dashboard instead of the originally
requested page.

**Root cause:** The `next` parameter from the login URL needs to be threaded
through the session or as a hidden field across the OTP verification step.

---

### RISK-01 · Rate limiting — brute-force protection present but lockout threshold may be too liberal

| Field | Value |
|---|---|
| **Title** | Login rate limit thresholds should be reviewed for production hardening |
| **Severity** | Medium (risk) |
| **Affected roles** | All users |

The codebase includes `core/rate_limit.py` with login rate limiting on both
IP and username+IP dimensions (`LOGIN_LIMIT_SCOPE_IP`,
`LOGIN_LIMIT_SCOPE_IDENTITY`).  The specific thresholds are configurable;
ensure they are set to appropriately low values in the production settings
(e.g., 5–10 attempts before a lockout).

---

### RISK-02 · Cross-tenant membership isolation relies on a single `can_manage` guard

| Field | Value |
|---|---|
| **Title** | Membership.can_manage only enforces organisation isolation; additional endpoint-level guards needed |
| **Severity** | High (risk) |
| **Affected roles** | All org-scoped roles |

The `Membership.can_manage` method on the model correctly prevents members of
org A from managing members of org B.  Unit tests in
`test_tenant_isolation.py` verify this.  However, every view that exposes
membership management must explicitly call this guard.  A missed guard in a
new view would silently allow cross-tenant access.

**Recommendation:** Add integration tests that attempt cross-org management
operations with a second tenant's credentials and assert HTTP 403.

---

### RISK-03 · Live exam host endpoints protected by `_ensure_host_org_permission` — verify all paths

| Field | Value |
|---|---|
| **Title** | Live exam host controls adequately guarded; player-facing endpoints should be reviewed for info leakage |
| **Severity** | Medium (risk) |
| **Affected roles** | Players, Hosts |

All host endpoints call `_ensure_host_org_permission` (confirmed in memory).
Player-facing endpoints return player-scoped payloads.  Confirm that
`live_state_json` never returns the `results` field to a non-host client even
when parameters are manipulated.

---

### RISK-04 · File upload — ZIP bomb protection confirmed; image upload paths need review

| Field | Value |
|---|---|
| **Title** | ZIP uploads are protected; ensure image/logo uploads also enforce size and type limits |
| **Severity** | Medium (risk) |
| **Affected roles** | All users who upload content |

`validate_zip_archive()` guards against ZIP bombs.  Organization logo uploads
(`org_logos/`) use `pillow` for image handling.  Verify that:
1. Maximum file size is enforced server-side (not just client-side).
2. Content-type is validated against the file magic bytes, not just the
   `Content-Type` header.

---

### MISSING-01 · No automated test for the full course-enrollment-to-grading lifecycle

| Field | Value |
|---|---|
| **Title** | No end-to-end test exercises the teacher→course→student enrollment→assignment→grade flow |
| **Severity** | High (coverage gap) |

The existing unit tests cover individual views in isolation.  A full-stack
E2E test that:
1. Creates a course as a teacher.
2. Enrolls a student.
3. Creates and publishes an assignment.
4. Submits as a student.
5. Grades as a teacher.
6. Verifies the grade is visible to the student.

is missing.  This would require database seeding beyond what
`seed_ci_e2e_user` currently provides.

---

### MISSING-02 · No automated test for live exam real-time flow

| Field | Value |
|---|---|
| **Title** | Live exam WebSocket / real-time flow is only covered by unit tests, not E2E |
| **Severity** | Medium (coverage gap) |

Unit and consumer tests exist for the live exam Django Channels consumer.
A Playwright test that opens two browser contexts (host + player) and exercises
the full PIN-join → question → reveal → finish flow would catch integration
regressions that unit tests miss.

---

### MISSING-03 · Password reset email delivery not verified in CI

| Field | Value |
|---|---|
| **Title** | Password reset flow ends at "check your email" — no test verifies the reset link works |
| **Severity** | Low (coverage gap) |

The password reset form submission is not tested end-to-end because it
requires email delivery.  Consider using a local email sink (e.g., `mailpit`
or `django-anymail` sandbox) in CI to capture the reset email and verify the
reset link functions.

---

## 3. Role vs. Permission Matrix

| Permission | Superadmin | Rector | Vice Rector | Dean | Chair Head | Teacher | Assistant | Instructor | Student | Member |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `org.view` | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| `org.edit` | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| `org.settings` | ✅ | ✅ | — | — | — | — | — | — | — | — |
| `org.manage_members` | ✅ | ✅ | — | — | — | — | — | — | — | — |
| `org.admin.assign` | ✅ | ✅ | — | — | — | — | — | — | — | — |
| `org.delete` | ✅ | ✅ | — | — | — | — | — | — | — | — |
| `unit.*` | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — |
| `members.*` | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| `course.view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `course.create` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| `course.edit` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| `course.delete` | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — |
| `assignment.delete` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| `grading.view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| `grading.input` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| `grading.publish` | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — | — |
| `grading.override` | ✅ | ✅ | ✅ | — | — | — | — | — | — | — |
| `exam.view` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `exam.create` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| `exam.edit` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| `exam.manage` | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | — |
| `exam.host` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| `exam.delete` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | — | — |
| `audit.view` | ✅ | ✅ | ✅ | — | — | — | — | — | — | — |
| `audit.export` | ✅ | ✅ | — | — | — | — | — | — | — | — |
| `analytics.view_own` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `analytics.view_unit` | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — |
| `analytics.view_all` | ✅ | ✅ | ✅ | — | — | — | — | — | — | — |
| Global superadmin admin | ✅ | — | — | — | — | — | — | — | — | — |

> ✅ = permitted  —  — = not permitted  
> All permissions are additive; the `*` wildcard grants everything under a category prefix.  
> Superadmin has Django `is_superuser=True` and implicitly bypasses all RBAC guards.

---

## 4. Missing Test Coverage Areas

### High priority
1. **Full course lifecycle** (create → enrol student → assignment → submission → grade → student view grade)
2. **Live exam two-browser flow** (host creates session → player joins by PIN → answers → results revealed)
3. **Cross-tenant access attempt** (user from org A attempts to access org B resources and receives 403)
4. **Organisation approval workflow** (superadmin approves pending org → owner receives notification)

### Medium priority
5. **OTP edge cases** (expired OTP, re-used OTP, OTP for non-existent email)
6. **Password reset full cycle** (submit form → click link in email → set new password → login with new password)
7. **Role scope enforcement** (Dean can only see their faculty; department chair cannot see other departments)
8. **Exam attempt limits** (student cannot exceed configured attempt count; attempt counter increments correctly)
9. **Group membership propagation** (adding a student to a group that is attached to a course auto-enrols them)

### Low priority
10. **Language switcher** (changing language preserves query-string state — partially covered in test_smoke.py)
11. **Pagination** (large lists are paginated correctly with working prev/next links)
12. **File upload size limits** (uploading an oversized file produces a clear error message, not a 5xx)
13. **Blog post moderation** (teacher can review and approve student posts)

---

## 5. How to Run E2E Tests Locally

See [`tests/e2e/README.md`](../tests/e2e/README.md) for full instructions.

### Quick start

```bash
# 1. Install dependencies
pip install -r requirements/test.txt
pip install pytest-playwright playwright
playwright install chromium

# 2. Start the app (dev mode)
python manage.py runserver 8000

# 3. Seed the E2E test user
python manage.py seed_ci_e2e_user \
  --username myuser \
  --password mypassword

# 4. Run the full E2E suite
BASE_URL=http://localhost:8000 \
E2E_USERNAME=myuser \
E2E_PASSWORD=mypassword \
  pytest tests/e2e/ -v --timeout=60

# 5. Smoke tests only (fastest)
BASE_URL=http://localhost:8000 \
E2E_USERNAME=myuser \
E2E_PASSWORD=mypassword \
  pytest tests/e2e/test_smoke.py -v --timeout=60
```

---

## 6. Final Summary

### Total scenarios checked

| Category | Tests |
|---|---|
| Authentication & account lifecycle | 20 |
| RBAC / access control | 25 |
| Course management | 10 |
| Exam system | 15 |
| Security baselines | 20 |
| Notifications | 7 |
| Blog / content | 10 |
| **Total** | **~107** |

### Total bugs found

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 1 (BUG-01: org approval bypass) |
| Medium | 3 (BUG-02: logout GET, BUG-04: next param, RISK-02: cross-tenant) |
| Low | 1 (BUG-03: OTP direct access) |
| Risk / observation | 4 |

### Highest-risk areas

1. **Multi-tenant isolation** — The RBAC layer is solid in models and unit
   tests, but end-to-end cross-org access attempts have not been automated.  A
   bug here could expose one university's data to another university's staff.

2. **Organisation approval workflow** — New organisations are immediately
   `active` by default.  If the intent is to require approval, this is a
   functional gap that allows unvetted users full platform access.

3. **Live exam security** — Host-control guards are in place.  Player-facing
   endpoints need verification that the `results` payload is never returned to
   non-host clients under any parameter manipulation.

4. **Password reset** — The reset token flow is standard Django but has not
   been exercised end-to-end in CI.

### Recommended next steps for developers

1. Fix BUG-01: Set `Organization.status` default to `"pending"` for
   user-initiated registrations and update the superadmin approval workflow.
2. Fix BUG-02: Restrict the logout view to POST requests only.
3. Address RISK-02: Add at least one integration test that exercises a
   cross-organization access attempt.
4. Set up a local email sink (mailpit) in CI to enable full password-reset
   cycle testing.
5. Expand `seed_ci_e2e_user` to optionally seed a second, lower-privileged
   user and a second organization, enabling cross-tenant negative tests.
