# EMS Arena API Documentation

## Overview

This document outlines the main API endpoints and URL patterns for EMS Arena, including the organization management system, permission decorators, and audit logging.

## URL Structure

- `/admin/` - Django admin interface
- `/organizations/` - Organization management
- `/organizations/select/` - Select active organization  
- `/organizations/switch/<slug>/` - Switch to organization
- `/audit/` - Audit log viewing (to be implemented)
- `/courses/` - Course management (existing)
- `/exams/` - Exam system (existing)
- `/assignments/` - Assignment management (existing)

## Authentication & Permissions

All organization views require authentication. Permission checks are performed via decorators:

- `@org_required` - Ensures user has active organization
- `@org_permission_required(permission)` - Checks specific permission
- `@org_level_required(level)` - Checks minimum role level
- `@org_role_required(roles)` - Checks for specific roles

## Session Management

- `active_organization` - Stores slug of active organization in session
- Middleware automatically loads organization context on each request

## For detailed API information, see:
- `architecture.md` - System architecture and request flow
- `models.md` - Database models and relationships
