# Audit 2026-09-28 — slug `exams` (Exam System + Concurrency/exam part)

Scope: apps/exams (student attempt flow, final centre/PIN, grading, results, sweeps, journal bridge), apps/live_exam,
apps/appeals, apps/trial_exams (as they touch results). Branch `Develop`, HEAD `914a6571` + uncommitted tree of 2026-09-28
(only exams changes today: `public.py` re-export + new `services/ai_json.py` used by courses AI planner, 2 template
`{% trans %}` context edits — reviewed, no exam-integrity impact).

## 1. Scope & method (what was actually run)

- Code read end-to-end: `views/student/{attempts,_answer_writes,access_guard,_timer_write_guard,results,coding,question_timer,final_center}.py`,
  `views/shared/access.py`, `domain/{attempts,access_policy}.py`, `services/{attempts,sweep_guard,student_pins,manual_grading,journal_sync,result_release,review_visibility,randomizer}.py`,
  `services/final_center/entry.py`, `consumers.py`, `tasks.py`, teacher results/grading views, bulk-import save path, `core/media_views.py` exam checkers.
- AST scan of every `request`-first view in `apps/exams/views` for a visible authorization guard (script
  `scratchpad/audit/exams_scratch/scan_views.py`); all hits spot-checked — each resolves to a helper guard (`get_center_session_or_404`,
  `center_org_or_403`, `_stats_org`, `_resolve_own_ticket`, …). No unguarded view found.
- Two read-only sub-reviews (live_exam; appeals + trial_exams). Their key claims were re-verified by me where marked.
- Sandbox Postgres `:55432/ems_audit_exams` (own DB), `USE_REDIS=False`:
  - `pytest apps/exams/tests/test_audit_2026_09_13_exam_integrity.py` → **19 passed** (prior EX-01…EX-10 regressions).
  - Scratch proofs `scratchpad/audit/exams_scratch/test_scratch_exams_0928.py` → **6 passed** (PASS = finding confirmed):
    `[A] min(option id) == correct for 8/8 questions; display-order-first correct for 2/8`,
    `[B] attempt1 correct=0 attempt2 correct=3 (of 3)`, `[C] status=submitted teacher_score=3 (stale, locked)`,
    `[D1] after sweep at deadline+3s the finish POST is dropped; saved=[]` (+ D2 same via a GET),
    `[E] sweep finished=1; concurrent NOWAIT lock on non-overdue attempt -> {'locked': 'OperationalError'}`.
- Not done: browser run, load test, Redis-down runtime test, coding sandbox (Piston disabled in prod compose).

## 2. Status of prior findings (2026-09-13 `findings/exams.md`)

| ID | Title | Status | Evidence |
|---|---|---|---|
| EX-01 P0 | result page of open attempt leaks key | **FIXED** | `results.py:141-143` expire + redirect; `InProgressResultPageTests` pass |
| EX-02 P1 | `/exams/code-check/` starts final outside hall | **FIXED** | `shared/access.py:93-97`; `CodeCheckFinalGateTests` pass. `start_exam` cannot start a final either (`access_policy.py:322-331` requires PIN when no active attempt) |
| EX-03 P1 | no PIN brute-force limit on code-check | **FIXED** | `shared/access.py:78-87` per-username limiter, 429 |
| EX-04 P2 | ticket path bypasses start policy | **FIXED** | `TicketStartPolicyTests` pass |
| EX-05 P2 | finish POST at deadline dropped | **PARTIALLY FIXED** — 15 s grace on POST (`attempts.py:397-398`) but defeated by the sweep and by any GET → see **EX28-04** |
| EX-06 P2 | per-student PIN path skips IP limiter | **FIXED** | `final_center.py:251-252` |
| EX-07 P2 | rejected upload deletes old files | **FIXED** | `_answer_writes.py:153-159` validate-then-replace |
| EX-08 P2 | draft outside unique constraint | **FIXED** | `domain/attempts.py:224-228` (`draft`,`in_progress`), migr. 0066 |
| EX-09 P2 | autosave lock takes `exams_exam` row | **FIXED** | `attempts.py:204-208` `select_for_update(of=("self",))`; `AutosaveLockShapeTests` pass |
| EX-10 P1 | bank question write by read-visibility | **FIXED** | `BankQuestionWriteOwnershipTests` pass |
| EX-11 P3 | finish N+1 | **FIXED** | `TestAnswerWriteBatch` (`_answer_writes.py:27-82`) |
| EX-12 P3 | examanswer RLS subplan | **CLOSED** (measured 2.4 µs/row, `ee58830b`; jit=off `8206abdb`) |
| note | `ERROR_LOCKED` reveals locked ticket | **STILL OPEN** (P3) `final_center/entry.py:153-157` |
| note | PIN login yields full platform session | **STILL OPEN** (P3, design) `final_center.py:280-282` |
| note | reissue/revoke PIN not audited | **MOOT** — `revoke_student_pin` has no callers; `reissue_student_pin` only via audited `second_chance.py:130` |
| note | capacity gate fails open without Redis | **STILL OPEN** (design, DB constraints hold) `services/attempts.py:84-86` |

