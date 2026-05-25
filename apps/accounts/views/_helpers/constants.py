"""
Shared constants for account view helpers.

Single source of truth for filter choices, role label maps, review-window
durations and operation-token settings used across the ``_helpers`` package.
"""

from datetime import timedelta

from django.core.signing import TimestampSigner

from core.helpers import REVIEW_EDIT_LOCK_WINDOW

from ...models import ProfileRole

# Avatar limits live in services.profile_actions (single source of truth).
# Re-exported here so existing `from views._helpers import ...` callers keep working.
from ...services.profile_actions import (  # noqa: F401
    MAX_PROFILE_AVATAR_SIZE_BYTES,
    PROFILE_AVATAR_ALLOWED_EXTENSIONS,
)

signer = TimestampSigner()

# --- Filter choices ---------------------------------------------------------
RESULT_FILTER_CHOICES = {"all", "exams", "courses", "labs", "independent"}
PENDING_ANSWER_FILTER_CHOICES = RESULT_FILTER_CHOICES | {"written_exams", "practical_exams"}
PENDING_REVIEW_TYPE_CHOICES = {"all", "exams", "assignments", "projects", "labs"}
PENDING_REVIEW_STATUS_CHOICES = {"all", "submitted", "expired", "pending", "late"}

# --- Profile role label maps ------------------------------------------------
PROFILE_ROLE_LABELS = dict(ProfileRole.CHOICES)
PROFILE_ROLE_NAMES = set(PROFILE_ROLE_LABELS.keys())
PROFILE_ROLE_NAMES_MANAGEABLE = PROFILE_ROLE_NAMES - {ProfileRole.SUPERADMIN, ProfileRole.ORG_OWNER}

# --- Review window ----------------------------------------------------------
REVIEW_EDIT_WINDOW_MINUTES = int(REVIEW_EDIT_LOCK_WINDOW.total_seconds() // 60)
REVIEW_EDIT_WINDOW = timedelta(minutes=REVIEW_EDIT_WINDOW_MINUTES)

# --- Student organization management ----------------------------------------
STUDENT_ORG_MANAGEMENT_MIN_LEVEL = ProfileRole.LEVELS.get(ProfileRole.HR, 65)
STUDENT_PENDING_INVITE_TITLE = "__student_pending_invite__"
STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH = 280
STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT = 50

# --- Role assignment operation token ----------------------------------------
ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT = "accounts.role_assignment.operation"  # nosec B105
ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS = 60 * 5
