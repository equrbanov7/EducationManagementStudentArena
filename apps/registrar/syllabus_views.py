"""«Sillabusa bax» səthi — jurnal (müəllim) və kabinet (tələbə) üçün ORTAQ.

İki istehlakçı, BİR giriş qapısı: :func:`_resolve` hər sorğunu açılışa
(``CourseOffering``) bağlayır və rolu iki rejimdən birinə salır —

``staff``    jurnalı aça bilən şəxs (müəllim / org sahibi / superuser / İKT
             korrektoru). Açıq (qərar gözləyən) versiyanı, o yoxdursa
             təsdiqlənmiş nüsxəni görür.
``student``  həmin açılışa qeydiyyatlı tələbə. ⚠️ YALNIZ ``APPROVED``
             versiyanı görür; yeni versiya təsdiqlənməyibsə ƏVVƏLKİ təsdiqlənmiş
             versiya görünməyə davam edir (``approved_version_for``).

FAIL-CLOSED: hər iki qapıdan keçməyən istifadəçi 404 alır (403 deyil — jurnalın
qalan səthləri kimi mövcudluq sızdırılmır). Açılışın özü
``journal_access.offering_or_404`` ilə aktiv tenant-a bağlı yüklənir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from apps.syllabus import public as syllabus_services
from apps.syllabus.public import activity_kinds_for_offering, build_document, rule_for_period

from . import journal_access
from .audit_write import create_audit_row

MODE_STAFF = "staff"
MODE_STUDENT = "student"
#: Yalnız-oxu jurnal girişi (``journal_access.can_observe_journal`` — kafedra müdiri / ``journal.view`` əhatəsi,
#: təhvil vermiş köhnə müəllim). Jurnal səhifəsində «Sillabusa bax» düyməsini görürdülər, amma panel 404
#: verirdi (2026-10-25). Tələbə kimi YALNIZ təsdiqlənmiş versiyanı görürlər.
MODE_OBSERVER = "observer"


def _(text):
    return pgettext("registrar.syllabus", text)


def _viewer_mode(request, offering) -> str | None:
    """``staff`` / ``student`` / ``observer`` / ``None`` — redaktə, qeydiyyat və yalnız-oxu qapıları."""
    from apps.registrar import corrections as corrections_service

    if journal_access.can_edit_journal(request.user, offering) or corrections_service.can_correct_journal(request):
        return MODE_STAFF

    from .models import Enrollment

    enrolled = Enrollment.objects.filter(
        offering=offering,
        student=request.user,
        organization=offering.organization,
    ).exists()
    if enrolled:
        return MODE_STUDENT
    return MODE_OBSERVER if journal_access.can_observe_journal(request.user, offering) else None


def _resolve(request, offering_id):
    """``(offering, syllabus, version, mode)`` — icazəsizdə/məzmunsuzda 404."""
    offering = journal_access.offering_or_404(request, offering_id)
    mode = _viewer_mode(request, offering)
    if mode is None:
        raise Http404

    syllabus = syllabus_services.syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )
    if syllabus is None:
        raise Http404

    if mode in (MODE_STUDENT, MODE_OBSERVER):
        version = syllabus_services.approved_version_for(syllabus)
    else:
        state = syllabus_services.offering_syllabus_state(syllabus)
        version = state["version"]
    if version is None:
        raise Http404
    return offering, syllabus, version, mode


@login_required
@require_GET
def offering_syllabus_json(request, offering_id):
    """Oxu-rejimli sillabus sənədi — jurnalın və kabinetin panelini doldurur."""
    offering, syllabus, version, mode = _resolve(request, offering_id)
    document = _document(offering, syllabus, version)
    approved_at = document.pop("approved_at", None)
    return JsonResponse(
        {
            "ok": True,
            "mode": mode,
            "subject": offering.subject.name,
            "approved_at": approved_at.strftime("%d.%m.%Y") if approved_at else "",
            # Tələbə üçün əlavə izah: gördüyü nüsxə niyə köhnə versiya ola bilər.
            "student_note": (
                _("Tələbələr yalnız təsdiqlənmiş versiyanı görür. Yeni versiya təsdiqlənənə qədər bu nüsxə qüvvədədir.")
                if mode == MODE_STUDENT
                else ""
            ),
            "pdf_url": _pdf_url(offering_id),
            # Həftəlik planın hər sətri üçün «keçilib» (tarixlərlə) / «keçilməyib» — sahib 2026-10-25.
            "week_progress": _week_progress(offering),
            **document,
        }
    )


def _week_progress(offering) -> dict:
    """TƏSDİQLƏNMİŞ planın sətirləri ↔ jurnal dərsləri (``journal_topics.week_progress``); plan yoxdursa boş.

    Göstərilən versiyadan (müəllim üçün açıq versiya ola bilər) asılı deyil: ``Lesson.syllabus_week`` qüvvədə
    olan təsdiqlənmiş planın sətir nömrəsidir."""
    from . import journal_topics

    week_rows = journal_topics.syllabus_week_rows(offering)
    if not week_rows:
        return {"rows": [], "covered": 0, "total": 0}
    lessons = list(offering.lessons.only("date", "topic", "syllabus_week"))
    rows = [
        {
            "week": row["week"],
            "title": row["title"] or "—",
            "covered": row["covered"],
            "planned": row["planned"],
            "dates": [day.strftime("%d.%m.%Y") for day in row["dates"]],
            "upcoming": [day.strftime("%d.%m.%Y") for day in row["upcoming"]],
        }
        for row in journal_topics.week_progress(offering, lessons, week_rows=week_rows)
    ]
    return {"rows": rows, "covered": sum(1 for row in rows if row["covered"]), "total": len(rows)}


def _document(offering, syllabus, version) -> dict:
    """Sənəd sillabusun CARİ qaydası ilə (sahib 2026-10-11: ``rule_for_period`` semestrdən asılı deyil —
    köhnə açılışda da «Sərbəst iş» bloku yoxdur, düstur midterm 30; RİM ``academic.selfwork_enabled``
    yandırılanda hər yerdə geri qayıdır). Jurnalın öz sərbəst iş qaydası (``core.academic_rules``) buna
    tabe deyil. Fəaliyyət növü açılışdandır (seminar / laboratoriya / 5 + 5)."""
    return build_document(
        syllabus,
        version,
        rule=rule_for_period(offering.period, offering.organization),
        activity_kinds=activity_kinds_for_offering(offering),
    )


def _pdf_url(offering_id) -> str:
    from django.urls import reverse

    return reverse("registrar:offering_syllabus_pdf", args=[offering_id])


@login_required
@require_GET
def offering_syllabus_pdf(request, offering_id):
    """Eyni sənədin PDF nüsxəsi — tələbə «PDF yüklə» düyməsindən alır."""
    from . import syllabus_pdf

    offering, syllabus, version, _mode = _resolve(request, offering_id)
    payload = syllabus_pdf.render_syllabus_pdf(
        organization=offering.organization,
        syllabus=syllabus,
        version=version,
        document=_document(offering, syllabus, version),
    )
    filename = f"sillabus-{offering.subject.code}-{version.label}.pdf"
    response = HttpResponse(payload, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    _audit_download(offering, version, request.user)
    return response


def _audit_download(offering, version, by_user):
    """Best-effort audit qeydi — mövcud ``audit_auditlog`` jurnalı (yeni jurnal YOX).

    Audit 2026-09-28 DB-01: SAVEPOINT-li yazı (audit_write)."""
    from core.constants import AuditAction

    create_audit_row(
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=offering.organization,
        action=AuditAction.UPDATE,
        resource_type="registrar.syllabus_pdf",
        resource_id=str(version.pk),
        resource_repr=f"{offering.subject.code} sillabusu {version.label} — PDF",
        reason="Sillabus PDF olaraq yükləndi.",
    )


__all__ = ["MODE_OBSERVER", "MODE_STAFF", "MODE_STUDENT", "offering_syllabus_json", "offering_syllabus_pdf"]
