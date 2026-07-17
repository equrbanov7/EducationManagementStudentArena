# RLS policy ownership & modular-monolith notes

_Companion to the 2026-07 architecture review. See also `docs/performance/OPTIMIZATION_5000_USERS.md`._

## 1. Cross-app RLS policy ownership (invisible coupling — read this before adding a tenant-scoped model)

EMSArena enforces multi-tenancy with Postgres **Row-Level Security**. The RLS
`CREATE POLICY` statements are **NOT** co-located with the models they protect —
they live in migrations under two apps. The module-boundary import graph
(`scripts/module_deps.py`) **cannot** see this coupling because it is SQL, not
Python imports. **If you add a new tenant-scoped table and forget its RLS policy,
the table is silently readable across tenants.**

### `apps/organizations/migrations/` — owns RLS for many apps' tables
| Migration | Covers tables in |
|---|---|
| `0003_rls_policies` | base tenant isolation (organizations, memberships, …) |
| `0004_expand_rls_scope` | expanded core scope |
| `0005_notification_org_fk_rls` | `notifications` |
| `0007_rls_question_bank_appeals` | `exams` (question bank) + `appeals` |
| `0012_rls_text_extraction_job` | `exams` (OCR job) |
| `0015_rls_final_center` | `exams` (final center: room/session/ticket) |
| `0016_rls_exam_room_computer` | `exams` (room computers) |
| `0017_rls_exam_gap_tables` | `exams` (gap tables) |
| `0018_rls_labs_projects` | `labs`, `projects` |
| `0020_rls_cross_fk_hardening` | cross-FK hardening (multiple apps) |
| `0022_rls_grade_event` | `exams`/grading |

### `apps/registrar/migrations/` — owns RLS for registrar-domain tables
`0002_rls_policies`, `0004_rls_enrollment`, `0007_rls_gradebook`, `0009_rls_journal`,
`0011_rls_scheduleslot`, `0013_rls_finals`, `0016_rls_assessment_components`,
`0020_rls_rubrics`, `0023_rls_journal_tables`, `0026_rls_kollokvium_window`.

**Rule of thumb:** new tenant-scoped model in app X → add its RLS policy migration in
`organizations` (cross-app tables) or `registrar` (registrar tables), and give the
tenant predicate column (`organization_id`) an index (RLS adds an org filter to
**every** query — see OPTIMIZATION doc §11, the `::uuid` cast fix). A future CI guard
that flags new `FORCE ROW LEVEL SECURITY`-less tenant tables would close this gap.

## 2. Modular-monolith improvement recommendations (NOT yet executed — need review)

The codebase is a genuinely disciplined modular monolith (enforced boundary gate,
`public.py` facades, clean `core/` kernel). Two structural improvements are
**recommended but intentionally left for a reviewed change** (too large/risky to
do blind):

- **Split `apps/accounts` (~24.6k LOC).** It is both auth/RBAC *and* the
  cross-domain dashboard-aggregation hub (`views/_dashboard_helpers/*`, a documented
  C4 exception). Extract the aggregation views into a new `apps/dashboards` app,
  still constrained to `.public` + `.models` surfaces, so a dashboard change can't
  touch auth code paths. Large import surface → do with the boundary gate green at
  each step.
- **Separate the heavy-dependency image.** `requirements/base.txt` bundles PyMuPDF
  (OCR), google-generativeai (AI), openpyxl (exports) into the one `emsarena-prod`
  image used by both web `app` and `celery_worker*`. The web app never needs OCR/AI
  at request time. A dedicated worker image (OCR/AI/export deps only) would slim web
  deploys. Now that `celery_worker_heavy` isolates those jobs (FAZA 1), this is the
  natural follow-up.

## 3. Microservices — verdict

For 5000–10000 concurrent users on one 80-core box: **scale the modular monolith,
do not go microservices.** Extract only the async/stateless leaves (Piston — already
a container; then OCR/AI/export/email as separate *queues* first, per FAZA 1). Never
extract the tenant-scoped transactional core (auth/org/exams/registrar/appeals) —
RLS is a single-Postgres-session mechanism, cross-app FKs + cross-app transactions
exist, and auth/org context is shared per-request. Full reasoning in the perf memory.
