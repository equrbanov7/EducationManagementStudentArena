# Migration Fix: live_exam.0001_initial

## Problem
After refactoring the project structure from `liveExam` to `live_exam`, migrations failed with:
```
ValueError: Related model 'liveExam.livesession' cannot be resolved
```

## Root Cause
The migration file `apps/live_exam/migrations/0001_initial.py` contained hardcoded references to the old app name `liveExam` in ForeignKey relationships:
- `to="liveExam.livesession"`
- `to="liveExam.liveplayer"`

These needed to be updated to use the new app label `live_exam`.

## Solution
Updated all ForeignKey references in the migration file from `liveExam` to `live_exam`:

**Lines changed:**
- Line 110: `to="liveExam.livesession"` → `to="live_exam.livesession"`
- Line 139: `to="liveExam.liveplayer"` → `to="live_exam.liveplayer"`
- Line 147: `to="liveExam.livesession"` → `to="live_exam.livesession"`

## Verification
✅ All migrations now apply successfully:
```bash
python manage.py migrate
```

✅ Django system check passes:
```bash
python manage.py check
# System check identified no issues (0 silenced).
```

✅ Models are accessible and working:
- `apps.live_exam.models.LiveSession`
- `apps.live_exam.models.LivePlayer`
- `apps.live_exam.models.LiveAnswer`

## Notes
Other references to "liveExam" in the codebase are intentional and should NOT be changed:
- `app_name = "liveExam"` in `urls.py` - URL namespace for backward compatibility
- Template paths like `"liveExam/host_lobby.html"` - actual directory structure
- `PLAYER_TOKEN_SALT = "liveExam.player"` - string constant for token generation

## Testing
To test from scratch:
```bash
rm db.sqlite3
python manage.py migrate
```

All migrations should complete successfully.
