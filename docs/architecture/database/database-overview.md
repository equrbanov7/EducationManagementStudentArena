# Database Overview

Bu sənəd real Django app registry-sindən çıxarılıb. `models.py` ilə yanaşı paketləşdirilmiş model modulları da daxildir: məsələn `apps/exams/domain/*`, `apps/courses/models/*`, `apps/registrar/models/*`, `apps/labs/models/*`.

## Domenlər Üzrə Model Sayı

| Domen | Concrete model sayı |
| --- | --- |
| AI Assistant | 1 |
| Appeals | 3 |
| Assignments / Projects / Labs | 11 |
| Audit and Security | 1 |
| Core / Tenant Management | 7 |
| Courses and Curriculum | 6 |
| Django System | 3 |
| Exams and Final Center | 28 |
| Live Exam | 3 |
| Notifications | 2 |
| Public Content and Requests | 8 |
| Registrar / Journal | 19 |
| Users and Authentication | 8 |


## App Üzrə Model Sayı

| App | Concrete model sayı |
| --- | --- |
| accounts | 2 |
| admin | 1 |
| ai_assistant | 1 |
| appeals | 3 |
| assignments | 3 |
| audit | 1 |
| auth | 3 |
| blog | 6 |
| contact | 1 |
| contenttypes | 1 |
| courses | 6 |
| exams | 28 |
| labs | 6 |
| live_exam | 3 |
| notifications | 2 |
| organizations | 7 |
| projects | 2 |
| registrar | 19 |
| sessions | 1 |
| trial_exams | 1 |


## Əsas Ownership Xəritəsi

- `organizations.Organization` tenant root modelidir.
- `organizations.OrgUnit`, `Role`, `Membership`, `AcademicPeriod` birbaşa `organization` FK daşıyır.
- `courses.Course` birbaşa `organization` FK daşıyır; course child modelləri tenant-ı `course -> organization` zənciri ilə alır.
- `exams.Exam` birbaşa `organization` FK daşıyır; attempt/answer/question child modelləri `exam` və ya `attempt -> exam` üzərindən scope olunur.
- `registrar.*` akademik/jurnal modellərinin çoxu birbaşa `organization` FK daşıyır.
- `appeals.*` əsasən `Appeal.organization` və `AppealItem -> Appeal` zənciri ilə tenant-a bağlanır.
- `auth.User` Django system modelidir; tenant üzvlüyü `organizations.Membership` və denormalized `accounts.UserProfile.organization` üzərindən qurulur.

## Diagram Faylları

- Global: `docs/architecture/database/emsarena-global-erd.drawio`, `.mmd`, `.svg`
- Domenlər: `docs/architecture/database/domains/*-erd.drawio` və `*-erd.mmd`

## Mənbə Qaydası

Hər table üçün data dictionary-də model source file və mümkün creation migration göstərilir. Migration tapılmayan contrib modelləri Django system table kimi qeyd olunur.

## Organization Structure Subtype Qeydi

`Faculty`, `Kafedra/Department`, `Specialty` və `Academic Group/Class` ayrıca DB table deyil. Bunlar `organizations_orgunit.unit_type` və `parent/path` hierarchy-si ilə ayrılan `OrgUnit` subtype-larıdır. Vizual oxunaqlılıq üçün ayrıca diaqram yaradılıb: `docs/architecture/database/domains/organization-structure-hierarchy.drawio`.
