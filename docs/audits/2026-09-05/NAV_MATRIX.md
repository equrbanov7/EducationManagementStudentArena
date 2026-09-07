# Naviqasiya matrisi (avtomatik) — HTTP süpürgəsi

Hesab: 29 · uğurlu login: 29 · uğursuz: 0 · fərqli bölmə: 81

## Rol üzrə yekun

| rol | bölmə | ajax200 | ajax403 | ajax4xx-digər | 5xx | ən yavaş (tam səhifə) | qabıq ms |
|---|---:|---:|---:|---:|---:|---|---:|
| `superadmin` | 72 | 49 | 23 | 0 | 0 | `analytics` 3472 ms | 105 |
| `rector` | 53 | 43 | 10 | 0 | 0 | `analytics` 3030 ms | 121 |
| `vice_rector` | 46 | 38 | 8 | 0 | 0 | `analytics` 3246 ms | 109 |
| `ikt_rehber` | 59 | 44 | 15 | 0 | 0 | `analytics` 3587 ms | 134 |
| `exam_center_head` | 31 | 21 | 10 | 0 | 0 | `analytics` 3300 ms | 89 |
| `exam_center` | 31 | 21 | 10 | 0 | 0 | `analytics` 3275 ms | 84 |
| `teaching_office_head` | 23 | 21 | 2 | 0 | 0 | `analytics` 2845 ms | 98 |
| `dean` | 44 | 36 | 8 | 0 | 0 | `lessons-log` 320 ms | 129 |
| `chair_head` | 44 | 36 | 8 | 0 | 0 | `chair-profile` 341 ms | 120 |
| `hr` | 26 | 20 | 6 | 0 | 0 | `analytics` 3219 ms | 94 |
| `exam_center_staff` | 27 | 18 | 9 | 0 | 0 | `analytics` 3461 ms | 87 |
| `student_services` | 18 | 16 | 2 | 0 | 0 | `chair-profile` 253 ms | 83 |
| `teaching_office_staff` | 21 | 19 | 2 | 0 | 0 | `analytics` 3642 ms | 97 |
| `teacher` | 20 | 17 | 3 | 0 | 0 | `applications` 119 ms | 89 |
| `program_coordinator` | 24 | 22 | 2 | 0 | 0 | `semester-opening` 274 ms | 99 |
| `lab_assistant` | 19 | 16 | 3 | 0 | 0 | `applications` 197 ms | 96 |
| `assistant` | 19 | 16 | 3 | 0 | 0 | `edit-profile` 204 ms | 96 |
| `tutor` | 12 | 10 | 2 | 0 | 0 | `my-schedule` 235 ms | 106 |
| `lead_student` | 17 | 15 | 2 | 0 | 0 | `assigned-courses` 388 ms | 131 |
| `member` | 14 | 12 | 2 | 0 | 0 | `academic-calendar` 372 ms | 165 |
| `student` | 17 | 15 | 2 | 0 | 0 | `pending-answers` 786 ms | 115 |
| `alumni` | 8 | 6 | 2 | 0 | 0 | `academic-calendar` 216 ms | 139 |
| `chair_head_b` | 44 | 36 | 8 | 0 | 0 | `org-faculties` 1254 ms | 403 |
| `dean_b` | 44 | 36 | 8 | 0 | 0 | `analytics` 441 ms | 127 |
| `ikt_rehber_b` | 59 | 44 | 15 | 0 | 0 | `analytics` 3697 ms | 158 |
| `teacher_a` | 20 | 17 | 3 | 0 | 0 | `applications` 143 ms | 114 |
| `teacher_b` | 20 | 17 | 3 | 0 | 0 | `lessons-log` 133 ms | 110 |
| `student_b` | 17 | 15 | 2 | 0 | 0 | `assigned-exams` 149 ms | 81 |
| `inactive_ikt` | 6 | 4 | 2 | 0 | 0 | `change-password` 100 ms | 62 |

## Anomaliyalar

