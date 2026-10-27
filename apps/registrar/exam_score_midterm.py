"""KAĞIZ MİDTERM balının sistemə köçürülməsi → elektron jurnalın «Midterm» xanası (sahib 2026-10-25).

Sahib: «İmtahan növü: midterm / final … təsdiqdən sonra sistemə düşür (jurnal: midterm → Midterm xanası, final →
final nəticəsi — mövcud sinxron servisləri ilə)». Final yolu ``exam_score_bulk``-dır (``FinalGrade``); bu modul
onun midterm qardaşıdır və EYNİ qərar köməkçilərini işlədir (``exam_score_entry.clean_row_score`` /
``change_decision`` / ``new_entry`` / ``entry_log``) — qayda fərqi yoxdur:

* **Hədəf** — açılışın aralıq komponenti («Midterm», ``ComponentKind.KOLLOKVIUM``, ``k_index=0``) —
  ``interim_components.ensure_kollokviums``, test midterm körpüsü (``midterm_bridge``) ilə EYNİ xana. Tavan
  komponentin FAKTİKİ ``max_score``-udur (RİM qaydası 30; DB qoruyucusu da onu tutur).
* **Mənbə** — ``ComponentScore.exam_source`` = ``{"source": "paper_sheet", "sheet_id", …}``: dolu mənbəli
  xananı müəllim jurnalda dəyişə bilmir (``gradebook_components.save_component_scores`` onu ötürür) — kağız
  midterm nəticəsi yalnız bu ekrandan (15 dəqiqə / apellyasiya / RİM qaydası ilə) dəyişir.
* **Sistem yazısı** — İmtahan Mərkəzi pəncərəsindən və jurnalın 15 dəqiqə kilidindən asılı deyil
  (``journal_unlock`` — midterm körpüsü və sənədli düzəlişin işlətdiyi rəsmi yol). Bağlanmış (dərc olunmuş)
  jurnala yazılmır — giriş balı bağlı jurnalda dəyişmir.
* **Audit fail-closed** — qiymət izi (``registrar.grade.midterm-paper``) və daxiletmə jurnalı
  (``ExamScoreEntry`` + ``log_action``) yazılmasa heç nə commit olunmur (R08 qaydası).
* **Bildiriş YOXDUR** — nəticə tələbəyə ``exam.score_release_hours`` sonra açılır (``exam_score_release``).

Sətirlər azdır (bir qrup ≤ 60) — yazı sətir-sətir, lakin kilidlər BİR dəfə və sabit sırada
(açılış → komponent → qeydiyyatlar ``id`` artan → xanalar).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils.translation import pgettext

from core.audit import log_actions

from . import exam_score_entry as entry_service
from . import grade_audit, interim_components
from .audit_write import AuditWriteFailed, audit_failure_message
from .corrections import correction_author_name
from .gradebook import journal_is_locked
from .models import (
    AssessmentComponent,
    ComponentScore,
    CourseOffering,
    Enrollment,
    ExamAssessment,
    ExamScoreEntry,
)

logger = logging.getLogger(__name__)

_CTX = "registrar.exam_score_entry"

#: Qiymət audit izinin növü (``registrar.grade.midterm-paper``) — jurnal tarixçəsi prefiksdən oxuyur.
AUDIT_KIND = "midterm-paper"
SOURCE_NOTE = "imtahan mərkəzi · kağız midterm"


def journal_locked_error() -> ValidationError:
    return ValidationError(
        pgettext(_CTX, "Jurnal bağlıdır (dərc olunub) — midterm balı yazıla bilməz. RİM-ə müraciət edin.")
    )


def midterm_component(offering):
    """Açılışın «Midterm» komponenti (idempotent yaradılır); Midterm rejimi deyilsə ``ValidationError``."""
    from . import exam_score_assessment

    exam_score_assessment.assert_assessment_allowed(offering, ExamAssessment.MIDTERM)
    return interim_components.ensure_kollokviums(offering)[0]


def _source(sheet, score, cap) -> dict:
    percent = (Decimal(score) * 100 / Decimal(cap)) if cap else Decimal(0)
    kind = getattr(sheet, "exam_kind", "") or ""
    return {
        "source": "paper_sheet",
        "sheet_id": str(sheet.pk) if sheet is not None else "",
        "exam_kind": kind,
        "exam_title": pgettext(_CTX, "Kağız midterm (İmtahan Mərkəzi)"),
        "exam_slug": "",
        "attempt_id": None,
        "exam_id": None,
        "percent": f"{percent.quantize(Decimal('0.1')):g}",
    }


def save_rows(*, offering, rows, by_user, request=None, sheet=None, policy, rules=None):
    """Midterm balları — ``exam_score_entry.save_roster_scores``-un midterm yolu (nəticə forması eynidir)."""
    ordered = sorted(rows, key=lambda r: str(r.get("enrollment_id") or ""))
    writer = _MidtermSave(offering=offering, by_user=by_user, request=request, sheet=sheet, policy=policy)
    writer.rules = rules
    try:
        with transaction.atomic():
            return writer.run(ordered)
    except AuditWriteFailed:
        logger.exception("exam_score_midterm: audit write failed — %d row(s) rolled back", len(ordered))
        return writer.audit_failed_result()


class _MidtermSave:
    def __init__(self, *, offering, by_user, request, sheet, policy):
        self.offering = offering
        self.by_user = by_user
        self.request = request
        self.sheet = sheet
        self.policy = policy
        self.rules = None
        self.slots: list = []

    def audit_failed_result(self) -> dict:
        for slot in self.slots:
            if slot["state"] == "written":
                slot["state"], slot["message"] = "failed", audit_failure_message()
        return _result(self.slots)

    def run(self, ordered):
        # Kilid sırası müəllim yazısı və midterm körpüsü ilə eyni: açılış → komponent → qeydiyyat → xana.
        CourseOffering.objects.select_for_update().filter(pk=self.offering.pk).exists()
        if journal_is_locked(self.offering):
            raise journal_locked_error()
        component = midterm_component(self.offering)
        component = AssessmentComponent.objects.select_for_update().get(pk=component.pk)
        cap = int(component.max_score)
        keys = [str(row.get("enrollment_id") or "") for row in ordered]
        enrollments = {
            str(e.pk): e
            for e in Enrollment.objects.select_for_update(of=("self",))
            .filter(offering=self.offering, status=Enrollment.Status.ENROLLED, pk__in=_valid_ids(keys))
            .select_related("student", "organization")
            .order_by("pk")
        }
        existing = {
            str(cs.enrollment_id): cs
            for cs in ComponentScore.objects.select_for_update()
            .filter(component=component, enrollment_id__in=[e.pk for e in enrollments.values()])
            .order_by("enrollment_id")
        }
        seen = set()
        author = correction_author_name(self.by_user, self.request)
        writes = []
        for row in ordered:
            key = str(row.get("enrollment_id") or "")
            slot = {"key": key, "row": row, "enrollment": enrollments.get(key), "state": None, "message": ""}
            self.slots.append(slot)
            if slot["enrollment"] is None or key in seen:
                slot["state"], slot["message"] = "inactive", entry_service.inactive_enrollment_message()
                continue
            seen.add(key)
            try:
                entry = self._decide(slot, existing.get(key), cap, author)
            except ValidationError as exc:
                slot["state"], slot["message"] = "failed", " ".join(exc.messages)
                continue
            if entry is None:
                slot["state"] = "skipped"
                continue
            slot.update(state="written", entry=entry)
            writes.append(slot)
        if writes:
            self._write(writes, component, existing, cap)
        return _result(self.slots)

    def _decide(self, slot, score_row, cap, author):
        row, enrollment = slot["row"], slot["enrollment"]
        cleaned, new_score = entry_service.clean_row_score(
            score=row.get("score"), question_scores=row.get("question_scores"), sheet=self.sheet, cap=cap
        )
        if new_score is None:
            return None  # boş sahə = toxunma
        old_score = score_row.score if score_row is not None else None
        # Müəllimin jurnalda əl ilə yazdığı (mənbəsiz) midterm balı və kağız tarixçəsi yoxdur → bu, kağız
        # nəticənin İLK köçürülməsidir (köhnə bal audit üçün ``old_score``-da qalır, təsdiq sərbəstdir).
        teacher_written = score_row is not None and not score_row.exam_source and not self._has_paper(enrollment)
        entry_kind = entry_service.change_decision(
            old_score=None if teacher_written else old_score,
            new_score=new_score,
            cleaned_questions=cleaned,
            latest_question_scores=lambda: _latest_questions(enrollment),
            policy=self.policy,
            reason=row.get("reason") or "",
            note=row.get("note") or "",
            evidence=row.get("evidence"),
            sheet=self.sheet,
            kind=row.get("kind") or "",
            rules=self.rules,
            enrollment_id=enrollment.pk,
            by_user=self.by_user,
        )
        if entry_kind is None or (teacher_written and old_score == new_score and cleaned is None):
            return None
        entry = entry_service.new_entry(
            enrollment=enrollment,
            organization=enrollment.organization,
            entry_kind=entry_kind,
            old_score=old_score,
            new_score=new_score,
            cleaned_questions=cleaned,
            reason=row.get("reason") or "",
            note=row.get("note") or "",
            evidence=row.get("evidence"),
            by_user=self.by_user,
            author_name=author,
            sheet=self.sheet,
            assessment=ExamAssessment.MIDTERM,
        )
        entry.full_clean(
            exclude=["entered_by", "sheet", "organization", "enrollment"],
            validate_unique=False,
            validate_constraints=False,
        )
        slot["score"], slot["old_score"], slot["questions"] = new_score, old_score, cleaned
        return entry

    def _has_paper(self, enrollment) -> bool:
        if self.rules is not None:
            return enrollment.pk in self.rules.initial
        return ExamScoreEntry.objects.filter(enrollment=enrollment, assessment=ExamAssessment.MIDTERM).exists()

    def _write(self, writes, component, existing, cap):
        from core.rls import journal_unlock

        changes = []
        with journal_unlock():  # jurnalın 15 dəqiqə trigger-i — sistem yazısı rəsmi yoldur
            for slot in writes:
                enrollment, score = slot["enrollment"], slot["score"]
                source = _source(self.sheet, score, cap)
                row = existing.get(slot["key"])
                if row is None:
                    ComponentScore.objects.create(
                        organization_id=self.offering.organization_id,
                        component=component,
                        enrollment=enrollment,
                        score=score,
                        entered_by=self.by_user,
                        exam_source=source,
                    )
                else:
                    row.score, row.exam_source, row.entered_by = score, source, self.by_user
                    row.save(update_fields=["score", "exam_source", "entered_by", "updated_at"])
                changes.append(
                    {
                        "student": grade_audit.student_label(enrollment),
                        "item": component.name,
                        "old": grade_audit.score_repr(slot["old_score"]),
                        "new": grade_audit.score_repr(score),
                        "source": f"exam_score_sheet:{getattr(self.sheet, 'pk', '')}",
                        "note": SOURCE_NOTE,
                    }
                )
        grade_audit.log_grade_changes(
            offering=self.offering,
            by_user=self.by_user,
            kind=AUDIT_KIND,
            changes=changes,
            fail_closed=True,
            request=self.request,
        )
        ExamScoreEntry.objects.bulk_create([slot["entry"] for slot in writes])
        try:
            log_actions(
                entry_service.entry_log(
                    slot["entry"],
                    by_user=self.by_user,
                    organization=slot["enrollment"].organization,
                    policy=self.policy,
                    request=self.request,
                    cleaned_questions=slot["questions"],
                )
                for slot in writes
            )
        except DatabaseError as exc:
            raise AuditWriteFailed("exam score entry audit (midterm)") from exc


def _valid_ids(keys) -> list:
    import uuid

    result = []
    for key in keys:
        try:
            result.append(uuid.UUID(key))
        except (TypeError, ValueError):
            continue
    return result


def _latest_questions(enrollment):
    row = (
        ExamScoreEntry.objects.filter(enrollment=enrollment, assessment=ExamAssessment.MIDTERM)
        .order_by("-created_at")
        .values_list("question_scores", flat=True)
        .first()
    )
    return row if row else None


def _result(slots) -> dict:
    written, skipped, errors, failed_by_enrollment, written_ids = 0, 0, [], {}, []
    for slot in slots:
        state = slot["state"]
        if state in ("inactive", "failed"):
            label = entry_service._student_label(slot["enrollment"]) if slot["enrollment"] is not None else slot["key"]
            errors.append((label, slot["message"]))
            failed_by_enrollment[slot["key"]] = slot["message"]
        elif state == "skipped":
            skipped += 1
        else:
            written += 1
            written_ids.append(slot["key"])
    return {
        "written": written,
        "skipped": skipped,
        "failed": len(errors),
        "total": len(slots),
        "errors": errors,
        "failed_by_enrollment": failed_by_enrollment,
        "written_ids": written_ids,
    }


def roster_for_offering(*, offering) -> dict:
    """Midterm siyahısı — ``exam_score_roster.roster_for_offering``-in midterm güzgüsü (sətir açarları eynidir).

    Bal jurnalın «Midterm» xanasından; tarixçə yalnız ``assessment=midterm`` sətirləri. Giriş/yekun/hərf
    sütunları midterm-ə aid deyil (``graded=False``). Sorğu sayı siyahı ölçüsündən asılı deyil.
    """
    from .exam_score_roster import entry_row

    component = midterm_component(offering)
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student", "student__profile")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    scores = {
        cs.enrollment_id: cs for cs in ComponentScore.objects.filter(component=component, enrollment__in=enrollments)
    }
    history: dict = {}
    entries_qs = ExamScoreEntry.objects.filter(enrollment__in=enrollments, assessment=ExamAssessment.MIDTERM)
    for entry in entries_qs.select_related("entered_by", "sheet"):
        history.setdefault(entry.enrollment_id, []).append(entry)
    cap = int(component.max_score)
    rows = []
    for enrollment in enrollments:
        entries = history.get(enrollment.pk, [])
        cell = scores.get(enrollment.pk)
        student = enrollment.student
        rows.append(
            {
                "enrollment": enrollment,
                "student": student,
                "name": student.get_full_name() or student.username,
                "exam_score": cell.score if cell is not None else None,
                "has_score": cell is not None and cell.score is not None,
                "is_changed": any(entry.kind != "initial" for entry in entries),
                "question_scores": list(entries[0].question_scores) if entries and entries[0].question_scores else [],
                "exam_score_max": cap,
                "entry_score": None,
                "total": None,
                "letter": "",
                "graded": False,
                "passed": False,
                "failed": False,
                "barred": False,
                "bonus": 0,
                # Müəllim jurnalda əl ilə yazıb (kağız tarixçəsi yoxdur) — ilk köçürmə sərbəstdir.
                "teacher_written": cell is not None and not cell.exam_source and not entries,
                "entries": [entry_row(entry) for entry in entries],
                "attempts": [],
            }
        )
    return {
        "offering": offering,
        "rows": rows,
        "exam_score_max": cap,
        "letter_bands": [],
        "pass_threshold": 0,
        "min_final_exam_score": 0,
    }


__all__ = ["AUDIT_KIND", "journal_locked_error", "midterm_component", "roster_for_offering", "save_rows"]
