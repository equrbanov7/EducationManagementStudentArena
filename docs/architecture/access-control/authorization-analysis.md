# Authorization Analysis

## Request-Time Flow

1. `apps/organizations/middleware.py — OrganizationMiddleware` aktiv tenant-i həll edir.
2. Aktiv `Membership` row-larından `Role.permissions` toplanır.
3. `request.org_permissions` set edilir.
4. FBV/servis səviyyəsində `core.permissions.request_has_permission()` və `ensure_request_permission()` canonical yoxlama rolunu oynayır.
5. CBV üçün `apps.organizations.decorators.PermissionRequiredMixin` və `LevelRequiredMixin` mövcuddur.
6. Object-level qaydalar ayrıca service policy-lərdədir: məsələn `apps/exams/services/access_policy.py`, `apps/exams/services/final_center/permissions.py`, `apps/appeals/services/permissions.py`.

## Backend Enforcement Mənbələri

- `core/permissions.py` — wildcard, alias və active org context check.
- `apps/organizations/decorators.py` — CBV organization/permission/level mixinləri.
- `apps/accounts/views/roles/manage.py` — role assignment: admin level, same-org, lower-level restriction.
- `apps/accounts/views/roles/permissions.py` — permission editor: `role.assign`, lower-role-only və grant delegation.
- `apps/accounts/views/_helpers/rbac.py` — dashboard/sidebar capability flags; backend source deyil, naviqasiya görünürlüyüdür.
- `apps/exams/services/access_policy.py` — teacher/exam-center/final-question-bank policies.
- `apps/exams/services/final_center/permissions.py` — final center manage/supervise/ticket-owner policies.
- `core/tenancy.py` — active organization context və scoped queryset helper.

## Permission String Traceability

