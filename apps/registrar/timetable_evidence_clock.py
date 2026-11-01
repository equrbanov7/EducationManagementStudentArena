"""Read-only clock evidence; a bell interval never proves academic-hour conversion."""

import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder

from .schedule import STANDARD_LESSON_TIMES


def timetable_clock_evidence(organization):
    raw = organization.settings if isinstance(organization.settings, dict) else {}
    # No arbitrary org settings or guessed 40/45-minute degree conversion leave the DB.
    policy = {
        k: raw[k]
        for k in ("academic_hour_minutes", "master_academic_hour_minutes")
        if type(raw.get(k)) is int and 1 <= raw[k] <= 120
    }
    encoded = json.dumps(raw, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")).encode()
    return {
        "standard_times": [list(pair) for pair in STANDARD_LESSON_TIMES],
        "explicit_minute_settings": policy,
        "organization_settings_sha256": hashlib.sha256(encoded).hexdigest(),
        "missing_duration_policy_is_unknown": True,
        "bells_are_not_academic_duration_authority": True,
    }
