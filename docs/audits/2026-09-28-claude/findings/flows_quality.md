# EMSArena audit 2026-09-28 — `flows_quality` (Business logic · Frontend · UX/UI · Accessibility · Testing · i18n)

Repo HEAD `914a6571` (Develop) plus today's uncommitted tree. Auditor mode: read-only. The only writes are to this file and to throwaway probes under `scratchpad/audit/scratch_{syl,jrn,exa,stu}/`.

## 1. Scope & method

**Flows.** Five flows were traced through the code by five read-only sub-audits: syllabus, journal, exam→appeal, student lifecycle, and workload→timetable.
- Where a finding says CONFIRMED-by-test, it was proven with throwaway pytest probes on the agent sandbox (`127.0.0.1:55432`, DB names `ems_audit_flows_*`, `--ds=config.settings.test`):
  - `scratch_syl/test_syl_audit_probe.py`: 4 pass
  - `scratch_exa/test_exa_appeal_flow.py`: 4 pass; `test_exa_history.py`: 1 pass
  - `scratch_jrn/test_jrn_probe.py`
  - `scratch_stu/test_audit_{stu,wl}_probe.py`
- I re-read the key lines of each P1 myself:
  - `syllabus/state_machine.py:103-108` (no author exclusion)
  - `exams/services/journal_sync.py:190-236` (no latest-attempt check)
  - `registrar/movements.py:235-247` (status change leaves Enrollment untouched)
  - `registrar/views.py:395-400` (save_finals → `finals.set_exam_score`)

**Targeted existing suites run:**
- `apps/syllabus/tests` + `apps/appeals/tests`: **331 passed**
- Journal subset: 277 passed
- `core/tests/test_w2_a11y_guards.py`, `tests/test_i18n_terminology.py`, `apps/accounts/tests/test_section_registry_consistency.py`: 27 passed
- Workload/transfer subset: 21 passed

**Static analysis (Python and perl scans, scripts in the audit directory: `fq_js_stats.py`, `fq_az_scan.py`):**
- 417 project JS files (81 337 lines), 382 CSS, 769 HTML
- CSP inline scan, a11y heuristics, fetch/error handling, native dialogs, AJAX-safety markers
- `scripts/check_module_size.py --check` (green) and `scripts/check_i18n_catalogs.py --report` (green: "yeni borc yoxdur")
- polib analysis of az/en/ru/tr: collapsed-translation detector, English-in-RU/TR detector, deasciified TR, and a random 40-entry spot-check (seed 20260928) outside courses/assignments/labs/projects

**React/TS:** none. There are no `.ts`, `.tsx` or `.jsx` files and no frontend `package.json`, apart from the unused `tests/js` jsdom harness. The stack is server-rendered Django templates plus vanilla JS.

**Not done:**
- No browser runs: the QA clone at :55433 and the real DB are off-limits.
- Responsive layout and contrast were not re-measured visually; the numbers come from source only.

## 2. Status of prior findings (2026-09-13 audit: frontend.md, tests.md, scorecard)

| Prior | Status | Evidence |
|---|---|---|
| FE F1/F2/F3 (RU/TR close / deselect / check wrong meaning) | FIXED | ru «Закрыть», «Снять выделение», «Проверить»; tr «Kapat», «Seçimi temizle», «Kontrol et» |
| FE F4 (613 `pgettext(_CTX,…)` not in catalogs) | FIXED | `scripts/i18n_source_scan.py:90-138` resolves `ast.Name` module constants |
| FE F5 (focus stays on body after AJAX swap) | FIXED | `section_loader.js:215-234` focuses `#profileSectionTitle` |
| FE F6 (neutral-400 used as text colour) | PARTIAL | 63 → 45 rules (FQ-A11Y-3) |
| FE F7 (workload JS without i18n) | FIXED | `workload_distribution.js:81-86` gettext bridge; `confirm("Sətir…")` gone |
| FE F8/F9 (March→Search; Duplicates) | FIXED | ru «Март», tr «Mart»; `stat_duplicates` «Дубликаты» / «Kopyalar» |
| FE F10 (nested `<main>`) | FIXED | `profile.html:24` comment; the only `<main>` is in `base.html:147` |
| FE F12 (setInterval leak after swap) | FIXED | `isConnected` guards in `review_submissions.js:61`, `teacher_pending_attempts.js:49` |
| FE F13 (console.log) | FIXED | the one remaining call is behind `debugOn` (`host_lobby/utils.js:281`) |
| FE F14 (`rim-center` drift) | FIXED | present in `data-ajax-sections`; registry test passes |
| FE F15/F16/F17/F18/F19/F21 | FIXED | commit e6e45657 plus guards in `core/tests/test_w2_a11y_guards.py` (10 pass). F19 residual: 2 template `onclick=confirm` survive (FQ-FE-1) |
| FE F20 («Закрой это») | FIXED | 0 occurrences |
| Legacy `card` count 1 194 | IMPROVED | 586 now; `ems-*` classes 3 082 |
| tests F-T1 (unsubmitted draft distribution) | PARTIAL | office-created drafts are blocked, but a chair-created draft still skips coordinator/dean (W1) |
| tests F-T2 (reinstatement to the same group → 409) | FIXED | `registrar/movements.py:293-303` exempts REINSTATEMENT |
| tests F-T7 (no schedule overlap constraint / publish state) | STILL OPEN | W3; generator runs have PUBLISHED status, live slots do not |
| tests F-T8 (correction note min length) | STILL OPEN (P3) | `corrections.py:119-121` only checks the note is non-empty |
| tests F-T11 (coverage: duplication 0 %, etc.) | FIXED for duplication | `apps/exams/tests/test_w2_duplication.py` (16 tests). The scorecard filed `duplication.py` under the syllabus flow by mistake; it is the exam duplication service |
| tests F-T13 (postgres marker on view-as test) | STILL OPEN | `test_view_as_session_end.py:120-122` self-skips with no marker |
| tests F-T14 (no time_machine/freezegun) | STILL OPEN | 0 files, 0 requirements |
| backend F-11 (appeal state machine is dead code) | STILL OPEN | EXA-06 |
| exams EX-01/04/05/08/09 | FIXED | per the exa sub-audit (`results.py:143-148`, `tickets.py:270`, `attempts.py:392-398`, `domain/attempts.py:224-228`, `attempts.py:201`) |
| Journal "finals/grid still opening-level absence limit" | FIXED | per-student `absence_limit.row_limits`; only the save_marks notices remain opening-level (J-04) |
| Syllabus flow scored 91 | REGRESSED in assessment | new P1/P2 integrity gaps found (SYL-1..4); not code regressions, they were previously unexamined |

