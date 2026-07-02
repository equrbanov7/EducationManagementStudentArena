# UI rəng token-ları — miqrasiya bələdçisi

## İCRA STATUSU (2026-07-01)

- ✅ `static/css/design-tokens.css` yaradıldı və **hər yerdə** yükləndi
  (base.html + base_auth.html + 6 standalone live_exam template).
- ✅ **623 hardcoded hex → token** miqrasiya edildi (17 böyük CSS faylı,
  behavior-neutral — eyni dəyər). Fayllar: host_lobby, player, wait_room, join,
  host_lobby_shell, test_question_bank, coding_exam, take_exam, teacher_questions_bank,
  teacher_exam_detail, exam_result, teacher_check_attempt, appeals, register, navbar,
  ai_assistant, blog/profile.
- ✅ **2026-07-02 (Faza 6.1-6.2, audit icra planı):** qalan BÜTÜN uyğun CSS
  faylları miqrasiya edildi — **+2723 hex → var(--ems-*)** (155 fayl, skript:
  sərhəd-təhlükəsiz regex, `url(` sətirlərinə toxunulmur). design-tokens.css-ə
  yeni token ailələri əlavə olundu: `--ems-gray-200/500` (legacy gray),
  `--ems-warning-100/500/600/800` (amber), `--ems-danger-100/200/500`,
  `--ems-success-100/600`. ✅ HƏLL OLUNDU (eyni gün): `errors/*.html` (5)
  + `admin/verify_otp.html` şablonlarına design-tokens linki əlavə edildi və
  `error-pages.css` (+19) / `admin_otp.css` (+2) də miqrasiya olundu — artıq
  İSTİSNA YOXDUR.
