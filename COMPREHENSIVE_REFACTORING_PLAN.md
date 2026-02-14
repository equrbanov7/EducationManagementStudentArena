# EMSArena Comprehensive Refactoring Plan

## Executive Summary

This document outlines a comprehensive refactoring plan for the EMSArena Django platform. The scope is extensive and will require multiple development sessions to complete properly.

---

## Scope Assessment

### Total Estimated Effort
- **Estimated Time:** 40-60 hours of development
- **Files to Modify:** 100+ files
- **New Files to Create:** 30+ files
- **Lines of Code:** 5,000+ lines

### Complexity Level
- **High Complexity Items:**
  - Multi-tenant isolation (affects all queries)
  - Organization-aware registration wizard
  - Pending review queue with grouping
  - RBAC enforcement across all views

- **Medium Complexity Items:**
  - Modern profile dashboard
  - Enhanced sidebar with badges
  - Assigned items views
  
- **Low Complexity Items:**
  - Static file cleanup
  - URL fixes
  - Template refactoring

---

## Phased Implementation Approach

### PHASE 1: Foundation & Critical Fixes (Session 1) 🔴 PRIORITY
**Estimated Time:** 8-12 hours

#### 1.1 Organization Model & Multi-Tenant Setup
- Create Organization model with country support
- Update UserProfile to link to Organization
- Create OrganizationMixin for query filtering
- Add tenant_id to all relevant models

**Files:**
- `core/models.py` (new Organization model)
- `apps/accounts/models.py` (update UserProfile)
- `core/mixins.py` (new OrganizationMixin)
- `apps/accounts/migrations/000X_add_organization.py`

#### 1.2 Fix Profile URL Conflicts
- Consolidate profile URLs (remove duplication)
- Update all template references
- Test navigation flows

**Files:**
- `apps/accounts/urls.py`
- `apps/blog/urls.py`
- `templates/partials/_navbar.html`
- All templates using `user_profile` URL

#### 1.3 Basic Static File Cleanup
- Remove inline CSS/JS from critical templates
- Consolidate duplicate CSS rules
- Move JS to separate files

**Files:**
- `templates/base.html`
- `templates/partials/_navbar.html`
- `static/css/main.css` (consolidate)
- `static/js/main.js` (consolidate)

---

### PHASE 2: Modern Profile Dashboard (Session 2)
**Estimated Time:** 6-8 hours

#### 2.1 Profile Dashboard Template
- Create new profile template with collapsible sidebar
- Sidebar open by default with toggle
- Sections: Overview, Posts, Exams, Courses
- Desktop: compact collapse, Mobile: overlay drawer

**Files:**
- `apps/accounts/templates/accounts/profile_dashboard.html` (new)
- `static/css/profile_dashboard.css` (new)
- `static/js/profile_sidebar.js` (new)

#### 2.2 Profile Views Enhancement
- Update user_profile view
- Add section routing
- Calculate badge counts
- Enforce readonly field protection

**Files:**
- `apps/accounts/views.py` (update user_profile)
- `apps/accounts/forms.py` (add ProfileUpdateForm)

---

### PHASE 3: Registration Wizard (Session 3)
**Estimated Time:** 8-10 hours

#### 3.1 Multi-Step Registration
- Step 1: Country selection
- Step 2: Account type selection
- Step 3: Organization selection (filtered)
- Handle "Other" option with manual entry

**Files:**
- `apps/accounts/views/registration.py` (new)
- `apps/accounts/forms/registration.py` (new)
- `apps/accounts/templates/accounts/registration/` (new directory)
  - `step1_country.html`
  - `step2_account_type.html`
  - `step3_organization.html`
  - `step4_details.html`
- `static/js/registration_wizard.js` (new)
- `static/css/registration_wizard.css` (new)

#### 3.2 Organization Data Integration
- Create Organization fixtures for testing
- API endpoint for filtered organization lookup
- Save organization data to profile

**Files:**
- `apps/accounts/fixtures/organizations.json` (new)
- `apps/accounts/api/views.py` (new)
- `apps/accounts/api/serializers.py` (new)

---

### PHASE 4: Pending Review Queue (Session 4)
**Estimated Time:** 8-10 hours

#### 4.1 Pending Review Feature
- Create PendingReview service layer
- Group by "Qruplar" with expandable sections
- Search functionality
- Filters (Type, Status, Sort)
- Quick actions

**Files:**
- `apps/accounts/views/pending_review.py` (new)
- `apps/accounts/services/pending_review_service.py` (new)
- `apps/accounts/templates/accounts/pending_review.html` (new)
- `static/css/pending_review.css` (new)
- `static/js/pending_review.js` (new)

#### 4.2 Integration Points
- Link from sidebar with badge
- Calculate pending count
- Group by course groups
- Tenant-aware queries

---

### PHASE 5: Enhanced Sidebar & Assigned Items (Session 5)
**Estimated Time:** 6-8 hours

#### 5.1 Sidebar Menu Enhancement
- Group menu items (Overview, Learning, Assigned, Account)
- Add badge counts for all items
- Show disabled state for zero counts
- Mobile-responsive drawer

**Files:**
- `templates/partials/_sidebar.html` (new)
- `apps/accounts/context_processors.py` (new, for badge counts)
- `static/css/sidebar.css` (new)
- `static/js/sidebar.js` (new)