- `superadmin` / `profile-info`: xam msgid şübhəsi: staging_admin
- `superadmin` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `superadmin` / `applications`: 1 inline `<script>` (CSP qaydası)
- `superadmin` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `superadmin` / `student-registry`: 1 inline `<script>` (CSP qaydası)
- `superadmin` / `my-schedule`: xam msgid şübhəsi: staging_admin
- `superadmin` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `superadmin` / `analytics`: yavaş — 3472 ms (tam səhifə), AJAX 8205 ms
- `superadmin` / `syllabus-review`: xam msgid şübhəsi: staging_admin
- `superadmin` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `superadmin` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `superadmin` / `groups`: 1 inline `<script>` (CSP qaydası)
- `superadmin` / `audit-log`: xam msgid şübhəsi: staging_admin
- `superadmin` / `rim-center`: 1 inline `<script>` (CSP qaydası)
- `rector` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `rector` / `applications`: 1 inline `<script>` (CSP qaydası)
- `rector` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `rector` / `student-registry`: 1 inline `<script>` (CSP qaydası)
- `rector` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `rector` / `analytics`: yavaş — 3030 ms (tam səhifə), AJAX 3497 ms
- `rector` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `rector` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `rector` / `groups`: 1 inline `<script>` (CSP qaydası)
- `rector` / `rim-center`: 1 inline `<script>` (CSP qaydası)
- `vice_rector` / `profile-info`: xam msgid şübhəsi: vice_rector
- `vice_rector` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `vice_rector` / `applications`: 1 inline `<script>` (CSP qaydası)
- `vice_rector` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `vice_rector` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `vice_rector` / `analytics`: yavaş — 3246 ms (tam səhifə), AJAX 3607 ms
- `vice_rector` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `vice_rector` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `vice_rector` / `groups`: 1 inline `<script>` (CSP qaydası)
- `vice_rector` / `rim-center`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `applications`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `student-registry`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `analytics`: yavaş — 3587 ms (tam səhifə), AJAX 4120 ms
- `ikt_rehber` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `ikt_rehber` / `groups`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber` / `rim-center`: 1 inline `<script>` (CSP qaydası)
- `exam_center_head` / `profile-info`: xam msgid şübhəsi: exam_center_head
- `exam_center_head` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `exam_center_head` / `applications`: 1 inline `<script>` (CSP qaydası)
- `exam_center_head` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `exam_center_head` / `analytics`: yavaş — 3300 ms (tam səhifə), AJAX 3832 ms
- `exam_center_head` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `exam_center` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `exam_center` / `applications`: 1 inline `<script>` (CSP qaydası)
- `exam_center` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `exam_center` / `analytics`: yavaş — 3275 ms (tam səhifə), AJAX 3546 ms
- `exam_center` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `teaching_office_head` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_head` / `applications`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_head` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `teaching_office_head` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_head` / `analytics`: yavaş — 2845 ms (tam səhifə), AJAX 3103 ms
- `dean` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `dean` / `applications`: 1 inline `<script>` (CSP qaydası)
- `dean` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `dean` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `dean` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `dean` / `groups`: 1 inline `<script>` (CSP qaydası)
- `chair_head` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `chair_head` / `applications`: 1 inline `<script>` (CSP qaydası)
- `chair_head` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `chair_head` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `chair_head` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `chair_head` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `chair_head` / `groups`: 1 inline `<script>` (CSP qaydası)
- `hr` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `hr` / `applications`: 1 inline `<script>` (CSP qaydası)
- `hr` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `hr` / `analytics`: yavaş — 3219 ms (tam səhifə), AJAX 3811 ms
- `hr` / `rim-center`: 1 inline `<script>` (CSP qaydası)
- `exam_center_staff` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `exam_center_staff` / `applications`: 1 inline `<script>` (CSP qaydası)
- `exam_center_staff` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `exam_center_staff` / `analytics`: yavaş — 3461 ms (tam səhifə), AJAX 3501 ms
- `exam_center_staff` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `student_services` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `student_services` / `applications`: 1 inline `<script>` (CSP qaydası)
- `student_services` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `student_services` / `student-registry`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_staff` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_staff` / `applications`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_staff` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `teaching_office_staff` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `teaching_office_staff` / `analytics`: yavaş — 3642 ms (tam səhifə), AJAX 3598 ms
- `teacher` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `teacher` / `applications`: 1 inline `<script>` (CSP qaydası)
- `teacher` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `program_coordinator` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `program_coordinator` / `applications`: 1 inline `<script>` (CSP qaydası)
- `program_coordinator` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `lab_assistant` / `profile-info`: xam msgid şübhəsi: lab_assistant
- `lab_assistant` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `lab_assistant` / `applications`: 1 inline `<script>` (CSP qaydası)
- `lab_assistant` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `assistant` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `assistant` / `applications`: 1 inline `<script>` (CSP qaydası)
- `assistant` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `tutor` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `tutor` / `applications`: 1 inline `<script>` (CSP qaydası)
- `tutor` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `lead_student` / `profile-info`: xam msgid şübhəsi: lead_student
- `lead_student` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `lead_student` / `applications`: 1 inline `<script>` (CSP qaydası)
- `lead_student` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `member` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `member` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `student` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `student` / `applications`: 1 inline `<script>` (CSP qaydası)
- `student` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `alumni` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `alumni` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `chair_head_b` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `chair_head_b` / `applications`: 1 inline `<script>` (CSP qaydası)
- `chair_head_b` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `chair_head_b` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `chair_head_b` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `chair_head_b` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `chair_head_b` / `groups`: 1 inline `<script>` (CSP qaydası)
- `dean_b` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `dean_b` / `applications`: 1 inline `<script>` (CSP qaydası)
- `dean_b` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `dean_b` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `dean_b` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `dean_b` / `groups`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `applications`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `student-registry`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `workload-distribution`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `analytics`: yavaş — 3697 ms (tam səhifə), AJAX 4147 ms
- `ikt_rehber_b` / `syllabus-review`: 2 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `academic-records`: menyuda var, amma «icazəniz yoxdur»
- `ikt_rehber_b` / `groups`: 1 inline `<script>` (CSP qaydası)
- `ikt_rehber_b` / `rim-center`: 1 inline `<script>` (CSP qaydası)
- `teacher_a` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `teacher_a` / `applications`: 1 inline `<script>` (CSP qaydası)
- `teacher_a` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `teacher_b` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `teacher_b` / `applications`: 1 inline `<script>` (CSP qaydası)
- `teacher_b` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `student_b` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `student_b` / `applications`: 1 inline `<script>` (CSP qaydası)
- `student_b` / `statistics`: 2 inline `<script>` (CSP qaydası)
- `inactive_ikt` / `notifications`: 1 inline `<script>` (CSP qaydası)
- `inactive_ikt` / `statistics`: 2 inline `<script>` (CSP qaydası)

## Rol × bölmə (✅ AJAX 200 · 🔒 AJAX 403 (tam səhifə 200) · ❌ xəta · · görünmür)

| bölmə | `superadmin` | `rector` | `vice_rector` | `ikt_rehber` | `exam_center_head` | `exam_center` | `teaching_office_head` | `dean` | `chair_head` | `hr` | `exam_center_staff` | `student_services` | `teaching_office_staff` | `teacher` | `program_coordinator` | `lab_assistant` | `assistant` | `tutor` | `lead_student` | `member` | `student` | `alumni` | `chair_head_b` | `dean_b` | `ikt_rehber_b` | `teacher_a` | `teacher_b` | `student_b` | `inactive_ikt` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `academic-calendar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `academic-records` | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | · | 🔒 | 🔒 | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · |
| `analytics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | ✅ | · | · | ✅ | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `appeal-stats` | 🔒 | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `applications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `assigned-courses` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · |
| `assigned-exams` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · |
| `audit-log` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |
| `category-management` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `chair-profile` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `change-password` | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 |
| `create-category` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `curriculum-editor` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `dashboard` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `edit-profile` | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 |
| `exam-center-pins` | 🔒 | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `exam-center-stats` | 🔒 | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `exam-chance` | 🔒 | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `exam-score-entry` | 🔒 | 🔒 | · | · | 🔒 | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `groups` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | ✅ | · | · | ✅ | · | ✅ | ✅ | · | · | ✅ | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `groups-registry` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `journal-close` | 🔒 | 🔒 | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `kollokvium-windows` | 🔒 | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `legacy-grade-review` | ✅ | ✅ | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |
| `lessons-log` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `manage-appeals` | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |
| `manage-roles` | 🔒 | 🔒 | 🔒 | 🔒 | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · |
| `my-appeals` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · |
| `my-courses` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | ✅ | · | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `my-exams` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | ✅ | · | · | ✅ | · | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `my-journal` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | ✅ | · |
| `my-results` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · |
| `my-schedule` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `my-subjects` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | ✅ | · |
| `my-workload` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `notifications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `org-faculties` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `org-kafedras` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `org-members` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | · | · | ✅ | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `org-roles` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `org-structure-tree` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `overall-academic` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | ✅ | · |
| `pending-answers` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · |
| `pending-review` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `people-students` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | ✅ | · | ✅ | · | · | ✅ | · | · | ✅ | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `people-teachers` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `permission-editor` | 🔒 | 🔒 | 🔒 | 🔒 | · | · | · | 🔒 | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · |
| `profile-info` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `programs-registry` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `publish-notification` | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | · | 🔒 | 🔒 | 🔒 | 🔒 | · | · | 🔒 | · | 🔒 | 🔒 | · | · | · | · | · | 🔒 | 🔒 | 🔒 | 🔒 | 🔒 | · | · |
| `question-bank` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | ✅ | · | · | ✅ | · | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `question-chair-review` | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `question-submissions` | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · | · | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · |
| `review-results` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `rim-center` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |
| `role-assignment` | 🔒 | 🔒 | 🔒 | 🔒 | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · |
| `schedule-manage` | ✅ | ✅ | · | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `semester-opening` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `statistics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `student-admission` | ✅ | ✅ | · | ✅ | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |
| `student-intake` | ✅ | ✅ | · | ✅ | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |
| `student-organization-management` | 🔒 | 🔒 | 🔒 | 🔒 | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | 🔒 | 🔒 | · | · | · | · |
| `student-registry` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | · | · | · | ✅ | · | · | ✅ | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · |
| `subject-catalog` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `superadmin-ai` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `superadmin-contact-messages` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `superadmin-exam-rooms` | 🔒 | · | · | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | 🔒 | · | · | · | · |
| `superadmin-org-features` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `superadmin-org-inspector` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `superadmin-organizations` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `superadmin-users` | 🔒 | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `syllabus-list` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | · | · |
| `syllabus-review` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `system-monitoring` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `teaching-handover` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `unit-exams` | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `workload-approval` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · |
| `workload-center` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | ✅ | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · |
| `workload-distribution` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | ✅ | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | ✅ | · | ✅ | · | · | · | · |
| `workload-overview` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · |
| `workload-visa` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | ✅ | · | · | · | · |

