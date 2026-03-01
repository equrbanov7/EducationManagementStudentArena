# Security Best Practices Review Report

Date: 2026-03-01  
Repository: `EMSArena`

## Executive Summary

This review found multiple high-impact security gaps in backend and frontend paths. The most urgent issues are:

1. Global TLS certificate verification is disabled for outbound HTTPS calls.
2. Multiple stored/DOM XSS paths allow attacker-controlled HTML/JS execution.
3. Several authenticated API endpoints expose course roster data without object-level authorization.
4. A state-changing endpoint is explicitly CSRF-exempt.

Finding counts:

- Critical: 1
- High: 6
- Medium: 2
- Low: 1

---

## Critical Findings

### [SBP-001] Global TLS certificate verification is disabled
- Rule ID: `DJANGO-HTTPS-001` (secure transport); general TLS verification best practice
- Severity: Critical
- Location: `config/settings/base.py:12`, `config/settings/base.py:13`
- Evidence:

```python
if hasattr(ssl, "_create_unverified_context"):
    ssl._create_default_https_context = ssl._create_unverified_context
```

- Impact: Any outbound HTTPS integration can be intercepted by MITM attackers because certificate validation is globally bypassed.
- Fix:
  - Remove this global override.
  - If local development needs custom trust behavior, use per-client/per-request SSL settings scoped to explicit development-only code paths.
- Mitigation:
  - Rotate credentials/tokens used by external integrations after fixing, in case traffic was previously intercepted.
  - Add CI/static checks that reject `ssl._create_unverified_context` usage.
- False positive notes: None. This is a direct global bypass.

---

## High Findings

### [SBP-002] CSRF protection is disabled on a state-changing exam endpoint
- Rule ID: `DJANGO-CSRF-001`
- Severity: High
- Location: `apps/exams/views/shared/access.py:13`, `apps/exams/views/shared/access.py:16`, `apps/exams/views/shared/access.py:30`
- Evidence:

```python
@csrf_exempt
@login_required
@require_POST
def exam_code_check(request):
    ...
    return _start_or_resume_attempt(request, exam)
```

- Impact: An attacker can forge authenticated POST requests from another site and trigger exam-attempt side effects for logged-in users.
- Fix:
  - Remove `@csrf_exempt`.
  - Keep CSRF token validation enabled for this POST endpoint.
- Mitigation:
  - Add tests asserting 403 on POST without valid CSRF token.
- False positive notes: None; endpoint changes user state and is explicitly exempted.

### [SBP-003] Stored XSS in teacher grading modal (`ans.text_answer` -> `innerHTML`)
- Rule ID: `JS-XSS-001`, `DJANGO-XSS-001`
- Severity: High
- Location:
  - `apps/exams/templates/exams/teacher/teacher_check_attempt.html:65`
  - `apps/exams/static/exams/js/teacher_check_attempt.js:44`
- Evidence:

```html
data-ans-text="{% if ans %}{{ ans.text_answer|escape }}{% else %}{% endif %}"
```

```javascript
const ansText = dataStore.getAttribute('data-ans-text');
document.getElementById('modalAnswerText').innerHTML = ansText ? ansText : ...
```

- Impact: A malicious student answer can execute script in a teacher’s browser when reviewing attempts.
- Fix:
  - Do not inject untrusted answer text with `innerHTML`.
  - Use `textContent` for text answers.
  - If rich HTML is required, sanitize with an allowlist sanitizer before insertion.
- Mitigation:
  - Add CSP and Trusted Types (where feasible) as defense-in-depth.
- False positive notes:
  - `|escape` in HTML attributes is insufficient here because the browser decodes entities before JS reads the attribute.

### [SBP-004] Stored/DOM XSS in exam access-code modal title rendering
- Rule ID: `JS-XSS-001`
- Severity: High
- Location:
  - `apps/exams/templates/exams/student/student_exam_list.html:107`
  - `apps/exams/templates/exams/student/student_exam_list.html:193`
- Evidence:

```html
data-exam-title="{{ exam.title }}"
```

```javascript
textEl.innerHTML = ... `<strong>"${title}"</strong>`
```

- Impact: Attacker-controlled exam titles can execute script when students open the access-code modal.
- Fix:
  - Escape `title` before interpolation or avoid `innerHTML` entirely.
  - Prefer building nodes with `textContent` + `createElement('strong')`.
- Mitigation:
  - Add automated frontend tests for XSS payloads in modal rendering.
- False positive notes:
  - This is exploitable if exam titles can include attacker-controlled content.

### [SBP-005] DOM XSS in lab modal roster rendering from API data
- Rule ID: `JS-XSS-001`
- Severity: High
- Location:
  - `apps/labs/templates/labs/partials/_lab_modals.html:439`
  - `apps/labs/templates/labs/partials/_lab_modals.html:440`
  - `apps/labs/templates/labs/partials/_lab_modals.html:492`
  - `apps/labs/templates/labs/partials/_lab_modals.html:493`
- Evidence:

```javascript
... 'value="' + g.name + '" data-group="' + g.name + '" ...'
... '<label ...>' + g.name + '</label>'
... '<label ...>' + s.name + '</label>'
... '<span ...>' + (s.group_name || '') + '</span>'
container.innerHTML = html;
```

- Impact: Malicious names/group values can inject arbitrary HTML/JS in teacher modals.
- Fix:
  - Escape all dynamic values before HTML concatenation, or build DOM nodes via `createElement`/`textContent`.
  - Avoid raw string concatenation for attacker-influenced fields.
- Mitigation:
  - Introduce a shared `escapeHtml()` utility and lint rule for `innerHTML` usage.
- False positive notes: None; these values originate from DB/user data and are injected unsafely.

