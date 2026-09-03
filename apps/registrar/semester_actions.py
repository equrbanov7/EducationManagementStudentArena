"""Ekran 07 «Semestr açılışı» ƏMƏLLƏRİ — tək JSON POST endpoint-i.

Əməllər: dövr yarat/redaktə et · «cari dövr» açarı (təsdiq + audit) · plandan
açılış YARAT · kafedraya göndər · açılışı ləğv et · semestri kilidlə · kilidi aç.

──────────────────────────────────────────────────────────────────────────────
İKİ QAYDA, HƏR İKİSİ AUDİTLİ
──────────────────────────────────────────────────────────────────────────────
* **«Cari dövr» İNSAN QƏRARIDIR.** ``AcademicPeriod.save()`` yeni cari dövrü
  təyin edəndə köhnəsini AVTOMATİK söndürür — yəni bu açar bütün universitetin
  jurnal/açılış konteksini bir kliklə dəyişir. Ona görə əməl ayrıca təsdiq
  dialoqundan keçir və ``core.audit``-a köhnə/yeni dövrlə yazılır.
* **Kilid geri qaytarılmır.** ``semester.lock`` kilidləyir; açmaq üçün AYRICA
  ``semester.unlock`` açarı + ≥20 simvol səbəb lazımdır (handoff §8 qayda 6).
  Kilid düyməsi şərtlər ödənməyəndə GİZLƏNMİR — `disabled` olur (§4).

**Açılış SİLİNMİR** — ləğv ``is_active=False``-dur: jurnal, qeydiyyat və qiymət
tarixçəsi olduğu kimi qalır (§8 qayda 5).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.audit import log_action
from core.constants import AuditAction

from .models import CourseOffering, Program
from .models.curriculum_meta import PLAN_REASON_MIN_LENGTH
from .semester_open import (
    can_lock_semester,
    can_open_semester,
    can_unlock_semester,
    can_view_semester,
    coverage,
    generate_offerings,
)

_CTX = "accounts.semester"


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _reason_or_none(request):
    reason = (request.POST.get("reason") or "").strip()
    if len(reason) < PLAN_REASON_MIN_LENGTH:
        return None, _error(
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
            code="reason_too_short",
            field="reason",
        )
    return reason, None


def _period(organization, period_id):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return AcademicPeriod.objects.filter(organization=organization, pk=(period_id or "").strip()).first()


def _save_period(request, organization):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    instance = None
    period_id = (request.POST.get("id") or "").strip()
    if period_id:
        instance = _period(organization, period_id)
        if instance is None:
            return _error(pgettext(_CTX, "Dövr tapılmadı."), status=404, code="not_found")

    name = (request.POST.get("name") or "").strip()[:100]
    year = (request.POST.get("academic_year") or "").strip()[:20]
    start = (request.POST.get("start_date") or "").strip()
    end = (request.POST.get("end_date") or "").strip()
    if not name:
        return _error(pgettext(_CTX, "Dövrün adı boş ola bilməz."), code="name_required", field="name")
    if not year:
        return _error(pgettext(_CTX, "Tədris ili boş ola bilməz."), code="year_required", field="academic_year")
    if not (start and end):
        return _error(
            pgettext(_CTX, "Başlama və bitmə tarixi tələb olunur."), code="dates_required", field="start_date"
        )
    if start >= end:
        return _error(
            pgettext(_CTX, "Başlama tarixi bitmə tarixindən əvvəl olmalıdır."), code="bad_dates", field="end_date"
        )

    is_create = instance is None
    if is_create:
        instance = AcademicPeriod(organization=organization, period_type="semester")
    elif instance.locked_at is not None:
        return _error(
            pgettext(_CTX, "Kilidlənmiş semestr redaktə olunmur — əvvəlcə kilidi açın."), status=409, code="locked"
        )

    old_values = {} if is_create else {"name": instance.name, "academic_year": instance.academic_year}
    instance.name = name
    instance.academic_year = year
    instance.start_date = start
    instance.end_date = end
    try:
        instance.save()
    except IntegrityError:
        return _error(pgettext(_CTX, "Bu ad və tədris ili ilə dövr artıq mövcuddur."), code="duplicate", field="name")

    log_action(
        action=AuditAction.CREATE if is_create else AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=instance,
        request=request,
        reason="semester: period saved",
        old_values=old_values or None,
        new_values={"name": name, "academic_year": year, "start": start, "end": end},
    )
    return JsonResponse({"ok": True, "id": str(instance.id), "created": is_create})


def _set_current(request, organization):
    """«Cari dövr» açarı — bütün universitetin konteksini dəyişir, ona görə auditlidir."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    period = _period(organization, request.POST.get("id"))
    if period is None:
        return _error(pgettext(_CTX, "Dövr tapılmadı."), status=404, code="not_found")

    previous = AcademicPeriod.objects.filter(organization=organization, is_current=True).exclude(pk=period.pk).first()
    period.is_current = True
    period.save()  # `save()` köhnə cari dövrü avtomatik söndürür.

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=period,
        request=request,
        reason="semester: current period switched",
        old_values={"previous_current": str(previous) if previous else ""},
        new_values={"is_current": True, "period": str(period)},
    )
    return JsonResponse({"ok": True, "id": str(period.id)})


