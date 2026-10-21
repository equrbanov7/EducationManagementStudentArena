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

Açar (sahib 2026-10-21): «Sistem tənzimləmələri» → ``exam.hall_computer_check``
(:func:`hall_computer_check_enabled`). Yandırılıbsa (defolt) yuxarıdakı hər şey
əvvəlki kimidir. Söndürüləndə HEÇ BİR kompüter/MAC/IP-allowlist tələbi yoxdur —
``final_exam_access_allowed`` / ``room_ip_access_allowed`` /
``org_computer_access_allowed`` həmişə ``True``; ``resolve_room_computer`` isə
yalnız MƏLUMAT üçün işləyir (org-da qeydli kompüter varsa və müştəri ona
uyğundursa zal qaytarılır — gözləmə otağı / zal monitoru işləməyə davam edir;
uyğun deyilsə rədd YOX, «qeydli kompüter yoxdur» yolu: birbaşa başlama).
Universitet şəbəkəsi qaydası (``exam_network``) bu açardan ASILI DEYİL.

SƏRT REJİM (sahib 2026-10-21, ikinci qərar): «Hansı kompüterlərin MAC ünvanlarını əlavə edəcəyəmsə, ancaq
onlardan midterm və final səhifəsinə girmək mümkün olsun; digər halda xəbərdarlıq mesajı göstərilsin. Sistem
tənzimləmələrindən açmadığım müddətcə heç kim kənar kompüterlə o səhifəni belə aça bilməsin.» → açar
YANDIRILIBSA (defolt) zal səhifələri (giriş GET/POST, gözləmə otağı, state/begin/cancel) YALNIZ AKTİV qeydli
``ExamRoomComputer``-dən açılır (:func:`ensure_hall_computer`; MAC rejimində ARP MAC-ı, əks halda IP). Qeydsiz
kompüter → :class:`HallComputerDenied` → 403 xəbərdarlıq səhifəsi (giriş forması YOXDUR) + bu kompüterin öz
ünvanı (:func:`client_address_diagnostic`). Org-da HEÇ qeydli kompüter yoxdursa da bloklanır (əvvəlki «qeyd
yoxdursa açıq» istisnası sərt rejimdə YOXDUR). Sınaq cəhdi və mərkəz əməkdaşı səhifələri bu qapıdan keçmir.
"""

import ipaddress
import json
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


def hall_computer_check_enabled() -> bool:
    """Zal kompüteri (MAC/IP) yoxlaması aktivdirmi — «Sistem tənzimləmələri» açarı (defolt: bəli)."""
    from core.runtime_settings_exam_center import hall_computer_check

    return hall_computer_check()


def mac_enforcement_active() -> bool:
    """Kompüter yoxlamaları MAC (ARP agenti) rejimindədirmi?"""
    return getattr(settings, "EXAM_CLIENT_MAC_RESOLUTION", "off") == "arp_agent"


_UNSET = object()


def resolve_client_mac(request) -> str | None:
    """Müştəri IP-sinin MAC-ı (yalnız MAC rejimi) — sorğu başına BİR dəfə ARP agentinə müraciət.

    Sərt zal qapısı, diaqnostika və otaq yoxlaması eyni sorğuda MAC-ı bir neçə dəfə soruşur; nəticə
    ``request``-də yadda saxlanır (agent 0,5 s gözləmə ilə çağırılır).
    """
    cached = getattr(request, "_exam_client_mac", _UNSET) if request is not None else _UNSET
    if cached is not _UNSET:
        return cached
    mac = _lookup_client_mac(request)
    if request is not None:
        try:
            request._exam_client_mac = mac
        except AttributeError:
            pass
    return mac


def _lookup_client_mac(request) -> str | None:
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


# EXAMQA 2026-10-01: kanonik saxlanma formatı (``normalize_mac`` nəticəsi).
_CANONICAL_MAC_REGEX = r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$"


def _canonical_mac_or_none(raw) -> str | None:
    from apps.exams.models import ExamRoomComputer

    try:
        return ExamRoomComputer.normalize_mac(raw)
    except ValueError:
        return None


def _find_active_computer_by_mac(queryset, client_mac):
    """Aktiv kompüter queryset-ində ``client_mac``-a (kanonik) uyğun sətir və ya None.

    EXAMQA 2026-10-01: DB-də MAC formatı məcburi deyil (CHECK yoxdur) —
    servis qatı (``room_admin``) normallaşdırır, amma skript/shell/SQL ilə
    yazılmış köhnə sətirlər (``aa:bb:..``, ``AA-BB-..``) dəqiq müqayisədə
    heç vaxt uyğun gəlmir və qeydli kompüterdəki tələbə «icazə yoxdur»
    alırdı. Əvvəl indeksli dəqiq axtarış (normal yol, 1 sorğu); tapılmasa
    YALNIZ qeyri-kanonik sətirlər Python-da normallaşdırılıb müqayisə olunur.
    """
    exact = queryset.filter(mac_address=client_mac).first()
    if exact is not None:
        return exact
    for computer in queryset.exclude(mac_address__regex=_CANONICAL_MAC_REGEX):
        if _canonical_mac_or_none(computer.mac_address) == client_mac:
            return computer
    return None


def _log_unregistered_mac(where: str, request, client_mac: str) -> None:
    """Qeydsiz MAC rəddi — İKT zalda «bu kompüterin MAC-ı nədir» sualını loqdan cavablasın."""
    logger.warning(
        "%s: MAC %s (IP %s) aktiv qeydli kompüterlərdə yoxdur — giriş rədd edildi.",
        where,
        client_mac,
        get_client_ip(request),
    )


def get_client_ip(request) -> str:
    """Sorğunun müştəri IP-si (etibarlı proxy arxasında XFF-in SON üzvü).

    Nginx (2026-07-11 auditindən sonra) X-Forwarded-For-u client zəncirinə
    əlavə ETMİR — başlığı öz gördüyü peer ünvanı ilə OVERWRITE edir, yəni
    dəyər həmişə tək və nginx-ə məxsusdur. Son üzvü götürmək köhnə (append)
    konfiqurasiya ilə də geriyə-uyğundur: hər iki halda son üzv müştəri
    tərəfindən idarə oluna bilmir. İmtahan zalı kompüterləri nginx-ə birbaşa
    qoşulduğu üçün dəyər real zal IP-sidir.
    """
    from core.utils import get_client_ip as _core_client_ip

    # Parse məntiqi TƏK yerdədir (``core.utils.get_client_ip``) — 2026-09-02
    # audit, P2-6: eyni başlıq beş yerdə müstəqil oxunurdu.
    return _core_client_ip(request) or ""


def _allowed_entries():
    return [entry for entry in getattr(settings, "FINAL_EXAM_ALLOWED_IPS", []) if entry]


def final_exam_access_allowed(request) -> bool:
    """
    Final səhifəsinə bu sorğu buraxılsınmı?

    Boş allowlist → True (açıq rejim). Yanlış formatlı siyahı girişləri
    sorğunu bloklamır — sadəcə ötürülür və log-a yazılır ki, konfiq səhvi
    bütün imtahan zalını kilidləməsin.
    """
    if not hall_computer_check_enabled():
        return True
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
    * Zal kompüteri yoxlaması söndürülübsə (``exam.hall_computer_check``) → ``True``.
    """
    if not hall_computer_check_enabled():
        return True
    if mac_enforcement_active():
        raw_values = list(room.computers.filter(is_active=True).values_list("mac_address", flat=True))
        if not raw_values:
            return True
        # Köhnə/xam formatda saxlanmış MAC-lar da kanonik formaya gətirilir.
        mac_values = {_canonical_mac_or_none(value) for value in raw_values} - {None}
        client_mac = resolve_client_mac(request)
        if client_mac is None:
            logger.warning("room_access: müştəri MAC-ı tapılmadı — giriş rədd edildi.")
            return False
        if client_mac not in mac_values:
            _log_unregistered_mac("room_access", request, client_mac)
            return False
        return True

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

    if organization is None or not hall_computer_check_enabled():
        return True
    with bypass_rls():
        qs = ExamRoomComputer.objects.filter(organization=organization, is_active=True)
        if not qs.exists():
            # Sərt rejim (2026-10-21): qeydli kompüter yoxdursa giriş də YOXDUR.
            logger.warning(
                "org_computer_access: org=%s üçün aktiv qeydli zal kompüteri yoxdur — rədd.", organization.pk
            )
            return False
        if mac_enforcement_active():
            client_mac = resolve_client_mac(request)
            if client_mac is None:
                logger.warning("org_computer_access: müştəri MAC-ı tapılmadı — giriş rədd edildi.")
                return False
            if _find_active_computer_by_mac(qs, client_mac) is None:
                _log_unregistered_mac("org_computer_access", request, client_mac)
                return False
            return True
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


