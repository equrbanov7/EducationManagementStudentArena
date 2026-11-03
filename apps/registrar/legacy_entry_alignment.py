"""Köçürülmüş (tarixi) giriş balını VERİLMİŞ rəsmi dəyərə bərabərləşdirmək — yalnız arxiv xanası (SYS-1, 2026-11-03).

Çağıran: ``apps.legacy_import.services.delta.official_entry`` (``registrar.public`` vasitəsilə). Qaydanın özü
(hansı dəyər rəsmidir) çağıranındır; burada yalnız registrar tərəfi: kanonik giriş balı, yaddaşda yoxlama, yazı,
audit.

* Yazılan YEGANƏ xana — açılışın köçürmə arxiv komponenti (``archive_name``, ``generic``):
  ``yeni = köhnə + (hədəf − cari kanonik giriş)``.
* Yazıdan ƏVVƏL dəyişdirilmiş xana ilə ``finals.compute_final_result`` yaddaşda (toplu dəstin surətində) yenidən
  hesablanır; giriş balı hədəfə bərabər çıxmırsa — yazılmır (``skip_unverifiable``). Çağıran rəsmi YEKUNU da
  veribsə, yeni yekun ona bərabər olmalıdır — deyilsə (məs. 25 % imtahanı yeni sistemdə yoxdur) xana yazılmır
  (``skip_total_mismatch``): yarım düzəliş tələbəni rəsmi nəticənin əksinə «kəsr»ə sala bilərdi.
* Müəllimin / düzəliş alətinin xanası (``entered_by`` doludur), dil səviyyə və Midterm açılışları, arxivsiz
  açılışlar — toxunulmur.
* Rəsmi vərəqdəki imtahan / 25 % təkrar imtahan balı yeni sistemdə BOŞDURSA (``FinalGrade.exam_score`` yoxdur,
  ``ResitRecord`` yoxdur) — əvvəlcə o doldurulur (yalnız boş; mövcud bal heç vaxt dəyişmir). Səbəb (2026-11-03):
  ~1 500 tarixi sətirdə imtahan, ~80-də 25 % balı köçməyib — tələbə rəsmi vərəqdə keçdiyi fənni «nəticə yoxdur» və
  ya «İmtahandan kəsilib — 25 %» kimi görürdü.
* PG trigger-i (köhnə xananın UPDATE-i) ``journal_unlock`` ilə keçilir; hər açılışa bir
  ``registrar.grade.component`` audit sətri (köhnə → yeni, ``reason``) — fail-closed.
"""

from __future__ import annotations

import copy
import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from core.rls import journal_unlock

from . import finals, finals_batch, grade_audit, language_level_grading
from .models import ComponentScore, Enrollment, FinalGrade, ResitReason, ResitRecord, ResitStatus

CHUNK = 1000


@dataclass(frozen=True)
class EntryTarget:
    """Rəsmi dəyərlər: giriş balı (məcburi), yekun, imtahan və 25 % balı (boşdursa doldurmaq üçün)."""

    entry: Decimal
    total: Decimal | None = None
    exam: Decimal | None = None
    resit: Decimal | None = None


@dataclass(frozen=True)
class EntryAlignment:
    """Bir yazılışın nəticəsi; ``outcome`` — ``written`` / ``same`` / ``skip_*``."""

    enrollment_id: object
    outcome: str
    entry_before: Decimal | None = None
    entry_after: Decimal | None = None
    total_before: Decimal | None = None
    total_after: Decimal | None = None
    result_before: str = ""
    result_after: str = ""
    filled: tuple = ()
    student: str = ""
    subject: str = ""
    period: str = ""


def _result(row) -> str:
    if row["passed"]:
        return "pass"
    if row["failed"]:
        return "fail"
    return "open"


def align_archive_entries(*, organization, actor, targets, archive_name, reason, archive_kind="generic"):
    """``targets`` = ``{enrollment pk: EntryTarget}`` → ``[EntryAlignment]``.

    Yazılar çağıranın tranzaksiyasındadır (dry-run onu geri qaytarır)."""

    out = []
    changes_by_offering: dict = defaultdict(list)
    finals_changes: dict = defaultdict(list)
    offerings: dict = {}
    pks = sorted(targets, key=str)
    for start in range(0, len(pks), CHUNK):
        chunk = list(
            Enrollment.objects.filter(organization=organization, pk__in=pks[start : start + CHUNK]).select_related(
                "student", "offering__subject", "offering__period", "offering__assessment_scheme"
            )
        )
        batch = finals_batch.build(chunk, organization=organization)
        # «Əvvəl» = tələbənin İNDİ gördüyü nəticə — doldurmadan əvvəl (hesabatdakı keçid/kəsr dəyişikliyi).
        original = {
            e.pk: finals.compute_final_result(enrollment=e, organization=organization, batch=batch)
            for e in chunk
            if _eligible(e, batch)
        }
        filled = _fill_missing_finals(chunk, targets, batch, organization, finals_changes, offerings)
        if filled:
            batch = finals_batch.build(chunk, organization=organization)
        writes = []
        for enrollment in chunk:
            target = targets[enrollment.pk]
            row, write = _align_one(
                enrollment, Decimal(target.entry), target.total, batch, organization, archive_name, archive_kind
            )
            if enrollment.pk in filled:
                row = dataclasses.replace(row, filled=tuple(filled[enrollment.pk]))
            if enrollment.pk in original and row.result_before:
                before = original[enrollment.pk]
                row = dataclasses.replace(row, total_before=before["total"], result_before=_result(before))
            out.append(row)
            if write is None:
                continue
            writes.append(write)
            offerings[enrollment.offering_id] = enrollment.offering
            cell, archive, _enrollment, new = write
            changes_by_offering[enrollment.offering_id].append(
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": archive.name,
                    "old": grade_audit.score_repr(cell.score if cell is not None else None),
                    "new": grade_audit.score_repr(new),
                }
            )
        now = timezone.now()
        with journal_unlock(local=True):
            for cell, archive, enrollment, new in writes:
                if cell is not None:
                    ComponentScore.objects.filter(pk=cell.pk).update(score=new, updated_at=now)
                else:
                    ComponentScore.objects.create(
                        organization=organization, component=archive, enrollment=enrollment, score=new
                    )
    audit_rows = [("component", oid, changes) for oid, changes in changes_by_offering.items()]
    audit_rows += [(kind, oid, changes) for (kind, oid), changes in finals_changes.items()]
    for kind, offering_id, changes in audit_rows:
        grade_audit.log_grade_changes(
            offering=offerings[offering_id], by_user=actor, kind=kind, changes=changes, fail_closed=True, reason=reason
        )
    return out


