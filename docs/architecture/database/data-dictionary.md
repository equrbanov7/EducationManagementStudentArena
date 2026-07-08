# Data Dictionary
Bu sənəddə bütün first-party concrete modellər, Django system modelləri və avtomatik M2M through table-lar göstərilir. Field siyahısı real Django `_meta` metadata-sından çıxarılıb.

## App: `accounts`

### `accounts_emailotp` — `accounts.EmailOTP`
- Mənbə: `apps/accounts/models.py`:24`
- Creation migration: `apps/accounts/migrations/0001_initial.py`
- Domen: Users and Authentication
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index; nullable; blank |
| email | email | CharField |  | index; blank; default='' |
| code | code | CharField |  | blank; default='' |
| otp_hash | otp_hash | CharField |  | blank; default='' |
| purpose | purpose | CharField |  | index; default=EmailOTP.Purpose.SIGNUP; choices=signup, login, password_reset, admin_login |
| created_at | created_at | DateTimeField |  | blank |
| expires_at | expires_at | DateTimeField |  |  |
| is_verified | is_verified | BooleanField |  | default=False |
| attempts_count | attempts_count | PositiveSmallIntegerField |  | default=0 |
| is_used | is_used | BooleanField |  | default=False |

Constraints / indexes:
- index: `<Index: fields=['email', 'purpose', 'created_at'] name='accounts_em_email_c46531_idx'>`
- index: `<Index: fields=['user', 'purpose', 'created_at'] name='accounts_em_user_id_1533d7_idx'>`

### `accounts_userprofile` — `accounts.UserProfile`
- Mənbə: `apps/accounts/models.py`:197`
- Creation migration: `apps/accounts/migrations/0001_initial.py`
- Domen: Users and Authentication
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `no/not detected`
- Ownership chain: `accounts.UserProfile.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| user_id | user | OneToOneField | OneToOne → auth_user (CASCADE) | unique; index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (SET_NULL) | index; nullable; blank |
| requested_organization_id | requested_organization | ForeignKey | ForeignKey → organizations_organization (SET_NULL) | index; nullable; blank |
| requested_organization_name | requested_organization_name | CharField |  | blank; default='' |
| requested_organization_message | requested_organization_message | CharField |  | blank; default='' |
| organization_type | organization_type | CharField |  | default='individual'; choices=university, school, course_center, individual |
| country | country | CharField |  | blank; default='' |
| student_university_name | student_university_name | CharField |  | blank; default='' |
| student_school_identifier | student_school_identifier | CharField |  | blank; default='' |
| student_specialization | student_specialization | CharField |  | blank; default='' |
| student_group_number | student_group_number | CharField |  | blank; default='' |
| department | department | CharField |  | blank; default='' |
| staff_position | staff_position | CharField |  | blank; default='' |
| role | role | CharField |  | index; default='member'; choices=superadmin, org_owner, org_admin, member, hr, exam_center_head, exam_center_staff, exam_center |
| avatar | avatar | FileField |  | nullable; blank |
| phone | phone | CharField |  | blank |
| bio | bio | TextField |  | blank |
| supervisor_code | supervisor_code | CharField |  | blank |
| location | location | CharField |  | blank |
| password_change_required | password_change_required | BooleanField |  | index; default=False |
| email_verified | email_verified | BooleanField |  | index; default=False |
| can_manage_exam_rooms | can_manage_exam_rooms | BooleanField |  | index; default=False |
| is_deleted | is_deleted | BooleanField |  | index; default=False |
| deleted_at | deleted_at | DateTimeField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['organization', 'created_at'] name='accounts_us_organiz_b2bf44_idx'>`
- index: `<Index: fields=['role'] name='accounts_us_role_e16858_idx'>`
- index: `<Index: fields=['requested_organization'] name='accounts_us_request_9a72ac_idx'>`
- index: `<Index: fields=['is_deleted', 'deleted_at'] name='accounts_us_is_dele_9bf4cd_idx'>`

## App: `admin`

### `django_admin_log` — `admin.LogEntry`
- Mənbə: `/Users/elvin/.pyenv/versions/3.11.6/lib/python3.11/site-packages/django/contrib/admin/models.py`:106`
- Creation migration: `tapılmadı / contrib model`
- Domen: Django System
- Primary key: `id` (AutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | AutoField |  | PK; unique; blank |
| action_time | action_time | DateTimeField |  | default=now |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| content_type_id | content_type | ForeignKey | ForeignKey → django_content_type (SET_NULL) | index; nullable; blank |
| object_id | object_id | TextField |  | nullable; blank |
| object_repr | object_repr | CharField |  |  |
| action_flag | action_flag | PositiveSmallIntegerField |  | choices=1, 2, 3 |
| change_message | change_message | TextField |  | blank |

## App: `ai_assistant`

### `ai_assistant_aiassistantlog` — `ai_assistant.AIAssistantLog`
- Mənbə: `apps/ai_assistant/models.py`:14`
- Creation migration: `apps/ai_assistant/migrations/0001_initial.py`
- Domen: AI Assistant
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `no/not detected`
- Ownership chain: `ai_assistant.AIAssistantLog.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (SET_NULL) | index; nullable; blank |
| role_name | role_name | CharField |  | blank; default='' |
| prompt | prompt | TextField |  |  |
| response_summary | response_summary | CharField |  | blank; default='' |
| status | status | CharField |  | default=AIAssistantLog.Status.SUCCESS; choices=success, blocked, rate_limited, error |
| block_reason | block_reason | CharField |  | blank; default='' |
| prompt_tokens | prompt_tokens | PositiveIntegerField |  | default=0 |
| response_tokens | response_tokens | PositiveIntegerField |  | default=0 |

Constraints / indexes:
- index: `<Index: fields=['user', '-created_at'] name='ai_assistan_user_id_59dc22_idx'>`
- index: `<Index: fields=['organization', '-created_at'] name='ai_assistan_organiz_d8356b_idx'>`
- index: `<Index: fields=['status', '-created_at'] name='ai_assistan_status_ee0029_idx'>`

## App: `appeals`

### `appeals_appeal` — `appeals.Appeal`
- Mənbə: `apps/appeals/models.py`:28`
- Creation migration: `apps/appeals/migrations/0001_initial.py`
- Domen: Appeals
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `appeals.Appeal.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| attempt_id | attempt | ForeignKey | ForeignKey → exams_examattempt (CASCADE) | index |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| org_unit_id | org_unit | ForeignKey | ForeignKey → organizations_orgunit (SET_NULL) | index; nullable; blank |
| status | status | CharField |  | index; default='pending'; choices=pending, under_review, accepted, rejected, partially_accepted |
| reviewed_by_id | reviewed_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| reviewed_at | reviewed_at | DateTimeField |  | nullable; blank |
| reviewer_note | reviewer_note | TextField |  | blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['organization', 'status', '-created_at'] name='appeal_org_status_idx'>`
- index: `<Index: fields=['exam', 'status'] name='appeal_exam_status_idx'>`
- index: `<Index: fields=['student', '-created_at'] name='appeal_student_created_idx'>`

### `appeals_appealitem` — `appeals.AppealItem`
- Mənbə: `apps/appeals/models.py`:106`
- Creation migration: `apps/appeals/migrations/0001_initial.py`
- Domen: Appeals
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `appeals.AppealItem.appeal -> appeals.Appeal` → `appeals.Appeal.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| appeal_id | appeal | ForeignKey | ForeignKey → appeals_appeal (CASCADE) | index |
| question_id | question | ForeignKey | ForeignKey → exams_examquestion (CASCADE) | index |
| answer_id | answer | ForeignKey | ForeignKey → exams_examanswer (SET_NULL) | index; nullable; blank |
| appeal_type | appeal_type | CharField |  | choices=wrong_question, wrong_answer_key, unclear_question, out_of_syllabus, technical_issue, grading_issue, other |
| comment | comment | TextField |  |  |
| status | status | CharField |  | index; default='pending'; choices=pending, accepted, rejected |
| reviewer_response | reviewer_response | TextField |  | blank |
| resolved_by_id | resolved_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| resolved_at | resolved_at | DateTimeField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('appeal', 'question') name='appeal_item_unique_question'>`
- index: `<Index: fields=['appeal', 'status'] name='appeal_item_status_idx'>`

### `appeals_scoreadjustment` — `appeals.ScoreAdjustment`
- Mənbə: `apps/appeals/models.py`:183`
- Creation migration: `apps/appeals/migrations/0001_initial.py`
- Domen: Appeals
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `appeals.ScoreAdjustment.appeal_item -> appeals.AppealItem` → `appeals.AppealItem.appeal -> appeals.Appeal` → `appeals.Appeal.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| appeal_item_id | appeal_item | OneToOneField | OneToOne → appeals_appealitem (CASCADE) | unique; index |
| attempt_id | attempt | ForeignKey | ForeignKey → exams_examattempt (CASCADE) | index |
| question_id | question | ForeignKey | ForeignKey → exams_examquestion (SET_NULL) | index; nullable; blank |
| delta_points | delta_points | DecimalField |  | default=0 |
| previous_is_correct | previous_is_correct | BooleanField |  | nullable; blank |
| new_is_correct | new_is_correct | BooleanField |  | nullable; blank |
| previous_score | previous_score | DecimalField |  | nullable; blank |
| new_score | new_score | DecimalField |  | nullable; blank |
| previous_answer_score | previous_answer_score | DecimalField |  | nullable; blank |
| applied_by_id | applied_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| applied_at | applied_at | DateTimeField |  | blank |
| reverted | reverted | BooleanField |  | default=False |

Constraints / indexes:
- index: `<Index: fields=['attempt'] name='score_adj_attempt_idx'>`

## App: `assignments`

### `assignments_assignment` — `assignments.Assignment`
- Mənbə: `apps/assignments/models.py`:30`
- Creation migration: `apps/assignments/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `assignments.Assignment.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| type | type | CharField |  | default='homework'; choices=homework, quiz, lab, midterm, final, project |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| instructions | instructions | TextField |  | blank |
| max_score | max_score | DecimalField |  | default=100.0 |
| weight | weight | DecimalField |  | default=1.0 |
| start_date | start_date | DateTimeField |  |  |
| due_date | due_date | DateTimeField |  | nullable; blank |
| allow_late | allow_late | BooleanField |  | default=False |
| late_penalty_per_day | late_penalty_per_day | DecimalField |  | default=0.0 |
| max_attempts | max_attempts | PositiveIntegerField |  | default=1 |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (CASCADE) | index; nullable; blank |
| status | status | CharField |  | default='draft'; choices=draft, published, active, inactive, archived |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| assigned_students | auth_user | assignments_assignment_assigned_students | auto |

### `assignments_notification` — `assignments.Notification`
- Mənbə: `apps/assignments/models.py`:381`
- Creation migration: `apps/assignments/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| title | title | CharField |  |  |
| message | message | TextField |  |  |
| type | type | CharField |  | default='system'; choices=deadline, submission, grade, system |
| is_read | is_read | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |
| link | link | CharField |  | nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['user', 'is_read'] name='assignments_user_id_52bdf7_idx'>`
- index: `<Index: fields=['user', '-created_at'] name='assignments_user_id_72f361_idx'>`

### `assignments_submission` — `assignments.Submission`
- Mənbə: `apps/assignments/models.py`:209`
- Creation migration: `apps/assignments/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `assignments.Submission.assignment -> assignments.Assignment` → `assignments.Assignment.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| assignment_id | assignment | ForeignKey | ForeignKey → assignments_assignment (CASCADE) | index |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| attempt_number | attempt_number | PositiveIntegerField |  | default=1 |
| content | content | TextField |  | blank |
| files | files | JSONField |  | blank; default=list |
| submitted_at | submitted_at | DateTimeField |  | blank |
| is_late | is_late | BooleanField |  | default=False |
| late_days | late_days | IntegerField |  | default=0 |
| status | status | CharField |  | default='submitted'; choices=submitted, grading, graded, returned |
| grade | grade | DecimalField |  | nullable; blank |
| feedback | feedback | TextField |  | blank |
| graded_by_id | graded_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| graded_at | graded_at | DateTimeField |  | nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['assignment', 'user'] name='assignments_assignm_fdd7af_idx'>`
- index: `<Index: fields=['status'] name='assignments_status_d82c9c_idx'>`

## App: `audit`

### `audit_auditlog` — `audit.AuditLog`
- Mənbə: `apps/audit/models.py`:103`
- Creation migration: `apps/audit/migrations/0001_initial.py`
- Domen: Audit and Security
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `no/not detected`
- Ownership chain: `audit.AuditLog.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| user_id | user | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (SET_NULL) | index; nullable; blank |
| action | action | CharField |  | choices=create, update, delete, login, logout, view, export, verify |
| resource_type | resource_type | CharField |  | blank |
| resource_id | resource_id | CharField |  | blank |
| resource_repr | resource_repr | CharField |  | blank |
| content_type_id | content_type | ForeignKey | ForeignKey → django_content_type (SET_NULL) | index; nullable; blank |
| object_id | object_id | CharField |  | blank |
| old_values | old_values | JSONField |  | nullable; blank |
| new_values | new_values | JSONField |  | nullable; blank |
| changes | changes | JSONField |  | nullable; blank |
| reason | reason | TextField |  | blank |
| ip_address | ip_address | GenericIPAddressField |  | nullable; blank |
| user_agent | user_agent | TextField |  | blank |
| request_id | request_id | UUIDField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | index; blank |

Constraints / indexes:
- index: `<Index: fields=['user', '-created_at'] name='audit_audit_user_id_429f6b_idx'>`
- index: `<Index: fields=['organization', '-created_at'] name='audit_audit_organiz_c1c99d_idx'>`
- index: `<Index: fields=['action', '-created_at'] name='audit_audit_action_0c6a84_idx'>`
- index: `<Index: fields=['resource_type', 'resource_id'] name='audit_audit_resourc_2a3aef_idx'>`
- index: `<Index: fields=['content_type', 'object_id'] name='audit_audit_content_4c2ead_idx'>`
- index: `<Index: fields=['request_id'] name='audit_audit_request_06fe30_idx'>`

## App: `auth`

### `auth_group` — `auth.Group`
- Mənbə: `/Users/elvin/.pyenv/versions/3.11.6/lib/python3.11/site-packages/django/contrib/auth/models.py`:102`
- Creation migration: `tapılmadı / contrib model`
- Domen: Users and Authentication
- Primary key: `id` (AutoField)
- Tenant scope: `django-system/global`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | AutoField |  | PK; unique; blank |
| name | name | CharField |  | unique |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| permissions | auth_permission | auth_group_permissions | auto |