def resolve_room_computer(request, organization):
    """Müştəri sorğusundan ZALI və kompüteri həll et — ``(room, computer)`` və ya ``(None, None)``.

    Zal kompüteri yoxlaması söndürülübsə (``exam.hall_computer_check``) nəticə yalnız MƏLUMATDIR: org-da aktiv
    qeydli kompüter yoxdursa ARP agentinə də müraciət olunmur; uyğunsuzluq «rədd» kimi loglanmır. Çağıran
    ``(None, None)``-da mövcud «qeydli kompüter yoxdur» yolunu işlədir.
    """
    if hall_computer_check_enabled():
        return _resolve_room_computer(request, organization, log_misses=True)
    if organization is None or not _org_has_active_computers(organization):
        return None, None
    return _resolve_room_computer(request, organization, log_misses=False)


def _org_has_active_computers(organization) -> bool:
    from apps.exams.models import ExamRoomComputer
    from core.rls import bypass_rls

    with bypass_rls():
        return ExamRoomComputer.objects.filter(organization=organization, is_active=True).exists()


def _resolve_room_computer(request, organization, *, log_misses: bool):
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

    def _scope(queryset):
        # ``organization=None`` — giriş səhifəsinin GET-i (imtahan/org hələ bilinmir): istənilən org-un zalı.
        return queryset if organization is None else queryset.filter(organization=organization)

    # Final girişi PUBLIC axındır (tələbə hələ login olmayıb, aktiv-org RLS
    # konteksti yoxdur). Kompüter axtarışı ``organization``-a görə AÇIQ filtrlənir
    # (biletin org-u), ona görə RLS bypass ilə işlədirik — tenant sızması yoxdur.
    if mac_enforcement_active():
        client_mac = resolve_client_mac(request)
        if client_mac is None:
            if log_misses:
                logger.warning("resolve_room_computer: müştəri MAC-ı tapılmadı — kompüter uyğunlaşdırılmadı.")
            return None, None
        with bypass_rls():
            comp = _find_active_computer_by_mac(
                _scope(ExamRoomComputer.objects.filter(is_active=True)).select_related("room"),
                client_mac,
            )
        if comp is None:
            if log_misses:
                _log_unregistered_mac("resolve_room_computer", request, client_mac)
            return None, None
        return comp.room, comp

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
            # Sərt zal qapısı hər zal sorğusunda işləyir — sətirlər DB-də müştəri IP-si ilə süzülür (inet bərabərliyi).
            _scope(ExamRoomComputer.objects.filter(is_active=True, ip_address=str(client_ip))).select_related("room")
        )
    for comp in computers:
        try:
            if ipaddress.ip_address(comp.ip_address) == client_ip:
                return comp.room, comp
        except ValueError:
            logger.warning("resolve_room_computer: kompüter IP-si yanlış formatdadır, ötürülür: %r", comp.ip_address)
            continue
    return None, None