## 3a. New findings — business-logic flows

### SYL-1 Author who also holds approval rights (e.g. chair head, prorector) can approve their own syllabus
Severity: P1   Category: Business logic / segregation of duties   Status: CONFIRMED (probe test)
Location: apps/syllabus/state_machine.py:103-108 (APPROVE rule), :156-201 `check`; apps/syllabus/services/workflow.py:66-73 `_in_scope`
Evidence:
```python
Transition.APPROVE: TransitionRule(name=Transition.APPROVE,
    sources=frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value}),
    target=SyllabusStatus.APPROVED.value, permission=PERM_APPROVE),   # no author exclusion
```
The rule table has `author_only` (line 77) but no `forbid_author`.
How verified: `scratch_syl` probe. A chair_head who is also the offering instructor runs create → fill → submit → approve, and ends with `approved_by == submitted_by`. The existing test (`test_state_machine.py:128`) only covers an author *without* `syllabus.approve`.
Impact: Chair heads usually also teach, so the four-eyes review of what students see and what journals are built from is bypassed.
Recommended fix: Add `forbid_author=True` to APPROVE, REQUEST_REVISION and REJECT, and route self-authored versions to the dean or an org-level actor. Hide the buttons in `available_actions`, and add a test.
Effort: Small

### SYL-2 MAJOR change approved as MINOR (reject v2.0, then open a minor v2.1 based on the rejected version)
Severity: P2   Category: Business logic / versioning   Status: CONFIRMED (probe test)
Location: apps/syllabus/services/drafts.py:279-298 `create_next_version`; apps/syllabus/services/versioning.py:39-47 `baseline_for`
Evidence: `base = syllabus.versions.order_by("-major","-minor").first()`. This can be the REJECTED version, and `baseline_for` then compares against `source_version`.
How verified: probe. v1.0 approved → structural minor draft escalated to v2.0 → rejected → `create_next_version(minor)` gives v2.1 with `source_version` = v2.0 → it submits as MINOR with `escalated_sections == ()` → approved, even though its week plan differs from the approved v1.0.
Impact: Structural changes land mid-semester and alter the structure of journals that are already open, which defeats README §10.3.
Recommended fix: Always compare against `syllabus.approved_version` when one exists, and branch new versions from the approved version.
Effort: Small

### SYL-3 Autosave can write into a SUBMITTED or APPROVED version (status checked on a stale, unlocked object)
Severity: P2   Category: Concurrency   Status: CONFIRMED (probe test)
Location: apps/syllabus/services/drafts.py:364-365, 379 `save_section`
Evidence:
```python
if version.status not in EDITABLE_STATUSES:   # in-memory object, no lock
    raise TransitionDenied("version.locked", ...)
row = SyllabusSection.objects.select_for_update().get(version=version, section_id=section_id)
```
How verified: probe. Load the version as DRAFT → `submit()` commits → `save_section(stale)` succeeds and clears a section of the SUBMITTED version; completion drops below 100.
Impact: A debounced autosave racing the "Göndər" click changes the version the chair reviews. The invariant "approved means immutable" is not DB-enforced.
Recommended fix: Re-read the version with `select_for_update()` in `save_section`, `set_plan_hours` and `seed_week_hours`, and check the status on the locked row.
Effort: Small

### SYL-4 `submit()` writes (escalation + completion) before checking permission, author and scope
Severity: P2   Category: Authorization order / state integrity   Status: CONFIRMED (probe test)
Location: apps/syllabus/services/workflow.py:171-173; apps/accounts/views/syllabus/api.py:280-285
Evidence: `version, escalated = versioning.escalate_if_structural(...)` and `recompute_completion(version)` run before `_apply(...)`, which does the guard.
How verified: probe. A non-author in the same org calls submit, gets `transition.out_of_scope`, but the draft has already been renumbered v1.1 → v2.0 MAJOR, with an audit row in the non-author's name. The view returns 409 without rolling back.
Impact: A side effect happens before authorization (a non-author needs the version UUID). An author's failed submit on an incomplete draft still leaves it permanently MAJOR.
Recommended fix: Run `check()` first; then escalate, recompute and transition in one locked transaction.
Effort: Small

### SYL-5..7 (P3, summarised)
- **SYL-5** `copy_from_previous` into the same period creates a parallel `offering=None` dossier. `services/offerings.py:80-81` then uses it as the tier-2 fallback for other teachers' offerings. The target lookup ignores the author (`copy_into.py:87-116`). CONFIRMED.
- **SYL-6** Double-click on "new version": the unlocked open-version check means an `IntegrityError` becomes a 500 (`drafts.py:275-301`). Data stays safe thanks to `uniq_syllabus_open_version`. PLAUSIBLE.
- **SYL-7** A GET on the editor as a non-author (chair) in `normal` mode writes `seed_week_hours`, which bumps the revision and causes a 409 for the author. The editor's completion check ignores the org's `assessment_weights`, while submit uses them (`editor.py:252-255,401`; `public.py:201,214`). PLAUSIBLE.

### EXA-01 Appeal (or late grading) on an earlier attempt overwrites the official grade from the later re-exam
Severity: P1   Category: Business logic / grade integrity   Status: CONFIRMED (probe test + read)
Location: apps/exams/services/journal_sync.py:190-236 `sync_attempt_to_journal`; callers apps/appeals/services/decisions.py:289,363; manual_grading.py:50-53
Evidence:
```python
is_expelled = getattr(attempt, "supervision_status", "") == "removed"
percent = 0 if is_expelled else _attempt_percent(attempt)
...
return record_exam_result(student=attempt.user, subject_id=subject_id, ..., score_percent=percent, ...)
```
There is no check whether a later finished final attempt exists.
How verified: `scratch_exa/test_exa_appeal_flow.py`. Attempt #1 scored 0 %, the "Yenidən şans" attempt #2 scored 100 % (FinalGrade exam 50), then an appeal on #1 was accepted and FinalGrade dropped to **25**. `exam_attempt_history` still marks #2 as official.
Impact: The official journal grade silently regresses, contradicting "last attempt is official", and can wrongly trigger `evaluate_resit`.
Recommended fix: Skip with a counted `superseded_attempt` code when a later finished, non-trial final attempt exists for the same user and subject, or always re-sync the latest attempt.
Effort: Small

