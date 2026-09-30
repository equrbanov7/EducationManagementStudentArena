# Responsive QA — whole site (RESP, 2026-09-30)

**Method:**
- Playwright (headless Chromium) against the QA clone at http://127.0.0.1:8012.
- Every URL checked at 320/360/390/768/1024/1440.
- Measured in code: elements past the right edge that are not inside a scroll box; page-level sideways scroll (`.profile-main` scrollWidth > clientWidth); text clipped inside `overflow:hidden` boxes or spilling out of its box.
- Extra checks: 142 modals opened at 360px (0 problems); AI button vs bottom-bar overlap (RİM, 189 URLs); take-exam rendered in the sandbox DB (0 problems).
- Coverage: student 55 URLs, teacher 58, chair head 78, dean 86, programme coordinator 59, exam-centre head 90, RİM head 186, rector 147, teaching office head 56, student services 52, anonymous 27 — 5,508 measurements in total.

| # | Page | Width | Problem | Fix | Status |
|---|---|---|---|---|---|
| 1 | Edit profile (all roles) | 320–390 | Save bar offset 80px; text clipped; 3-row, 200px bar; AI button over "Save" | Mobile save bar full width, one row of buttons, icon-only preview ≤420px, AI button lifted | ✅ |
| 2 | /jurnal/ | 320 | Lesson-type pills clipped | Pills wrap | ✅ |
| 3–4 | Question bank | 320–390 | Filter column 370px (`1fr`); image options squeeze text to 22px | `minmax(0,1fr)`; option image wraps to next line | ✅ |
| 5 | Teacher attempt view | 320–390 | Appeal badge overflows; question header breaks per word | Badge wraps; header re-laid out | ✅ |
| 6 | My exams | 320 | KPI label overflows its card | Tighter spacing ≤359px | ✅ |
| 7 | Exam languages | 320–390 | Action column hidden | Table scrolls inside its panel | ✅ |
| 8 | Question submission pages | 320 | No-wrap badge overflows | Badge wraps | ✅ |
| 9 | Exam results | 320 | "(@username)" clipped | Teacher line wraps | ✅ |
| 10 | Syllabus list | 320–390 | Sort + view toggle row causes 395px sideways scroll | Row wraps on mobile | ✅ |
| 11 | Shared filter bar (8+ sections) | 320–768 | Sideways scroll 393–431px; 200–320px-tall fields | Single-column grid ≤768px | ✅ |
| 12 | My results / assigned tasks | 320 | 303px cards | `minmax(0,1fr)`, title ellipsis | ✅ |
| 13 | Notifications (type filter on) | 320–360 | "Mark all as read" off-screen | Toolbar wraps | ✅ |
| 14 | Schedule manager | 320 | Action row 346px | Row wraps | ✅ |
| 15 | Analytics (exam-centre head, teaching office head) | 320–390 | No `journal.css`, table 531px | `journal.css` loaded for these roles | ✅ |
| 16 | Exam score entry meta | 320 | 9rem+9rem pair = 333px | Pair columns shrink | ✅ |
| 17 | Journal close | 320–390 | Reopen form 392px | Input full width, button below | ✅ |
| 18 | RİM centre | 320–390 | 5 status tabs 401px | Tabs wrap | ✅ |
| 19 | Statistics (rector) | 320–768 | Section 902px | `minmax(0,1fr)` | ✅ |
| 20 | Category management (rector) | 320–360 | Cards 327px | `minmax(0,1fr)`, toggle wraps | ✅ |
| 21 | /organizations/‹slug›/roles/ | 320–390 | Shared UI assets missing, table 481px | Assets included | ✅ |
| 22 | Error pages | all | Decorative circle covers caption | Caption panel raised above it | ✅ |
| 23 | /technology/ | 320 | Category name hits its count | Name wraps | ✅ |
| 24 | Global long words | 320–390 | Long words overflow | `overflow-wrap: break-word` on body | ✅ |
| 25 | Sticky header | all | Header never sticks (`body { overflow-x: hidden }`) | `clip` was tried, then **reverted** by the orchestrator — see below | ⏸ |
| 26 | Take-exam / coding top bar | — | Only needed because of #25 | Reverted together with #25 | ⏸ |
| 27 | Surveys inbox / builder | — | 500 on clone (migration 0005 was missing) | Clone migrated; checked in the separate QA pass | ➜ |
| 28 | /technology/ links | — | 404 | Content issue | ⚠️ |

## Why #25/#26 were reverted

`body { overflow-x: clip }` makes the header sticky, but it also activates every page-level
`position: sticky` rule that has silently never worked (the exam top bar and question sidebar,
the final-exam monitor violations panel `top: 12px`, syllabus steps, workload aside, survey
progress bar …). Several of them use `top: 0–16px` and would slide under the 72px sticky header
(z-index 100); on non-final exams the timer bar would be covered. Production has always run
without a sticky header, so the conservative choice is to keep `hidden` and do the sticky header
as a separate change with a page-by-page pass over those rules.

## Lessons for future code

- Use `minmax(0,1fr)` rather than `1fr` for a single grid column; `1fr` grows to the content's minimum width.
- Don't use `flex-wrap: wrap` on a column flex container; each line takes the widest item's full content width.
- A grid with no `grid-template-columns` still has an implicit `auto` column that grows the same way.
- Any page that reuses a cabinet partial must also load that partial's assets (shared UI assets, `journal.css`).
- The CSP blocks `<style>` injected from the console; test CSS changes with `el.style` instead.
