"""Public read-facing helpers the accounts profile reuses for the student cabinet.

Mirrors the ``apps.appeals.public`` pattern: the accounts profile context
builder calls :func:`build_student_subjects_context` for the "Fənlərim" section
without importing registrar internals. Tenant/RLS scoping is inherited from the
active request; the helper only reads the requesting student's own record.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from apps.registrar import services
from apps.registrar.models import StudentAcademicRecord

# ``AcademicPeriod`` lives in the organizations module. Registrar already
# references organizations models only via string FKs (no Python import), which
# keeps the module-dependency graph acyclic (organizations → registrar via the
# seed command, but not back). We resolve it through the app registry to keep
# that property instead of a static ``from apps.organizations`` import.


def _academic_period_model():
    return django_apps.get_model("organizations", "AcademicPeriod")


def _empty_section() -> dict:
    return {
        "has_record": False,
        "record": None,
        "period": None,
        "semester_number": 1,
        "subjects": [],
        "elective_blocks": {},
        "group_decisions": {},
        "credit_summary": None,
    }


def _resolve_semester_number(request, default=1) -> int:
    try:
        value = int(request.GET.get("semester") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def build_student_subjects_context(request, *, organization, semester_number=None) -> dict:
    """Context for the student "Fənlərim" (my-subjects) cabinet section.

    Resolves the requesting user's :class:`StudentAcademicRecord` and the
    current :class:`AcademicPeriod` in *organization*, then delegates to
    :func:`services.get_student_cabinet_data`. Degrades to a friendly empty
    state (``has_record=False``) when the student has no academic record yet,
    so non-university tenants render a harmless placeholder.
    """
    section = _empty_section()
    if organization is None or not getattr(request.user, "is_authenticated", False):
        return {"student_subjects_section": section}

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("program", "curriculum", "group")
        .first()
    )
    if record is None:
        return {"student_subjects_section": section}

    section["has_record"] = True
    section["record"] = record

    AcademicPeriod = _academic_period_model()
    period = (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )
    if period is None:
        return {"student_subjects_section": section}

    if semester_number is None:
        semester_number = _resolve_semester_number(request)

    data = services.get_student_cabinet_data(record=record, period=period, semester_number=semester_number)

    # Attach each subject's electronic-journal result (component scores → total /
    # letter / pass), so "Fənlərim" doubles as the student's "Qiymətlərim" view.
    from apps.registrar import gradebook

    grade_summary = gradebook.get_student_grade_summary(record=record, period=period, semester_number=semester_number)
    grade_by_enrollment = {row["enrollment"].id: row["result"] for row in grade_summary["subjects"]}
    for subject_row in data["subjects"]:
        subject_row["grade"] = grade_by_enrollment.get(subject_row["enrollment"].id)

    # Pre-join each elective block with the group's decision so the template
    # renders without a dict-lookup filter (block name → chosen subject).
    group_decisions = data["group_decisions"]
    elective_blocks = [
        {
            "name": name,
            "required_choices": block["required_choices"],
            "options": block["options"],
            "chosen": group_decisions.get(name),
        }
        for name, block in data["elective_blocks"].items()
    ]
    section.update(
        {
            "period": period,
            "semester_number": semester_number,
            "subjects": data["subjects"],
            "elective_blocks": elective_blocks,
            "group_decisions": group_decisions,
            "credit_summary": data["credit_summary"],
        }
    )
    return {"student_subjects_section": section}
