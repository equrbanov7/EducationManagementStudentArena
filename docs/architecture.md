# EMS Arena Architecture Documentation

## Overview

EMS Arena is a multi-tenant education management system built with Django. It supports multiple organization types (universities, schools, course centers, and individuals) with flexible role-based access control.

## Application Structure

### Core Applications

#### `apps/organizations/`
Multi-tenant organization management system.

**Models:**
- `Organization`: Top-level organization entity
- `OrgUnit`: Hierarchical organizational units (faculties, departments, classes, etc.)
- `AcademicPeriod`: Academic periods (semesters, trimesters, quarters)
- `Role`: Role definitions with permissions
- `Membership`: User membership in organizations with roles

**Features:**
- Organization type-specific unit structures
- Materialized path for hierarchical units
- Flexible permission system with wildcards
- Default roles per organization type
- Organization-scoped middleware

#### `apps/audit/`
Audit logging system for tracking all user actions.

**Models:**
- `AuditLog`: Comprehensive audit log entries

**Features:**
- Automatic login/logout logging
- Generic foreign key support
- Change tracking (old/new values)
- IP address and user agent capture
- Request ID tracking

#### `apps/accounts/`
User authentication and profile management.

**Models:**
- Uses Django's built-in `User` model
- Extended with organization memberships

#### `apps/courses/`
Course management (existing).

#### `apps/exams/`
Exam and assessment management (existing).

#### `apps/assignments/`, `apps/projects/`, `apps/labs/`
Additional learning activities (existing).

#### `apps/blog/`
Communication and announcements (existing).

#### `apps/live_exam/`
Live exam hosting (existing).

### Core Module (`core/`)

Shared utilities and base models used across all apps.

**Base Models:**
- `TimeStampedModel`: Automatic created_at/updated_at timestamps
- `UUIDModel`: UUID primary keys
- `SoftDeleteModel`: Soft deletion support
- `TitleSlugModel`: Title and auto-generated slug
- `ActiveModel`: is_active field with custom manager
- `OrderedModel`: Order field for sorting

**Constants:**
- Organization types
- Unit types by organization
- Permission categories
- Academic period types
- Role scope types
- Audit action types

**Utilities:**
- `generate_unique_slug()`: Generate unique slugs
- `get_client_ip()`: Extract client IP from request
- OTP/PIN/code generators
- Email utilities

## Architecture Patterns

### Multi-Tenancy

Organizations are completely isolated at the database level. All content is scoped to an organization through foreign keys.

**Session-based Organization Selection:**
- Users can be members of multiple organizations
- Active organization stored in session
- Middleware loads organization context into request

### Permission System

**Hierarchical Permissions:**
- Wildcard support: `*` for all, `category.*` for category
- Permission categories: organization, structure, members, roles, courses, grading, exams, etc.
- Permission checking via decorators and mixins

**Role Levels:**
- Numeric levels (1-100) indicate hierarchy
- Higher levels can manage lower levels
- Default roles per organization type

### Hierarchical Organization Units

**Materialized Path Pattern:**
- `path` field stores full hierarchy (e.g., "uuid1/uuid2/uuid3")
- `level` field for depth
- Efficient ancestor/descendant queries

**Organization-Specific Types:**
- University: rectorate, faculty, deanery, chair, department, lab
- School: directorate, section, parallel, class, grade_level
- Course Center: branch, division, group, classroom
- Individual: basic unit structure

## Request Flow

1. **Request arrives** → Django middleware stack
2. **OrganizationMiddleware** → Loads organization context
   - Sets `request.organization`
   - Sets `request.org_memberships`
   - Sets `request.org_permissions`
3. **View processing** → Decorators check permissions
   - `@org_required`: Ensures organization selected
   - `@org_permission_required(perm)`: Checks permission
   - `@org_level_required(level)`: Checks role level
4. **Template rendering** → Context processors add organization data
   - `current_organization`
   - `user_organizations`
   - `user_permissions`
5. **Audit logging** → Actions logged via signals or explicit calls

## Deployment Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
┌──────▼──────────┐
│   Web Server    │
│  (Nginx/Apache) │
└──────┬──────────┘
       │
┌──────▼──────────┐
│  WSGI Server    │
│   (Gunicorn)    │
└──────┬──────────┘
       │
┌──────▼──────────┐
│  Django App     │
└──────┬──────────┘
       │
┌──────▼──────────┐
│   Database      │
│  (PostgreSQL)   │
└─────────────────┘
```

## Security Considerations

1. **Organization Isolation**: All queries scoped to organization
2. **Permission Checks**: Decorators on all sensitive views
3. **Audit Logging**: All actions logged with user/IP/timestamp
4. **Role Hierarchy**: Higher roles can only manage lower roles
5. **Session Security**: Organization context in secure session

## Scalability

- **Database**: Use PostgreSQL for production
- **Caching**: Redis for sessions and caching
- **Media Files**: S3 or CDN for uploaded files
- **Async Tasks**: Celery for background jobs
- **Search**: Elasticsearch for full-text search

## Development Guidelines

1. Always use base models from `core/` for consistency
2. Add audit logging to sensitive operations
3. Use decorators for permission checks
4. Test with multiple organization types
5. Follow Django best practices
6. Use type hints where beneficial
7. Write comprehensive docstrings
8. Keep functions small and focused (max ~20 lines)
