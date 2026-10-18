"""«Sənəd yoxlaması» — əməkdaş səhifəsi (``/sened-yoxlamasi/``): siyahı, axtarış, «Ləğv et».

Kabinet bölməsi DEYİL, ayrıca səhifədir (``sections_api.py`` 600 sətir büdcəsindədir); sidebar-dakı
keçid ``role_capabilities.can_manage_document_seals`` bayrağı ilə görünür (``rbac_sections.py``).

Qapı: açar yoxdursa 403; möhür əhatədən kənardadırsa 404; view-as altında ləğv 403. ATOMIC_REQUESTS
altında səlahiyyət HƏR YAZIDAN ƏVVƏL yoxlanılır.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import access, codes, services
from .lookup import STATUS_REVOKED, STATUS_VALID

PAGE_SIZE = 25
STATUS_FILTERS = ("all", STATUS_VALID, STATUS_REVOKED)


def _organization_or_404(request):
    organization = getattr(request, "organization", None)
    if organization is None:
        raise Http404
    return organization


def _search(queryset, raw: str):
    text = " ".join(str(raw or "").split())[:80]
    if not text:
        return queryset
    code = codes.normalize(text)
    if code is not None:
        return queryset.filter(code=code)
    condition = Q(code__icontains=text)
    tokens = text.split()
    name_q = Q()
    for token in tokens[:4]:
        name_q &= (
            Q(subject_user__first_name__icontains=token)
            | Q(subject_user__last_name__icontains=token)
            | Q(subject_user__username__icontains=token)
        )
    return queryset.filter(condition | name_q)


def _filter_status(queryset, status: str):
    if status == STATUS_VALID:
        return queryset.filter(revoked_at__isnull=True)
    if status == STATUS_REVOKED:
        return queryset.filter(revoked_at__isnull=False)
    return queryset


def _status_links(base_params: dict, current: str):
    labels = {
        "all": pgettext("verification.staff", "Hamısı"),
        STATUS_VALID: pgettext("verification.staff", "Etibarlı"),
        STATUS_REVOKED: pgettext("verification.staff", "Ləğv edilib"),
    }
    out = []
    for key in STATUS_FILTERS:
        params = {k: v for k, v in base_params.items() if v}
        if key != "all":
            params["status"] = key
        out.append({"key": key, "label": labels[key], "active": key == current, "query": urlencode(params)})
    return out


@never_cache
@login_required
@require_GET
def seal_list(request):
    organization = _organization_or_404(request)
    scope = access.manage_scope(request.user, organization, request=request)
    if not scope.has_structure_access:
        raise PermissionDenied
    query = (request.GET.get("q") or "").strip()[:80]
    status = request.GET.get("status") or "all"
    if status not in STATUS_FILTERS:
        status = "all"
    queryset = access.scoped_seals(scope, organization).select_related("subject_user", "issued_by", "revoked_by")
    queryset = _filter_status(_search(queryset, query), status).order_by("-issued_at")
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    context = {
        "page_obj": page,
        "seals": page.object_list,
        "query": query,
        "status": status,
        "status_links": _status_links({"q": query}, status),
        "page_query": urlencode({k: v for k, v in (("q", query), ("status", status if status != "all" else "")) if v}),
        "read_only": access.is_read_only(request),
        "min_reason": services.MIN_REVOKE_REASON,
        "organization": organization,
        "seo_robots": "noindex, nofollow",
    }
    response = render(request, "verification/staff/list.html", context)
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def seal_revoke(request, pk):
    organization = _organization_or_404(request)
    scope = access.manage_scope(request.user, organization, request=request)
    if not scope.has_structure_access or access.is_read_only(request):
        raise PermissionDenied
    seal = access.scoped_seals(scope, organization).filter(pk=pk).first()
    if seal is None:
        raise Http404
    try:
        services.revoke_seal(seal=seal, actor=request.user, reason=request.POST.get("reason"), request=request)
    except services.SealError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, pgettext("verification.staff", "Sənəd ləğv edildi: %(code)s") % {"code": seal.code})
    return redirect(f"{reverse('verification:staff_list')}?{urlencode({'q': seal.code})}")


__all__ = ["seal_list", "seal_revoke"]