| Permission | Detected source references |
| --- | --- |
| analytics.build_period_analytics | apps/registrar/page_contexts.py:83 |
| analytics.html | apps/registrar/analytics_views.py:27 |
| analytics.view_all | apps/organizations/permissions.py:85; apps/organizations/default_roles.py:30; apps/organizations/default_roles.py:54; apps/organizations/default_roles.py:78; apps/organizations/default_roles.py:98; apps/organizations/default_roles.py:310 |
| analytics.view_own | apps/organizations/permissions.py:83; apps/organizations/default_roles.py:177; apps/organizations/default_roles.py:190; apps/organizations/default_roles.py:208; apps/organizations/default_roles.py:258; apps/organizations/default_roles.py:271 |
| analytics.view_unit | apps/organizations/permissions.py:84; apps/organizations/default_roles.py:119; apps/organizations/default_roles.py:138; apps/organizations/default_roles.py:154; apps/organizations/default_roles.py:225; apps/organizations/default_roles.py:242 |
| appeal.attempt | apps/appeals/views/shared/detail.py:41; apps/appeals/views/shared/detail.py:49; apps/appeals/views/shared/detail.py:50; apps/appeals/views/teacher/endpoints.py:232; apps/appeals/views/teacher/endpoints.py:239; apps/appeals/views/teacher/endpoints.py:290 |
| appeal.attempt_id | apps/appeals/services/creation.py:152; apps/appeals/services/scoring.py:445 |
| appeal.create | apps/organizations/permissions.py:78; apps/organizations/default_roles.py:256; apps/organizations/default_roles.py:270; apps/organizations/default_roles.py:529; apps/organizations/default_roles.py:531; apps/appeals/constants.py:88 |
| appeal.decide | apps/organizations/permissions.py:80; apps/organizations/default_roles.py:52; apps/organizations/default_roles.py:76; apps/organizations/default_roles.py:529; apps/appeals/constants.py:90; apps/exams/management/commands/seed_demo_hierarchy.py:53 |
| appeal.exam | apps/appeals/views/shared/detail.py:41; apps/appeals/views/teacher/endpoints.py:168; apps/appeals/services/creation.py:149; apps/appeals/services/scoring.py:442 |
| appeal.exam_id | apps/appeals/services/creation.py:152; apps/appeals/services/scoring.py:445 |
| appeal.field | apps/appeals/models.py:35; apps/appeals/models.py:42; apps/appeals/models.py:48; apps/appeals/models.py:54; apps/appeals/models.py:63; apps/appeals/models.py:70 |
| appeal.id | apps/appeals/views/teacher/endpoints.py:224; apps/appeals/services/creation.py:150; apps/appeals/services/creation.py:152; apps/appeals/services/scoring.py:194; apps/appeals/services/scoring.py:443; apps/appeals/services/scoring.py:445 |
| appeal.items | apps/appeals/views/shared/detail.py:40; apps/appeals/views/teacher/endpoints.py:163; apps/appeals/services/scoring.py:387 |
| appeal.meta | apps/appeals/models.py:93; apps/appeals/models.py:94 |
| appeal.organization | apps/appeals/services/creation.py:153; apps/appeals/services/scoring.py:446 |
| appeal.organization_id | apps/appeals/services/creation.py:111; apps/appeals/services/creation.py:120; apps/appeals/services/permissions.py:24 |
| appeal.respond | apps/organizations/permissions.py:79; apps/organizations/default_roles.py:51; apps/organizations/default_roles.py:75; apps/organizations/default_roles.py:529; apps/appeals/constants.py:89; apps/exams/management/commands/seed_demo_hierarchy.py:52 |
| appeal.reviewed_at | apps/appeals/services/scoring.py:413 |
| appeal.reviewed_by | apps/appeals/services/scoring.py:416 |
| appeal.reviewer_note | apps/appeals/views/teacher/endpoints.py:217 |
| appeal.save | apps/appeals/views/teacher/endpoints.py:218; apps/appeals/services/scoring.py:418 |
| appeal.status | apps/appeals/services/scoring.py:395; apps/appeals/services/scoring.py:411 |
| appeal.student | apps/appeals/services/creation.py:142; apps/appeals/services/scoring.py:437 |
| appeal.student_id | apps/appeals/views/shared/detail.py:36; apps/appeals/services/creation.py:126 |
| assignment.admin | apps/assignments/admin.py:23; apps/assignments/admin.py:26; apps/assignments/admin.py:28; apps/assignments/admin.py:38; apps/assignments/admin.py:40 |
| assignment.allow_late | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:257 |
| assignment.answers | apps/labs/lab_grading_service.py:57 |
| assignment.app | apps/assignments/apps.py:8 |
| assignment.assign_questions | apps/labs/models/assignment.py:60; apps/labs/models/assignment.py:62; apps/labs/views/student/endpoints.py:59; apps/labs/views/teacher/blocks.py:145 |
| assignment.assigned_at | apps/labs/views/student/endpoints.py:165 |
| assignment.assigned_questions | apps/labs/models/assignment.py:59; apps/labs/views/student/endpoints.py:53; apps/labs/views/student/endpoints.py:60; apps/labs/views/teacher/preview.py:43 |
| assignment.assigned_students | apps/organizations/management/commands/seed_ci_e2e_scenario.py:396; apps/organizations/management/commands/seed_ci_e2e_scenario.py:427; apps/assignments/services.py:235; apps/assignments/views/student/endpoints.py:61; apps/assignments/views/student/endpoints.py:108; apps/assignments/views/student/endpoints.py:183 |
| assignment.can_user_submit | apps/assignments/templatetags/assignment_tags.py:15; apps/assignments/views/student/endpoints.py:77; apps/assignments/views/student/endpoints.py:118; apps/assignments/views/student/endpoints.py:196 |
| assignment.choice | apps/assignments/models.py:34; apps/assignments/models.py:35; apps/assignments/models.py:36; apps/assignments/models.py:37; apps/assignments/models.py:38; apps/assignments/models.py:39 |
| assignment.course | apps/assignments/services.py:240; apps/assignments/views/student/endpoints.py:64; apps/assignments/views/student/endpoints.py:185; apps/assignments/views/shared/api.py:197; apps/assignments/views/shared/api.py:207; apps/assignments/views/shared/_helpers.py:58 |
| assignment.created_at | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:274 |
| assignment.deadline | apps/assignments/services.py:247; apps/assignments/views/teacher/crud.py:154; apps/assignments/views/teacher/crud.py:179 |
| assignment.deadline_badge_variant | apps/accounts/views/dashboard/student.py:52 |
| assignment.delete | apps/organizations/permissions.py:59; apps/organizations/default_roles.py:174; apps/organizations/default_roles.py:345; apps/organizations/default_roles.py:423; apps/organizations/default_roles.py:473; apps/assignments/views/teacher/endpoints.py:38 |
| assignment.description | apps/assignments/views/teacher/crud.py:152; apps/assignments/views/teacher/crud.py:177; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:252; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:277 |
| assignment.due_date | apps/assignments/models.py:367; apps/assignments/models.py:370; apps/assignments/models.py:372; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:257; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:275; apps/accounts/views/dashboard/student.py:51 |
| assignment.edit | apps/assignments/views/shared/api.py:194; apps/assignments/views/shared/api.py:198 |
| assignment.form | apps/assignments/forms.py:19; apps/assignments/forms.py:26; apps/assignments/forms.py:35; apps/assignments/forms.py:36; apps/assignments/forms.py:37; apps/assignments/forms.py:38 |
| assignment.get_user_attempts | apps/assignments/templatetags/assignment_tags.py:9; apps/assignments/views/student/endpoints.py:142 |
| assignment.id | apps/labs/course_dashboard.py:100; apps/assignments/views/student/endpoints.py:81; apps/assignments/views/student/endpoints.py:200; apps/assignments/views/teacher/crud.py:103; apps/assignments/views/teacher/crud.py:150; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:270 |
| assignment.lab | apps/labs/lab_submission_service.py:101; apps/labs/lab_submission_service.py:119; apps/labs/models/assignment.py:206; apps/labs/models/assignment.py:213; apps/labs/models/assignment.py:215; apps/labs/models/assignment.py:217 |
| assignment.max_attempts | apps/assignments/views/student/endpoints.py:78; apps/assignments/views/student/endpoints.py:197; apps/assignments/views/teacher/crud.py:155; apps/assignments/views/teacher/crud.py:180 |
| assignment.max_score | apps/assignments/views/teacher/crud.py:156; apps/assignments/views/teacher/crud.py:181; apps/accounts/views/dashboard/review.py:113 |
| assignment.message | apps/assignments/views/student/endpoints.py:145; apps/assignments/views/student/endpoints.py:149; apps/assignments/views/teacher/endpoints.py:198; apps/assignments/views/teacher/endpoints.py:199 |
| assignment.model | apps/assignments/models.py:55; apps/assignments/models.py:62; apps/assignments/models.py:65; apps/assignments/models.py:66; apps/assignments/models.py:67; apps/assignments/models.py:73 |
| assignment.needs_reassignment | apps/labs/models/assignment.py:61 |
| assignment.notification | apps/assignments/models.py:385; apps/assignments/models.py:386; apps/assignments/models.py:387; apps/assignments/models.py:388; apps/assignments/models.py:395; apps/assignments/models.py:398 |
| assignment.save | apps/assignments/views/teacher/crud.py:183 |
| assignment.start_date | apps/assignments/views/teacher/crud.py:153; apps/assignments/views/teacher/crud.py:178; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:255; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:274 |
| assignment.status | apps/assignments/services.py:231; apps/assignments/views/teacher/crud.py:95; apps/assignments/views/teacher/crud.py:157; apps/assignments/views/teacher/crud.py:174; apps/assignments/views/teacher/crud.py:182; apps/assignments/views/teacher/crud.py:208 |
| assignment.student | apps/labs/lab_submission_service.py:103; apps/labs/lab_submission_service.py:120; apps/labs/models/assignment.py:206; apps/labs/views/teacher/submissions.py:125; apps/labs/views/teacher/submissions.py:130; apps/labs/views/teacher/submissions.py:254 |
| assignment.student_id | core/media_views.py:197 |
| assignment.submission | apps/assignments/models.py:213; apps/assignments/models.py:214; apps/assignments/models.py:215; apps/assignments/models.py:216; apps/assignments/models.py:223; apps/assignments/models.py:230 |
| assignment.submissions | apps/labs/lab_grading_service.py:64; apps/labs/lab_submission_service.py:12; apps/labs/lab_submission_service.py:16; apps/assignments/views/student/endpoints.py:68; apps/assignments/views/student/endpoints.py:188; apps/assignments/views/teacher/endpoints.py:69 |
| assignment.title | apps/assignments/models.py:303; apps/assignments/views/teacher/crud.py:151; apps/assignments/views/teacher/crud.py:176; apps/accounts/views/_dashboard_helpers/results.py:143; apps/accounts/views/_dashboard_helpers/evaluated_review.py:166; apps/accounts/views/_dashboard_helpers/pending_review.py:184 |
| audit.0003 | apps/audit/models.py:22 |
| audit.apps | apps/audit/__init__.py:5 |
| audit.export | apps/organizations/permissions.py:94 |
| audit.log_action | apps/audit/public.py:3 |
| audit.models | apps/organizations/services.py:317; apps/organizations/views/org_admin/endpoints.py:30; apps/exams/services/final_center/history.py:80 |
| audit.public | apps/live_exam/views/host/game.py:15; apps/live_exam/views/host/session.py:11; apps/blog/views/moderator/post_management.py:24; apps/blog/views/author/posts.py:16; apps/accounts/middleware.py:340; apps/accounts/views/profile/post_handler.py:21 |
| audit.signals | apps/audit/apps.py:12 |
| audit.utils | apps/audit/tests.py:338; apps/audit/tests.py:353; apps/audit/tests.py:364; apps/audit/tests.py:383; apps/audit/tests.py:397 |
| audit.view | apps/organizations/permissions.py:93; apps/organizations/default_roles.py:31; apps/organizations/default_roles.py:55; apps/organizations/default_roles.py:79; apps/organizations/default_roles.py:99; apps/organizations/default_roles.py:120 |
| audit.views | apps/audit/public.py:8; apps/accounts/views/_helpers/rbac.py:416 |
| course.assignments | apps/assignments/course_dashboard.py:20; apps/assignments/course_dashboard.py:29 |
| course.create | apps/organizations/permissions.py:56; apps/organizations/default_roles.py:165; apps/organizations/default_roles.py:336; apps/organizations/middleware.py:242; apps/organizations/decorators.py:12; apps/organizations/templatetags/org_tags.py:40 |
| course.delete | apps/organizations/permissions.py:58; apps/labs/views/teacher/submissions.py:44; apps/assignments/views/teacher/endpoints.py:39; apps/projects/views/teacher/endpoints.py:39; apps/courses/views/teacher/crud.py:199 |
| course.edit | apps/organizations/permissions.py:57; apps/organizations/default_roles.py:166; apps/organizations/default_roles.py:337; apps/organizations/default_roles.py:419; apps/courses/views/teacher/membership.py:153; apps/courses/views/teacher/membership.py:224 |
| course.error | apps/courses/forms.py:113; apps/courses/forms.py:116; apps/courses/models/course.py:179 |
| course.get_status_display | apps/courses/views/teacher/crud.py:238 |
| course.id | apps/courses/views/student/courses.py:51; apps/courses/views/teacher/topics.py:68; apps/courses/views/teacher/topics.py:71; apps/courses/views/teacher/topics.py:93; apps/courses/views/teacher/topics.py:123; apps/courses/views/teacher/topics.py:126 |
| course.label | apps/courses/forms.py:47 |
| course.labs | apps/labs/course_dashboard.py:21; apps/labs/course_dashboard.py:38 |
| course.memberships | apps/assignments/views/shared/api.py:52; apps/courses/services.py:251; apps/courses/services.py:270; apps/courses/models/course.py:34; apps/courses/views/shared/dashboard.py:153; apps/courses/views/shared/dashboard.py:287 |
| course.organization | apps/exams/management/commands/_seed_helpers/courses.py:24; apps/exams/domain/exam_definition.py:252; core/media_views.py:199; core/media_views.py:294 |
| course.organization_id | apps/exams/management/commands/_seed_helpers/courses.py:23 |
| course.owner | apps/labs/views/teacher/crud.py:37; apps/assignments/views/teacher/crud.py:55; apps/projects/views/teacher/crud.py:54; apps/task_submission_core/access.py:8; apps/courses/views/teacher/membership.py:92; apps/accounts/services/statistics_selectors/org_admin.py:169 |
| course.owner_id | apps/labs/models/lab.py:224; apps/courses/views/shared/dashboard.py:87; apps/courses/views/shared/dashboard.py:109; apps/accounts/services/statistics_selectors/org_admin.py:169; apps/exams/views/teacher/exams/_shared.py:275 |
| course.placeholder | apps/courses/forms.py:48; apps/courses/forms.py:84; apps/courses/forms.py:91 |
| course.projects | apps/projects/course_dashboard.py:19; apps/projects/course_dashboard.py:28 |
| course.resources | apps/courses/models/course.py:35; apps/courses/views/shared/dashboard.py:147 |
| course.save | apps/courses/services.py:333; apps/courses/views/teacher/crud.py:235; apps/exams/management/commands/_seed_helpers/courses.py:33 |
| course.settings | apps/exams/management/commands/_seed_helpers/courses.py:29; apps/exams/management/commands/_seed_helpers/courses.py:30 |
| course.slug | apps/exams/management/commands/_seed_helpers/courses.py:72; apps/exams/management/commands/_seed_helpers/courses.py:80 |
| course.status | apps/courses/services.py:332; apps/courses/views/teacher/crud.py:234; apps/exams/management/commands/_seed_helpers/courses.py:26; apps/exams/management/commands/_seed_helpers/courses.py:27 |
| course.title | apps/labs/models/lab.py:143; apps/assignments/models.py:153; apps/projects/models.py:68; apps/courses/models/content.py:63; apps/courses/models/enrollment.py:77; apps/courses/models/enrollment.py:141 |
| course.topics | apps/courses/models/course.py:33; apps/courses/views/shared/dashboard.py:146 |
| course.view | apps/organizations/permissions.py:55; apps/organizations/default_roles.py:47; apps/organizations/default_roles.py:71; apps/organizations/default_roles.py:94; apps/organizations/default_roles.py:164; apps/organizations/default_roles.py:187 |
| courses.Course | apps/labs/models/lab.py:35; apps/registrar/models/academic.py:231; apps/registrar/models/academic.py:248; apps/exams/domain/exam_definition.py:123 |
| courses.com | apps/organizations/management/commands/create_sample_orgs.py:150; apps/organizations/management/commands/create_sample_orgs.py:153 |
| courses.count | apps/accounts/services/statistics_selectors/superadmin.py:52; apps/accounts/services/statistics_selectors/org_admin.py:59 |
| courses.dashboard_sources | apps/courses/public.py:3; apps/courses/public.py:8 |
| courses.filter | apps/accounts/views/dashboard/student.py:123; apps/accounts/services/statistics_selectors/superadmin.py:49; apps/accounts/services/statistics_selectors/superadmin.py:51; apps/accounts/services/statistics_selectors/teacher.py:36; apps/accounts/services/statistics_selectors/teacher.py:38; apps/accounts/services/statistics_selectors/org_admin.py:56 |
| courses.form | apps/courses/forms.py:47; apps/courses/forms.py:48; apps/courses/forms.py:84; apps/courses/forms.py:91; apps/courses/forms.py:113; apps/courses/forms.py:116 |
| courses.forms | apps/courses/views/shared/dashboard.py:22; apps/courses/views/teacher/topics.py:20; apps/courses/views/teacher/resources.py:18; apps/courses/views/teacher/crud.py:25 |
| courses.model | apps/courses/models/course.py:179 |
| courses.models | apps/labs/lab_access.py:3; apps/labs/models/lab.py:185; apps/labs/models/lab.py:227; apps/labs/views/shared/api.py:11; apps/labs/views/shared/_helpers.py:11; apps/labs/views/teacher/preview.py:11 |
| courses.partial | apps/courses/templates/courses/partials/_create_course_modal_form.html 2.py:20; apps/courses/templates/courses/partials/_create_course_modal_form.html 2.py:24; apps/courses/templates/courses/partials/_topic_edit_modal.html 2.py:10; apps/courses/templates/courses/partials/_topic_edit_modal.html 2.py:12; apps/courses/templates/courses/partials/_topic_edit_modal.html 2.py:26; apps/courses/templates/courses/partials/_topic_edit_modal.html 2.py:36 |
| courses.py | apps/courses/views/teacher/membership.py:3 |
| courses.select_related | apps/accounts/services/statistics_selectors/org_admin.py:168 |
| courses.values | apps/accounts/services/statistics_selectors/teacher.py:39 |
| courses.values_list | apps/accounts/services/statistics_selectors/org_admin.py:62 |
| courses.view | apps/courses/views/shared/dashboard.py:90; apps/courses/views/shared/_helpers.py:52; apps/courses/views/shared/_helpers.py:86; apps/courses/views/shared/_helpers.py:99; apps/courses/views/teacher/topics.py:46; apps/courses/views/teacher/topics.py:67 |
| exam._meta | apps/exams/services/duplication.py:67 |
| exam.access_code | apps/courses/views/shared/dashboard.py:253; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:201; apps/accounts/views/dashboard/student.py:98; apps/exams/views/student/lists.py:293; apps/exams/views/student/lists.py:295 |
| exam.allowed_groups | apps/organizations/management/commands/seed_ci_e2e_scenario.py:417; apps/exams/management/commands/seed_demo_hierarchy.py:143; apps/exams/management/commands/seed_final_exam_demo.py:87; apps/exams/management/commands/seed_group_demo_data.py:149; apps/exams/views/exam_center/statistics.py:126; apps/exams/services/duplication.py:86 |
| exam.allowed_users | apps/exams/management/commands/seed_final_exam_demo.py:88; apps/exams/management/commands/seed_group_demo_data.py:150; apps/exams/services/duplication.py:87; apps/exams/services/access_policy.py:29; apps/notifications/services/events.py:385; core/media_views.py:274 |
| exam.archived_at | apps/exams/views/teacher/exams/actions.py:153 |
| exam.attempts | apps/exams/views/teacher/results/_attempt_views.py:75; apps/exams/views/teacher/results/_helpers.py:264; apps/exams/views/teacher/results/_helpers.py:345; apps/exams/views/teacher/results/_helpers.py:370; apps/exams/views/teacher/results/_results_views.py:156; apps/exams/services/attempts.py:178 |
| exam.attempts_left_for | apps/exams/views/student/lists.py:290; apps/exams/views/student/results.py:313; apps/exams/views/teacher/results/_results_views.py:212; apps/exams/views/teacher/exams/attempt_grants.py:86 |
| exam.author | apps/live_exam/views/host/session.py:36; apps/accounts/views/_dashboard_helpers/evaluated_review.py:128; apps/accounts/views/_dashboard_helpers/pending_review.py:113; apps/exams/views/exam_center/statistics.py:129; apps/exams/views/student/attempts.py:438; apps/exams/views/teacher/results/_attempt_views.py:185 |
| exam.author_id | apps/exams/views/exam_center/statistics.py:129; apps/exams/views/teacher/exams/actions.py:97; apps/exams/views/teacher/exams/actions.py:149; apps/exams/views/teacher/exams/_shared.py:209 |
| exam.can_user_see | apps/courses/views/shared/dashboard.py:242; apps/exams/views/student/lists.py:279 |
| exam.can_user_start | apps/courses/views/shared/dashboard.py:250; apps/accounts/views/dashboard/student.py:94; apps/exams/views/student/final_center.py:239; apps/exams/views/student/lists.py:292; apps/exams/views/student/results.py:310; apps/exams/views/student/attempts.py:295 |
| exam.choice | apps/exams/domain/exam_definition.py:24; apps/exams/domain/exam_definition.py:25; apps/exams/domain/exam_definition.py:26; apps/exams/domain/exam_definition.py:29; apps/exams/domain/exam_definition.py:30; apps/exams/domain/exam_definition.py:31 |
| exam.course | apps/courses/views/teacher/membership.py:403; apps/courses/views/teacher/membership.py:438; apps/accounts/views/_dashboard_helpers/evaluated_review.py:98; apps/accounts/views/_dashboard_helpers/pending_review.py:93; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:140; apps/accounts/views/_dashboard_helpers/pending_answers.py:110 |
| exam.course_id | apps/exams/management/commands/_seed_helpers/exams.py:37; apps/exams/views/student/results.py:54; apps/exams/views/student/results.py:55; apps/exams/views/student/results.py:292; apps/exams/views/student/results.py:293; apps/notifications/services/events.py:388 |
| exam.create | apps/organizations/permissions.py:71; apps/organizations/default_roles.py:170; apps/organizations/default_roles.py:341; apps/organizations/default_roles.py:516; apps/ai_assistant/context_builder.py:254; apps/ai_assistant/context_builder.py:330 |
| exam.created_at | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:232 |
| exam.default_question_points | apps/exams/views/student/results.py:302; apps/exams/views/teacher/question_bank/_views_misc.py:251; apps/exams/views/teacher/question_bank/_views_misc.py:259 |
| exam.default_question_time_seconds | apps/exams/domain/question_bank/exam_question.py:309; apps/exams/domain/question_bank/exam_question.py:310 |
| exam.delete | apps/organizations/permissions.py:75; apps/organizations/default_roles.py:173; apps/organizations/default_roles.py:344; apps/assignments/views/teacher/endpoints.py:40; apps/projects/views/teacher/endpoints.py:40; apps/exams/views/teacher/results/_attempt_views.py:61 |
| exam.description | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:139; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:235 |
| exam.edit | apps/organizations/permissions.py:72; apps/organizations/default_roles.py:171; apps/organizations/default_roles.py:342; apps/organizations/default_roles.py:516; apps/exams/management/commands/_seed_helpers/users.py:113; apps/exams/views/teacher/supervision/_shared.py:40 |
| exam.enable_paint | apps/exams/forms/question.py:180; apps/exams/management/commands/_seed_helpers/exams.py:28; apps/exams/management/commands/_seed_helpers/exams.py:29; apps/exams/views/teacher/question_bank/_views_create.py:98; apps/exams/views/teacher/questions/_shared.py:121 |
| exam.end_datetime | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:188; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:198; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:218; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:233 |
| exam.error | apps/exams/forms/exam.py:536; apps/exams/forms/exam.py:546; apps/exams/forms/exam.py:605; apps/exams/forms/exam.py:615; apps/exams/forms/exam.py:621; apps/exams/domain/exam_definition.py:258 |
| exam.exam_type | apps/accounts/views/_dashboard_helpers/results.py:73; apps/accounts/views/_dashboard_helpers/evaluated_review.py:100; apps/accounts/views/_dashboard_helpers/pending_review.py:124; apps/accounts/views/_dashboard_helpers/pending_answers.py:121; apps/accounts/views/dashboard/results.py:78; apps/exams/management/commands/_seed_helpers/exams.py:25 |
| exam.exam_type_extended | apps/exams/management/commands/seed_demo_hierarchy.py:292; apps/exams/management/commands/seed_demo_hierarchy.py:294; apps/exams/management/commands/seed_final_exam_demo.py:137; apps/exams/views/exam_center/statistics.py:141; apps/exams/views/student/lists.py:186; apps/exams/views/student/lists.py:187 |
| exam.field | apps/exams/domain/exam_definition.py:50; apps/exams/domain/exam_definition.py:54; apps/exams/domain/exam_definition.py:58; apps/exams/domain/exam_definition.py:61; apps/exams/domain/exam_definition.py:67; apps/exams/domain/exam_definition.py:73 |
| exam.get_exam_type_display | apps/accounts/views/_dashboard_helpers/results.py:100; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:195; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:225; apps/accounts/views/_dashboard_helpers/pending_answers.py:125; apps/exams/views/teacher/statistics.py:402 |
| exam.get_exam_type_extended_display | apps/exams/views/exam_center/statistics.py:141 |
| exam.help | apps/exams/forms/exam.py:304; apps/exams/forms/exam.py:306; apps/exams/forms/exam.py:310; apps/exams/domain/exam_definition.py:70; apps/exams/domain/exam_definition.py:76; apps/exams/domain/exam_definition.py:81 |
| exam.host | apps/organizations/permissions.py:74; apps/organizations/default_roles.py:172; apps/organizations/default_roles.py:343; apps/organizations/default_roles.py:516; apps/live_exam/views/results.py:29; apps/live_exam/views/host/_shared.py:23 |
| exam.id | apps/courses/views/shared/dashboard.py:55; apps/courses/views/shared/dashboard.py:230; apps/courses/views/shared/dashboard.py:244; apps/appeals/views/student/endpoints.py:59; apps/exams/views/student/lists.py:250; apps/exams/views/student/lists.py:282 |
| exam.is_active | apps/live_exam/views/host/session.py:41; apps/courses/views/teacher/membership.py:406; apps/exams/management/commands/seed_demo_hierarchy.py:292; apps/exams/management/commands/seed_demo_hierarchy.py:293; apps/exams/management/commands/seed_final_exam_demo.py:135; apps/exams/management/commands/_seed_helpers/exams.py:31 |
| exam.is_after_end | apps/courses/views/shared/dashboard.py:251; apps/exams/views/student/lists.py:277; apps/exams/services/attempts.py:276 |
| exam.is_archived | apps/exams/views/teacher/exams/actions.py:152; apps/exams/views/teacher/exams/actions.py:153; apps/exams/views/teacher/exams/actions.py:164; apps/exams/views/teacher/exams/actions.py:165; apps/exams/views/teacher/exams/actions.py:185 |
| exam.is_before_start | apps/courses/views/shared/dashboard.py:251; apps/exams/services/attempts.py:276 |
| exam.is_public | apps/exams/management/commands/_seed_helpers/exams.py:34; apps/exams/management/commands/_seed_helpers/exams.py:35; apps/exams/views/student/lists.py:297 |
| exam.label | apps/exams/forms/exam.py:132; apps/exams/forms/exam.py:278; apps/exams/forms/exam.py:279; apps/exams/forms/exam.py:280; apps/exams/forms/exam.py:281; apps/exams/forms/exam.py:282 |
| exam.language_variants | apps/exams/forms/question.py:189; apps/exams/forms/question.py:210; apps/exams/views/teacher/languages.py:42; apps/exams/views/teacher/languages.py:114; apps/exams/services/language_variants.py:32; apps/exams/services/language_variants.py:38 |
| exam.lifecycle_status | apps/exams/services/teacher_dashboard.py:60 |
| exam.manage | apps/organizations/permissions.py:73; apps/organizations/default_roles.py:516; apps/live_exam/views/results.py:26; apps/live_exam/views/results.py:29; apps/live_exam/views/host/_shared.py:24; apps/live_exam/views/host/_shared.py:38 |
| exam.max_attempts_per_user | apps/courses/views/shared/dashboard.py:248; apps/exams/views/student/attempts.py:302; apps/exams/views/shared/access.py:73; apps/exams/views/shared/access.py:82; apps/exams/services/attempts.py:194; apps/exams/services/attempts.py:275 |
| exam.meta | apps/exams/domain/exam_definition.py:222; apps/exams/domain/exam_definition.py:223 |
| exam.organization | apps/live_exam/views/host/game.py:58; apps/live_exam/views/host/game.py:172; apps/live_exam/views/host/game.py:196; apps/live_exam/views/host/game.py:254; apps/live_exam/views/host/game.py:313; apps/live_exam/views/host/game.py:352 |
| exam.organization_id | apps/live_exam/views/results.py:32; apps/exams/export_registry.py:30; apps/exams/views/student/final_center.py:260; apps/exams/services/final_center/sessions.py:73 |
| exam.pk | apps/live_exam/views/host/session.py:83; apps/exams/views/teacher/results/_results_views.py:366; apps/exams/views/teacher/exams/actions.py:113; apps/exams/views/teacher/exams/actions.py:171; apps/exams/views/teacher/exams/actions.py:177; apps/exams/views/teacher/questions/crud.py:79 |
| exam.placeholder | apps/exams/forms/exam.py:133; apps/exams/forms/exam.py:163; apps/exams/forms/exam.py:170; apps/exams/forms/exam.py:204; apps/exams/forms/exam.py:215; apps/exams/forms/exam.py:237 |
| exam.question_blocks | apps/exams/views/teacher/statistics.py:320; apps/exams/views/teacher/question_library/_shared.py:186; apps/exams/views/teacher/question_bank/_views_misc.py:104; apps/exams/views/teacher/question_bank/_views_create.py:84; apps/exams/views/teacher/questions/_shared.py:116; apps/exams/services/randomizer.py:311 |
| exam.questions | apps/exams/management/commands/seed_demo_hierarchy.py:299; apps/exams/management/commands/seed_final_exam_demo.py:160; apps/exams/views/student/final_center.py:245; apps/exams/views/student/results.py:302; apps/exams/views/student/results.py:304; apps/exams/views/student/attempts.py:309 |
| exam.random_question_count | apps/exams/management/commands/seed_final_exam_demo.py:141; apps/exams/views/teacher/question_bank/_views_misc.py:248; apps/exams/views/teacher/question_bank/_views_create.py:136 |
| exam.results_hidden_from_students | apps/accounts/views/dashboard/results.py:68; apps/exams/views/teacher/exams/actions.py:65; apps/exams/views/teacher/exams/actions.py:68 |
| exam.save | apps/courses/views/teacher/membership.py:404; apps/courses/views/teacher/membership.py:439; apps/exams/management/commands/seed_demo_hierarchy.py:295; apps/exams/management/commands/seed_final_exam_demo.py:146; apps/exams/management/commands/_seed_helpers/exams.py:41; apps/exams/views/teacher/exams/actions.py:41 |
| exam.settings | apps/exams/views/teacher/statistics.py:133; apps/exams/services/duplication.py:73; apps/exams/services/difficulty.py:177; apps/exams/services/difficulty.py:187 |
| exam.slug | apps/live_exam/views/results.py:84; apps/live_exam/views/results.py:85; apps/live_exam/views/host/session.py:43; apps/live_exam/views/host/session.py:57; apps/accounts/views/_dashboard_helpers/results.py:114; apps/accounts/views/_dashboard_helpers/evaluated_review.py:134 |
| exam.start_datetime | apps/registrar/schedule.py:209; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:186; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:197; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:217; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:232 |
| exam.supervision_config | apps/exams/views/teacher/supervision/monitor.py:302; apps/exams/views/teacher/exams/list_detail.py:95; apps/exams/services/supervision/_shared.py:35 |
| exam.title | apps/live_exam/views/results.py:323; apps/ai_assistant/context_builder.py:354; apps/accounts/views/_dashboard_helpers/results.py:99; apps/accounts/views/_dashboard_helpers/evaluated_review.py:123; apps/accounts/views/_dashboard_helpers/pending_review.py:114; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:138 |
| exam.total_duration_minutes | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:196; apps/exams/management/commands/seed_final_exam_demo.py:139; apps/exams/views/student/attempts.py:329; apps/exams/views/student/attempts.py:330; apps/exams/views/student/attempts.py:520; apps/exams/views/student/attempts.py:522 |
| exam.user_attempt_count | apps/exams/views/student/lists.py:306 |
| exam.view | apps/organizations/permissions.py:70; apps/organizations/default_roles.py:169; apps/organizations/default_roles.py:189; apps/organizations/default_roles.py:207; apps/organizations/default_roles.py:224; apps/organizations/default_roles.py:241 |
| exams.BankQuestion | apps/exams/domain/question_bank/exam_question.py:181; apps/exams/domain/question_bank/bank_question.py:143 |
| exams.CodingExamQuestion | apps/exams/domain/coding.py:125; apps/exams/domain/coding.py:214 |
| exams.CodingSubmission | apps/exams/domain/coding.py:292 |
| exams.Exam | apps/appeals/models.py:39; apps/exams/domain/final_center.py:309; apps/exams/domain/final_center.py:467; apps/exams/domain/coding.py:200; apps/exams/domain/exam_definition.py:314; apps/exams/domain/student_access.py:22 |
| exams.ExamAnswer | apps/appeals/models.py:123; apps/exams/domain/attempts.py:360 |
| exams.ExamAttempt | apps/appeals/models.py:32; apps/appeals/models.py:198; apps/exams/domain/final_center.py:479; apps/exams/domain/coding.py:206; apps/exams/domain/supervision.py:245; apps/exams/domain/attempts.py:317 |
| exams.ExamLanguageVariant | apps/exams/domain/attempts.py:53; apps/exams/domain/question_bank/exam_question.py:198 |
| exams.ExamQuestion | apps/appeals/models.py:116; apps/appeals/models.py:204; apps/exams/domain/coding.py:32; apps/exams/domain/attempts.py:318; apps/exams/domain/question_bank/exam_question.py:390 |
| exams.ExamQuestionOption | apps/exams/domain/attempts.py:320 |
| exams.ExamRoom | apps/exams/domain/final_center.py:201; apps/exams/domain/final_center.py:316 |
| exams.ExamRoomSession | apps/exams/domain/final_center.py:459 |
| exams.QuestionBank | apps/exams/domain/submission_inbox.py:125; apps/exams/domain/question_bank/exam_question.py:169; apps/exams/domain/question_bank/bank_question.py:41 |
| exams.QuestionBlock | apps/exams/domain/question_bank/exam_question.py:161 |
| exams.StudentGroup | apps/exams/domain/exam_definition.py:186; apps/exams/domain/submission_inbox.py:66 |
| exams.all | apps/exams/views/teacher/results/_attempt_views.py:396 |
| exams.constants | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:13; apps/exams/public.py:10; apps/exams/templatetags/exams_ui.py:11; apps/exams/forms/bank_question.py:14; apps/exams/forms/question.py:10; apps/exams/views/student/lists.py:9 |
| exams.count | apps/accounts/services/statistics_selectors/org_admin.py:76 |
| exams.dashboard | apps/exams/services/teacher_dashboard.py:27; apps/exams/services/teacher_dashboard.py:28; apps/exams/services/teacher_dashboard.py:29; apps/exams/services/teacher_dashboard.py:30; apps/exams/services/teacher_dashboard.py:33; apps/exams/services/teacher_dashboard.py:34 |
| exams.distinct | apps/registrar/schedule.py:208 |
| exams.domain | apps/ai_assistant/context_builder.py:325; apps/ai_assistant/context_builder.py:326; apps/exams/public.py:17; apps/exams/public.py:20; apps/exams/models.py:4; apps/exams/models.py:9 |
| exams.expire_stale_resumed_attempts | apps/exams/tasks.py:19 |
| exams.export | apps/exams/export_registry.py:50; apps/exams/export_registry.py:54; apps/exams/export_registry.py:57; apps/exams/export_registry.py:60; apps/exams/views/teacher/question_library/export.py:73; apps/exams/views/teacher/question_library/export.py:77 |
| exams.export_registry | apps/exams/tasks.py:278 |
| exams.features | apps/exams/public.py:24; apps/exams/consumers.py:19; apps/exams/forms/exam.py:12; apps/exams/views/student/coding.py:16; apps/exams/views/student/attempts.py:16; apps/exams/views/shared/tenant.py:3 |
| exams.filter | apps/accounts/views/dashboard/student.py:90; apps/accounts/services/statistics_selectors/teacher.py:66; apps/accounts/services/statistics_selectors/teacher.py:68; apps/accounts/services/statistics_selectors/org_admin.py:73; apps/accounts/services/statistics_selectors/org_admin.py:75; apps/exams/templatetags/exam_filters.py:40 |
| exams.final_center | apps/exams/forms/final_center.py:30; apps/exams/forms/final_center.py:76; apps/exams/forms/final_center.py:80; apps/exams/forms/final_center.py:91; apps/exams/forms/final_center.py:96; apps/exams/forms/final_center.py:97 |
| exams.form | apps/exams/forms/exam.py:30; apps/exams/forms/exam.py:35; apps/exams/forms/exam.py:40; apps/exams/forms/exam.py:45; apps/exams/forms/exam.py:50; apps/exams/forms/exam.py:55 |
| exams.forms | apps/accounts/views/superadmin/exam_rooms.py:21; apps/exams/public.py:27; apps/exams/forms/__init__.py:6; apps/exams/views/exam_center/sessions.py:11; apps/exams/views/teacher/groups.py:10; apps/exams/views/teacher/question_library/questions.py:11 |
| exams.message | apps/exams/views/teacher/exams/list_detail.py:221; apps/exams/views/teacher/exams/list_detail.py:223; apps/exams/views/teacher/exams/actions.py:71; apps/exams/views/teacher/exams/actions.py:76; apps/exams/views/teacher/exams/actions.py:184; apps/exams/views/teacher/exams/actions.py:186 |
| exams.model | apps/exams/domain/final_center.py:106; apps/exams/domain/final_center.py:110; apps/exams/domain/final_center.py:114; apps/exams/domain/final_center.py:115; apps/exams/domain/final_center.py:120; apps/exams/domain/final_center.py:125 |
| exams.models | apps/live_exam/models.py:7; apps/live_exam/transport.py:217; apps/live_exam/transport.py:261; apps/live_exam/scoring.py:14; apps/live_exam/views/results.py:18; apps/live_exam/views/host/session.py:12 |
| exams.navigation | apps/exams/views/student/_helpers.py:6; apps/exams/services/attempts.py:16; apps/exams/services/attempts.py:17 |
| exams.notification | apps/exams/services/question_submission.py:301; apps/exams/services/question_submission.py:306; apps/exams/services/question_submission.py:315; apps/exams/services/question_submission.py:338; apps/exams/services/question_submission.py:343; apps/exams/services/question_submission.py:348 |
| exams.notify_upcoming_final_exams | apps/exams/tasks.py:44 |
| exams.permission | apps/exams/views/teacher/exams/list_detail.py:137; apps/exams/views/teacher/exams/_shared.py:115; apps/exams/views/teacher/exams/_shared.py:197; apps/exams/views/teacher/exams/_shared.py:210 |
| exams.public | apps/live_exam/views/results.py:19; apps/live_exam/views/host/session.py:13; apps/courses/views/shared/dashboard.py:25; apps/courses/views/teacher/membership.py:32; apps/ai_assistant/gemini_client.py:71; apps/accounts/views/_helpers/tenant.py:10 |
| exams.question_bank | apps/exams/views/teacher/question_bank/_views_misc.py:72 |
| exams.run_ai_generation_job | apps/exams/tasks.py:161 |
| exams.run_export_job | apps/exams/tasks.py:265 |
| exams.run_text_extraction_job | apps/exams/tasks.py:65; apps/exams/domain/import_jobs.py:5 |
| exams.score_adjustments | apps/appeals/public.py:4; apps/exams/public.py:4 |
| exams.service | apps/exams/views/student/attempts.py:301; apps/exams/views/shared/access.py:72; apps/exams/views/shared/access.py:81; apps/exams/views/teacher/submission_inbox.py:397; apps/exams/views/teacher/supervision/_shared.py:43; apps/exams/services/question_submission.py:85 |
| exams.services | apps/accounts/models.py:366; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:160; apps/exams/public.py:30; apps/exams/public.py:40; apps/exams/public.py:41; apps/exams/public.py:44 |
| exams.supervision | apps/exams/consumers.py:21 |
| exams.task | apps/exams/tasks.py:140; apps/exams/tasks.py:225 |
| exams.tasks | apps/exams/views/teacher/extract_jobs.py:21; apps/exams/views/teacher/extract_jobs.py:81; apps/exams/views/teacher/extract_jobs.py:199 |
| exams.teacher | apps/exams/views/teacher/results/_helpers.py:213; apps/exams/views/teacher/results/_helpers.py:223; apps/exams/views/teacher/results/_helpers.py:230; apps/exams/views/teacher/results/_helpers.py:238 |
| exams.teacher_results | apps/exams/views/teacher/results/_helpers.py:16 |
| exams.template | apps/exams/templates/exams/student/student_exam_history.html 2.py:158; apps/exams/templates/exams/student/student_exam_history.html 2.py:160; apps/exams/templates/exams/student/student_exam_history.html 2.py:162; apps/exams/templates/exams/student/student_exam_history.html 2.py:251; apps/exams/templates/exams/teacher/teacher_check_attempt.html 2.py:4; apps/exams/templates/exams/teacher/teacher_check_attempt.html 2.py:14 |
| exams.type | apps/exams/views/student/lists.py:194; apps/exams/views/student/lists.py:195; apps/exams/views/student/lists.py:196; apps/exams/views/student/lists.py:197; apps/exams/views/student/lists.py:198; apps/exams/views/student/lists.py:199 |
| exams.validator | apps/exams/validators.py:34; apps/exams/validators.py:37; apps/exams/validators.py:44; apps/exams/validators.py:56; apps/exams/validators.py:67 |
| exams.validators | apps/exams/views/student/attempts.py:25; apps/exams/domain/attempts.py:9 |
| exams.values | apps/accounts/services/statistics_selectors/teacher.py:212; apps/accounts/services/statistics_selectors/org_admin.py:155; apps/accounts/services/statistics_selectors/org_admin.py:200 |
| exams.values_list | apps/accounts/services/statistics_selectors/teacher.py:69 |
| exams.view | apps/exams/views/student/final_center.py:71; apps/exams/views/student/final_center.py:321; apps/exams/views/student/lists.py:296; apps/exams/views/student/lists.py:298; apps/exams/views/student/lists.py:300; apps/exams/views/student/lists.py:420 |
| exams.views | apps/appeals/views/student/endpoints.py:13; apps/exams/public.py:71; apps/exams/export_registry.py:26; apps/exams/export_registry.py:27; apps/exams/tasks.py:173; apps/exams/tasks.py:232 |
| exams.wizard | apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html 2.py:20; apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html 2.py:28; apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html 2.py:32; apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html 2.py:36; apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html 2.py:40; apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html 2.py:45 |
| grade.input | apps/organizations/permissions.py:65; apps/organizations/default_roles.py:152; apps/organizations/default_roles.py:168; apps/organizations/default_roles.py:206; apps/organizations/default_roles.py:339; apps/organizations/default_roles.py:421 |
| grade.label | apps/projects/forms.py:127; apps/projects/forms.py:128; apps/projects/forms.py:129 |
| grade.override | apps/organizations/permissions.py:67 |
| grade.placeholder | apps/projects/forms.py:114; apps/projects/forms.py:121 |
| grade.publish | apps/organizations/permissions.py:66; apps/organizations/default_roles.py:50; apps/organizations/default_roles.py:74; apps/exams/management/commands/seed_demo_hierarchy.py:51 |
| grade.view | apps/organizations/permissions.py:64; apps/organizations/default_roles.py:49; apps/organizations/default_roles.py:73; apps/organizations/default_roles.py:96; apps/organizations/default_roles.py:151; apps/organizations/default_roles.py:167 |
| lab.allow_file_upload | apps/labs/views/teacher/crud.py:127; apps/labs/views/teacher/crud.py:161 |
| lab.allow_late_submission | apps/labs/views/student/submissions.py:116; apps/labs/views/teacher/crud.py:125; apps/labs/views/teacher/crud.py:159; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:310 |
| lab.allow_link_submission | apps/labs/views/teacher/crud.py:128; apps/labs/views/teacher/crud.py:162 |
| lab.allowed_extensions | apps/labs/views/student/submissions.py:72; apps/labs/views/teacher/questions.py:40; apps/labs/views/teacher/crud.py:130; apps/labs/views/teacher/crud.py:164; apps/labs/views/teacher/crud.py:170 |
| lab.allowed_groups | apps/labs/course_dashboard.py:62; apps/labs/course_dashboard.py:63; apps/labs/views/teacher/crud.py:109; apps/labs/views/teacher/crud.py:110; apps/labs/views/teacher/crud.py:166; apps/accounts/views/_dashboard_helpers/cheap_counts.py:108 |
| lab.allowed_students | apps/labs/course_dashboard.py:58; apps/labs/views/teacher/crud.py:80; apps/labs/views/teacher/crud.py:113; apps/labs/views/teacher/crud.py:182; apps/accounts/views/_dashboard_helpers/cheap_counts.py:107; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:289 |
| lab.assignments | apps/labs/views/teacher/blocks.py:144 |
| lab.blocks | apps/labs/models/assignment.py:73; apps/labs/models/assignment.py:114; apps/labs/views/teacher/blocks.py:30; apps/labs/views/teacher/blocks.py:60 |
| lab.can_student_access | apps/labs/lab_access.py:14; apps/labs/models/assignment.py:52 |
| lab.can_teacher_access | apps/labs/lab_access.py:18 |
| lab.course | apps/labs/lab_access.py:43; apps/labs/views/student/submissions.py:139; apps/labs/views/student/endpoints.py:125; apps/labs/views/student/endpoints.py:133; apps/labs/views/shared/_helpers.py:106; apps/labs/views/teacher/preview.py:24 |
| lab.course_id | apps/accounts/views/_dashboard_helpers/cheap_counts.py:114; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:296 |
| lab.created_at | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:325 |
| lab.created_by | apps/labs/views/teacher/preview.py:22; apps/labs/views/teacher/questions.py:32; apps/labs/views/teacher/questions.py:73; apps/labs/views/teacher/questions.py:104; apps/labs/views/teacher/questions.py:128; apps/labs/views/teacher/blocks.py:26 |
| lab.delete | apps/organizations/permissions.py:61; apps/organizations/default_roles.py:176; apps/organizations/default_roles.py:347; apps/organizations/default_roles.py:425; apps/organizations/default_roles.py:475; apps/labs/views/teacher/submissions.py:44 |
| lab.description | apps/labs/views/teacher/crud.py:118; apps/labs/views/teacher/crud.py:148; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:305; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:328 |
| lab.end_datetime | apps/labs/lab_submission_service.py:22; apps/labs/lab_submission_service.py:23; apps/labs/views/teacher/crud.py:120; apps/labs/views/teacher/crud.py:150; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:310; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:326 |
| lab.get_allowed_groups_list | apps/notifications/services/events.py:401 |
| lab.id | apps/labs/course_dashboard.py:42; apps/labs/course_dashboard.py:92; apps/labs/views/student/endpoints.py:107; apps/labs/views/teacher/blocks.py:148; apps/labs/views/teacher/submissions.py:195; apps/labs/views/teacher/submissions.py:206 |
| lab.is_open | apps/labs/course_dashboard.py:106 |
| lab.late_penalty_percent | apps/labs/views/teacher/crud.py:126; apps/labs/views/teacher/crud.py:160 |
| lab.max_attempts | apps/labs/course_dashboard.py:105; apps/labs/views/student/submissions.py:123; apps/labs/views/student/endpoints.py:78; apps/labs/views/student/endpoints.py:136; apps/labs/views/teacher/crud.py:156 |
| lab.max_file_size_mb | apps/labs/views/student/submissions.py:76; apps/labs/views/teacher/questions.py:44; apps/labs/views/teacher/crud.py:129; apps/labs/views/teacher/crud.py:163; apps/labs/views/teacher/crud.py:174 |
| lab.max_score | apps/labs/views/teacher/submissions.py:315; apps/labs/views/teacher/crud.py:121; apps/labs/views/teacher/crud.py:151 |
| lab.questions_per_student | apps/labs/models/assignment.py:88; apps/labs/models/assignment.py:89; apps/labs/models/assignment.py:127; apps/labs/models/assignment.py:128; apps/labs/views/teacher/blocks.py:140; apps/labs/views/teacher/crud.py:124 |
| lab.save | apps/labs/views/teacher/blocks.py:141; apps/labs/views/teacher/crud.py:84; apps/labs/views/teacher/crud.py:178; apps/labs/views/teacher/crud.py:239 |
| lab.start_datetime | apps/labs/lab_submission_service.py:22; apps/labs/lab_submission_service.py:23; apps/labs/views/student/endpoints.py:165; apps/labs/views/teacher/crud.py:119; apps/labs/views/teacher/crud.py:149; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:308 |
| lab.status | apps/labs/lab_submission_service.py:23; apps/labs/lab_submission_service.py:25; apps/labs/views/teacher/crud.py:123; apps/labs/views/teacher/crud.py:140; apps/labs/views/teacher/crud.py:152; apps/labs/views/teacher/crud.py:185 |
| lab.teacher_files | apps/labs/views/teacher/crud.py:83; apps/labs/views/teacher/crud.py:132; apps/labs/views/teacher/crud.py:176 |
| lab.teacher_instructions | apps/labs/views/teacher/crud.py:131; apps/labs/views/teacher/crud.py:165 |
| lab.title | apps/labs/models/assignment.py:45; apps/labs/models/lab.py:271; apps/labs/views/teacher/crud.py:117; apps/labs/views/teacher/crud.py:147; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:305; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:317 |
| member.edit | apps/organizations/permissions.py:43; apps/organizations/default_roles.py:115; apps/organizations/default_roles.py:134; apps/organizations/structure_views/_shared.py:38; apps/organizations/structure_views/_shared.py:39; apps/organizations/structure_views/_shared.py:229 |
| member.invite | apps/organizations/permissions.py:42; apps/organizations/default_roles.py:114; apps/organizations/default_roles.py:133; apps/accounts/policies/roles.py:68; apps/accounts/views/organization/_management_flow/flow.py:71; apps/accounts/views/_helpers/rbac.py:225 |
| member.pk | apps/exams/services/question_submission.py:311 |
| member.remove | apps/organizations/permissions.py:44; apps/organizations/default_roles.py:116 |
| member.student_manage | apps/organizations/permissions.py:45; apps/accounts/views/organization/_management_flow/flow.py:70; apps/accounts/views/_helpers/rbac.py:224 |
| member.view | apps/organizations/permissions.py:41; apps/organizations/default_roles.py:46; apps/organizations/default_roles.py:70; apps/organizations/default_roles.py:93; apps/organizations/default_roles.py:113; apps/organizations/default_roles.py:132 |
| members.count | apps/courses/models/enrollment.py:221 |
| members.filter | apps/organizations/views/org_admin/context.py:196; apps/organizations/views/org_admin/context.py:200; apps/courses/views/teacher/membership.py:64; apps/courses/views/teacher/membership.py:65; apps/courses/views/teacher/membership.py:66; apps/accounts/views/profile/_sections/role_assignment.py:56 |
| members.html | apps/organizations/views/org_admin/endpoints.py:144 |
| members.order_by | apps/organizations/views/org_admin/context.py:207 |
| members.set | apps/exams/management/commands/_seed_helpers/courses.py:134 |
| org.admin | apps/organizations/permissions.py:30; apps/accounts/views/roles/_assignment_flow/_resolvers.py:65; apps/accounts/views/roles/_assignment_flow/_resolvers.py:230; apps/accounts/views/roles/_assignment_flow/flow.py:78 |
| org.admin.assign | default role/category only |
| org.delete | apps/organizations/permissions.py:32 |
| org.edit | apps/organizations/permissions.py:27; apps/organizations/default_roles.py:24; apps/organizations/default_roles.py:304 |
| org.get_org_type_display | apps/accounts/views/superadmin/endpoints.py:106 |
| org.id | apps/organizations/views/member/selection.py:33; apps/organizations/views/member/selection.py:34; apps/organizations/views/member/selection.py:38; apps/live_exam/views/results.py:32; apps/live_exam/views/host/_shared.py:32; apps/accounts/views/roles/_assignment_flow/_resolvers.py:96 |
| org.is_active | apps/organizations/management/commands/backfill_admin_memberships.py:195; apps/organizations/views/member/selection.py:32 |
| org.is_suspended | apps/live_exam/views/host/_shared.py:35 |
| org.license_identifier | apps/accounts/views/organization/_management_flow/_requests.py:109 |
| org.manage_members | apps/organizations/permissions.py:29; apps/accounts/views/roles/_assignment_flow/flow.py:72; apps/accounts/views/roles/_assignment_flow/flow.py:123; apps/accounts/views/profile/context_builder/_stage3.py:122 |
| org.message | apps/accounts/views/organization/invitations.py:69; apps/accounts/views/organization/invitations.py:77; apps/accounts/views/organization/invitations.py:88; apps/accounts/views/organization/invitations.py:164; apps/accounts/views/organization/invitations.py:186; apps/accounts/views/organization/invitations.py:192 |
| org.name | apps/organizations/management/commands/seed_western_caspian.py:522; apps/blog/views/moderator/post_management.py:241; apps/blog/views/moderator/post_management.py:247; apps/blog/views/moderator/post_management.py:438; apps/blog/views/moderator/post_management.py:502; apps/accounts/views/organization/_management_flow/_members.py:98 |
| org.org_type | apps/accounts/views/organization/_management_flow/flow.py:378; apps/accounts/views/organization/_management_flow/_requests.py:102; apps/accounts/views/organization/_management_flow/_requests.py:110; apps/accounts/views/roles/_assignment_flow/flow.py:202; apps/accounts/views/roles/_assignment_flow/flow.py:268; apps/accounts/services/statistics_selectors/superadmin.py:157 |
| org.organization_identifier | apps/accounts/views/organization/_management_flow/_requests.py:109 |
| org.owner | apps/organizations/permissions.py:31; apps/organizations/management/commands/seed_western_caspian.py:208; apps/accounts/views/superadmin/endpoints.py:77; apps/accounts/views/roles/_assignment_flow/_resolvers.py:52; apps/accounts/views/roles/_assignment_flow/_resolvers.py:213; apps/accounts/views/roles/_assignment_flow/flow.py:74 |
| org.owner.assign | default role/category only |
| org.owner_id | apps/organizations/management/commands/seed_western_caspian.py:207; apps/accounts/views/superadmin/endpoints.py:86 |
| org.pk | apps/accounts/views/superadmin/endpoints.py:87; apps/accounts/views/superadmin/endpoints.py:117; apps/accounts/views/profile/statistics_export.py:76; apps/accounts/views/profile/statistics_export.py:85; apps/accounts/views/profile/statistics_export.py:114; apps/accounts/views/profile/context_builder/_helpers.py:79 |
| org.roles | apps/accounts/management/commands/import_users_from_excel.py:116; apps/accounts/views/organization/_management_flow/flow.py:340; apps/accounts/views/organization/_management_flow/flow.py:344; apps/accounts/views/organization/_management_flow/flow.py:348 |
| org.save | apps/organizations/management/commands/seed_western_caspian.py:209 |
| org.settings | apps/organizations/permissions.py:28 |
| org.slug | apps/organizations/management/commands/seed_western_caspian.py:160; apps/organizations/management/commands/seed_ci_e2e_scenario.py:556; apps/organizations/management/commands/backfill_admin_memberships.py:197 |
| org.view | apps/organizations/permissions.py:26; apps/organizations/default_roles.py:23; apps/organizations/default_roles.py:44; apps/organizations/default_roles.py:68; apps/organizations/default_roles.py:91; apps/organizations/default_roles.py:111 |
| project.assigned_students | apps/projects/services.py:229; apps/projects/views/student/endpoints.py:61; apps/projects/views/student/endpoints.py:105; apps/projects/views/student/endpoints.py:177; apps/projects/views/teacher/crud.py:84; apps/projects/views/teacher/crud.py:92 |
| project.can_user_submit | apps/projects/views/student/endpoints.py:77; apps/projects/views/student/endpoints.py:115; apps/projects/views/student/endpoints.py:190 |
| project.choice | apps/projects/models.py:18; apps/projects/models.py:19; apps/projects/models.py:20 |
| project.course | apps/projects/services.py:234; apps/projects/views/student/endpoints.py:64; apps/projects/views/student/endpoints.py:179; apps/projects/views/shared/_helpers.py:58; apps/projects/views/shared/_helpers.py:67; apps/projects/views/teacher/endpoints.py:65 |
| project.created_at | apps/accounts/views/_dashboard_helpers/assigned_tasks.py:366 |
| project.deadline | apps/projects/services.py:241; apps/projects/views/teacher/crud.py:153; apps/projects/views/teacher/crud.py:178; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:349; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:367 |
| project.delete | apps/organizations/permissions.py:60; apps/organizations/default_roles.py:175; apps/organizations/default_roles.py:346; apps/organizations/default_roles.py:424; apps/organizations/default_roles.py:474; apps/projects/views/teacher/endpoints.py:38 |
| project.description | apps/projects/views/teacher/crud.py:151; apps/projects/views/teacher/crud.py:176; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:344; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:369 |
| project.field | apps/projects/models.py:27; apps/projects/models.py:29; apps/projects/models.py:31; apps/projects/models.py:33; apps/projects/models.py:34; apps/projects/models.py:37 |
| project.id | apps/projects/views/student/endpoints.py:80; apps/projects/views/student/endpoints.py:193; apps/projects/views/teacher/crud.py:102; apps/projects/views/teacher/crud.py:149; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:362 |
| project.label | apps/projects/forms.py:44; apps/projects/forms.py:45; apps/projects/forms.py:46; apps/projects/forms.py:47; apps/projects/forms.py:48; apps/projects/forms.py:49 |
| project.max_attempts | apps/projects/views/student/endpoints.py:78; apps/projects/views/student/endpoints.py:191; apps/projects/views/teacher/crud.py:154; apps/projects/views/teacher/crud.py:179 |
| project.max_score | apps/projects/views/teacher/crud.py:155; apps/projects/views/teacher/crud.py:180; apps/accounts/views/dashboard/review.py:198 |
| project.meta | apps/projects/models.py:57; apps/projects/models.py:58 |
| project.placeholder | apps/projects/forms.py:27; apps/projects/forms.py:34 |
| project.save | apps/projects/views/teacher/crud.py:182 |
| project.start_date | apps/projects/views/teacher/crud.py:152; apps/projects/views/teacher/crud.py:177; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:347; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:366 |
| project.status | apps/projects/services.py:225; apps/projects/views/teacher/crud.py:94; apps/projects/views/teacher/crud.py:156; apps/projects/views/teacher/crud.py:173; apps/projects/views/teacher/crud.py:181; apps/projects/views/teacher/crud.py:207 |
| project.submissions | apps/projects/views/student/endpoints.py:68; apps/projects/views/student/endpoints.py:182; apps/projects/views/teacher/endpoints.py:69; apps/projects/views/teacher/endpoints.py:138 |
| project.title | apps/projects/views/teacher/crud.py:150; apps/projects/views/teacher/crud.py:175; apps/accounts/views/_dashboard_helpers/results.py:229; apps/accounts/views/_dashboard_helpers/evaluated_review.py:207; apps/accounts/views/_dashboard_helpers/pending_review.py:247; apps/accounts/views/_dashboard_helpers/assigned_tasks.py:344 |
| qa.flag | apps/organizations/permissions.py:90 |
| qa.review | apps/organizations/permissions.py:89 |
| qa.view | apps/organizations/permissions.py:88 |
| role.assign | apps/organizations/permissions.py:51; apps/organizations/default_roles.py:118; apps/accounts/views/_helpers/membership.py:124; apps/accounts/views/roles/permissions.py:46; apps/accounts/views/roles/_assignment_flow/flow.py:71; apps/accounts/views/roles/_assignment_flow/flow.py:123 |
| role.create | apps/organizations/permissions.py:49 |
| role.delete | apps/organizations/permissions.py:52 |
| role.description | templates/organizations/partials/_roles_content.html:21 |
| role.display_name | apps/organizations/models.py:528; apps/organizations/management/commands/seed_ci_e2e_scenario.py:141; apps/organizations/management/commands/seed_ci_e2e_user.py:141; apps/organizations/structure_views/_shared.py:87; apps/organizations/views/member/selection.py:66; apps/ai_assistant/context_builder.py:215 |
| role.edit | apps/organizations/permissions.py:50 |
| role.get | apps/organizations/default_roles.py:528 |
| role.id | apps/exams/management/commands/_seed_helpers/users.py:149 |
| role.is_system | templates/organizations/partials/_roles_content.html:25 |
| role.level | apps/organizations/models.py:555; apps/organizations/scoping.py:100; apps/organizations/context_processors.py:46; apps/organizations/user_extensions.py:121; apps/organizations/decorators.py:214; apps/organizations/templatetags/org_tags.py:77 |
| role.meta | apps/organizations/models.py:471; apps/organizations/models.py:472 |
| role.name | apps/organizations/management/commands/seed_western_caspian.py:116; apps/organizations/management/commands/seed_ci_e2e_scenario.py:89; apps/organizations/management/commands/seed_ci_e2e_user.py:68; apps/organizations/management/commands/seed_ci_e2e_user.py:234; apps/organizations/management/commands/seed_ci_e2e_user.py:248; apps/organizations/management/commands/backfill_admin_memberships.py:122 |
| role.permissions | apps/organizations/user_extensions.py:58; apps/organizations/user_extensions.py:59; apps/organizations/middleware.py:240; apps/organizations/middleware.py:241; apps/ai_assistant/tests.py:246; apps/ai_assistant/tests.py:300 |
| role.scope_type | apps/organizations/scoping.py:100; apps/organizations/management/commands/seed_western_caspian.py:531 |
| role.view | apps/organizations/permissions.py:48; apps/organizations/default_roles.py:117; apps/ai_assistant/context_builder.py:263; templates/organizations/dashboard.html:59 |
| roles.all | apps/organizations/views/org_admin/context.py:241 |
| roles.append | apps/accounts/views/_helpers/rbac.py:47 |
| roles.exists | apps/accounts/policies/roles.py:22; apps/exams/management/commands/_seed_helpers/users.py:71 |
| roles.filter | apps/organizations/management/commands/create_sample_orgs.py:86; apps/organizations/management/commands/create_sample_orgs.py:135; apps/organizations/management/commands/create_sample_orgs.py:170; apps/organizations/views/org_admin/context.py:209; apps/organizations/views/org_admin/endpoints.py:45; apps/accounts/policies/roles.py:30 |
| roles.first | apps/accounts/views/roles/permissions.py:228; apps/accounts/views/profile/_sections/permission_editor.py:45 |
| roles.get | apps/organizations/management/commands/seed_western_caspian.py:122; apps/ai_assistant/tests.py:162; apps/ai_assistant/tests.py:228; apps/ai_assistant/tests.py:287; apps/audit/tests.py:367 |
| roles.html | apps/organizations/views/org_admin/endpoints.py:161 |
| roles.order_by | apps/accounts/policies/roles.py:26; apps/accounts/policies/roles.py:33; apps/accounts/policies/roles.py:36; apps/accounts/policies/roles.py:48; apps/accounts/policies/roles.py:56; apps/accounts/policies/roles.py:73 |
| roles.py | apps/organizations/default_roles.py:198; apps/accounts/models.py:307; apps/accounts/views/__init__.py:8; apps/accounts/views/roles/__init__.py:4; core/roles.py:83 |
| unit.children | apps/organizations/structure_views/_shared.py:207; apps/organizations/structure_views/_shared.py:298 |
| unit.code | apps/organizations/structure_views/_shared.py:200; apps/organizations/structure_views/_shared.py:281 |
| unit.create | apps/organizations/permissions.py:36; apps/organizations/structure_views/_shared.py:35; apps/organizations/structure_views/_shared.py:175; apps/organizations/structure_views/_shared.py:251; apps/organizations/views/org_admin/context.py:45; apps/organizations/views/org_admin/context.py:113 |
| unit.delete | apps/organizations/permissions.py:38; apps/organizations/structure_views/_shared.py:37; apps/organizations/structure_views/_shared.py:206; apps/organizations/structure_views/_shared.py:289 |
| unit.edit | apps/organizations/permissions.py:37; apps/organizations/default_roles.py:131; apps/organizations/default_roles.py:403; apps/organizations/structure_views/_shared.py:36; apps/organizations/structure_views/_shared.py:195; apps/organizations/structure_views/_shared.py:273 |
| unit.head | apps/organizations/structure_views/_shared.py:148; apps/organizations/structure_views/_shared.py:163 |
| unit.id | apps/organizations/structure_views/_shared.py:317; apps/organizations/structure_views/context.py:121; apps/organizations/structure_views/context.py:127 |
| unit.is_active | apps/organizations/structure_views/_shared.py:223; apps/organizations/structure_views/_shared.py:301; apps/exams/management/commands/seed_demo_hierarchy.py:242; apps/exams/management/commands/seed_demo_hierarchy.py:243 |
| unit.memberships | apps/organizations/structure_views/_shared.py:215; apps/organizations/structure_views/_shared.py:290 |
| unit.name | apps/organizations/structure_views/_shared.py:165; apps/organizations/structure_views/_shared.py:199; apps/organizations/structure_views/_shared.py:211; apps/organizations/structure_views/_shared.py:219; apps/organizations/structure_views/_shared.py:225; apps/organizations/structure_views/_shared.py:280 |
| unit.parent | apps/organizations/management/commands/seed_western_caspian.py:223; apps/organizations/structure_views/_shared.py:282; apps/exams/management/commands/seed_demo_hierarchy.py:240 |
| unit.parent_id | apps/organizations/management/commands/seed_western_caspian.py:222; apps/exams/management/commands/seed_demo_hierarchy.py:239 |
| unit.save | apps/organizations/management/commands/seed_western_caspian.py:226; apps/organizations/structure_views/_shared.py:149; apps/organizations/structure_views/_shared.py:164; apps/organizations/structure_views/_shared.py:201; apps/organizations/structure_views/_shared.py:224; apps/organizations/structure_views/_shared.py:284 |
| unit.teacher_members | apps/organizations/structure_views/context.py:127 |
| unit.unit_type | apps/organizations/management/commands/seed_western_caspian.py:219; apps/organizations/management/commands/seed_western_caspian.py:220; apps/exams/management/commands/seed_demo_hierarchy.py:236; apps/exams/management/commands/seed_demo_hierarchy.py:237 |
| unit.view | apps/organizations/permissions.py:35; apps/organizations/default_roles.py:45; apps/organizations/default_roles.py:69; apps/organizations/default_roles.py:92; apps/organizations/default_roles.py:112; apps/organizations/default_roles.py:130 |