### `auth_permission` — `auth.Permission`
- Mənbə: `/Users/elvin/.pyenv/versions/3.11.6/lib/python3.11/site-packages/django/contrib/auth/models.py`:39`
- Creation migration: `tapılmadı / contrib model`
- Domen: Users and Authentication
- Primary key: `id` (AutoField)
- Tenant scope: `django-system/global`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | AutoField |  | PK; unique; blank |
| name | name | CharField |  |  |
| content_type_id | content_type | ForeignKey | ForeignKey → django_content_type (CASCADE) | index |
| codename | codename | CharField |  |  |

Constraints / indexes:
- unique_together: (content_type, codename)

### `auth_user` — `auth.User`
- Mənbə: `/Users/elvin/.pyenv/versions/3.11.6/lib/python3.11/site-packages/django/contrib/auth/models.py`:517`
- Creation migration: `tapılmadı / contrib model`
- Domen: Users and Authentication
- Primary key: `id` (AutoField)
- Tenant scope: `django-system/global`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | AutoField |  | PK; unique; blank |
| password | password | CharField |  |  |
| last_login | last_login | DateTimeField |  | nullable; blank |
| is_superuser | is_superuser | BooleanField |  | default=False |
| username | username | CharField |  | unique |
| first_name | first_name | CharField |  | blank |
| last_name | last_name | CharField |  | blank |
| email | email | CharField |  | blank |
| is_staff | is_staff | BooleanField |  | default=False |
| is_active | is_active | BooleanField |  | default=True |
| date_joined | date_joined | DateTimeField |  | default=now |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| groups | auth_group | auth_user_groups | auto |
| user_permissions | auth_permission | auth_user_user_permissions | auto |

## App: `blog`

### `blog_category` — `blog.Category`
- Mənbə: `apps/blog/models.py`:19`
- Creation migration: `apps/blog/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `global-or-unclear`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| name | name | CharField |  |  |
| name_az | name_az | CharField |  | blank; default='' |
| name_en | name_en | CharField |  | blank; default='' |
| name_ru | name_ru | CharField |  | blank; default='' |
| name_tr | name_tr | CharField |  | blank; default='' |
| slug | slug | SlugField |  | unique; index |
| parent_id | parent | ForeignKey | ForeignKey → blog_category (PROTECT) | index; nullable; blank |
| sort_order | sort_order | PositiveIntegerField |  | default=0 |
| show_in_navbar | show_in_navbar | BooleanField |  | index; default=False |
| is_default | is_default | BooleanField |  | index; default=False |

Constraints / indexes:
- constraint: `<UniqueConstraint: expressions=(Lower(F(name_az)),) name='blog_category_root_name_az_unique' condition=(AND: ('parent__isnull', True))>`
- constraint: `<UniqueConstraint: expressions=(Lower(F(name_en)),) name='blog_category_root_name_en_unique' condition=(AND: ('parent__isnull', True))>`
- constraint: `<UniqueConstraint: expressions=(Lower(F(name_ru)),) name='blog_category_root_name_ru_unique' condition=(AND: ('parent__isnull', True))>`
- constraint: `<UniqueConstraint: expressions=(Lower(F(name_tr)),) name='blog_category_root_name_tr_unique' condition=(AND: ('parent__isnull', True))>`
- constraint: `<UniqueConstraint: expressions=(F(parent), Lower(F(name_az))) name='blog_subcategory_parent_name_az_unique' condition=(AND: ('parent__isnull', False))>`
- constraint: `<UniqueConstraint: expressions=(F(parent), Lower(F(name_en))) name='blog_subcategory_parent_name_en_unique' condition=(AND: ('parent__isnull', False))>`
- constraint: `<UniqueConstraint: expressions=(F(parent), Lower(F(name_ru))) name='blog_subcategory_parent_name_ru_unique' condition=(AND: ('parent__isnull', False))>`
- constraint: `<UniqueConstraint: expressions=(F(parent), Lower(F(name_tr))) name='blog_subcategory_parent_name_tr_unique' condition=(AND: ('parent__isnull', False))>`

### `blog_comment` — `blog.Comment`
- Mənbə: `apps/blog/models.py`:431`
- Creation migration: `apps/blog/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| post_id | post | ForeignKey | ForeignKey → blog_post (CASCADE) | index |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| text | text | TextField |  |  |
| rating | rating | PositiveSmallIntegerField |  | default=5; choices=1, 2, 3, 4, 5 |
| created_at | created_at | DateTimeField |  | blank |

### `blog_post` — `blog.Post`
- Mənbə: `apps/blog/models.py`:218`
- Creation migration: `apps/blog/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| author_id | author | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| category_id | category | ForeignKey | ForeignKey → blog_category (PROTECT) | index; nullable; blank |
| title | title | CharField |  |  |
| slug | slug | SlugField |  | unique; index; blank |
| excerpt | excerpt | TextField |  | blank |
| content | content | TextField |  |  |
| view_count | view_count | PositiveBigIntegerField |  | index; default=0 |
| image_url | image_url | CharField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| is_published | is_published | BooleanField |  | default=True |
| requires_approval | requires_approval | BooleanField |  | index; default=False |
| approval_status | approval_status | CharField |  | index; default=Post.ApprovalStatus.APPROVED; choices=approved, pending, needs_changes |
| approval_feedback | approval_feedback | TextField |  | blank; default='' |
| approved_by_id | approved_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| approved_at | approved_at | DateTimeField |  | nullable; blank |
| approval_requested_at | approval_requested_at | DateTimeField |  | nullable; blank |
| image | image | FileField |  | nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['is_published', 'approval_status', '-created_at'] name='blog_post_public_list_idx'>`
- index: `<Index: fields=['category', '-created_at'] name='blog_post_category_idx'>`
- index: `<Index: fields=['author', '-created_at'] name='blog_post_author_idx'>`
- index: `<Index: fields=['approval_status', '-approval_requested_at'] name='blog_post_review_idx'>`

### `blog_postapprovallog` — `blog.PostApprovalLog`
- Mənbə: `apps/blog/models.py`:399`
- Creation migration: `apps/blog/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| post_id | post | ForeignKey | ForeignKey → blog_post (CASCADE) | index |
| reviewer_id | reviewer | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| action | action | CharField |  | choices=approved, needs_changes, feedback |
| feedback | feedback | TextField |  | blank; default='' |
| created_at | created_at | DateTimeField |  | blank |

### `blog_question` — `blog.Question`
- Mənbə: `apps/blog/models.py`:474`
- Creation migration: `apps/blog/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| author_id | author | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| question_text | question_text | TextField |  |  |
| answer_text | answer_text | TextField |  | nullable; blank |
| visible_to_all | visible_to_all | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| visible_users | auth_user | blog_question_visible_users | auto |

### `blog_subscriber` — `blog.Subscriber`
- Mənbə: `apps/blog/models.py`:461`
- Creation migration: `apps/blog/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `global-or-unclear`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| email | email | CharField |  | unique |
| conf_token | conf_token | CharField |  | nullable; blank |
| is_active | is_active | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |

## App: `contact`

### `contact_contactmessage` — `contact.ContactMessage`
- Mənbə: `apps/contact/models.py`:20`
- Creation migration: `apps/contact/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| name | name | CharField |  |  |
| email | email | CharField |  |  |
| phone | phone | CharField |  | blank |
| subject | subject | CharField |  | default='general'; choices=general, sales, support, partnership, feedback, other |
| message | message | TextField |  |  |
| ip_address | ip_address | GenericIPAddressField |  | nullable; blank |
| user_agent | user_agent | CharField |  | blank |
| is_handled | is_handled | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |
| handled_at | handled_at | DateTimeField |  | nullable; blank |
| reply_body | reply_body | TextField |  | blank |
| reply_from | reply_from | CharField |  | blank; choices=info, support |
| reply_delivery_status | reply_delivery_status | CharField |  | blank; choices=pending, sent, failed, recorded |
| reply_delivery_error | reply_delivery_error | CharField |  | blank |
| reply_sent_at | reply_sent_at | DateTimeField |  | nullable; blank |
| reply_sent_by_id | reply_sent_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['-created_at'] name='contact_con_created_00b9df_idx'>`
- index: `<Index: fields=['is_handled', '-created_at'] name='contact_con_is_hand_01c13a_idx'>`

## App: `contenttypes`

### `django_content_type` — `contenttypes.ContentType`
- Mənbə: `/Users/elvin/.pyenv/versions/3.11.6/lib/python3.11/site-packages/django/contrib/contenttypes/models.py`:134`
- Creation migration: `tapılmadı / contrib model`
- Domen: Django System
- Primary key: `id` (AutoField)
- Tenant scope: `django-system/global`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | AutoField |  | PK; unique; blank |
| app_label | app_label | CharField |  |  |
| model | model | CharField |  |  |

Constraints / indexes:
- unique_together: (app_label, model)

## App: `courses`

### `courses_course` — `courses.Course`
- Mənbə: `apps/courses/models/course.py`:15`
- Creation migration: `apps/courses/migrations/0001_initial.py`
- Domen: Courses and Curriculum
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| owner_id | owner | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| slug | slug | SlugField |  | unique; index; blank |
| status | status | CharField |  | default='draft'; choices=draft, published, archived |
| cover_image | cover_image | FileField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| unit_id | unit | ForeignKey | ForeignKey → organizations_orgunit (SET_NULL) | index; nullable; blank |
| period_id | period | ForeignKey | ForeignKey → organizations_academicperiod (SET_NULL) | index; nullable; blank |
| grading_type | grading_type | CharField |  | default='percentage'; choices=percentage, letter, pass_fail, points |
| passing_grade | passing_grade | DecimalField |  | nullable; blank |
| settings | settings | JSONField |  | blank; default=dict |

Constraints / indexes:
- index: `<Index: fields=['owner', '-created_at'] name='courses_cou_owner_i_e2e8dd_idx'>`
- index: `<Index: fields=['status'] name='courses_cou_status_158bbf_idx'>`
- index: `<Index: fields=['slug'] name='courses_cou_slug_2e551f_idx'>`

### `courses_coursegroup` — `courses.CourseGroup`
- Mənbə: `apps/courses/models/enrollment.py`:144`
- Creation migration: `apps/courses/migrations/0001_initial.py`
- Domen: Courses and Curriculum
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `courses.CourseGroup.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| name | name | CharField |  |  |
| schedule | schedule | JSONField |  | blank; default=dict |
| instructor_id | instructor | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| max_students | max_students | PositiveIntegerField |  | default=30 |
| created_at | created_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| members | auth_user | courses_coursegroup_members | auto |

