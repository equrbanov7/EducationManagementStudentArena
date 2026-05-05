from django.conf import settings

PRACTICAL_EXAM_TYPE = "coding"


def practical_exams_enabled() -> bool:
    return bool(getattr(settings, "PRACTICAL_EXAMS_ENABLED", True))


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