class HallComputerDenied(Exception):
    """Sərt zal rejimi: sorğu aktiv qeydli zal kompüterindən gəlmir — 403 xəbərdarlıq səhifəsi/JSON."""


def registered_hall_computer(request, organization=None):
    """Müştəriyə uyğun AKTİV qeydli zal kompüteri (``organization`` verilməyibsə istənilən org) və ya ``None``.

    Eyni sorğuda tapılmış kompüter yadda saxlanır: gözləmə otağı əvvəl ümumi (``None``), sonra biletin org-u ilə
    yoxlayır — kompüter həmin org-dadırsa ikinci axtarış (RLS bypass + SELECT) edilmir.
    """
    cached = getattr(request, "_exam_hall_computer", None)
    if cached is not None and (organization is None or cached.organization_id == getattr(organization, "pk", None)):
        return cached
    computer = _resolve_room_computer(request, organization, log_misses=True)[1]
    if computer is not None and request is not None:
        try:
            request._exam_hall_computer = computer
        except AttributeError:
            pass
    return computer


def hall_computer_gate_allows(request, organization=None) -> bool:
    """Sərt zal qapısı: açar söndürülübsə həmişə ``True``; yandırılıbsa yalnız qeydli aktiv kompüterdən."""
    if not hall_computer_check_enabled():
        return True
    return registered_hall_computer(request, organization) is not None


