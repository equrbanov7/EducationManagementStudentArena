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
