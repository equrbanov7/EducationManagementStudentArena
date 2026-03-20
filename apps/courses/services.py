"""
Business logic layer for courses app.
This module contains service functions that encapsulate business operations.
"""

from django.db import transaction
from django.db.models import Q

from apps.exams.models import StudentGroup

from .models import Course, CourseMembership


# ════════════════════════════════════════════════════════════════════════════
# Course Enrollment Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def enroll_user_in_course(course, user, role="student", group_name=""):
    """
    Enroll a user in a course.

    Args:
        course: Course instance
        user: User instance
        role: Membership role (default: "student")
        group_name: Optional group name for student

    Returns:
        CourseMembership: Created membership
    """
    membership, created = CourseMembership.objects.get_or_create(
        course=course,
        user=user,
        defaults={
            "role": role,
            "group_name": group_name,
        },
    )

    if not created and role == "student":
        membership.group_name = group_name
        membership.save()

    return membership


@transaction.atomic
def remove_user_from_course(course, user):
    """
    Remove a user from a course.

    Args:
        course: Course instance
        user: User instance

    Returns:
        bool: True if membership was deleted
    """
    deleted_count, _ = CourseMembership.objects.filter(
        course=course,
        user=user,
    ).delete()

    return deleted_count > 0


# ════════════════════════════════════════════════════════════════════════════
# Roster Management Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def add_students_from_group_to_course(course, student_group, group_name=""):
    """
    Add all students from a StudentGroup to a course.

    Uses bulk_create + bulk_update to avoid N+1 queries: all existing
    memberships are fetched in a single query, new ones are inserted in a
    single batch, and group-name updates for existing student members are
    applied in a single bulk_update call.

    Args:
        course: Course instance
        student_group: StudentGroup instance
        group_name: Group name to assign (defaults to StudentGroup name)

    Returns:
        tuple: (created_count, existing_count)
    """
    assigned_group_name = group_name or student_group.name
    student_ids = list(student_group.students.values_list("id", flat=True))

    if not student_ids:
        return 0, 0

    # Single query: fetch all existing memberships for these students.
    existing_by_user = {
        m.user_id: m
        for m in CourseMembership.objects.filter(course=course, user_id__in=student_ids)
    }

    new_memberships = []
    to_update = []

    for student_id in student_ids:
        if student_id in existing_by_user:
            membership = existing_by_user[student_id]
            if membership.role == "student" and membership.group_name != assigned_group_name:
                membership.group_name = assigned_group_name
                to_update.append(membership)
        else:
            new_memberships.append(
                CourseMembership(
                    course=course,
                    user_id=student_id,
                    role="student",
                    group_name=assigned_group_name,
                )
            )

    # Single INSERT for all new members.
    # ignore_conflicts=True guards against the TOCTOU race: two concurrent
    # requests can both read "no membership" and then race to insert the same
    # row.  The atomic transaction prevents phantom reads under SERIALIZABLE
    # isolation, but PostgreSQL defaults to READ COMMITTED, so the defensive
    # ignore is necessary for safety.
    if new_memberships:
        CourseMembership.objects.bulk_create(new_memberships, ignore_conflicts=True)

    # Single UPDATE for existing members whose group name changed.
    if to_update:
        CourseMembership.objects.bulk_update(to_update, ["group_name"])

    created_count = len(new_memberships)
    existing_count = len(existing_by_user)
    return created_count, existing_count


