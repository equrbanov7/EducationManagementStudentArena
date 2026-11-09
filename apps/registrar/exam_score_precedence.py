"""Onlayn final cəhdi ilə sonrakı rəsmi bal qeydi arasında mənbə üstünlüyü.

Əl ilə daxil edilmiş nəticə/düzəliş cəhdin bitməsindən yenidirsə qorunur.
Rəqəmsal apellyasiyanın öz ledger sətri eyni cəhdin növbəti apellyasiya
hesabını bloklamır. Naməlum mənbə və ya bitmə tarixi qoruyucu istiqamətdədir.
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.db import transaction

from . import finals
from .exam_score_entry import record_appeal_score_change
from .models import Enrollment, ExamAssessment, ExamScoreEntry, ExamScoreEntryKind, FinalGrade

_DIGITAL_APPEAL_NOTE = re.compile(r"Rəqəmsal apellyasiya #([0-9]+)\Z")


def _digital_appeal_entry(entry, enrollment, attempt) -> bool:
    """Mövcud append-only ledger-in rəqəmsal mənbə müqaviləsi.

    Standart note yalnız mənbə id-sini tapır, özü sübut deyil. Həmin tələbənin
    həmin cəhdi üçün qəbul/adjustment və ya sual-açarı krediti də olmalıdır.
    Geri alınmış adjustment/credit tarixçəsi də mənbəni sübut edir: onun
    reversalı effektiv balı yenidən hesablaya bilməlidir.
    """
    if entry.kind != ExamScoreEntryKind.APPEAL or entry.evidence or entry.sheet_id is not None:
        return False
    match = _DIGITAL_APPEAL_NOTE.fullmatch(entry.note)
    if match is None or getattr(attempt, "pk", None) is None:
        return False
    if attempt.user_id != enrollment.student_id:
        return False
    Appeal = django_apps.get_model("appeals", "Appeal")
    appeal = Appeal.objects.filter(
        pk=int(match[1]),
        organization_id=enrollment.organization_id,
        exam_id=attempt.exam_id,
        exam__organization_id=enrollment.organization_id,
        exam__subject_id=enrollment.offering.subject_id,
    ).first()
    if appeal is None:
        return False
    if appeal.attempt_id == attempt.pk and appeal.student_id == enrollment.student_id:
        if appeal.status in {"accepted", "partially_accepted"}:
            return True
        Adjustment = django_apps.get_model("appeals", "ScoreAdjustment")
        if Adjustment.objects.filter(attempt_id=attempt.pk, appeal_item__appeal_id=appeal.pk).exists():
            return True
    # Bir tələbənin apellyasiyası ilə açar düzələndə başqa cəhdlər də kredit ala
    # bilər. Sadəcə yad appeal id-si deyil, məhz bu cəhdin kredit zənciri tələbdir.
    Credit = django_apps.get_model("appeals", "KeyCorrectionCredit")
    return Credit.objects.filter(
        attempt_id=attempt.pk,
        correction__organization_id=enrollment.organization_id,
        correction__exam_id=attempt.exam_id,
        correction__source_item__appeal_id=appeal.pk,
    ).exists()


def has_later_authoritative_entry(enrollment, attempt, *, purged_attempt=None) -> bool:
    """Purge preflight yalnız silinəcək cəhdin sübut edilmiş digital izini çıxara bilər."""
    from .exam_score_purge_provenance import purged_digital_entry_ids

    entries = ExamScoreEntry.objects.filter(
        organization_id=enrollment.organization_id,
        enrollment=enrollment,
        assessment=ExamAssessment.FINAL,
    )
    finished_at = getattr(attempt, "finished_at", None)
    if finished_at is not None:
        entries = entries.filter(created_at__gte=finished_at)
    authoritative = [
        entry
        for entry in entries
        if not _digital_appeal_entry(entry, enrollment, attempt)
        and not (purged_attempt is not None and _digital_appeal_entry(entry, enrollment, purged_attempt))
    ]
    if not authoritative:
        return False
    purged_ids = purged_digital_entry_ids(enrollment, authoritative)
    return any(entry.pk not in purged_ids for entry in authoritative)


@transaction.atomic
def record_attempt_final_score(*, enrollment, score, by_user, source_note, attempt=None, appeal_id=None):
    """Əl yazısı ilə eyni parent lock: yoxlama və bal yazısı bir tranzaksiyadır."""
    Enrollment.objects.select_for_update().get(pk=enrollment.pk, organization_id=enrollment.organization_id)
    previous_grade = FinalGrade.objects.filter(enrollment=enrollment).first()
    if has_later_authoritative_entry(enrollment, attempt):
        return "overridden", previous_grade
    previous_score = previous_grade.exam_score if previous_grade is not None else None
    grade = finals.set_exam_score(enrollment=enrollment, score=score, by_user=by_user, source_note=source_note)
    if grade is not None and appeal_id is not None:
        record_appeal_score_change(
            enrollment=enrollment,
            old_score=previous_score,
            new_score=grade.exam_score,
            by_user=by_user,
            appeal_id=appeal_id,
        )
    return "written", grade
