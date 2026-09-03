"""Ekran 01 «Universitet strukturu» — AĞAC ƏMƏLLƏRİ (JSON POST).

Dörd əməl: alt bölmə yaratmaq, adını/kodunu dəyişmək, rəhbər təyin etmək,
ARXİVLƏMƏK. **Silmə yoxdur** (handoff §8 qayda 5) — arxivləmə
``OrgUnit.is_active=False``-dur; bölmə ilə bağlı tələbə, jurnal və qiymət
tarixçəsi olduğu kimi qalır.

SƏBƏB MƏCBURİDİR (handoff §8 qayda 6): rəhbər təyini və arxivləmə üçün ≥20
simvol. Səbəb ``core.audit.log_action``-a aktor + timestamp ilə yazılır.

QAPI ÜÇ QAT:
  1. ``unit.view`` + struktur scope-u (fail-closed — əhatəsiz aktor 403);
  2. əməl açarı — yaratma/redaktə/arxiv üçün ``unit.tree_manage`` (və ya köhnə
     ``unit.create``/``unit.edit``), rəhbər təyini üçün AYRICA ``unit.assign_head``;
  3. hədəf bölmənin GÖRÜNƏN olması (``_visible_units_queryset``) — cross-tenant
     və əhatədən kənar id 404 alır (IDOR).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.audit import log_action
from core.constants import AuditAction

from .models import Membership, Organization, OrgUnit
from .structure_views.tree import TREE_TYPE_ORDER, tree_scope
from .views import _has_org_permission, _unique_unit_slug, _visible_units_queryset

_CTX = "accounts.structure_tree"

#: Səbəb tələb edən əməllərin minimum uzunluğu (handoff §8 qayda 6).
REASON_MIN_LENGTH = 20


def _error(message, *, status=400, code="invalid"):
    return JsonResponse({"ok": False, "error": code, "message": message}, status=status)


def _reason_or_none(request):
    reason = (request.POST.get("reason") or "").strip()
    if len(reason) < REASON_MIN_LENGTH:
        return None, _error(
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
            code="reason_too_short",
        )
    return reason, None


def _visible_unit(organization, scope, unit_id):
    if not unit_id:
        return None
    return _visible_units_queryset(organization, scope).filter(pk=unit_id).select_related("parent", "head").first()


def _create_child(request, organization, scope):
    parent = _visible_unit(organization, scope, (request.POST.get("parent") or "").strip())
    if parent is None:
        return _error(pgettext(_CTX, "Valideyn bölmə tapılmadı."), status=404, code="not_found")

    name = (request.POST.get("name") or "").strip()[:255]
    if not name:
        return _error(pgettext(_CTX, "Bölmənin adı boş ola bilməz."), code="name_required")

    unit_type = (request.POST.get("unit_type") or "").strip()
    if unit_type not in TREE_TYPE_ORDER:
        return _error(pgettext(_CTX, "Bölmə tipi bu təşkilat üçün keçərli deyil."), code="bad_type")

    unit = OrgUnit.objects.create(
        organization=organization,
        parent=parent,
        unit_type=unit_type,
        name=name,
        code=(request.POST.get("code") or "").strip()[:50],
        slug=_unique_unit_slug(organization, name, "unit"),
    )
    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=organization,
        obj=unit,
        request=request,
        reason=f"structure tree: child unit created under {parent.name}",
        new_values={"name": unit.name, "unit_type": unit.unit_type, "parent": str(parent.id)},
    )
    return JsonResponse({"ok": True, "unit_id": str(unit.id)})


def _rename(request, organization, scope):
    unit = _visible_unit(organization, scope, (request.POST.get("unit") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı."), status=404, code="not_found")

    name = (request.POST.get("name") or "").strip()[:255]
    if not name:
        return _error(pgettext(_CTX, "Bölmənin adı boş ola bilməz."), code="name_required")

    old = {"name": unit.name, "code": unit.code}
    unit.name = name
    unit.code = (request.POST.get("code") or "").strip()[:50]
    unit.save(update_fields=["name", "code", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=unit,
        request=request,
        reason="structure tree: unit renamed",
        old_values=old,
        new_values={"name": unit.name, "code": unit.code},
    )
    return JsonResponse({"ok": True, "unit_id": str(unit.id)})


def _assign_head(request, organization, scope):
    if not _has_org_permission(request, "unit.assign_head"):
        return _error(pgettext(_CTX, "Rəhbər təyini üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    unit = _visible_unit(organization, scope, (request.POST.get("unit") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı."), status=404, code="not_found")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    head_id = (request.POST.get("head") or "").strip()
    new_head = None
    if head_id:
        # Rəhbər YALNIZ bu təşkilatın aktiv üzvü ola bilər (cross-tenant qapısı).
        membership = (
            Membership.objects.filter(organization=organization, is_active=True, user_id=head_id)
            .select_related("user")
            .first()
        )
        if membership is None:
            return _error(pgettext(_CTX, "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil."), code="bad_head")
        new_head = membership.user

    old_head = unit.head
    unit.head = new_head
    unit.save(update_fields=["head", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=unit,
        request=request,
        reason=f"structure tree: head assigned — {reason}",
        old_values={"head": str(old_head) if old_head else ""},
        new_values={"head": str(new_head) if new_head else ""},
    )
    return JsonResponse({"ok": True, "unit_id": str(unit.id)})


def _archive(request, organization, scope):
    unit = _visible_unit(organization, scope, (request.POST.get("unit") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı."), status=404, code="not_found")

    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure

    if OrgUnit.objects.filter(organization=organization, parent=unit, is_active=True).exists():
        return _error(
            pgettext(_CTX, "Aktiv alt bölməsi olan vahid arxivlənə bilməz — əvvəlcə alt bölmələri arxivləyin."),
            code="has_children",
        )

    unit.is_active = False
    unit.save(update_fields=["is_active", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=unit,
        request=request,
        reason=f"structure tree: unit archived — {reason}",
        old_values={"is_active": True},
        new_values={"is_active": False, "archived_at": timezone.now().isoformat()},
    )
    return JsonResponse({"ok": True, "unit_id": str(unit.id)})


_HANDLERS = {
    "create_child": _create_child,
    "rename": _rename,
    "assign_head": _assign_head,
    "archive": _archive,
}

#: Rəhbər təyini ÖZ açarını yoxlayır (``_assign_head``); qalan üçü ağac
#: idarəetməsi açarını tələb edir.
_TREE_MANAGE_ACTIONS = frozenset({"create_child", "rename", "archive"})


@login_required
@require_POST
def structure_tree_action(request, slug):
    """«Universitet strukturu» ağac əməlləri — tək JSON endpoint."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")

    action = (request.POST.get("action") or "").strip()
    handler = _HANDLERS.get(action)
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")

    if action in _TREE_MANAGE_ACTIONS and not (
        _has_org_permission(request, "unit.tree_manage")
        or _has_org_permission(request, "unit.edit")
        or _has_org_permission(request, "unit.create")
    ):
        return _error(
            pgettext(_CTX, "Struktur ağacını idarə etmək səlahiyyətiniz yoxdur."), status=403, code="forbidden"
        )

    return handler(request, organization, scope)


__all__ = ["structure_tree_action", "REASON_MIN_LENGTH"]
