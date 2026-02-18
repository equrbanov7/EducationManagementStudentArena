"""
Core constants for EMS Arena project.
Application-wide constants and enumerations.
"""


class UserRole:
    """User role constants - Deprecated, use ORGANIZATION_ROLES instead"""

    TEACHER = "teacher"
    STUDENT = "student"
    ADMIN = "admin"

    CHOICES = [
        (TEACHER, "Teacher"),
        (STUDENT, "Student"),
        (ADMIN, "Admin"),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# ORGANIZATION-TYPE-AWARE ROLE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

# Organization-specific role definitions with hierarchy levels
ORGANIZATION_ROLES = {
    "university": {
        "rector": {"level": 100, "label": "Rektor"},
        "vice_rector": {"level": 95, "label": "Prorektor"},
        "dean": {"level": 90, "label": "Dekan"},
        "vice_dean": {"level": 85, "label": "Dekan müavini"},
        "department_head": {"level": 80, "label": "Kafedra müdiri"},
        "professor": {"level": 75, "label": "Professor"},
        "associate_professor": {"level": 70, "label": "Dosent"},
        "teacher": {"level": 60, "label": "Müəllim"},
        "assistant_teacher": {"level": 55, "label": "Assistent"},
        "lab_assistant": {"level": 50, "label": "Laborant"},
        "moderator": {"level": 40, "label": "Moderator"},
        "student": {"level": 10, "label": "Tələbə"},
    },
    "school": {
        "director": {"level": 100, "label": "Direktor"},
        "vice_director": {"level": 95, "label": "Direktor müavini"},
        "department_head": {"level": 80, "label": "Şöbə müdiri"},
        "teacher": {"level": 60, "label": "Müəllim"},
        "assistant_teacher": {"level": 55, "label": "Müəllim köməkçisi"},
        "moderator": {"level": 40, "label": "Moderator"},
        "student": {"level": 10, "label": "Şagird"},
    },
    "course_center": {
        "manager": {"level": 100, "label": "Menecer"},
        "senior_instructor": {"level": 80, "label": "Baş təlimçi"},
        "instructor": {"level": 60, "label": "Təlimçi"},
        "assistant": {"level": 55, "label": "Köməkçi"},
        "moderator": {"level": 40, "label": "Moderator"},
        "student": {"level": 10, "label": "Kursant"},
    },
    "individual": {
        "owner": {"level": 100, "label": "Sahibi"},
        "student": {"level": 10, "label": "Tələbə"},
    },
}

# Flat role → level mapping for quick lookups (all unique role names)
ROLE_LEVELS = {
    # University roles
    "rector": 100,
    "vice_rector": 95,
    "dean": 90,
    "vice_dean": 85,
    "department_head": 80,
    "professor": 75,
    "associate_professor": 70,
    # School roles
    "director": 100,
    "vice_director": 95,
    # Course center roles
    "manager": 100,
    "senior_instructor": 80,
    "instructor": 60,
    "assistant": 55,
    # Common roles (same across organizations)
    "teacher": 60,
    "assistant_teacher": 55,
    "lab_assistant": 50,
    "moderator": 40,
    "student": 10,
    "owner": 100,
    # Profile-level roles (from UserProfile.role)
    "superadmin": 100,
    "org_owner": 90,
    "org_admin": 80,
    "hr": 65,
    "member": 20,
    "lead_student": 30,
}

# Role level thresholds
ROLE_LEVEL_TEACHER = 60  # Teacher and above
ROLE_LEVEL_MODERATOR = 40  # Moderator and above
ROLE_LEVEL_ADMIN = 80  # Admin level (department_head and above)
ROLE_LEVEL_TOP_ADMIN = 95  # Top admin (rector/director/vice_rector/vice_director)


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

    ALL_CHOICES = UNIVERSITY_CHOICES + SCHOOL_CHOICES + COURSE_CENTER_CHOICES + INDIVIDUAL_CHOICES


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
