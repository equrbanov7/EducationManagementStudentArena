# Organization System - Complete Guide

## Overview

The EMS Arena now includes a complete multi-tenant organization management system with role-based access control, hierarchical organizational units, and comprehensive audit logging.

## Features

### ✅ Sprint 2-5 (Core Infrastructure)
- Multi-tenant organization system
- Hierarchical organizational units (materialized path)
- Role-based permission system with wildcards
- Organization-scoped middleware
- Permission decorators and mixins
- Context processors and template tags
- Audit logging system
- User extension functions

### ✅ Sprint 6 (Dashboard & Management)
- Organization dashboard with statistics
- Organizational structure management with tree view
- Member management with filters and search
- Role & permissions management
- Organization settings page
- Sample data creation command

## Quick Start

### 1. Run Migrations

```bash
python manage.py migrate
```

### 2. Create Sample Organizations

```bash
python manage.py create_sample_orgs --username=admin
```

This creates:
- **Sample University** (with rector role)
- **Sample High School** (with director role)
- **Sample Course Center** (with manager role)

Default credentials: `admin` / `admin123`

### 3. Access the System

1. Login: `/blog/login/`
2. Select Organization: `/organizations/select/`
3. Dashboard: `/organizations/<slug>/`

## Organization Types

### University
**Units:** rectorate, vice_rectorate, faculty, deanery, chair, department, lab, institute, center

**Default Roles:**
- Rector (Level 100) - Full access
- Vice Rector (Level 90)
- Dean (Level 80)
- Department Chair (Level 70)
- Teacher (Level 50)
- Teaching Assistant (Level 40)
- Student (Level 10)

### School
**Units:** directorate, section, parallel, class, grade_level

**Default Roles:**
- Director (Level 100)
- Deputy Director (Level 90)
- Section Head (Level 70)
- Teacher (Level 50)
- Student (Level 10)

### Course Center
**Units:** branch, division, group, classroom

**Default Roles:**
- Center Manager (Level 100)
- Branch Manager (Level 80)
- Instructor (Level 50)
- Student (Level 10)

## Permission System

### Permission Categories

- **organization**: org.view, org.edit, org.settings, org.delete
- **structure**: unit.view, unit.create, unit.edit, unit.delete
- **members**: member.view, member.invite, member.edit, member.remove
- **roles**: role.view, role.create, role.edit, role.assign, role.delete
- **courses**: course.view, course.create, course.edit, course.delete
- **grading**: grade.view, grade.input, grade.publish, grade.override
- **exams**: exam.view, exam.create, exam.edit, exam.host, exam.delete
- **appeal**: appeal.create, appeal.respond, appeal.decide
- **analytics**: analytics.view_own, analytics.view_unit, analytics.view_all
- **qa**: qa.view, qa.review, qa.flag
- **audit**: audit.view, audit.export

### Wildcard Support

- `*` - All permissions
- `category.*` - All permissions in a category (e.g., `course.*`)
- Exact match - Specific permission (e.g., `course.create`)

### Using Permissions in Views

#### Function-Based Views

```python
from apps.organizations.decorators import org_required, org_permission_required

@org_required
def my_view(request):
    # Organization is available in request.organization
    pass

@org_permission_required('course.create')
def create_course(request):
    # Only users with course.create permission can access
    pass
```

#### Class-Based Views

```python
from apps.organizations.decorators import PermissionRequiredMixin

class CreateCourseView(PermissionRequiredMixin, CreateView):
    permission_required = 'course.create'
    # ...
```

#### In Templates

```django
{% load org_tags %}

{% has_perm 'course.create' as can_create %}
{% if can_create %}
    <button>Create Course</button>
{% endif %}
```

## Organizational Structure

### Creating Units

```python
from apps.organizations.models import Organization, OrgUnit

org = Organization.objects.get(slug='sample-university')

# Create a faculty
faculty = OrgUnit.objects.create(
    organization=org,
    unit_type='faculty',
    name='Faculty of Computer Science',
    slug='cs-faculty'
)

# Create a department under the faculty
department = OrgUnit.objects.create(
    organization=org,
    parent=faculty,
    unit_type='department',
    name='Software Engineering',
    slug='software-engineering'
)
```

### Hierarchy Methods

```python
# Get ancestors
ancestors = unit.get_ancestors()

# Get descendants
descendants = unit.get_descendants()

# Get direct children
children = unit.get_children()

# Get full path
path = unit.get_full_path()  # "Faculty / Department / Lab"
```

## Managing Members

### Adding Members

```python
from apps.organizations.models import Membership, Role

role = org.roles.get(name='teacher')

membership = Membership.objects.create(
    user=user,
    organization=org,
    role=role,
    scope_unit=department,  # Optional: scope to specific unit
    is_primary=True
)
```

### Checking Permissions

```python
from apps.organizations.user_extensions import has_org_permission

if has_org_permission(user, org, 'course.create'):
    # User can create courses
    pass
```

## Audit Logging

### Automatic Logging

The system automatically logs:
- User login/logout
- Organization creation
- Role assignments
- Membership changes

### Manual Logging

```python
from apps.audit.utils import log_action
from core.constants import AuditAction

log_action(
    action=AuditAction.CREATE,
    user=request.user,
    organization=request.organization,
    obj=course,
    new_values={'name': course.name},
    reason="Created new course",
    request=request
)
```

## Middleware

The `OrganizationMiddleware` adds to every request:

- `request.organization` - Active Organization or None
- `request.org_memberships` - User's memberships in active org
- `request.org_permissions` - List of permission strings

## URL Patterns

```
/organizations/select/                    - Organization selector
/organizations/switch/<slug>/             - Switch to organization
/organizations/<slug>/                    - Dashboard
/organizations/<slug>/structure/          - Structure management
/organizations/<slug>/members/            - Member management
/organizations/<slug>/roles/              - Role management
/organizations/<slug>/settings/           - Settings
```

## Admin Interface

All models are available in Django admin:
- Organizations
- Organizational Units (with tree view)
- Roles
- Memberships
- Academic Periods
- Audit Logs

## API

### User Extension Functions

```python
from apps.organizations import user_extensions

# Get user's organizations
orgs = user_extensions.get_organizations(user)

# Get user's memberships
memberships = user_extensions.get_memberships(user, org)

# Get user's permissions
perms = user_extensions.get_permissions(user, org)

# Get primary organization
primary = user_extensions.get_primary_organization(user)

# Check permission
has_perm = user_extensions.has_org_permission(user, org, 'course.create')
```

## Testing

### Run Tests

```bash
# All organization tests
python manage.py test apps.organizations

# Just permission tests
python manage.py test apps.organizations.tests.test_permissions
```

### Create Test Data

```bash
python manage.py create_sample_orgs --username=testuser
```

## Documentation

- `docs/architecture/architecture.md` - System architecture
- `docs/architecture/models.md` - Model relationships with ER diagrams
- `docs/api/api.md` - API documentation

## Security

- ✅ CodeQL scan: 0 vulnerabilities
- ✅ All permissions validated
- ✅ Audit logging enabled
- ✅ Role-based access control
- ✅ Organization isolation

## Support

For issues or questions:
1. Check the documentation in `docs/`
2. Review the admin interface for configuration
3. Check audit logs for troubleshooting
