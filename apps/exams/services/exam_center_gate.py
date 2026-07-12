"""
Final imtahan mərkəzi (/exams/final/) üçün şəbəkə-səviyyəli giriş qapısı.

Qayda:
* ``FINAL_EXAM_ALLOWED_IPS`` BOŞDURSA → hamıya açıq (hazırkı rejim).
* Doldurulubsa → yalnız siyahıdakı IP-lərdən / CIDR şəbəkələrindən gələn
  sorğular buraxılır (məs. imtahan zalının kompüterləri).

MAC ünvanı barədə: MAC HTTP sorğusu ilə serverə ÇATMIR — proxy/router
arxasından oxuna bilməz. AMMA imtahan zalı kompüterləri serverlə eyni L2
seqmentdə olduqda onların real MAC-ları host-un ARP cədvəlində görünür.
``EXAM_CLIENT_MAC_RESOLUTION="arp_agent"`` rejimində müştəri IP-sinin MAC-ı
host ARP agentindən (bax docker/arp-agent) soruşulur və kompüter yoxlamaları
IP əvəzinə MAC ilə aparılır — DHCP-də IP dəyişəndə giriş pozulmur. Rejim
"off" olduqda köhnə IP-əsaslı yoxlama qalır (dev/test). Kənar (marşrutlanmış)
sorğular üçün ARP qeydi yoxdur → MAC rejimi fail-closed işləyir.
"""

import ipaddress
import json
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


def mac_enforcement_active() -> bool:
    """Kompüter yoxlamaları MAC (ARP agenti) rejimindədirmi?"""
    return getattr(settings, "EXAM_CLIENT_MAC_RESOLUTION", "off") == "arp_agent"


def resolve_client_mac(request) -> str | None:
    """Müştəri IP-sinin MAC-ını host ARP agentindən alır (yalnız MAC rejimi).

    Qaytarır: kanonik ``AA:BB:CC:DD:EE:FF`` formatında MAC, tapılmayanda /
    agent əlçatmaz olanda / rejim "off" olanda ``None``. Kənar müştərilərin
    (başqa şəbəkədən marşrutlanan) ARP qeydi olmur — onlar üçün həmişə None.
    """
    from apps.exams.models import ExamRoomComputer

    if not mac_enforcement_active():
        return None
    base = (getattr(settings, "EXAM_ARP_AGENT_URL", "") or "").rstrip("/")
    if not base:
        logger.error("resolve_client_mac: EXAM_ARP_AGENT_URL boşdur — MAC rejimi işləyə bilmir.")
        return None
    ip_text = get_client_ip(request)
    try:
        ipaddress.ip_address(ip_text)
    except ValueError:
        return None
    timeout = getattr(settings, "EXAM_ARP_AGENT_TIMEOUT_SECONDS", 0.5)
    try:
        with urlopen(f"{base}/mac?{urlencode({'ip': ip_text})}", timeout=timeout) as resp:  # nosec B310
            raw_mac = (json.load(resp) or {}).get("mac")
    except Exception as exc:  # agent xətası imtahan qapısını AÇMIR (fail-closed)
        logger.warning("resolve_client_mac: ARP agenti cavab vermədi (%s) — giriş rədd ediləcək.", exc)
        return None
    if not raw_mac:
        return None
    try:
        return ExamRoomComputer.normalize_mac(raw_mac)
    except ValueError:
        logger.warning("resolve_client_mac: agentdən yanlış MAC formatı: %r", raw_mac)
        return None


