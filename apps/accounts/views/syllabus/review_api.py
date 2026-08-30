"""Kafedra QƏRAR səthi — baxış panelini açan və qərarı yazan JSON endpoint-ləri.

Bu qat state maşınını TƏKRARLAMIR: `status = …` burada yazılmır, icazə məntiqi
kopyalanmır. Yalnız (1) HTTP girişi, (2) FAIL-CLOSED əhatə qapısı, (3) səbəbin
minimum uzunluğu, (4) domen xəta kodunun istifadəçi mətninə çevrilməsi.

⚠️ ƏHATƏ QAPISI: versiya ``services.review_scope_queryset`` ilə süzülmüş
dosyelərdən gəlir. Yəni kafedra müdiri BAŞQA kafedranın versiyasının id-sini
əlində tutsa belə nə baxa, nə də qərar verə bilir — servis qatındakı
``in_scope`` yoxlaması isə ikinci müstəqil qapıdır.

⚠️ SƏBƏB MƏCBURİDİR (README §4) və ÜÇ yerdə tətbiq olunur: burada (uzunluq),
``state_machine.check`` (boşluq) və DB ``CheckConstraint``-lərində.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_POST

from apps.syllabus import services
from apps.syllabus.constants import RULE_SECTIONS, SyllabusStatus
from apps.syllabus.models import SyllabusVersion
from apps.syllabus.state_machine import Transition, TransitionDenied

from .._helpers import _get_active_organization
from .labels import transition_text
from .lookup import safe_uuid
from .review_panel import build_review_payload
from .review_text import MIN_DECISION_REASON

_CTX = "accounts.syllabus"

#: Bir bölmə şərhinin maksimum uzunluğu — JSON sahəsi hədsiz şişməsin.
MAX_SECTION_COMMENT = 2000

_NO_ORG = pgettext_lazy(_CTX, "Aktiv təşkilat seçilməyib.")
_NOT_FOUND = pgettext_lazy(_CTX, "Sillabus versiyası tapılmadı və ya əhatənizdə deyil.")
_BAD_REQUEST = pgettext_lazy(_CTX, "Sorğu düzgün deyil.")
_REASON_SHORT = pgettext_lazy(_CTX, "Səbəb ən azı %(min)s simvol olmalıdır.")
_APPROVED = pgettext_lazy(_CTX, "%(name)s — %(version)s təsdiqləndi və kilidləndi.")
_REVISED = pgettext_lazy(_CTX, "%(name)s — düzəliş üçün geri qaytarıldı, müəllimə bildiriş göndərildi.")
_REJECTED = pgettext_lazy(_CTX, "%(name)s — versiya rədd edildi. Tələbələr köhnə təsdiqlənmiş versiyanı görür.")

#: Əməl açarı → (servis funksiyası, səbəb məcburidirmi, uğur mətni).
_DECISIONS = {
    "approve": (services.approve, False, _APPROVED),
    "revise": (services.request_revision, True, _REVISED),
    "reject": (services.reject, True, _REJECTED),
}


def _body(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return {}


def _fail(message, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": str(message)}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _context(request):
    organization = _get_active_organization(request)
    if organization is None:
        return None, None
    return organization, services.resolve_actor(request.user, organization, request=request)


def _scoped_version(organization, actor, version_id):
    """Versiya YALNIZ aktorun təsdiq əhatəsindən gəlir (fail-closed qapı)."""
    parsed = safe_uuid(version_id)
    if parsed is None:
        return None
    in_scope = services.review_scope_queryset(organization=organization, actor=actor)
    return (
        SyllabusVersion.objects.filter(organization=organization, pk=parsed, syllabus__in=in_scope)
        .select_related(
            "syllabus",
            "syllabus__subject",
            "syllabus__program",
            "syllabus__period",
            "syllabus__author",
            "syllabus__approved_version",
            "submitted_by",
        )
        .first()
    )


def _section_comments(payload) -> dict:
    """Bölmə şərhləri — yalnız TANINAN bölmə açarları, kəsilmiş uzunluqla."""
    raw = payload.get("sections")
    if not isinstance(raw, dict):
        return {}
    rows = {}
    for section_id, text in raw.items():
        if section_id not in RULE_SECTIONS or not isinstance(text, str):
            continue
        value = text.strip()[:MAX_SECTION_COMMENT]
        if value:
            rows[section_id] = value
    return rows


@login_required
@require_POST
def syllabus_review_open(request, version_id):
    """Baxış panelini açır: SUBMITTED → REVIEW keçidi + panelin məzmunu.

    Keçid mümkün deyilsə (versiya artıq ``REVIEW``-dədir) panel yenə açılır —
    baxış oxu əməliyyatıdır. İcazə/əhatə pozuntusu isə YUXARIDAKI qapıda
    dayandırılır, ona görə burada «səssiz keçir» riski yoxdur.
    """
    organization, actor = _context(request)
    if organization is None:
        return _fail(_NO_ORG, status=403)
    version = _scoped_version(organization, actor, version_id)
    if version is None:
        return _fail(_NOT_FOUND, status=404)

    if version.status == SyllabusStatus.SUBMITTED.value:
        try:
            version = services.start_review(version=version, actor=actor, request=request)
        except TransitionDenied as denied:
            if denied.code == "transition.permission_denied":
                return _fail(transition_text(denied.code, denied.params), status=403, code=denied.code)
            if denied.code == "transition.out_of_scope":
                return _fail(transition_text(denied.code, denied.params), status=403, code=denied.code)
        version = _scoped_version(organization, actor, version_id)
        if version is None:
            return _fail(_NOT_FOUND, status=404)

    return JsonResponse(
        {"ok": True, "transition": Transition.START_REVIEW, **build_review_payload(version, now=timezone.now())}
    )


@login_required
@require_POST
def syllabus_decision(request, version_id):
    """Təsdiq · düzəliş üçün geri qaytarma · rədd — üçü də bir endpoint-dən.

    Səbəb ``revise``/``reject`` üçün MƏCBURİDİR; boş və ya qısa səbəb 400 ilə
    dayandırılır və domen funksiyası ÇAĞIRILMIR.
    """
    organization, actor = _context(request)
    if organization is None:
        return _fail(_NO_ORG, status=403)
    version = _scoped_version(organization, actor, version_id)
    if version is None:
        return _fail(_NOT_FOUND, status=404)

    payload = _body(request)
    action = (payload.get("action") or "").strip()
    handler = _DECISIONS.get(action)
    if handler is None:
        return _fail(_BAD_REQUEST)
    service, reason_required, success = handler

    reason = (payload.get("reason") or "").strip()
    if reason_required and len(reason) < MIN_DECISION_REASON:
        return _fail(str(_REASON_SHORT) % {"min": MIN_DECISION_REASON}, code="transition.reason_required")

    kwargs = {
        "version": version,
        "actor": actor,
        "comment": (payload.get("comment") or "").strip(),
        "section_comments": _section_comments(payload),
        "request": request,
    }
    if reason_required:
        kwargs["reason"] = reason

    try:
        updated = service(**kwargs)
    except TransitionDenied as denied:
        return _fail(transition_text(denied.code, denied.params), status=409, code=denied.code)

    name = version.syllabus.subject.name
    return JsonResponse(
        {
            "ok": True,
            "message": str(success) % {"name": name, "version": updated.label},
            "version": str(updated.pk),
            "status": updated.status,
            "status_label": str(SyllabusStatus(updated.status).label),
        }
    )


__all__ = ["MAX_SECTION_COMMENT", "MIN_DECISION_REASON", "syllabus_decision", "syllabus_review_open"]
