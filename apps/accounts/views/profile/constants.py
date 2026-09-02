"""
Constants for the profile views package.

Length limits, validation regexes and section-name sets used by the
``user_profile`` orchestrator and the public-profile view.
"""

import re

PUBLIC_PROFILE_SEARCH_MAX_LENGTH = 100
PUBLIC_PROFILE_CATEGORY_MAX_LENGTH = 120
PROFILE_AVATAR_VERSION_MAX_LENGTH = 64

PUBLIC_PROFILE_PAGE_NUMBER_PATTERN = re.compile(r"^[0-9]+$")
PUBLIC_PROFILE_ALLOWED_QUERY_PUNCTUATION = frozenset({" ", "-", "_", ".", ",", "@", "#", "+"})
PUBLIC_PROFILE_FORMAT_SPECIFIER_PATTERN = re.compile(r"%(?:\d+\$)?[-+#0*. ]*[a-zA-Z]")
PUBLIC_PROFILE_CATEGORY_PATTERN = re.compile(r"^[a-z0-9_-]{1,%s}$" % PUBLIC_PROFILE_CATEGORY_MAX_LENGTH)
PROFILE_AVATAR_VERSION_PATTERN = re.compile(r"^[0-9]{1,%s}$" % PROFILE_AVATAR_VERSION_MAX_LENGTH)

#: Kabinetin DEFAULT açılış bölməsi (FAZA 22).  Əvvəl `profile-info` idi —
#: yəni hər rol kabinetə öz doğum tarixi ilə girirdi.  `?section=profile-info`
#: əvvəlki kimi işləyir; dəyişən yalnız parametrsiz açılışın hədəfidir.
DEFAULT_PROFILE_SECTION = "dashboard"

#: Default hədəf `allowed_sections`-da yoxdursa (nəzəri hal) bura düşülür.
FALLBACK_PROFILE_SECTION = "profile-info"

# Sections that require an active organization context to render correctly.
PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT = {
    "dashboard",
    "profile-info",
    "courses",
    "assigned-exams",
    "assigned-courses",
    "my-results",
    "pending-answers",
    "groups",
    "my-courses",
    "my-exams",
    "pending-post-approvals",
    "pending-review",
    "review-results",
    "role-assignment",
    "student-organization-management",
    "permission-editor",
    "manage-roles",
    "org-structure",
    "org-faculties",
    "org-kafedras",
    "org-members",
    "org-roles",
    "audit-log",
    "publish-notification",
    "statistics",
}

# Sections where a multi-org profile may fall back to the profile organization.
PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK = {
    "groups",
    "my-courses",
    "my-exams",
    "courses",
    "pending-post-approvals",
    "pending-review",
    "review-results",
    "role-assignment",
    "student-organization-management",
    "permission-editor",
    "manage-roles",
    "org-structure",
    "org-faculties",
    "org-kafedras",
    "org-members",
    "org-roles",
    "audit-log",
    "publish-notification",
    "statistics",
}

# Sections that should highlight the "exams" main-nav item.
PROFILE_EXAM_NAV_SECTIONS = {
    "groups",
    "my-exams",
    "assigned-exams",
    "my-results",
    "pending-answers",
    "pending-review",
    "review-results",
}
