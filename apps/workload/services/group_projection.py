"""Academic group identity shared by private exports and reviewed repairs.

Unexported settings are deliberately not claimed as external source evidence.
Repairs separately fingerprint and preserve the complete live settings object.
"""

import uuid

SETTING_KEYS = frozenset(
    {"parent_group", "degree_level", "education_form", "language", "sector", "language_level_cohort"}
)


def project_group_settings(settings, *, canonical_group_ids):
    settings = settings or {}
    projected = {
        key: value
        for key, value in settings.items()
        if key in SETTING_KEYS
        and isinstance(value, (str, int, bool))
        and (key != "language_level_cohort" or isinstance(value, bool))
    }
    try:
        canonical = uuid.UUID(str(settings.get("canonical_group")))
    except (ValueError, TypeError, AttributeError):
        return projected
    if str(canonical) in {str(pk) for pk in canonical_group_ids}:
        projected["canonical_group"] = str(canonical)
    return projected
