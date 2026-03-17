# N+1 Query Audit — Before/After Profiling Notes

## Summary

This document records the N+1 query patterns found, the fixes applied, and the
estimated query-count reduction for the heaviest live-exam and middleware flows.

---

## 1. `serialize_question_results` (apps/live_exam/serializers.py)

### Before

Two separate database round-trips for the same set of answers:

```
Query 1: SELECT id, answer_ms, created_at
         FROM live_exam_liveanswer
         WHERE session_id = ? AND question_id = ?
         ORDER BY answer_ms, created_at, id
         -- used only to build the speed-rank lookup

Query 2: SELECT liveanswer.*, liveplayer.*
         FROM live_exam_liveanswer
         JOIN live_exam_liveplayer ON …
         WHERE session_id = ? AND question_id = ?
         ORDER BY awarded_points DESC, answer_ms, created_at, id
         LIMIT 50
```

### After

Single query with `select_related("player")`; speed rank is computed in Python:

```
Query 1: SELECT liveanswer.*, liveplayer.*
         FROM live_exam_liveanswer
         JOIN live_exam_liveplayer ON …
         WHERE session_id = ? AND question_id = ?
         ORDER BY answer_ms, created_at, id
```

**Savings: −1 query per reveal event / API call.**

---

## 2. `detect_multi` & `build_options` (apps/live_exam/domain/session.py, serializers.py)

### Before

Both functions issued independent `SELECT` queries against `ExamQuestionOption`:

```
# detect_multi
SELECT id FROM exams_examquestionoption
WHERE question_id = ? AND is_correct = true

# build_options
SELECT id, label, text, is_correct FROM exams_examquestionoption
WHERE question_id = ?
ORDER BY id
```

When called together (e.g. during `serialize_question` → host-start-game flow),
this was **2 option queries per question**.

### After

Both functions now use the ORM relation accessor `exam_question.options.all()`.
Query sites that call `prefetch_related("options")` before passing the question
object to these helpers pay **0 extra queries** (the Django prefetch cache is
reused).

Prefetch added in:
- `get_question_by_index` — used by host start-game, next-question, skip-intro
- `get_active_question` — used by the scoring path (answer submission)
- `build_reveal_payload` — used by host-reveal and auto-reveal
- `build_player_reveal_payload` — used by auto-reveal (player broadcast)

**Savings: −1 to −2 option queries per question served/revealed.**

---

## 3. `build_lobby_state_payload` & `live_state_json` (transport.py, views/api.py)

### Before

In lobby state, player data was fetched **twice**: once for the player list and
once for the count:

```
# live_state_json
SELECT COUNT(*) FROM live_exam_liveplayer WHERE session_id = ?   -- count

# serialize_players
SELECT id, nickname, avatar_key, accessory_key
FROM live_exam_liveplayer
WHERE session_id = ?
ORDER BY -created_at LIMIT 200                                   -- list
```

`build_lobby_state_payload` had the same pattern.

### After

The player list is fetched once; `len()` is used for the count:

```
SELECT id, nickname, avatar_key, accessory_key
FROM live_exam_liveplayer
WHERE session_id = ?
ORDER BY -created_at LIMIT 200
```

**Savings: −1 COUNT query per lobby-state request / WebSocket join.**

---

## 4. `OrganizationMiddleware.__call__` (apps/organizations/middleware.py)

### Before

`_materialize_legacy_teacher_membership(request.user)` was called
**unconditionally** for every authenticated HTTP request, regardless of whether
an active organization was already set in the session. This function accesses
`user.profile` and `profile.organization`, potentially triggering 2–3 extra
queries (profile lookup, org lookup, and sometimes a membership query) on every
request even for users who have already been backfilled.

A second call then happened inside `if request.organization:` with the proper
org + memberships context.

### After

The unconditional early call is removed. The backfill is now only invoked when
`request.organization is None` (i.e. the user has no active-org session), which
is the only scenario where the backfill is actually needed. Users with an active
session org are backfilled by the existing call in the `if request.organization:`
block (which receives the already-loaded memberships, skipping the extra fetch).

**Savings: −2 to −3 queries per request for all authenticated users who already
have an active organization in their session (the common case).**

---

## Endpoints Reviewed for Pagination / Caching / Async

| Endpoint | Notes |
|---|---|
| `live_state_json` | Rate-limited; lobby player count optimized above |
| `host_start_game` | One-shot; questions pre-fetched with options |
| `host_next_question` | One-shot; question pre-fetched with options |
| `host_reveal` | One-shot; question pre-fetched with options |
| `serialize_question_results` | Now single query; already capped at 50 rows |
| `serialize_players` | Already capped at 200 rows |
| `serialize_top` | Already capped; uses `.values()` — no extra joins |
| `OrganizationMiddleware` | Backfill moved to conditional path |

Pagination, additional caching, and async processing were not required for the
current traffic levels but should be revisited if session player counts
consistently exceed 200 or if the middleware becomes a bottleneck under
horizontal scale.