## 3. New findings

### EX28-01 Option DB ids reveal the correct answer for END_QUESTION-imported questions
Severity: P0   Category: exam-answer exposure   Status: CONFIRMED
Location: `apps/exams/services/parsing/_core.py:258-262` (convention: in END_QUESTION format the first variant is correct);
`apps/exams/views/teacher/question_bank/_views_misc.py:357-371` and `views/teacher/question_library/_shared.py:162-173`
(options persisted in label order A→E via `bulk_create`); `services/question_bank_attach.py:240-247` (bank→exam copy keeps order);
`templates/exams/student/take_exam.html:241,256` and `partials/_delivered_question_body.html:51,65` (`value="{{ opt.id }}"`);
`services/randomizer.py:60-76` (shuffle changes display order only, keeps raw ids).
Evidence:
```
for lab in "ABCDE":
    if lab in options:
        option_rows.append(ExamQuestionOption(question=eq, label=lab, text=options[lab], is_correct=(lab in correct)))
...
<input type="radio" name="q_{{ q.id }}" value="{{ opt.id }}" ...>
```
How verified: scratch test `EndQuestionOptionIdLeakTests` — teacher imports 8 END_QUESTION questions through the real
`test_question_bank` save view, student opens `take_exam`; for **8/8** questions the smallest radio `value` is the correct option
(display order put the correct option first only 2/8 times, i.e. the shuffle works but the ids betray it).
Impact: any student who opens View Source / DevTools (or a trivial bookmarklet) answers every END_QUESTION-imported question
correctly — including finals, since final/midterm test exams use the same `take_exam` page. The convention is used for real banks
(parser comment: the defaulted-A warning used to flood the workbench with 299 errors). For other formats, id rank still reveals the
author's original letter.
Root cause: raw sequential primary keys used as answer values; creation order == author order.
Recommended fix: (1) submit an opaque per-attempt token instead of `opt.id` — e.g. displayed index from the deterministic shuffle
(`random.Random(f"{attempt_id}:{question_id}")`, already used) or `salted_hmac(attempt_id, option_id)`; map back server-side in
`selected_option_ids_from_request`; this also protects already-imported questions. (2) Shuffle rows before `bulk_create` in every
creation path (import, bank import, bank→exam attach, language variants, AI generation). Add a regression test asserting
`min(value)` is not correlated with correctness.
Effort: Medium

