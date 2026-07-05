"""Registrar models paketi (U14 bölgüsü) — sxem dəyişikliyi YOXDUR.

Köhnə tək ``models.py`` iki məntiqi modula bölünüb; bütün ictimai adlar burada
re-eksport olunur, ona görə ``from apps.registrar.models import X`` toxunulmaz
işləyir (migrasiyalar da dəyişməz qalır).
"""

from .academic import (
    AcademicStatus,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    DegreeLevel,
    Enrollment,
    EnrollmentKind,
    GroupElectiveChoice,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
    WeekType,
)
from .grading import (
    ApprovalStatus,
    AssessmentComponent,
    AssessmentScheme,
    AttendanceStatus,
    ComponentScore,
    FinalGrade,
    Lesson,
    LessonKind,
    LessonMark,
    ResitReason,
    ResitRecord,
    ResitStatus,
)

__all__ = [
    "AcademicStatus",
    "ApprovalStatus",
    "AssessmentComponent",
    "AssessmentScheme",
    "AttendanceStatus",
    "ComponentScore",
    "CourseOffering",
    "Curriculum",
    "CurriculumSubject",
    "DegreeLevel",
    "Enrollment",
    "EnrollmentKind",
    "FinalGrade",
    "GroupElectiveChoice",
    "Lesson",
    "LessonKind",
    "LessonMark",
    "Program",
    "ResitReason",
    "ResitRecord",
    "ResitStatus",
    "ScheduleSlot",
    "StudentAcademicRecord",
    "Subject",
    "WeekType",
]
