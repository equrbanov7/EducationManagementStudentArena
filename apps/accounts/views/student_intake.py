"""«Tələbə idxalı» bölməsinin JSON/fayl endpoint-ləri (`user.import`).

Üç marşrut:

* ``student_intake_template`` — boş şablon faylı (GET, .xlsx / CSV);
* ``student_intake_preview``  — QURU İCRA: fayl yüklənir, sətir-sətir yoxlanılır,
  HEÇ NƏ YAZILMIR (POST, multipart);
* ``student_intake_apply``    — tətbiq: sətir başına savepoint + audit
  (POST, multipart). Cavabda birdəfəlik parollar qayıdır — operator onları
  CSV kimi endirir; parol nə DB-də, nə də audit jurnalında saxlanılmır.

Hər üçü FAIL-CLOSED: aktiv təşkilat konteksti + `user.import` açarı olmayan
aktor 403 alır. Ön baxış və tətbiq EYNİ plan qurucusundan keçir, ona görə
«gördüyün nəticə = alacağın nəticə».

Qəsdən STATE SAXLANILMIR: «Tətbiq et» eyni faylı yenidən göndərir. Serverdə
yüklənmiş fayl və ya parsed sətirlər sessiyada/kəşdə qalmır (PII + parol riski).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import intake

_CTX = "student_intake"


def _organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


def _denied():
    return JsonResponse(
        {
            "ok": False,
            "error": "permission_denied",
            "message": pgettext(_CTX, "Tələbə idxalı üçün icazəniz yoxdur."),
        },
        status=403,
    )


def _gate(request):
    """``(organization, error_response)`` — fail-closed icazə qapısı."""

    organization = _organization(request)
    if organization is None or not intake.can_import(request.user, organization):
        return None, _denied()
    return organization, None


def _group_overrides(request) -> dict:
    """`group_<sətir>=<qrup id>` POST sahələri → `{sətir: id}`.

    Ekran 08-in «Qrup təyinatı» addımı: operator avtomatik təklifi dəyişəndə
    seçim faylla BİRLİKDƏ göndərilir. Serverdə state saxlanılmır (PII/parol
    riski) — ona görə ön baxış da, tətbiq də eyni sözlüyü alır.
    """
    overrides = {}
    for key, value in request.POST.items():
        if not key.startswith("group_") or not value:
            continue
        overrides[key[len("group_") :]] = value
    return overrides


def _plans_from_request(request, organization):
    """``(plans, error_response)`` — faylı oxuyub planları qurur."""

    try:
        rows = intake.read_rows(request.FILES.get("file"))
    except intake.IntakeFileError as exc:
        return None, JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=400)
    return intake.build_plans(organization, rows, group_overrides=_group_overrides(request)), None


@never_cache
@login_required
@require_GET
def student_intake_template(request):
    """Boş şablon faylı — sütun başlıqları + izah sətri."""

    _organization_or_none, denied = _gate(request)
    if denied is not None:
        return denied
    payload, content_type, filename = intake.build_template()
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
@require_POST
def student_intake_preview(request):
    """Quru icra — nə yaranacaq, nə ötürüləcək, harada xəta var."""

    organization, denied = _gate(request)
    if denied is not None:
        return denied
    plans, error = _plans_from_request(request, organization)
    if error is not None:
        return error
    return JsonResponse(
        {
            "ok": True,
            "summary": intake.summarize(plans),
            "rows": [plan.as_dict() for plan in plans],
        }
    )


@never_cache
@login_required
@require_POST
def student_intake_apply(request):
    """Tətbiq — sətir başına savepoint; bir pis sətir faylı dayandırmır."""

    organization, denied = _gate(request)
    if denied is not None:
        return denied
    plans, error = _plans_from_request(request, organization)
    if error is not None:
        return error
    try:
        result = intake.apply_plans(
            organization=organization,
            plans=plans,
            actor=request.user,
            request=request,
        )
    except intake.IntakeApplyError as exc:
        return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=409)
    result["ok"] = True
    return JsonResponse(result)


@never_cache
@login_required
@require_POST
def student_admission_create_group(request):
    """Ekran 08 «Yeni qrup yarat» — `student.assign_group` icazəsi ilə.

    QƏSDƏN `user.import`-dan AYRI AÇAR: siyahı yükləyə bilən operator
    universitetin struktur ağacına avtomatik qrup əlavə edə bilməməlidir.
    """
    from apps.accounts.services import people
    from apps.accounts.services.student_groups import create_group
    from apps.organizations.models import OrgUnit
    from core.audit import log_action
    from core.constants import AuditAction, OrgUnitType

    organization = _organization(request)
    actor = people.resolve_actor(request)
    if organization is None or not actor.can_assign_groups:
        return _denied()

    import uuid

    try:
        specialty_pk = uuid.UUID((request.POST.get("specialty") or "").strip())
    except ValueError:
        # Qeyri-UUID dəyər `filter(pk=...)`-də ValidationError → 500 verirdi (QA 2026-09-05 STUDENT-MGMT-01).
        specialty_pk = None
    specialty = OrgUnit.objects.filter(
        organization=organization,
        pk=specialty_pk,
        unit_type=OrgUnitType.SPECIALTY,
        is_active=True,
    ).first()
    if specialty is None:
        return JsonResponse(
            {"ok": False, "error": "specialty_not_found", "message": pgettext(_CTX, "İxtisas tapılmadı.")},
            status=404,
        )
    try:
        group = create_group(
            organization,
            specialty_unit=specialty,
            name=request.POST.get("name") or "",
            capacity=request.POST.get("capacity") or 0,
            sector=request.POST.get("sector") or "",
            code=request.POST.get("code") or "",
        )
    except ValueError as exc:
        messages = {
            "group_name_required": pgettext(_CTX, "Qrupun adı boş ola bilməz."),
            "group_name_taken": pgettext(_CTX, "Bu adla qrup artıq var."),
            "specialty_outside_tenant": pgettext(_CTX, "İxtisas tapılmadı."),
        }
        # CodeQL py/stack-trace-exposure: istisna mətni müştəriyə OLDUĞU KİMİ
        # qaytarılmır — yalnız bilinən kod siyahısından keçir, qalanı generik.
        raw = str(exc)
        # Cavaba istisnadan gələn DƏYƏR deyil, sabit açar siyahısındakı EKVİVALENTİ yazılır.
        code = next((known for known in messages if known == raw), "invalid")
        message = messages.get(code) or pgettext(_CTX, "Qrup yaradıla bilmədi.")
        return JsonResponse({"ok": False, "error": code, "field": "name", "message": message}, status=400)

    log_action(
        AuditAction.CREATE,
        user=request.user,
        organization=organization,
        obj=group,
        reason="student_admission_group_created",
        request=request,
        resource_type="organizations.org_unit",
        resource_id=str(group.pk),
        resource_repr=group.name,
        changes={"specialty": str(specialty.pk), "capacity": group.settings.get("capacity")},
    )
    return JsonResponse({"ok": True, "id": str(group.pk), "name": group.name})


__all__ = [
    "student_admission_create_group",
    "student_intake_apply",
    "student_intake_preview",
    "student_intake_template",
]
