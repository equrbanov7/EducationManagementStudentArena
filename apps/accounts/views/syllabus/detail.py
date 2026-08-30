"""Sillabusun AYRICA TAM SƏHİFƏSİ (`target="_blank"` hədəfi) + PDF nüsxəsi.

⚠️ Bu, profil bölməsi DEYİL: siyahı və təsdiq növbəsi əvvəlki kimi profil
qabığının içində (sol sidebar ilə) qalır, KONKRET bir sillabusun detalı isə
yeni tabda ayrıca səhifə kimi açılır. Ona görə burada ``SECTION_PARTIALS``
qeydiyyatı YOXDUR — səhifə ``base.html``-i extend edir.

──────────────────────────────────────────────────────────────────────────────
GİRİŞ QAPISI — iki rejim, BİR resolver (``resolve_access``)
──────────────────────────────────────────────────────────────────────────────
``staff``    ``syllabus.view`` + kafedra əhatəsi olan (və ya müəllif olan)
             şəxs. ``?version=<uuid>`` ilə konkret versiyanı aça bilir; parametr
             yoxdursa açıq (qərar gözləyən) versiya, o da yoxdursa təsdiqlənmiş
             nüsxə göstərilir (``offering_syllabus_state``).
``student``  sillabusun açılışına qeydiyyatlı tələbə. ⚠️ YALNIZ ``APPROVED``
             versiyanı görür və ``?version=`` parametri ONA TƏTBİQ OLUNMUR —
             əks halda qaralama URL ilə sızardı.

FAIL-CLOSED: hər iki qapıdan keçməyən istifadəçi 404 alır (403 deyil — başqa
kafedranın sillabusunun MÖVCUDLUĞU da sızdırılmır, bax
``apps.registrar.syllabus_views`` ilə eyni qayda).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.syllabus import services
from apps.syllabus.document import build_document
from apps.syllabus.models import Syllabus, SyllabusVersion

from .._helpers import _get_active_organization
from .detail_context import MODE_STAFF, MODE_STUDENT, build_detail_context
from .lookup import safe_uuid

TEMPLATE = "accounts/syllabus/detail.html"

_SYLLABUS_RELATED = (
    "organization",
    "subject",
    "period",
    "program",
    "chair_unit",
    "author",
    "offering",
    "current_version",
    "approved_version",
    "approved_version__approved_by",
)

_VERSION_RELATED = ("approved_by", "reviewer", "submitted_by")


def _syllabus_or_404(organization, syllabus_id):
    """Aktiv tenant-a bağlı dosye; yanlış UUID / özgə tenant → 404."""
    if organization is None:
        raise Http404
    parsed = safe_uuid(syllabus_id)
    if parsed is None:
        raise Http404
    syllabus = Syllabus.objects.filter(organization=organization, pk=parsed).select_related(*_SYLLABUS_RELATED).first()
    if syllabus is None:
        raise Http404
    return syllabus


def _staff_version(syllabus, version_id):
    """``?version=`` verilibsə HƏMİN dosyenin versiyası, yoxsa cari açıq nüsxə."""
    parsed = safe_uuid(version_id) if version_id else None
    if parsed is None:
        return services.offering_syllabus_state(syllabus)["version"]
    return (
        SyllabusVersion.objects.filter(
            organization=syllabus.organization,
            syllabus=syllabus,
            pk=parsed,
        )
        .select_related(*_VERSION_RELATED)
        .first()
    )


def _is_enrolled(request, syllabus) -> bool:
    """Tələbə bu sillabusun açılışına qeydiyyatlıdırmı."""
    if syllabus.offering_id is None:
        return False
    from apps.registrar.models import Enrollment

    return Enrollment.objects.filter(
        offering_id=syllabus.offering_id,
        student=request.user,
        organization=syllabus.organization,
    ).exists()


def resolve_access(request, syllabus_id, *, version_id=None):
    """``(organization, syllabus, version, mode)`` — icazəsizdə/məzmunsuzda 404."""
    organization = _get_active_organization(request)
    syllabus = _syllabus_or_404(organization, syllabus_id)
    actor = services.resolve_actor(request.user, organization, request=request)

    if services.can_view(actor, syllabus):
        mode = MODE_STAFF
        version = _staff_version(syllabus, version_id)
    elif _is_enrolled(request, syllabus):
        # ⚠️ `version_id` QƏSDƏN nəzərə alınmır: tələbə həmişə qüvvədə olan
        # təsdiqlənmiş nüsxəni görür, URL ilə qaralamaya keçə bilmir.
        mode = MODE_STUDENT
        version = services.approved_version_for(syllabus)
    else:
        raise Http404

    if version is None:
        raise Http404
    return organization, syllabus, version, mode


@login_required
@require_GET
def syllabus_detail(request, syllabus_id):
    """Sillabusun tam səhifəli, oxu-rejimli sənədi (yeni tabda açılır)."""
    organization, syllabus, version, mode = resolve_access(
        request, syllabus_id, version_id=(request.GET.get("version") or "").strip()
    )
    context = build_detail_context(
        organization=organization,
        syllabus=syllabus,
        version=version,
        mode=mode,
        is_student=(mode == MODE_STUDENT),
    )
    return render(request, TEMPLATE, context)


@login_required
@require_GET
def syllabus_detail_pdf(request, syllabus_id):
    """Eyni sənədin PDF nüsxəsi — MÖVCUD renderer (`registrar.syllabus_pdf`).

    Yeni PDF axını icad EDİLMİR: məzmun ``apps.syllabus.document.build_document``
    -dən, blank isə transkriptlə paylaşılan ``render_syllabus_pdf``-dən gəlir.
    Fərq yalnız GİRİŞ QAPISIDIR: jurnal endpoint-i açılışa (``offering``) bağlı
    idi, burada isə sillabusun öz əhatəsi yoxlanılır — kafedra müdiri başqasının
    jurnalını aça bilmədiyi halda da öz kafedrasının sənədini yükləyə bilir.
    """
    from apps.registrar.syllabus_pdf import render_syllabus_pdf

    organization, syllabus, version, _mode = resolve_access(
        request, syllabus_id, version_id=(request.GET.get("version") or "").strip()
    )
    document = build_document(syllabus, version)
    payload = render_syllabus_pdf(
        organization=organization,
        syllabus=syllabus,
        version=version,
        document=document,
    )
    response = HttpResponse(payload, content_type="application/pdf")
    filename = f"sillabus-{syllabus.subject.code}-{version.label}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


__all__ = [
    "MODE_STAFF",
    "MODE_STUDENT",
    "TEMPLATE",
    "resolve_access",
    "syllabus_detail",
    "syllabus_detail_pdf",
]