### EXA-02 Appeals are possible before a written attempt is graded; the window runs from `finished_at`
Severity: P2   Category: Business logic   Status: CONFIRMED (probe test)
Location: apps/appeals/services/permissions.py:30-47; window.py:22-45; decisions.py:218-246
Evidence: `base = previous_answer_score if … else Decimal("0")` … `attempt.teacher_score = int(new_score)` while `checked_by_teacher` stays False.
How verified: probe. Accepting an appeal on an ungraded 2×10 written final wrote `teacher_score=1` and `FinalGrade.exam_score=3` (F).
Impact: A premature F and a resit record. The +1 is later overwritten while `ScoreAdjustment` stays "active". Conversely, if grading takes more than 3 days the student can never appeal. Written finals are mostly paper, hence P2.
Recommended fix: Require `checked_by_teacher` (or a published result) before an appeal, and start the window from `teacher_checked_at`.
Effort: Small–Medium

### EXA-03 The attempt-history surface for the owner memo (re-exam/appeal history) shows wrong data and has no appeal records
Severity: P2   Category: Business logic / owner requirement   Status: CONFIRMED (probe test, parts a–c)
Location: apps/registrar/exam_attempt_history.py:56-115; exams/domain/attempts.py:252-261; appeals/services/permissions.py:52-73
Evidence: the history filter has no `exam_type_extended="final"`; `"percent": _safe_percent(attempt)` (written: correct/(correct+wrong) = 0); `"is_official": index == last_index`.
How verified: `test_exa_history.py`. A written final graded 8/10 (FinalGrade 40) shows 0.0 % and is not official; a later midterm is labelled official. Appeal bonuses are ignored.
Impact: The memo requirement from 2026-09-07 ("record every re-exam/appeal attempt, visible to coordinator/dean") is effectively unmet:
- percentages are wrong;
- midterms are marked official;
- digital appeals never create an `ExamScoreEntry(kind=appeal)`;
- appeals are visible only to exam-centre users.
Recommended fix: Filter to finals, reuse `journal_sync._attempt_percent` (including the bonus), add appeal rows, grant read to coordinator and dean, and append an `ExamScoreEntry(kind=appeal)` on digital decisions.
Effort: Medium

### EXA-04 Absence-limit admission gate is missing on the final-hall start paths and fails open
Severity: P2   Category: Business logic / eligibility   Status: CONFIRMED (read)
Location: gate only at apps/exams/views/student/attempts.py:186-191. Missing in services/final_center/tickets.py:288-313 (`_ensure_exam_start_policy`), views/student/final_center.py:382 (PIN start) and views/shared/access.py:141. journal_sync.py:264-266 returns `None` (allowed) on exception.
Impact: A barred student can sit the final in the hall. `compute_final_result` still fails them, but the admission rule is not enforced at the door.
Recommended fix: Call the eligibility check in `_ensure_exam_start_policy` and in the PIN and code paths; fail closed.
Effort: Small

### EXA-05..08 (P3, summarised)
- **EXA-05** Re-edit within 5 min: `revert_item_adjustment(item)` runs without `reviewer`/`request` and outside a transaction with the new decision (`appeals/views/teacher/endpoints.py:301-302`). The ledger row has `grader_id=None` (probe). CONFIRMED.
- **EXA-06** Appeal header status is recomputed without locking the Appeal row, and `assert_transition` is never called (`decisions.py:367-407`, prior backend F-11). Concurrent reviewers can leave the header `under_review` with no notification. Race PLAUSIBLE.
- **EXA-07** `can_create_appeal` doesn't restrict the exam category server-side; quiz and practice appeals can be created with a crafted POST. CONFIRMED (read).
- **EXA-08** The written-appeal clamp uses live `question.points` instead of the delivered snapshot (`decisions.py:188,230`). CONFIRMED (read).

### J-01 Journal `save_finals` writes exam/resit scores around the ExamScoreEntry ledger and the past-period lock; garbage → 0
Severity: P2   Category: Business logic / audit   Status: CONFIRMED (probe test)
Location: apps/registrar/views.py:378-410 `_handle_save_finals` (line 400 `finals.set_exam_score(...)`); apps/registrar/finals.py:53-58 `_clamp`, :322
How verified: `scratch_jrn` probe. A privileged user posted `exam__<id>=abc` on a finished period with an existing score of 40: HTTP 302, score `0.00`, 0 `ExamScoreEntry` rows.
Who can reach it: holders of direct edit rights plus `final_score.entry` (superuser, org owner, RİM head, or a teacher granted that permission).
Impact: Bypasses the owner's 2026-09-26 period-lock rule (RİM head + correction mode + document) and the reason/document requirement, and is missing from the «Dəyişən nəticələr» report and the attempt history. Resit scores are written only through this path.
Recommended fix: Route `exam__`/`resit__` through `exam_score_entry.record_exam_score(period_policy=…)`, or remove them. Make `_clamp` reject non-numeric input.
Effort: Small

### J-02 `update_lesson` accepts `hours=0` or any value, allows duplicate time slots, and is unaudited
Severity: P2   Category: Business logic / eligibility integrity   Status: CONFIRMED (probe test)
Location: apps/registrar/journal_actions.py:174; apps/registrar/gradebook_lessons.py:200-245
Evidence:
```python
hours = int(request.POST.get("lesson_hours")) if (...).isdigit() else None   # "0"/"40" accepted
if hours is not None:
    lesson.hours = hours
```
How verified: probe. A student absent in lesson B (2 h) → update B with `hours=0` and lesson A's slot → HTTP 302, two lessons at 08:30, absence recomputed to 0.
Impact: Within the 2 h edit window a teacher can erase or inflate absence hours. That changes the 25 % admission decision, with no audit row. `create_lesson` does validate all of this.
Recommended fix: Mirror the `create_lesson` validation (1..MAX_SLOT_HOURS, `hours_cap_error`, duplicate check under the offering lock), write `grade_audit` for date/hours/kind, and consider a partial unique index on `(offering, date, start_time)`.
Effort: Small