Constraints / indexes:
- unique_together: (course, name)
- index: `<Index: fields=['course'] name='courses_cou_course__225864_idx'>`
- index: `<Index: fields=['instructor'] name='courses_cou_instruc_f2ed74_idx'>`

### `courses_courseinstructor` — `courses.CourseInstructor`
- Mənbə: `apps/courses/models/enrollment.py`:80`
- Creation migration: `apps/courses/migrations/0001_initial.py`
- Domen: Courses and Curriculum
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `courses.CourseInstructor.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| role | role | CharField |  | default='assistant'; choices=primary, assistant, guest |
| permissions | permissions | JSONField |  | blank; default=dict |
| created_at | created_at | DateTimeField |  | blank |

Constraints / indexes:
- unique_together: (course, user)
- index: `<Index: fields=['course', 'role'] name='courses_cou_course__13a825_idx'>`

### `courses_coursemembership` — `courses.CourseMembership`
- Mənbə: `apps/courses/models/enrollment.py`:13`
- Creation migration: `apps/courses/migrations/0001_initial.py`
- Domen: Courses and Curriculum
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `courses.CourseMembership.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| role | role | CharField |  | default='student'; choices=teacher, assistant, student |
| group_name | group_name | CharField |  | blank |
| joined_at | joined_at | DateTimeField |  | blank |

Constraints / indexes:
- unique_together: (course, user)
- index: `<Index: fields=['course', 'role'] name='courses_cou_course__076371_idx'>`
- index: `<Index: fields=['course', 'group_name'] name='courses_cou_course__44546e_idx'>`

### `courses_courseresource` — `courses.CourseResource`
- Mənbə: `apps/courses/models/content.py`:66`
- Creation migration: `apps/courses/migrations/0001_initial.py`
- Domen: Courses and Curriculum
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `courses.CourseResource.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| topic_id | topic | ForeignKey | ForeignKey → courses_coursetopic (SET_NULL) | index; nullable; blank |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| resource_type | resource_type | CharField |  | default='file'; choices=file, link, document, video |
| file | file | FileField |  | nullable; blank |
| url | url | CharField |  | blank |
| created_at | created_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['course', 'topic'] name='courses_cou_course__c30055_idx'>`

### `courses_coursetopic` — `courses.CourseTopic`
- Mənbə: `apps/courses/models/content.py`:10`
- Creation migration: `apps/courses/migrations/0001_initial.py`
- Domen: Courses and Curriculum
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `courses.CourseTopic.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| order | order | PositiveIntegerField |  | default=1 |
| created_at | created_at | DateTimeField |  | blank |

Constraints / indexes:
- unique_together: (course, order)
- index: `<Index: fields=['course', 'order'] name='courses_cou_course__0e20e3_idx'>`

## App: `exams`

### `exams_aiconfiguration` — `exams.AIConfiguration`
- Mənbə: `apps/exams/domain/ai_config.py`:17`
- Creation migration: `apps/exams/migrations/0003_aiconfiguration.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `global-or-unclear`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| enabled | enabled | BooleanField |  | default=True |
| rate_limit | rate_limit | CharField |  | default='100/1h' |
| summary_model | summary_model | CharField |  | default='gemini-2.5-flash'; choices=gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.5-pro |
| grading_model | grading_model | CharField |  | default='gemini-2.5-flash'; choices=gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.5-pro |
| assistant_model | assistant_model | CharField |  | default='gemini-2.5-flash'; choices=gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.5-pro |
| monthly_budget | monthly_budget | DecimalField |  | default=5.0 |
| updated_at | updated_at | DateTimeField |  | blank |

### `exams_bankquestion` — `exams.BankQuestion`
- Mənbə: `apps/exams/domain/question_bank/bank_question.py`:25`
- Creation migration: `apps/exams/migrations/0017_question_bank_library.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.BankQuestion.bank -> exams.QuestionBank` → `exams.QuestionBank.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| bank_id | bank | ForeignKey | ForeignKey → exams_questionbank (CASCADE) | index |
| text | text | TextField |  |  |
| question_type | question_type | CharField |  | default='test'; choices=test, written |
| answer_mode | answer_mode | CharField |  | default='single'; choices=single, multiple |
| correct_answer | correct_answer | TextField |  | blank |
| difficulty | difficulty | CharField |  | default='medium'; choices=easy, medium, hard |
| language | language | CharField |  | index; default='az'; choices=az, en, ru, tr |
| points | points | PositiveIntegerField |  | default=1 |
| tags | tags | JSONField |  | blank; default=list |
| explanation | explanation | TextField |  | blank |
| fingerprint | fingerprint | CharField |  | index; blank |
| image | image | FileField |  | nullable; blank |
| video | video | FileField |  | nullable; blank |
| is_active | is_active | BooleanField |  | index; default=True |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['bank', 'is_active'] name='bankq_bank_active_idx'>`
- index: `<Index: fields=['bank', 'language'] name='bankq_bank_lang_idx'>`
- index: `<Index: fields=['bank', 'difficulty'] name='bankq_bank_diff_idx'>`

### `exams_bankquestionoption` — `exams.BankQuestionOption`
- Mənbə: `apps/exams/domain/question_bank/bank_question.py`:139`
- Creation migration: `apps/exams/migrations/0017_question_bank_library.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.BankQuestionOption.question -> exams.BankQuestion` → `exams.BankQuestion.bank -> exams.QuestionBank` → `exams.QuestionBank.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| question_id | question | ForeignKey | ForeignKey → exams_bankquestion (CASCADE) | index |
| label | label | CharField |  | nullable; blank; choices=A, B, C, D, E |
| text | text | TextField |  |  |
| image | image | FileField |  | nullable; blank |
| is_correct | is_correct | BooleanField |  | default=False |

### `exams_codingexamquestion` — `exams.CodingExamQuestion`
- Mənbə: `apps/exams/domain/coding.py`:8`
- Creation migration: `apps/exams/migrations/0005_alter_exam_exam_type_codingexamquestion_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.CodingExamQuestion.question -> exams.ExamQuestion` → `exams.ExamQuestion.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| question_id | question | OneToOneField | OneToOne → exams_examquestion (CASCADE) | unique; index |
| language | language | CharField |  | default='python'; choices=javascript, python, cpp, java, html |
| title | title | CharField |  |  |
| problem_statement | problem_statement | TextField |  |  |
| input_description | input_description | TextField |  | blank |
| output_description | output_description | TextField |  | blank |
| example_input | example_input | TextField |  | blank |
| example_output | example_output | TextField |  | blank |
| time_limit_seconds | time_limit_seconds | PositiveIntegerField |  | default=2 |
| memory_limit_mb | memory_limit_mb | PositiveIntegerField |  | default=128 |
| max_score | max_score | PositiveIntegerField |  | default=100 |
| starter_code | starter_code | TextField |  | blank |
| allow_file_creation | allow_file_creation | BooleanField |  | default=False |
| allow_multiple_files | allow_multiple_files | BooleanField |  | default=False |
| enable_code_execution | enable_code_execution | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

### `exams_codingfile` — `exams.CodingFile`
- Mənbə: `apps/exams/domain/coding.py`:290`
- Creation migration: `apps/exams/migrations/0005_alter_exam_exam_type_codingexamquestion_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.CodingFile.submission -> exams.CodingSubmission` → `exams.CodingSubmission.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| submission_id | submission | ForeignKey | ForeignKey → exams_codingsubmission (CASCADE) | index |
| name | name | CharField |  |  |
| content | content | TextField |  | blank |
| language | language | CharField |  | blank |
| is_main | is_main | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- unique_together: (submission, name)

### `exams_codingsubmission` — `exams.CodingSubmission`
- Mənbə: `apps/exams/domain/coding.py`:166`
- Creation migration: `apps/exams/migrations/0005_alter_exam_exam_type_codingexamquestion_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.CodingSubmission.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| attempt_id | attempt | ForeignKey | ForeignKey → exams_examattempt (CASCADE) | index; nullable; blank |
| question_id | question | ForeignKey | ForeignKey → exams_codingexamquestion (CASCADE) | index |
| selected_language | selected_language | CharField |  | choices=javascript, python, cpp, java, html |
| submitted_code | submitted_code | TextField |  | blank |
| files | files | JSONField |  | blank; default=list |
| output | output | TextField |  | blank |
| error_message | error_message | TextField |  | blank |
| execution_status | execution_status | CharField |  | default='draft'; choices=draft, success, runtime_error, compile_error, timeout, execution_disabled, sandbox_unavailable, submitted |
| score | score | DecimalField |  | nullable; blank |
| test_results | test_results | JSONField |  | blank; default=list |
| execution_time_ms | execution_time_ms | PositiveIntegerField |  | nullable; blank |
| memory_usage_kb | memory_usage_kb | PositiveIntegerField |  | nullable; blank |
| is_final | is_final | BooleanField |  | default=False |
| submitted_at | submitted_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['student', 'exam', '-submitted_at'] name='exams_codin_student_2a03b5_idx'>`
- index: `<Index: fields=['attempt', 'question', 'is_final'] name='exams_codin_attempt_ba27be_idx'>`
- index: `<Index: fields=['execution_status'] name='exams_codin_executi_9bb611_idx'>`

### `exams_codingtestcase` — `exams.CodingTestCase`
- Mənbə: `apps/exams/domain/coding.py`:115`
- Creation migration: `apps/exams/migrations/0005_alter_exam_exam_type_codingexamquestion_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.CodingTestCase.coding_question -> exams.CodingExamQuestion` → `exams.CodingExamQuestion.question -> exams.ExamQuestion` → `exams.ExamQuestion.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| coding_question_id | coding_question | ForeignKey | ForeignKey → exams_codingexamquestion (CASCADE) | index |
| input_data | input_data | TextField |  | blank |
| expected_output | expected_output | TextField |  | blank |
| visibility | visibility | CharField |  | default='visible'; choices=visible, hidden |
| point_value | point_value | PositiveIntegerField |  | default=1 |
| order | order | PositiveIntegerField |  | default=1 |
| created_at | created_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['coding_question', 'visibility', 'order'] name='exams_codin_coding__d6c308_idx'>`

### `exams_exam` — `exams.Exam`
- Mənbə: `apps/exams/domain/exam_definition.py`:22`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| author_id | author | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| exam_type | exam_type | CharField |  | default='test'; choices=test, written, coding |
| start_datetime | start_datetime | DateTimeField |  | nullable; blank |
| end_datetime | end_datetime | DateTimeField |  | nullable; blank |
| is_active | is_active | BooleanField |  | default=False |
| results_hidden_from_students | results_hidden_from_students | BooleanField |  | default=False |
| total_duration_minutes | total_duration_minutes | PositiveIntegerField |  | nullable; blank |
| default_question_time_seconds | default_question_time_seconds | PositiveIntegerField |  | nullable; blank |
| max_attempts_per_user | max_attempts_per_user | PositiveIntegerField |  | nullable; blank |
| random_question_count | random_question_count | PositiveIntegerField |  | default=10 |
| fair_question_distribution_enabled | fair_question_distribution_enabled | BooleanField |  | default=True |
| ai_difficulty_balance_enabled | ai_difficulty_balance_enabled | BooleanField |  | default=False |
| default_question_points | default_question_points | PositiveIntegerField |  | default=1 |
| course_id | course | ForeignKey | ForeignKey → courses_course (SET_NULL) | index; nullable; blank |
| subject_id | subject | ForeignKey | ForeignKey → registrar_subject (SET_NULL) | index; nullable; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| exam_type_extended | exam_type_extended | CharField |  | nullable; blank; choices=quiz, midterm, final, placement, practice |
| mode | mode | CharField |  | default='online'; choices=online, offline, hybrid |
| proctoring_level | proctoring_level | CharField |  | default='none'; choices=none, basic, strict |
| settings | settings | JSONField |  | blank; default=dict |
| is_public | is_public | BooleanField |  | default=True |
| access_code | access_code | CharField |  | blank |
| slug | slug | SlugField |  | unique; index; blank |
| created_at | created_at | DateTimeField |  | blank |
| enable_paint | enable_paint | BooleanField |  | default=False |
| is_archived | is_archived | BooleanField |  | index; default=False |
| archived_at | archived_at | DateTimeField |  | nullable; blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| allowed_users | auth_user | exams_exam_allowed_users | auto |
| allowed_groups | exams_studentgroup | exams_exam_allowed_groups | auto |

Constraints / indexes:
- index: `<Index: fields=['organization', 'is_active', '-created_at'] name='exam_org_active_created_idx'>`
- index: `<Index: fields=['organization', 'exam_type', '-created_at'] name='exam_org_type_created_idx'>`
- index: `<Index: fields=['course', '-created_at'] name='exam_course_created_idx'>`
- index: `<Index: fields=['author', '-created_at'] name='exam_author_created_idx'>`
- index: `<Index: fields=['author', 'is_archived', '-created_at'] name='exam_author_archived_idx'>`

### `exams_examanswer` — `exams.ExamAnswer`
- Mənbə: `apps/exams/domain/attempts.py`:311`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ExamAnswer.attempt -> exams.ExamAttempt` → `exams.ExamAttempt.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| attempt_id | attempt | ForeignKey | ForeignKey → exams_examattempt (CASCADE) | index |
| question_id | question | ForeignKey | ForeignKey → exams_examquestion (CASCADE) | index |
| text_answer | text_answer | TextField |  | blank |
| is_correct | is_correct | BooleanField |  | default=False |
| teacher_score | teacher_score | PositiveIntegerField |  | nullable; blank |
| teacher_feedback | teacher_feedback | TextField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| has_paint | has_paint | BooleanField |  | default=False |
| paint_image | paint_image | FileField |  | nullable; blank |
| paint_updated_at | paint_updated_at | DateTimeField |  | nullable; blank |
| paint_data_url | paint_data_url | TextField |  | nullable; blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| selected_options | exams_examquestionoption | exams_examanswer_selected_options | auto |

