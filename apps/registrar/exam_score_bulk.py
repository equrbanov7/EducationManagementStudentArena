"""İmtahan balının TOPLU yazısı — ``exam_score_entry.save_roster_scores``-un sabit sorğulu yolu.

2026-10-08 tutum testi (10 app × 1 CPU, DB 6 CPU, 300 müəllim): «jf exam-score save»
p50 1.2 s idi. 25 tələbəlik siyahının yadda saxlanması ~1 190 sorğu edirdi — sətir
başına ~47: qeydiyyat kilidi ×2, aktivlik yoxlaması ×2, sxem ×4, ``FinalGrade`` ×4,
təşkilat ×3, ``ResitRecord`` ×2, ``evaluate_resit``-in batch-siz yenidən hesablaması
(komponent, bal, dərs balları, hədd, istisna …), FK/pk validasiyası ×3, audit ×2 və
~14 SAVEPOINT. Burada sorğu sayı sətir sayından ASILI DEYİL.

Qayda və ardıcıllıq ``record_exam_score`` ilə EYNİDİR — qərar köməkçiləri ortaqdır
(``clean_row_score``, ``change_decision``, ``new_entry``, ``entry_log``,
``finals.resit_action``, ``finals.exam_score_change``, ``grade_audit.grade_change_row``):

1. aktiv qeydiyyatlar BİR sorğu ilə; sətirlər ``enrollment_id`` sırası ilə emal olunur
   (tutum testi 2026-10-05 deadlock düzəlişi saxlanılır);
2. balı boş olmayan sətirlərin qeydiyyatları BİR ``SELECT … ORDER BY id FOR UPDATE`` ilə
   kilidlənir — kilid sırası əvvəlki sətir-sətir kilidlə eynidir (id artan);
3. kilidDƏN SONRA ``FinalGrade`` / ``ResitRecord`` / giriş balı girişləri toplu oxunur
   (``finals_batch``); yeni yazılan bal batch-ə YERİNDƏ qoyulur, ona görə
   ``evaluate_resit``-in qərarı tək yoldakı təzə oxu ilə eynidir;
4. hər sətrin qərarı (validasiya, eyni bal, bitmiş dövr qaydası, təqdimat, aktivlik)
   yaddaşda verilir — xəta YALNIZ həmin sətri dayandırır və heç bir yazı yarımçıq
   qalmır (əvvəlki sətir savepoint-inin semantikası);
5. yazılar toplu: ``FinalGrade`` (``bulk_update`` + ``bulk_create``), qiymət audit izi
   (best-effort, öz savepoint-ində — ``log_grade_changes`` siyasəti), ``ResitRecord``
   (yarat / səbəbi yenilə / sil), ``ExamScoreEntry`` və ``log_action`` sətirləri.

Eyni qeydiyyat siyahıda iki dəfə gələrsə (forma və idxal bunu etmir — idxal dublikatı
rədd edir) köhnə sətir-sətir yol (``record_exam_score``) işləyir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.audit import log_actions

from . import exam_score_entry as entry_service
from . import exam_score_questions as questions
from . import finals, finals_batch, grade_audit, gradebook
from .audit_write import create_audit_rows
from .corrections import correction_author_name
from .models import Enrollment, ExamScoreEntry, FinalGrade, ResitRecord, ResitStatus

#: ``full_clean``-də buraxılan sahələr: ``organization`` / ``enrollment`` bu sorğuda oxunmuş
#: və kilidlənmiş sətirlərdir (FK mövcudluq sorğusu lazımsızdır), ``entered_by`` / ``sheet``
#: tək yolda da buraxılır. Fayl validatorları, seçimlər və ``clean()`` İŞLƏYİR.
_CLEAN_EXCLUDE = ["entered_by", "sheet", "organization", "enrollment"]

_INACTIVE = "inactive"
_FAILED = "failed"
_SKIPPED = "skipped"
_WRITTEN = "written"


def save_rows(*, offering, rows, by_user, request=None, sheet=None, policy):
    """``save_roster_scores``-un yazısı (siyasət və partiya yoxlaması çağırandadır)."""
    # Tutum testi 2026-10-05 (deadlock düzəlişi — SAXLANILIR): qeydiyyat kilidi çağıranın
    # tranzaksiyası boyu qalır; iki işçi eyni siyahını fərqli ardıcıllıqla saxlayanda deadlock
    # alınırdı — sətirlər sabit (enrollment_id) ardıcıllıqla emal olunur, kilid də o sıra ilə.
    ordered = sorted(rows, key=lambda r: str(r.get("enrollment_id") or ""))
    keys = [str(row.get("enrollment_id") or "") for row in ordered]
    if len(set(keys)) != len(keys):
        return _save_sequential(
            offering=offering, ordered=ordered, by_user=by_user, request=request, sheet=sheet, policy=policy
        )
    with transaction.atomic():
        return _BulkSave(offering=offering, by_user=by_user, request=request, sheet=sheet, policy=policy).run(ordered)


def _active_enrollments(offering, *related):
    return {
        str(enrollment.id): enrollment
        for enrollment in offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related(*related)
    }


def _cached_relation(instance, name):
    """FK artıq yüklənibsə onu qaytar (sorğusuz), yoxsa ``None``."""
    return getattr(getattr(instance, "_state", None), "fields_cache", {}).get(name)


class _BulkSave:
    """Bir POST-un toplu yazısı — sətirlərin vəziyyəti ``slots``-da (sıra = ``enrollment_id``)."""

    def __init__(self, *, offering, by_user, request, sheet, policy):
        self.offering = offering
        self.by_user = by_user
        self.request = request
        self.sheet = sheet
        self.policy = policy
        self.scheme = gradebook.ensure_assessment_scheme(offering=offering)
        self.cap = finals.exam_score_max(self.scheme)

    # ── 1. sətirlər: aktivlik + balın təmizlənməsi (sorğusuz) ────────────────

    def run(self, ordered):
        enrollments = _active_enrollments(self.offering, "student", "organization")
        slots, pending = [], []
        for row in ordered:
            key = str(row.get("enrollment_id") or "")
            enrollment = enrollments.get(key)
            slot = {"key": key, "row": row, "enrollment": enrollment, "state": None, "message": ""}
            slots.append(slot)
            if enrollment is None:
                slot["state"], slot["message"] = _INACTIVE, entry_service.inactive_enrollment_message()
                continue
            # Bütün sətirlər EYNİ açılış obyektini paylaşır (sxem/fənn/dövr keşi bir dəfə).
            enrollment.offering = self.offering
            try:
                entry_service.assert_sheet_matches(
                    self.sheet, organization_id=enrollment.organization_id, offering_id=enrollment.offering_id
                )
                cleaned, new_score = entry_service.clean_row_score(
                    score=row.get("score"), question_scores=row.get("question_scores"), sheet=self.sheet, cap=self.cap
                )
            except ValidationError as exc:
                _fail(slot, exc)
                continue
            if new_score is None:
                slot["state"] = _SKIPPED  # boş sahə = toxunma
                continue
            slot["questions"], slot["score"] = cleaned, new_score
            pending.append(slot)
        if pending:
            self._decide_and_write(pending)
        return _result(slots)

    # ── 2-4. kilid → təzə oxu → sətir qərarları ───────────────────────────────

    def _decide_and_write(self, pending):
        # Əvvəlki sətir-sətir `select_for_update` ilə EYNİ kilid obyekti və EYNİ sıra (id artan;
        # kanonik UUID mətninin sırası = PostgreSQL uuid sırası): `ORDER BY id … FOR UPDATE`
        # sətirləri sıralanmış çıxışla kilidləyir. Status kilidlənmiş (təzə) sətirdən oxunur —
        # `finals._is_current_enrollment` yoxlamasının toplu güzgüsü.
        status_by_id = dict(
            Enrollment.objects.select_for_update()
            .filter(pk__in=[slot["enrollment"].pk for slot in pending])
            .order_by("pk")
            .values_list("pk", "status")
        )
        batch = finals_batch.build(
            [slot["enrollment"] for slot in pending],
            organization=self.offering.organization,
            period=_cached_relation(self.offering, "period"),
        )
        latest = self._latest_question_scores(pending, batch)
        author = correction_author_name(self.by_user, self.request)
        writes = []
        for slot in pending:
            enrollment, row = slot["enrollment"], slot["row"]
            final_grade = batch.final_grades.get(enrollment.id)
            old_score = final_grade.exam_score if final_grade is not None else None
            try:
                entry_score = gradebook.entry_score_for(
                    enrollment, self.scheme.entry_score_max, **batch.entry_kwargs(enrollment)
                )
                questions.assert_total_within_hundred(entry_score, slot["score"])
                is_correction = entry_service.change_decision(
                    old_score=old_score,
                    new_score=slot["score"],
                    cleaned_questions=slot["questions"],
                    latest_question_scores=lambda eid=enrollment.id: latest.get(eid),
                    policy=self.policy,
                    reason=row.get("reason") or "",
                    note=row.get("note") or "",
                    evidence=row.get("evidence"),
                    sheet=self.sheet,
                )
                if is_correction is None:
                    slot["state"] = _SKIPPED  # eyni bal → nə dublikat sətir, nə audit
                    continue
                entry = entry_service.new_entry(
                    enrollment=enrollment,
                    organization=enrollment.organization,
                    is_correction=is_correction,
                    kind=row.get("kind") or "",
                    old_score=old_score,
                    new_score=slot["score"],
                    cleaned_questions=slot["questions"],
                    reason=row.get("reason") or "",
                    note=row.get("note") or "",
                    evidence=row.get("evidence"),
                    by_user=self.by_user,
                    author_name=author,
                    sheet=self.sheet,
                )
                # Fayl (şəkil/PDF) ölçü + tip validatorları BAL YAZILMAMIŞDAN ƏVVƏL işləsin.
                entry.full_clean(exclude=_CLEAN_EXCLUDE, validate_unique=False)
                if status_by_id.get(enrollment.pk) != Enrollment.Status.ENROLLED:
                    # Kilidli (təzə) sətir: qeydiyyat artıq aktiv deyil — sətir yazılmır.
                    raise ValidationError(entry_service.inactive_enrollment_message())
            except ValidationError as exc:
                _fail(slot, exc)
                continue
            slot.update(state=_WRITTEN, entry=entry, old_score=old_score)
            writes.append(slot)
        if writes:
            self._write(writes, batch)

    def _latest_question_scores(self, pending, batch) -> dict:
        """Eyni cəm + sual bölgüsü verilən sətirlər üçün sonuncu daxiletmənin bölgüsü (BİR sorğu)."""
        wanted = []
        for slot in pending:
            final_grade = batch.final_grades.get(slot["enrollment"].id)
            old_score = final_grade.exam_score if final_grade is not None else None
            if slot["questions"] is not None and entry_service._same_score(old_score, slot["score"]):
                wanted.append(slot["enrollment"].pk)
        latest: dict = {}
        if wanted:
            rows = (
                ExamScoreEntry.objects.filter(enrollment_id__in=wanted)
                .order_by("-created_at")
                .values_list("enrollment_id", "question_scores")
            )
            for enrollment_id, scores in rows:
                latest.setdefault(enrollment_id, scores if scores else None)
        return latest

    # ── 5. toplu yazılar ────────────────────────────────────────────────────

    def _write(self, writes, batch):
        now = timezone.now()
        created, updated, grade_rows = [], [], []
        for slot in writes:
            enrollment, new_score, old_score = slot["enrollment"], slot["score"], slot["old_score"]
            final_grade = batch.final_grades.get(enrollment.id)
            if final_grade is None:
                final_grade = FinalGrade(
                    organization=enrollment.organization,
                    enrollment=enrollment,
                    exam_score=new_score,
                    entered_by=self.by_user,
                )
                created.append(final_grade)
                # Batch TƏZƏ dəyəri görsün — evaluate_resit tək yolda yazıdan sonra yenidən oxuyur.
                batch.final_grades[enrollment.id] = final_grade
            else:
                final_grade.exam_score = new_score
                final_grade.entered_by = self.by_user
                final_grade.updated_at = now
                updated.append(final_grade)
            if old_score != new_score:
                grade_rows.append(
                    grade_audit.grade_change_row(
                        offering=self.offering,
                        by_user=self.by_user,
                        kind="final",
                        changes=[
                            finals.exam_score_change(
                                enrollment, old_score, new_score, source_note=entry_service.SOURCE_NOTE
                            )
                        ],
                    )
                )
        if created:
            FinalGrade.objects.bulk_create(created)
        if updated:
            FinalGrade.objects.bulk_update(updated, ["exam_score", "entered_by", "updated_at"])
        create_audit_rows(grade_rows)  # best-effort — ``log_grade_changes`` ilə eyni siyasət
        self._sync_resits(writes, batch)
        ExamScoreEntry.objects.bulk_create([slot["entry"] for slot in writes])
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

    def _sync_resits(self, writes, batch):
        """``finals.evaluate_resit`` — eyni qərar (``resit_action``), yazılar toplu."""
        creates, reasons, deletes = [], [], []
        for slot in writes:
            enrollment = slot["enrollment"]
            result = finals.compute_final_result(
                enrollment=enrollment, scheme=self.scheme, organization=self.offering.organization, batch=batch
            )
            existing = batch.resits.get(enrollment.id)
            action, reason = finals.resit_action(result, existing)
            if action == finals.RESIT_CREATE:
                creates.append(
                    ResitRecord(
                        organization=enrollment.organization,
                        enrollment=enrollment,
                        reason=reason,
                        status=ResitStatus.ELIGIBLE,
                        decided_by=self.by_user,
                    )
                )
            elif action == finals.RESIT_UPDATE_REASON:
                existing.reason = reason
                reasons.append(existing)
            elif action == finals.RESIT_DELETE:
                deletes.append(existing.pk)
        if creates:
            ResitRecord.objects.bulk_create(creates)
        if reasons:
            ResitRecord.objects.bulk_update(reasons, ["reason"])
        if deletes:
            ResitRecord.objects.filter(pk__in=deletes).delete()


def _fail(slot, exc):
    slot["state"], slot["message"] = _FAILED, " ".join(exc.messages)


def _result(slots) -> dict:
    written, skipped, errors, failed_by_enrollment, written_ids = 0, 0, [], {}, []
    for slot in slots:
        state = slot["state"]
        if state == _INACTIVE:
            errors.append((slot["key"], slot["message"]))
            failed_by_enrollment[slot["key"]] = slot["message"]
        elif state == _FAILED:
            errors.append((entry_service._student_label(slot["enrollment"]), slot["message"]))
            failed_by_enrollment[str(slot["enrollment"].id)] = slot["message"]
        elif state == _SKIPPED:
            skipped += 1
        else:
            written += 1
            written_ids.append(str(slot["enrollment"].id))
    return {
        "written": written,
        "skipped": skipped,
        "failed": len(errors),
        "total": len(slots),
        "errors": errors,
        "failed_by_enrollment": failed_by_enrollment,
        "written_ids": written_ids,
    }


def _save_sequential(*, offering, ordered, by_user, request, sheet, policy):
    """Köhnə sətir-sətir yol (eyni qeydiyyat iki dəfə gələndə): hər sətir öz savepoint-ində."""
    enrollments = _active_enrollments(offering, "student", "offering")
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    batch = finals_batch.build(list(enrollments.values()), with_finals=False)
    entry_scores = {
        enrollment_id: gradebook.entry_score_for(enrollment, scheme.entry_score_max, **batch.entry_kwargs(enrollment))
        for enrollment_id, enrollment in enrollments.items()
    }
    slots = []
    for row in ordered:
        key = str(row.get("enrollment_id") or "")
        enrollment = enrollments.get(key)
        slot = {"key": key, "row": row, "enrollment": enrollment, "state": None, "message": ""}
        slots.append(slot)
        if enrollment is None:
            slot["state"], slot["message"] = _INACTIVE, entry_service.inactive_enrollment_message()
            continue
        try:
            with transaction.atomic():
                entry = entry_service.record_exam_score(
                    enrollment=enrollment,
                    score=row.get("score"),
                    by_user=by_user,
                    reason=row.get("reason") or "",
                    note=row.get("note") or "",
                    evidence=row.get("evidence"),
                    request=request,
                    sheet=sheet,
                    question_scores=row.get("question_scores"),
                    kind=row.get("kind") or "",
                    entry_score=entry_scores.get(key),
                    period_policy=policy,
                )
        except ValidationError as exc:
            _fail(slot, exc)
            continue
        slot["state"] = _SKIPPED if entry is None else _WRITTEN
    return _result(slots)


__all__ = ["save_rows"]
