# QA-1 — Teacher and student functional QA (2026-10-17)

Scope: teacher and student cabinet, electronic journal, profile-completion gate, password change, starosta section, mobile 375 px, console/CSP, translations (az/en/ru/de), "EMS Arena" text, native selects.
Environment: local QA clone only (DB `emsarena_rehearsal_a0d170000901` @ 127.0.0.1:55433, code at `Develop` / 9ea233634). Own server on :8031 with private hosts `qa1.localhost` (student session) and `qa1t.localhost` (teacher session) so cookies did not collide with other agents; stopped at the end. No qa.* password was changed. Production was not touched. No repo code was modified or committed.

Evidence folder: `/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/qa/` (screenshots `*.jpg`, helper scripts `s*.py` for the test-client checks).

## Summary

| Severity | Count |
|---|---|
| P0 | 0 |
| P1 | 0 |
| P2 | 6 |
| P3 | 12 |

No blocking defect found in the new features. Journal lesson/room auto-fill, i/e and q/b autosave, minute-based edit windows, late-entry days, workload grouping, syllabus (1 outcome), profile gate, password policy, starosta section and student exemption view all behave as specified. The P2 items are an exam-access hole in the profile gate, three untranslated areas, a missing search in the room picker, and the exempt-student UX.

## Clone data / test-fixture changes I made (so others are not surprised)

- Applied nothing to the schema (another agent had already applied `accounts.0031_profile_completed_at`; before that, login on the clone returned 500 `column accounts_userprofile.profile_completed_at does not exist`, a known "clone needs migrate" situation).
- `qa.teacher`: added 2 `ScheduleSlot`s (Saturday 08:30–10:00 lecture room 103 for Veb texnologiyalar; Saturday 10:10–11:40 seminar room 104 for Proqramlaşdırmanın əsasları); 2 new `TeachingTaskRow`s under the distributed task of the "Proqramlaşdırma və informasiya təhlükəsizliyi" chair with `TeacherAssignment`s for qa.teacher (105 h total); a draft syllabus for Veb texnologiyalar with 1 learning outcome (`QA1 sinaq: ...`).
- `qa.chair_head`: one extra row + 15 h lecture assignment (to check the "Redaktə et" link).
- New obvious test student `zz.qa1.gate` (own password, not a qa.* account) in group 235 KE ing, enrolled in Veb texnologiyalar, later also given a `lead_student` membership on the group (to test the starosta section), and exempted from Veb texnologiyalar through `qa.ikt_rehber` (test client). Its profile fields were filled via the gate page.
- Other agents also exempted two real-name students from the same Veb journal (visible in `JournalHygieneDecision`); the teacher's student count fell 32 -> 30 for that reason, not because of my actions (my own exemption: `zz.qa1.gate` only).
- My test lessons (Veb 17.10 with room 104 and q/b marks, plus Proqramlaşdırma probes) were deleted at the end. Note: one of my cleanup commands removed my own Veb lesson (`topic startswith 'QA1'`) — this is why the Veb journal has no lesson for 17.10 any more; not a product bug.

## Findings

### F1 (P2) Profile-completion gate still blocks the student exam list (`/exams/`, `/exams/available/`, `/exams/assigned/`)
- Page: `/exams/`, `/exams/available/`, `/exams/assigned/` as a student whose FIN/phone/e-mail are empty.
- Repro: log in as a non-`qa.*` student with empty FIN/phone/e-mail (qa.* accounts are exempt, I used `zz.qa1.gate` before filling the fields). Open `/exams/available/`.
- Expected (commit 6ecd548d2 "profil tamamlama qapısı imtahan yollarını (/exams/) dayandırmır"): the exam list is reachable.
- Actual: the middleware lets `/exams/…` through, but those views redirect to `/accounts/profile/?section=assigned-exams` (or `section=my-exams`), which is gated, so the final page is `/accounts/complete-profile/?next=%2Faccounts%2Fprofile%2F%3Fsection%3Dassigned-exams`. Only deep exam URLs (attempt/start/final waiting) and `/live/` stay open; `/exams/my-history/` also loads.
- Evidence (in-page fetch with redirect following):
  `/exams/ -> 200 final=/accounts/complete-profile/?next=%2Faccounts%2Fprofile%2F%3Fsection%3Dmy-exams`
  `/exams/available/ -> final=/accounts/complete-profile/?next=...section%3Dassigned-exams`
  `/exams/my-history/ -> final=/exams/my-history/` (not gated).