Constraints / indexes:
- unique_together: (attempt, question)

### `exams_examanswerfile` — `exams.ExamAnswerFile`
- Mənbə: `apps/exams/domain/attempts.py`:358`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ExamAnswerFile.answer -> exams.ExamAnswer` → `exams.ExamAnswer.attempt -> exams.ExamAttempt` → `exams.ExamAttempt.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| answer_id | answer | ForeignKey | ForeignKey → exams_examanswer (CASCADE) | index |
| file | file | FileField |  |  |
| uploaded_at | uploaded_at | DateTimeField |  | blank |

### `exams_examattempt` — `exams.ExamAttempt`
- Mənbə: `apps/exams/domain/attempts.py`:16`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ExamAttempt.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| checked_by_teacher | checked_by_teacher | BooleanField |  | default=False |
| teacher_checked_at | teacher_checked_at | DateTimeField |  | nullable; blank |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| language | language | CharField |  | nullable; blank; choices=az, en, ru, tr |
| language_variant_id | language_variant | ForeignKey | ForeignKey → exams_examlanguagevariant (SET_NULL) | index; nullable; blank |
| attempt_number | attempt_number | PositiveIntegerField |  | default=1 |
| is_trial | is_trial | BooleanField |  | index; default=False |
| marked_question_ids | marked_question_ids | JSONField |  | blank; default=list |
| status | status | CharField |  | default='in_progress'; choices=draft, in_progress, submitted, expired |
| started_at | started_at | DateTimeField |  | blank |
| finished_at | finished_at | DateTimeField |  | nullable; blank |
| duration_seconds | duration_seconds | PositiveIntegerField |  | nullable; blank |
| correct_count | correct_count | PositiveIntegerField |  | default=0 |
| wrong_count | wrong_count | PositiveIntegerField |  | default=0 |
| teacher_score | teacher_score | PositiveIntegerField |  | nullable; blank |
| teacher_feedback | teacher_feedback | TextField |  | blank |
| supervision_status | supervision_status | CharField |  | default='active'; choices=active, warned, locked, removed, resumed |
| supervision_violation_count | supervision_violation_count | PositiveIntegerField |  | default=0 |
| supervision_extra_chances | supervision_extra_chances | PositiveIntegerField |  | default=0 |
| supervision_resumed_at | supervision_resumed_at | DateTimeField |  | nullable; blank |
| supervision_locked_at | supervision_locked_at | DateTimeField |  | nullable; blank |
| supervision_manual_lock | supervision_manual_lock | BooleanField |  | default=False |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('user', 'exam') name='uniq_active_attempt_per_user_exam' condition=(AND: ('status', 'in_progress'))>`
- constraint: `<UniqueConstraint: fields=('user', 'exam', 'attempt_number') name='uniq_attempt_number_per_user_exam'>`
- index: `<Index: fields=['user', 'exam', 'status'] name='exams_exama_user_id_6ce609_idx'>`
- index: `<Index: fields=['user', 'exam', '-started_at'] name='exams_exama_user_id_bf4f2e_idx'>`

### `exams_examlanguagevariant` — `exams.ExamLanguageVariant`
- Mənbə: `apps/exams/domain/language.py`:19`
- Creation migration: `apps/exams/migrations/0015_exam_language_variant.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ExamLanguageVariant.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| language | language | CharField |  | default='az'; choices=az, en, ru, tr |
| display_name | display_name | CharField |  | blank |
| is_active | is_active | BooleanField |  | default=True |
| question_count_override | question_count_override | PositiveIntegerField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('exam', 'language') name='exam_language_variant_unique'>`
- index: `<Index: fields=['exam', 'is_active'] name='exam_lang_variant_active_idx'>`

### `exams_examquestion` — `exams.ExamQuestion`
- Mənbə: `apps/exams/domain/question_bank/exam_question.py`:137`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ExamQuestion.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| points | points | PositiveIntegerField |  | default=1 |
| fingerprint | fingerprint | CharField |  | index; blank |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| block_id | block | ForeignKey | ForeignKey → exams_questionblock (SET_NULL) | index; nullable; blank |
| bank_id | bank | ForeignKey | ForeignKey → exams_questionbank (SET_NULL) | index; nullable; blank |
| source_bank_question_id | source_bank_question | ForeignKey | ForeignKey → exams_bankquestion (SET_NULL) | index; nullable; blank |
| language | language | CharField |  | index; default='az'; choices=az, en, ru, tr |
| language_variant_id | language_variant | ForeignKey | ForeignKey → exams_examlanguagevariant (SET_NULL) | index; nullable; blank |
| difficulty | difficulty | CharField |  | default='medium'; choices=easy, medium, hard |
| difficulty_source | difficulty_source | CharField |  | default='manual'; choices=manual, ai |
| difficulty_checked_at | difficulty_checked_at | DateTimeField |  | nullable; blank |
| tags | tags | JSONField |  | blank; default=list |
| explanation | explanation | TextField |  | blank |
| usage_count | usage_count | PositiveIntegerField |  | default=0 |
| text | text | TextField |  |  |
| correct_answer | correct_answer | TextField |  | blank |
| order | order | PositiveIntegerField |  | default=1 |
| answer_mode | answer_mode | CharField |  | default='single'; choices=single, multiple |
| time_limit_seconds | time_limit_seconds | PositiveIntegerField |  | nullable; blank |
| image | image | FileField |  | nullable; blank |
| video | video | FileField |  | nullable; blank |
| enable_paint | enable_paint | BooleanField |  | default=False |
| disable_paint | disable_paint | BooleanField |  | default=False |
| is_active | is_active | BooleanField |  | index; default=True |
| created_at | created_at | DateTimeField |  | blank |

### `exams_examquestionoption` — `exams.ExamQuestionOption`
- Mənbə: `apps/exams/domain/question_bank/exam_question.py`:379`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ExamQuestionOption.question -> exams.ExamQuestion` → `exams.ExamQuestion.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| label | label | CharField |  | nullable; blank; choices=A, B, C, D, E |
| question_id | question | ForeignKey | ForeignKey → exams_examquestion (CASCADE) | index |
| text | text | TextField |  |  |
| image | image | FileField |  | nullable; blank |
| is_correct | is_correct | BooleanField |  | default=False |

### `exams_examroom` — `exams.ExamRoom`
- Mənbə: `apps/exams/domain/final_center.py`:99`
- Creation migration: `apps/exams/migrations/0030_examroom_examroomsession_finalexamticket_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.ExamRoom.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| name | name | CharField |  |  |
| code | code | CharField |  |  |
| building | building | CharField |  | blank |
| floor | floor | CharField |  | blank |
| capacity | capacity | PositiveIntegerField |  | default=0 |
| computer_count | computer_count | PositiveIntegerField |  | default=0 |
| notes | notes | TextField |  | blank |
| is_active | is_active | BooleanField |  | default=True |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| invigilators | auth_user | exams_examroom_invigilators | auto |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'code') name='uniq_exam_room_code_per_org'>`
- index: `<Index: fields=['organization', 'is_active', 'name'] name='examroom_org_active_name_idx'>`

### `exams_examroomcomputer` — `exams.ExamRoomComputer`
- Mənbə: `apps/exams/domain/final_center.py`:181`
- Creation migration: `apps/exams/migrations/0038_examroom_invigilators_examroomcomputer.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.ExamRoomComputer.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| room_id | room | ForeignKey | ForeignKey → exams_examroom (CASCADE) | index |
| label | label | CharField |  |  |
| seat_number | seat_number | PositiveIntegerField |  | nullable; blank |
| mac_address | mac_address | CharField |  |  |
| ip_address | ip_address | GenericIPAddressField |  | nullable; blank |
| is_active | is_active | BooleanField |  | default=True |
| notes | notes | CharField |  | blank |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('room', 'mac_address') name='uniq_room_computer_mac'>`
- constraint: `<UniqueConstraint: fields=('room', 'label') name='uniq_room_computer_label'>`
- constraint: `<UniqueConstraint: fields=('room', 'seat_number') name='uniq_room_computer_seat' condition=(AND: ('seat_number__isnull', False))>`
- index: `<Index: fields=['room', 'is_active'] name='roomcomp_room_active_idx'>`

### `exams_examroomsession` — `exams.ExamRoomSession`
- Mənbə: `apps/exams/domain/final_center.py`:284`
- Creation migration: `apps/exams/migrations/0030_examroom_examroomsession_finalexamticket_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.ExamRoomSession.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| room_id | room | ForeignKey | ForeignKey → exams_examroom (PROTECT) | index |
| invigilator_id | invigilator | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| scheduled_start | scheduled_start | DateTimeField |  |  |
| scheduled_end | scheduled_end | DateTimeField |  |  |
| state | state | CharField |  | default='prepared'; choices=prepared, entry_open, active, ended, cancelled |
| entry_opened_at | entry_opened_at | DateTimeField |  | nullable; blank |
| started_at | started_at | DateTimeField |  | nullable; blank |
| started_by_id | started_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| start_connected_count | start_connected_count | PositiveIntegerField |  | default=0 |
| ended_at | ended_at | DateTimeField |  | nullable; blank |
| ended_by_id | ended_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| notes | notes | TextField |  | blank |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| staff | auth_user | exams_examroomsession_staff | auto |

Constraints / indexes:
- constraint: `<CheckConstraint: condition=(AND: ('scheduled_end__gt', F(scheduled_start))) name='room_session_end_after_start'>`
- index: `<Index: fields=['organization', 'state', '-scheduled_start'] name='roomsess_org_state_sched_idx'>`
- index: `<Index: fields=['exam', '-scheduled_start'] name='roomsess_exam_sched_idx'>`
- index: `<Index: fields=['room', '-scheduled_start'] name='roomsess_room_sched_idx'>`
- index: `<Index: fields=['invigilator', 'state'] name='roomsess_invig_state_idx'>`

