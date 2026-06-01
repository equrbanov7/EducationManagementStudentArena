from django.conf import settings

PRACTICAL_EXAM_TYPE = "coding"


def practical_exams_enabled() -> bool:
    return bool(getattr(settings, "PRACTICAL_EXAMS_ENABLED", True))


def exam_supervision_enabled() -> bool:
    return bool(getattr(settings, "EXAM_SUPERVISION_ENABLED", True))


def selectable_exam_type_choices(choices):
    if practical_exams_enabled():
        return choices
    return [choice for choice in choices if choice[0] != PRACTICAL_EXAM_TYPE]


def without_disabled_practical_exams(queryset):
    if practical_exams_enabled():
        return queryset
    return queryset.exclude(exam_type=PRACTICAL_EXAM_TYPE)


def practical_exam_disabled_message() -> str:
    return "Praktiki imtahan hazırda production mühitində deaktivdir."


def supervision_disabled_message() -> str:
    return "İmtahan nəzarəti production mühitində deaktivdir."


def disabled_supervision_status(attempt=None) -> dict:
    payload = {
        "supervised": False,
        "supervision_status": "active",
        "manual_lock": False,
        "violation_count": 0,
        "max_violations": 0,
        "extra_chances_used": 0,
        "resume_window_seconds": 0,
        "resume_seconds_remaining": None,
        "resume_deadline": None,
        "config": {},
    }
    if attempt is not None:
        payload.update(
            {
                "is_finished": attempt.is_finished,
                "attempt_status": attempt.status,
            }
        )
    return payload
