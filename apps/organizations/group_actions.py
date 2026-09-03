"""Ekran 06 «Qruplar» ƏMƏLLƏRİ — tək JSON POST endpoint-i.

Əməllər: qrup yarat/redaktə et · ARXİVLƏ (səbəb ≥20) · arxivdən qaytar ·
**toplu «kursa keçir»** (promote).

──────────────────────────────────────────────────────────────────────────────
SİLMƏ YOXDUR (handoff §8 qayda 5)
──────────────────────────────────────────────────────────────────────────────
Qrup ``OrgUnit``-dur: arxivləmə ``is_active=False``-dur. Tələbənin qeydiyyatı,
jurnal və qiymət tarixçəsi TOXUNULMUR. Tələbəsi olan qrup arxivlənmir — əvvəlcə
tələbələr köçürülməlidir (Mərhələ 3 «Tələbə hərəkəti» ekranı).

──────────────────────────────────────────────────────────────────────────────
«KURSA KEÇİR» — TOPLU, AMMA AUDİTLİ
──────────────────────────────────────────────────────────────────────────────
Kurs nömrəsi ``OrgUnit.settings["course_year"]``-dədir; promote onu +1 edir.
Hər qrup üçün AYRICA audit yazısı düşür (köhnə → yeni kurs), yəni toplu əməl
sonradan sətir-sətir izlənə bilir. Məzun kursu (>` MAX_COURSE_YEAR`) keçmir —
məzunluq ayrı əməldir (tələbə hərəkəti), qrup nömrəsi ilə həll olunmur.

QAPI ÜÇ QAT: tenant + ``unit.group_manage`` açarı + görünən (scope daxilində)
hədəf — əhatədən kənar id 404 alır (IDOR).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from .groups_registry import can_manage_groups, can_view_groups, group_meta, group_scope
from .models import Organization, OrgUnit
from .scoping import scope_org_units
from .views.shared._helpers import _unique_unit_slug

_CTX = "accounts.groups"

#: Səbəb tələb edən əməllərin minimum uzunluğu (handoff §8 qayda 6).
REASON_MIN_LENGTH = 20

#: Kurs nömrəsinin yuxarı həddi — bundan sonrası MƏZUNLUQDUR (ayrı əməl).
MAX_COURSE_YEAR = 6

#: Toplu əməlin bir sorğuda emal etdiyi maksimum qrup (UI-da seçim onsuz da
#: səhifə ilə məhduddur; server tərəfdə də bağlanır).
MAX_BULK = 200


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _reason_or_none(request):
    reason = (request.POST.get("reason") or "").strip()
    if len(reason) < REASON_MIN_LENGTH:
        return None, _error(
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
            code="reason_too_short",
            field="reason",
        )
    return reason, None


def _visible_group(organization, scope, unit_id, *, include_archived=False):
    queryset = OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP)
    if not include_archived:
        queryset = queryset.filter(is_active=True)
    return scope_org_units(queryset, scope).filter(pk=(unit_id or "").strip()).select_related("parent", "head").first()


def _int_or(value, default, *, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _apply_meta(unit, request):
    """`settings` JSON-u yerində yeniləyir — MÖVCUD açarlar silinmir."""
    settings_blob = dict(unit.settings) if isinstance(unit.settings, dict) else {}
    settings_blob["language_sector"] = (request.POST.get("language_sector") or "").strip()[:16]
    settings_blob["course_year"] = _int_or(request.POST.get("course_year"), 1, low=1, high=MAX_COURSE_YEAR)
    settings_blob["admission_year"] = _int_or(request.POST.get("admission_year"), 0, low=0, high=2100)
    settings_blob["capacity"] = _int_or(request.POST.get("capacity"), 0, low=0, high=500)
    curriculum_id = (request.POST.get("curriculum_id") or "").strip()
    if curriculum_id:
        Curriculum = django_apps.get_model("registrar", "Curriculum")
        exists = Curriculum.objects.filter(organization=unit.organization, pk=curriculum_id).exists()
        settings_blob["curriculum_id"] = curriculum_id if exists else ""
    else:
        settings_blob["curriculum_id"] = ""
    unit.settings = settings_blob


def _save_group(request, organization, scope):
    unit_id = (request.POST.get("id") or "").strip()
    instance = None
    if unit_id:
        instance = _visible_group(organization, scope, unit_id, include_archived=True)
        if instance is None:
            return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")

    name = (request.POST.get("name") or "").strip()[:255]
    if not name:
        return _error(pgettext(_CTX, "Qrupun adı boş ola bilməz."), code="name_required", field="name")

    specialty = None
    specialty_id = (request.POST.get("specialty") or "").strip()
    if specialty_id:
        specialty = (
            scope_org_units(
                OrgUnit.objects.filter(
                    organization=organization,
                    is_active=True,
                    unit_type__in=(OrgUnitType.SPECIALTY, OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
                ),
                scope,
            )
            .filter(pk=specialty_id)
            .first()
        )
        if specialty is None:
            return _error(pgettext(_CTX, "İxtisas bölməsi tapılmadı."), status=404, code="not_found", field="specialty")
    if instance is None and specialty is None:
        return _error(
            pgettext(_CTX, "Yeni qrup üçün ixtisas seçilməlidir."), code="specialty_required", field="specialty"
        )

    is_create = instance is None
    if is_create:
        instance = OrgUnit(
            organization=organization,
            unit_type=OrgUnitType.GROUP,
            slug=_unique_unit_slug(organization, name, "group"),
        )
    old_values = (
        {} if is_create else {"name": instance.name, "code": instance.code, "settings": dict(instance.settings or {})}
    )

    instance.name = name
    instance.code = (request.POST.get("code") or "").strip()[:50]
    if specialty is not None:
        instance.parent = specialty
    _apply_meta(instance, request)

    tutor_id = (request.POST.get("tutor") or "").strip()
    if tutor_id:
        Membership = django_apps.get_model("organizations", "Membership")
        membership = (
            Membership.objects.filter(organization=organization, is_active=True, user_id=tutor_id)
            .select_related("user")
            .first()
        )
        if membership is None:
            return _error(
                pgettext(_CTX, "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil."), code="bad_tutor", field="tutor"
            )
        instance.head = membership.user
    elif "tutor" in request.POST:
        instance.head = None

    instance.save()
    log_action(
        action=AuditAction.CREATE if is_create else AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=instance,
        request=request,
        reason="groups: group created" if is_create else "groups: group updated",
        old_values=old_values or None,
        new_values={"name": instance.name, "code": instance.code, "settings": dict(instance.settings or {})},
    )
    return JsonResponse({"ok": True, "id": str(instance.id), "created": is_create})


def _archive(request, organization, scope, *, restore: bool):
    unit = _visible_group(organization, scope, request.POST.get("id"), include_archived=True)
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    if not restore:
        StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
        if StudentAcademicRecord.objects.filter(organization=organization, group=unit, is_active=True).exists():
            return _error(
                pgettext(_CTX, "Tələbəsi olan qrup arxivlənmir — əvvəlcə tələbələri köçürün."),
                code="has_students",
            )

    unit.is_active = restore
    unit.save(update_fields=["is_active", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=unit,
        request=request,
        reason=("groups: restored from archive — " if restore else "groups: archived — ") + reason,
        old_values={"is_active": not restore},
        new_values={"is_active": restore, "reason": reason},
    )
    return JsonResponse({"ok": True, "id": str(unit.id), "is_active": unit.is_active})


@transaction.atomic
def _promote(request, organization, scope):
    """Toplu «kursa keçir» — hər qrup üçün AYRICA audit yazısı."""
    ids = [value for value in request.POST.getlist("ids") if value][:MAX_BULK]
    if not ids:
        return _error(pgettext(_CTX, "Qrup seçilməyib."), code="ids_required")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    units = list(
        scope_org_units(
            OrgUnit.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.GROUP), scope
        ).filter(pk__in=ids)
    )
    promoted, graduated = 0, 0
    for unit in units:
        meta = group_meta(unit)
        current = meta["course_year"] or 1
        if current >= MAX_COURSE_YEAR:
            # Məzunluq qrup nömrəsi ilə həll olunmur — sətir toxunulmaz qalır.
            graduated += 1
            continue
        settings_blob = dict(unit.settings) if isinstance(unit.settings, dict) else {}
        settings_blob["course_year"] = current + 1
        unit.settings = settings_blob
        unit.save(update_fields=["settings", "updated_at"])
        promoted += 1
        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=organization,
            obj=unit,
            request=request,
            reason=f"groups: promoted to next course year — {reason}",
            old_values={"course_year": current},
            new_values={"course_year": current + 1, "reason": reason},
        )
    return JsonResponse({"ok": True, "promoted": promoted, "graduated": graduated, "requested": len(ids)})


_HANDLERS = {
    "save_group": lambda request, organization, scope: _save_group(request, organization, scope),
    "archive": lambda request, organization, scope: _archive(request, organization, scope, restore=False),
    "restore": lambda request, organization, scope: _archive(request, organization, scope, restore=True),
    "promote": lambda request, organization, scope: _promote(request, organization, scope),
}


@login_required
@require_POST
def group_action(request, slug):
    """Akademik qrup əməlləri — tək JSON endpoint (`unit.group_manage` qapısı)."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not can_view_groups(request):
        return _error(pgettext(_CTX, "Qrup reyestrinə səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    scope = group_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")
    if not can_manage_groups(request):
        return _error(pgettext(_CTX, "Qrupları idarə etmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    return handler(request, organization, scope)


__all__ = ["MAX_COURSE_YEAR", "REASON_MIN_LENGTH", "group_action"]
