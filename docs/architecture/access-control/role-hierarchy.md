# Role Hierarchy

Bu sənəd rolları strict parent-child kimi deyil, üç ayrı baxış kimi göstərir:

1. Administrative/organizational placement.
2. Authorization scope (`Role.permissions`, `Membership.scope_unit`, `request.org_permissions`).
3. Academic assignment (`Course`, `StudentGroup`, `OrgUnit`, registrar records).

## Mənbələr

- `apps/organizations/default_roles.py` — organization type üzrə default `Role` şablonları.
- `core/roles.py — ProfileRole` — profile-level cache/compat role choice-ları.
- `apps/organizations/models.py — Role`, `Membership` — tenant-scoped source of truth.
- `apps/accounts/models.py — UserProfile.role` — denormalized cache; source of truth deyil.

## Default Organization Rolları

Cədvəl `apps/organizations/default_roles.py` (+ `default_roles_university.py`) şablonlarından 2026-09-14-də yenidən
törədilib (audit dalğa 2: `qa.*`, `org.delete`, `role.create`/`role.delete`, `grade.override` kataloqdan çıxarılıb;
`org.settings`/`org.edit`, `role.edit`, `audit.export`, `journal.view`, `analytics.view_own` real qapılara bağlanıb;
RİM rəhbərinə (`exam_center_head`) `final_score.entry` verilib — bax `permission-matrix.md`). Köhnə `exam_center`
şablonu artıq yoxdur (yalnız `ProfileRole` seçimi kimi qalır).