### J-03..09 (P3, summarised; details in the journal sub-audit)
- **J-03** `save_component_scores` (non-`require_all` path, midterm/kollokvium) turns invalid input into 0 and `"NaN"` into a 500 (`gradebook_components.py:392`). CONFIRMED by probe: 15 → "abc" → 0.00, "Infinity" → 20.00.
- **J-04** `save_marks` barred/near-limit notifications still use the opening-level absence limit (`gradebook.py:234`).
- **J-05** A documented score correction can put a score on an absent or excused cell (`corrections.py:151-158`).
- **J-06** Possible deadlock: correction lock order is Lesson→Enrollment→Mark; save_marks is Offering→Mark→Enrollment. PLAUSIBLE.
- **J-07** Best-effort `log_grade_changes(fail_closed=False)` has no savepoint inside the atomic block (`grade_audit.py:84-104`). A DB error there aborts the transaction silently. PLAUSIBLE.
- **J-08** No DB CHECK on `LessonMark.score` / `ComponentScore.score`, and no unique constraint on Lesson (`models/grading.py`).
- **J-09** A cancelled offering (`is_active=False`) is still writable by URL (`journal_access.py:22-49`).

### S1 Expelled and on-leave students keep ENROLLED enrollments (journal, exam-score roster, LMS re-add)
Severity: P1   Category: Business logic / student lifecycle   Status: CONFIRMED (probe test + read)
Location: apps/registrar/movements.py:235-247 `_apply_status` (+ :387-393); rosters at apps/registrar/gradebook.py:156,325 and exam_score_roster.py:197
Evidence:
```python
record.status = to_status
record.is_active = academic_status.is_active_for(to_status)
record.save(update_fields=["status", "is_active", "updated_at"])
academic_status.audit_status_change(...); _sync_access_state(record, to_status=to_status)   # Enrollment untouched
```
Rosters filter `offering.enrollments.filter(status=Enrollment.Status.ENROLLED)` only.
How verified: `scratch_stu` probe. After EXPULSION through `movements.create_movement`, the enrollment is still `enrolled` and `roster_for_offering` still includes the student. I did not verify whether the journal UI badges them.
Impact: Expelled or on-leave students stay gradable and markable in journals and exam sheets, count in pass statistics, and today's `course_groups` re-adds them to LMS courses (C1).
Recommended fix: In the same transaction, move current-period ENROLLED rows to a `suspended`/`withdrawn` status; REINSTATEMENT restores them. Add a test. Confirm the intended display with the owner first.
Effort: Medium

### S2 Group split or transfer into a new subgroup creates offerings with no teacher (students leave the teacher's journal)
Severity: P2   Category: Business logic   Status: CONFIRMED (probe test)
Location: apps/registrar/transfer.py:118-133; apps/registrar/services.py:59-81; apps/organizations/group_split.py:175-190
Evidence: `successor, was_created = services.enroll_student_in_subject(...)` and then `enrollment.status = DROPPED`. The new offering has `instructor=None`, `lesson_hours=0`, `course=None`.
Impact: After a partial split, the moved students disappear from the teacher's journal onto a journal with no teacher until a manual repair. The split tests make no assertions about offerings.
Recommended fix: Copy instructor, lesson_hours and course from the source offering, or keep the students as guests on the parent offering.
Effort: Medium

### S3/S4 Group-registry scope (P2)
- **S3** (CONFIRMED, read): the `_add_students` / `group_student_candidates` candidate list isn't limited to the actor's faculty scope. Group-less students from any faculty can be pulled in, within the tenant (`group_actions.py:311-314`, `group_students.py:141-145`).
- **S4** (PLAUSIBLE): write handlers get the `unit.view` scope instead of `unit.group_manage` (`groups_registry.py:70-72`, `group_actions.py:440-452`).
Recommended fix: Scope candidates, and resolve write scope with `PERM_MANAGE`.
Effort: Small

### W1 Chair-created draft workload task still skips coordinator/dean approval (prior F-T1 only partly fixed)
Severity: P2   Category: Business logic / approval chain   Status: CONFIRMED (existing test documents it)
Location: apps/workload/services/workflow.py:76-107; apps/workload/tests/test_audit_2026_09_13_draft_distribution_gate.py:84-91 (`test_chair_own_draft_keeps_the_legacy_exception`)
Evidence: `if task.status == DRAFT and (task.submitted_at is not None or not _draft_created_by_chair(task)): raise …`
Impact: A chair head (or an org-wide `workload.*` holder) can create, distribute and confirm a task, which creates CourseOfferings and enrollments with no coordinator or dean step.
Recommended fix: Limit the exception to tasks created before a cutoff date, or never sync offerings for tasks that were never submitted.
Effort: Small

### W2 Row hours can be cut below the assigned hours; over-assignment still counts as complete
Severity: P2   Category: Business logic / workload   Status: CONFIRMED (probe test)
Location: apps/workload/services/tasks.py:276-337 `save_row` (no lock, no floor); assignments.py:78 `"is_complete": used >= total`
How verified: probe. Assign 30 lecture h → `save_row(lecture_total=10)` is OK → readiness `is_ready=True` → `confirm_distribution` returns `distributed`.
Recommended fix: Lock the row, reject totals below the assigned sum (409), and treat `used > total` as incomplete.
Effort: Small

### W3 No DB guard against teacher/group/room double-booking; check-then-write is not atomic
Severity: P2   Category: Concurrency / timetable   Status: CONFIRMED (probe test)
Location: apps/registrar/models/academic.py:548-555 (no constraint); schedule_manage_actions.py:193-205; schedule_editor_actions.py:241-270; schedule_publish.py:265-283
How verified: probe. Two overlapping slots for the same teacher were both accepted by the DB. There is no ExclusionConstraint or advisory lock in registrar or timetable. The prior F-T7 is still open.
Recommended fix: `pg_advisory_xact_lock(org, period)` around check and write in all three paths. Later, a btree_gist exclusion constraint on the effective instructor.
Effort: Medium

### W4 Changing an offering's teacher via workload sync never re-checks the timetable
Severity: P2   Category: Business logic   Status: CONFIRMED (code path); double-booking PLAUSIBLE
Location: apps/workload/services/offering_sync.py:388-418 (`_update` sets `instructor_id`, no `schedule_conflicts` call)
Recommended fix: Run `schedule_conflicts.detect` for the offering's slots after an instructor change, and report or park the conflicts.
Effort: Medium