@transaction.atomic
def bulk_add_members_to_course(course, user_ids, role="student", group_name=""):
    """
    Add multiple users to a course.

    Uses bulk_create to avoid N+1 queries: all existing memberships are
    fetched in a single query, and new ones are inserted in a single batch.

    Args:
        course: Course instance
        user_ids: List of user IDs
        role: Membership role
        group_name: Group name for students

    Returns:
        tuple: (created_count, existing_count)
    """
    user_ids = list(user_ids)
    if not user_ids:
        return 0, 0

    # Single query: find which users are already members.
    existing_user_ids = set(
        CourseMembership.objects.filter(course=course, user_id__in=user_ids).values_list("user_id", flat=True)
    )

    new_memberships = [
        CourseMembership(
            course=course,
            user_id=uid,
            role=role,
            group_name=group_name if role == "student" else "",
        )
        for uid in user_ids
        if uid not in existing_user_ids
    ]

    # Single INSERT for all new members.
    # ignore_conflicts=True guards against the TOCTOU race: two concurrent
    # requests can both read "no membership" and then race to insert the same
    # row.  The atomic transaction prevents phantom reads under SERIALIZABLE
    # isolation, but PostgreSQL defaults to READ COMMITTED, so the defensive
    # ignore is necessary for safety.
    if new_memberships:
        CourseMembership.objects.bulk_create(new_memberships, ignore_conflicts=True)

    created_count = len(new_memberships)
    existing_count = len(existing_user_ids)
    return created_count, existing_count


@transaction.atomic
def remove_group_from_course(course, group_name):
    """
    Remove all members of a group from a course.

    Args:
        course: Course instance
        group_name: Group name to remove

    Returns:
        int: Number of memberships deleted
    """
    deleted_count, _ = CourseMembership.objects.filter(
        course=course,
        role="student",
        group_name=group_name,
    ).delete()

    return deleted_count


@transaction.atomic
def update_member_group(course, user, new_group_name):
    """
    Update group name for a course member.

    Args:
        course: Course instance
        user: User instance
        new_group_name: New group name

    Returns:
        CourseMembership or None
    """
    try:
        membership = CourseMembership.objects.get(
            course=course,
            user=user,
            role="student",
        )
        membership.group_name = new_group_name
        membership.save()
        return membership
    except CourseMembership.DoesNotExist:
        return None


# ════════════════════════════════════════════════════════════════════════════
# Course Query Services
# ════════════════════════════════════════════════════════════════════════════


def get_course_members(course, role=None):
    """
    Get members of a course, optionally filtered by role.

    Args:
        course: Course instance
        role: Optional role filter

    Returns:
        QuerySet: CourseMembership queryset
    """
    qs = course.memberships.select_related("user", "user__profile")

    if role:
        qs = qs.filter(role=role)

    return qs.order_by("joined_at")


def get_course_groups(course):
    """
    Get unique group names in a course.

    Args:
        course: Course instance

    Returns:
        list: List of unique group names
    """
    group_names = (
        course.memberships.filter(role="student")
        .exclude(group_name="")
        .values_list("group_name", flat=True)
        .distinct()
        .order_by("group_name")
    )

    return list(group_names)


def get_available_student_groups(organization, teacher):
    """
    Get available StudentGroups for a teacher.

    Args:
        organization: Organization instance or None
        teacher: User instance

    Returns:
        QuerySet: StudentGroup queryset
    """
    qs = StudentGroup.objects.filter(
        Q(teacher=teacher) | Q(teachers=teacher)
    ).distinct()

    if organization is not None:
        qs = qs.filter(organization=organization)

    return qs.order_by("name")


def is_user_enrolled_in_course(course, user):
    """
    Check if user is enrolled in course.

    Args:
        course: Course instance
        user: User instance

    Returns:
        bool: True if user is enrolled
    """
    return CourseMembership.objects.filter(
        course=course,
        user=user,
    ).exists()


# ════════════════════════════════════════════════════════════════════════════
# Course Status Management Services
# ════════════════════════════════════════════════════════════════════════════


def update_course_status(course, new_status):
    """
    Update course status.

    Args:
        course: Course instance
        new_status: New status value

    Returns:
        Course: Updated course
    """
    course.status = new_status
    course.save()
    return course


def publish_course(course):
    """
    Publish a course.

    Args:
        course: Course instance

    Returns:
        Course: Updated course
    """
    return update_course_status(course, "published")


def archive_course(course):
    """
    Archive a course.

    Args:
        course: Course instance

    Returns:
        Course: Updated course
    """
    return update_course_status(course, "archived")
