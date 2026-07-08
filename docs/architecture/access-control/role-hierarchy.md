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

| Org type | Role | Display | Level | Scope | Permissions | Description |
| --- | --- | --- | --- | --- | --- | --- |
| university | rector | Rector | 100 | organization | * | University rector with full administrative access |
| university | vice_rector | Vice Rector | 90 | organization | org.view, org.edit, unit.*, member.*, course.*, grade.*, exam.*, analytics.view_all, audit.view, appeal.create | Vice rector with broad administrative permissions |
| university | exam_center | Exam Center | 85 | organization | org.view, unit.view, member.view, course.view, exam.*, grade.view, grade.publish, appeal.respond, appeal.decide, qa.*, analytics.view_all, audit.view, appeal.create | Exam center managing exam lifecycle, monitoring, results and appeals |
| university | exam_center_head | Exam Center Head | 85 | organization | org.view, unit.view, member.view, course.view, exam.*, grade.view, grade.publish, appeal.respond, appeal.decide, qa.*, analytics.view_all, audit.view, appeal.create | Exam center head — assigns invigilators and manages the exam centre |
| university | exam_center_staff | Exam Center Staff | 60 | organization | org.view, unit.view, member.view, course.view, exam.*, grade.view, qa.*, analytics.view_all, audit.view, appeal.create | Exam center staff — live monitoring, PIN lookup and reports (no invigilator assignment) |
| university | hr | HR | 65 | organization | org.view, unit.view, member.view, member.invite, member.edit, member.remove, role.view, role.assign, analytics.view_unit, audit.view | HR managing staff, positions and faculty/department assignments |
| university | dean | Dean | 80 | unit | unit.view, unit.edit, member.view, member.invite, member.edit, course.*, grade.*, exam.*, analytics.view_unit, appeal.create | Faculty dean managing a specific faculty |
| university | chair_head | Department Chair | 70 | unit | unit.view, member.view, course.*, grade.view, grade.input, exam.*, analytics.view_unit, appeal.create | Department chair managing courses and faculty |
| university | teacher | Teacher | 50 | course | course.view, course.create, course.edit, grade.view, grade.input, exam.view, exam.create, exam.edit, exam.host, exam.delete, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Teacher with course management and grading permissions |
| university | assistant | Teaching Assistant | 40 | course | course.view, grade.view, exam.view, analytics.view_own, appeal.create | Teaching assistant with limited permissions |
| university | lab_assistant | Lab Assistant | 40 | course | course.view, grade.view, grade.input, exam.view, analytics.view_own, appeal.create | Laboratory assistant supporting lab work and grading within their course |
| university | tutor | Tutor | 40 | unit | member.view, course.view, exam.view, analytics.view_unit, appeal.create | Tutor providing academic guidance to student groups within their unit |
| university | program_coordinator | Program Coordinator | 45 | unit | member.view, course.view, exam.view, analytics.view_unit, appeal.create | Program coordinator curating a specialty/program (tutor-equivalent scope) |
| university | lead_student | Lead Student | 30 | unit | course.view, exam.view, appeal.create, member.view, analytics.view_own | Lead student with limited group-level visibility |
| university | student | Student | 10 | unit | course.view, exam.view, appeal.create, analytics.view_own | Student with view and self-service permissions |
| university | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role before specialized assignment |
| school | director | Director | 100 | organization | * | School director with full administrative access |
| school | deputy_director | Deputy Director | 90 | organization | org.view, org.edit, unit.*, member.*, course.*, grade.*, exam.*, analytics.view_all, appeal.create | Deputy director with broad permissions |
| school | section_head | Section Head | 70 | unit | unit.view, member.view, course.*, grade.*, exam.*, analytics.view_unit, appeal.create | Section head managing teachers and courses |
| school | teacher | Teacher | 50 | course | course.view, course.create, course.edit, grade.view, grade.input, exam.view, exam.create, exam.edit, exam.host, exam.delete, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Teacher with course and grading permissions |
| school | student | Student | 10 | unit | course.view, exam.view, analytics.view_own, appeal.create | Student with view permissions |
| school | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role before student/teacher assignment |
| school | parent | Parent | 5 | unit | analytics.view_own | Parent with view access to student data |
| course_center | manager | Center Manager | 100 | organization | * | Course center manager with full access |
| course_center | branch_manager | Branch Manager | 80 | unit | unit.view, unit.edit, member.*, course.*, grade.*, exam.*, analytics.view_unit, appeal.create | Branch manager |
| course_center | instructor | Instructor | 50 | course | course.view, course.edit, grade.view, grade.input, exam.*, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Course instructor |
| course_center | student | Student | 10 | unit | course.view, exam.view, analytics.view_own, appeal.create | Student enrolled in courses |
| course_center | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role |
| individual | owner | Owner | 100 | organization | * | Individual owner with full access |
| individual | collaborator | Collaborator | 50 | course | course.*, grade.*, exam.*, assignment.delete, project.delete, lab.delete, analytics.view_own, appeal.create | Collaborator with course permissions |
| individual | student | Student | 10 | organization | course.view, exam.view, analytics.view_own, appeal.create | Student with view permissions |
| individual | member | Member | 20 | organization | course.view, exam.view, analytics.view_own, appeal.create | Default onboarding role |


## ProfileRole Choice-ları

| Role | Display | Level | Source |
| --- | --- | --- | --- |
| superadmin | Super Admin | 100 | core/roles.py — ProfileRole |
| org_owner | Təşkilat Sahibi | 90 | core/roles.py — ProfileRole |
| org_admin | Təşkilat Admini | 80 | core/roles.py — ProfileRole |
| member | Üzv | 20 | core/roles.py — ProfileRole |
| hr | HR | 65 | core/roles.py — ProfileRole |
| exam_center_head | İmtahan Mərkəzi Rəhbəri | 85 | core/roles.py — ProfileRole |
| exam_center_staff | İmtahan Mərkəzi İşçisi | 60 | core/roles.py — ProfileRole |
| exam_center | İmtahan Mərkəzi | 85 | core/roles.py — ProfileRole |
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