def get_client_ip(request) -> str:
    """Sorğunun müştəri IP-si (etibarlı proxy arxasında XFF-in SON üzvü).

    Nginx (2026-07-11 auditindən sonra) X-Forwarded-For-u client zəncirinə
    əlavə ETMİR — başlığı öz gördüyü peer ünvanı ilə OVERWRITE edir, yəni
    dəyər həmişə tək və nginx-ə məxsusdur. Son üzvü götürmək köhnə (append)
    konfiqurasiya ilə də geriyə-uyğundur: hər iki halda son üzv müştəri
    tərəfindən idarə oluna bilmir. İmtahan zalı kompüterləri nginx-ə birbaşa
    qoşulduğu üçün dəyər real zal IP-sidir.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        candidate = forwarded_for.split(",")[-1].strip()
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
    gəlirmi? MAC rejimində müqayisə MAC ilə, "off" rejimində IP ilə aparılır.

    * Zalın heç bir aktiv kompüteri (MAC rejimində) / IP-li kompüteri ("off")
      yoxdursa → ``True`` (bu zal üçün per-kompüter məhdudiyyət yoxdur; qlobal
      ``final_exam_access_allowed`` artıq qərar verib).
    * Qeydlər varsa → müştəri onlardan birinə uyğun gəlməlidir; MAC/IP
      oxunmursa → ``False`` (fail-closed).
    """
    if mac_enforcement_active():
        mac_values = set(room.computers.filter(is_active=True).values_list("mac_address", flat=True))
        if not mac_values:
            return True
        client_mac = resolve_client_mac(request)
        if client_mac is None:
            logger.warning("room_access: müştəri MAC-ı tapılmadı — giriş rədd edildi.")
            return False
        return client_mac in mac_values

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


def org_computer_access_allowed(request, organization) -> bool:
    """
    Org-səviyyə kompüter qapısı — biletsiz (ExamStudentPin) final girişi üçün.

    Org-da HEÇ aktiv qeydli kompüter yoxdursa → ``True`` (zal-kompüter sistemi
    işlətməyən org-lar üçün mövcud davranış qorunur). Qeydlər varsa → sorğu
    onlardan birindən gəlməlidir (MAC rejimində MAC, "off" rejimində IP ilə).
    PUBLIC axındır (tələbə hələ login olmayıb) — RLS bypass ilə oxunur.
    """
    from apps.exams.models import ExamRoomComputer
    from core.rls import bypass_rls

    if organization is None:
        return True
    with bypass_rls():
        qs = ExamRoomComputer.objects.filter(organization=organization, is_active=True)
        if not qs.exists():
            return True
        if mac_enforcement_active():
            client_mac = resolve_client_mac(request)
            if client_mac is None:
                logger.warning("org_computer_access: müştəri MAC-ı tapılmadı — giriş rədd edildi.")
                return False
            return qs.filter(mac_address=client_mac).exists()
        client_text = get_client_ip(request)
        try:
            client_ip = ipaddress.ip_address(client_text)
        except ValueError:
            logger.warning("org_computer_access: müştəri IP-si oxunmadı (%r) — giriş rədd edildi.", client_text)
            return False
        for entry in qs.filter(ip_address__isnull=False).values_list("ip_address", flat=True):
            try:
                if ipaddress.ip_address(entry) == client_ip:
                    return True
            except ValueError:
                continue
    return False


def exam_room_isolation_allowed(exam, room) -> bool:
    """
    Otaq izolyasiyası (PIN final yolu): imtahan hansı zal(lar)da CANLI gedirsə,
    yeni giriş yalnız həmin zal(lar)ın kompüterlərindən mümkündür. İlk girən
    tələbənin zalı imtahanı həmin zala bağlayır; canlı bilet/cəhdlər bitəndə
    bağlılıq öz-özünə düşür. ``room`` None olduqda (org-da qeydli kompüter
    yoxdur) məhdudiyyət tətbiq olunmur.
    """
    if room is None:
        return True
    from apps.exams.domain.final_center import (
        ROOM_SESSION_STATE_ACTIVE,
        ROOM_SESSION_STATE_ENTRY_OPEN,
        TICKET_LIVE_STATUSES,
        TICKET_STATUS_ASSIGNED,
    )
    from apps.exams.models import ExamAttempt, FinalExamTicket
    from core.rls import bypass_rls

    # Public giriş axını (login-dən əvvəl) — RLS bypass (bax resolve_room_computer).
    # ASSIGNED bilet də sayılır (tələbə girib, hələ təsdiq/gözləmədədir) —
    # amma yalnız CANLI oturumda; bitmiş oturumların biletləri bağlamır.
    with bypass_rls():
        live_room_ids = set(
            ExamAttempt.objects.filter(exam=exam, status="in_progress", is_trial=False, room__isnull=False).values_list(
                "room_id", flat=True
            )
        ) | set(
            FinalExamTicket.objects.filter(
                exam=exam,
                status__in=(TICKET_STATUS_ASSIGNED, *TICKET_LIVE_STATUSES),
                session__state__in=(ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE),
            ).values_list("session__room_id", flat=True)
        )
    return not live_room_ids or room.pk in live_room_ids