- ⬜ Qalan iş: `url()`-daxili/istisna fayllardakı ~18 map-lənmiş hex + aşağı
  tezlikli legacy hex-lər (#eee/#333/#555...) — semantik qərar tələb edir.


## Problem

Layihədə **881 CSS custom-property** təyin olunub, amma brend rəngləri hələ də
fayllar boyu **hardcode** edilir (vahid mənbə yoxdur):

| Rəng | İstifadə sayı | Məna |
|------|---------------|------|
| `#ffffff` / `#fff` | ~718 | ağ (fon/mətn) |
| `#2563eb` | 269 | əsas brend mavisi |
| `#1d4ed8` | 139 | mavi (hover) |
| `#64748b` | 135 | boz mətn |
| `#f8fafc` | 123 | subtle fon |
| `#e2e8f0` | 112 | border |
| `#0f172a` | 94 | tünd mətn |
| `#dc2626` | 76 | danger |
| `#10b981` | 59 | success |

Nəticə: rebrand / dark-mode / kontrast düzəlişi **269+ yerdə əl ilə** dəyişməyi
tələb edir; rənglər faylar arası **fərqlənə bilir** (uyğunsuz UI).

## Həll

`static/css/design-tokens.css` — mövcud de-fakto palitranı vahid `var(--ems-*)`
token-larına çevirir (vizual dəyişiklik YOXDUR — eyni hex dəyərləri). Bu fayl
base template-də (bütün digər CSS-lərdən ƏVVƏL) yüklənməlidir:

```html
<link rel="stylesheet" href="{% static 'css/design-tokens.css' %}">
```

## Miqrasiya (tədricən, təhlükəsiz — hər PR bir neçə fayl)

1. Yeni/redaktə olunan CSS-də hex ƏVƏZİNƏ token işlət:
   ```css
   /* əvvəl */  color: #2563eb;
   /* sonra */  color: var(--ems-primary-600);
   ```
2. Mövcud faylları böyükdən-kiçiyə miqrasiya et (host_lobby.css 3606, player.css
   1576, ...). Hər fayl üçün: hex → token sed-əvəzləməsi + vizual smoke.
3. **Təhlükəsizlik:** əvəzləmə eyni-rəng (behavior-neutral) olmalıdır; token
   dəyəri hex ilə eyni. Yalnız adlandırma dəyişir.

## Tövsiyə olunan avtomatlaşdırma

Hər böyük CSS üçün:
```
sed -i 's/#2563eb/var(--ems-primary-600)/gI; s/#1d4ed8/var(--ems-primary-700)/gI; ...' fayl.css
```
Sonra brauzer/regress smoke. **Kütləvi avtomatik əvəzləmə nəzarətsiz
edilməməlidir** — hər fayl ayrıca yoxlanmalıdır (bəzi hex-lər gradient/rgba
kontekstində fərqli davrana bilər).


## İnline style → klass miqrasiyası (Faza 6.4, 2026-07-02)

**İnventar:** cəmi 501 `style=""` atributu, bunun **165-i email şablonlarındadır
və QANUNİDİR** (email klientləri xarici/embedded CSS-i dəstəkləmir — inline
industry-standarddır; bu fayllar hədəfdən ÇIXARILIB). **Browser hədəfi: 336.**

**Qaydalar:**
1. Email şablonlarına (`*email*/`, `*mail*`) toxunulmur.
2. Dinamik dəyərlər (`style="width:{{ x }}%"`) inline qalır — bu, düzgün pattern-dir.
3. `style="display:none"` JS-toggle ilə işləyirsə klassa keçid JS-lə birgə edilməlidir
   (kor-koranə `hidden` atributuna keçmək `el.style.display=""` açılışını sındırar).
4. Statik dekorativ atributlar səhifənin ÖZ CSS faylına semantik klass kimi köçür,
   rənglər `var(--ems-*)` tokenləri ilə.

**Sprint-1 ✅:** `teacher_live_session_detail.html` — 22 atributdan 20-si klassa
(`sd-ai-panel`, `sd-charts-grid`, `sd-num--correct/incorrect/muted`,
`sd-bar__text--green/blue/red`, `sd-col-*` və s.), 2 dinamik width inline (düzgün).

**Sprint-2 ✅ (eyni gün):** `teacher_exam_statistics.html` (17 konversiya, 2 dinamik
width inline), `_create_exam_modal_form.html` (14 konversiya + dublikat-class
düzəlişi; 3 JS-toggled display inline), `exam_live_monitor.html` (11 konversiya;
4 JS-toggled display inline). Cəmi Sprint-1+2: **62 atribut → klass**, browser
pool-u 336 → ~274.

**Sprint-3 ✅ (eyni gün):** `assignments/detail.html` (15 + öz nonce-style
blokuna klasslar; pre-mövcud boş atribut cruft-u da təmizləndi),
`teacher_check_attempt.html` (9; 2 JS-toggled qaldı), `labs/lab_detail.html`
(9; JS-driven progress width qaldı), `_teacher_live_session_detail_js.html`
(10 — JS innerHTML şablonlarındakı inline stillər `sd-ai-*`/`sd-md-*`
klasslarına). **Cəmi Sprint-1+2+3: 105 konversiya**, browser pool ~336 → ~231.

**Növbəti hədəflər (browser, çoxdan-aza):** `_take_exam_scripts` ailəsindən sonra
qalan orta-ölçülülər — `teacher_check_attempt`, `exam_result`, profil bölmələri;
hər sprintdə eyni 4 qayda tətbiq olunur.

## YEKUN QALIQ İNVENTARI (Faza 6.4 bağlanışı — 2026-07-02)

4 sprint nəticəsi: **154 atribut klassa köçürüldü** (105 + Sprint-4: 49).
Qalıq bölgüsü:

- **167** — EMAIL (qanuni)
- **119** — MİKRO-STATİK (opsional gələcək iş)
- **39** — JS-TOGGLE display (qanuni — qayda 3)
- **21** — DİNAMİK (qanuni — şablon dəyəri)

**Arxitektur qeyd (CSP):** `style-src-attr 'unsafe-inline'` DİNAMİK və JS-TOGGLE
kateqoriyaları mövcud olduqca qalmalıdır — bunlar dizayn etibarilə inline-dır.
Gələcəkdə tam bağlamaq üçün yol: JS-lərin `el.style.x=` (CSSOM — CSP-yə düşmür)
istifadəsinə keçməsi + dinamik dəyərlərin CSS custom-property ilə ötürülməsi.

**MİKRO-STATİK siyahı (119 ədəd — hamısı 1-4 atributluq xırda fayllar):**

| Fayl | Sətir | Dəyər |
|---|---:|---|
| apps/accounts/templates/accounts/assigned_courses.html | 13 | `max-width: 1000px; margin: 0 auto;` |
| apps/accounts/templates/accounts/assigned_exams.html | 13 | `max-width: 1000px; margin: 0 auto;` |
| apps/accounts/templates/accounts/assigned_exams.html | 96 | `margin-top:.4rem;color:#b91c1c;font-size:.84rem;font-weight:` |
| apps/accounts/templates/accounts/grading_queue.html | 159 | `align-self: center;` |
| apps/accounts/templates/accounts/grading_queue.html | 209 | `white-space: pre-wrap; font-family: inherit;` |
| apps/accounts/templates/accounts/my_result_detail.html | 17 | `max-width: 900px; margin: 0 auto;` |
| apps/accounts/templates/accounts/partials/_pending_review_content.html | 94 | `background:#fceaea;color:#a32d2d;border:1px solid #e24b4a;` |
| apps/accounts/templates/accounts/partials/_student_org_request_content.html | 114 | `max-width: 240px;` |
| apps/accounts/templates/accounts/partials/_student_org_request_content.html | 173 | `width: 48px;` |
| apps/accounts/templates/accounts/partials/staff_management/_staff_tabs.html | 263 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/staff_management/_staff_tabs.html | 395 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/staff_management/_students_invites.html | 77 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/staff_management/_students_pending.html | 86 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/staff_management/_students_unassigned.html | 74 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/staff_management/_teacher_tabs.html | 261 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/staff_management/_teacher_tabs.html | 391 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/student_org_management/_pending.html | 71 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/student_org_management/_students.html | 134 | `width: 44px;` |
| apps/accounts/templates/accounts/partials/student_org_management/_unassigned.html | 74 | `width: 44px;` |
| apps/accounts/templates/accounts/profile/_messages.html | 3 | `font-size:1.1rem;margin-top:0.1rem;flex-shrink:0;color:#d977` |
| apps/accounts/templates/accounts/profile/_sidebar.html | 178 | `color:#dc3545;` |
| apps/accounts/templates/accounts/profile/_sidebar.html | 491 | `margin:0;padding:0` |
| apps/accounts/templates/accounts/profile/sections/_delete_account.html | 19 | `border-bottom-color: var(--danger-color, #dc3545);` |
| apps/accounts/templates/accounts/profile/sections/_delete_account.html | 20 | `color: var(--danger-color, #dc3545);` |
| apps/accounts/templates/accounts/profile/sections/_edit_profile.html | 95 | `border-radius: 8px;` |
| apps/accounts/templates/accounts/profile/sections/_statistics.html | 189 | `max-width:200px;` |
| apps/accounts/templates/accounts/profile/sections/_statistics.html | 236 | `max-width:200px;` |
| apps/accounts/templates/accounts/profile/sections/_statistics.html | 277 | `max-width:200px;` |
| apps/accounts/templates/accounts/profile/sections/_statistics.html | 324 | `max-width:200px;` |
| apps/accounts/templates/accounts/profile/sections/_statistics.html | 367 | `max-width:220px;` |
| apps/assignments/templates/assignments/assignment_detail.html | 117 | `max-width: 200px;` |
| apps/assignments/templates/assignments/assignment_section.html | 6 | `color: #ff9800;` |
| apps/assignments/templates/assignments/assignment_section.html | 89 | `font-size: 2rem; color: #ccc;` |
| apps/assignments/templates/assignments/assignment_section.html | 174 | `font-size: 2rem; color: #ccc;` |
| apps/assignments/templates/assignments/assignment_section.html | 181 | `font-size: 2rem; color: #ccc;` |
| apps/assignments/templates/assignments/modals.html | 73 | `max-height: 250px;` |
| apps/assignments/templates/assignments/modals.html | 85 | `max-height: 250px;` |
| apps/assignments/templates/assignments/modals.html | 90 | `font-size: 0.6rem;` |
| apps/assignments/templates/assignments/modals.html | 105 | `min-height: 200px;` |
| apps/assignments/templates/assignments/my_submissions.html | 45 | `letter-spacing: 0.5px;` |
| apps/assignments/templates/assignments/my_submissions.html | 53 | `letter-spacing: 0.5px;` |
| apps/assignments/templates/assignments/my_submissions.html | 157 | `white-space: pre-wrap;` |
| apps/assignments/templates/assignments/my_submissions.html | 212 | `width: 80px; height: 80px;` |
| apps/assignments/templates/assignments/partials/_assignment_modals.html | 53 | `max-height:250px;overflow-y:auto;` |
| apps/assignments/templates/assignments/partials/_assignment_modals.html | 59 | `max-height:250px;overflow-y:auto;` |
| apps/assignments/templates/assignments/partials/_assignment_modals.html | 125 | `max-height:250px;overflow-y:auto;` |
| apps/assignments/templates/assignments/partials/_assignment_modals.html | 131 | `max-height:250px;overflow-y:auto;` |
| apps/assignments/templates/assignments/partials/_edit_assignment_form.html | 57 | `max-height: 160px; overflow:auto;` |
| apps/assignments/templates/assignments/partials/_edit_assignment_form.html | 75 | `max-height: 160px; overflow:auto;` |
| apps/blog/templates/blog/create_question.html | 7 | `max-width: 840px;` |
| apps/blog/templates/blog/my_questions.html | 7 | `max-width: 960px;` |
| apps/blog/templates/blog/questions_i_can_see.html | 7 | `max-width: 960px;` |
| apps/blog/templates/post_form.html | 18 | `margin-bottom: 16px; padding: 12px 14px; border-radius: 10px` |
| apps/blog/templates/post_form.html | 73 | `text-align: center; margin: 10px 0; color: #888; font-size: ` |
| apps/contact/templates/admin/contact/contactmessage/reply.html | 107 | `margin-bottom:16px;` |
| apps/contact/templates/admin/contact/contactmessage/reply.html | 116 | `margin-bottom:16px;` |
| apps/contact/templates/admin/contact/contactmessage/reply.html | 157 | `border-left-color:#1e40af;` |
| apps/courses/templates/courses/edit_course.html | 309 | `color: var(--edit-primary);` |
| apps/courses/templates/courses/edit_course.html | 359 | `background: var(--edit-primary);` |
| apps/courses/templates/courses/partials/_resource_accordion.html | 30 | `border-left: 4px solid #28a745;` |
| apps/courses/templates/courses/student_courses.html | 37 | `height: 150px; background: linear-gradient(135deg, #2563eb 0` |
| apps/courses/templates/courses/student_courses.html | 41 | `object-fit: cover;` |
| apps/exams/templates/exams/components/_exam_modals.html | 34 | `max-height: 400px; overflow-y: auto;` |
| apps/exams/templates/exams/student/take_coding_exam.html | 101 | `margin-top:0.75rem;` |
| apps/exams/templates/exams/student/take_coding_exam.html | 102 | `max-width:100%;max-height:320px;border-radius:8px;` |
| apps/exams/templates/exams/student/take_coding_exam.html | 106 | `margin-top:0.75rem;` |
| apps/exams/templates/exams/student/take_coding_exam.html | 107 | `max-width:100%;max-height:320px;border-radius:8px;` |
| apps/exams/templates/exams/student/take_exam.html | 67 | `width: 0%;` |
| apps/exams/templates/exams/teacher/exam_bank_picker.html | 6 | `max-width: 1040px;` |
| apps/exams/templates/exams/teacher/exam_section.html | 129 | `font-size: 2rem; color: #ccc;` |
| apps/exams/templates/exams/teacher/exam_section.html | 285 | `font-size: 2rem; color: #ccc;` |
| apps/exams/templates/exams/teacher/exam_section.html | 292 | `font-size: 2rem; color: #ccc;` |
| apps/exams/templates/exams/teacher/exam_section.html | 376 | `margin-top:.4rem;color:#b91c1c;font-size:.84rem;font-weight:` |
| apps/exams/templates/exams/teacher/partials/_bulk_question_workbench.html | 491 | `width:70px;` |
| apps/exams/templates/exams/teacher/partials/_coding_exam_fields.html | 5 | `color:#0f766e;` |
| apps/exams/templates/exams/teacher/partials/_question_bank_list_body.html | 38 | `color:var(--danger,#e74c3c)` |
| apps/exams/templates/exams/teacher/partials/_question_form.html | 109 | `width:100%; border-radius:8px;` |
| apps/exams/templates/exams/teacher/partials/_question_form.html | 120 | `width:100%; border-radius:8px;` |
| apps/exams/templates/exams/teacher/partials/_teacher_exam_statistics_js.html | 161 | `margin-top:12px;padding:8px 12px;background:#f0f9ff;border-r` |
| apps/exams/templates/exams/teacher/partials/_teacher_exam_statistics_js.html | 165 | `color:#059669` |
| apps/exams/templates/exams/teacher/supervision_monitor.html | 55 | `flex:1;min-width:200px;` |
| apps/exams/templates/exams/teacher/supervision_monitor.html | 126 | `font-size:0.72rem;` |
| apps/exams/templates/exams/teacher/supervision_monitor.html | 182 | `white-space:nowrap;color:var(--sm-text-muted);` |
| apps/exams/templates/exams/teacher/supervision_monitor.html | 192 | `opacity:0.5;cursor:not-allowed;` |
| apps/exams/templates/exams/teacher/teacher_view_attempt.html | 186 | `max-height:360px;` |
| apps/exams/templates/exams/teacher/teacher_view_attempt.html | 191 | `max-height:360px;` |
| apps/labs/templates/labs/grade_submission.html | 66 | `background: linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%` |
| apps/labs/templates/labs/grade_submission.html | 75 | `width: 40px; height: 40px;` |
| apps/labs/templates/labs/grade_submission.html | 139 | `top: 20px;` |
| apps/labs/templates/labs/lab_detail.html | 119 | `width: 0%;` |
| apps/labs/templates/labs/lab_section.html | 86 | `font-size: 2rem; color: #ccc;` |
| apps/labs/templates/labs/lab_section.html | 178 | `font-size: 2rem; color: #ccc;` |
| apps/labs/templates/labs/lab_section.html | 185 | `font-size: 2rem; color: #ccc;` |
| apps/labs/templates/labs/partials/lab_modals/_add_lab_modal.html | 73 | `max-height:200px;overflow-y:auto;` |
| apps/labs/templates/labs/partials/lab_modals/_add_lab_modal.html | 79 | `max-height:200px;overflow-y:auto;` |
| apps/labs/templates/labs/partials/lab_modals/_edit_lab_modal.html | 74 | `max-height:200px;overflow-y:auto;` |
| apps/labs/templates/labs/partials/lab_modals/_edit_lab_modal.html | 80 | `max-height:200px;overflow-y:auto;` |
| apps/labs/templates/labs/preview_randomization.html | 105 | `width: 80px; height: 80px;` |
| apps/labs/templates/labs/preview_randomization.html | 116 | `width: 80px; height: 80px;` |
| apps/labs/templates/labs/preview_randomization.html | 146 | `background-color: var(--light-blue); color: var(--primary-bl` |
| apps/labs/templates/labs/preview_randomization.html | 155 | `background-color: #fef3c7; color: #d97706;` |
| apps/live_exam/templates/liveExam/teacher_live_results.html | 75 | `font-size:.78rem` |
| apps/projects/templates/projects/partials/_project_modals.html | 56 | `max-height:250px;overflow-y:auto;` |
| apps/projects/templates/projects/partials/_project_modals.html | 62 | `max-height:250px;overflow-y:auto;` |
| apps/projects/templates/projects/partials/_project_modals.html | 131 | `max-height:250px;overflow-y:auto;` |
| apps/projects/templates/projects/partials/_project_modals.html | 137 | `max-height:250px;overflow-y:auto;` |
| apps/projects/templates/projects/project_section.html | 6 | `color: #17a2b8;` |
| apps/projects/templates/projects/project_section.html | 94 | `font-size: 2rem; color: #ccc;` |
| apps/projects/templates/projects/project_section.html | 183 | `font-size: 2rem; color: #ccc;` |
| apps/projects/templates/projects/project_section.html | 190 | `font-size: 2rem; color: #ccc;` |
| apps/trial_exams/templates/admin/trial_exams/trialexamrequest/reply.html | 98 | `margin-top:-6px;` |
| apps/trial_exams/templates/admin/trial_exams/trialexamrequest/reply.html | 105 | `margin-bottom:16px;` |
| apps/trial_exams/templates/admin/trial_exams/trialexamrequest/reply.html | 112 | `margin-bottom:16px;` |
| apps/trial_exams/templates/admin/trial_exams/trialexamrequest/reply.html | 149 | `border-left-color:#1e40af;` |
| templates/organizations/dashboard.html | 206 | `margin-bottom: 2rem; font-size: 28px;` |
| templates/organizations/dashboard.html | 281 | `background: #dbeafe; color: #1e40af; padding: 0.5rem 1rem; b` |
| templates/organizations/select_organization.html | 218 | `margin-top: 12px;` |
| templates/organizations/settings.html | 130 | `font-size: 24px; font-weight: 600;` |
| templates/organizations/settings.html | 142 | `margin-bottom: 2rem;` |