### [SBP-006] Missing object-level authorization on course roster API endpoints
- Rule ID: `DJANGO-AUTHZ-001`
- Severity: High
- Location:
  - `apps/projects/views.py:496` to `apps/projects/views.py:565`
  - `apps/assignments/views.py:516` to `apps/assignments/views.py:631`
  - `apps/labs/views.py:964` to `apps/labs/views.py:1004`
- Evidence:

```python
@login_required
def api_get_groups(request):
    course = get_object_or_404(Course, id=course_id)
    ...
    return JsonResponse({"groups": ...})
```

```python
@login_required
def api_get_students(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    memberships = CourseMembership.objects.filter(course=course, role="student")
```

- Impact: Any authenticated user can enumerate groups and student names for arbitrary course IDs (IDOR/data leakage).
- Fix:
  - Enforce authorization checks (owner/teacher/assistant/member policy) before returning course roster data.
  - Reuse centralized permission helpers/mixins to avoid drift.
- Mitigation:
  - Add regression tests for unauthorized access returning 403.
- False positive notes:
  - If edge-layer authz exists, it is not visible in app code. No in-view object-level checks are present.

### [SBP-007] Live exam player token cookie is not marked `Secure`
- Rule ID: `DJANGO-HTTPS-001`, cookie hardening
- Severity: High
- Location: `apps/live_exam/views.py:572`
- Evidence:

```python
resp.set_cookie(PLAYER_COOKIE_NAME, token, max_age=60 * 60 * 6, samesite="Lax", httponly=True)
```

- Impact: If any HTTP path is reachable in deployment, this auth-like token may be exposed over cleartext transport.
- Fix:
  - Set `secure=True` for this cookie in TLS deployments.
  - Keep `httponly=True` and review `samesite` policy based on cross-site requirements.
- Mitigation:
  - Add an environment-gated helper for all security-sensitive cookies.
- False positive notes:
  - If the app is strictly HTTPS-only at every edge hop, exploitability is reduced, but `Secure` should still be set.

---

## Medium Findings

### [SBP-008] Open redirect via unvalidated `next` in organization switch
- Rule ID: `DJANGO-REDIRECT-001`
- Severity: Medium
- Location: `apps/organizations/views.py:63`, `apps/organizations/views.py:64`
- Evidence:

```python
next_url = request.GET.get("next", "/")
return redirect(next_url)
```

- Impact: Enables phishing and trust abuse by bouncing users to attacker-controlled domains.
- Fix:
  - Validate `next` with `url_has_allowed_host_and_scheme` and restrict to same-origin paths.
  - Fall back to an internal safe URL when invalid.
- Mitigation:
  - Use a shared `_safe_same_origin_redirect_path()` helper consistently across apps.
- False positive notes: None; current code redirects directly to user-supplied URL.

### [SBP-009] Unrestricted file upload surfaces without consistent validators
- Rule ID: `DJANGO-UPLOAD-001`
- Severity: Medium
- Location:
  - `apps/projects/models.py:91`
  - `apps/labs/models.py:97`
  - `apps/labs/models.py:262`
  - `apps/labs/models.py:431`
  - `apps/labs/models.py:523`
  - `apps/projects/views.py:351` to `apps/projects/views.py:353`
  - `apps/labs/views.py:85` to `apps/labs/views.py:87`
  - `apps/labs/views.py:351` to `apps/labs/views.py:353`
  - `apps/labs/views.py:892` to `apps/labs/views.py:894`
- Evidence:

```python
file = models.FileField(upload_to="projects/submissions/", blank=True, null=True)
...
submission.file = request.FILES["file"]
```

- Impact: Risk of malicious uploads (HTML/script/polyglot files, oversized payloads) and unsafe content serving.
- Fix:
  - Enforce extension/content-type/size validation on all upload fields.
  - Store untrusted files under non-executable media storage with safe download headers.
- Mitigation:
  - Add AV scanning/quarantine for high-risk upload flows.
- False positive notes:
  - Some exam upload paths do use validators; this finding targets the uncovered upload surfaces above.

---

## Low Findings

### [SBP-010] Missing explicit CSP and modern security-header hardening in app config
- Rule ID: `DJANGO-CSP-001`, `DJANGO-HEADERS-001`
- Severity: Low
- Location: `config/settings/production.py:40` to `config/settings/production.py:55` (headers present, CSP not configured in app code)
- Evidence:
  - App-level security headers include `X_FRAME_OPTIONS`, `SECURE_CONTENT_TYPE_NOSNIFF`, HSTS.
  - No visible CSP/referrer/COOP app settings in this module.
- Impact: Reduced defense-in-depth against XSS/data exfiltration/browser cross-origin abuse classes.
- Fix:
  - Add a strict CSP rollout (start report-only, then enforce).
  - Set explicit referrer and cross-origin policies where compatible.
- Mitigation:
  - If these are set at CDN/reverse proxy, document and test them in deployment checks.
- False positive notes:
  - These controls may exist at edge/proxy; not visible in repository code.

---

## Secure-by-Default Improvement Plan

1. **Immediate (today)**
   - Remove global TLS verification bypass.
   - Remove `@csrf_exempt` from `exam_code_check`.
   - Patch the three XSS paths (`teacher_check_attempt`, `student_exam_list`, lab modals).

2. **Short term (this week)**
   - Add object-level authorization checks to all roster APIs in projects/assignments/labs.
   - Add `secure=True` to `live_player_token` cookie.
   - Add safe redirect helper to `switch_organization`.

3. **Hardening (next sprint)**
   - Standardize upload validation/storage policy across all apps.
   - Roll out CSP and add security regression tests for XSS/CSRF/IDOR/open redirect.
   - Add CI security checks (`manage.py check --deploy`, grep/lint for `csrf_exempt`, `innerHTML`, unsafe redirects).

