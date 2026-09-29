# Live exam — security review (LX-SEC, Audit 2026-09-28)

Scope: the HTTP surface of `apps/live_exam` (`urls.py`, `api/v1/urls.py`), player identity (`auth.py`),
host/player/results views, rate limits, and — as a scope addition — typed answers. WebSocket consumers
(`consumers.py`) are owned by LX-BE; WS findings below ship as PoC tests only.

Method: every finding was first reproduced with a failing test in the local sandbox DB, then fixed; the
same test now guards the fix. Tests live in `apps/live_exam/tests/test_lx_sec_*.py`
(shared fixtures: `lx_sec_support.py`). WS PoCs are `xfail(strict=False)` until LX-BE lands the fix.

Threat model notes:

* 90–150 legitimate students join from **one university NAT IP**, on phones, with flaky Wi-Fi (reloads,
  reconnects, the odd PIN typo). Any per-IP bucket is shared by the whole class — an IP limit that counts
  legitimate traffic locks a real class out.
* Players are anonymous; a cookie jar is the only identity. A student can always get a fresh identity by
  clearing cookies, so the lobby **lock** (host) is the real control against unwanted joins.
* 10-character PINs from a 31-symbol alphabet (~49.5 bits): brute force is infeasible even without limits;
  the PIN-miss budget is defence in depth and load control, not the primary control.

## Findings

