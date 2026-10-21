"""Deploy system check-i — rəsmi sənədin QR yoxlama ünvanının kökü (rəy 2026-10-21).

QR kodda çap olunan URL ``services.verification_base_url()``-dən qurulur: ``DOCUMENT_VERIFY_BASE_URL``,
boşdursa ``SITE_URL``. Production-da ``SITE_URL``-in defoltu ``https://127.0.0.1``-dir — .env-də unudulsa
hər çap olunan sənədin QR kodu kənardan açılmayan ünvana aparır və bunu heç kim deploy anında görmür.

Bu check ``manage.py check --deploy`` (``scripts/deploy/remote_deploy.sh`` → ``preflight_django_deploy_check``,
CI ``_security.yml``) zamanı işləyir və effektiv kök boşdursa, ``127.0.0.1`` / ``localhost`` / ``0.0.0.0`` /
``::1``-dirsə və ya ``https`` deyilsə:

* production-da (``MANAGEMENT_COMMAND_ENVIRONMENT == "production"``) — ``Error`` (``verification.E001``);
* digər mühitlərdə — ``Warning`` (``verification.W001``; lokal ``check --deploy`` sınağı bloklanmasın).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, Tags
from django.core.checks import Warning as CheckWarning
from django.core.checks import register

E_VERIFY_BASE_URL = "verification.E001"
W_VERIFY_BASE_URL = "verification.W001"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]"})

_HINT = (
    ".env-də DOCUMENT_VERIFY_BASE_URL=https://<publik domen> (məs. https://ems.wcu.edu.az) və ya düzgün "
    "SITE_URL təyin edin; docker-compose.prod.yml hər ikisini konteynerə ötürür."
)


def verify_base_url_problem(base: str) -> str | None:
    """Effektiv kökün problemi (insan mətni) və ya ``None`` — düzgündür."""
    base = str(base or "").strip()
    if not base:
        return "boşdur"
    parts = urlsplit(base)
    host = (parts.hostname or "").lower()
    if not host:
        return f"host yoxdur ({base})"
    if host in _LOOPBACK_HOSTS or host.startswith("127."):
        return f"loopback ünvandır ({base}) — kənardan açılmır"
    if parts.scheme != "https":
        return f"https deyil ({base})"
    return None


@register(Tags.security, deploy=True)
def check_document_verify_base_url(app_configs, **kwargs):
    from .services import verification_base_url

    problem = verify_base_url_problem(verification_base_url())
    if problem is None:
        return []
    message = f"Rəsmi sənədin QR yoxlama ünvanının kökü {problem} (DOCUMENT_VERIFY_BASE_URL / SITE_URL)."
    if getattr(settings, "MANAGEMENT_COMMAND_ENVIRONMENT", "") == "production":
        return [Error(message, hint=_HINT, id=E_VERIFY_BASE_URL)]
    return [CheckWarning(message, hint=_HINT, id=W_VERIFY_BASE_URL)]


__all__ = ["E_VERIFY_BASE_URL", "W_VERIFY_BASE_URL", "check_document_verify_base_url", "verify_base_url_problem"]
