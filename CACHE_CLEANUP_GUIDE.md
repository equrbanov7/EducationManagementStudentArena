# Python Cache Cleanup Guide

## Issue

After deleting root-level `accounts/` and `assignments/` directories (keeping only `apps/accounts/` and `apps/assignments/`), you may encounter import errors when starting the Django development server:

```
ImportError: Couldn't import Django...
ModuleNotFoundError: No module named '...'
```

Or during URL loading:

```
Exception in thread django-main-thread:
Traceback (most recent call last):
  ...
  File ".../django/urls/resolvers.py", line 711, in urlconf_module
    return import_module(self.urlconf_name)
```

## Root Cause

Python caches compiled bytecode in `__pycache__/` directories and `.pyc` files. When you delete a module directory, these cache files may remain and cause Python to attempt importing from the deleted location, resulting in import errors.

## Solution

### Quick Fix

Run these commands in your project root directory:

```bash
# Remove all Python cache files
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type f -name '*.pyc' -delete 2>/dev/null
find . -type f -name '*.pyo' -delete 2>/dev/null

# Restart your development server
python manage.py runserver
```

### For Windows Users

```cmd
# PowerShell
Get-ChildItem -Path . -Include __pycache__ -Recurse -Force | Remove-Item -Force -Recurse
Get-ChildItem -Path . -Include *.pyc -Recurse -Force | Remove-Item -Force

# Then restart
python manage.py runserver
```

### Alternative: Use pyclean

If you have `pyclean` installed (part of `python3-debian` package on Linux):

```bash
pyclean .
python manage.py runserver
```

## Prevention

The `.gitignore` file already includes rules to prevent cache files from being committed:

```
__pycache__/
*.py[cod]
*$py.class
*.pyo
*.pyd
```

However, local cache files in your working directory are not automatically cleaned when folders are deleted.

## When to Clean Cache

Clean Python cache whenever you:

1. Delete module directories
2. Rename packages or modules
3. Restructure the codebase
4. Experience strange import errors after pulling updates
5. Switch between branches with different module structures

## Verification

After cleaning cache, verify everything works:

```bash
# Run Django system checks
python manage.py check

# Try importing the main URL configuration
python manage.py shell -c "from config import urls; print('URLs loaded successfully')"

# Start development server
python manage.py runserver
```

## Additional Notes

- Cache files are automatically regenerated when you run Python again
- It's safe to delete cache files at any time - they're just optimizations
- If you're using Docker, you may need to rebuild your container after major structural changes
- In production with gunicorn/uwsgi, restart your application server after structural changes

## Related Changes

This guide was created after the cleanup task that removed:
- Root-level `assignments/` directory (commit 896e791)
- Root-level `accounts/` directory (commit 896e791)
- Duplicate code and constants across the codebase

All functionality has been preserved in the proper `apps/` directory structure.