### EX28-02 Teacher can grade an in-progress written attempt; grade is journal-synced and then frozen
Severity: P1   Category: grading integrity / data corruption   Status: CONFIRMED
Location: `apps/exams/views/teacher/results/_attempt_views.py:217-305` (`teacher_check_attempt` — no `is_finished` check);
`services/manual_grading.py:185-262` (`apply_manual_grading` — no status check) → `_mark_attempt_graded` → `schedule_journal_sync`
(`manual_grading.py:48-52`); `services/journal_sync.py:190-236` (`sync_attempt_to_journal` — no `is_finished` check);
`views/teacher/results/_helpers.py:219-251` (results list offers «Yoxla» for any status; list includes `in_progress`/`draft`, `_helpers.py:388-393`);
`services/review_visibility.py:45-54` (5-min lock starts at `teacher_checked_at`).
Evidence:
```
attempt = ExamAttempt.objects.select_for_update().get(pk=attempt_id)
if attempt_review_window_locked(attempt, current_time=now):
    raise ManualGradingWindowClosed
answers = list(attempt.answers.select_for_update()...)   # no status check anywhere
```
How verified: `GradeInProgressAttemptTests` — results page contains the check URL for the in-progress row; teacher POST → 302,
attempt still `in_progress`, `checked_by_teacher=True`, `teacher_score=3`, journal sync callback fired; 6 min later student
finishes with full answers; teacher re-grade is refused (window closed); final state `submitted`, `teacher_score=3`.
Impact: an official score computed from partial answers is written to `FinalGrade` (for `final` category) while the student is
still writing, and after 5 minutes it can no longer be corrected by the teacher (only via appeal/registrar correction). Student
visibility rule (`annotate_attempt_result_visibility`) then shows the stale grade.
Root cause: grading entry points assume finished attempts; UI does not filter by status.
Recommended fix: in `apply_manual_grading`/`apply_single_answer_grade`/`apply_attempt_grade` raise if `not attempt.is_finished`
(under the existing lock); in `teacher_check_attempt` redirect to view-only for unfinished attempts; `_resolve_attempt_action_state`
→ no «Yoxla» for `draft`/`in_progress`; `sync_attempt_to_journal` early-return when `not attempt.is_finished`. Also stop
`teacher_check_attempt` GET from calling `generate_random_questions_for_attempt` on a student's attempt (`:256-257`).
Effort: Small

### EX28-03 Multi-attempt exams: answer key of attempt N is shown immediately → full score on attempt N+1
Severity: P2   Category: exam integrity / policy gap   Status: CONFIRMED
Location: `apps/exams/services/result_release.py:17-22` (`exam_answers_release_locked` always `False`, owner decision 2026-07-13);
`views/student/results.py:152-154`; `templates/exams/student/exam_result.html:302-311` (`correct-option`);
`services/attempts.py:347-373,373-460` (retake allowed without considering that the key was disclosed).
How verified: `AnswerKeyThenRetakeTests` — quiz `max_attempts_per_user=2`, pool == delivered count: blank attempt 1 → result
page shows `correct-option` + key text → attempt 2 scored 3/3 (attempt 1: 0/3).
Impact: any exam with `max_attempts_per_user>1`, unlimited attempts, or a teacher «second chance» grant (`second_chance.py`) —
including finals — can be passed by sacrificing one attempt when the pool is not much larger than the delivered count. The owner
decision explicitly accepted early-finisher leakage in the hall, not retake leakage.
Recommended fix: hide the key (keep verdict/score) when the student still has attempts left or a grant exists
(`attempts_left_for(user) != 0`), or release it only after the last allowed attempt / `end_datetime`. Product decision needed.
Effort: Small

