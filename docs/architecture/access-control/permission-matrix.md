# Permission Matrix

Bu matrix `apps/organizations/default_roles.py` default role şablonlarından, `core/roles.py` ProfileRole alias məntiqindən və `apps/organizations/permissions.py` canonical permission category-lərindən generasiya olunub. Backend enforcement ayrıca `authorization-analysis.md` sənədində source reference-larla göstərilir.

## Legend

C=create, R=read, U=update, D=delete, A=approve/publish/decide, M=manage/wildcard, X=no explicit default permission, SO=self only analytics, DP/FC=unit/faculty/department scope, ORG=organization scope, GLOBAL=all organizations/superadmin bypass, COURSE=course scope.

Qeyd: `superadmin`, `org_owner`, `org_admin`, `assistant_teacher` sütunları `ProfileRole` alias/cache səthindən gəlir. `superadmin` backend-də `is_superuser`/`is_superadmin` ilə bypass edilir; `org_owner` və `org_admin` `resolve_membership_role()` və owner-membership backfill ilə aktiv təşkilatın ən yüksək `Role` səviyyəsinə bağlanır; `assistant_teacher` isə `assistant`/`lab_assistant` membership alias-larından yığılır.


## Matrix

| Resource | director | manager | owner | rector | superadmin | deputy_director | org_owner | vice_rector | exam_center | exam_center_head | branch_manager | dean | org_admin | chair_head | section_head | hr | exam_center_staff | teacher | assistant_teacher | collaborator | instructor | program_coordinator | assistant | lab_assistant | tutor | lead_student | member | student | parent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Organizations | M ORG | M ORG | M ORG | M ORG | M GLOBAL | R U M | M ORG | R U M | R M | R M | X | X | M ORG | X | X | R M | R M | X | X | X | X | X | X | X | X | X | X | X | X |
| Faculties / Departments / Units | M ORG | M ORG | M ORG | M ORG | M GLOBAL | C R U D M | M ORG | C R U D M | R M | R M | R U M | R U M | M ORG | R M | R M | R M | R M | X | X | X | X | X | X | X | X | X | X | X | X |
| Members / Staff / Students | M ORG | M ORG | M ORG | M ORG | M GLOBAL | C R U D M | M ORG | C R U D M | R M | R M | C R U D M | C R U M | M ORG | R M | R M | C R U D M | R M | X | X | X | X | R M | X | X | R M | R M | X | X | X |
| Role Assignment | M ORG | M ORG | M ORG | M ORG | M GLOBAL | X | M ORG | X | X | X | X | X | M ORG | X | X | R M | X | X | X | X | X | X | X | X | X | X | X | X | X |
| Courses | M ORG | M ORG | M ORG | M ORG | M GLOBAL | C R U D M | M ORG | C R U D M | R M | R M | C R U D M | C R U D M | M ORG | C R U D M | C R U D M | X | R M | C R U M | R M COURSE | C R U D M | R U M | R M | R M | R M | R M | R M | R M | R M | X |
| Assignments | M ORG | M ORG | M ORG | M ORG | M GLOBAL | R M | M ORG | R M | R M | R M | R M | R M | M ORG | R M | R M | X | R M | R D M | R M COURSE | R D M | R D M | R M | R M | R M | R M | R M | R M | R M | X |
| Projects | M ORG | M ORG | M ORG | M ORG | M GLOBAL | R M | M ORG | R M | R M | R M | R M | R M | M ORG | R M | R M | X | R M | R D M | R M COURSE | R D M | R D M | R M | R M | R M | R M | R M | R M | R M | X |
| Labs | M ORG | M ORG | M ORG | M ORG | M GLOBAL | R M | M ORG | R M | R M | R M | R M | R M | M ORG | R M | R M | X | R M | R D M | R M COURSE | R D M | R D M | R M | R M | R M | R M | R M | R M | R M | X |
| Exams | M ORG | M ORG | M ORG | M ORG | M GLOBAL | C R U D M | M ORG | C R U D M | C R U D M | C R U D M | C R U D M | C R U D M | M ORG | C R U D M | C R U D M | X | C R U D M | C R U D M | R M COURSE | C R U D M | C R U D M | R M | R M | R M | R M | R M | R M | R M | X |
| Question Bank / QA | M ORG | M ORG | M ORG | M ORG | M GLOBAL | R M | M ORG | R M | R U M | R U M | R M | R M | M ORG | R M | R M | X | R U M | R M | R M COURSE | R M | R M | R M | R M | R M | R M | R M | R M | R M | X |
| Grades / Journal | M ORG | M ORG | M ORG | M ORG | M GLOBAL | R U A M | M ORG | R U A M | R A M | R A M | R U A M | R U A M | M ORG | R U M | R U A M | X | R M | R U M | R U M COURSE | R U A M | R U M | X | R M | R U M | X | X | X | X | X |
| Appeals | M ORG | M ORG | M ORG | M ORG | M GLOBAL | C R M | M ORG | C R M | C R U A M | C R U A M | C R M | C R M | M ORG | C R M | C R M | X | C R M | C R M | C R M COURSE | C R M | C R M | C R M | C R M | C R M | C R M | C R M | C R M | C R M | X |
| Analytics / Reports | M ORG | M ORG | M ORG | M ORG | M GLOBAL | ORG | M ORG | ORG | ORG | ORG | DP | DP | M ORG | DP | DP | DP | ORG | SO | SO COURSE | SO | SO | DP | SO | SO | DP | SO | SO | SO | SO |
| Audit Logs | M ORG | M ORG | M ORG | M ORG | M GLOBAL | X | M ORG | R M | R M | R M | X | X | M ORG | X | X | R M | R M | X | X | X | X | X | X | X | X | X | X | X | X |


