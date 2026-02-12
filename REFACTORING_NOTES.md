# EMS Arena - Django Best Practice Refactoring

## Overview
This document outlines the major refactoring completed to bring the EMS Arena project in line with Django best practices and industry standards.

## What Changed

### 1. Settings Structure
**Before:**
```
emsarena/settings.py  # Single settings file
```

**After:**
```
config/
├── settings/
│   ├── __init__.py
│   ├── base.py       # Common settings
│   ├── local.py      # Development
│   ├── production.py # Production
│   └── test.py       # Testing
├── urls.py
├── wsgi.py
└── asgi.py
```

**Benefits:**
- Environment-specific configurations
- Better security (production vs development)
- Easier deployment management

### 2. Apps Organization
**Before:**
```
accounts/
courses/
exams/
liveExam/  # Mixed naming convention
...
```

**After:**
```
apps/
├── accounts/
├── courses/
├── exams/
├── assignments/
├── labs/
├── live_exam/  # Consistent snake_case
├── projects/
└── blog/
```

**Benefits:**
- All apps in one location
- Consistent naming (snake_case)
- Clear namespace separation

### 3. Core Module
**New structure:**
```
core/
├── models.py        # TimeStampedModel, UUIDModel, SoftDeleteModel, TitleSlugModel
├── mixins.py        # TeacherRequiredMixin, StudentRequiredMixin, OwnerRequiredMixin
├── permissions.py   # is_teacher(), is_student(), decorators
├── utils.py         # generate_otp(), generate_pin(), send_template_email()
├── validators.py    # Custom validators
├── exceptions.py    # Custom exceptions
└── constants.py     # UserRole, ExamType, SubmissionStatus, QuestionType
```

**Benefits:**
- Reusable components across apps
- DRY principle
- Centralized business logic

### 4. Requirements Management
**Before:**
```
requirements.txt  # All dependencies in one file
```

**After:**
```
requirements/
├── base.txt        # Core dependencies
├── local.txt       # Development tools (black, isort, pytest, etc.)
├── production.txt  # Production server (gunicorn)
└── test.txt        # Testing tools
```

**Benefits:**
- Environment-specific dependencies
- Faster CI/CD (only install what's needed)
- Clear separation of concerns

### 5. Project Structure
**New additions:**
```
templates/          # Global templates
static/             # Global static files
tests/              # Integration tests with fixtures
scripts/            # Utility scripts (create_groups.py, seed_data.py)
docker/             # Docker configuration
docs/               # Documentation (api.md, deployment.md)
```

## Usage

### Development
```bash
# Install dependencies
pip install -r requirements/local.txt

# Run with local settings
python manage.py runserver
```

### Production
```bash
# Install dependencies
pip install -r requirements/production.txt

# Set environment
export DJANGO_SETTINGS_MODULE=config.settings.production

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic

# Run with gunicorn
gunicorn config.wsgi:application
```

### Testing
```bash
# Install test dependencies
pip install -r requirements/test.txt

# Run tests
pytest
```

## Import Changes

All imports have been updated to use the new `apps.*` structure:

**Before:**
```python
from courses.models import Course
from exams.models import Exam
from liveExam.models import LiveSession
```

**After:**
```python
from apps.courses.models import Course
from apps.exams.models import Exam
from apps.live_exam.models import LiveSession
```

## Migration Notes

- Two new migrations were created to handle the app name changes:
  - `apps/labs/migrations/0002_*.py`
  - `apps/live_exam/migrations/0002_*.py`
- All existing migrations remain valid
- No data migration required

## Configuration Updates

### manage.py
```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
```

### CI/CD (.github/workflows/ci.yml)
- Updated `DJANGO_SETTINGS_MODULE` to `config.settings.test`
- Updated requirements paths to use `requirements/test.txt`

### pytest Configuration
- Updated to use `config.settings.test`
- Test paths include both `tests/` and `apps/`

## Verification

All checks pass:
- ✅ Django system check: No issues
- ✅ Migrations check: Valid
- ✅ Static files collection: 195 files collected
- ✅ Code formatting: black and isort compliant
- ✅ Import paths: All updated successfully

## Next Steps

1. Update any deployment scripts to use new structure
2. Update documentation with new import paths
3. Train team members on new structure
4. Update any external tools/scripts that reference old paths

## Rollback (if needed)

If you need to rollback:
1. Checkout the commit before this refactoring
2. No database changes were made, so no data loss risk

## Questions?

For questions about the new structure, refer to:
- Django documentation on project layout
- Two Scoops of Django (best practices book)
- This document's examples above