#### 5.2 Assigned Items Views
- "Assigned Exams" list view
- "Assigned Courses" list view
- Search, filter, pagination
- Cards with status

**Files:**
- `apps/accounts/views/assigned_items.py` (new)
- `apps/accounts/templates/accounts/assigned_exams.html` (new)
- `apps/accounts/templates/accounts/assigned_courses.html` (new)

---

### PHASE 6: Organization Management & RBAC (Session 6)
**Estimated Time:** 10-12 hours

#### 6.1 Organization Admin Panel
- User invitation system
- Role assignment interface
- Enforce role hierarchy
- "Create user without signup"
- Audit trail

**Files:**
- `apps/accounts/views/organization_admin.py` (new)
- `apps/accounts/templates/accounts/organization_admin/` (new directory)
  - `dashboard.html`
  - `invite_user.html`
  - `manage_roles.html`
  - `audit_log.html`
- `apps/accounts/models.py` (add AuditLog model)

#### 6.2 RBAC Enforcement
- Update all views with organization checks
- Add OrganizationPermissionMixin
- Update querysets for tenant isolation
- Test permission boundaries

**Files:**
- `core/mixins.py` (add OrganizationPermissionMixin)
- All view files (add permission checks)

---

### PHASE 7: Testing & Quality Assurance (Session 7)
**Estimated Time:** 4-6 hours

#### 7.1 Code Quality
- Run black and isort on all code
- Fix any flake8 issues
- Remove unused imports

#### 7.2 Manual Testing
- Test registration flow end-to-end
- Test profile dashboard on desktop/mobile
- Test sidebar collapse/expand
- Test pending review queue
- Test assigned items
- Test multi-tenant isolation
- Test all permission checks

#### 7.3 Documentation & Screenshots
- Take screenshots of all UI changes
- Update README
- Create user guide
- Create admin guide

---

## Current Status (Session 1)

### ✅ Completed
- Comprehensive planning document created
- Architecture analysis complete
- No duplicate *_2 files found (good!)
- Identified profile URL conflicts

### 🔄 In Progress
- Organization model design
- Profile dashboard wireframe

### ⏳ Pending
- All other phases (2-7)

---

## Key Decision Points

### 1. Profile URL Strategy
**Options:**
A. Keep both `accounts:profile` (own) and `blog:user_profile` (public)
B. Merge into single URL with permission check
C. Redirect old URLs to new

**Recommendation:** Option A - Keep separate for clarity

### 2. Organization Model Location
**Options:**
A. In `core/models.py` (shared across apps)
B. In `apps/accounts/models.py` (accounts-focused)
C. Separate `apps/organizations/` app

**Recommendation:** Option A - Core model for reuse

### 3. Registration Wizard Implementation
**Options:**
A. Django FormWizard (built-in)
B. Custom multi-step with session
C. JavaScript SPA with Django API

**Recommendation:** Option A - Django FormWizard (reliable)

### 4. Sidebar Implementation
**Options:**
A. Server-side rendering with JS enhancement
B. React/Vue component
C. Pure JavaScript with templates

**Recommendation:** Option A - Progressive enhancement

---

## Risk Assessment

### High Risk Items
1. **Multi-tenant isolation** - Breaking existing functionality
   - Mitigation: Gradual rollout, feature flags, extensive testing

2. **Data migration** - Organization assignment for existing users
   - Mitigation: Write migration scripts, backup database, dry-run

3. **Permission changes** - Breaking existing access patterns
   - Mitigation: Audit all views, add compatibility layer

### Medium Risk Items
1. **UI/UX changes** - User confusion with new layout
   - Mitigation: User testing, gradual rollout, help documentation

2. **Performance** - Additional queries for organization filtering
   - Mitigation: Database indexing, query optimization, caching

### Low Risk Items
1. **Static file cleanup** - Minimal risk
2. **URL changes** - Can add redirects
3. **Template updates** - Easy to rollback

---

## Resource Requirements

### Development Environment
- Python 3.11+
- Django 4.2+
- PostgreSQL 14+ (for multi-tenant)
- Redis (for caching)

### Testing Environment
- Selenium for UI testing
- Pytest for unit tests
- Coverage.py for code coverage

### Deployment Considerations
- Database backup before migration
- Feature flags for gradual rollout
- Monitoring for performance regression
- User communication plan

---

## Success Criteria

### Phase 1 Success
- [ ] Organization model created and migrated
- [ ] Profile URL conflicts resolved
- [ ] No regression in existing functionality

### Full Project Success
- [ ] All 7 phases completed
- [ ] 90%+ test coverage
- [ ] Zero security vulnerabilities
- [ ] <200ms page load times
- [ ] Mobile responsive (all pages)
- [ ] Positive user feedback
- [ ] Zero critical bugs in production

---

## Next Steps

1. **Immediate (This Session):**
   - Create Organization model
   - Fix profile URL conflicts
   - Start profile dashboard template

2. **Short Term (Next Session):**
   - Complete profile dashboard
   - Start registration wizard

3. **Medium Term (Following Sessions):**
   - Implement pending review queue
   - Enhance sidebar with badges
   - Build organization admin panel

4. **Long Term:**
   - Full multi-tenant rollout
   - Advanced RBAC features
   - Analytics dashboard

---

## Contact & Support

For questions or clarifications on this refactoring plan, please contact the development team.

**Last Updated:** 2026-02-14
**Version:** 1.0
**Status:** In Progress - Phase 1