### EX28-04 Deadline grace (EX-05 fix) is defeated by the 60 s sweep and by any GET
Severity: P2   Category: concurrency / answer loss   Status: CONFIRMED
Location: `apps/exams/services/attempts.py:231` (`sweep_overdue_attempts` → `expire_if_time_limit_reached()` without grace);
`views/student/attempts.py:397-398` (grace applied only to POST); `views/student/results.py:141`; `services/attempts.py:187-192`
(`get_active_attempt_for_user` lazy expiry, no grace); client posts finish 1.5 s after the timer reaches 0 (`static/exams/js/take_exam/timers.js`).
How verified: `SweepIgnoresGraceTests` — deadline+3 s, sweep runs → finish POST returns `already_finished`, selection not saved
(D1); same with a GET of `take_exam` from another tab/reload (D2). Control: prior `DeadlineGraceTests` pass when nothing else touches the attempt.
Impact: whatever changed since the last autosave (≤1 s test / ≤3 s written, plus any queued autosave) is discarded. In a
supervisor-started final all deadlines coincide, so one badly-phased sweep (probability ≈ (1.5 s + latency)/60 s per exam) hits
the whole room at once.
Recommended fix: apply `EXAM_SUBMIT_GRACE_SECONDS` in the sweep (`at_time=now-grace`) and in all lazy GET expiries, or make GET
expiry mark-only after `deadline+grace`; keep the locked POST path as the only one that closes inside the grace window.
Effort: Small

### EX28-05 With `RLS_TRANSACTION_SCOPED=True` the global sweep row-locks every open attempt for its whole run
Severity: P2 (latent — flag is OFF in prod today; staged rollout documented in `docs/operations/FAZA4_STAGING_RUNBOOK.md`)
Category: concurrency / performance   Status: CONFIRMED (sandbox, flag forced on)
Location: `apps/exams/tasks.py:45-63` (`with rls_worker_atomic(), bypass_rls(): sweep_overdue_attempts()`);
`core/rls_pooling.py:106-108` (`transaction.atomic()` when flag on); `services/sweep_guard.py:91-106` (per-attempt `atomic()` becomes a
savepoint; `select_for_update(skip_locked=True)` is issued for every open attempt, overdue or not — no deadline filter in SQL).
How verified: `SweepHoldsAllRowLocksTests` (TransactionTestCase): inside the outer atomic after the sweep processed 2 attempts, a
second connection's `SELECT … FOR UPDATE NOWAIT` on the NON-overdue attempt → `OperationalError` (lock held).
Impact: once the flag is enabled, every 60 s all students' autosave/finish (`select_for_update` without `skip_locked`) block until
the sweep over all open attempts commits (thousands of row locks in a big final); journal `on_commit` callbacks are also deferred
to the end; one exception rolls back the whole sweep (no per-attempt isolation — also true with flag off: an exception aborts the loop).
Recommended fix: run each attempt in its own real transaction (do not wrap the sweep in `rls_worker_atomic`; set `SET LOCAL`
bypass per inner atomic), pre-filter candidates in SQL by deadline (`started_at + duration < now - grace`), and wrap `action` in
try/except per attempt. Add this test to the `rls-txn-pool` CI job.
Effort: Small–Medium

### EX28-06 Journal `FinalGrade.exam_score` is last-write-wins across attempts
Severity: P2   Category: data integrity   Status: PLAUSIBLE (code-confirmed mechanism; sequence not reproduced)
Location: `apps/registrar/finals.py:318-325` (`set_exam_score` overwrites unconditionally); `apps/exams/services/journal_sync.py:190-247`
(sync carries no attempt identity/ordering); re-sync triggers: `mark_finished`, `_mark_attempt_graded`, appeal accept/revert
(`apps/appeals/services/decisions.py:289,363`).
Impact: with a second-chance/retake final, a later event on the OLDER attempt (manual re-grade inside the window, appeal accepted
days later) overwrites the newer attempt's score in the official journal; also EX28-02 feeds partial scores in.
Recommended fix: store `source_attempt_id` on `FinalGrade` (or pass it to `record_exam_result`) and apply an explicit policy
(latest finished attempt / best attempt) instead of “last sync wins”.
Effort: Medium