def _eligible(enrollment, batch) -> bool:
    return not language_level_grading.is_level(enrollment.offering) and not batch.rule_for(enrollment).midterm


def _fill_missing_finals(chunk, targets, batch, organization, finals_changes, offerings) -> dict:
    """Boş imtahan / 25 % balını rəsmi dəyərlə doldur → ``{enrollment pk: ["exam", "resit"]}``."""

    filled: dict = defaultdict(list)
    for enrollment in chunk:
        target = targets[enrollment.pk]
        if (target.exam is None and target.resit is None) or not _eligible(enrollment, batch):
            continue
        grade = batch.final_grade_for(enrollment)
        if target.exam is not None and (grade is None or grade.exam_score is None):
            FinalGrade.objects.update_or_create(
                organization=organization, enrollment=enrollment, defaults={"exam_score": target.exam}
            )
            filled[enrollment.pk].append("exam")
        resit = batch.resit_for(enrollment)
        if target.resit is not None and (resit is None or resit.resit_score is None):
            ResitRecord.objects.update_or_create(
                organization=organization,
                enrollment=enrollment,
                defaults={
                    "reason": ResitReason.TOTAL,
                    "status": ResitStatus.COMPLETED,
                    "resit_score": target.resit,
                },
            )
            filled[enrollment.pk].append("resit")
        for kind in filled.get(enrollment.pk, ()):
            offerings[enrollment.offering_id] = enrollment.offering
            finals_changes[("final" if kind == "exam" else "resit", enrollment.offering_id)].append(
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": "İmtahan" if kind == "exam" else "25 % təkrar imtahan",
                    "old": "—",
                    "new": grade_audit.score_repr(target.exam if kind == "exam" else target.resit),
                }
            )
    return filled


def _align_one(enrollment, target, official_total, batch, organization, archive_name, archive_kind):
    offering = enrollment.offering
    student = enrollment.student
    base = {
        "enrollment_id": enrollment.pk,
        "student": (student.get_full_name() or student.username) if student else "",
        "subject": offering.subject.name,
        "period": f"{offering.period.academic_year} {offering.period.name}",
    }
    if language_level_grading.is_level(offering):
        return EntryAlignment(outcome="skip_language_level", **base), None
    if batch.rule_for(enrollment).midterm:
        return EntryAlignment(outcome="skip_midterm_period", **base), None
    archive = next(
        (
            c
            for c in batch.components_by_offering.get(offering.id, [])
            if c.name == archive_name and c.kind == archive_kind
        ),
        None,
    )
    if archive is None:
        return EntryAlignment(outcome="skip_no_archive_component", **base), None
    before = finals.compute_final_result(enrollment=enrollment, organization=organization, batch=batch)
    current = Decimal(before["entry_score"])
    known = {"entry_before": current, "total_before": before["total"], "result_before": _result(before)}
    if current == target:
        unchanged = {"entry_after": current, "total_after": before["total"], "result_after": _result(before)}
        return EntryAlignment(outcome="same", **base, **known, **unchanged), None
    scores = batch.scores_by_enrollment[enrollment.id]
    cell = next((cs for cs in scores if cs.component_id == archive.id), None)
    if cell is not None and cell.entered_by_id is not None:
        return EntryAlignment(outcome="skip_edited_kept", **base, **known), None
    new = (Decimal(cell.score) if cell is not None else Decimal("0")) + (target - current)
    if not Decimal("0") <= new <= Decimal(archive.max_score):
        return EntryAlignment(outcome="skip_out_of_range", **base, **known), None
    simulated = copy.copy(cell) if cell is not None else ComponentScore(component=archive, enrollment=enrollment)
    simulated.score = new
    batch.scores_by_enrollment[enrollment.id] = [cs for cs in scores if cs is not cell] + [simulated]
    after = finals.compute_final_result(enrollment=enrollment, organization=organization, batch=batch)
    outcome = "written"
    if Decimal(after["entry_score"]) != target:
        outcome = "skip_unverifiable"
    elif official_total is not None and Decimal(after["total"]) != Decimal(official_total):
        outcome = "skip_total_mismatch"
    row = EntryAlignment(
        outcome=outcome,
        entry_after=Decimal(after["entry_score"]),
        total_after=after["total"],
        result_after=_result(after),
        **base,
        **known,
    )
    if outcome != "written":
        batch.scores_by_enrollment[enrollment.id] = scores
        return row, None
    return row, (cell, archive, enrollment, new)


__all__ = ["EntryAlignment", "EntryTarget", "align_archive_entries"]