def resolve_room_computer(request, organization):
    """
    Müştəri sorğusundan ZALI və kompüteri həll et (oturum sisteminin ləğvi, 2026-07).

    Tələbə qeydli kompüterdən girəndə hansı zalda olduğunu bilmək üçün: org-un
    aktiv ``ExamRoomComputer`` sətirlərində müştəri axtarılır — MAC rejimində
    ARP-dən alınan MAC ilə, "off" rejimində müştəri IP-si ilə. Uyğun gələn
    kompüterin zalı qaytarılır — imtahandan asılı olmayaraq, tələbə həmin zalın
    açıq oturumuna qoşulur (bax ``attach_ticket_to_room_sitting``).

    Qaytarır: ``(room, computer)`` uyğun gələndə, əks halda ``(None, None)``.
    """
    from apps.exams.models import ExamRoomComputer
    from core.rls import bypass_rls

    # Final girişi PUBLIC axındır (tələbə hələ login olmayıb, aktiv-org RLS
    # konteksti yoxdur). Kompüter axtarışı ``organization``-a görə AÇIQ filtrlənir
    # (biletin org-u), ona görə RLS bypass ilə işlədirik — tenant sızması yoxdur.
    if mac_enforcement_active():
        client_mac = resolve_client_mac(request)
        if client_mac is None:
            logger.warning("resolve_room_computer: müştəri MAC-ı tapılmadı — kompüter uyğunlaşdırılmadı.")
            return None, None
        with bypass_rls():
            comp = (
                ExamRoomComputer.objects.filter(organization=organization, is_active=True, mac_address=client_mac)
                .select_related("room")
                .first()
            )
        return (comp.room, comp) if comp else (None, None)

    client_text = get_client_ip(request)
    try:
        client_ip = ipaddress.ip_address(client_text)
    except ValueError:
        logger.warning("resolve_room_computer: müştəri IP-si oxunmadı (%r).", client_text)
        return None, None

    # QEYD: ``ip_address`` GenericIPAddressField (postgres ``inet``) — boş dəyər
    # NULL kimi saxlanır, "" YOX. inet sütununu "" ilə müqayisə etmək bütün
    # sətirləri düşürür, ona görə yalnız ``isnull=False`` filtri işlədilir.
    with bypass_rls():
        computers = list(
            ExamRoomComputer.objects.filter(
                organization=organization, is_active=True, ip_address__isnull=False
            ).select_related("room")
        )
    for comp in computers:
        try:
            if ipaddress.ip_address(comp.ip_address) == client_ip:
                return comp.room, comp
        except ValueError:
            logger.warning("resolve_room_computer: kompüter IP-si yanlış formatdadır, ötürülür: %r", comp.ip_address)
            continue
    return None, None


__all__ = [
    "exam_room_isolation_allowed",
    "final_exam_access_allowed",
    "get_client_ip",
    "mac_enforcement_active",
    "org_computer_access_allowed",
    "resolve_client_mac",
    "resolve_room_computer",
    "room_ip_access_allowed",
]
