# Tenant Isolation Checklist

This document records the manual review of tenant isolation across every tenant-aware
application in EMS Arena.  "Tenant-safe" means no object belonging to Organization B
can be fetched, modified, or enumerated by a user authenticated under Organization A.

---

## Architecture Overview

The system enforces isolation at three layers:

| Layer | Mechanism |
|-------|-----------|
| **Middleware** | `OrganizationMiddleware` sets `request.organization` and `request.org_memberships` from the session.  A missing or forged slug results in `request.organization = None`. |
| **Core helper** | `scoped_by_organization(queryset, request)` in `core/tenancy.py` applies `filter(organization=request.organization)` and returns `queryset.none()` when the context is absent. |
| **App-level wrappers** | Each app exposes thin wrappers (`_tenant_scoped_courses`, `tenant_scoped_exams`, …) that delegate to the core helper and are used by every view and CBV. |

---

## Per-App Status

### courses

| Check | Status | Notes |
|-------|--------|-------|
| `get_queryset()` uses `_tenant_scoped_courses` | ✅ | All list/detail CBVs |
| `get_object()` falls through tenant-scoped QS | ✅ | `CourseDashboardView` etc. |
| `Model.objects.get(id=…)` replaced | ✅ | No bare `.objects.get` in views |
| Fallback-free: missing org → empty set | ✅ | `scoped_by_organization` returns `.none()` |

### assignments

| Check | Status | Notes |
|-------|--------|-------|
| `get_queryset()` uses `_tenant_scoped_assignments` | ✅ | All list/detail views |
| `_get_tenant_assignment_or_404` used everywhere | ✅ | |
| `remove_student_from_assignment` scopes student lookup to course membership | ✅ | Fixed – was `User.objects.get(pk=…)`, now `CourseMembership.objects.filter(course=assignment.course, user_id=…)` |
| AJAX search endpoints use tenant-scoped course | ✅ | `search_students`, `search_groups`, `students_by_groups` |

### labs

| Check | Status | Notes |
|-------|--------|-------|
| `get_queryset()` uses `_tenant_scoped_labs` | ✅ | All CRUD and student views |
| `_get_tenant_lab_or_404` used everywhere | ✅ | |
| `preview_randomization` student lookup scoped to course members | ✅ | Fixed – was `User.objects.get(id=…)`, now `memberships.filter(user_id=…)` |

### projects

| Check | Status | Notes |
|-------|--------|-------|
| `get_queryset()` uses `_tenant_scoped_projects` | ✅ | All list/detail views |
| `_get_tenant_project_or_404` used everywhere | ✅ | |
| Submission scoping via `_tenant_scoped_submissions` | ✅ | |

### exams

| Check | Status | Notes |
|-------|--------|-------|
| `get_queryset()` uses `tenant_scoped_exams` | ✅ | Student list, teacher list |
| `get_teacher_exam_or_404` used for teacher writes | ✅ | |
| `exam_in_active_tenant` validates org match before actions | ✅ | |
| Student exam list filters by active org | ✅ | |

### live_exam (HTTP views)

| Check | Status | Notes |
|-------|--------|-------|
| All host endpoints call `_ensure_host_org_permission` | ✅ | Enforces org context, org ownership, org active status, and `exam.manage` permission |
| Player join scoped to session PIN (unique) | ✅ | No cross-org leakage via PIN lookup |
| WebSocket consumers authenticate via `authorize_socket_connection` | ✅ | |

### notifications

| Check | Status | Notes |
|-------|--------|-------|
| `InAppNotification` is per-recipient (no org FK needed) | ✅ | |
| All read/delete ops use `_get_own_notification_or_404(pk, user)` | ✅ | Scoped to `recipient=user` |
| Publish targets (`all`, `org_*`, `group_*`) validated against caller permissions | ✅ | Superadmin-only for `all`; membership verified for `org_*`; teacher ownership verified for `group_*` |

### blog

| Check | Status | Notes |
|-------|--------|-------|
| `Post`, `Category`, `Comment` have no organization FK | ℹ️ | Blog content is platform-wide, not per-tenant.  No isolation required. |

### organizations (self)

| Check | Status | Notes |
|-------|--------|-------|
| `tenant_filter()` respects org active status | ✅ | Returns `.none()` for inactive orgs |
| Role assignment enforces hierarchy | ✅ | `can_user_assign_role` checks caller vs target level |
| Cross-org membership management blocked | ✅ | All management views verify org ownership |

---

## Helper Functions Audit

| Function | Location | Tenant-safe? |
|----------|----------|-------------|
| `scoped_by_organization` | `core/tenancy.py` | ✅ Returns `.none()` without context |
| `tenant_filter` | `apps/organizations/services.py` | ✅ Rejects inactive orgs |
| `_tenant_scoped_courses` | `core/helpers.py` | ✅ Delegates to `scoped_by_organization` |
| `_tenant_scoped_assignments` | `apps/assignments/views/_helpers.py` | ✅ Filters by tenant-scoped courses |
| `_tenant_scoped_submissions` (assignments) | `apps/assignments/views/_helpers.py` | ✅ |
| `_tenant_scoped_labs` | `apps/labs/views/_helpers.py` | ✅ |
| `_tenant_scoped_blocks` | `apps/labs/views/_helpers.py` | ✅ |
| `_tenant_scoped_questions` | `apps/labs/views/_helpers.py` | ✅ |
| `_tenant_scoped_submissions` (labs) | `apps/labs/views/_helpers.py` | ✅ |
| `_tenant_scoped_projects` | `apps/projects/views/_helpers.py` | ✅ |
| `_tenant_scoped_submissions` (projects) | `apps/projects/views/_helpers.py` | ✅ |
| `tenant_scoped_exams` | `apps/exams/views/shared/tenant.py` | ✅ |
| `get_teacher_exam_or_404` | `apps/exams/views/shared/tenant.py` | ✅ |

---

## Patterns to Maintain

When adding a new view or API endpoint:

1. **List views**: always call the app-specific `_tenant_scoped_*` helper from `get_queryset()`.
2. **Detail / edit views**: use `_get_tenant_*_or_404(request, pk)` instead of `Model.objects.get(pk=pk)`.
3. **User lookups within a resource**: resolve the user through the resource's related membership or ownership queryset (e.g. `course.memberships.filter(user_id=…)`), never via `User.objects.get(pk=…)`.
4. **No fallback on missing org**: do not add `if organization is None: return all_objects`. Missing org must yield an empty result or 403.
5. **Service layer**: pass the `organization` object to service functions; never accept a raw `org_id` from user input without re-fetching and validating the org.

---

## Automated Test Coverage

Cross-tenant integration tests live in:

- `apps/organizations/tests/test_tenant_isolation.py`
  - `TenantIsolationTest` – queryset and service layer
  - `RequestTenantContextTest` – request-scoped permission and queryset isolation
  - `HttpTenantIsolationTest` – HTTP end-to-end for courses, exams, sessions
  - `CrossTenantAssignmentIsolationTest` – assignments `remove_student` and lab `preview` endpoints

Run the full suite with:

```bash
python -m pytest apps/organizations/tests/test_tenant_isolation.py -v
```