### `exams_examstudentpin` — `exams.ExamStudentPin`
- Mənbə: `apps/exams/domain/student_access.py`:20`
- Creation migration: `apps/exams/migrations/0036_exam_subject_examstudentpin_studentexamattemptgrant.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.ExamStudentPin.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| pin_hash | pin_hash | CharField |  |  |
| pin_cipher | pin_cipher | TextField |  | blank; default='' |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('exam', 'student') name='uniq_exam_student_pin'>`
- index: `<Index: fields=['exam', 'student'] name='exam_student_pin_idx'>`

### `exams_examsupervisionconfig` — `exams.ExamSupervisionConfig`
- Mənbə: `apps/exams/domain/supervision.py`:15`
- Creation migration: `apps/exams/migrations/0004_add_supervision_models.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.ExamSupervisionConfig.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_id | exam | OneToOneField | OneToOne → exams_exam (CASCADE) | unique; index |
| enabled | enabled | BooleanField |  | default=False |
| template | template | CharField |  | default='custom'; choices=custom, light, medium, strict |
| force_fullscreen | force_fullscreen | BooleanField |  | default=True |
| grace_period_seconds | grace_period_seconds | PositiveIntegerField |  | default=15 |
| resume_window_seconds | resume_window_seconds | PositiveIntegerField |  | default=600 |
| max_fullscreen_violations | max_fullscreen_violations | PositiveIntegerField |  | default=3 |
| detect_tab_switch | detect_tab_switch | BooleanField |  | default=True |
| block_copy_paste | block_copy_paste | BooleanField |  | default=True |
| disable_right_click | disable_right_click | BooleanField |  | default=True |
| disable_text_selection | disable_text_selection | BooleanField |  | default=False |
| restrict_keyboard_shortcuts | restrict_keyboard_shortcuts | BooleanField |  | default=True |
| violation_action | violation_action | CharField |  | default='lock_exam'; choices=auto_submit, lock_exam, remove_student, mark_suspicious |
| recovery_policy | recovery_policy | CharField |  | default='teacher_controlled'; choices=no_second_chance, one_extra_chance, teacher_controlled |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

### `exams_finalexamticket` — `exams.FinalExamTicket`
- Mənbə: `apps/exams/domain/final_center.py`:425`
- Creation migration: `apps/exams/migrations/0030_examroom_examroomsession_finalexamticket_and_more.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.FinalExamTicket.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| session_id | session | ForeignKey | ForeignKey → exams_examroomsession (CASCADE) | index |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| attempt_id | attempt | ForeignKey | ForeignKey → exams_examattempt (SET_NULL) | index; nullable; blank |
| seat_number | seat_number | PositiveIntegerField |  | nullable; blank |
| language | language | CharField |  | blank; default=''; choices=az, en, ru, tr |
| status | status | CharField |  | default='assigned'; choices=assigned, waiting, ready, active, completed, removed, absent |
| pin_hash | pin_hash | CharField |  | blank; default='' |
| pin_cipher | pin_cipher | TextField |  | blank; default='' |
| pin_issued_at | pin_issued_at | DateTimeField |  | nullable; blank |
| pin_expires_at | pin_expires_at | DateTimeField |  | nullable; blank |
| pin_revoked_at | pin_revoked_at | DateTimeField |  | nullable; blank |
| pin_failed_attempts | pin_failed_attempts | PositiveIntegerField |  | default=0 |
| pin_locked_until | pin_locked_until | DateTimeField |  | nullable; blank |
| pin_generated_by_id | pin_generated_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| reminder_stage | reminder_stage | PositiveSmallIntegerField |  | default=0 |
| entry_validated_at | entry_validated_at | DateTimeField |  | nullable; blank |
| rules_accepted_at | rules_accepted_at | DateTimeField |  | nullable; blank |
| waiting_since | waiting_since | DateTimeField |  | nullable; blank |
| ready_at | ready_at | DateTimeField |  | nullable; blank |
| started_at | started_at | DateTimeField |  | nullable; blank |
| completed_at | completed_at | DateTimeField |  | nullable; blank |
| removed_at | removed_at | DateTimeField |  | nullable; blank |
| removed_by_id | removed_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| removal_action | removal_action | CharField |  | blank; default=''; choices=removed, suspended, technical |
| removal_reason | removal_reason | TextField |  | blank; default='' |
| reconnect_count | reconnect_count | PositiveIntegerField |  | default=0 |
| last_seen_at | last_seen_at | DateTimeField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('session', 'student') name='uniq_ticket_per_session_student'>`
- constraint: `<UniqueConstraint: fields=('exam', 'student') name='uniq_ticket_per_exam_student'>`
- constraint: `<UniqueConstraint: fields=('session', 'seat_number') name='uniq_seat_per_session' condition=(AND: ('seat_number__isnull', False))>`
- index: `<Index: fields=['session', 'status'] name='finticket_session_status_idx'>`
- index: `<Index: fields=['student', 'status'] name='finticket_student_status_idx'>`
- index: `<Index: fields=['organization', '-created_at'] name='finticket_org_created_idx'>`

