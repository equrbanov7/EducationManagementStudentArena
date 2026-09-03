"""Akademik kataloq ƏMƏLLƏRİ — ekran 03/04 (JSON POST).

Beş əməl: ixtisas yarat/redaktə et, fənn yarat/redaktə et, ARXİVLƏ (hər ikisi),
arxivdən qaytar. **Silmə yoxdur** (handoff §8 qayda 5): arxivlənmiş ixtisas və
fənn reyestrdən süzülür, əlaqəli plan sətri, jurnal və qiymət tarixçəsi qalır.

SƏBƏB MƏCBURİDİR (qayda 6): arxivləmə və arxivdən qaytarma üçün ≥20 simvol;
səbəb həm sətirdə (``archived_reason``), həm də ``core.audit.log_action``-da
aktor + timestamp ilə saxlanılır.

İCAZƏ: ``catalog.manage``. Oxu açarı (``catalog.view``) YAZMAĞA yetmir.
Tenant qapısı: hər sorğu ``request.organization`` ilə filtrlənir — başqa
tenantın id-si 404 alır (IDOR).

MODUL SƏRHƏDİ: ``apps.organizations`` STATİK import edilmir.
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

from .catalog_registry import can_manage_catalog
from .models import Program, Subject
from .models.academic import DegreeLevel
from .models.catalog_meta import ARCHIVE_REASON_MIN_LENGTH, EducationForm, SubjectKind

_CTX = "accounts.catalog"


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _reason_or_none(request):
    reason = (request.POST.get("reason") or "").strip()
    if len(reason) < ARCHIVE_REASON_MIN_LENGTH:
        return None, _error(
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
            code="reason_too_short",
            field="reason",
        )
    return reason, None


def _chair_unit(organization, unit_id):
    """Kafedra vahidini tenant daxilində həll edir (string-ref, statik import yox)."""
    if not unit_id:
        return None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return OrgUnit.objects.filter(
        organization=organization, is_active=True, pk=unit_id, unit_type__in=("chair", "department", "specialty")
    ).first()


def _int_or(value, default, *, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


# --------------------------------------------------------------------------- #
# İxtisas (Program)
# --------------------------------------------------------------------------- #


def _save_program(request, organization):
    program_id = (request.POST.get("id") or "").strip()
    instance = None
    if program_id:
        instance = Program.objects.filter(organization=organization, pk=program_id).first()
        if instance is None:
            return _error(pgettext(_CTX, "İxtisas tapılmadı."), status=404, code="not_found")

    name = (request.POST.get("name") or "").strip()[:255]
    if not name:
        return _error(pgettext(_CTX, "İxtisasın adı boş ola bilməz."), code="name_required", field="name")

    degree = (request.POST.get("degree_level") or "").strip()
    if degree not in dict(DegreeLevel.choices):
        return _error(pgettext(_CTX, "Təhsil pilləsi seçilməyib."), code="bad_degree", field="degree_level")

    form = (request.POST.get("education_form") or "").strip()
    if form not in dict(EducationForm.choices):
        return _error(pgettext(_CTX, "Təhsil forması seçilməyib."), code="bad_form", field="education_form")

    specialty_unit = _chair_unit(organization, (request.POST.get("specialty_unit") or "").strip())

    is_create = instance is None
    if is_create:
        # `code` DAXİLİ sabit identifikatordur (istifadəçiyə göstərilmir) —
        # rəsmi şifrdən AYRIDIR. Boş qala bilmədiyi üçün ad-slug-undan törədilir.
        base = (request.POST.get("official_code") or name)[:20].strip().upper().replace(" ", "-")
        candidate = base or "PROG"
        suffix = 2
        while Program.objects.filter(organization=organization, code=candidate).exists():
            candidate = f"{base or 'PROG'}-{suffix}"
            suffix += 1
        instance = Program(organization=organization, code=candidate)

    old_values = (
        {}
        if is_create
        else {
            "name": instance.name,
            "degree_level": instance.degree_level,
            "education_form": instance.education_form,
            "official_code": instance.official_code,
        }
    )

    instance.name = name
    instance.degree_level = degree
    instance.education_form = form
    instance.official_code = (request.POST.get("official_code") or "").strip()[:16]
    instance.specialty_unit = specialty_unit
    instance.ects_total = _int_or(request.POST.get("ects_total"), instance.ects_total or 240, low=30, high=600)
    instance.absence_limit_percent = _int_or(
        request.POST.get("absence_limit_percent"), instance.absence_limit_percent or 25, low=0, high=100
    )
    try:
        instance.full_clean(exclude=["code"])
        instance.save()
    except IntegrityError:
        return _error(pgettext(_CTX, "Bu kodla ixtisas artıq mövcuddur."), code="duplicate", field="official_code")
    except Exception as exc:  # noqa: BLE001 — ValidationError mesajı istifadəçiyə qaytarılır
        return _error(str(exc), code="validation")

    log_action(
        action=AuditAction.CREATE if is_create else AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=instance,
        request=request,
        reason="catalog: program created" if is_create else "catalog: program updated",
        old_values=old_values or None,
        new_values={"name": instance.name, "degree_level": degree, "education_form": form},
    )
    return JsonResponse({"ok": True, "id": str(instance.id), "created": is_create})


# --------------------------------------------------------------------------- #
# Fənn (Subject)
# --------------------------------------------------------------------------- #


def _save_subject(request, organization):
    subject_id = (request.POST.get("id") or "").strip()
    instance = None
    if subject_id:
        instance = Subject.objects.filter(organization=organization, pk=subject_id).first()
        if instance is None:
            return _error(pgettext(_CTX, "Fənn tapılmadı."), status=404, code="not_found")

    code = (request.POST.get("code") or "").strip()[:32]
    name = (request.POST.get("name") or "").strip()[:255]
    if not code:
        return _error(pgettext(_CTX, "Fənn kodu boş ola bilməz."), code="code_required", field="code")
    if not name:
        return _error(pgettext(_CTX, "Fənnin adı boş ola bilməz."), code="name_required", field="name")

    kind = (request.POST.get("kind") or "").strip()
    if kind not in dict(SubjectKind.choices):
        return _error(pgettext(_CTX, "Fənn növü seçilməyib."), code="bad_kind", field="kind")

    clash = Subject.objects.filter(organization=organization, code=code)
    if instance is not None:
        clash = clash.exclude(pk=instance.pk)
    if clash.exists():
        return _error(pgettext(_CTX, "Bu kodla fənn artıq mövcuddur."), code="duplicate", field="code")

    is_create = instance is None
    if is_create:
        instance = Subject(organization=organization)

    old_values = (
        {}
        if is_create
        else {"code": instance.code, "name": instance.name, "ects": instance.ects, "kind": instance.kind}
    )
    instance.code = code
    instance.name = name
    instance.kind = kind
    instance.ects = _int_or(request.POST.get("ects"), instance.ects or 5, low=1, high=60)
    instance.chair_unit = _chair_unit(organization, (request.POST.get("chair_unit") or "").strip())
    instance.description = (request.POST.get("description") or "").strip()
    try:
        instance.save()
    except IntegrityError:
        return _error(pgettext(_CTX, "Bu kodla fənn artıq mövcuddur."), code="duplicate", field="code")

    log_action(
        action=AuditAction.CREATE if is_create else AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=instance,
        request=request,
        reason="catalog: subject created" if is_create else "catalog: subject updated",
        old_values=old_values or None,
        new_values={"code": code, "name": name, "kind": kind, "ects": instance.ects},
    )
    return JsonResponse({"ok": True, "id": str(instance.id), "created": is_create})


# --------------------------------------------------------------------------- #
# Arxivləmə / bərpa (hər iki model üçün eyni axın)
# --------------------------------------------------------------------------- #

_ARCHIVABLE = {"program": Program, "subject": Subject}


def _archive(request, organization, *, restore: bool):
    model = _ARCHIVABLE.get((request.POST.get("kind") or "").strip())
    if model is None:
        return _error(pgettext(_CTX, "Naməlum kataloq növü."), code="unknown_kind")

    instance = model.objects.filter(organization=organization, pk=(request.POST.get("id") or "").strip()).first()
    if instance is None:
        return _error(pgettext(_CTX, "Yazı tapılmadı."), status=404, code="not_found")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    instance.is_archived = not restore
    instance.archived_reason = reason
    instance.archived_at = None if restore else timezone.now()
    instance.archived_by = None if restore else request.user
    instance.save(update_fields=["is_archived", "archived_reason", "archived_at", "archived_by", "updated_at"])

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=instance,
        request=request,
        reason=("catalog: restored from archive — " if restore else "catalog: archived — ") + reason,
        old_values={"is_archived": restore},
        new_values={"is_archived": not restore},
    )
    return JsonResponse({"ok": True, "id": str(instance.id), "is_archived": instance.is_archived})


_HANDLERS = {
    "save_program": lambda request, organization: _save_program(request, organization),
    "save_subject": lambda request, organization: _save_subject(request, organization),
    "archive": lambda request, organization: _archive(request, organization, restore=False),
    "restore": lambda request, organization: _archive(request, organization, restore=True),
}


@login_required
@require_POST
def catalog_action(request):
    """Kataloq əməlləri — tək JSON endpoint (`catalog.manage` qapısı)."""
    organization = getattr(request, "organization", None)
    if organization is None:
        return _error(pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=403, code="no_org")
    if not can_manage_catalog(request):
        return _error(pgettext(_CTX, "Kataloqu idarə etmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    return handler(request, organization)


__all__ = ["catalog_action"]