def ensure_hall_computer(request, organization=None) -> None:
    """Zal səhifələrinin ortaq qapısı — qeydsiz kompüterdə :class:`HallComputerDenied`.

    Çağırış yerləri: imtahan zalı giriş/gözləmə view-ları (``views/student/_center_common.ensure_hall_access``).
    Mərkəz (zal) cəhdinin take/nəticə səhifələri üçün də eyni funksiya çağırılmalıdır (sınaq cəhdi istisna) —
    ``final_device_guarded`` istisnanı 403 xəbərdarlıq səhifəsinə çevirir.
    """
    if not hall_computer_gate_allows(request, organization):
        raise HallComputerDenied()


_LAN_NETWORKS = tuple(
    ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def _is_lan_address(ip_text: str) -> bool:
    """RFC 1918 / ULA / loopback / link-local və ya ``INTERNAL_NETWORKS`` (universitet CIDR-ləri)."""
    try:
        parsed = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    if parsed.is_loopback or parsed.is_link_local or any(parsed in net for net in _LAN_NETWORKS):
        return True
    for entry in getattr(settings, "INTERNAL_NETWORKS", []) or []:
        try:
            if parsed in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_address_diagnostic(request) -> dict:
    """Xəbərdarlıq səhifəsi üçün YALNIZ müştərinin öz LAN ünvanı: ``{"ip": str, "mac": str}``.

    İP yalnız özəl/lokal şəbəkə ünvanıdırsa göstərilir (publik və ya server ünvanı YOX); MAC yalnız MAC
    rejimində ARP agentindən oxunur, oxunmayanda boş sətir.
    """
    ip_text = get_client_ip(request)
    shown_ip = ip_text if _is_lan_address(ip_text) else ""
    mac = resolve_client_mac(request) if mac_enforcement_active() else None
    return {"ip": shown_ip, "mac": mac or ""}


__all__ = [
    "HallComputerDenied",
    "client_address_diagnostic",
    "ensure_hall_computer",
    "final_exam_access_allowed",
    "hall_computer_gate_allows",
    "registered_hall_computer",
    "get_client_ip",
    "hall_computer_check_enabled",
    "mac_enforcement_active",
    "org_computer_access_allowed",
    "resolve_client_mac",
    "resolve_room_computer",
    "room_ip_access_allowed",
]
