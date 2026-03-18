from apps.courses.models import CourseMembership


def can_user_access_course_roster(user, course):
    """
    User must be the course owner or have teacher/assistant membership.
    """
    if course.owner == user:
        return True

    return CourseMembership.objects.filter(
        course=course,
        user=user,
        role__in=["teacher", "assistant"],
    ).exists()


__all__ = [
    "can_user_access_course_roster",
]