| Org type | Role | Display | Level | Scope | Permissions | Description |
| --- | --- | --- | --- | --- | --- | --- |
| university | rector | Rector | 100 | organization | * | University rector with full administrative access |
| university | vice_rector | Vice Rector | 90 | organization | org.view, org.edit, unit.*, member.*, course.*, grade.*, group.view, group.manage, exam.*, syllabus.*, workload.*, user.search, user.credentials, user.block, user.soft_delete, user.edit, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, people.manage_status, people.manage_teacher_role, people.manage_academic, journal.reassign, analytics.view_all, audit.view, audit.export, org.settings, application.create, application.handle, application.manage, catalog.view, catalog.manage, student.registry_view, plan.view, plan.edit, plan.submit, plan.approve_council, plan.approve_office, semester.view, semester.open, semester.lock, semester.unlock, appeal.create | Vice rector with broad administrative permissions |
| university | exam_center_head | Exam Center Head | 85 | organization | org.view, unit.view, member.view, course.view, exam.*, final_score.entry, grade.view, grade.publish, appeal.respond, appeal.decide, people.view_teachers, people.view_students, people.view_contacts, analytics.view_all, audit.view, audit.export, application.create, application.handle, appeal.create | Exam center head — assigns invigilators and manages the exam centre |
| university | ikt_rehber | Rəqəmsal İnkişaf Mərkəzi (RİM) rəhbəri | 95 | organization | org.view, org.edit, unit.*, member.*, course.*, exam.*, final_score.entry, grade.*, group.view, group.manage, journal.correct, journal.close, journal.roster, journal.reassign, schedule.view, schedule.manage, syllabus.*, workload.*, role.*, user.search, user.credentials, user.block, user.soft_delete, user.edit, user.import, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, people.manage_status, people.manage_teacher_role, people.manage_academic, appeal.respond, appeal.decide, analytics.view_all, audit.view, audit.export, org.settings, application.create, application.handle, application.manage, catalog.view, catalog.manage, student.registry_view, student.movement, student.assign_group, plan.view, plan.edit, plan.submit, plan.approve_chair, plan.approve_council, plan.approve_office, semester.view, semester.open, semester.lock, semester.unlock, appeal.create | ICT manager — documented journal-correction override (bypasses edit-window & closed semesters), full exam-centre + structure access; every action audited |
| university | exam_center_staff | Exam Center Staff | 60 | organization | org.view, unit.view, member.view, course.view, exam.*, grade.view, analytics.view_all, audit.view, audit.export, application.create, application.handle, appeal.create | Exam center staff — live monitoring, PIN lookup and reports (no invigilator assignment) |
| university | hr | HR | 65 | organization | org.view, unit.view, member.view, member.invite, member.edit, member.remove, role.view, role.assign, user.search, user.edit, user.import, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, people.manage_teacher_role, analytics.view_unit, audit.view, audit.export, application.create, application.handle | HR managing staff, positions and faculty/department assignments |
| university | dean | Dean | 80 | unit | unit.view, unit.edit, member.view, member.invite, member.edit, course.*, grade.*, group.view, group.manage, exam.*, syllabus.view, syllabus.review, question.chair_review, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, people.manage_status, people.manage_academic, journal.roster, workload.view, workload.report, journal.reassign, schedule.view, schedule.manage, analytics.view_unit, application.create, application.handle, catalog.view, student.registry_view, plan.view, plan.approve_council, semester.view, workload.approve, appeal.create | Faculty dean managing a specific faculty |
| university | chair_head | Department Chair | 70 | unit | unit.view, member.view, course.*, grade.view, grade.input, group.view, group.manage, exam.*, syllabus.view, syllabus.review, syllabus.approve, syllabus.revise, syllabus.reject, question.chair_review, journal.reassign, workload.view, workload.manage, workload.distribute, workload.report, people.view_teachers, people.view_students, people.view_contacts, schedule.view, schedule.manage, analytics.view_unit, application.create, application.handle, catalog.view, plan.view, plan.edit, plan.submit, plan.approve_chair, semester.view, appeal.create | Department chair managing courses and faculty |
| university | teacher | Teacher | 50 | course | course.view, course.create, course.edit, grade.view, grade.input, exam.view, exam.create, exam.edit, exam.host, exam.delete, syllabus.view, syllabus.edit, syllabus.submit, workload.view, assignment.edit, assignment.delete, project.delete, lab.delete, analytics.view_own, application.create, workload.object, appeal.create | Teacher with course management and grading permissions |
| university | assistant | Teaching Assistant | 40 | course | course.view, grade.view, exam.view, analytics.view_own, application.create, workload.view, workload.object, appeal.create | Teaching assistant with limited permissions |
| university | lab_assistant | Lab Assistant | 40 | unit | course.view, grade.view, grade.input, exam.view, analytics.view_own, journal.lessons_unit, application.create, workload.view, workload.object, appeal.create | Laboratory assistant supporting lab work and grading within their course |
| university | tutor | Tutor | 40 | unit | member.view, course.view, exam.view, people.view_students, people.manage_academic, group.manage, unit.view, journal.roster, schedule.view, schedule.manage, analytics.view_unit, application.create, appeal.create | Tutor providing academic guidance to student groups within their unit |
| university | program_coordinator | Program Coordinator | 45 | unit | member.view, course.view, exam.view, people.view_students, people.manage_academic, group.manage, unit.view, journal.roster, schedule.view, schedule.manage, analytics.view_unit, application.create, application.handle, catalog.view, student.registry_view, student.assign_group, plan.view, semester.view, unit.group_manage, workload.view, workload.review, appeal.create | Program coordinator curating a specialty/program (tutor-equivalent scope) |
| university | lead_student | Lead Student | 30 | unit | course.view, exam.view, appeal.create, member.view, analytics.view_own, application.create | Lead student with limited group-level visibility |
| university | student | Student | 10 | unit | course.view, exam.view, appeal.create, analytics.view_own, application.create | Student with view and self-service permissions |
| university | alumni | Məzun / arxiv | 5 | unit | — | Archived alumni/released student — no access, historical records only |
| university | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role before specialized assignment |
| university | teaching_office_head | Tədris şöbəsinin rəhbəri | 85 | organization | org.view, unit.view, unit.create, unit.edit, unit.tree_manage, catalog.view, catalog.manage, member.view, course.view, workload.view, people.view_teachers, analytics.view_all, unit.assign_head, audit.view, audit.export, application.create, plan.view, plan.edit, plan.submit, plan.approve_office, semester.view, semester.open, semester.lock, semester.unlock, unit.group_manage, workload.manage, workload.submit, workload.report | Teaching office head — owner of the structure tree and the academic catalogue |
| university | teaching_office_staff | Tədris şöbəsi əməkdaşı | 60 | organization | org.view, unit.view, unit.create, unit.edit, unit.tree_manage, catalog.view, catalog.manage, member.view, course.view, workload.view, people.view_teachers, analytics.view_all, application.create, plan.view, plan.edit, plan.submit, semester.view, semester.open, unit.group_manage, workload.manage, workload.submit | Teaching office staff — same surface, no head-assignment authority |
| university | student_services | Tələbə Xidmətləri Mərkəzi | 60 | organization | org.view, unit.view, catalog.view, member.view, user.import, student.assign_group, student.registry_view, student.movement, people.view_students, people.view_contacts, people.view_demographics, people.manage_academic, application.create, application.handle | Student services centre — admission intake, student registry and movement orders |
| university | rim_staff | Rəqəmsal İnkişaf Mərkəzi (RİM) əməkdaşı | 60 | organization | org.view, unit.view, catalog.view, member.view, course.view, grade.view, schedule.view, syllabus.view, workload.view, exam.view, exam.create, exam.edit, exam.manage, exam.host, analytics.view_all, audit.view, audit.export, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, application.create, appeal.create | RİM staff — read-only academic surfaces plus exam operations (no account or role actions) |
| university | vice_dean | Dekan müavini | 75 | unit | unit.view, member.view, course.view, grade.view, group.view, exam.view, syllabus.view, syllabus.review, journal.roster, schedule.view, schedule.manage, workload.view, workload.report, analytics.view_unit, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, application.create, appeal.create | Vice dean — faculty read/day-to-day surface without decision keys |
| university | trustee | Qəyyumlar Şurası üzvü | 78 | organization | org.view, unit.view, member.view, catalog.view, course.view, schedule.view, syllabus.view, workload.view, analytics.view_all, audit.view, audit.export, application.create | Board of trustees member — read-only oversight (analytics and audit trail, no write keys) |
| university | admin_unit_head | İnzibati şöbə müdiri | 65 | unit | org.view, unit.view, member.view, catalog.view, schedule.view, analytics.view_unit, people.view_teachers, people.view_students, people.view_contacts, people.view_demographics, application.create | Administrative department head — own unit read surface, no academic or tenant keys |
| school | director | Director | 100 | organization | * | School director with full administrative access |
| school | deputy_director | Deputy Director | 90 | organization | org.view, org.edit, unit.*, member.*, course.*, grade.*, group.view, group.manage, exam.*, user.search, user.credentials, user.block, user.soft_delete, user.edit, analytics.view_all, org.settings, appeal.create | Deputy director with broad permissions |
| school | section_head | Section Head | 70 | unit | unit.view, member.view, course.*, grade.*, group.view, group.manage, exam.*, analytics.view_unit, appeal.create | Section head managing teachers and courses |
| school | teacher | Teacher | 50 | course | course.view, course.create, course.edit, grade.view, grade.input, exam.view, exam.create, exam.edit, exam.host, exam.delete, assignment.edit, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Teacher with course and grading permissions |
| school | student | Student | 10 | unit | course.view, exam.view, analytics.view_own, appeal.create | Student with view permissions |
| school | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role before student/teacher assignment |
| school | parent | Parent | 5 | unit | analytics.view_own | Parent with view access to student data |
| course_center | manager | Center Manager | 100 | organization | * | Course center manager with full access |
| course_center | branch_manager | Branch Manager | 80 | unit | unit.view, unit.edit, member.*, course.*, grade.*, group.view, group.manage, exam.*, analytics.view_unit, appeal.create | Branch manager |
| course_center | instructor | Instructor | 50 | course | course.view, course.edit, grade.view, grade.input, exam.*, assignment.edit, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Course instructor |
| course_center | student | Student | 10 | unit | course.view, exam.view, analytics.view_own, appeal.create | Student enrolled in courses |
| course_center | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role |
| individual | owner | Owner | 100 | organization | * | Individual owner with full access |
| individual | collaborator | Collaborator | 50 | course | course.*, grade.*, exam.*, assignment.edit, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Collaborator with course permissions |
| individual | student | Student | 10 | organization | course.view, exam.view, analytics.view_own, appeal.create | Student with view permissions |
| individual | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role |