### `exams_proctoringlog` — `exams.ProctoringLog`
- Mənbə: `apps/exams/domain/attempts.py`:382`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.ProctoringLog.exam_attempt -> exams.ExamAttempt` → `exams.ExamAttempt.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_attempt_id | exam_attempt | ForeignKey | ForeignKey → exams_examattempt (CASCADE) | index |
| event_type | event_type | CharField |  | choices=tab_switch, copy_paste, right_click, fullscreen_exit, focus_loss, browser_console, screenshot_attempt, multiple_windows |
| timestamp | timestamp | DateTimeField |  | blank |
| details | details | JSONField |  | blank; default=dict |

Constraints / indexes:
- index: `<Index: fields=['exam_attempt', '-timestamp'] name='exams_proct_exam_at_76f1af_idx'>`
- index: `<Index: fields=['event_type'] name='exams_proct_event_t_d8a785_idx'>`

### `exams_questionbank` — `exams.QuestionBank`
- Mənbə: `apps/exams/domain/question_bank/exam_question.py`:21`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.QuestionBank.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| name | name | CharField |  |  |
| description | description | TextField |  | blank |
| subject | subject | CharField |  | blank |
| topic | topic | CharField |  | blank |
| language | language | CharField |  | index; default='az'; choices=az, en, ru, tr |
| default_question_type | default_question_type | CharField |  | default='test'; choices=test, written |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index; nullable; blank |
| org_unit_id | org_unit | ForeignKey | ForeignKey → organizations_orgunit (SET_NULL) | index; nullable; blank |
| organization_type | organization_type | CharField |  | default='individual'; choices=university, school, course_center, individual |
| is_shared | is_shared | BooleanField |  | default=False |
| is_active | is_active | BooleanField |  | index; default=True |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['created_by', '-created_at'] name='exams_quest_created_b2b8da_idx'>`
- index: `<Index: fields=['is_active', 'is_shared'] name='exams_quest_is_acti_1cb61b_idx'>`

### `exams_questionblock` — `exams.QuestionBlock`
- Mənbə: `apps/exams/domain/exam_definition.py`:312`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `exams.QuestionBlock.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| name | name | CharField |  |  |
| order | order | PositiveIntegerField |  | default=1 |
| time_limit_minutes | time_limit_minutes | PositiveIntegerField |  | nullable; blank |
| enable_paint | enable_paint | BooleanField |  | nullable; blank; default=None |

### `exams_questionsubmission` — `exams.QuestionSubmission`
- Mənbə: `apps/exams/domain/submission_inbox.py`:28`
- Creation migration: `apps/exams/migrations/0027_questionsubmission.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `no/not detected`
- Ownership chain: `exams.QuestionSubmission.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| teacher_id | teacher | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| title | title | CharField |  |  |
| subject | subject | CharField |  | default='' |
| student_group_id | student_group | ForeignKey | ForeignKey → exams_studentgroup (SET_NULL) | index; nullable; blank |
| group_label | group_label | CharField |  | default='' |
| language | language | CharField |  | default='az'; choices=az, en, ru, tr |
| raw_text | raw_text | TextField |  |  |
| teacher_note | teacher_note | TextField |  | blank; default='' |
| parsed_snapshot | parsed_snapshot | JSONField |  | blank; default=list |
| question_count | question_count | PositiveIntegerField |  | default=0 |
| error_count | error_count | PositiveIntegerField |  | default=0 |
| warning_count | warning_count | PositiveIntegerField |  | default=0 |
| status | status | CharField |  | index; default='pending'; choices=pending, accepted, rejected |
| resubmission_count | resubmission_count | PositiveIntegerField |  | default=0 |
| reviewer_id | reviewer | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| reviewed_at | reviewed_at | DateTimeField |  | nullable; blank |
| reviewer_note | reviewer_note | TextField |  | blank |
| accepted_bank_id | accepted_bank | ForeignKey | ForeignKey → exams_questionbank (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['organization', 'status', '-created_at'] name='qsub_org_status_idx'>`
- index: `<Index: fields=['teacher', '-created_at'] name='qsub_teacher_created_idx'>`

### `exams_studentexamattemptgrant` — `exams.StudentExamAttemptGrant`
- Mənbə: `apps/exams/domain/student_access.py`:53`
- Creation migration: `apps/exams/migrations/0036_exam_subject_examstudentpin_studentexamattemptgrant.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `exams.StudentExamAttemptGrant.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| extra_attempts | extra_attempts | PositiveIntegerField |  | default=1 |
| granted_by_id | granted_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('exam', 'student') name='uniq_exam_student_attempt_grant'>`

### `exams_studentgroup` — `exams.StudentGroup`
- Mənbə: `apps/exams/domain/access_policy.py`:12`
- Creation migration: `apps/exams/migrations/0001_initial.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.StudentGroup.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| teacher_id | teacher | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index; nullable; blank |
| name | name | CharField |  |  |
| org_unit_id | org_unit | ForeignKey | ForeignKey → organizations_orgunit (SET_NULL) | index; nullable; blank |
| created_at | created_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| students | auth_user | exams_studentgroup_students | auto |
| teachers | auth_user | exams_studentgroup_teachers | auto |
| subjects | registrar_subject | exams_studentgroup_subjects | auto |

Constraints / indexes:
- unique_together: (organization, teacher, name)

### `exams_supervisionincident` — `exams.SupervisionIncident`
- Mənbə: `apps/exams/domain/supervision.py`:192`
- Creation migration: `apps/exams/migrations/0004_add_supervision_models.py`
- Domen: Exams and Final Center
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `no/not detected`
- Ownership chain: `exams.SupervisionIncident.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| attempt_id | attempt | ForeignKey | ForeignKey → exams_examattempt (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| event_type | event_type | CharField |  | choices=fullscreen_exited, fullscreen_restored, tab_switched, window_blurred, window_focused, copy_attempt, paste_attempt, cut_attempt |
| severity | severity | CharField |  | default='medium'; choices=info, low, medium, high, critical |
| timestamp | timestamp | DateTimeField |  | blank |
| metadata | metadata | JSONField |  | blank; default=dict |
| violation_count_at_time | violation_count_at_time | PositiveIntegerField |  | default=0 |
| teacher_action | teacher_action | CharField |  | blank; default='' |

Constraints / indexes:
- index: `<Index: fields=['attempt', '-timestamp'] name='exams_super_attempt_6c8795_idx'>`
- index: `<Index: fields=['organization', '-timestamp'] name='exams_super_organiz_413f14_idx'>`
- index: `<Index: fields=['exam', '-timestamp'] name='exams_super_exam_id_b3121a_idx'>`
- index: `<Index: fields=['student', '-timestamp'] name='exams_super_student_34affa_idx'>`
- index: `<Index: fields=['event_type'] name='exams_super_event_t_f8c193_idx'>`
- index: `<Index: fields=['severity'] name='exams_super_severit_e94589_idx'>`

### `exams_textextractionjob` — `exams.TextExtractionJob`
- Mənbə: `apps/exams/domain/import_jobs.py`:31`
- Creation migration: `apps/exams/migrations/0024_textextractionjob.py`
- Domen: Exams and Final Center
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `exams.TextExtractionJob.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index; nullable; blank |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| kind | kind | CharField |  | default='extract'; choices=extract, ai_generate, export |
| payload | payload | JSONField |  | blank; default=dict |
| result_meta | result_meta | JSONField |  | blank; default=dict |
| source_name | source_name | CharField |  | blank; default='' |
| file | file | FileField |  | nullable; blank |
| result_file | result_file | FileField |  | nullable; blank |
| status | status | CharField |  | index; default='pending'; choices=pending, processing, success, failed |
| text | text | TextField |  | blank; default='' |
| error | error | TextField |  | blank; default='' |
| created_at | created_at | DateTimeField |  | blank |
| started_at | started_at | DateTimeField |  | nullable; blank |
| finished_at | finished_at | DateTimeField |  | nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['user', '-created_at'] name='exams_extjob_user_created'>`

## App: `labs`

### `labs_lab` — `labs.Lab`
- Mənbə: `apps/labs/models/lab.py`:14`
- Creation migration: `apps/labs/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `labs.Lab.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| start_datetime | start_datetime | DateTimeField |  |  |
| end_datetime | end_datetime | DateTimeField |  |  |
| max_score | max_score | PositiveIntegerField |  | default=100 |
| max_attempts | max_attempts | PositiveIntegerField |  | default=1 |
| status | status | CharField |  | default='draft'; choices=draft, published, archived |
| allow_late_submission | allow_late_submission | BooleanField |  | default=False |
| late_penalty_percent | late_penalty_percent | PositiveIntegerField |  | default=0 |
| teacher_files | teacher_files | FileField |  | nullable; blank |
| teacher_instructions | teacher_instructions | TextField |  | blank |
| allow_file_upload | allow_file_upload | BooleanField |  | default=True |
| allow_link_submission | allow_link_submission | BooleanField |  | default=True |
| allowed_extensions | allowed_extensions | CharField |  | default='zip,pdf,docx,png,jpg,txt,py,java,cpp' |
| max_file_size_mb | max_file_size_mb | PositiveIntegerField |  | default=50 |
| questions_per_student | questions_per_student | PositiveIntegerField |  | default=0 |
| allowed_groups | allowed_groups | TextField |  | blank |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| allowed_students | auth_user | labs_lab_allowed_students | auto |

### `labs_labanswer` — `labs.LabAnswer`
- Mənbə: `apps/labs/models/assignment.py`:230`
- Creation migration: `apps/labs/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `labs.LabAnswer.lab -> labs.Lab` → `labs.Lab.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| lab_id | lab | ForeignKey | ForeignKey → labs_lab (CASCADE) | index |
| question_id | question | ForeignKey | ForeignKey → labs_labquestion (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| submission_id | submission | ForeignKey | ForeignKey → labs_labsubmission (CASCADE) | index; nullable; blank |
| attempt_number | attempt_number | PositiveIntegerField |  | default=1 |
| answer | answer | TextField |  | blank |
| answer_file | answer_file | FileField |  | nullable; blank |
| is_draft | is_draft | BooleanField |  | default=True |
| is_correct | is_correct | BooleanField |  | nullable; blank |
| score | score | DecimalField |  | nullable; blank |
| submitted_at | submitted_at | DateTimeField |  | blank |

Constraints / indexes:
- unique_together: (lab, question, student, attempt_number)

### `labs_labassignment` — `labs.LabAssignment`
- Mənbə: `apps/labs/models/assignment.py`:18`
- Creation migration: `apps/labs/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `labs.LabAssignment.lab -> labs.Lab` → `labs.Lab.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| lab_id | lab | ForeignKey | ForeignKey → labs_lab (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| assigned_at | assigned_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| assigned_questions | labs_labquestion | labs_labassignment_assigned_questions | auto |

Constraints / indexes:
- unique_together: (lab, student)

### `labs_labblock` — `labs.LabBlock`
- Mənbə: `apps/labs/models/lab.py`:236`
- Creation migration: `apps/labs/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `labs.LabBlock.lab -> labs.Lab` → `labs.Lab.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| lab_id | lab | ForeignKey | ForeignKey → labs_lab (CASCADE) | index |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| order | order | PositiveIntegerField |  | default=1 |
| questions_to_pick | questions_to_pick | PositiveIntegerField |  | default=0 |
| created_at | created_at | DateTimeField |  | blank |

### `labs_labquestion` — `labs.LabQuestion`
- Mənbə: `apps/labs/models/lab.py`:278`
- Creation migration: `apps/labs/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `labs.LabQuestion.block -> labs.LabBlock` → `labs.LabBlock.lab -> labs.Lab` → `labs.Lab.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| block_id | block | ForeignKey | ForeignKey → labs_labblock (CASCADE) | index |
| question_number | question_number | PositiveIntegerField |  | default=1 |
| question_text | question_text | TextField |  |  |
| attachment | attachment | FileField |  | nullable; blank |
| points | points | PositiveIntegerField |  | default=0 |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

### `labs_labsubmission` — `labs.LabSubmission`
- Mənbə: `apps/labs/models/assignment.py`:134`
- Creation migration: `apps/labs/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `labs.LabSubmission.assignment -> labs.LabAssignment` → `labs.LabAssignment.lab -> labs.Lab` → `labs.Lab.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| assignment_id | assignment | ForeignKey | ForeignKey → labs_labassignment (CASCADE) | index |
| submission_text | submission_text | TextField |  | blank |
| submission_file | submission_file | FileField |  | nullable; blank |
| submission_link | submission_link | CharField |  | blank |
| status | status | CharField |  | default='submitted'; choices=submitted, late, graded, returned |
| score | score | DecimalField |  | nullable; blank |
| feedback | feedback | TextField |  | blank |
| graded_by_id | graded_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| graded_at | graded_at | DateTimeField |  | nullable; blank |
| submitted_at | submitted_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| attempt_number | attempt_number | PositiveIntegerField |  | default=1 |

Constraints / indexes:
- index: `<Index: fields=['assignment', 'status', '-submitted_at'] name='labsub_assign_status_idx'>`

## App: `live_exam`

### `live_exam_liveanswer` — `live_exam.LiveAnswer`
- Mənbə: `apps/live_exam/models.py`:169`
- Creation migration: `apps/live_exam/migrations/0001_initial.py`
- Domen: Live Exam
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `live_exam.LiveAnswer.session -> live_exam.LiveSession` → `live_exam.LiveSession.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| session_id | session | ForeignKey | ForeignKey → live_exam_livesession (CASCADE) | index |
| player_id | player | ForeignKey | ForeignKey → live_exam_liveplayer (CASCADE) | index |
| question_id | question_id | IntegerField |  |  |
| choice_id | choice_id | IntegerField |  | nullable; blank |
| choice_ids | choice_ids | JSONField |  | blank; default=list |
| is_correct | is_correct | BooleanField |  | default=False |
| answer_ms | answer_ms | IntegerField |  | default=0 |
| awarded_points | awarded_points | IntegerField |  | default=0 |
| created_at | created_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('session', 'player', 'question_id') name='uniq_answer_per_player_question'>`
- index: `<Index: fields=['session', 'question_id'] name='liveans_session_question_idx'>`

### `live_exam_liveplayer` — `live_exam.LivePlayer`
- Mənbə: `apps/live_exam/models.py`:126`
- Creation migration: `apps/live_exam/migrations/0001_initial.py`
- Domen: Live Exam
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `live_exam.LivePlayer.session -> live_exam.LiveSession` → `live_exam.LiveSession.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| session_id | session | ForeignKey | ForeignKey → live_exam_livesession (CASCADE) | index |
| nickname | nickname | CharField |  |  |
| avatar_key | avatar_key | CharField |  | default='avatar_1' |
| accessory_key | accessory_key | CharField |  | default='accessory_none' |
| client_id | client_id | CharField |  | index |
| score | score | IntegerField |  | default=0 |
| streak | streak | PositiveIntegerField |  | default=0 |
| is_connected | is_connected | BooleanField |  | default=True |
| last_seen | last_seen | DateTimeField |  | default=now |
| created_at | created_at | DateTimeField |  | blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('session', 'client_id') name='uniq_player_per_session_client'>`

### `live_exam_livesession` — `live_exam.LiveSession`
- Mənbə: `apps/live_exam/models.py`:26`
- Creation migration: `apps/live_exam/migrations/0001_initial.py`
- Domen: Live Exam
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `yes`
- Ownership chain: `live_exam.LiveSession.exam -> exams.Exam` → `exams.Exam.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| exam_id | exam | ForeignKey | ForeignKey → exams_exam (CASCADE) | index |
| host_user_id | host_user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| pin | pin | CharField |  | unique; index; default=generate_pin |
| state | state | CharField |  | default='lobby'; choices=lobby, question, reveal, finished |
| is_locked | is_locked | BooleanField |  | default=False |
| current_index | current_index | PositiveIntegerField |  | default=0 |
| question_started_at | question_started_at | DateTimeField |  | nullable; blank |
| question_ends_at | question_ends_at | DateTimeField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| current_question_id | current_question_id | IntegerField |  | index; nullable; blank |
| question_seconds | question_seconds | PositiveIntegerField |  | default=15 |
| question_limit | question_limit | PositiveIntegerField |  | default=10 |
| selected_question_ids | selected_question_ids | JSONField |  | blank; default=list |
| host_settings | host_settings | JSONField |  | blank; default=dict |

## App: `notifications`

### `notifications_inappnotification` — `notifications.InAppNotification`
- Mənbə: `apps/notifications/models.py`:95`
- Creation migration: `apps/notifications/migrations/0001_initial.py`
- Domen: Notifications
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `notifications.InAppNotification.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| recipient_id | recipient | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index; nullable; blank |
| title | title | CharField |  |  |
| message | message | TextField |  | blank; default='' |
| link | link | CharField |  | blank; default='' |
| notification_type | notification_type | CharField |  | index; default=NotificationType.SYSTEM; choices=assignment, exam, grade, system, course, live_exam, approval |
| is_read | is_read | BooleanField |  | index; default=False |
| read_at | read_at | DateTimeField |  | nullable; blank |
| deleted_at | deleted_at | DateTimeField |  | index; nullable; blank |
| metadata | metadata | JSONField |  | blank; default=dict |
| created_at | created_at | DateTimeField |  | index; blank |

Constraints / indexes:
- index: `<Index: fields=['recipient', 'deleted_at', 'is_read'] name='notificatio_recipie_54c709_idx'>`
- index: `<Index: fields=['recipient', 'deleted_at', 'created_at'] name='notificatio_recipie_1788e0_idx'>`
- index: `<Index: fields=['organization', 'recipient'] name='notif_org_recipient_idx'>`

### `notifications_studentorganizationrequest` — `notifications.StudentOrganizationRequest`
- Mənbə: `apps/notifications/models.py`:25`
- Creation migration: `apps/notifications/migrations/0001_initial.py`
- Domen: Notifications
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `notifications.StudentOrganizationRequest.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| role_type | role_type | CharField |  | index; default=MembershipRequestRoleType.STUDENT; choices=student, teacher, staff |
| message | message | CharField |  | blank; default='' |
| status | status | CharField |  | index; default=StudentOrganizationRequestStatus.PENDING; choices=pending, approved, rejected, cancelled, auto_closed |
| resolution_note | resolution_note | CharField |  | blank; default='' |
| responded_by_id | responded_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| responded_at | responded_at | DateTimeField |  | nullable; blank |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Constraints / indexes:
- index: `<Index: fields=['user', 'status'] name='notificatio_user_id_5a1d0b_idx'>`
- index: `<Index: fields=['organization', 'status'] name='notificatio_organiz_4a40b7_idx'>`
- index: `<Index: fields=['organization', 'role_type', 'status'] name='notificatio_organiz_278c6d_idx'>`

## App: `organizations`

### `organizations_academicperiod` — `organizations.AcademicPeriod`
- Mənbə: `apps/organizations/models.py`:360`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `organizations.AcademicPeriod.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| name | name | CharField |  |  |
| period_type | period_type | CharField |  | choices=semester, trimester, quarter, year, term |
| academic_year | academic_year | CharField |  |  |
| start_date | start_date | DateField |  |  |
| end_date | end_date | DateField |  |  |
| registration_start | registration_start | DateField |  | nullable; blank |
| registration_end | registration_end | DateField |  | nullable; blank |
| exam_session_start | exam_session_start | DateField |  | nullable; blank |
| exam_session_end | exam_session_end | DateField |  | nullable; blank |
| is_current | is_current | BooleanField |  | index; default=False |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- unique_together: (organization, name, academic_year)
- index: `<Index: fields=['organization', '-start_date'] name='organizatio_organiz_655adc_idx'>`
- index: `<Index: fields=['organization', 'is_current'] name='organizatio_organiz_a61403_idx'>`

### `organizations_country` — `organizations.Country`
- Mənbə: `apps/organizations/models.py`:43`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (BigAutoField)
- Tenant scope: `global/master-data`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| code | code | CharField |  | unique |
| name | name | CharField |  | unique |
| is_active | is_active | BooleanField |  | index; default=True |

### `organizations_institution` — `organizations.Institution`
- Mənbə: `apps/organizations/models.py`:59`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (BigAutoField)
- Tenant scope: `global/master-data`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| country_id | country | ForeignKey | ForeignKey → organizations_country (CASCADE) | index |
| institution_type | institution_type | CharField |  | choices=school, university, course_center |
| name | name | CharField |  |  |
| code | code | CharField |  | blank; default='' |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- unique_together: (country, institution_type, name)
- index: `<Index: fields=['country', 'institution_type', 'is_active'] name='org_inst_country_type_idx'>`

### `organizations_membership` — `organizations.Membership`
- Mənbə: `apps/organizations/models.py`:482`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `organizations.Membership.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| user_id | user | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| role_id | role | ForeignKey | ForeignKey → organizations_role (CASCADE) | index |
| scope_unit_id | scope_unit | ForeignKey | ForeignKey → organizations_orgunit (CASCADE) | index; nullable; blank |
| title | title | CharField |  | blank |
| employee_id | employee_id | CharField |  | blank |
| assigned_by_id | assigned_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| is_primary | is_primary | BooleanField |  | index; default=False |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- unique_together: (user, organization, role, scope_unit)
- index: `<Index: fields=['user', 'organization'] name='organizatio_user_id_a85932_idx'>`
- index: `<Index: fields=['organization', 'role'] name='organizatio_organiz_130fbf_idx'>`
- index: `<Index: fields=['user', 'is_primary'] name='organizatio_user_id_3055f4_idx'>`

### `organizations_organization` — `organizations.Organization`
- Mənbə: `apps/organizations/models.py`:94`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-root`; RLS policy: `no/not detected`
- Ownership chain: `organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| name | name | CharField |  |  |
| slug | slug | SlugField |  | unique; index |
| org_type | org_type | CharField |  | choices=university, school, course_center, individual |
| country | country | CharField |  | blank; default='' |
| organization_identifier | organization_identifier | CharField |  | blank; default='' |
| license_identifier | license_identifier | CharField |  | blank; default='' |
| logo | logo | FileField |  | nullable; blank |
| description | description | TextField |  | blank |
| email | email | CharField |  | blank |
| phone | phone | CharField |  | blank |
| address | address | TextField |  | blank |
| website | website | CharField |  | blank |
| owner_id | owner | ForeignKey | ForeignKey → auth_user (PROTECT) | index |
| enabled_apps | enabled_apps | JSONField |  | blank; default=list |
| settings | settings | JSONField |  | blank; default=dict |
| is_active | is_active | BooleanField |  | index; default=True |
| status | status | CharField |  | default='active'; choices=active, pending, suspended |
| suspended_at | suspended_at | DateTimeField |  | nullable; blank |
| suspension_reason | suspension_reason | TextField |  | blank; default='' |

### `organizations_orgunit` — `organizations.OrgUnit`
- Mənbə: `apps/organizations/models.py`:228`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `organizations.OrgUnit.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| order | order | PositiveIntegerField |  | index; default=0 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| parent_id | parent | ForeignKey | ForeignKey → organizations_orgunit (CASCADE) | index; nullable; blank |
| unit_type | unit_type | CharField |  | choices=rectorate, vice_rectorate, faculty, deanery, chair, department, specialty, lab |
| name | name | CharField |  |  |
| slug | slug | SlugField |  | index |
| code | code | CharField |  | blank |
| head_id | head | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| settings | settings | JSONField |  | blank; default=dict |
| level | level | PositiveIntegerField |  | index; default=0 |
| path | path | CharField |  | index; blank |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- unique_together: (organization, slug)
- index: `<Index: fields=['organization', 'unit_type'] name='organizatio_organiz_c7fd85_idx'>`
- index: `<Index: fields=['organization', 'parent'] name='organizatio_organiz_5303a2_idx'>`

### `organizations_role` — `organizations.Role`
- Mənbə: `apps/organizations/models.py`:450`
- Creation migration: `apps/organizations/migrations/0001_initial.py`
- Domen: Core / Tenant Management
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `organizations.Role.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| name | name | CharField |  |  |
| display_name | display_name | CharField |  |  |
| description | description | TextField |  | blank |
| level | level | PositiveIntegerField |  | index; default=50 |
| scope_type | scope_type | CharField |  | choices=organization, unit, course |
| permissions | permissions | JSONField |  | blank; default=list |
| is_system | is_system | BooleanField |  | default=False |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- unique_together: (organization, name)
- index: `<Index: fields=['organization', '-level'] name='organizatio_organiz_4831d9_idx'>`
- index: `<Index: fields=['organization', 'is_active'] name='organizatio_organiz_e166c4_idx'>`

## App: `projects`

### `projects_project` — `projects.Project`
- Mənbə: `apps/projects/models.py`:16`
- Creation migration: `apps/projects/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `projects.Project.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (CASCADE) | index |
| title | title | CharField |  |  |
| description | description | TextField |  | blank |
| start_date | start_date | DateTimeField |  |  |
| deadline | deadline | DateTimeField |  |  |
| max_attempts | max_attempts | PositiveIntegerField |  | default=1 |
| max_score | max_score | PositiveIntegerField |  | default=100 |
| status | status | CharField |  | default='active'; choices=active, inactive, archived |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |

Many-to-many:

| Field | Target | Through table | Through type |
| --- | --- | --- | --- |
| assigned_students | auth_user | projects_project_assigned_students | auto |

Constraints / indexes:
- index: `<Index: fields=['course', 'status', '-created_at'] name='project_course_status_idx'>`

### `projects_projectsubmission` — `projects.ProjectSubmission`
- Mənbə: `apps/projects/models.py`:95`
- Creation migration: `apps/projects/migrations/0001_initial.py`
- Domen: Assignments / Projects / Labs
- Primary key: `id` (BigAutoField)
- Tenant scope: `tenant-indirect`; RLS policy: `no/not detected`
- Ownership chain: `projects.ProjectSubmission.project -> projects.Project` → `projects.Project.course -> courses.Course` → `courses.Course.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| project_id | project | ForeignKey | ForeignKey → projects_project (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| content | content | TextField |  |  |
| file | file | FileField |  | nullable; blank |
| status | status | CharField |  | default='pending'; choices=pending, graded, rejected |
| grade | grade | DecimalField |  | nullable; blank |
| feedback | feedback | TextField |  | blank |
| submitted_at | submitted_at | DateTimeField |  | blank |
| graded_at | graded_at | DateTimeField |  | nullable; blank |
| graded_by_id | graded_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['project', 'status', '-submitted_at'] name='projsub_project_status_idx'>`
- index: `<Index: fields=['student', '-submitted_at'] name='projsub_student_idx'>`

## App: `registrar`

### `registrar_assessmentcomponent` — `registrar.AssessmentComponent`
- Mənbə: `apps/registrar/models/grading.py`:223`
- Creation migration: `apps/registrar/migrations/0015_assessmentcomponent_componentscore_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.AssessmentComponent.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| order | order | PositiveIntegerField |  | index; default=0 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| offering_id | offering | ForeignKey | ForeignKey → registrar_courseoffering (CASCADE) | index |
| name | name | CharField |  |  |
| max_score | max_score | PositiveSmallIntegerField |  | default=10 |
| rubric_id | rubric | ForeignKey | ForeignKey → registrar_rubric (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('offering', 'name') name='uniq_component_offering_name'>`
- index: `<Index: fields=['organization', 'offering'] name='registrar_a_organiz_ad70cd_idx'>`

### `registrar_assessmentscheme` — `registrar.AssessmentScheme`
- Mənbə: `apps/registrar/models/grading.py`:50`
- Creation migration: `apps/registrar/migrations/0006_courseoffering_instructor_assessmentscheme_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.AssessmentScheme.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| offering_id | offering | OneToOneField | OneToOne → registrar_courseoffering (CASCADE) | unique; index |
| entry_score_max | entry_score_max | PositiveSmallIntegerField |  | default=50 |
| pass_threshold | pass_threshold | PositiveSmallIntegerField |  | default=51 |
| min_final_exam_score | min_final_exam_score | PositiveSmallIntegerField |  | default=17 |
| is_published | is_published | BooleanField |  | default=False |
| approval_status | approval_status | CharField |  | index; default=ApprovalStatus.DRAFT; choices=draft, submitted, chair_approved, approved, returned |
| submitted_by_id | submitted_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| chair_approved_by_id | chair_approved_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| dean_approved_by_id | dean_approved_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| returned_reason | returned_reason | TextField |  | blank |

### `registrar_componentscore` — `registrar.ComponentScore`
- Mənbə: `apps/registrar/models/grading.py`:258`
- Creation migration: `apps/registrar/migrations/0006_courseoffering_instructor_assessmentscheme_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.ComponentScore.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| component_id | component | ForeignKey | ForeignKey → registrar_assessmentcomponent (CASCADE) | index |
| enrollment_id | enrollment | ForeignKey | ForeignKey → registrar_enrollment (CASCADE) | index |
| score | score | DecimalField |  | default=0 |
| entered_by_id | entered_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('component', 'enrollment') name='uniq_component_enrollment_score'>`
- index: `<Index: fields=['organization', 'enrollment'] name='registrar_c_organiz_587067_idx'>`

### `registrar_courseoffering` — `registrar.CourseOffering`
- Mənbə: `apps/registrar/models/academic.py`:228`
- Creation migration: `apps/registrar/migrations/0003_courseoffering_enrollment_groupelectivechoice_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.CourseOffering.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| subject_id | subject | ForeignKey | ForeignKey → registrar_subject (PROTECT) | index |
| period_id | period | ForeignKey | ForeignKey → organizations_academicperiod (PROTECT) | index |
| group_id | group | ForeignKey | ForeignKey → organizations_orgunit (CASCADE) | index; nullable; blank |
| course_id | course | ForeignKey | ForeignKey → courses_course (SET_NULL) | index; nullable; blank |
| instructor_id | instructor | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| lesson_hours | lesson_hours | PositiveSmallIntegerField |  | default=0 |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'subject', 'period', 'group') name='uniq_offering_subject_period_group'>`
- index: `<Index: fields=['organization', 'period'] name='registrar_c_organiz_8c8ef4_idx'>`

### `registrar_criterionscore` — `registrar.CriterionScore`
- Mənbə: `apps/registrar/models/grading.py`:285`
- Creation migration: `apps/registrar/migrations/0019_rubric_assessmentcomponent_rubric_rubriccriterion_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.CriterionScore.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| criterion_id | criterion | ForeignKey | ForeignKey → registrar_rubriccriterion (CASCADE) | index |
| enrollment_id | enrollment | ForeignKey | ForeignKey → registrar_enrollment (CASCADE) | index |
| points | points | DecimalField |  | default=0 |
| entered_by_id | entered_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('criterion', 'enrollment') name='uniq_criterion_enrollment_score'>`
- index: `<Index: fields=['organization', 'enrollment'] name='registrar_c_organiz_bf53cf_idx'>`

### `registrar_curriculum` — `registrar.Curriculum`
- Mənbə: `apps/registrar/models/academic.py`:95`
- Creation migration: `apps/registrar/migrations/0001_initial.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.Curriculum.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| program_id | program | ForeignKey | ForeignKey → registrar_program (CASCADE) | index |
| admission_year | admission_year | PositiveIntegerField |  |  |
| name | name | CharField |  | blank |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'program', 'admission_year') name='uniq_curriculum_program_year'>`

### `registrar_curriculumsubject` — `registrar.CurriculumSubject`
- Mənbə: `apps/registrar/models/academic.py`:126`
- Creation migration: `apps/registrar/migrations/0001_initial.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.CurriculumSubject.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| order | order | PositiveIntegerField |  | index; default=0 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| curriculum_id | curriculum | ForeignKey | ForeignKey → registrar_curriculum (CASCADE) | index |
| subject_id | subject | ForeignKey | ForeignKey → registrar_subject (PROTECT) | index |
| semester_number | semester_number | PositiveSmallIntegerField |  |  |
| is_elective | is_elective | BooleanField |  | index; default=False |
| elective_group | elective_group | CharField |  | blank |
| required_choices | required_choices | PositiveSmallIntegerField |  | default=1 |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'curriculum', 'subject', 'semester_number') name='uniq_curriculum_subject_semester'>`
- index: `<Index: fields=['curriculum', 'semester_number'] name='registrar_c_curricu_d66d74_idx'>`
- index: `<Index: fields=['curriculum', 'elective_group'] name='registrar_c_curricu_d5ed14_idx'>`

### `registrar_enrollment` — `registrar.Enrollment`
- Mənbə: `apps/registrar/models/academic.py`:285`
- Creation migration: `apps/registrar/migrations/0003_courseoffering_enrollment_groupelectivechoice_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.Enrollment.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| offering_id | offering | ForeignKey | ForeignKey → registrar_courseoffering (CASCADE) | index |
| kind | kind | CharField |  | default=EnrollmentKind.MANDATORY; choices=mandatory, elective, retake |
| status | status | CharField |  | index; default=Enrollment.Status.ENROLLED; choices=enrolled, completed, dropped |
| absence_hours | absence_hours | PositiveSmallIntegerField |  | default=0 |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'student', 'offering') name='uniq_student_offering'>`
- index: `<Index: fields=['organization', 'student'] name='registrar_e_organiz_06332c_idx'>`
- index: `<Index: fields=['offering', 'status'] name='registrar_e_offerin_315790_idx'>`

### `registrar_finalgrade` — `registrar.FinalGrade`
- Mənbə: `apps/registrar/models/grading.py`:319`
- Creation migration: `apps/registrar/migrations/0012_assessmentscheme_min_final_exam_score_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.FinalGrade.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| enrollment_id | enrollment | OneToOneField | OneToOne → registrar_enrollment (CASCADE) | unique; index |
| exam_score | exam_score | DecimalField |  | nullable; blank |
| bonus | bonus | DecimalField |  | default=0 |
| comment | comment | CharField |  | blank |
| is_published | is_published | BooleanField |  | default=False |
| entered_by_id | entered_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['organization', 'enrollment'] name='registrar_f_organiz_1ee27f_idx'>`

### `registrar_groupelectivechoice` — `registrar.GroupElectiveChoice`
- Mənbə: `apps/registrar/models/academic.py`:323`
- Creation migration: `apps/registrar/migrations/0003_courseoffering_enrollment_groupelectivechoice_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.GroupElectiveChoice.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| group_id | group | ForeignKey | ForeignKey → organizations_orgunit (CASCADE) | index |
| period_id | period | ForeignKey | ForeignKey → organizations_academicperiod (PROTECT) | index |
| elective_group | elective_group | CharField |  |  |
| chosen_subject_id | chosen_subject | ForeignKey | ForeignKey → registrar_subject (PROTECT) | index |
| decided_by_id | decided_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'group', 'period', 'elective_group') name='uniq_group_elective_block'>`

### `registrar_lesson` — `registrar.Lesson`
- Mənbə: `apps/registrar/models/grading.py`:97`
- Creation migration: `apps/registrar/migrations/0008_remove_gradecomponent_organization_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.Lesson.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| offering_id | offering | ForeignKey | ForeignKey → registrar_courseoffering (CASCADE) | index |
| date | date | DateField |  |  |
| kind | kind | CharField |  | default=LessonKind.LECTURE; choices=lecture, seminar, lab |
| topic | topic | CharField |  | blank |
| hours | hours | PositiveSmallIntegerField |  | default=2 |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['organization', 'offering', 'date'] name='registrar_l_organiz_7c6e08_idx'>`

### `registrar_lessonmark` — `registrar.LessonMark`
- Mənbə: `apps/registrar/models/grading.py`:127`
- Creation migration: `apps/registrar/migrations/0008_remove_gradecomponent_organization_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.LessonMark.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| lesson_id | lesson | ForeignKey | ForeignKey → registrar_lesson (CASCADE) | index |
| enrollment_id | enrollment | ForeignKey | ForeignKey → registrar_enrollment (CASCADE) | index |
| status | status | CharField |  | default=AttendanceStatus.PRESENT; choices=present, absent |
| score | score | DecimalField |  | nullable; blank |
| entered_by_id | entered_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('lesson', 'enrollment') name='uniq_lesson_enrollment_mark'>`
- index: `<Index: fields=['organization', 'enrollment'] name='registrar_l_organiz_f4590b_idx'>`

### `registrar_program` — `registrar.Program`
- Mənbə: `apps/registrar/models/academic.py`:24`
- Creation migration: `apps/registrar/migrations/0001_initial.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.Program.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| specialty_unit_id | specialty_unit | ForeignKey | ForeignKey → organizations_orgunit (SET_NULL) | index; nullable; blank |
| code | code | CharField |  |  |
| name | name | CharField |  |  |
| degree_level | degree_level | CharField |  | default=DegreeLevel.BACHELOR; choices=bachelor, master, phd |
| ects_total | ects_total | PositiveIntegerField |  | default=240 |
| absence_limit_percent | absence_limit_percent | PositiveSmallIntegerField |  | default=25 |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'code') name='uniq_program_code_per_org'>`

### `registrar_resitrecord` — `registrar.ResitRecord`
- Mənbə: `apps/registrar/models/grading.py`:367`
- Creation migration: `apps/registrar/migrations/0012_assessmentscheme_min_final_exam_score_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.ResitRecord.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| enrollment_id | enrollment | ForeignKey | ForeignKey → registrar_enrollment (CASCADE) | index |
| reason | reason | CharField |  | choices=absence, total, exam |
| status | status | CharField |  | default=ResitStatus.ELIGIBLE; choices=eligible, completed |
| resit_score | resit_score | DecimalField |  | nullable; blank |
| decided_by_id | decided_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('enrollment',) name='uniq_resit_per_enrollment'>`
- index: `<Index: fields=['organization', 'enrollment'] name='registrar_r_organiz_957295_idx'>`

### `registrar_rubric` — `registrar.Rubric`
- Mənbə: `apps/registrar/models/grading.py`:170`
- Creation migration: `apps/registrar/migrations/0019_rubric_assessmentcomponent_rubric_rubriccriterion_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.Rubric.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| name | name | CharField |  |  |
| description | description | CharField |  | blank; default='' |
| is_active | is_active | BooleanField |  | default=True |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'name') name='uniq_rubric_org_name'>`

### `registrar_rubriccriterion` — `registrar.RubricCriterion`
- Mənbə: `apps/registrar/models/grading.py`:197`
- Creation migration: `apps/registrar/migrations/0019_rubric_assessmentcomponent_rubric_rubriccriterion_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.RubricCriterion.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| rubric_id | rubric | ForeignKey | ForeignKey → registrar_rubric (CASCADE) | index |
| name | name | CharField |  |  |
| max_points | max_points | PositiveSmallIntegerField |  | default=5 |
| order | order | PositiveSmallIntegerField |  | default=0 |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('rubric', 'name') name='uniq_criterion_rubric_name'>`
- index: `<Index: fields=['organization', 'rubric'] name='registrar_r_organiz_b9fe30_idx'>`

