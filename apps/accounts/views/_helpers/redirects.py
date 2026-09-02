"""
Safe redirect helpers.

Both functions enforce same-origin redirect targets so untrusted ``next``
parameters cannot be used for open-redirect attacks.

⚠️ ``url_has_allowed_host_and_scheme`` MÜTLƏQ birinci arqumenti POZİSİYA ilə
alır. Statik analiz (CodeQL ``py/url-redirection``) bu çağırışı yalnız o formada
«sanitizer» kimi tanıyır; ``url=`` açar sözü ilə yazılsa yoxlama işləsə də,
analiz onu görmür və hər çağıran səthdə saxta open-redirect xəbərdarlığı çıxır.
"""

from django.utils.http import url_has_allowed_host_and_scheme


def _resolve_next_url(request, fallback_url):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not next_url:
        return fallback_url

    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    return raw_url