## Frontend Visibility Qeydiyyatı

Aşağıdakı mənbələr dashboard/sidebar visibility üçün istifadə olunur; bunlar backend enforcement kimi təkbaşına qəbul edilməməlidir:

| Source reference |
| --- |
| apps/organizations/cabinet_modules.py:6 |
| apps/organizations/cabinet_modules.py:116 |
| apps/organizations/user_extensions.py:124 |
| apps/organizations/structure_views/_shared.py:15 |
| apps/organizations/structure_views/_shared.py:16 |
| apps/organizations/structure_views/_shared.py:33 |
| apps/organizations/structure_views/_shared.py:116 |
| apps/organizations/structure_views/context.py:9 |
| apps/organizations/structure_views/context.py:29 |
| apps/organizations/structure_views/context.py:88 |
| apps/organizations/views/__init__.py:24 |
| apps/organizations/views/__init__.py:25 |
| apps/organizations/views/shared/_helpers.py:29 |
| apps/organizations/views/shared/_helpers.py:61 |
| apps/organizations/views/org_admin/context.py:19 |
| apps/organizations/views/org_admin/context.py:20 |
| apps/organizations/views/org_admin/context.py:42 |
| apps/organizations/views/org_admin/context.py:43 |
| apps/organizations/views/org_admin/context.py:110 |
| apps/organizations/views/org_admin/context.py:113 |
| apps/organizations/views/org_admin/context.py:185 |
| apps/organizations/views/org_admin/context.py:229 |
| apps/organizations/views/org_admin/context.py:243 |
| apps/organizations/views/org_admin/endpoints.py:11 |
| apps/organizations/views/org_admin/endpoints.py:12 |
| apps/organizations/views/org_admin/endpoints.py:83 |
| apps/organizations/views/org_admin/endpoints.py:154 |
| apps/labs/views/teacher/submissions.py:123 |
| apps/labs/views/teacher/submissions.py:126 |
| apps/labs/views/teacher/submissions.py:131 |
| apps/registrar/console_views.py:49 |
| apps/registrar/console_views.py:72 |
| apps/registrar/console_views.py:111 |
| apps/registrar/console_views.py:163 |
| apps/registrar/console_views.py:189 |
| apps/registrar/console_views.py:237 |
| apps/registrar/console_views.py:253 |
| apps/registrar/console_views.py:283 |
| apps/registrar/console_views.py:327 |
| apps/registrar/console_views.py:371 |
| apps/registrar/public.py:70 |
| apps/registrar/pdf_views.py:22 |
| apps/registrar/pdf_views.py:134 |
| apps/task_submission_core/review.py:180 |
| apps/task_submission_core/review.py:182 |
| apps/task_submission_core/review.py:185 |
| apps/blog/profile_sections.py:84 |
| apps/blog/profile_sections.py:346 |
| apps/blog/profile_sections.py:364 |
| apps/blog/views/moderator/posts.py:18 |
| apps/blog/views/moderator/posts.py:107 |
| apps/blog/views/author/posts.py:29 |
| apps/blog/views/author/posts.py:38 |
| apps/blog/views/author/posts.py:143 |
| apps/blog/views/shared/_helpers.py:4 |
| apps/courses/views/shared/dashboard.py:113 |
| apps/courses/views/shared/dashboard.py:114 |
| apps/courses/views/shared/dashboard.py:152 |
| apps/courses/views/shared/dashboard.py:179 |
| apps/courses/views/shared/dashboard.py:188 |

