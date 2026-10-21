"""Test formatlı midterm → elektron jurnalın «Midterm» xanası (sahib 2026-10-21).

Sahib: «Midterm test olaraq verənlərdə avtomatik olaraq jurnala da düşsün, tələbənin balı əl ilə
doldurulmasın, tələbədə görünsün». Bu modul registrar tərəfidir — exams tərəfi
(``apps/exams/services/midterm_journal_sync.py``) onu ``apps.registrar.public`` fasadı ilə çağırır
(registrar exams-ı import etmir; cəhd haqqında lazım olan hər şey arqument kimi gəlir).

Qaydalar:

* **Hədəf** — açılışın aralıq komponenti («Midterm», ``ComponentKind.KOLLOKVIUM``, ``k_index=0``),
  ``interim_components.ensure_kollokviums`` ilə — müəllimin tabı ilə EYNİ xana. Keçmiş (K1–K3
  kollokvium) dövrlərdə yazılmır (``not_midterm_period``).
* **Şkala** — ``round_half_up(faiz × tavan / 100)``, tavan komponentin FAKTİKİ ``max_score``-u (RİM
  qaydası ``core.academic_rules.midterm_max``: 30, sərbəst iş açıqdırsa 20 — komponent bu qaydanı
  izləyir və DB qoruyucusu da onu tutur). Yuvarlaqlaşdırma yekun körpüsü ilə ORTAQDIR
  (``exam_bridge.scale_percent``). Proctordan qovulma → 0.
* **Mənbə** — ``ComponentScore.exam_source`` (cəhd id, imtahan adı/slug, faiz). Dolu mənbəli xananı
  müəllim jurnalda dəyişə bilmir (``gradebook_components.save_component_scores`` onu ötürür).
* **Sistem yazısı** — İmtahan Mərkəzi pəncərəsindən və 2 saat kilidindən asılı deyil
  (``journal_unlock`` — sənədli düzəlişin işlətdiyi rəsmi yol). Bağlanmış (dərc olunmuş) jurnala
  yazılmır (``journal_locked``) — giriş balı bağlı jurnalda dəyişmir.
* **Yeganə əl ilə müdaxilə** — RİM / İKT rəhbərinin sənədli düzəlişi
  (``item_corrections.apply_component_correction``, PDF + səbəb + audit). Cəhd BİTDİKDƏN SONRA
  edilmiş qüvvədə olan düzəliş varsa həmin cəhdin təkrar sinxronizasiyası (apellyasiya, açar düzəlişi)
  onu əzmir (``overridden``); düzəlişdən sonra bitən YENİ cəhd yenə yazır.
* **İdempotent** — bal və mənbə eynidirsə heç nə yazılmır; audit + bildiriş YALNIZ bal dəyişəndə.
* **Audit fail-closed** (rəy 2026-10-21, R08) — audit sətri yazılmasa xana da yazılmır
  (``audit_write.AuditWriteFailed``); exams tərəfi onu ``write_failed`` kimi sayır.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.registrar import exam_bridge, grade_audit, interim_assessment, interim_components
from apps.registrar.gradebook import journal_is_locked
from apps.registrar.models import ComponentKind, ComponentScore, ComponentScoreCorrection, CourseOffering

logger = logging.getLogger(__name__)

#: ``record_midterm_result`` nəticə statusları (exams tərəfi sayğaca yazır).
WRITTEN = "written"
UNCHANGED = "unchanged"
NO_ENROLLMENT = "no_enrollment"
NOT_MIDTERM_PERIOD = "not_midterm_period"
JOURNAL_LOCKED = "journal_locked"
OVERRIDDEN = "overridden"

#: Audit izinin növü (``registrar.grade.midterm-auto``) — jurnal tarixçəsi eyni prefiksdən oxuyur.
AUDIT_KIND = "midterm-auto"


def is_auto_score(score_row) -> bool:
    """Xana test midterm cəhdindən avtomatik yazılıbmı (müəllim dəyişə bilməz)."""
    return bool(getattr(score_row, "exam_source", None))


def _percent_label(percent) -> str:
    """Faiz etiketi (1 onluq, «.0» atılır) — mənbə nişanında «… (66.7%)»."""
    try:
        value = round(float(percent), 1)
    except (TypeError, ValueError):
        return str(percent)
    return f"{value:g}" if value == int(value) else f"{value:.1f}"


def _source_payload(*, attempt_id, exam_id, exam_title, exam_slug, percent) -> dict:
    return {
        "attempt_id": int(attempt_id),
        "exam_id": int(exam_id) if exam_id is not None else None,
        "exam_title": str(exam_title or "")[:255],
        "exam_slug": str(exam_slug or "")[:255],
        "percent": _percent_label(percent),
    }


def _overridden(component, enrollment, attempt_finished_at) -> bool:
    """Cəhd bitdikdən SONRA edilmiş, geri alınmamış sənədli düzəliş varmı (RİM müdaxiləsi qalib gəlir)."""
    corrections = ComponentScoreCorrection.objects.filter(
        component=component, enrollment=enrollment, reversal__isnull=True
    )
    if attempt_finished_at is not None:
        corrections = corrections.filter(created_at__gt=attempt_finished_at)
    return corrections.exists()


def _writer(organization, by_user):
    """``entered_by`` — reviewer (apellyasiya) yalnız təşkilatda yaza bilirsə; yoxsa sistem (``None``)."""
    if by_user is not None and exam_bridge._actor_can_write(organization, by_user):
        return by_user
    return None


def record_midterm_result(
    *,
    student,
    subject_id,
    organization,
    score_percent,
    attempt_id,
    exam_id=None,
    exam_title="",
    exam_slug="",
    attempt_finished_at=None,
    is_expelled=False,
    by_user=None,
    appeal_id=None,
    notify=True,
):
    """Test midterm cəhdinin nəticəsini jurnalın «Midterm» xanasına yaz → ``(status, ComponentScore | None)``.

    Çağıran (exams) cəhdin RƏSMİ olduğunu (bitib, sınaq deyil, sonrakı cəhdlə əvəzlənməyib, nəticə
    tələbəyə açıqdır) artıq yoxlayıb. ``notify=False`` — toplu bərpa (``sync_midterm_scores``) üçün."""
    enrollment = exam_bridge.resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None:
        return NO_ENROLLMENT, None
    offering = enrollment.offering
    if not interim_assessment.is_midterm_offering(offering):
        return NOT_MIDTERM_PERIOD, None
    with transaction.atomic():
        return _write(
            offering=offering,
            enrollment=enrollment,
            score_percent=score_percent,
            source=_source_payload(
                attempt_id=attempt_id,
                exam_id=exam_id,
                exam_title=exam_title,
                exam_slug=exam_slug,
                percent=score_percent,
            ),
            attempt_finished_at=attempt_finished_at,
            is_expelled=is_expelled,
            by_user=_writer(organization, by_user),
            appeal_id=appeal_id,
            notify=notify,
        )


def _write(
    *, offering, enrollment, score_percent, source, attempt_finished_at, is_expelled, by_user, appeal_id, notify
):
    from core.rls import journal_unlock

    from .correction_target_locks import lock_component

    # Kilid sırası müəllim yazısı ilə eyni: açılış → komponent → qeydiyyat → xana.
    CourseOffering.objects.select_for_update().filter(pk=offering.pk).exists()
    if journal_is_locked(offering):
        return JOURNAL_LOCKED, None
    component = interim_components.ensure_kollokviums(offering)[0]
    component, enrollment, existing = lock_component(component, enrollment)
    if _overridden(component, enrollment, attempt_finished_at):
        return OVERRIDDEN, existing
    score = 0 if is_expelled else exam_bridge.scale_percent(score_percent, component.max_score)
    old_score = existing.score if existing is not None else None
    score_changed = old_score is None or old_score != score
    if not score_changed and existing.exam_source == source:
        return UNCHANGED, existing
    with journal_unlock():  # 2 saat DB trigger-i — sistem yazısı rəsmi yoldur (sənədli düzəliş kimi)
        if existing is None:
            existing = ComponentScore.objects.create(
                organization_id=offering.organization_id,
                component=component,
                enrollment=enrollment,
                score=score,
                entered_by=by_user,
                exam_source=source,
            )
        else:
            existing.score = score
            existing.exam_source = source
            fields = ["exam_source", "updated_at"]
            if score_changed:
                existing.entered_by = by_user
                fields[:0] = ["score", "entered_by"]
            existing.save(update_fields=fields)
    if score_changed:
        _audit_and_notify(
            offering=offering,
            component=component,
            enrollment=enrollment,
            old_score=old_score,
            score=score,
            source=source,
            by_user=by_user,
            appeal_id=appeal_id,
            notify=notify,
        )
    return WRITTEN, existing


def _audit_and_notify(*, offering, component, enrollment, old_score, score, source, by_user, appeal_id, notify):
    change = {
        "student": grade_audit.student_label(enrollment),
        "item": component.name,
        "old": grade_audit.score_repr(old_score),
        "new": grade_audit.score_repr(score),
        "source": f"exam_attempt:{source['attempt_id']}",
        "note": "imtahan mərkəzi · avtomatik" if by_user is None else "imtahan mərkəzi · apellyasiya",
    }
    if appeal_id is not None:
        change["appeal"] = str(appeal_id)
    # R08 (2026-10-21): fail-closed — audit düşsə ``record_midterm_result``-un savepoint-i xananı geri qaytarır,
    # exams körpüsü ``write_failed`` sayır; növbəti sinxronizasiya (idempotent) yenidən yazır.
    grade_audit.log_grade_changes(
        offering=offering, by_user=by_user, kind=AUDIT_KIND, changes=[change], fail_closed=True
    )
    if not notify:
        return
    from apps.registrar import journal_notifications as jn

    event = {"enrollment": enrollment, "kind": jn.EVENT_KOLLOKVIUM, "score": score, "label": component.name}
    transaction.on_commit(lambda: jn.send_journal_events(offering=offering, events=[event]))


def auto_sources_for(components, enrollment_ids=None) -> dict:
    """``{(component_id, enrollment_id): exam_source}`` — yalnız avtomatik yazılmış aralıq xanaları (1 sorğu)."""
    components = [c for c in components if getattr(c, "kind", None) == ComponentKind.KOLLOKVIUM]
    if not components:
        return {}
    rows = ComponentScore.objects.filter(component__in=components, exam_source__isnull=False)
    if enrollment_ids is not None:
        rows = rows.filter(enrollment_id__in=list(enrollment_ids))
    return {
        (r.component_id, r.enrollment_id): r.exam_source
        for r in rows.only("component_id", "enrollment_id", "exam_source")
    }


def student_interim_rows(interim, components, enrollment) -> list[dict]:
    """Tələbə jurnalının aralıq qiymətləndirmə sətirləri (1 sorğu); ``auto`` — balı test midtermindən avtomatik."""
    if not components:
        return []
    rows = {
        cs.component_id: cs for cs in ComponentScore.objects.filter(component__in=components, enrollment=enrollment)
    }
    return [
        {
            "component": c,
            "score": getattr(rows.get(c.id), "score", None),
            "held_on": c.held_on,
            "label": interim.label_for(i),
            "auto": is_auto_score(rows.get(c.id)),
        }
        for i, c in enumerate(components)
    ]


__all__ = [
    "AUDIT_KIND",
    "JOURNAL_LOCKED",
    "NOT_MIDTERM_PERIOD",
    "NO_ENROLLMENT",
    "OVERRIDDEN",
    "UNCHANGED",
    "WRITTEN",
    "auto_sources_for",
    "is_auto_score",
    "record_midterm_result",
    "student_interim_rows",
]