## İnventar (rol üzrə ən çox elementli bölmələr — funksional test hədəfləri)

| rol | bölmə | cədvəl | forma | düymə | select | input | fayl | modal | səhifələmə |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `superadmin` | `superadmin-exam-rooms` | 158 | 809 | 2252 | 3 | 1907 | 0 | 17 | 0 |
| `superadmin` | `org-kafedras` | 0 | 379 | 463 | 6 | 5 | 0 | 104 | 2 |
| `superadmin` | `org-structure-tree` | 0 | 4 | 891 | 2 | 5 | 0 | 0 | 0 |
| `superadmin` | `permission-editor` | 0 | 150 | 240 | 2 | 115 | 0 | 17 | 0 |
| `superadmin` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `superadmin` | `student-organization-management` | 13 | 41 | 132 | 4 | 24 | 0 | 45 | 6 |
| `rector` | `org-kafedras` | 0 | 379 | 463 | 6 | 5 | 0 | 104 | 2 |
| `rector` | `org-structure-tree` | 0 | 5 | 894 | 3 | 5 | 0 | 0 | 0 |
| `rector` | `semester-opening` | 2 | 5 | 418 | 3 | 5 | 0 | 0 | 0 |
| `rector` | `permission-editor` | 0 | 187 | 276 | 0 | 114 | 0 | 17 | 0 |
| `rector` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `rector` | `manage-roles` | 1 | 28 | 49 | 0 | 135 | 0 | 23 | 2 |
| `vice_rector` | `org-kafedras` | 0 | 379 | 463 | 6 | 5 | 0 | 104 | 2 |
| `vice_rector` | `org-structure-tree` | 0 | 5 | 894 | 3 | 5 | 0 | 0 | 0 |
| `vice_rector` | `semester-opening` | 2 | 5 | 418 | 3 | 5 | 0 | 0 | 0 |
| `vice_rector` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `vice_rector` | `manage-roles` | 1 | 28 | 49 | 0 | 135 | 0 | 23 | 2 |
| `vice_rector` | `student-organization-management` | 12 | 38 | 126 | 0 | 21 | 0 | 45 | 6 |
| `ikt_rehber` | `superadmin-exam-rooms` | 158 | 807 | 2251 | 1 | 1906 | 0 | 17 | 0 |
| `ikt_rehber` | `permission-editor` | 0 | 166 | 256 | 1 | 115 | 0 | 17 | 0 |
| `ikt_rehber` | `org-structure-tree` | 0 | 5 | 894 | 3 | 5 | 0 | 0 | 0 |
| `ikt_rehber` | `semester-opening` | 2 | 5 | 418 | 3 | 5 | 0 | 0 | 0 |
| `ikt_rehber` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `ikt_rehber` | `student-organization-management` | 12 | 39 | 128 | 1 | 22 | 0 | 45 | 6 |
| `exam_center_head` | `org-structure-tree` | 0 | 4 | 891 | 2 | 5 | 0 | 0 | 0 |
| `exam_center_head` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `exam_center_head` | `exam-score-entry` | 1 | 21 | 35 | 34 | 90 | 29 | 11 | 0 |
| `exam_center_head` | `edit-profile` | 0 | 18 | 48 | 3 | 17 | 1 | 32 | 0 |
| `exam_center_head` | `appeal-stats` | 1 | 16 | 37 | 6 | 9 | 0 | 17 | 0 |
| `exam_center_head` | `kollokvium-windows` | 0 | 20 | 39 | 5 | 6 | 0 | 13 | 0 |
| `exam_center` | `org-structure-tree` | 0 | 4 | 891 | 2 | 5 | 0 | 0 | 0 |
| `exam_center` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `exam_center` | `exam-score-entry` | 1 | 21 | 35 | 34 | 90 | 29 | 11 | 0 |
| `exam_center` | `edit-profile` | 0 | 18 | 48 | 3 | 15 | 1 | 32 | 0 |
| `exam_center` | `appeal-stats` | 1 | 16 | 37 | 6 | 9 | 0 | 17 | 0 |
| `exam_center` | `kollokvium-windows` | 0 | 20 | 39 | 5 | 6 | 0 | 13 | 0 |
| `teaching_office_head` | `org-structure-tree` | 0 | 5 | 894 | 3 | 5 | 0 | 0 | 0 |
| `teaching_office_head` | `semester-opening` | 2 | 5 | 418 | 3 | 5 | 0 | 0 | 0 |
| `teaching_office_head` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `teaching_office_head` | `groups-registry` | 1 | 5 | 66 | 6 | 32 | 0 | 0 | 2 |
| `teaching_office_head` | `edit-profile` | 0 | 17 | 42 | 2 | 16 | 1 | 21 | 0 |
| `teaching_office_head` | `programs-registry` | 1 | 4 | 62 | 8 | 5 | 0 | 0 | 2 |
| `dean` | `semester-opening` | 2 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |
| `dean` | `manage-roles` | 1 | 29 | 51 | 1 | 136 | 0 | 23 | 2 |
| `dean` | `student-organization-management` | 12 | 39 | 106 | 1 | 22 | 0 | 45 | 2 |
| `dean` | `role-assignment` | 2 | 19 | 56 | 13 | 5 | 0 | 30 | 2 |
| `dean` | `edit-profile` | 0 | 18 | 50 | 3 | 15 | 1 | 38 | 0 |
| `dean` | `change-password` | 0 | 18 | 41 | 1 | 9 | 0 | 17 | 0 |
| `chair_head` | `semester-opening` | 2 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |
| `chair_head` | `student-organization-management` | 12 | 39 | 106 | 1 | 22 | 0 | 45 | 2 |
| `chair_head` | `manage-roles` | 1 | 29 | 51 | 1 | 88 | 0 | 23 | 2 |
| `chair_head` | `role-assignment` | 2 | 19 | 56 | 13 | 5 | 0 | 30 | 2 |
| `chair_head` | `org-kafedras` | 0 | 77 | 94 | 5 | 3 | 0 | 41 | 0 |
| `chair_head` | `edit-profile` | 0 | 18 | 50 | 3 | 15 | 1 | 38 | 0 |
| `hr` | `org-structure-tree` | 0 | 1 | 882 | 1 | 1 | 0 | 0 | 0 |
| `hr` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `hr` | `student-organization-management` | 12 | 39 | 123 | 1 | 22 | 0 | 28 | 6 |
| `hr` | `manage-roles` | 1 | 29 | 46 | 1 | 76 | 0 | 6 | 2 |
| `hr` | `role-assignment` | 2 | 19 | 51 | 13 | 5 | 0 | 13 | 2 |
| `hr` | `edit-profile` | 0 | 18 | 44 | 3 | 15 | 1 | 21 | 0 |
| `exam_center_staff` | `org-structure-tree` | 0 | 1 | 882 | 1 | 1 | 0 | 0 | 0 |
| `exam_center_staff` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `exam_center_staff` | `edit-profile` | 0 | 17 | 46 | 2 | 14 | 1 | 32 | 0 |
| `exam_center_staff` | `appeal-stats` | 1 | 15 | 35 | 5 | 8 | 0 | 17 | 0 |
| `exam_center_staff` | `change-password` | 0 | 17 | 38 | 0 | 8 | 0 | 11 | 0 |
| `exam_center_staff` | `academic-records` | 1 | 15 | 34 | 2 | 7 | 0 | 16 | 0 |
| `student_services` | `org-structure-tree` | 0 | 1 | 882 | 1 | 1 | 0 | 0 | 0 |
| `student_services` | `edit-profile` | 0 | 17 | 42 | 2 | 14 | 1 | 21 | 0 |
| `student_services` | `student-registry` | 1 | 2 | 56 | 11 | 11 | 1 | 0 | 2 |
| `student_services` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `student_services` | `groups-registry` | 1 | 1 | 2 | 5 | 1 | 0 | 0 | 2 |
| `student_services` | `programs-registry` | 1 | 1 | 2 | 5 | 1 | 0 | 0 | 2 |
| `teaching_office_staff` | `org-structure-tree` | 0 | 4 | 891 | 2 | 5 | 0 | 0 | 0 |
| `teaching_office_staff` | `semester-opening` | 2 | 4 | 414 | 3 | 5 | 0 | 0 | 0 |
| `teaching_office_staff` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `teaching_office_staff` | `groups-registry` | 1 | 5 | 66 | 6 | 32 | 0 | 0 | 2 |
| `teaching_office_staff` | `edit-profile` | 0 | 17 | 42 | 2 | 16 | 1 | 21 | 0 |
| `teaching_office_staff` | `programs-registry` | 1 | 4 | 62 | 8 | 5 | 0 | 0 | 2 |
| `teacher` | `edit-profile` | 0 | 17 | 48 | 2 | 14 | 1 | 38 | 0 |
| `teacher` | `change-password` | 0 | 17 | 39 | 0 | 8 | 0 | 17 | 0 |
| `teacher` | `publish-notification` | 0 | 15 | 33 | 0 | 2 | 0 | 17 | 0 |
| `teacher` | `notifications` | 0 | 15 | 21 | 0 | 8 | 0 | 15 | 0 |
| `teacher` | `syllabus-list` | 1 | 0 | 30 | 4 | 1 | 0 | 1 | 0 |
| `teacher` | `question-bank` | 0 | 4 | 6 | 6 | 5 | 0 | 12 | 0 |
| `program_coordinator` | `semester-opening` | 2 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |
| `program_coordinator` | `edit-profile` | 0 | 17 | 42 | 2 | 14 | 1 | 21 | 0 |
| `program_coordinator` | `lessons-log` | 16 | 1 | 2 | 6 | 1 | 0 | 0 | 0 |
| `program_coordinator` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `program_coordinator` | `groups-registry` | 1 | 5 | 38 | 6 | 18 | 0 | 0 | 0 |
| `program_coordinator` | `notifications` | 0 | 11 | 17 | 0 | 6 | 0 | 15 | 0 |
| `lab_assistant` | `edit-profile` | 0 | 17 | 48 | 2 | 16 | 1 | 38 | 0 |
| `lab_assistant` | `change-password` | 0 | 17 | 39 | 0 | 8 | 0 | 17 | 0 |
| `lab_assistant` | `publish-notification` | 0 | 15 | 33 | 0 | 2 | 0 | 17 | 0 |
| `lab_assistant` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `lab_assistant` | `applications` | 0 | 0 | 25 | 1 | 5 | 2 | 0 | 0 |
| `lab_assistant` | `lessons-log` | 0 | 1 | 2 | 5 | 1 | 0 | 0 | 0 |
| `assistant` | `edit-profile` | 0 | 17 | 48 | 2 | 14 | 1 | 38 | 0 |
| `assistant` | `change-password` | 0 | 17 | 39 | 0 | 8 | 0 | 17 | 0 |
| `assistant` | `publish-notification` | 0 | 15 | 33 | 0 | 2 | 0 | 17 | 0 |
| `assistant` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `assistant` | `applications` | 0 | 0 | 25 | 1 | 5 | 2 | 0 | 0 |
| `assistant` | `lessons-log` | 0 | 1 | 2 | 5 | 1 | 0 | 0 | 0 |
| `tutor` | `edit-profile` | 0 | 18 | 44 | 3 | 17 | 1 | 21 | 0 |
| `tutor` | `change-password` | 0 | 18 | 36 | 1 | 9 | 0 | 0 | 0 |
| `tutor` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `tutor` | `org-members` | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 2 |
| `tutor` | `applications` | 0 | 0 | 25 | 1 | 5 | 2 | 0 | 0 |
| `tutor` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `lead_student` | `edit-profile` | 0 | 17 | 42 | 0 | 16 | 1 | 21 | 0 |
| `lead_student` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `lead_student` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `lead_student` | `applications` | 0 | 0 | 25 | 1 | 5 | 2 | 0 | 0 |
| `lead_student` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `lead_student` | `my-appeals` | 0 | 1 | 3 | 1 | 1 | 0 | 13 | 0 |
| `member` | `edit-profile` | 0 | 17 | 42 | 2 | 14 | 1 | 21 | 0 |
| `member` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `member` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `member` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `member` | `my-appeals` | 0 | 1 | 3 | 1 | 1 | 0 | 13 | 0 |
| `member` | `my-schedule` | 0 | 0 | 2 | 2 | 0 | 0 | 10 | 0 |
| `student` | `edit-profile` | 0 | 17 | 42 | 0 | 14 | 1 | 21 | 0 |
| `student` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `student` | `notifications` | 0 | 19 | 25 | 0 | 10 | 0 | 15 | 0 |
| `student` | `applications` | 0 | 0 | 25 | 1 | 5 | 2 | 0 | 0 |
| `student` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `student` | `my-appeals` | 0 | 1 | 3 | 1 | 1 | 0 | 13 | 0 |
| `alumni` | `edit-profile` | 0 | 17 | 42 | 2 | 16 | 1 | 21 | 0 |
| `alumni` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `alumni` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `alumni` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `alumni` | `my-schedule` | 0 | 0 | 2 | 2 | 0 | 0 | 10 | 0 |
| `alumni` | `statistics` | 0 | 1 | 1 | 1 | 2 | 0 | 0 | 0 |
| `chair_head_b` | `semester-opening` | 2 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |
| `chair_head_b` | `manage-roles` | 1 | 29 | 51 | 1 | 88 | 0 | 23 | 2 |
| `chair_head_b` | `student-organization-management` | 12 | 39 | 105 | 1 | 22 | 0 | 45 | 2 |
| `chair_head_b` | `role-assignment` | 2 | 19 | 56 | 13 | 5 | 0 | 30 | 2 |
| `chair_head_b` | `edit-profile` | 0 | 18 | 50 | 3 | 15 | 1 | 38 | 0 |
| `chair_head_b` | `change-password` | 0 | 18 | 41 | 1 | 9 | 0 | 17 | 0 |
| `dean_b` | `semester-opening` | 2 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |
| `dean_b` | `manage-roles` | 1 | 29 | 51 | 1 | 136 | 0 | 23 | 2 |
| `dean_b` | `org-kafedras` | 0 | 105 | 149 | 6 | 5 | 0 | 69 | 0 |
| `dean_b` | `student-organization-management` | 12 | 39 | 104 | 1 | 22 | 0 | 45 | 2 |
| `dean_b` | `role-assignment` | 2 | 19 | 56 | 13 | 5 | 0 | 30 | 2 |
| `dean_b` | `edit-profile` | 0 | 18 | 50 | 3 | 15 | 1 | 38 | 0 |
| `ikt_rehber_b` | `superadmin-exam-rooms` | 158 | 807 | 2251 | 1 | 1906 | 0 | 17 | 0 |
| `ikt_rehber_b` | `permission-editor` | 0 | 166 | 256 | 1 | 115 | 0 | 17 | 0 |
| `ikt_rehber_b` | `org-structure-tree` | 0 | 5 | 894 | 3 | 5 | 0 | 0 | 0 |
| `ikt_rehber_b` | `semester-opening` | 2 | 5 | 418 | 3 | 5 | 0 | 0 | 0 |
| `ikt_rehber_b` | `analytics` | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `ikt_rehber_b` | `student-organization-management` | 12 | 39 | 128 | 1 | 22 | 0 | 45 | 6 |
| `teacher_a` | `edit-profile` | 0 | 17 | 48 | 2 | 14 | 1 | 38 | 0 |
| `teacher_a` | `change-password` | 0 | 17 | 39 | 0 | 8 | 0 | 17 | 0 |
| `teacher_a` | `publish-notification` | 0 | 15 | 33 | 0 | 2 | 0 | 17 | 0 |
| `teacher_a` | `notifications` | 0 | 7 | 13 | 0 | 4 | 0 | 15 | 0 |
| `teacher_a` | `syllabus-list` | 1 | 0 | 32 | 4 | 1 | 0 | 1 | 0 |
| `teacher_a` | `question-bank` | 0 | 4 | 8 | 6 | 5 | 0 | 12 | 0 |
| `teacher_b` | `edit-profile` | 0 | 17 | 48 | 2 | 14 | 1 | 38 | 0 |
| `teacher_b` | `change-password` | 0 | 17 | 39 | 0 | 8 | 0 | 17 | 0 |
| `teacher_b` | `publish-notification` | 0 | 15 | 33 | 0 | 2 | 0 | 17 | 0 |
| `teacher_b` | `syllabus-list` | 1 | 0 | 34 | 4 | 1 | 0 | 1 | 0 |
| `teacher_b` | `question-bank` | 0 | 4 | 8 | 6 | 5 | 0 | 12 | 0 |
| `teacher_b` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `student_b` | `edit-profile` | 0 | 17 | 42 | 0 | 14 | 1 | 21 | 0 |
| `student_b` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `student_b` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `student_b` | `applications` | 0 | 0 | 25 | 1 | 5 | 2 | 0 | 0 |
| `student_b` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `student_b` | `my-appeals` | 0 | 1 | 3 | 1 | 1 | 0 | 13 | 0 |
| `inactive_ikt` | `edit-profile` | 0 | 17 | 42 | 2 | 14 | 1 | 21 | 0 |
| `inactive_ikt` | `change-password` | 0 | 17 | 34 | 0 | 8 | 0 | 0 | 0 |
| `inactive_ikt` | `notifications` | 0 | 1 | 7 | 0 | 1 | 0 | 15 | 0 |
| `inactive_ikt` | `profile-info` | 0 | 1 | 4 | 0 | 1 | 1 | 8 | 0 |
| `inactive_ikt` | `statistics` | 0 | 1 | 1 | 1 | 2 | 0 | 0 | 0 |
| `inactive_ikt` | `dashboard` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