| ID | Severity | Finding | Status | Test |
|----|----------|---------|--------|------|
| LXS-01 | P2 | Live results (list, detail, JSON, AI summary) readable by **any** teacher with `exam.host`/`exam.manage` in the org — question texts and correct-option colours (`chart_data.colors`) of someone else's exam | Fixed | `test_lx_sec_access.py::ResultsAccessMatrixTest` |
| LXS-02 | P2 | NUL / control characters in a nickname → PostgreSQL error → HTTP 500 | Fixed | `test_lx_sec_identity.py::NicknameJoinTest::test_nul_byte_nickname_does_not_crash`, `NicknameNormalizationUnitTest` |
| LXS-03 | P2 | Invisible (zero-width, Hangul filler, Braille blank), bidi-override and homoglyph nicknames (`Ali​`, `‭Ali`, Cyrillic `Аli`, fullwidth `Ａｌｉ`, `ALİ`) passed the `iexact` uniqueness check → impersonation on the leaderboard/podium; invisible-only names accepted | Fixed | `NicknameJoinTest::test_invisible_and_homoglyph_duplicates_are_rejected`, `::test_invisible_only_nickname_is_rejected`, `::test_profile_update_applies_the_same_rules` |
| LXS-04 | P2 | Attribute injection on the host projector: JS `esc()` does not escape `"`, and nicknames are interpolated into `alt="…"` / `aria-label="…"` (`host_lobby/utils.js:50`, `host_lobby/lobby.js:54,157`); CSP allows `style` attributes → a 32-char nickname can restyle/cover the projector | Fixed server-side (`" < > \``stripped from nicknames); JS fix → LX-FE | `NicknameJoinTest::test_attribute_breaking_characters_are_stripped` |
| LXS-05 | P2 | Rate limits lock out a real class: pin+IP join bucket 150/10 min counted **every** attempt incl. reconnects; cookieless clients were keyed by IP in the "per-client" bucket (whole NAT shared 20/5 min); PIN-miss budget 100/10 min | Fixed (redesign below) | `test_lx_sec_ratelimit.py::ClassroomNatScenarioTest`, `SharedIpFairnessTest` |
| LXS-06 | P3 | PIN oracles outside the PIN-miss budget: join page (GET), join/enter (POST), wait room / player screen (404 vs 302), profile / reaction (404 vs 403); a rate-limited POST still resolved the PIN and leaked the session theme in `data-live-theme` | Fixed | `PinOracleTest` |
| LXS-07 | P2 | Nickname/avatar could be changed after the lobby (mid-game, after finish — the renamed nickname lands on the podium and the teacher's results) and in a locked lobby (bypasses host vetting); join/enter "reconnect" renamed mid-game | Fixed | `test_lx_sec_identity.py::LobbyLifecycleTest` |
| LXS-08 | P3 | Locked lobby also blocked **already admitted** players whose token cookie was lost (switching browser) | Fixed (lock applies to new players only) | `LobbyLifecycleTest::test_locked_lobby_lets_existing_player_back_in` |
| LXS-09 | P3 | A kicked player re-joined instantly with the same `live_client_id` cookie | Fixed (denylist in `host_settings["_kicked_client_ids"]`; LX-BE calls `remember_kicked_client` in `services.remove_player`) | `KickedClientTest` (incl. end-to-end via `host_remove_player`) |
| LXS-10 | P3 | `live_client_id` cookie (the key that re-issues a player token on join/enter) was not HttpOnly and not validated; a >64-char value → `varchar(64)` DataError → 500 | Fixed (HttpOnly, `[A-Za-z0-9_-]{1,64}` else re-minted) | `ClientIdCookieTest` |
| LXS-11 | P3 | Reaction fan-out: per-player limit only (3/10 s) — each reaction is pushed to every lobby socket, throw-away players multiply it; reactions accepted in any state | Fixed (session cap `LIVE_REACTION_SESSION_RATE_LIMIT`, default 60/10 s; lobby only) | `ReactionFanOutTest`, `LobbyLifecycleTest::test_reactions_only_in_lobby` |
| LXS-12 | P3 | `?ai_summary=1` is a GET with side effects (external AI call, per-user quota) — a cross-site top-level navigation could trigger it | Fixed (requires `X-Requested-With: XMLHttpRequest`, which the page's `fetch` already sends) | `AiSummaryCsrfTest` |
| LXS-13 | P4 | `_ensure_host_org_permission` consistency | Reviewed: all state-changing host endpoints and host pages enforce host + org + permission; `qr_png` is host-only and encodes only the join URL (no change); host branch of `live_state_json` (views/api.py) has no org check → LX-BE | `HostEndpointAuthorizationMatrixTest` |
| LXS-14 | P3 | Open redirect in `core.helpers._safe_same_origin_redirect_path`: `http://host//evil.com` → `//evil.com`, `http://host/\evil.com` → `/\evil.com` (protocol-relative); live results propagate `return_to` into navigation links | Fixed locally in live_exam; core fix → other owner | `ReturnToNavigationTest` |
| LXS-15 | P3 | WS: anonymous viewer with only the PIN gets the lobby roster + reactions; lobby socket is an unlimited PIN oracle (accept vs close 4401); kicked player's lobby socket stayed open | Handed to LX-BE — applied in the working tree (`allow_anonymous=False`, `player_kicked` closes the socket); PoCs XPASS | `test_lx_sec_ws.py` (xfail, strict=False) |
| LXS-16 | P2 | Typed answers on the results side: the teacher detail page, JSON and a (new) CSV export must show player text safely | Fixed: `clean_typed_answer` strips control/bidi/invisible chars, templates autoescape, CSV cells neutralised via `core.export_safety` (`= + - @ \t \r \n`) | `test_lx_sec_typed.py::ResultsExportTest` |
| LXS-17 | P3 | Typed answers on the input side: `transport.parse_answer_submission` only collapsed whitespace — NUL → 500, bidi overrides stored and echoed to the host reveal | Handed to LX-BE — applied in the working tree (`text_safety.sanitize_player_text`) | `TypedPreRevealLeakTest::test_nul_in_typed_answer_does_not_500` (xfail, strict=False) |
| LXS-18 | P3 | Pre-reveal leakage of typed text / accepted answers via HTTP (state, `/api/v1/…/state/`, answer POST, join/wait/player pages) | Verified no leak (regression tests added) | `TypedPreRevealLeakTest` |
| LXS-19 | P4 | `live_exam.view.message/game_already_started` was translated in all four languages as "this attempt was terminated and cannot be restored" | Fixed (FORCE in `scripts/i18n_fill_lxsec_2026_09_28.py`) | — |

Checked without findings: all state-changing endpoints are POST + CSRF (none is `csrf_exempt`; host
routes incl. the `live/<pin>/start|next|finish/` aliases return 405 on GET); JSON-in-HTML blocks use
`json_script` / `escapejs`; question and option texts are escaped in every JS renderer; avatar, accessory
and reaction keys are whitelisted server-side; the player token is signed (salt, 6 h), bound to
PIN + player id + client id and rejected for other sessions; per-player correctness stays hidden until
reveal (EX28-10); private settings (`typed_questions`) are stripped from player pages; there was no
CSV/XLSX export before this review (added in LXS-16). View-as: READONLY/LIMITED actors are blocked by
the middleware on every host POST; FULL-mode actors (org owner/admin, rector, İKT rəhbəri) can drive a
teacher's live session — by design, audited.

## Rate-limit design (LXS-05 / LXS-06)

| Bucket | Key | Counts | Default (env) |
|--------|-----|--------|---------------|
| PIN miss, per IP | IP | **only failed** PIN lookups, shared by `pin_entry`, join page, join/enter | `LIVE_PIN_IP_RATE_LIMIT` = 300/10m (was 100/10m) |
| PIN miss, per client | valid `live_client_id` only | failed lookups | `LIVE_EXAM_JOIN_RATE_LIMIT` = 20/5m |
| Join, per client | pin + valid `live_client_id` | every join/enter | `LIVE_EXAM_JOIN_RATE_LIMIT` = 20/5m |
| Join, per pin + IP | pin + IP | **new-player** attempts only (reconnects of admitted players are free) | `LIVE_EXAM_JOIN_IP_RATE_LIMIT` = 600/10m (was 150/10m; ≥ 3 × 150) |
| Reaction, per session | pin | every reaction | `LIVE_REACTION_SESSION_RATE_LIMIT` setting = 60/10s (module default) |

Rules: when the PIN-miss budget is exhausted the PIN is **not resolved at all** (a "found / not found"
difference would keep brute force going); a request carrying a validly signed player token for that PIN
is never subject to the miss budget (already admitted students keep working); player pages and player
POSTs check the signed token before any DB lookup, so unknown PINs answer exactly like known ones.
The 150-student same-IP scenario (typos, QR, reloads, re-joins) passes with the defaults, and a
one-IP brute force is cut after 300 misses (`test_lx_sec_ratelimit.py`).

## Residual risks

* **Insider DoS on the shared NAT**: a scripted client can burn the 300-miss budget; new joiners from that
  IP then wait ≤ 10 minutes. Admitted players are unaffected. Inherent to IP limits behind one NAT.
* **New cookie jar after a kick** = new identity; the host must lock the lobby.
* Active sessions are never auto-finished — old (incl. legacy 6-char) PINs stay resolvable.
* Nicknames and typed text reach the AI summary prompt (prompt-injection surface; output is escaped, SA-05).

## Hand-offs

* **LX-FE** — make every `esc()` also escape quotes (`host_lobby/utils.js`, `player/utils.js`,
  `wait_room*.js`, `join.js`): `.replace(/"/g, "&quot;").replace(/'/g, "&#39;")`; render typed text
  (`typed_summary`, `your_text`, results page) with `textContent` / escaped markup only. Optional: link the
  CSV export (`liveExam:teacher_live_session_export`) from `teacher_live_session_detail.html` and render
  `question_stats[i].typed_answers` (`{text, count, correct}`).
* **LX-BE** — `consumers.py`: lobby socket for host/players only (`allow_anonymous=False`) and close a
  kicked player's sockets; `transport.parse_answer_submission`: typed text through `text_safety`
  (all three already applied in the working tree — once settled, drop the `xfail` markers in
  `test_lx_sec_ws.py` / `test_lx_sec_typed.py` and update `test_consumers.py` tests that still expect
  anonymous lobby viewers). Still open: `views/api.py` — apply `_ensure_host_org_permission` to the host
  branch of `live_state_json` (P4).
* **Core owner** — `core/helpers.py::_safe_same_origin_redirect_path`: reject parsed paths starting with
  `//` or `/\`.