def _generate(request, organization):
    if not can_open_semester(request):
        return _error(pgettext(_CTX, "Semestr açmaq üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    period = _period(organization, request.POST.get("period"))
    if period is None:
        return _error(pgettext(_CTX, "Dövr tapılmadı."), status=404, code="not_found")
    if period.locked_at is not None:
        return _error(pgettext(_CTX, "Semestr kilidlidir — açılış yaradıla bilməz."), status=409, code="locked")

    try:
        semester_number = int((request.POST.get("semester_number") or "").strip())
    except (TypeError, ValueError):
        return _error(pgettext(_CTX, "Semestr nömrəsi seçilməyib."), code="bad_semester", field="semester_number")
    if not 1 <= semester_number <= 16:
        return _error(
            pgettext(_CTX, "Semestr 1–16 aralığında olmalıdır."), code="bad_semester", field="semester_number"
        )

    program_ids = [value for value in request.POST.getlist("programs") if value]
    programs = Program.objects.filter(organization=organization, is_archived=False)
    if program_ids:
        programs = programs.filter(pk__in=program_ids)
    programs = list(programs.select_related("specialty_unit"))
    if not programs:
        return _error(pgettext(_CTX, "İxtisas seçilməyib."), code="programs_required", field="programs")

    result = generate_offerings(
        organization=organization,
        period=period,
        programs=programs,
        semester_number=semester_number,
        actor=request.user,
    )
    if period.opening_status == "not_started" and result["created"]:
        period.opening_status = "generated"
        period.save(update_fields=["opening_status", "updated_at"])

    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=organization,
        obj=period,
        request=request,
        reason="semester: offerings generated from approved plans",
        new_values={
            "semester_number": semester_number,
            "created": result["created"],
            "existing": result["existing"],
            "blocked": [item["label"] for item in result["blocked_programs"]],
        },
    )
    return JsonResponse({"ok": True, **{key: result[key] for key in result if key != "offering_ids"}})


def _send_to_chairs(request, organization):
    if not can_open_semester(request):
        return _error(pgettext(_CTX, "Bu əməl üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    period = _period(organization, request.POST.get("period"))
    if period is None:
        return _error(pgettext(_CTX, "Dövr tapılmadı."), status=404, code="not_found")
    if period.locked_at is not None:
        return _error(pgettext(_CTX, "Semestr kilidlidir."), status=409, code="locked")

    period.opening_status = "sent"
    period.save(update_fields=["opening_status", "updated_at"])
    _notify_chairs(organization, period, actor=request.user)
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=period,
        request=request,
        reason="semester: offerings sent to chairs for instructor assignment",
        new_values={"opening_status": "sent"},
    )
    return JsonResponse({"ok": True, "opening_status": "sent"})


def _cancel_offering(request, organization):
    """Açılışı LƏĞV edir — sətir qalır, `is_active=False` (silmə yoxdur)."""
    if not can_open_semester(request):
        return _error(pgettext(_CTX, "Bu əməl üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    offering = CourseOffering.objects.filter(
        organization=organization, pk=(request.POST.get("id") or "").strip()
    ).first()
    if offering is None:
        return _error(pgettext(_CTX, "Açılış tapılmadı."), status=404, code="not_found")
    if offering.period.locked_at is not None:
        return _error(pgettext(_CTX, "Kilidlənmiş semestrdə açılış dəyişmir."), status=409, code="locked")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    offering.is_active = False
    offering.save(update_fields=["is_active", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=offering,
        request=request,
        reason=f"semester: offering cancelled — {reason}",
        old_values={"is_active": True},
        new_values={"is_active": False, "reason": reason},
    )
    return JsonResponse({"ok": True, "id": str(offering.id)})


def _lock(request, organization):
    if not can_lock_semester(request):
        return _error(pgettext(_CTX, "Semestri kilidləmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    period = _period(organization, request.POST.get("period"))
    if period is None:
        return _error(pgettext(_CTX, "Dövr tapılmadı."), status=404, code="not_found")
    if period.locked_at is not None:
        return _error(pgettext(_CTX, "Semestr artıq kilidlidir."), status=409, code="already_locked")

    stats = coverage(organization, period)
    if stats["total"] == 0:
        return _error(pgettext(_CTX, "Semestrdə açılış yoxdur — kilidləmək mümkün deyil."), code="no_offerings")
    if stats["without_instructor"]:
        return _error(
            pgettext(_CTX, "Müəllimi olmayan açılış var — semestr kilidlənmir."),
            status=409,
            code="missing_instructors",
        )

    period.locked_at = timezone.now()
    period.locked_by = request.user
    period.lock_reason = (request.POST.get("reason") or "").strip()
    period.opening_status = "locked"
    period.save(update_fields=["locked_at", "locked_by", "lock_reason", "opening_status", "updated_at"])

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=period,
        request=request,
        reason="semester: locked",
        new_values={"locked_at": period.locked_at.isoformat(), "offerings": stats["total"]},
    )
    return JsonResponse({"ok": True, "locked": True})


def _unlock(request, organization):
    if not can_unlock_semester(request):
        return _error(pgettext(_CTX, "Kilidi açmaq səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    period = _period(organization, request.POST.get("period"))
    if period is None:
        return _error(pgettext(_CTX, "Dövr tapılmadı."), status=404, code="not_found")
    if period.locked_at is None:
        return _error(pgettext(_CTX, "Semestr kilidli deyil."), status=409, code="not_locked")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    previous_lock = period.locked_at.isoformat()
    period.locked_at = None
    period.locked_by = None
    period.lock_reason = reason
    period.opening_status = "sent"
    period.save(update_fields=["locked_at", "locked_by", "lock_reason", "opening_status", "updated_at"])

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=period,
        request=request,
        reason=f"semester: unlocked — {reason}",
        old_values={"locked_at": previous_lock},
        new_values={"locked_at": "", "reason": reason},
    )
    return JsonResponse({"ok": True, "locked": False})


def _notify_chairs(organization, period, *, actor=None) -> None:
    """Kafedra rəhbərlərinə «müəllim təyinatı gözlənilir» bildirişi."""
    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.public import create_notification
    except Exception:  # pragma: no cover
        return

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    heads = (
        OrgUnit.objects.filter(
            organization=organization, is_active=True, unit_type__in=("chair", "department"), head__isnull=False
        )
        .select_related("head")
        .exclude(head_id=getattr(actor, "id", None))
    )
    for unit in heads:
        try:
            create_notification(
                recipient=unit.head,
                title=f"Semestr açılışı: {period.year_display} · {period.name}"[:255],
                message="Kafedranızın açılışlarına müəllim təyin edilməlidir.",
                link="/accounts/profile/?section=semester-opening&sm_period=%s" % period.id,
                notification_type=NotificationType.SYSTEM,
                organization=organization,
                metadata={"event": "semester_opening_sent", "period_id": str(period.id)},
            )
        except Exception:  # pragma: no cover
            continue


_HANDLERS = {
    "save_period": _save_period,
    "set_current": _set_current,
    "generate": _generate,
    "send_to_chairs": _send_to_chairs,
    "cancel_offering": _cancel_offering,
    "lock": _lock,
    "unlock": _unlock,
}


@login_required
@require_POST
def semester_action(request):
    """Semestr açılışı əməlləri — tək JSON endpoint (`semester.*` qapısı)."""
    organization = getattr(request, "organization", None)
    if organization is None:
        return _error(pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=403, code="no_org")
    if not can_view_semester(request):
        return _error(pgettext(_CTX, "Semestr açılışına səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    # `save_period` və `set_current` də AÇILIŞ səlahiyyəti tələb edir: təqvim
    # dövrünü dəyişmək semestrin özünü açmaqla eyni ağırlıqdadır.
    if handler in (_save_period, _set_current) and not can_open_semester(request):
        return _error(pgettext(_CTX, "Bu əməl üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    return handler(request, organization)


__all__ = ["semester_action"]
