"""Publik sənəd yoxlaması — ``/yoxla/`` (kod formu) və ``/yoxla/<kod>/`` (nəticə + faylı müqayisə).

Girişsiz işləyir; şəbəkə zonası qapısı ``/yoxla/``-nı kənardan da açıq saxlayır
(``apps.accounts.network_zone._ALWAYS_OPEN_PREFIXES``).

Təhlükəsizlik:

* **Sadalamaya qarşı**: kod 80 bitdir; yanlış format və tapılmayan kod EYNİ 404 səhifəsini alır (fərq
  sızmır); İP başına iki büdcə — ümumi sorğu (``DOCUMENT_VERIFY_RATE_LIMIT``) və «tapılmadı»
  (``DOCUMENT_VERIFY_MISS_RATE_LIMIT``). «Tapılmadı» büdcəsi bitəndə kod ÜMUMİYYƏTLƏ həll olunmur
  (live_exam LXS-06 dərsi: limit səhifəsi orakul olmasın).
* **PII minimumu**: sahibin adı maskalıdır («Elvin Q.»), yalnız ``payload``-dakı yekun faktlar göstərilir.
* ``noindex`` (meta + ``X-Robots-Tag``), ``no-store``, ``Referrer-Policy: same-origin`` — kod URL-dədir (üçüncü tərəfə getmir).
* **Audit**: tapılan kod üzrə hər baxış/müqayisə ``log_action`` (kod + nəticə + İP-nin HMAC həşi; tam İP
  YAZILMIR); tapılmayan kod üçün yalnız yüngül sayğac (keş) + log — audit cədvəli zibillə dolmasın.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from django.apps import apps as django_apps
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

from core.rate_limit import is_rate_limited, record_rate_limit_hit
from core.utils import get_client_ip

from . import codes, facts, upload
from .lookup import STATUS_REVOKED, find_by_code

logger = logging.getLogger("verification")

LOOKUP_SCOPE = "doc_verify_lookup"
MISS_SCOPE = "doc_verify_miss"
UPLOAD_SCOPE = "doc_verify_upload"
LOOKUP_RATE_DEFAULT = "60/10m"
MISS_RATE_DEFAULT = "15/10m"
UPLOAD_RATE_DEFAULT = "10/10m"
AUDIT_LOOKUP = "verification.lookup"

_TEMPLATE = "verification/public/verify.html"


def _rate(name: str, default: str) -> str:
    return getattr(settings, name, default) or default


def _ip_key(request) -> str:
    return f"ip:{get_client_ip(request) or 'unknown'}"


def ip_hash(request) -> str:
    """İP-nin açarlı (SECRET_KEY) HMAC-SHA256 qısa həşi — eyni mənbəni tanımaq olur, İP-ni bərpa etmək olmur."""
    raw = str(get_client_ip(request) or "unknown").encode()
    return hmac.new(str(settings.SECRET_KEY).encode(), raw, hashlib.sha256).hexdigest()[:16]


def _secure(response):
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Cache-Control"] = "no-store, private"
    # `same-origin`: kod üçüncü tərəfə getmir, amma öz formamızın POST-u real `Origin` daşıyır
    # (`no-referrer` → `Origin: null` → Django CSRF HTTPS-də rədd edir).
    response["Referrer-Policy"] = "same-origin"
    return response


def _page(request, context, *, status=200, retry_after=None):
    base = {
        "seo_robots": "noindex, nofollow",
        "form_code": "",
        "upload_field": upload.FIELD_NAME,
        "upload_max_mb": upload.max_bytes() // (1024 * 1024),
    }
    base.update(context)
    response = render(request, _TEMPLATE, base, status=status)
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return _secure(response)


def _limited_page(request, retry_after, *, code=""):
    return _page(request, {"state": "limited", "form_code": code}, status=429, retry_after=retry_after)


def _not_found_page(request, *, code=""):
    return _page(request, {"state": "not_found", "form_code": code}, status=404)


def _lookup_budget(request):
    """``retry_after`` (limitlidir) və ya ``None``. «Tapılmadı» büdcəsi bitibsə kod həll olunmur."""
    key = _ip_key(request)
    limited, retry_after = is_rate_limited(MISS_SCOPE, _rate("DOCUMENT_VERIFY_MISS_RATE_LIMIT", MISS_RATE_DEFAULT), key)
    if limited:
        return retry_after or 60
    limited, retry_after = record_rate_limit_hit(
        LOOKUP_SCOPE, _rate("DOCUMENT_VERIFY_RATE_LIMIT", LOOKUP_RATE_DEFAULT), key
    )
    return (retry_after or 60) if limited else None


def _record_miss(request) -> None:
    record_rate_limit_hit(MISS_SCOPE, _rate("DOCUMENT_VERIFY_MISS_RATE_LIMIT", MISS_RATE_DEFAULT), _ip_key(request))
    day_key = f"doc_verify:miss:{timezone.localdate():%Y%m%d}"
    try:
        if not cache.add(day_key, 1, timeout=2 * 24 * 3600):
            cache.incr(day_key)
    except Exception:  # noqa: BLE001 — sayğac heç vaxt cavabı sındırmasın
        pass
    logger.info("verification: unknown code lookup ip_hash=%s", ip_hash(request))


def _audit_lookup(request, seal, result: str) -> None:
    """Tapılmış möhür üzrə publik baxış/müqayisə — kod + nəticə + İP həşi (``request`` ötürülmür: tam İP yox)."""
    from core.audit import log_action
    from core.constants import AuditAction

    Organization = django_apps.get_model("organizations", "Organization")
    try:
        with transaction.atomic():
            log_action(
                AuditAction.VERIFY,
                organization=Organization(pk=seal.organization_id),
                resource_type=AUDIT_LOOKUP,
                resource_id=seal.code,
                resource_repr=f"{seal.doc_type_label} — {seal.code}"[:200],
                reason="public_lookup",
                new_values={"result": result, "ip_hash": ip_hash(request)},
            )
    except Exception:  # noqa: BLE001 — audit publik səhifəni sındırmasın
        logger.exception("verification: lookup audit yazılmadı")


def _seal_context(seal) -> dict:
    payload = seal.payload or {}
    return {
        "seal": seal,
        "state": seal.status,
        "facts": facts.labelled(payload.get("facts")),
        "holder": payload.get("holder") or "—",
        "org_name": payload.get("org") or "",
        "can_compare": bool(seal.file_sha256),
    }


@never_cache
@require_GET
def verify_home(request):
    """Kod formu. ``?kod=`` ilə gələn sorğu kanonik ``/yoxla/<kod>/``-a yönləndirilir (DB sorğusu YOX)."""
    raw = (request.GET.get("kod") or "").strip()
    if not raw:
        return _page(request, {"state": "form"})
    code = codes.normalize(raw)
    if code is None:
        return _page(request, {"state": "invalid", "form_code": raw[:40]})
    return redirect("verification:detail", code=code)


@never_cache
@csrf_exempt  # CSRF aşağıda `csrf_protect` ilə — upload handler POST oxunmamışdan ƏVVƏL qurulmalıdır
@require_http_methods(["GET", "POST"])
def verify_detail(request, code):
    if request.method == "POST":
        if upload.body_too_large(request):
            return _upload_result(request, code, forced=upload.RESULT_TOO_LARGE)
        upload.install_memory_handler(request)
        return _compare_upload(request, code)
    canonical = codes.normalize(code)
    if canonical is None:
        return _not_found_page(request)
    if canonical != code:
        return redirect("verification:detail", code=canonical)
    retry_after = _lookup_budget(request)
    if retry_after:
        return _limited_page(request, retry_after)
    seal = find_by_code(canonical)
    if seal is None:
        _record_miss(request)
        return _not_found_page(request)
    _audit_lookup(request, seal, seal.status)
    return _page(request, _seal_context(seal))


@csrf_protect
def _compare_upload(request, code):
    return _upload_result(request, code)


def _upload_result(request, code, *, forced=None):
    canonical = codes.normalize(code)
    if canonical is None:
        return _not_found_page(request)
    key = _ip_key(request)
    limited, retry_after = record_rate_limit_hit(
        UPLOAD_SCOPE, _rate("DOCUMENT_VERIFY_UPLOAD_RATE_LIMIT", UPLOAD_RATE_DEFAULT), key
    )
    if limited:
        return _limited_page(request, retry_after or 60)
    retry_after = _lookup_budget(request)
    if retry_after:
        return _limited_page(request, retry_after)
    seal = find_by_code(canonical)
    if seal is None:
        _record_miss(request)
        return _not_found_page(request)
    uploaded = None if forced is not None else request.FILES.get(upload.FIELD_NAME)  # parse burada (handler bayrağı)
    if forced is not None or getattr(request, "doc_verify_upload_too_large", False):
        result = forced or upload.RESULT_TOO_LARGE
    else:
        result = upload.compare(uploaded, seal.file_sha256)
    _audit_lookup(request, seal, f"upload_{result}")
    context = _seal_context(seal)
    context["compare_result"] = result
    context["compare_revoked"] = seal.status == STATUS_REVOKED
    return _page(request, context)


__all__ = ["ip_hash", "verify_detail", "verify_home"]
