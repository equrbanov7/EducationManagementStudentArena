"""25% / alt qrup müraciəti — HTTP səthi (JSON / multipart POST, CSRF ``EMSCore.fetchJSON`` ilə).

Prefiks ``/tekrar-imtahan/`` — QƏSDƏN ``/jurnal/`` altında DEYİL: şəbəkə zonası ``/jurnal/``-u kənar
zonadan hər kəsə bağlayır, tələbə isə müraciəti evdən də göndərə bilməlidir (apellyasiya ilə eyni qayda).

Qapılar: tələbə əməlləri yalnız ÖZ müraciətinə (yad id → 404); heyət əməllərində açar yoxdursa 403,
müraciət aktorun struktur əhatəsində deyilsə 404 (mövcudluq sızmasın). Bütün cavablar
``{"ok": bool, "message"|"error": str}``.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from core.tenancy import get_request_organization, request_has_active_organization_context

from . import retake_access, retake_decisions, retake_rules, retake_services
from .models import CourseOffering, RetakeApplication

_CTX = "registrar.retake"


def _block_view_as(view):
    """«Başqasının adından» (view-as) rejimində heç bir yazı yoxdur — 403 + ``view_as_blocked`` (EMSCore toast)."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "is_view_as", False):
            return JsonResponse(
                {
                    "ok": False,
                    "view_as_blocked": True,
                    "detail": pgettext(_CTX, "Başqasının adından baxış rejimində dəyişiklik etmək olmaz."),
                },
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapper


def _error(message, status=400, code=""):
    payload = {"ok": False, "error": str(message)}
    if code:
        payload["code"] = code
    return JsonResponse(payload, status=status)


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": str(message), **extra})


def _organization(request):
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        raise Http404
    return organization


def _data(request):
    if (request.content_type or "").startswith("application/json"):
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
    return request.POST


def _field(data, key) -> str:
    return str(data.get(key) or "").strip()


def _validation_message(exc) -> str:
    return "; ".join(str(m) for m in exc.messages)


def _run(callable_, *, success):
    try:
        callable_()
    except ObjectDoesNotExist:  # müraciət / pəncərə / təhsil haqqı sətri yoxdur və ya yaddır → 404 (LOW-8)
        raise Http404 from None
    except PermissionDenied:
        raise Http404 from None
    except ValidationError as exc:
        return _error(_validation_message(exc), code=getattr(exc, "code", "") or "")
    return _ok(success)


# ── Tələbə ───────────────────────────────────────────────────────────────────


@login_required
@require_POST
@_block_view_as
def apply(request):
    organization = _organization(request)
    data = _data(request)
    return _run(
        lambda: retake_services.apply(
            student=request.user,
            organization=organization,
            enrollment_id=_field(data, "enrollment"),
            kind=_field(data, "kind"),
            note=_field(data, "note"),
            receipt=request.FILES.get("receipt"),
            request=request,
        ),
        success=pgettext(_CTX, "Müraciətiniz göndərildi."),
    )


@login_required
@require_POST
@_block_view_as
def upload_receipt(request, application_id):
    organization = _organization(request)
    receipt = request.FILES.get("receipt")
    if receipt is None:
        return _error(pgettext(_CTX, "Qəbz faylını seçin (PDF, JPG və ya PNG)."))
    return _run(
        lambda: retake_services.upload_receipt(
            student=request.user,
            organization=organization,
            application_id=application_id,
            receipt=receipt,
            request=request,
        ),
        success=pgettext(_CTX, "Qəbz yükləndi — Mühasibatlıq yoxlayacaq."),
    )


@login_required
@require_POST
@_block_view_as
def withdraw(request, application_id):
    organization = _organization(request)
    data = _data(request)
    return _run(
        lambda: retake_services.withdraw(
            student=request.user,
            organization=organization,
            application_id=application_id,
            note=_field(data, "note"),
            request=request,
        ),
        success=pgettext(_CTX, "Müraciət geri götürüldü."),
    )


# ── Heyət ────────────────────────────────────────────────────────────────────


def _staff_application(request, application_id, keys):
    """Açar yoxdursa 403 (PermissionDenied), əhatədən kənar / yoxdursa 404."""
    organization = _organization(request)
    if not any(retake_access.has_key(request.user, organization, key) for key in keys):
        raise PermissionDenied
    application = RetakeApplication.objects.filter(pk=application_id, organization=organization).first()
    if application is None or not retake_access.application_in_scope(request.user, application, keys):
        raise Http404
    return organization, application


@login_required
@require_POST
@_block_view_as
def payment(request, application_id):
    organization, application = _staff_application(request, application_id, (retake_rules.PERM_PAYMENT_VERIFY,))
    data = _data(request)
    action = _field(data, "action")
    if action == "verify":
        return _run(
            lambda: retake_decisions.verify_payment(
                actor=request.user,
                organization=organization,
                application_id=application.pk,
                paid_amount=_field(data, "paid_amount"),
                payment_reference=_field(data, "payment_reference"),
                note=_field(data, "note"),
                request=request,
            ),
            success=pgettext(_CTX, "Ödəniş təsdiqləndi."),
        )
    if action == "reject":
        return _run(
            lambda: retake_decisions.reject_payment(
                actor=request.user,
                organization=organization,
                application_id=application.pk,
                reason=_field(data, "reason"),
                request=request,
            ),
            success=pgettext(_CTX, "Qəbz rədd edildi — tələbəyə bildiriş göndərildi."),
        )
    return _error(pgettext(_CTX, "Naməlum əməl."))


@login_required
@require_POST
@_block_view_as
def decision(request, application_id):
    organization, application = _staff_application(request, application_id, (retake_rules.PERM_MANAGE,))
    data = _data(request)
    action = _field(data, "action")
    common = {"actor": request.user, "organization": organization, "application_id": application.pk}
    if action == "admit":
        return _run(
            lambda: retake_decisions.admit(note=_field(data, "note"), request=request, **common),
            success=pgettext(_CTX, "Tələbə 25% imtahana buraxıldı."),
        )
    decision = {
        "order_number": _field(data, "order_number"),
        "order_date": _field(data, "order_date") or None,
        "document": request.FILES.get("document"),
    }
    if action == "reject":
        return _run(
            lambda: retake_decisions.reject(reason=_field(data, "reason"), request=request, **decision, **common),
            success=pgettext(_CTX, "Müraciət rədd edildi."),
        )
    if action in ("no_show", "withdraw"):
        from . import retake_closure

        return _run(
            lambda: retake_closure.close(
                action=action, reason=_field(data, "reason"), request=request, **decision, **common
            ),
            success=(
                pgettext(_CTX, "«İmtahana gəlmədi» qərarı yazıldı — cəhd istifadə olunmuş sayılır.")
                if action == "no_show"
                else pgettext(_CTX, "Müraciət qərarla geri götürüldü.")
            ),
        )
    if action == "approve_subgroup":
        document = request.FILES.get("document")
        if document is None:
            return _error(pgettext(_CTX, "Sənəd (təqdimat / sərəncam) yüklənməlidir — alt qrup sənədsiz olmur."))
        return _run(
            lambda: retake_decisions.approve_subgroup(
                document=document,
                reason=_field(data, "reason"),
                offering_id=_field(data, "offering") or None,
                request=request,
                **common,
            ),
            success=pgettext(_CTX, "Alt qrup qərarı yazıldı."),
        )
    if action == "place":
        document = request.FILES.get("document")
        if document is None:
            return _error(pgettext(_CTX, "Sənəd (təqdimat / sərəncam) yüklənməlidir — alt qrup sənədsiz olmur."))
        return _run(
            lambda: retake_decisions.place_subgroup(
                document=document,
                reason=_field(data, "reason"),
                offering_id=_field(data, "offering"),
                request=request,
                **common,
            ),
            success=pgettext(_CTX, "Tələbə alt qrupa yerləşdirildi."),
        )
    return _error(pgettext(_CTX, "Naməlum əməl."))


def _restores_attempt(data) -> bool:
    """Dialoq: gizli ``0`` + işarələnmiş checkbox ``1`` (son dəyər qalır). Sahə yoxdursa — defolt ``True`` (sahib qaydası)."""
    raw = str(data.get("restores_attempt") or "").strip().lower()
    return True if not raw else raw in ("1", "true", "on", "yes")


@login_required
@require_POST
@_block_view_as
def refund(request, application_id):
    """2026-10-19: «Ödənişin qaytarılması qərarı» (``action=decide``) və Mühasibatlığın «Qaytarıldı» (``action=mark``).

    Qərar — ``retake.manage`` TƏŞKİLAT əhatəsində: açarı olmayan da, açarı yalnız fakültə əhatəsində olan dekan da 403
    alır (səlahiyyət yoxdur — mövcudluq yox); icra — ``retake.payment_verify``. Yad / mövcud olmayan müraciət 404."""
    from . import retake_refund

    data = _data(request)
    action = _field(data, "action")
    if action == "decide":
        organization, application = _staff_application(request, application_id, (retake_rules.PERM_MANAGE,))
        if not retake_refund.can_decide(request.user, organization):
            raise PermissionDenied
        return _run(
            lambda: retake_refund.decide(
                actor=request.user,
                organization=organization,
                application_id=application.pk,
                reason=_field(data, "reason"),
                amount=_field(data, "amount"),
                order_number=_field(data, "order_number"),
                order_date=_field(data, "order_date") or None,
                document=request.FILES.get("document"),
                restores_attempt=_restores_attempt(data),
                request=request,
            ),
            success=pgettext(_CTX, "Qaytarılma qərarı yazıldı — Mühasibatlığa bildiriş göndərildi."),
        )
    if action == "mark":
        organization, application = _staff_application(request, application_id, (retake_rules.PERM_PAYMENT_VERIFY,))
        return _run(
            lambda: retake_refund.mark_refunded(
                actor=request.user,
                organization=organization,
                application_id=application.pk,
                refunded_on=_field(data, "refunded_on"),
                reference=_field(data, "reference"),
                note=_field(data, "note"),
                request=request,
            ),
            success=pgettext(_CTX, "Ödəniş qaytarılmış kimi qeyd olundu."),
        )
    return _error(pgettext(_CTX, "Naməlum əməl."))


@login_required
@require_POST
@_block_view_as
def result(request, application_id):
    keys = (retake_rules.PERM_MANAGE, retake_rules.PERM_SCORE_ENTRY)
    organization, application = _staff_application(request, application_id, keys)
    data = _data(request)
    return _run(
        lambda: retake_decisions.record_result(
            actor=request.user,
            organization=organization,
            application_id=application.pk,
            score=_field(data, "score"),
            note=_field(data, "note"),
            request=request,
        ),
        success=pgettext(_CTX, "25% imtahanın nəticəsi yazıldı."),
    )


@login_required
@require_GET
def subgroup_offerings(request, application_id):
    """Alt qrup üçün hədəf jurnallar — eyni fənn, CARİ dövr, tələbənin öz qrupundan başqa (EMSSearchableSelect)."""
    organization, application = _staff_application(request, application_id, (retake_rules.PERM_MANAGE,))
    query = (request.GET.get("q") or "").strip()
    rows = (
        CourseOffering.objects.filter(
            organization=organization,
            subject_id=application.subject_id,
            is_active=True,
            period__is_current=True,
        )
        .exclude(group_id=application.student_group_id)
        .select_related("group", "period", "instructor")
        .order_by("group__name")
    )
    if query:
        rows = rows.filter(group__name__icontains=query)
    results = []
    for offering in rows[:50]:
        teacher = getattr(offering, "instructor", None)
        teacher_name = ((teacher.get_full_name() or "").strip() or teacher.username) if teacher else ""
        label = " · ".join(
            part
            for part in (getattr(offering.group, "name", ""), getattr(offering.period, "name", ""), teacher_name)
            if part
        )
        results.append({"id": str(offering.pk), "text": label})
    return JsonResponse({"results": results, "has_more": False})


@login_required
@require_GET
def trail(request, student_id):
    """Tələbənin 25% izi (HTML fraqment) — YALNIZ ``retake.manage`` / ``student.records_view``.

    Mühasib (yalnız ``retake.payment_verify``) → 403: ballar və cəhd tarixçəsi ödəniş yoxlamasına aid deyil
    (sahibin qaydası, 2026-10-18). Əhatədən kənar / mövcud olmayan tələbə → 404."""
    from django.contrib.auth import get_user_model
    from django.shortcuts import render

    from . import retake_queries

    organization = _organization(request)
    if not retake_access.can_view_trail(request.user, organization):
        raise PermissionDenied
    student = get_user_model().objects.filter(pk=student_id).first()
    if student is None or not retake_access.student_in_scope(
        request.user, organization, student.pk, retake_access.TRAIL_KEYS
    ):
        raise Http404
    keys = retake_access.desk_keys(request.user, organization)
    context = {
        "trail": retake_queries.student_trail(student=student, organization=organization),
        "rd": {"tab": "all", "keys": keys},
        "profile_base_url": reverse("accounts:profile"),
    }
    return render(request, "registrar/retake/_trail.html", context)


__all__ = [
    "apply",
    "decision",
    "payment",
    "refund",
    "result",
    "subgroup_offerings",
    "trail",
    "upload_receipt",
    "withdraw",
]
