"""
Business logic layer for courses app.
This module contains service functions that encapsulate business operations.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.exams.models import StudentGroup

from .models import CourseMembership

User = get_user_model()


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

    Args:
        course: Course instance
        student_group: StudentGroup instance
        group_name: Group name to assign (defaults to StudentGroup name)

    Returns:
        tuple: (created_count, existing_count)
    """
    assigned_group_name = group_name or student_group.name
    students = student_group.students.all()

    created_count = 0
    existing_count = 0

    for student in students:
        membership, created = CourseMembership.objects.get_or_create(
            course=course,
            user=student,
            defaults={
                "role": "student",
                "group_name": assigned_group_name,
            },
        )

        if created:
            created_count += 1
        else:
            existing_count += 1
            # Update group name for existing membership
            if membership.role == "student":
                membership.group_name = assigned_group_name
                membership.save()

    return created_count, existing_count


@transaction.atomic
def bulk_add_members_to_course(course, user_ids, role="student", group_name=""):
    """
    Add multiple users to a course.

    Args:
        course: Course instance
        user_ids: List of user IDs
        role: Membership role
        group_name: Group name for students

    Returns:
        tuple: (created_count, existing_count)
    """
    users = User.objects.filter(id__in=user_ids)

    created_count = 0
    existing_count = 0

    for user in users:
        membership, created = CourseMembership.objects.get_or_create(
            course=course,
            user=user,
            defaults={
                "role": role,
                "group_name": group_name if role == "student" else "",
            },
        )

        if created:
            created_count += 1
        else:
            existing_count += 1

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
    qs = StudentGroup.objects.filter(Q(teacher=teacher) | Q(teachers=teacher)).distinct()

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