### `registrar_scheduleslot` — `registrar.ScheduleSlot`
- Mənbə: `apps/registrar/models/academic.py`:377`
- Creation migration: `apps/registrar/migrations/0010_scheduleslot.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.ScheduleSlot.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| offering_id | offering | ForeignKey | ForeignKey → registrar_courseoffering (CASCADE) | index |
| weekday | weekday | PositiveSmallIntegerField |  |  |
| start_time | start_time | TimeField |  |  |
| end_time | end_time | TimeField |  |  |
| room | room | CharField |  | blank |
| week_type | week_type | CharField |  | default=WeekType.ALL; choices=all, odd, even |
| created_by_id | created_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['organization', 'offering', 'weekday'] name='registrar_s_organiz_f12378_idx'>`

### `registrar_studentacademicrecord` — `registrar.StudentAcademicRecord`
- Mənbə: `apps/registrar/models/academic.py`:185`
- Creation migration: `apps/registrar/migrations/0003_courseoffering_enrollment_groupelectivechoice_and_more.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.StudentAcademicRecord.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| student_id | student | ForeignKey | ForeignKey → auth_user (CASCADE) | index |
| program_id | program | ForeignKey | ForeignKey → registrar_program (PROTECT) | index |
| curriculum_id | curriculum | ForeignKey | ForeignKey → registrar_curriculum (PROTECT) | index |
| group_id | group | ForeignKey | ForeignKey → organizations_orgunit (SET_NULL) | index; nullable; blank |
| admission_year | admission_year | PositiveIntegerField |  |  |
| status | status | CharField |  | index; default=AcademicStatus.ENROLLED; choices=enrolled, academic_leave, expelled, graduated |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'student', 'program') name='uniq_student_program'>`
- index: `<Index: fields=['organization', 'group'] name='registrar_s_organiz_53ed8c_idx'>`

