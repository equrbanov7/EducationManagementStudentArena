"""final_center paketi — imtahan zalı + kompüter/MAC administrasiyası.

Bu servis YALNIZ zal infrastrukturunu (zal özü + zaldakı fiziki kompüterlərin
MAC/IP qeydləri) idarə edir. İcazə ``can_manage_exam_rooms`` (superadmin, yaxud
superadminin bayraqla həvalə etdiyi istifadəçi) view qatında yoxlanır.

Təhlükəsizlik qeydi (``exam_center_gate.py``): MAC HTTP sorğusu ilə serverə
çatmır — giriş məhdudiyyəti ``ip_address`` üzərindən tətbiq olunur; MAC etibarlı
identifikasiya sahəsidir.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext

from apps.exams.models import ExamRoom, ExamRoomComputer


class RoomAdminError(ValueError):
    """İstifadəçiyə göstərilə bilən (lokalizə olunmuş) zal-admin xətası."""


def _clean_ip(raw: str) -> str:
    """IP-ni validasiya edir (boş buraxıla bilər). Yanlışdırsa xəta atır."""
    import ipaddress

    value = (raw or "").strip()
    if not value:
        return ""
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "IP ünvanı düzgün deyil: %(ip)s") % {"ip": value}
        ) from exc
    return value


def _normalize_mac_or_error(raw: str) -> str:
    try:
        return ExamRoomComputer.normalize_mac(raw)
    except ValueError as exc:
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "MAC ünvanı düzgün deyil: %(mac)s") % {"mac": (raw or "").strip()}
        ) from exc


def _coerce_seat(raw) -> int | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        seat = int(value)
    except (TypeError, ValueError) as exc:
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Yer nömrəsi rəqəm olmalıdır: %(seat)s") % {"seat": value}
        ) from exc
    if seat <= 0:
        raise RoomAdminError(pgettext("exams.final_center.room_admin", "Yer nömrəsi müsbət olmalıdır."))
    return seat


def _ensure_mac_free_in_org(room: ExamRoom, mac_norm: str, *, exclude_pk=None) -> None:
    """MAC bu təşkilatın BAŞQA zalında qeydlidirsə, zalın adını deyən xəta atır.

    Fiziki kompüter eyni anda bir zaldadır — MAC başqa zalda tapılırsa bu, demək
    olar həmişə admin səhvidir («əlavə etmişəm, amma siyahıda görmürəm»
    şikayətinin klassik səbəbi: qeyd başqa zalda/təşkilat seçimində qalıb).
    """
    clash = (
        ExamRoomComputer.objects.filter(organization_id=room.organization_id, mac_address=mac_norm)
        .exclude(room=room)
        .select_related("room")
    )
    if exclude_pk:
        clash = clash.exclude(pk=exclude_pk)
    other = clash.first()
    if other is not None:
        raise RoomAdminError(
            pgettext(
                "exams.final_center.room_admin",
                "Bu MAC artıq «%(room)s» zalında qeydlidir (%(label)s). Kompüteri əvvəlcə oradan silin və ya redaktə edin.",
            )
            % {"room": other.room.name, "label": other.label}
        )


def add_computer(
    *, room: ExamRoom, label: str, mac: str, seat_number=None, ip_address: str = "", notes: str = "", user=None
) -> ExamRoomComputer:
    """Zala bir kompüter əlavə edir (MAC normalizə + dublikat yoxlaması)."""
    label = (label or "").strip()
    if not label:
        raise RoomAdminError(pgettext("exams.final_center.room_admin", "Kompüter adı boş ola bilməz."))
    mac_norm = _normalize_mac_or_error(mac)
    ip_norm = _clean_ip(ip_address)
    seat = _coerce_seat(seat_number)

    base = ExamRoomComputer.objects.filter(room=room)
    if base.filter(mac_address=mac_norm).exists():
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Bu MAC artıq bu zalda qeydlidir: %(mac)s") % {"mac": mac_norm}
        )
    _ensure_mac_free_in_org(room, mac_norm)
    if base.filter(label__iexact=label).exists():
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Bu adla kompüter artıq var: %(label)s") % {"label": label}
        )
    if seat is not None and base.filter(seat_number=seat).exists():
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Bu yer nömrəsi artıq tutulub: %(seat)s") % {"seat": seat}
        )

    return ExamRoomComputer.objects.create(
        organization_id=room.organization_id,
        room=room,
        label=label,
        mac_address=mac_norm,
        ip_address=ip_norm or None,
        seat_number=seat,
        notes=(notes or "").strip(),
        created_by=user if getattr(user, "pk", None) else None,
    )


def update_computer(
    *,
    computer: ExamRoomComputer,
    label: str,
    mac: str,
    seat_number=None,
    ip_address: str = "",
    notes: str = "",
    is_active=None,
) -> ExamRoomComputer:
    """Mövcud kompüter qeydini yeniləyir (dublikat yoxlaması özündən başqa)."""
    label = (label or "").strip()
    if not label:
        raise RoomAdminError(pgettext("exams.final_center.room_admin", "Kompüter adı boş ola bilməz."))
    mac_norm = _normalize_mac_or_error(mac)
    ip_norm = _clean_ip(ip_address)
    seat = _coerce_seat(seat_number)

    siblings = ExamRoomComputer.objects.filter(room=computer.room).exclude(pk=computer.pk)
    if siblings.filter(mac_address=mac_norm).exists():
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Bu MAC artıq bu zalda qeydlidir: %(mac)s") % {"mac": mac_norm}
        )
    _ensure_mac_free_in_org(computer.room, mac_norm, exclude_pk=computer.pk)
    if siblings.filter(label__iexact=label).exists():
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Bu adla kompüter artıq var: %(label)s") % {"label": label}
        )
    if seat is not None and siblings.filter(seat_number=seat).exists():
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Bu yer nömrəsi artıq tutulub: %(seat)s") % {"seat": seat}
        )

    computer.label = label
    computer.mac_address = mac_norm
    computer.ip_address = ip_norm or None
    computer.seat_number = seat
    computer.notes = (notes or "").strip()
    if is_active is not None:
        computer.is_active = bool(is_active)
    computer.save()
    return computer


def delete_room(*, room: ExamRoom) -> None:
    """Zalı silir. Oturum tarixçəsi olan zal SİLİNMİR (audit qorunur) —
    əvəzində deaktiv edilməlidir. Kompüter qeydləri zalla birgə silinir."""
    if room.sessions.exists():
        raise RoomAdminError(
            pgettext(
                "exams.final_center.room_admin",
                "«%(room)s» zalının oturum tarixçəsi var — silinə bilməz. Zalı deaktiv edin.",
            )
            % {"room": room.name}
        )
    room.delete()


@transaction.atomic
def bulk_add_computers(*, room: ExamRoom, text: str, user=None) -> tuple[int, list[str]]:
    """Sətir-sətir kompüter əlavə edir.

    Format (hər sətir): ``AD, MAC[, YER][, IP]`` — vergül və ya tab ilə.
    Ad və MAC məcburidir; yer nömrəsi və IP seçimlidir. Qalan sahələr
    məzmununa görə avtomatik tanınır (nöqtə/iki-nöqtə olan token = IP,
    sırf rəqəm = yer nömrəsi), ona görə sıra çevik saxlanır və IP boş
    buraxılanda («AD, MAC, YER») xəta vermir. Boş/``#``-şərh sətirləri
    ötürülür. Uğursuz sətirlər ATLANIR və mesajları qaytarılır (qismən
    uğur). Yaradılan sayı + xəta siyahısı qaytarır.
    """
    created = 0
    errors: list[str] = []
    for index, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Boş tokenlər buraxılır ki, «AD, MAC, , YER» kimi boş IP-slotu olan
        # köhnə sətirlər də pozisiya sürüşməsi yaratmasın.
        parts = [p.strip() for p in line.replace("\t", ",").split(",") if p.strip()]
        if len(parts) < 2:
            errors.append(pgettext("exams.final_center.room_admin", "Sətir %(n)s: ad və MAC lazımdır.") % {"n": index})
            continue
        label, mac = parts[0], parts[1]
        seat = None
        ip_address = ""
        # Qalan (seçimli) tokenləri məzmununa görə təsnif et: IP-də nöqtə
        # (IPv4) və ya iki nöqtə (IPv6) olur, yer nömrəsi isə sırf rəqəmdir.
        for token in parts[2:]:
            if "." in token or ":" in token:
                if not ip_address:
                    ip_address = token
            elif seat is None:
                seat = token
            elif not ip_address:
                ip_address = token
        try:
            add_computer(room=room, label=label, mac=mac, seat_number=seat, ip_address=ip_address, user=user)
            created += 1
        except RoomAdminError as exc:
            errors.append(pgettext("exams.final_center.room_admin", "Sətir %(n)s: %(err)s") % {"n": index, "err": exc})
    return created, errors


__all__ = [
    "RoomAdminError",
    "add_computer",
    "bulk_add_computers",
    "delete_room",
    "update_computer",
]