- Likely file: `apps/accounts/middleware_profile_completion.py` (`EXAM_PREFIXES`, `_is_exempt_path`) together with the redirect in `apps/exams/views` (student_exam_list) into the cabinet section; exempting only the prefix is not enough while the exam list is a cabinet section.

### F2 (P2) "Statistika" page is not translated in en/ru/de (teacher and student)
- Page: `/accounts/profile/?section=statistics`, both roles, UI language en/ru/de.
- Repro: switch language to English, open Statistics.
- Expected: English/Russian/German texts.
- Actual (en): "Başlanğıc tarixi", "Son tarix", "Fənn açılışı", "Bağlı jurnal", "cari dövrün açılışları üzrə", "Davamiyyət", "92 davamiyyət qeydi", "Yoxlama növbəsi", "imtahan 0 · tapşırıq 0", "İmtahanlarım", "aktiv 1 · planlaşdırılıb 0", "Fənlərim (cari dövr)", "İmtahan həyat dövrü", "Qaralama/Planlaşdırılıb/Aktiv/Bitib"; student: "Toplanmış kredit", "proqram tələbi: 240 ECTS", "Semestr üzrə nəticə", "Orta yekun bal (0–100) və keçid…", "Son imtahan nəticələri", "Yekunlaşmış imtahan cəhdi yoxdur." Same in ru and de.
- Cause: all these strings use `pgettext("profile.statistics", …)`; `msgctxt "profile.statistics"` has no entries in `locale/{en,ru,de}/LC_MESSAGES/django.po` (other contexts such as `registrar.records` do exist for the same msgids).
- Likely file: `apps/accounts/services/statistics_metrics/presenter.py`, `presenter_org.py`, `filters.py` + the .po files (an i18n fill script is missing).

### F3 (P2) "Mənim dərs yüküm": activity, study form, level and hour labels frozen in Azerbaijani
- Page: `/accounts/profile/?section=my-workload`, language en/ru/de.
- Repro: language English -> open "My teaching load" as qa.teacher (needs approved assignments).
- Expected: "Lecture 15 · Seminar 30", "Full-time", "Bachelor", "15 h".
- Actual: table rows show "Mühazirə 15 · Seminar/təcrübi 30", "Əyani", "Bakalavr"; the objection dialog options show "Proqramlaşdırmanın əsasları · Mühazirə · 15 saat" (same in ru, de). The season filter ("Fall/Spring/Summer") and headings are translated.
- Cause: module-level dicts evaluated at import time with `str()` freeze the language: `_ACTIVITY_LABELS`/`_SEASON_LABELS` in `apps/workload/services/queries.py` (lines 19-20) and `_FORM_LABELS`/`_LEVEL_LABELS`/`_ACTIVITY_ORDER` in `apps/workload/services/my_workload_lines.py` (lines 20-22). They must be evaluated per request (or kept lazy).
- Evidence: scratchpad `my_workload_grouped_lines.jpg` (az layout), text dump in session; en lines quoted above.

### F4 (P2) Student "Fənlərim" status legend and "Gözləmədə olan cavablar" statuses untranslated in en/ru/de
- Page: `?section=my-subjects`, `?section=pending-answers`.
- Actual (en/ru/de): legend still reads "İmtahana buraxılır", "Limitə yaxın — buraxılır", "İmtahana buraxılmır", "Köhnə sistemdən" (their descriptions are translated); pending answers shows "Gözləmədə", "Yoxlanır".
- Likely file: `apps/registrar/templates/registrar/partials/_journal_student_content.html` / `_academic_records.html` (msgctxt `registrar.journal`) — msgids without msgstr for the new status badge names.

### F5 (P2) Lesson-modal room picker has no in-menu search (owner rule: long lists need search)
- Page: teacher journal -> «Yeni dərs» -> Korpus/Otaq.
- Repro: open the modal; open the "Otaq" dropdown (44 rooms in building 1, 159 in total) or "Korpus".
- Expected: a sticky search field in the menu (project select component, `data-live-search="true"`).
- Actual: plain scrolling list, `lesson_room`/`lesson_building`/`lesson_time` have `data-live-search=null`. Also two different rooms are both labelled "102" in building 1 (ids 33 and 48), indistinguishable.
- Evidence: `lesson_modal_room_dropdown_no_search.jpg`.
- Likely file: `apps/registrar/templates/registrar/partials/_jd_lesson_modal.html` (lines ~146-160); label building in `apps/registrar/lesson_rooms.py::lesson_room_choices`.