### `registrar_subject` — `registrar.Subject`
- Mənbə: `apps/registrar/models/academic.py`:69`
- Creation migration: `apps/registrar/migrations/0001_initial.py`
- Domen: Registrar / Journal
- Primary key: `id` (UUIDField)
- Tenant scope: `tenant-direct`; RLS policy: `yes`
- Ownership chain: `registrar.Subject.organization -> organizations.Organization`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| created_at | created_at | DateTimeField |  | blank |
| updated_at | updated_at | DateTimeField |  | blank |
| id | id | UUIDField |  | PK; unique; default=uuid4 |
| organization_id | organization | ForeignKey | ForeignKey → organizations_organization (CASCADE) | index |
| code | code | CharField |  |  |
| name | name | CharField |  |  |
| ects | ects | PositiveSmallIntegerField |  | default=5 |
| description | description | TextField |  | blank |
| is_active | is_active | BooleanField |  | index; default=True |

Constraints / indexes:
- constraint: `<UniqueConstraint: fields=('organization', 'code') name='uniq_subject_code_per_org'>`

## App: `sessions`

### `django_session` — `sessions.Session`
- Mənbə: `/Users/elvin/.pyenv/versions/3.11.6/lib/python3.11/site-packages/django/contrib/sessions/models.py`:8`
- Creation migration: `tapılmadı / contrib model`
- Domen: Django System
- Primary key: `session_key` (CharField)
- Tenant scope: `django-system/global`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| session_key | session_key | CharField |  | PK; unique |
| session_data | session_data | TextField |  |  |
| expire_date | expire_date | DateTimeField |  | index |

## App: `trial_exams`

### `trial_exams_trialexamrequest` — `trial_exams.TrialExamRequest`
- Mənbə: `apps/trial_exams/models.py`:38`
- Creation migration: `apps/trial_exams/migrations/0001_initial.py`
- Domen: Public Content and Requests
- Primary key: `id` (BigAutoField)
- Tenant scope: `user-owned/no-direct-org`; RLS policy: `no/not detected`
| Column | Field | Type | Relation | Attributes |
| --- | --- | --- | --- | --- |
| id | id | BigAutoField |  | PK; unique; blank |
| user_id | user | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |
| full_name | full_name | CharField |  |  |
| email | email | CharField |  |  |
| subject_name | subject_name | CharField |  |  |
| note | note | TextField |  | blank |
| questions_file | questions_file | FileField |  |  |
| original_filename | original_filename | CharField |  | blank |
| status | status | CharField |  | index; default='pending'; choices=pending, processing, added, rejected |
| ip_address | ip_address | GenericIPAddressField |  | nullable; blank |
| user_agent | user_agent | CharField |  | blank |
| is_handled | is_handled | BooleanField |  | default=False |
| created_at | created_at | DateTimeField |  | blank |
| handled_at | handled_at | DateTimeField |  | nullable; blank |
| reply_body | reply_body | TextField |  | blank |
| reply_from | reply_from | CharField |  | blank; choices=info, support |
| reply_delivery_status | reply_delivery_status | CharField |  | blank; choices=pending, sent, failed, recorded |
| reply_delivery_error | reply_delivery_error | CharField |  | blank |
| reply_sent_at | reply_sent_at | DateTimeField |  | nullable; blank |
| reply_sent_by_id | reply_sent_by | ForeignKey | ForeignKey → auth_user (SET_NULL) | index; nullable; blank |

Constraints / indexes:
- index: `<Index: fields=['-created_at'] name='trial_exams_created_6f7f34_idx'>`
- index: `<Index: fields=['status', '-created_at'] name='trial_exams_status_0806d1_idx'>`
- index: `<Index: fields=['is_handled', '-created_at'] name='trial_exams_is_hand_263044_idx'>`

## Avtomatik Many-to-Many Through Cədvəlləri
| Table | Auto model | FK columns | RLS |
| --- | --- | --- | --- |
| assignments_assignment_assigned_students | assignments.Assignment_assigned_students | assignment_id -> assignments_assignment; user_id -> auth_user | yes |
| auth_group_permissions | auth.Group_permissions | group_id -> auth_group; permission_id -> auth_permission | no/not detected |
| auth_user_groups | auth.User_groups | user_id -> auth_user; group_id -> auth_group | no/not detected |
| auth_user_user_permissions | auth.User_user_permissions | user_id -> auth_user; permission_id -> auth_permission | no/not detected |
| blog_question_visible_users | blog.Question_visible_users | question_id -> blog_question; user_id -> auth_user | no/not detected |
| courses_coursegroup_members | courses.CourseGroup_members | coursegroup_id -> courses_coursegroup; user_id -> auth_user | yes |
| exams_exam_allowed_groups | exams.Exam_allowed_groups | exam_id -> exams_exam; studentgroup_id -> exams_studentgroup | yes |
| exams_exam_allowed_users | exams.Exam_allowed_users | exam_id -> exams_exam; user_id -> auth_user | yes |
| exams_examanswer_selected_options | exams.ExamAnswer_selected_options | examanswer_id -> exams_examanswer; examquestionoption_id -> exams_examquestionoption | yes |
| exams_examroom_invigilators | exams.ExamRoom_invigilators | examroom_id -> exams_examroom; user_id -> auth_user | no/not detected |
| exams_examroomsession_staff | exams.ExamRoomSession_staff | examroomsession_id -> exams_examroomsession; user_id -> auth_user | no/not detected |
| exams_studentgroup_students | exams.StudentGroup_students | studentgroup_id -> exams_studentgroup; user_id -> auth_user | yes |
| exams_studentgroup_subjects | exams.StudentGroup_subjects | studentgroup_id -> exams_studentgroup; subject_id -> registrar_subject | no/not detected |
| exams_studentgroup_teachers | exams.StudentGroup_teachers | studentgroup_id -> exams_studentgroup; user_id -> auth_user | yes |
| labs_lab_allowed_students | labs.Lab_allowed_students | lab_id -> labs_lab; user_id -> auth_user | no/not detected |
| labs_labassignment_assigned_questions | labs.LabAssignment_assigned_questions | labassignment_id -> labs_labassignment; labquestion_id -> labs_labquestion | no/not detected |
| projects_project_assigned_students | projects.Project_assigned_students | project_id -> projects_project; user_id -> auth_user | no/not detected |