### EX28-07 Exam window: `deadline_at` ignores `end_datetime`; duration is optional
Severity: P3   Category: exam rules   Status: CONFIRMED (code read)
Location: `apps/exams/domain/attempts.py:243-250`; `domain/exam_definition.py:88-97` (`null=True`, “empty = no limit”);
`views/student/attempts.py:195-357` (POST path never checks `exam.is_after_end()`).
Impact: a student who starts one minute before `end_datetime` gets the full duration after the window closes; with no duration the
attempt never expires and answers can be changed indefinitely after the exam ended.
Fix: `deadline_at = min(started_at + duration, end_datetime)` when `end_datetime` is set (product decision).
Effort: Small

### EX28-08 Coding submit accepted after the deadline
Severity: P3   Category: timer enforcement   Status: CONFIRMED (code read)
Location: `apps/exams/views/student/coding.py:493-510,514,582` — `coding_submit` grades and stores the final submission even when
`is_time_limit_reached()`; only the status becomes `expired`. `coding_autosave`/`coding_run` do expire lazily.
Impact: bounded by the 60 s sweep normally; unbounded while Celery beat is down.
Fix: reject (or apply the same grace as test/written) when `now > deadline + grace`.
Effort: Small

### EX28-09 Coding submission ZIP downloadable by any teacher of the organisation
Severity: P3   Category: authorization (intra-org)   Status: CONFIRMED (code read)
Location: `apps/exams/views/student/coding.py:156-174` — teacher branch = `_ensure_teacher` + `tenant_scoped_exams(request)` (org-wide,
not author/centre-scoped), unlike `teacher_view_attempt` (`get_result_viewable_exam_or_404`, author or exam centre).
Note: `core/media_views.py:121-161` applies the same org-wide teacher rule to written-answer uploads/paints (consistent, but broad).
Fix: use `get_result_viewable_exam_or_404` for the teacher branch.
Effort: Small

### EX28-10 live_exam: per-player correctness returned before reveal
Severity: P2   Category: answer exposure (non-official quiz)   Status: CONFIRMED (code read, re-verified)
Location: `apps/live_exam/scoring.py:290-303` (`answer` payload has `is_correct`, `picked_correct`, `picked_wrong`, `correct_total`);
`consumers.py:288` (`answer_saved` sent immediately); `views/api.py:233-249`; state endpoint `views/api.py:159-160`
(`player_answer` during open question).
Impact: combined with trivial multi-join (client-controlled `live_client_id` cookie also keys the join rate-limit —
`views/player/_shared.py:151-152`), one person probes options with throw-away players and answers correctly with the main one.
Rated P2, not P0/P1: live sessions are anonymous and not linked to gradebook/journal.
Other live_exam items (sub-review, not re-run): PIN prefix match `pin__startswith` + unthrottled GET join (`_shared.py:100-116`,
`join.py:74-75,138-144`) P2; server never enforces `max_select` → select-all partial credit (`scoring.py:221`) P2;
`live_create_session_by_slug` state change via GET (`views/host/session.py:27-87`) P2/P3; host/auto-reveal race, removed player keeps WS P3.
Fix: return only `{"saved": true}` until reveal; key join limiter by IP + session; exact PIN match; enforce `max_select`; POST-only create.
Effort: Small each

### EX28-11 Appeals: internal reviewer note shown to student; «already correct» check uses live key
Severity: P3   Category: confidentiality / scoring consistency   Status: CONFIRMED (code read)
Location: `apps/appeals/templates/appeals/partials/_review_appeal_body.html:206-210` (placeholder «Opsional daxili qeyd») vs
`_appeal_detail_body.html:69-72` (rendered to student); `apps/appeals/services/scoring.py:299-307` (`_question_already_correct` uses live
`selected_options`/`options`, base score uses delivery snapshot — `result_calculation.py`).
Also from sub-review (PLAUSIBLE, not reproduced): accepting an appeal on an ungraded written attempt makes `teacher_score` non-null
and syncs a partial percentage (`decisions.py:228-246`); revert on re-edit loses reviewer identity (`views/teacher/endpoints.py:302`).
Trial exams: per-account 8×25 MB/h upload with no total quota/retention (`apps/trial_exams/views.py:38`) — P3.
Effort: Small

