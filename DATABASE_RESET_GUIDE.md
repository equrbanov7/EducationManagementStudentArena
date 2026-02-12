# Database Reset Guide for Migration Issues

## Problem
If you encounter the error:
```
psycopg2.errors.DuplicateTable: relation "uniq_player_per_session_client" already exists
```

This means your database has a constraint that Django's migration system doesn't know about, creating a conflict.

## Solution 1: Reset PostgreSQL Database (Recommended for Test Environment)

Since you mentioned this is a test environment ("bu menimcun test hissesidi"), the cleanest approach is to reset the database completely:

### Step 1: Drop and Recreate Database

**Option A: Using psql command line**
```bash
# Connect to PostgreSQL
psql -U postgres

# Drop the database (replace 'emsarena' with your database name)
DROP DATABASE emsarena;

# Recreate it
CREATE DATABASE emsarena;

# Grant permissions (replace 'your_user' with your database user)
GRANT ALL PRIVILEGES ON DATABASE emsarena TO your_user;

# Exit psql
\q
```

**Option B: Using Django management command (if you have dropdb permissions)**
```bash
# This will drop all tables
python manage.py flush --no-input
```

### Step 2: Run Migrations Fresh
```bash
python manage.py migrate
```

## Solution 2: Manual Constraint Removal (If you want to keep data)

If you have important test data and want to keep it:

```bash
# Connect to PostgreSQL
psql -U postgres -d emsarena

# Remove the conflicting constraint
ALTER TABLE live_exam_liveplayer DROP CONSTRAINT IF EXISTS uniq_player_per_session_client;

# Exit psql
\q

# Now run migrations
python manage.py migrate
```

## Solution 3: Fake the Migration (Temporary fix)

If you just want to mark the migration as applied without running it:

```bash
# Mark live_exam migrations as applied without executing them
python manage.py migrate live_exam --fake

# Or fake just the initial migration
python manage.py migrate live_exam 0001 --fake-initial
```

## What Was Fixed

The migration had a redundant constraint definition:
- It was using both `AddConstraint` and `AlterUniqueTogether` for the same fields
- This created the constraint twice, causing conflicts

The fix removed the redundant `AlterUniqueTogether` operation, keeping only the modern `AddConstraint` approach.

## Best Practices Going Forward

1. **For Test/Development**: Always feel free to drop and recreate your database when you encounter migration conflicts
2. **For Production**: Use proper migration strategies and never drop databases
3. **Backup**: Even for test databases, keep a backup if you have valuable test data

## Quick Reset Script

Create a file `reset_db.sh`:
```bash
#!/bin/bash
echo "Dropping database..."
psql -U postgres -c "DROP DATABASE IF EXISTS emsarena;"
echo "Creating database..."
psql -U postgres -c "CREATE DATABASE emsarena;"
echo "Running migrations..."
python manage.py migrate
echo "Done!"
```

Make it executable:
```bash
chmod +x reset_db.sh
./reset_db.sh
```

## Verification

After resetting, verify everything works:
```bash
# Check Django configuration
python manage.py check

# Verify migrations are applied
python manage.py showmigrations

# Test the live_exam models
python manage.py shell
>>> from apps.live_exam.models import LiveSession, LivePlayer
>>> LivePlayer.objects.all()
```

## Need Help?

If you still encounter issues:
1. Check your database credentials in `.env` or settings
2. Ensure PostgreSQL is running
3. Verify you have the correct permissions
4. Check Django version compatibility
