"""
Final imtahan mərkəzi (/exams/final/) üçün şəbəkə-səviyyəli giriş qapısı.

Qayda:
* ``FINAL_EXAM_ALLOWED_IPS`` BOŞDURSA → hamıya açıq (hazırkı rejim).
* Doldurulubsa → yalnız siyahıdakı IP-lərdən / CIDR şəbəkələrindən gələn
  sorğular buraxılır (məs. imtahan zalının kompüterləri).

MAC ünvanı barədə: MAC yalnız lokal şəbəkə (L2) kadrlarında mövcuddur və
HTTP sorğusu ilə serverə ÇATMIR — proxy/router arxasından texniki cəhətdən
oxuna bilməz. MAC-əsaslı məhdudiyyət imtahan zalının şlüzündə (məs. router
MAC-filter + sabit IP mapping) və ya gələcək müştəri agenti ilə tətbiq
olunmalıdır; server tərəfində etibarlı yoxlama vahidi IP/CIDR-dir.
"""

import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """Sorğunun müştəri IP-si (etibarlı proxy arxasında XFF-in ilk üzvü)."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
        if candidate:
            return candidate
    return request.META.get("REMOTE_ADDR") or ""


def _allowed_entries():
    return [entry for entry in getattr(settings, "FINAL_EXAM_ALLOWED_IPS", []) if entry]


def final_exam_access_allowed(request) -> bool:
    """
    Final səhifəsinə bu sorğu buraxılsınmı?

    Boş allowlist → True (açıq rejim). Yanlış formatlı siyahı girişləri
    sorğunu bloklamır — sadəcə ötürülür və log-a yazılır ki, konfiq səhvi
    bütün imtahan zalını kilidləməsin.
    """
    entries = _allowed_entries()
    if not entries:
        return True

    ip_text = get_client_ip(request)
    try:
        client_ip = ipaddress.ip_address(ip_text)
    except ValueError:
        logger.warning("final_exam_access: müştəri IP-si oxunmadı (%r) — giriş rədd edildi.", ip_text)
        return False

    for entry in entries:
        try:
            if "/" in entry:
                if client_ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif client_ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            logger.warning("final_exam_access: allowlist girişi yanlış formatdadır, ötürülür: %r", entry)
            continue
    return False


def room_ip_access_allowed(request, room) -> bool:
    """
    Zal-səviyyəli giriş qapısı: bu sorğu HƏMİN zalın qeydli kompüterlərindən
    (IP üzrə) gəlirmi?

    * Zalın aktiv kompüterlərində HEÇ IP təyin olunmayıbsa → ``True`` (bu zal
      üçün per-kompüter məhdudiyyət yoxdur; qlobal ``final_exam_access_allowed``
      artıq qərar verib).
    * IP-lər varsa → müştəri IP-si həmin siyahıda olmalıdır. Müştəri IP-si
      oxunmursa/uyğun gəlmirsə → ``False``.

    QEYD: MAC HTTP ilə serverə çatmadığı üçün etibarlı yoxlama vahidi IP-dir
    (bax modul başlığı). MAC yalnız identifikasiya/inventar sahəsidir.
    """
    ip_values = [ip for ip in room.computers.filter(is_active=True).values_list("ip_address", flat=True) if ip]
    if not ip_values:
        return True

    client_text = get_client_ip(request)
    try:
        client_ip = ipaddress.ip_address(client_text)
    except ValueError:
        logger.warning("room_ip_access: müştəri IP-si oxunmadı (%r) — giriş rədd edildi.", client_text)
        return False

    for entry in ip_values:
        try:
            if client_ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            logger.warning("room_ip_access: zal kompüteri IP-si yanlış formatdadır, ötürülür: %r", entry)
            continue
    return False


__all__ = [
    "final_exam_access_allowed",
    "get_client_ip",
    "room_ip_access_allowed",
]
