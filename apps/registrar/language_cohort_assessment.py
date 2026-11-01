"""Explicit cohort grading configuration; source identity is exact and reviewable."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from .models import AssessmentComponent, AssessmentScheme

FIELDS = ("entry_score_max", "pass_threshold", "min_final_exam_score")


def configure(
    *, offering, actor, source_offering=None, entry_score_max=None, pass_threshold=None, min_final_exam_score=None
):
    values = dict(
        entry_score_max=30,
        pass_threshold=51 if pass_threshold is None else pass_threshold,
        min_final_exam_score=17 if min_final_exam_score is None else min_final_exam_score,
    )
    if source_offering:
        from .journal_access import can_edit_journal, can_observe_journal

        if not (can_edit_journal(actor, source_offering) or can_observe_journal(actor, source_offering)):
            raise PermissionDenied
        if (
            source_offering.organization_id != offering.organization_id
            or source_offering.subject_id != offering.subject_id
            or source_offering.period_id != offering.period_id
            or source_offering.instructor_id != offering.instructor_id
            or source_offering.course_format != "regular"
        ):
            raise ValidationError(_("Qiymətləndirmə mənbəyi eyni fənn, semestr və müəllimə aid olmalıdır."))
        source = AssessmentScheme.objects.filter(
            organization_id=offering.organization_id, offering=source_offering
        ).first()
        if source is None:
            raise ValidationError(_("Seçilmiş mənbə jurnalında qiymətləndirmə sxemi yoxdur."))
        values = {field: getattr(source, field) for field in FIELDS}
    values["entry_score_max"] = 30
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
        raise ValidationError(_("Qiymətləndirmə bal hədləri uyğun deyil."))
    if not (
        1 <= values["entry_score_max"] <= 100
        and 1 <= values["pass_threshold"] <= 100
        and 0 <= values["min_final_exam_score"] <= 100 - values["entry_score_max"]
    ):
        raise ValidationError(_("Qiymətləndirmə bal hədləri uyğun deyil."))
    scheme = AssessmentScheme.objects.create(organization=offering.organization, offering=offering, **values)
    source_midterm = (
        AssessmentComponent.objects.filter(
            organization=offering.organization, offering=source_offering, kind="kollokvium", name__iexact="Midterm"
        ).first()
        if source_offering
        else None
    )
    AssessmentComponent.objects.create(
        organization=offering.organization,
        offering=offering,
        name="Midterm",
        kind="kollokvium",
        max_score=10,
        rubric=source_midterm.rubric if source_midterm else None,
    )
    return scheme