### P3 notes (no card)
- Lazy expiry on GET paths is a blind unlocked write (`domain/attempts.py:273-278` called from `take_exam`, `exam_result`,
  `get_active_attempt_for_user`, coding) — can race a locked POST at the deadline boundary (status/`finished_at` overwrite,
  duplicate journal sync). Sweep was fixed for this (P2-6); GET paths were not.
- Final/midterm PIN never expires (`provision_exam_student_pins` sets `expires_at=None`, `student_pins.py:105-114`) — acceptable
  because entry is hall/IP gated for finals; midterm via `code-check` works from anywhere (policy).
- `access_code` compared with `!=` (`access_policy.py:345`) — rate-limited, low value.
- Redis outage: `student_pin_login_rate_limited` (`student_pins.py:51-56`) and sweep overlap lock call the cache without guards →
  `/exams/final/` login 500s while Redis is down (final entry depends on Redis).
- AI written grading is suggestion-only (`_attempt_views.py:336-377`) — student text is a prompt-injection vector into the
  suggestion; teacher must confirm (acceptable).

### PASS highlights (verified)
Server-side deadline + lock + OCC 409 on autosave/finish; idempotent double submit (`already_finished`); coding submit under row
lock; DB unique constraints for open attempt/attempt number; ownership filter `user=request.user` on every student attempt
endpoint; `take_exam`/`question-seen` HTML/JSON contain no `is_correct`; hidden coding test cases redacted
(`coding_runtime/grading.py:120-132`); question media only after delivery (`core/media_views.py:253-333`); supervision WS limited to
owner/author/superuser; final entry session bound to ticket (`entry.py:322-333`); manual grading ledger + AuditLog; journal sync
synchronous on_commit (no Celery dependency), category-gated to `final`.

## 4. Scores

| Area | Score | Justification |
|---|---|---|
| Exam System | **70 / 100** | All 2026-09-13 P0/P1 fixes hold (19/19 regression tests), strong timer/lock/tenant design; but a new P0 answer-key leak via option ids (END_QUESTION banks), P1 grading of unfinished attempts into the journal, and retake-after-key leakage keep it below 80. |
| Concurrency (exam part) | **75 / 100** | Row locks, OCC, unique constraints, skip_locked sweep are solid; grace window defeated by sweep/GET, latent all-rows lock under transaction-scoped RLS, last-write-wins journal, unlocked lazy expiry on GET. |

## 5. Prioritized remediation (exams)

| Pri | Action | Dependency | Risk | Effort | Benefit |
|---|---|---|---|---|---|
| 1 | EX28-01: opaque per-attempt option tokens in take_exam/question-seen + shuffle on create | none (template + `selected_option_ids_from_request`) | Medium — autosave/finish/OCC and saved-answer rendering must map tokens; cover with tests | Medium | closes P0 key exposure, incl. existing banks |
| 2 | EX28-02: refuse grading/journal sync of unfinished attempts; hide «Yoxla» for open rows | none | Low | Small | no partial official grades |
| 3 | EX28-04: grace in sweep + lazy GET expiry | none | Low | Small | no lost last answers in finals |
| 4 | EX28-05: sweep per-attempt real transactions + SQL deadline prefilter + per-attempt try/except; add to rls-txn-pool CI | before enabling `RLS_TRANSACTION_SCOPED` | Low | Small–Medium | avoids room-wide autosave stalls after rollout |
| 5 | EX28-03: key release policy for multi-attempt / granted exams | owner decision | Low | Small | closes retake loophole |
| 6 | EX28-06: attempt-aware journal write policy (`source_attempt_id`) | registrar change + migration | Medium | Medium | deterministic official score |
| 7 | EX28-10: live_exam — no correctness before reveal, IP-keyed join limit, exact PIN, enforce max_select, POST-only create | none | Low | Small | fair live quizzes |
| 8 | EX28-07/08/09/11 + P3 notes | product decisions for 07 | Low | Small | hygiene |