### W5/W6, C1/C2, S5 (summarised)
- **W5** (P3, CONFIRMED read): the timetable generator reads teacher assignments from unconfirmed and cancelled tasks (`timetable/sources/offerings.py:95-134`, `workload/services/offering_teachers.py:57-66`).
- **W6** (P3): DISTRIBUTED is set without `ensure_transition`, and confirm/publish take no locks (`assignments.py:190-192`, `distribution.py:176-179`, `timetable/services/publish.py:56-74`).
- **C1** (P2, CONFIRMED probe, today's untracked `apps/registrar/course_groups.py:68-79`): `_enrollment_students` doesn't check the academic-record status, so an expelled student is re-added to LMS courses. Fix: filter `academic_records__status=ENROLLED`, or fix S1.
- **C2** (P3, owner decision): any course owner can bulk-add any active org group to their LMS course, with no teaching or scope link (`courses/views/teacher/groups.py:83-104`). Minor: delete matches `group_name` exactly while `in_course` uses casefold (`:89` vs `:173-175`).
- **S5** (P3): the group capacity check runs before the lock, and the registry add/move/split paths skip it (`accounts/services/people/movements.py:150-161`).

### What works well (flows, with evidence)
- **Syllabus:**
  - A single fail-closed state machine with `select_for_update` and a re-check under lock (`workflow.py:139-142`).
  - DB constraints: `uniq_syllabus_open_version`, `uniq_syllabus_approved_version`, and approved ⇒ locked and has an approver.
  - Students see only the approved version.
  - Every transition writes a `SyllabusReview` and an AuditLog row.
- **Journal:**
  - Tenant checks plus RLS plus coherence triggers (mig. 0041).
  - Instructor-only edits, a 2 h freeze enforced in both the service and a PG trigger, an atomic bulk save under the offering lock, close/reopen audited.
  - Corrections require reason + note + PDF, are append-only and fail-closed.
  - `FinalGrade.exam_score` has a CHECK of 0..100.
- **Appeals:**
  - The attempt row is locked on create, the window is re-checked in the service, and the same question can't be appealed twice.
  - `ScoreAdjustment` is one-to-one (idempotent), bounds are clamped, the `ExamGradeEvent` ledger is fail-closed, and the journal sync runs on commit.
- **Student transfer:**
  - `transfer_student_group` validates tenant, group type and period, locks the record and enrollments, uses a two-phase token checked by a DB trigger, and keeps a `superseded_by` lineage.
  - Movement rules are validated under `select_for_update`.
  - Students can't be made teachers.
- **Workload:**
  - submit/approve/return lock their rows and call `ensure_transition`.
  - `assign_teacher` locks the row, preventing concurrent over-spend.
  - `publish_slots` checks scope and conflicts and is audited.
## 3b. New findings — Frontend / UX / Accessibility / i18n / Testing

### FQ-FE-1 Inline `onclick="return confirm(...)"` in notification templates is blocked by CSP; delete runs without confirmation
Severity: P3   Category: Frontend/CSP/UX   Status: CONFIRMED (static; not browser-verified)
Location: apps/notifications/templates/notifications/notification_list.html:158; apps/notifications/templates/notifications/notification_detail.html:85
Evidence:
```html
<button type="submit" class="btn btn-sm btn-outline-danger" title="{% trans 'Delete' %}"
        onclick="return confirm('{% trans "Delete this notification?" %}')">
```
`config/settings/components/csp.py:40-44` — `script-src: [SELF, NONCE, clarity]`, no `'unsafe-inline'`/`'unsafe-hashes'` → inline event-handler attributes are not executed.
How verified: read + python template scan (only 2 `on*=` attributes left in 769 templates); CSP config read. The a11y guard `core/tests/test_w2_a11y_guards.py:30,63-65` scans only `*.js` for native `confirm(` — templates are a blind spot.
Impact: The confirm dialog never appears (plus a CSP violation report per click); the form submits and the notification is deleted immediately. Low data value, but it breaks the "dangerous action = EMSConfirm" rule and the CLAUDE.md "no inline JS" rule.
Root cause: Missed by the 4ac4a52f CSP sweep; the guard test does not scan HTML.
Recommended fix: Replace with `data-ems-confirm="…"` (existing EMSConfirm delegate). Extend the guard to fail on `\son[a-z]+=` in `apps/**/templates` and `templates/`.
Effort: Small

### FQ-FE-2 CLAUDE.md verification grep does not run (PCRE look-ahead under ERE)
Severity: P3   Category: Frontend/process   Status: CONFIRMED
Location: CLAUDE.md «Yoxlama» section
Evidence: `grep -rlE '<style|<script(?![^>]*src=)[^>]*>[^<]' apps templates --include='*.html'` → `ugrep: error: error at position 20 … invalid syntax` (GNU grep -E also rejects `(?!`).
How verified: ran the command.
Impact: The documented gate is a no-op for agents and humans. Equivalent perl scan: 36 matching files, **all** are `type="application/json"` / `application/ld+json` (nonce'd) data blocks or comments — **0 executable inline `<script>`/`<style>`**.
Recommended fix: Use `grep -rlP` or a perl one-liner, and exclude `type="application/json"`. Better, turn it into a pytest guard.
Effort: Small

### FQ-FE-3 Hand-written JSON i18n blocks without `escapejs` (latent JSON breakage)
Severity: P3   Category: Frontend/i18n robustness   Status: CONFIRMED (latent; no currently broken string)
Location: apps/accounts/templates/accounts/profile/sections/_people_directory.html:402-445 (42 keys); apps/accounts/templates/accounts/register.html:245+ (≈38 keys)
Evidence:
```html
<script type="application/json" id="people-detail-i18n-{{ people_section.kind }}">{
     "title_student": "{% trans 'Tələbə' context 'accounts.people.detail' %}",
```
How verified: perl scan of every JSON block; polib check of az/en/ru/tr found no current msgstr with `"`, `\` or newline in those contexts.
Impact: A future translation containing `\` or a newline breaks `JSON.parse`, and the whole people-detail drawer or register JS i18n fails. An autoescaped `"` or `'` would show literally as `&quot;`/`&#x27;`. Every other JSON block (≈30 files) already uses `|escapejs`.
Recommended fix: Add `|escapejs` (as in `_academic_records.html:173`) or build a dict and use `json_script`.
Effort: Small

### FQ-FE-4 Course-panel item modals (labs/assignments/projects, today's scope) still use native `alert()` for errors and skip `res.ok` checks
Severity: P3   Category: UX/Frontend   Status: CONFIRMED
Location: apps/labs/static/labs/js/lab_modals.js:141,149,164,203,224,228,402,404,431,433; assignment_modals.js (8 sites), project_modals.js (8 sites); 73 `alert(` sites in 23 files overall
Evidence: `.catch(function() { alert(I18N.errorServer); })` (lab_modals.js:404)
How verified: python scan of 417 project JS files. 21 files that call `fetch` never inspect `response.ok`/`status` (labs/assignments/projects/blog) — a non-JSON 403/500 page surfaces as a JSON parse error and then a generic alert.
Impact: Inconsistent error UX: blocking browser dialogs, not styled, not announced through the toast `aria-live` region, and they cannot be dismissed by the design-system overlay. Native `confirm()` is guarded, but `alert()` is not.
Recommended fix: Route through `EMSToast.error(...)` / `EMSCore.fetchJSON` (it already handles status and non-JSON). Add `alert(` to the native-dialog guard with an allowlist.
Effort: Medium

### FQ-FE-5 41 JS files still bind with `querySelectorAll().forEach(addEventListener)`; 59 files are DOMContentLoaded-only
Severity: P3   Category: Frontend/AJAX-safety   Status: CONFIRMED (static); impact PLAUSIBLE only for swapped panels
Location: e.g. apps/registrar/static/registrar/js/journal_list.js, apps/labs/static/labs/js/lab_modals.js:122,278,337,453, assignments/projects review_submissions*.js
How verified: python scan. Totals: 417 files, EMSReady 102, EMSDelegate 93, DCL 90, DCL without EMSReady/Delegate 59. The prior audit classified the DCL-only files as full-page (not AJAX-swapped). I did not re-verify all 41 against `AJAX_SAFE_SECTIONS`. `journal_list.js` is the only one in a cabinet section; it was not browser-tested here.
Impact: Double binding or dead handlers only if a file is loaded inside a swapped panel. The rule in docs/frontend/AJAX_SAFE_JS_PATTERN.md is not enforced by a test.
Recommended fix: Add a static guard: a file loaded from a template under `profile/sections/` must use EMSReady/EMSDelegate.
Effort: Medium

### FQ-FE-6 JS files hug the 600-line soft cap
Severity: P3   Category: Maintainability   Status: CONFIRMED
Evidence: 16 HTML/CSS/JS assets are 580–599 lines (syllabus_editor.js 599, ui.js 596, applications.js 596, schedule_editor.js 595, workload_distribution.js 595, searchable_select.js 594, …). `scripts/check_module_size.py --check` → green; budget list is empty.
Impact: The ratchet is met by trimming to just under the cap, not by cohesive modules. The next small change will force an unplanned split.
Recommended fix: Plan splits for the top 5 by responsibility, not by line count.
Effort: Medium

### FQ-A11Y-1 Error pages hard-code `<html lang="az">`
Severity: P3   Category: Accessibility (WCAG 3.1.1)   Status: CONFIRMED
Location: templates/errors/_base.html:7 (also templates/admin/verify_otp.html:3)
Evidence: `<html lang="az">`, while 400/403/404/500/network_zone pages contain 8–10 `{% trans %}` strings.
Impact: Screen readers read EN/RU/TR error pages with Azerbaijani pronunciation rules.
Recommended fix: `{% get_current_language as LANGUAGE_CODE %}<html lang="{{ LANGUAGE_CODE }}">`.
Effort: Small

### FQ-A11Y-2 Residual unlabeled controls and nameless icon buttons
Severity: P3   Category: Accessibility (WCAG 1.3.1/4.1.2)   Status: PLAUSIBLE (heuristic scan; some may be labelled via JS)
Evidence: heuristic scan of 1 073 form controls found 77 with no `<label for>`, wrapping label, `aria-label`, `aria-labelledby` or `title`, in 34 files. Top files: liveExam/_host_settings_drawer.html 13, registrar/_jd_lesson_modal.html 9 (e.g. selects `lesson_topic`/`lesson_kind`/`lesson_hours`/`lesson_time` use a visual `span.jd2-field-label` not tied to the control), exams/_create_exam_modal_form.html 5. There are 34 `<button>` elements with no text or aria-label (host_presentation.html 6, labs/manage_blocks.html 5, assignments/projects modals and review pages 2 each). `img` without alt: 0/66. Non-focusable click targets (div/span with data-bs-toggle/role=button without tabindex): 0.
Recommended fix: Wrap `jd2-field-label` + control in `<label>` or add `aria-labelledby`. Add aria-labels to the listed buttons. Extend `test_icon_only_buttons_have_aria_label` beyond its current file list.
Effort: Small

### FQ-A11Y-3 Low-contrast text token still used as text colour
Severity: P3   Category: Accessibility (WCAG 1.4.3)   Status: PARTIAL FIX of prior F6
Evidence: `--ems-neutral-400: #94a3b8` (static/css/design-tokens.css:29, 2.56:1 on white) is still `color:` in **45** rules (prior: 63). Examples: static/css/global_search.css:87,108,402; apps/registrar/static/registrar/css/jd2_window.css:43; journal_list.css:64.
Recommended fix: Use `neutral-500` or darker for text; keep 400 for borders and icons only.
Effort: Small

### FQ-I18N-1 Password-reset pages are English in all four languages (AZ catalog holds English msgstr)
Severity: P2   Category: i18n   Status: CONFIRMED
Location: apps/accounts/templates/accounts/password_reset_confirm.html:21,23,81,85; password_reset_complete.html:22,25 (key-style msgids, ctx `accounts.password_reset_confirm_page` / `…complete_page`)
Evidence (locale/az/LC_MESSAGES/django.po:6726-6728):
```
msgctxt "accounts.password_reset_confirm_page"
msgid "heading_valid"
msgstr "Set new password"
```
The next line of the same template is Azerbaijani (`Şifrəni yeniləmək üçün emailə gələn OTP kodunu da daxil edin.`). RU and TR hold the same English text.
How verified: polib dump of az/ru/tr. The same pattern (English in az/ru/tr) affects about 20 more keys: accounts/assigned_exams.html:54,69,77,87; assigned_courses.html:49; grading_queue.html:193; _grading_queue_js.html:5-6; my_results.html:156; apps/exams/domain/attempts.py:506-507 ("View answer/details"); staff_management `_staff_management_content.html:17,21,25` (RU/TR English).
Impact: A security-sensitive flow (password reset) shows mixed-language UI to every user. The catalog gate cannot see it, because `identity` compares against the AZ msgstr, which is itself English.
Root cause: Key-style msgids whose AZ msgstr was filled with English. No detector for "AZ msgstr is ASCII English" or "RU msgstr has no Cyrillic".
Recommended fix: Translate these about 25 keys. Add checker rules: AZ multi-word msgstr with no Azerbaijani letters and matching the EN msgstr → debt; RU msgstr with ≥3 Latin words and no Cyrillic → debt.
Effort: Small

### FQ-I18N-2 Registration role choices collapsed in RU/TR (teacher/staff shown as institution or even as "course student")
Severity: P2   Category: i18n / UX (wrong meaning)   Status: CONFIRMED
Location: apps/accounts/forms/auth/register.py:98-125 (`pgettext_lazy("accounts.form.register.choice", "org_type_*")`); locale/ru|tr django.po
Evidence:
```
org_type_school_teacher      ru "Школа"            tr "Okul"
org_type_university_teacher  ru "Университет"      tr "Üniversite"
org_type_course_teacher      ru "Учебный центр"    tr "Kurs merkezi"
org_type_school_staff        ru "Школа"            tr "Okul"
org_type_university_staff    ru "Университет"      tr "Üniversite"
org_type_course_staff        ru "Слушатель курса"  tr "Kurs öğrencisi"   (= course STUDENT)
```
(EN is correct: "School teacher", "Course staff", …)
How verified: polib dump; a "collapsed translation" detector (one target string for several distinct AZ sources in the same context) flagged these.
Impact: In RU/TR, the registration role picker shows the same label for org / teacher / staff, and labels course staff as "course student". Users can self-register into the wrong role type.
Recommended fix: ru «Учитель школы / Преподаватель университета / Преподаватель учебного центра / Сотрудник школы / Сотрудник университета / Сотрудник учебного центра»; tr «Okul öğretmeni / Üniversite öğretim elemanı / Kurs merkezi öğretmeni / Okul personeli / Üniversite personeli / Kurs merkezi personeli».
Effort: Small

### FQ-I18N-3 EN staff-management student tabs say "teacher"
Severity: P2   Category: i18n (wrong meaning)   Status: CONFIRMED
Location: apps/accounts/templates/accounts/partials/staff_management/_students_members.html:75, _students_pending.html:26,152, _students_unassigned.html:9,11,119
Evidence: msgid `Students without organization` → EN msgstr `Teachers without organization`; `No student found.` → `No teacher found.`; `Search pending students...` → `Search teacher invites...` (6 entries, ctx `staff.management`). RU is correct.
Impact: English UI on the student tabs tells staff they are handling teachers.
Recommended fix: Correct the 6 EN msgstrs.
Effort: Small

### FQ-I18N-4 Smaller wrong-meaning / quality items (spot-check)
Severity: P3   Category: i18n   Status: CONFIRMED
- The spot-check sampled 40 random user-facing entries outside courses/assignments/labs/projects (seed 20260928). 38 of 40 are correct in en/ru/tr. #22: `profile.groups/student_search_placeholder` RU «Поиск студента или экзамена...» (AZ: search by name/username/email). #38 is FQ-I18N-2.
- TR contains about 20 deasciified strings (no ç/ğ/ı/ö/ş/ü), mainly the registration privacy policy (register.html:99-202, `_step4.html:178`: «Hesabinizi olusturmadan once…»), register.py:282 «Devam etmek icin…» and exams `_question_management.html:391` «…bulunamadi».
- student_registry.js:201: `lang === "en" ? "Document" : "Sənəd"`, so RU/TR get Azerbaijani.
- 16 user-visible Python strings are not wrapped in gettext, e.g. apps/registrar/transfer.py:32-41 (5 ValidationErrors in the group transfer UI), apps/accounts/views/auth/_shared.py:245, apps/exams/forms/question.py:351, apps/accounts/views/people/actions.py:78.
- Baseline ratchet grew: TR identity 223 (2026-09-14) → 244 now, accepted through `--update`.
Recommended fix: Fix via one fill script, and wrap the Python strings in pgettext.
Effort: Small

### FQ-TEST-1 81 k lines of shipped JS have no JS test execution in CI
Severity: P2   Category: Testing   Status: CONFIRMED
Evidence:
- `tests/js/package.json` (jsdom harness «emsarena-shipped-js-gate») is not referenced by any workflow.
- apps/syllabus/tests/e2e/conftest.py:3 says «Node + jsdom tələb edir (CI-da node quraşdırılmayıb)».
- The only browser coverage is Playwright `tests/e2e` (9 files) in `_e2e-smoke.yml`, which runs only on the main/PR Docker chain.
- Python guard tests assert strings in JS source (a11y guards, KaTeX assets) but never run it.
Impact: Regressions in the JS for journal grid, exam score entry, syllabus editor, workload SPA or take-exam draft are found only manually. The prior audit noted "0 console errors" from a browser sweep, which is not repeatable in CI.
Recommended fix: Install node in one CI job and run the existing jsdom harness plus a few unit tests for EMSReady/EMSDelegate, `section_loader` and journal_grid save payloads. Run the Playwright smoke nightly on Develop.
Effort: Medium

### FQ-TEST-2 Concurrency and time-dependence are thinly tested
Severity: P3   Category: Testing   Status: CONFIRMED
Evidence:
- 54 test files mention `select_for_update`/concurrency/`TransactionTestCase`, mostly registrar grade/exam-score and subject_folder.
- The syllabus agent found no race tests for submit/autosave/approve.
- `time_machine`/`freezegun` appear in 0 test files and 0 requirements (prior F-T14 still OPEN).
- `apps/accounts/tests/test_view_as_session_end.py` is PG-only through `_skip_if_not_pg()` but has no `postgres` marker (prior F-T13 still OPEN).
Recommended fix: Add `time_machine` for journal "today" and edit-window rules. Add `TransactionTestCase` race tests for syllabus submit/autosave and appeal decisions.
Effort: Medium

## 3c. Testing: suite size and critical-workflow coverage

**Size:**
- 726 test files, **9 155** `def test_` functions, 210 k lines.
- By app:

| App | Tests |
|---|---|
| accounts | 2 116 |
| registrar | 1 418 |
| exams | 1 369 |
| legacy_import | 1 127 |
| organizations | 406 |
| syllabus | 254 |
| workload | 172 |
| appeals | 90 |
| timetable | 51 |

- There are also 9 Playwright E2E files and 33 root `tests/` guards: URL auth sweep, query budgets, module gate, i18n terminology, migration single-leaf.

**CI:**
- `ci.yml` runs 8 pytest-split shards (`least_duration`, `.test_durations` with 9 456 entries, last refreshed 2026-09-20), `-n 4 --dist loadfile`, timeout 300.
- RLS tests run in 2 shards.
- Coverage (`--cov-fail-under=68`) runs only on PR/dispatch with Python 3.11 (`ci.yml:66-69`), so direct pushes to Develop are never coverage-gated.

**Coverage per critical workflow:**

| Workflow | Meaningful tests | Gaps found today |
|---|---|---|
| Tenant isolation | RLS tests per app, `tests/test_url_auth_sweep.py`, 74 files with cross-org cases | not re-audited here (tenancy auditor) |
| Permissions | 105 files assert 403, permission matrices | self-approval (SYL-1), group-registry scope (S3/S4) untested |
| Exams → grades | exams 1 369, `test_journal_bridge`, `test_w2_duplication` | multi-attempt re-sync (EXA-01), history percent/category (EXA-03), hall-path eligibility (EXA-04) |
| Journal | ≈60 registrar files, 277 targeted pass | `update_lesson` validation (J-02), `save_finals` ledger (J-01), garbage component input (J-03), the 2 h PG trigger itself |
| Enrollment / lifecycle | transfer, movements, groups_registry tests | enrollments on expulsion/leave (S1), split → offerings (S2) |
| Syllabus approval | workflow/state_machine/review_scope/chair authority (331 pass together with appeals) | self-approval, reject → next version, races |
| Appeals | 13 files | concurrent reviewers, 5-minute re-edit actor, ungraded written attempts, category |
| Workload / timetable | 172 / 51 | hours below assigned (W2), double-booking races (W3), task-status filter (W5) |
| Frontend JS | 0 executed JS tests in CI | FQ-TEST-1 |

## 4. Scores (0–100)

| Area | Score | One-line justification |
|---|---|---|
| **Business Logic** | **71** | Mean of the flow sub-scores (syllabus 80, journal 80, exam→appeal 62, student lifecycle 68, workload→timetable 66). Core state machines, locks and ledgers are sound. Deductions: 3 confirmed P1s (self-approval, appeal regresses the official grade, expelled students stay enrolled) and ~14 P2 integrity gaps. |
| **Frontend** | **83** | No React/TS. 0 executable inline JS/CSS (36 JSON/ld+json blocks only), CSRF on all POSTs, all prior JS findings fixed, module budget green. Deductions: 2 CSP-blocked `onclick`, 73 native `alert()`, JSON blocks without escapejs, cap-hugging files, no JS tests. |
| **UX/UI** | **77** | `ems_ui` dominates (3 082 uses), legacy `card` halved (1 194 → 586), EMSConfirm everywhere guarded, ARIA tabs in the new course panel, empty/loading states common (96 / 55 templates). Deductions: native `alert()` error UX in labs/assignments/projects, 21 fetch files that ignore `res.ok`, 5 parallel BEM systems remain. |
| **Accessibility** | **76** | F5/F10/F15–F18 fixed with guard tests; 0 img without alt; 0 non-focusable click targets; 214 `:focus-visible` rules; reduced-motion in 44 files. Deductions: 45 low-contrast text rules, error pages `lang="az"`, ~77 unlabeled controls / 34 nameless buttons (heuristic), no screen-reader attestation. |
| **Testing** | **75** | Large, well-sharded suite with strong guard tests. Deductions: today's P1/P2 flow bugs had no covering tests; no JS execution in CI; no time_machine; thin race tests; coverage gate only on PRs. |
| **Internationalization** | **76** | Gate green (0 missing, untranslated, placeholder or raw-key debt in 4 languages × 2 domains), all prior semantic P1s fixed, 38/40 spot-check correct. Deductions: password-reset and ~20 other keys English in all languages, RU/TR registration role collapse, EN "teacher" on student tabs, ~20 deasciified TR strings, checker blind spots (English-in-AZ/RU), TR identity ratchet raised 223 → 244. |

## 5. Prioritized remediation (my areas)

| # | Priority | Action | Dependency | Risk | Effort | Benefit |
|---|---|---|---|---|---|---|
| 1 | P1 | EXA-01: skip the journal sync for superseded attempts (or re-sync the latest), plus a regression test | none | low | S | stops official grades regressing |
| 2 | P1 | S1 + C1: on expulsion or leave, move current ENROLLED enrollments to suspended/withdrawn (restore on reinstatement); filter `course_groups` by record status | owner confirms display rule | medium (roster/stat queries) | M | expelled students out of journals, sheets and LMS |
| 3 | P1 | SYL-1: `forbid_author` on approve, revise and reject, routed to dean/org | owner confirms routing | low | S | four-eyes on syllabi |
| 4 | P2 | J-01 / J-02: route `save_finals` exam/resit through `record_exam_score`; validate plus audit `update_lesson` | none | low | S | the period lock and the admission rule can't be bypassed |
| 5 | P2 | SYL-3 / SYL-4 / SYL-2: lock the version in autosave; check before escalating; baseline = approved version | none | low | S | versioning integrity |
| 6 | P2 | EXA-03 / EXA-02 / EXA-04: fix the history surface (finals only, correct %, appeal rows, dean/coordinator read); require graded before appeal; eligibility on hall/PIN paths | owner memo | medium | M | owner requirement met; admission enforced |
| 7 | P2 | W1 / W2 / W3 / W4: chair-draft cutoff, row-hours floor, advisory lock around schedule writes, conflict re-check on instructor change | none | medium | M | approval chain + no double-booking |
| 8 | P2 | S2 / S3 / S4: carry instructor across a split; scope group candidates and write scope | none | low | M | no orphan journals |
| 9 | P2 | i18n: fix FQ-I18N-1/2/3 (≈35 msgstrs) in one fill script; add checker rules for English-in-AZ and Latin-only RU | none | low | S | correct language on auth, registration and staff pages |
| 10 | P2 | FQ-TEST-1: wire the `tests/js` jsdom harness or a nightly Playwright run on Develop; add `time_machine`; race tests for syllabus submit and appeal decisions | CI minutes | low | M | JS and race regressions caught |
| 11 | P3 | FQ-FE-1 / FQ-FE-2: replace the 2 `onclick=confirm` with `data-ems-confirm`; HTML guard for `on*=`; fix the CLAUDE.md grep | none | low | S | CSP rule actually enforced |
| 12 | P3 | FQ-FE-3 / FQ-FE-4: add `escapejs` in people/register JSON; replace `alert()` with toast / `EMSCore.fetchJSON` | none | low | S–M | robust, consistent error UX |
| 13 | P3 | FQ-A11Y-1/2/3: `lang="{{ LANGUAGE_CODE }}"` on error pages; label the jd lesson modal and host drawer; neutral-400 → 500 for text | none | low | S | WCAG 3.1.1 / 1.3.1 / 1.4.3 |
| 14 | P3 | J-03..J-09, EXA-05..08, SYL-5..7, W5/W6, S5, F-T8/F-T13: small hardening items (DB CHECKs on marks, locks, validation) | none | low | S each | defence in depth |