## Canonical Permission Categories

| Category | Permissions |
| --- | --- |
| organization | org.view, org.edit, org.settings, org.manage_members, org.admin.assign, org.owner.assign |
| structure | unit.view, unit.create, unit.edit, unit.delete |
| members | member.view, member.invite, member.edit, member.remove, member.student_manage |
| roles | role.view, role.edit, role.assign |
| courses | course.view, course.create, course.edit, course.delete, assignment.delete, project.delete, lab.delete |
| grading | grade.view, grade.input, grade.publish |
| exams | exam.view, exam.create, exam.edit, exam.manage, exam.host, exam.delete |
| appeal | appeal.create, appeal.respond, appeal.decide |
| analytics | analytics.view_own, analytics.view_unit, analytics.view_all |
| audit | audit.view, audit.export |

## Kataloq drift-i — 2026-09-14 (audit 2026-09-13 `access` F-06, hesabat §27)

Reyestrdə olub kodda heç yerdə yoxlanmayan 13 açar («yalançı düymələr»):

| Açar | Qərar | Qapı / mənbə |
| --- | --- | --- |
| `org.settings` | bağlandı | `organizations:settings` səhifəsi — səviyyə (≥90) + açar (`views/shared/_helpers._can_manage_org_settings`) |
| `org.edit` | bağlandı | eyni səhifənin POST-u (məlumat dəyişikliyi) |
| `role.edit` | bağlandı | icazə redaktoru POST-u (`accounts/views/roles/permissions.py`); baxış `role.assign`-da qalır |
| `audit.export` | bağlandı | `audit:export` CSV (`audit/views.can_export_audit`); açar yoxdursa düymə gizlənir |
| `journal.view` | bağlandı | əhatəli YALNIZ-OXU jurnal girişi (`registrar/journal_access.can_observe_journal`, siyahı `journal_scope.journal_view_q`) |
| `analytics.view_own` | bağlandı | «Statistika» şəxsi profili (`teacher` / `student`), yoxdursa `restricted` |
| `org.delete` | çıxarıldı | tenant səviyyəsində təşkilat silmə/arxiv əməli yoxdur (superadmin paneli açarsızdır) |
| `role.create`, `role.delete` | çıxarıldı | xüsusi rol CRUD-u yoxdur (rollar şablondan seed olunur) |
| `grade.override` | çıxarıldı | `journal.correct`-in dublikatı (sahibin qərarı: sənədli düzəliş açarı təkdir) |
| `qa.view`, `qa.review`, `qa.flag` | çıxarıldı | keyfiyyət modulu / modeli / view-u yoxdur (`qa.*` wildcard-ı da şablonlardan silindi) |

Miqrasiya `organizations.0051_permission_catalog_drift`: çıxarılan açarları saxlanılan rollardan silir;
`audit.view` daşıyan hər rola `audit.export`, `level ≥ 90` (wildcard-sız) rollara `org.settings` + `org.edit` əkir —
mövcud tenantlarda heç bir rol kilidlənmir. Şablonlar: `vice_rector` / `ikt_rehber` / `deputy_director` → `org.settings`;
`audit.view` daşıyan 8 şablon → `audit.export`. CI qoruyucusu: `apps/accounts/tests/test_audit_2026_09_13_rbac.py::PermissionCatalogDriftTest`
(pin siyahısı boşdur), `apps/organizations/tests/test_w2_rbac_catalog.py`.