### F6 (P2) Subject-exempt student: group timetable and "next lesson" still show the exempted subject; empty-states are misleading
- Pages: student `?section=dashboard`, `?section=my-schedule`, `?section=my-subjects`, `?section=my-journal`.
- Repro: exempt a student from a subject through `/jurnal/<id>/fenden-azad/` (qa.ikt_rehber has the power), log in as that student.
- Expected: «Azad edildiyiniz fənlər» lists it (works: "Veb texnologiyalar · Azad edilib", with the correct explanation); other places should not present the subject as the student's own.
- Actual: dashboard "Növbəti dərs günü · Şənbə 24.10 08:30–10:00 Veb texnologiyalar · aud. 103" and the timetable still show it; «Fənlərim» empty-state says "Bu semestr üçün hələ fənn qeydiyyatı yoxdur. Qeydiyyat semestr açılışında dekanlıq tərəfindən aparılır…" and «Elektron jurnal» says "Bu semestr üçün fənn qeydiyyatı tapılmadı." although the student is only exempt, not unregistered. Teacher side is correct (student leaves the grid; 403 for plain teacher).
- May be a conscious choice (group timetable), flag for the owner.

### F7 (P3) Journal change-history shows raw audit codes "iə"/"qb" and mixed-language lesson labels
- Page: journal -> «Tarixçə».
- Actual: values read "— → iə" and "— → qb" while the grid uses "i/e" and "q/b"; in English UI the newest row says "Lecture" but older rows keep stored Azerbaijani "Mühazirə".
- Evidence: `journal_history_codes_ie_qb.jpg`; JSON `/jurnal/<id>/tarixce/` returns `"new":"iə"`, `"qb"`.
- Likely file: `apps/registrar/grade_audit.py:207-211` (`att = "qb"/"iə"`), `corrections.py:41-42`, `correction_reversals.py:29` (labels hard-coded).

### F8 (P3) English wording in «Keçirilmiş dərslər»
- Page: `?section=lessons-log` in en: "1 lesson · 2 hour", "3 lesson · 6 hour" (no plural), semester filter says "Autumn / Spring / Summer" while elsewhere (workload, filters) it is "Fall".

### F9 (P3) Mobile 375 px: the cabinet drawer flashes open on every page load
- Pages: student cabinet (dashboard, my-subjects, my-schedule, my-group), reproduced on 3 pages; screenshot right after navigation shows the sidebar drawer covering the content, 2 s later it is closed (`aside.profile-sidebar.collapsed`).
- Evidence: `mobile_drawer_flash_my_subjects.jpg`, `mobile_drawer_flash_schedule.jpg`.
- Likely cause: drawer is rendered open and collapsed by JS after load (or transition from open to closed). No horizontal overflow on any checked page (see "tested OK").

### F10 (P3) Mobile: the "AI Assistant" tooltip bubble covers page content on first load
- Pages: journal list, teacher/student cabinet at 375 px (bubble above the floating button, covers a group card/row until its ✕ is pressed). `mobile_journal_list.jpg`.

### F11 (P3) Student journal headline score is rounded while the breakdown shows the exact value
- Page: `?section=my-journal` (subject view). "İMTAHANA QƏDƏR BAL 10 / 50" while the breakdown reads "Davamiyyət: 9,55/10 · Aktivlik 0/10 · Midterm 0/30" (card "Giriş balı: 10/50", dashboard "Cari ballar 10"). Sum 9.55, shown 10.

### F12 (P3) Password policy gaps (simple policy, commit c55973474)
- Page: `?section=change-password`.
- Accepted: "aaaaaaaa", "kitabdan", "12345678a", passwords with spaces ("ab cd efg"). Rejected: "12345678", "11111111", "password", "qwertyui", "Parol123", "abcd1234", username as password. Setting the new password equal to the current one returns "Şifrə uğurla yeniləndi."
- Expected per page text ("çox asan parol … olmasın"): consistent rejection of "aaaaaaaa"; probably reject same-as-current. Low impact, owner decision.