## ProfileRole Choice-ları

`core/roles.py — ProfileRole.CHOICES` / `LEVELS` (2026-09-14: 14 seçim; `ikt_rehber` və `rim_staff` əlavə olunub).

| Role | Display | Level | Source |
| --- | --- | --- | --- |
| superadmin | Super Admin | 100 | core/roles.py — ProfileRole |
| org_owner | Təşkilat Sahibi | 90 | core/roles.py — ProfileRole |
| org_admin | Təşkilat Admini | 80 | core/roles.py — ProfileRole |
| member | Üzv | 20 | core/roles.py — ProfileRole |
| hr | HR | 65 | core/roles.py — ProfileRole |
| exam_center_head | İmtahan Mərkəzi Rəhbəri | 85 | core/roles.py — ProfileRole |
| exam_center_staff | İmtahan Mərkəzi İşçisi | 60 | core/roles.py — ProfileRole |
| exam_center | İmtahan Mərkəzi (köhnə alias) | 85 | core/roles.py — ProfileRole |
| ikt_rehber | İKT Rəhbəri | 95 | core/roles.py — ProfileRole |
| rim_staff | RİM İşçisi | 60 | core/roles.py — ProfileRole |
| teacher | Müəllim | 60 | core/roles.py — ProfileRole |
| assistant_teacher | Müəllim Köməkçisi | 55 | core/roles.py — ProfileRole |
| lead_student | Baş Tələbə | 30 | core/roles.py — ProfileRole |
| student | Tələbə | 10 | core/roles.py — ProfileRole |


## Diagramlar

- `role-hierarchy.drawio` editable diagrams.net formatıdır.
- `role-hierarchy.mmd` Mermaid flowchart alternatividir.
- `role-hierarchy.svg` statik baxışdır.

## Şərh

`level` daha yüksək role-ların aşağı səviyyəli role-ları idarə etməsində istifadə olunur, amma bu təkbaşına reporting hierarchy deyil. Məsələn `exam_center` yüksək səviyyəli əməliyyat roludur, lakin HR və struktur idarəetməsinin meneceri kimi təqdim edilmir.
