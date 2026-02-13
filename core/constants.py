"""
Core constants for EMS Arena project.
Application-wide constants and enumerations.
"""


class UserRole:
    """User role constants"""

    TEACHER = "teacher"
    STUDENT = "student"
    ADMIN = "admin"

    CHOICES = [
        (TEACHER, "Teacher"),
        (STUDENT, "Student"),
        (ADMIN, "Admin"),
    ]


class ExamType:
    """Exam type constants"""

    QUIZ = "quiz"
    MIDTERM = "midterm"
    FINAL = "final"
    ASSIGNMENT = "assignment"

    CHOICES = [
        (QUIZ, "Quiz"),
        (MIDTERM, "Midterm"),
        (FINAL, "Final"),
        (ASSIGNMENT, "Assignment"),
    ]


class SubmissionStatus:
    """Submission status constants"""

    PENDING = "pending"
    SUBMITTED = "submitted"
    GRADED = "graded"
    LATE = "late"

    CHOICES = [
        (PENDING, "Pending"),
        (SUBMITTED, "Submitted"),
        (GRADED, "Graded"),
        (LATE, "Late"),
    ]


class QuestionType:
    """Question type constants"""

    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"

    CHOICES = [
        (MULTIPLE_CHOICE, "Multiple Choice"),
        (TRUE_FALSE, "True/False"),
        (SHORT_ANSWER, "Short Answer"),
        (ESSAY, "Essay"),
    ]


# Organization System Constants


class OrganizationType:
    """Organization type constants"""

    UNIVERSITY = "university"
    SCHOOL = "school"
    COURSE_CENTER = "course_center"
    INDIVIDUAL = "individual"

    CHOICES = [
        (UNIVERSITY, "University"),
        (SCHOOL, "School"),
        (COURSE_CENTER, "Course Center"),
        (INDIVIDUAL, "Individual"),
    ]


class OrgUnitType:
    """Organizational unit type constants"""

    # University types
    RECTORATE = "rectorate"
    VICE_RECTORATE = "vice_rectorate"
    FACULTY = "faculty"
    DEANERY = "deanery"
    CHAIR = "chair"
    DEPARTMENT = "department"
    LAB = "lab"
    INSTITUTE = "institute"
    CENTER = "center"

    # School types
    DIRECTORATE = "directorate"
    SECTION = "section"
    PARALLEL = "parallel"
    CLASS = "class"
    GRADE_LEVEL = "grade_level"

    # Course Center types
    BRANCH = "branch"
    DIVISION = "division"
    GROUP = "group"
    CLASSROOM = "classroom"

    # Common types
    UNIT = "unit"

    UNIVERSITY_CHOICES = [
        (RECTORATE, "Rectorate"),
        (VICE_RECTORATE, "Vice Rectorate"),
        (FACULTY, "Faculty"),
        (DEANERY, "Deanery"),
        (CHAIR, "Chair"),
        (DEPARTMENT, "Department"),
        (LAB, "Laboratory"),
        (INSTITUTE, "Institute"),
        (CENTER, "Center"),
    ]

    SCHOOL_CHOICES = [
        (DIRECTORATE, "Directorate"),
        (SECTION, "Section"),
        (PARALLEL, "Parallel"),
        (CLASS, "Class"),
        (GRADE_LEVEL, "Grade Level"),
    ]

    COURSE_CENTER_CHOICES = [
        (BRANCH, "Branch"),
        (DIVISION, "Division"),
        (GROUP, "Group"),
        (CLASSROOM, "Classroom"),
    ]

    INDIVIDUAL_CHOICES = [
        (UNIT, "Unit"),
    ]

    ALL_CHOICES = (
        UNIVERSITY_CHOICES + SCHOOL_CHOICES + COURSE_CENTER_CHOICES + INDIVIDUAL_CHOICES
    )


class PermissionCategory:
    """Permission category constants"""

    ORGANIZATION = "organization"
    STRUCTURE = "structure"
    MEMBERS = "members"
    ROLES = "roles"
    COURSES = "courses"
    GRADING = "grading"
    EXAMS = "exams"
    APPEAL = "appeal"
    ANALYTICS = "analytics"
    QA = "qa"
    AUDIT = "audit"

    CHOICES = [
        (ORGANIZATION, "Organization"),
        (STRUCTURE, "Structure"),
        (MEMBERS, "Members"),
        (ROLES, "Roles"),
        (COURSES, "Courses"),
        (GRADING, "Grading"),
        (EXAMS, "Exams"),
        (APPEAL, "Appeal"),
        (ANALYTICS, "Analytics"),
        (QA, "QA"),
        (AUDIT, "Audit"),
    ]


class AcademicPeriodType:
    """Academic period type constants"""

    SEMESTER = "semester"
    TRIMESTER = "trimester"
    QUARTER = "quarter"
    YEAR = "year"
    TERM = "term"

    CHOICES = [
        (SEMESTER, "Semester"),
        (TRIMESTER, "Trimester"),
        (QUARTER, "Quarter"),
        (YEAR, "Year"),
        (TERM, "Term"),
    ]


class RoleScopeType:
    """Role scope type constants"""

    ORGANIZATION = "organization"
    UNIT = "unit"
    COURSE = "course"

    CHOICES = [
        (ORGANIZATION, "Organization-wide"),
        (UNIT, "Unit-specific"),
        (COURSE, "Course-specific"),
    ]


class AuditAction:
    """Audit action constants"""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    VIEW = "view"
    EXPORT = "export"

    CHOICES = [
        (CREATE, "Create"),
        (UPDATE, "Update"),
        (DELETE, "Delete"),
        (LOGIN, "Login"),
        (LOGOUT, "Logout"),
        (VIEW, "View"),
        (EXPORT, "Export"),
    ]