### F13 (P3) Future-dated lessons accepted and shown as "✓ keçirilib"
- Page: journal «Yeni dərs»; test-client POST `action=add_lesson` with `lesson_date=2026-10-20` (today is 17.10) by qa.teacher -> "Dərs əlavə edildi."; calendar plan lists it with the badge "✓ keçirilib" three days before it happens. The semester end (31.01.2027) is enforced ("Dərs tarixi dövrün sonundan … sonra ola bilməz"), "Keçirilmiş X/105 saat" did not count it, "qalan" did.
- Probably intended planning; the "keçirilib" (held) badge for a future date is misleading.

### F14 (P3) Journal banners
- "Bu fənn üzrə sillabus yazılmayıb — Dərslər başlayıb, amma …" appears on a journal with 0 lessons and, with a «Sillabus yarat» button, on a closed/finalised journal (`ac769e6f…`/`75f25e7d…`).
- Correction contact differs: closed journal says "RİM-ə (sənədli düzəliş)", open journal footer says "Tyutor xidmətinə yazılı müraciət".

### F15 (P3) Import placeholders show in journals and starosta lists
- Patronymic "-" renders as "Saılov Akhlıman -", "Əhmədov Said -" (journal rows, Midterm tab). Data quality in the clone import, not code.

### F16 (P3) Starosta «Qrup yoldaşları» shows classmates' student numbers
- `?section=my-group` -> tab «Qrup yoldaşları 32» lists "Aysu Axundova 8914 …". Names are fine; the student number is shown to a peer — owner to confirm this is intended (commit a96ca0c3d tightened photo privacy only).

### F17 (P3) Environment: Microsoft Clarity runs on the dev clone
- Cookies `_clck`/`_clsk` and `i.clarity.ms/collect` were present on `qa1.localhost`/`qa1t.localhost` — session recording from a clone that holds real student names. `templates/partials/_microsoft_clarity.html` is controlled by `microsoft_clarity_enabled` (`.env`). Also every page carries `<meta name="robots" content="index, follow">` and a `canonical`/`og:url` on a `*.ngrok-free.dev` host from `SITE_URL` (also on authenticated pages like `/jurnal/<id>/`).

### F18 (P3) Misc
- `next=/accounts/complete-profile/` after a valid submission redirects back to the gate URL (harmless loop target; open redirect attempts `https://evil.example/x`, `//evil.example/x`, `javascript:alert(1)` all fall back to `/accounts/profile/` — OK).
- Turkish duration label inconsistency: "2 sa." vs "2 saat 30 dakika" (`pgettext('registrar.journal_timing', '%(n)s saat')`).

## Tested and found OK

Teacher
- Mənim dərs yüküm: lines grouped per subject+group ("Mühazirə 15 · Seminar/təcrübi 30", hours = sum, 105 h total, 21 % fill); no «Redaktə et» for plain teacher; present for `qa.chair_head` (test client: `'Redaktə et' in html` True/False). Excel/objection buttons render. Mobile: table in a scroll container (643 > 341), no page overflow.
- Journal list: next lesson from the timetable ("Şənbə, 24.10 08:30–10:00 · Mühazirə · 103"), kind pills, counts.
- «Yeni dərs»: with a timetable slot the form is pre-filled (time 08:30–10:00, kind locked "Mühazirə", building 1, room 103; banner + "Otaq dərs cədvəlindən götürülüb — dəyişə bilərsiniz."); room changed to 104 shows "Cədvəldəki otaq: 103 ↺"; lesson saved with room 104; empty room POST falls back to the slot room (104 in a second test); student cabinet shows "104 (1)".
- Marking: q/b chosen from the custom dropdown, counter `0 -> 1 q/b`, DB row `absent`; header "i/e" bulk fills only empty cells (the q/b row kept); data persisted after reload; "Dəyişikliklər avtomatik yadda saxlanılır" plus explicit «Yadda saxla».
- Edit-window messages in minutes: `duration_text` gives "45 dəqiqə", "90 dəqiqə", "2 saat", "2 saat 30 dəqiqə" in az/en/ru/de (tr noted above); page footers and modal note render the configured window (tested with patched runtime overrides: mark 30 -> "45 dəqiqə", mark 150 -> "2 saat 30 dəqiqə").
- Late-entry days (patched `journal.late_entry_days=2`): modal date `min=2026-10-15`, text "Keçmiş tarixə dərs ən çox 2 gün geriyə açmaq olar", lesson on 16.10 accepted and a new q/b on it accepted; 10.10 rejected with "…ən erkən 15.10.2026…"; with default 0 the same new mark returns "Yeni qeyd yalnız dərsin öz günündə yazılır — keçmiş dərsə yazmaq olmaz." and a past date returns "Keçmiş tarixə dərs əlavə etmək olmaz."
- «Fəndən azad et» is not in the teacher DOM, direct POST `/jurnal/<id>/fenden-azad/` returns 403 `permission_denied`.
- Schedule view shows the seeded Saturday slots (room 103/104, kind colours, upper/lower week toggle); mobile uses a scroll container.
- Syllabus editor: new draft created; "Ən azı 1 təlim nəticəsi tələb olunur (hazırda 0)" turns into a ✓ after one outcome, deleting the last outcome gives the toast "Ən azı 1 təlim nəticəsi tələb olunur — silinmə mümkün deyil." (EN: "At least 1 learning outcome is required — deletion is not possible.").
- Exams list (4 exams, 1 active, 3 drafts) counts and filters consistent; Midterm/Final tabs load, no native selects.
- Exports: journal xlsx, syllabus pdf/json 200.

