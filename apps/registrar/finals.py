"""Yekun qiymət + təkrar imtahan (finals/resit) — services (U3+).

Yekun bal = jurnaldan "giriş balı" (semestr fəaliyyəti, ≈50) + yekun imtahan
balı (≈50). Tələbə kəsilir (qayıb limitini keçib, VƏ YA ümumi bal < keçid həddi,
VƏ YA imtahan < minimum) → ``ResitRecord`` (təkrar imtahan hüququ). Təkrar
imtahan balı daxil ediləndə yekun yenidən hesablanır (resit balı imtahan balını
əvəz edir və qayıb bloku aradan qalxır). Jurnal finalizasiyası yalnız təsdiq
zəncirində edilir və həmin tranzaksiyada auditə yazılır.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.registrar import grade_audit, gradebook, grading_scale, services
from apps.registrar.exam_eligibility import fail_reason_code as eligibility_reason
from apps.registrar.exam_eligibility import status_code as eligibility_status
from apps.registrar.exam_eligibility import status_label as eligibility_label
from apps.registrar.exam_eligibility import status_notice as eligibility_notice
from apps.registrar.models import ApprovalStatus, Enrollment, FinalGrade, ResitReason, ResitRecord, ResitStatus


def _is_current_enrollment(enrollment) -> bool:
    """Check persisted state so a stale pre-transfer instance cannot write."""
    return Enrollment.objects.filter(pk=enrollment.pk, status=Enrollment.Status.ENROLLED).exists()


def score_to_letter(total, organization=None) -> tuple[str, Decimal]:
    """0..100 ümumi bal → hərf + GPA — tenant şkalası (U17, ``grading_scale``)."""
    return grading_scale.score_to_letter(total, organization)


def _to_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _clamp(raw, ceiling) -> Decimal:
    value = _to_decimal(raw)
    top = Decimal(int(ceiling))
    if value < 0:
        return Decimal("0")
    return top if value > top else value


def entry_score_for(enrollment, cap) -> Decimal:
    """Semester entry score — delegates to the canonical component-aware
    computation in :func:`gradebook.entry_score_for` (weighted components when
    defined, otherwise the legacy per-lesson mark sum)."""
    return gradebook.entry_score_for(enrollment, cap)


def exam_score_max(scheme) -> int:
    return max(0, 100 - scheme.entry_score_max)


def athlete_exemption(enrollment) -> bool:
    """Bu yazılışın tələbəsində rəsmi idmançı istisnası varmı (tək sorğu).

    ``compute_final_result`` sətir-sətir işlədiyi üçün toplu səthlər
    (``transcript``, ``analytics``) istisnanı ÖZLƏRİ həll edib ötürür —
    bu fallback yalnız tək-sətir çağırışları üçündür
    (:func:`exam_eligibility.exempt_student_ids` toplu variantdır).

    ⚠️ PUBLIC (adı alt-xətsizdir): imtahan **giriş qapısı** da
    (:func:`apps.registrar.exam_bridge.exam_eligibility`) məhz bunu çağırır.
    Qapı istisnanı ötürməyəndə idmançı-tələbə kabinetdə «buraxılır», imtahan
    qapısında isə «buraxılmır» görürdü — 3-cü blokerin ən bahalı halı, çünki
    orada söhbət ekran etiketindən yox, imtahana BURAXILMAMAQDAN gedirdi.
    """
    from apps.registrar.models import StudentAcademicRecord

    return bool(
        StudentAcademicRecord.objects.filter(
            organization_id=enrollment.organization_id, student_id=enrollment.student_id
        )
        .values_list("national_athlete_exemption", flat=True)
        .first()
    )


def compute_final_result(*, enrollment, scheme=None, organization=None, exempt=None, hours_map=None, batch=None):
    """Full result for one enrollment: entry + exam → total → letter → pass/fail.

    A completed resit supersedes the original exam score and lifts the absence
    bar. Until an exam (or resit) score exists the result is "not graded yet".
    ``organization`` feeds the tenant letter-band scale (U17); when omitted it
    is resolved from the scheme (FK-cached per instance).

    ``total`` TAM ƏDƏDDİR (sahibin qaydası, 2026-08-30): clamp-dan SONRA
    yarım-yuxarı yuvarlaqlaşdırılır (``gradebook.round_score``; 72.5 → 73,
    72.4 → 72) və hərf/keçid qərarı MƏHZ yuvarlaqlaşdırılmış dəyər üzərindən
    verilir (50.5 → 51 keçir).

    ``batch`` — :class:`apps.registrar.finals_batch.FinalsBatch`: roster
    səthləri (jurnalın «Yekun» tab-ı, transkript, «Nəticələrim») bu funksiyanı
    DÖNGÜDƏ çağırır, ona görə komponent/bal/sərbəst-iş/``FinalGrade``/
    ``ResitRecord``/donma/hədd/istisna oxumaları BİR dəfə toplu edilib buraya
    ötürülür.  Verilməsə davranış əvvəlki kimidir (sətir-sətir sorğu) — yazı
    yolları (``evaluate_resit``) məhz o yolla getməlidir ki, eyni tranzaksiyada
    təzəcə yazılmış bal görünsün."""
    scheme = scheme or getattr(enrollment.offering, "assessment_scheme", None)
    if scheme is None:
        scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    if organization is None:
        organization = scheme.organization

    entry_score = gradebook.entry_score_for(
        enrollment, scheme.entry_score_max, **(batch.entry_kwargs(enrollment) if batch is not None else {})
    )
    frozen = None
    if batch is None:
        # Query fresh (avoid a stale cached reverse-O2O after an update in the same request).
        final_grade = FinalGrade.objects.filter(enrollment=enrollment).first()
        resit = ResitRecord.objects.filter(enrollment=enrollment).first()
        limit_percent = gradebook.absence_limit_percent_for(enrollment.offering)
    else:
        final_grade = batch.final_grade_for(enrollment)
        resit = batch.resit_for(enrollment)
        limit_percent = batch.limit_percent_for(enrollment.offering)
        frozen = batch.frozen_for(enrollment.offering)
        if exempt is None:
            exempt = batch.exempt_for(enrollment)
        if hours_map is None:
            hours_map = batch.hours_map
    exam_score = final_grade.exam_score if (final_grade and final_grade.exam_score is not None) else None
    resit_done = bool(resit and resit.resit_score is not None)
    effective_exam = resit.resit_score if resit_done else exam_score

    # TƏK MƏNBƏ: «tamamlanmış təkrar imtahan qadağanı qaldırır» qaydası da artıq
    # resolver-in içindədir (``resit_done=``), burada TƏKRARLANMIR.  Tarixi/
    # köçürülmüş semestrdə ``barred`` heç vaxt qalxmır — aşağıdakı ``passed``/
    # ``failed`` köhnə sistemin faktiki imtahan balından çıxır.
    # İdmançı-tələbə istisnası da resolver-dən keçir (2026-08-31, 3-cü bloker):
    # əvvəl yalnız kabinet onu ötürürdü, yəni eyni tələbə kabinetdə «buraxılır»,
    # yekun/analitika yolunda «buraxılmır» görünürdü.  ``exempt=None`` = özün tap.
    eligibility = services.get_exam_eligibility(
        enrollment=enrollment,
        limit_percent=limit_percent,
        exempt=athlete_exemption(enrollment) if exempt is None else bool(exempt),
        resit_done=resit_done,
        # Məxrəc fallback-ı: döngüdə çağıran (transkript) map-i əvvəlcədən qurur.
        hours_map=hours_map,
        # Donma dəsti də toplu gəlir — ``None`` olduqda açılış başına sorğu olur.
        frozen=frozen,
    )
    barred = eligibility["barred"]

    bonus = final_grade.bonus if final_grade is not None else Decimal("0")
    graded = effective_exam is not None
    total = entry_score + (effective_exam or Decimal("0")) + bonus
    total = max(Decimal("0"), min(Decimal("100"), total))  # bonus/cərimə clamp (U15)
    total = gradebook.round_score(total)  # tam ədəd — hərf və keçid bundan hesablanır
    letter, gpa = score_to_letter(total, organization)
    exam_ok = graded and effective_exam >= scheme.min_final_exam_score
    passed = graded and not barred and total >= scheme.pass_threshold and exam_ok
    # Failed once we can judge it: barred (no exam needed) or graded-but-not-passed.
    failed = barred or (graded and not passed)

    return {
        "entry_score": entry_score,
        "exam_score": exam_score,
        "effective_exam": effective_exam,
        "total": total,
        "letter": letter,
        "gpa": gpa,
        "barred": barred,
        "graded": graded,
        "exam_ok": exam_ok,
        "passed": passed,
        "failed": failed,
        "resit": resit,
        "resit_done": resit_done,
        "pass_threshold": scheme.pass_threshold,
        "min_final_exam_score": scheme.min_final_exam_score,
        "exam_score_max": exam_score_max(scheme),
        "is_published": scheme.is_published,
        "eligibility": eligibility,
        # Şəffaflıq: status canlı qaydadan, köhnə sistemdən, yoxsa köhnə
        # sistemin BOŞLUĞUNDAN gəlir (bax exam_eligibility.status_code).
        "status_code": eligibility_status(eligibility, graded=graded),
        "status_label": eligibility_label(eligibility_status(eligibility, graded=graded)),
        "status_notice": eligibility_notice(eligibility_status(eligibility, graded=graded)),
        # Görünən sahələr də resolver-dən gəlir — çağıran yenidən hesablamır.
        "attendance_score": eligibility["attendance_score"],
        "exempt": eligibility["exempt"],
        "fail_reason": (eligibility_reason({"barred": barred, "graded": graded, "passed": passed}) if failed else ""),
        "bonus": bonus,
        "comment": final_grade.comment if final_grade is not None else "",
    }


def _resit_reason(result) -> str:
    if result["barred"]:
        return ResitReason.ABSENCE
    if result["graded"] and not result["exam_ok"]:
        return ResitReason.EXAM
    return ResitReason.TOTAL


@transaction.atomic
def evaluate_resit(*, enrollment, by_user=None):
    """Sync the enrollment's ResitRecord with the current result.

    Creates/keeps an ``eligible`` resit when the student is failing; removes a
    still-unused eligible resit once they pass."""
    if not _is_current_enrollment(enrollment):
        return enrollment.resit_records.first()
    result = compute_final_result(enrollment=enrollment)
    existing = enrollment.resit_records.first()

    if result["failed"]:
        reason = _resit_reason(result)
        if existing is None:
            return ResitRecord.objects.create(
                organization=enrollment.organization,
                enrollment=enrollment,
                reason=reason,
                status=ResitStatus.ELIGIBLE,
                decided_by=by_user,
            )
        if existing.status == ResitStatus.ELIGIBLE and existing.reason != reason:
            existing.reason = reason
            existing.save(update_fields=["reason"])
        return existing

    # Passed → an untouched eligibility is no longer needed.
    if existing and existing.status == ResitStatus.ELIGIBLE and existing.resit_score is None:
        existing.delete()
        return None
    return existing


@transaction.atomic
def set_exam_score(*, enrollment, score, by_user=None, source_note=""):
    """Record the final-exam score (teacher/exam centre), then re-evaluate resit.

    ⚠️ JURNAL KİLİDİ BURADA TƏTBİQ OLUNMUR (sahibin qərarı, 2026-08).

    Jurnal semestr SONUNDA bağlanır, imtahan isə ondan SONRA keçir — yəni yekun
    imtahan balı demək olar həmişə KİLİDLİ jurnala düşür. Əvvəllər bu yol kilidli
    jurnalda sükutla ``None`` qaytarırdı və nəticə İTİRDİ (körpü tərəfdə yalnız
    WARNING kimi loglanırdı). İndi bölgü belədir:

    * GİRİŞ balı (jurnal xanaları: davamiyyət, dərs balı, kollokvium, sərbəst iş)
      — kilidlidir; dəyişiklik yalnız sənədli düzəlişlə (``corrections``) olur;
    * ÇIXIŞ balı (yekun imtahan) — kilidə TABE DEYİL, çünki imtahan jurnal
      bağlandıqdan sonra keçir.

    ``set_resit_score`` və ``set_final_extras`` kilid yoxlamasını SAXLAYIR —
    onlar jurnal-daxili redaktədir.

    ``source_note`` — audit izində bal sətrinin yanına yazılan MƏNBƏ qeydi
    (məsələn "imtahan mərkəzi · avtomatik"): aktoru olmayan sistem yazılarının
    tarixçədə boş "kim?" xanası ilə qalmaması üçün (2026-08 auditi, G7).
    İDEMPOTENT: ``get_or_create`` + yalnız real dəyişiklikdə audit."""
    if not _is_current_enrollment(enrollment):
        return None
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    final_grade, _created = FinalGrade.objects.get_or_create(
        organization=enrollment.organization, enrollment=enrollment
    )
    old_score = final_grade.exam_score
    new_score = _clamp(score, exam_score_max(scheme)) if score not in (None, "") else None
    final_grade.exam_score = new_score
    final_grade.entered_by = by_user
    final_grade.save()
    if old_score != new_score:
        grade_audit.log_grade_changes(
            offering=enrollment.offering,
            by_user=by_user,
            kind="final",
            changes=[
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": f"Yekun imtahan ({source_note})" if source_note else "Yekun imtahan",
                    "old": grade_audit.score_repr(old_score),
                    "new": grade_audit.score_repr(new_score),
                }
            ],
        )
    evaluate_resit(enrollment=enrollment, by_user=by_user)
    return final_grade


@transaction.atomic
def set_resit_score(*, enrollment, score, by_user=None):
    """Record a resit exam score → mark the resit completed + recompute."""
    if not _is_current_enrollment(enrollment):
        return None
    scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
    if gradebook.journal_is_locked(enrollment.offering):
        return None
    resit = enrollment.resit_records.first()
    if resit is None:
        return None  # not eligible for a resit
    old_score = resit.resit_score
    resit.resit_score = _clamp(score, exam_score_max(scheme)) if score not in (None, "") else None
    resit.status = ResitStatus.COMPLETED if resit.resit_score is not None else ResitStatus.ELIGIBLE
    resit.decided_by = by_user
    resit.save()
    if old_score != resit.resit_score:
        grade_audit.log_grade_changes(
            offering=enrollment.offering,
            by_user=by_user,
            kind="resit",
            changes=[
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": "Təkrar imtahan",
                    "old": grade_audit.score_repr(old_score),
                    "new": grade_audit.score_repr(resit.resit_score),
                }
            ],
        )
    return resit


_BONUS_LIMIT = Decimal("20")


@transaction.atomic
def set_final_extras(*, enrollment, bonus=None, comment=None, by_user=None):
    """Bonus/cərimə (±%(limit)s) və yekun rəyi yaz (U15).

    Bonus bal düzəlişidir → dəyişikliyi qiymət audit izinə yazılır; rəy bal
    deyil, audit olunmur. Jurnal kilidlidirsə heç nə yazılmır.""" % {"limit": _BONUS_LIMIT}
    if not _is_current_enrollment(enrollment) or gradebook.journal_is_locked(enrollment.offering):
        return None
    final_grade, _created = FinalGrade.objects.get_or_create(
        organization=enrollment.organization, enrollment=enrollment
    )
    changed_fields = []
    if bonus is not None:
        value = _to_decimal(bonus)
        value = max(-_BONUS_LIMIT, min(_BONUS_LIMIT, value))
        if value != final_grade.bonus:
            grade_audit.log_grade_changes(
                offering=enrollment.offering,
                by_user=by_user,
                kind="final",
                changes=[
                    {
                        "student": grade_audit.student_label(enrollment),
                        "item": "Bonus/cərimə",
                        "old": grade_audit.score_repr(final_grade.bonus),
                        "new": grade_audit.score_repr(value),
                    }
                ],
            )
            final_grade.bonus = value
            changed_fields.append("bonus")
    if comment is not None:
        cleaned = comment.strip()[:500]
        if cleaned != final_grade.comment:
            final_grade.comment = cleaned
            changed_fields.append("comment")
    if changed_fields:
        final_grade.entered_by = by_user
        final_grade.save(update_fields=changed_fields + ["entered_by", "updated_at"])
        evaluate_resit(enrollment=enrollment, by_user=by_user)
    return final_grade


@transaction.atomic
def publish_offering(*, offering, by_user=None):
    """Compatibility guard: only the full approval chain may publish."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if scheme.approval_status != ApprovalStatus.APPROVED or not scheme.is_published:
        raise PermissionDenied("Jurnal yalnız tam təsdiq zənciri ilə rəsmiləşdirilə bilər.")
    return scheme


def get_offering_results(*, offering, batch=None):
    """Per-student final result rows for the teacher's "Yekun/Nəticə" grid.

    ⚠️ TOPLU SƏTHDİR: sətir başına ~18 sorğu (555 tələbəlik açılışda 10 000)
    əvəzinə ``finals_batch`` ilə sabit ~11 sorğu edilir.  ``batch`` xaricdən
    verilə bilər — jurnal səhifəsi eyni dəsti qrid və «Yekun» tab-ı ilə bölüşür.
    """
    from apps.registrar import finals_batch

    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    enrollments = list(
        offering.enrollments.filter(status=offering.enrollments.model.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    if batch is None:
        batch = finals_batch.build(enrollments)
    rows = [
        {
            "enrollment": e,
            "student": e.student,
            "result": compute_final_result(enrollment=e, scheme=scheme, batch=batch),
        }
        for e in enrollments
    ]
    return {"offering": offering, "scheme": scheme, "rows": rows}
