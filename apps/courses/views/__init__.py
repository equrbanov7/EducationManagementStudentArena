"""
courses/views/__init__.py — FASAD.

F3 rol-skeleti (2026-07-02, AGENTS §6): fayllar views/{student,teacher,shared}/
qovluqlarına köçürülüb; membership.py rol üzrə bölünüb. WP9a (2026-10-10): köhnə
siyahı səhifələri (``MyCoursesListView``, ``StudentCoursesView``) silindi — kabinet
bölmələri əvəz edir.
"""

from .shared import CourseDashboardView
from .teacher import (
    AddMembersBulkView,
    AddMemberView,
    AddResourceView,
    AddTopicView,
    AvailableGroupsView,
    AvailableStudentsView,
    CourseAIApplyView,
    CourseAIPlanView,
    CourseMembersView,
    CourseSyllabusImportView,
    CourseSyllabusOptionsView,
    CourseSyllabusPreviewView,
    CreateCourseView,
    DeleteCourseView,
    DeleteGroupFromCourseView,
    DeleteMemberView,
    DeleteResourceView,
    DeleteTopicView,
    EditCourseView,
    EditTopicView,
    link_exam_to_course,
    unlink_exam_from_course,
    update_course_status,
)

__all__ = [
    "CourseAIPlanView",
    "CourseAIApplyView",
    "CreateCourseView",
    "EditCourseView",
    "DeleteCourseView",
    "update_course_status",
    "CourseDashboardView",
    "AddTopicView",
    "EditTopicView",
    "DeleteTopicView",
    "AddResourceView",
    "DeleteResourceView",
    "CourseMembersView",
    "AvailableStudentsView",
    "AvailableGroupsView",
    "AddMemberView",
    "AddMembersBulkView",
    "DeleteMemberView",
    "DeleteGroupFromCourseView",
    "link_exam_to_course",
    "unlink_exam_from_course",
    "CourseSyllabusImportView",
    "CourseSyllabusOptionsView",
    "CourseSyllabusPreviewView",
]