Student
- Cabinet pages (21 sections) all HTTP 200 in az/en/ru/de for the student role; 22 for the starosta.
- Profile gate (non-qa test student): redirected to `/accounts/complete-profile/?next=…` with explanations ("Nəyə lazımdır: …"), 7-char FIN auto-upper-cased, server validation messages for empty / bad FIN / bad phone / bad e-mail / placeholder e-mail (all translated in az/en/ru/de/tr); phone normalised to `+994…`; success -> cabinet with a toast; XHR gets 403 JSON `profile_completion_required`; open-redirect safe; `/live/` and deep `/exams/…` not gated (see F1 for the list pages). `qa.*` accounts are exempt by design, so the gate cannot be tested with them.
- Journal: today's q/b was visible immediately in the student journal ("Qayıb 2 saat", row "17.10 ÜST Mühazirə … 104 (1) q/b").
- «Fənlərim» / «Azad edildiyiniz fənlər»: after exemption the section lists "Veb texnologiyalar · Azad edilib" with the explanation ("jurnal, davamiyyət və imtahan tələbi sizə aid deyil; qrupunuz dəyişmir"), teacher grid drops the student.
- Password change: 8 chars minimum, no composition rule, banned short list works, mismatch and wrong-old-password messages correct (see F12 for gaps).
- Starosta: appears only for an active enrolled student with a `lead_student` membership on the group (`qa.lead_student` has no academic record so no section — fail-closed as documented); panel shows subjects (2), elective, merged lessons, timetable, exams, announcements, classmates (32), own attendance; no classmates' scores.

Cross-cutting
- Mobile 375 px: no horizontal page overflow on student dashboard, my-subjects, my-schedule, my-journal, my-group; teacher journal list, journal detail, modal (bottom sheet, buttons visible), my-workload, my-schedule, syllabus editor. Wide tables sit in scroll containers.
- Console: no CSP script/style errors on the visited pages (only my own probes: 403/404/405/500 fetches, and `frame-ancestors 'none'` from my iframe attempt). `scripts/check_inline_assets.py` passes (exit 0).
- "EMS Arena" user-visible text: none in the HTML of 23 teacher + 22 student pages × 5 languages, journal exports, locale catalogs (0 hits in all .po). Only code comments/SVG comment contain it.
- Native selects: none visible on teacher (journal incl. modal/tabs, lessons-log, syllabus, exams, notifications, applications, edit-profile) and student pages (results, overall-academic, calendar, assigned exams, applications, edit-profile, statistics). Project select component used; only F5 (no search).
- Translations: profile gate, journal detail, lesson modal, syllabus editor translated in en/ru/de; remaining gaps are F2, F3, F4, F8 and stored notification texts (written in az at creation, e.g. "Jurnal bağlandı: Payız (Bütün təşkilat)").

## Not tested / limits
- Real exam taking, appeals, surveys, announcements, notifications flows (other agents' lanes).
- "Yükü təsdiqlə" / "Etiraz bildir" actions on the workload page (buttons render only).
- Clone limitation: the QA accounts have no workload/timetable by default; I seeded them as listed above. `qa.student` has no academic record, so student-journal checks were done with `zz.qa1.gate`.
- Real-device mobile (only emulation 375x812 with Pixel UA).
