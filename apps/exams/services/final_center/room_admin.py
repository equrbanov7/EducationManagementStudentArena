"""final_center paketi — imtahan zalı + kompüter/MAC administrasiyası.

Bu servis YALNIZ zal infrastrukturunu (zal özü + zaldakı fiziki kompüterlərin
MAC/IP qeydləri) idarə edir. İcazə ``can_manage_exam_rooms`` (superadmin, yaxud
superadminin bayraqla həvalə etdiyi istifadəçi) view qatında yoxlanır.

Təhlükəsizlik qeydi (``exam_center_gate.py``): brauzer MAC göndərmir — server tələbənin IP-sini
ARP agentinə soruşub MAC-ı özü tapır və bu cədvəldəki qeydlə (normallaşdırılmış formada) tutuşdurur
(``EXAM_CLIENT_MAC_RESOLUTION=arp_agent``). Ona görə admin daxiletməsi sərt yoxlanır: səhv MAC həmin
kompüterdə tələbəni bloklayır (2026-10-02, EXAMQA R3/R4).
"""

from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import pgettext

from apps.exams.models import ExamRoom, ExamRoomComputer


class RoomAdminError(ValueError):
    """İstifadəçiyə göstərilə bilən (lokalizə olunmuş) zal-admin xətası.

    2026-10-21 (sahib: «səhv edəndə səhvi göstərmir, … modalda göstərsin»): xəta hansı FORM SAHƏSİNƏ aiddirsə
    ``field`` onu deyir (``label`` / ``mac_address`` / ``ip_address`` / ``seat_number`` — dialoqun input adları),
    ``errors`` isə ``{sahə: mesaj}`` xəritəsidir (ModelForm-un bütün xətaları). ``str(exc)`` əvvəlki kimi əsas
    mesajdır — köhnə çağıranlar dəyişmir.
    """

    def __init__(self, message="", field=None, errors=None):
        # Bütün arqumentlər `super()`-ə ötürülür (pickle/copy — B042); mətn `__str__`-dən gəlir.
        super().__init__(message, field, errors)
        self.field = field
        self.errors = {str(key): str(value) for key, value in (errors or {}).items()}
        if field and field not in self.errors:
            self.errors[field] = str(message)

    def __str__(self):
        return str(self.args[0]) if self.args else ""


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
            pgettext("exams.final_center.room_admin", "IP ünvanı düzgün deyil: %(ip)s") % {"ip": value},
            field="ip_address",
        ) from exc
    return value


#: 2026-10-02 (EXAMQA R3): admin daxiletməsində yalnız hex + adi ayırıcılar. `normalize_mac` hex olmayan
#: simvolları SƏSSİZCƏ atırdı («AA:BB:CC:DD:EE:GZ1» → başqa MAC) — səhv qeydiyyat tələbəni bloklayardı.
_MAC_INPUT_RE = re.compile(r"^[0-9A-Fa-f:\-.\s]+$")


def _normalize_mac_or_error(raw: str) -> str:
    value = (raw or "").strip()
    invalid = RoomAdminError(
        pgettext("exams.final_center.room_admin", "MAC ünvanı düzgün deyil: %(mac)s") % {"mac": value},
        field="mac_address",
    )
    if not value or not _MAC_INPUT_RE.match(value):
        raise invalid
    try:
        mac = ExamRoomComputer.normalize_mac(value)
    except ValueError as exc:
        raise invalid from exc
    # Sıfır, yayım (FF…) və multicast (1-ci oktetin ən kiçik biti) heç bir şəbəkə kartına aid deyil.
    if mac in {"00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"} or int(mac[:2], 16) & 1:
        raise RoomAdminError(
            pgettext(
                "exams.final_center.room_admin",
                "Bu MAC ünvanı kompüterə aid ola bilməz (sıfır, yayım və ya multicast): %(mac)s",
            )
            % {"mac": mac},
            field="mac_address",
        )
    return mac


def _coerce_seat(raw) -> int | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        seat = int(value)
    except (TypeError, ValueError) as exc:
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Yer nömrəsi rəqəm olmalıdır: %(seat)s") % {"seat": value},
            field="seat_number",
        ) from exc
    if seat <= 0:
        raise RoomAdminError(
            pgettext("exams.final_center.room_admin", "Yer nömrəsi müsbət olmalıdır."), field="seat_number"
        )
    return seat


def _same_mac_q(mac_norm: str) -> Q:
    """Eyni MAC-ın istənilən saxlanmış yazılışı (EXAMQA R2, 2026-10-02).

    Köhnə qeydlər «aa:bb:…», «AA-BB-…», «AABBCC…» kimi saxlanıla bilir; dəqiq bərabərlik onları tutmurdu →
    eyni kompüter ikinci dəfə qeydə alına bilirdi (gate isə normallaşdırılmış müqayisədə iki qeyd tapırdı).
    """
    hexes = mac_norm.replace(":", "")
    pairs = [hexes[i : i + 2] for i in range(0, 12, 2)]
    variants = {":".join(pairs), "-".join(pairs), hexes, ".".join(hexes[i : i + 4] for i in range(0, 12, 4))}
    query = Q()
    for variant in variants:
        query |= Q(mac_address__iexact=variant)
    return query


def _ensure_mac_free_in_org(room: ExamRoom, mac_norm: str, *, exclude_pk=None) -> None:
    """MAC bu təşkilatın BAŞQA zalında qeydlidirsə, zalın adını deyən xəta atır.

    Fiziki kompüter eyni anda bir zaldadır — MAC başqa zalda tapılırsa bu, demək
    olar həmişə admin səhvidir («əlavə etmişəm, amma siyahıda görmürəm»
    şikayətinin klassik səbəbi: qeyd başqa zalda/təşkilat seçimində qalıb).
    """
    clash = (
        ExamRoomComputer.objects.filter(_same_mac_q(mac_norm), organization_id=room.organization_id)
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
            % {"room": other.room.name, "label": other.label},
            field="mac_address",
        )


def _ensure_ip_free_in_org(room: ExamRoom, ip_norm: str, *, exclude_pk=None) -> None:
    """IP təşkilatda YALNIZ bir kompüterə aiddir (2026-10-21).

    Giriş qapısı (``exam_center_gate``) zalı və kompüteri IP ilə həll edir — eyni IP iki qeyddə olanda hansı
    kompüterin (və hansı zalın) nəzərdə tutulduğu bilinmir. Əvvəl bu yoxlanmırdı və səssizcə qeydə alınırdı.
    """
    if not ip_norm:
        return
    clash = ExamRoomComputer.objects.filter(organization_id=room.organization_id, ip_address=ip_norm)
    if exclude_pk:
        clash = clash.exclude(pk=exclude_pk)
    other = clash.select_related("room").first()
    if other is not None:
        raise RoomAdminError(
            pgettext(
                "exams.final_center.room_admin",
                "Bu IP artıq «%(room)s» zalında «%(label)s» kompüterinə verilib: %(ip)s",
            )
            % {"room": other.room.name, "label": other.label, "ip": ip_norm},
            field="ip_address",
        )


def _validate_computer(room: ExamRoom, *, label, mac, seat_number, ip_address, exclude_pk=None):
    """Bütün sahələri yoxlayır və xətaları SAHƏ-SAHƏ yığır (bir dəfəyə hamısı görünsün).

    Qaytarır ``(label, mac_norm, ip_norm, seat)``; xəta varsa ``RoomAdminError(errors={sahə: mesaj})``
    — əsas mesaj sahələrin dialoqdakı sırası ilə (ad → yer → MAC → IP) BİRİNCİ xətadır.
    """
    errors: dict[str, str] = {}
    label = (label or "").strip()
    mac_norm = ip_norm = ""
    seat = None
    if not label:
        errors["label"] = pgettext("exams.final_center.room_admin", "Kompüter adı boş ola bilməz.")
    for field, check in (
        ("mac_address", lambda: _normalize_mac_or_error(mac)),
        ("ip_address", lambda: _clean_ip(ip_address)),
        ("seat_number", lambda: _coerce_seat(seat_number)),
    ):
        try:
            value = check()
        except RoomAdminError as exc:
            errors[field] = str(exc)
            continue
        if field == "mac_address":
            mac_norm = value
        elif field == "ip_address":
            ip_norm = value
        else:
            seat = value

    siblings = ExamRoomComputer.objects.filter(room=room)
    if exclude_pk:
        siblings = siblings.exclude(pk=exclude_pk)
    if mac_norm:
        try:
            if siblings.filter(_same_mac_q(mac_norm)).exists():
                raise RoomAdminError(
                    pgettext("exams.final_center.room_admin", "Bu MAC artıq bu zalda qeydlidir: %(mac)s")
                    % {"mac": mac_norm}
                )
            _ensure_mac_free_in_org(room, mac_norm, exclude_pk=exclude_pk)
        except RoomAdminError as exc:
            errors["mac_address"] = str(exc)
    if ip_norm:
        try:
            _ensure_ip_free_in_org(room, ip_norm, exclude_pk=exclude_pk)
        except RoomAdminError as exc:
            errors["ip_address"] = str(exc)
    if label and siblings.filter(label__iexact=label).exists():
        errors["label"] = pgettext("exams.final_center.room_admin", "Bu adla kompüter artıq var: %(label)s") % {
            "label": label
        }
    if seat is not None and siblings.filter(seat_number=seat).exists():
        errors["seat_number"] = pgettext("exams.final_center.room_admin", "Bu yer nömrəsi artıq tutulub: %(seat)s") % {
            "seat": seat
        }
    if errors:
        first = next(errors[key] for key in _COMPUTER_FIELD_ORDER if key in errors)
        raise RoomAdminError(first, errors=errors)
    return label, mac_norm, ip_norm, seat


#: Dialoqdakı sahə sırası — əsas (xülasə) mesaj bu sıra ilə seçilir.
_COMPUTER_FIELD_ORDER = ("label", "seat_number", "mac_address", "ip_address")

#: Unikal məhdudiyyət → sahə (yoxlamadan SONRA paralel yazı yarışında DB xətası).
_CONSTRAINT_FIELDS = {
    "uniq_room_computer_seat": "seat_number",
    "uniq_room_computer_mac": "mac_address",
    "uniq_room_computer_label": "label",
}


def _save_or_field_error(save, *, label, mac_norm, seat):
    """``save()``-i savepoint-də icra edir; unikal məhdudiyyət pozulsa SAHƏ xətası atır (500 yox)."""
    try:
        with transaction.atomic():
            return save()
    except IntegrityError as exc:
        text = str(exc)
        field = next((name for key, name in _CONSTRAINT_FIELDS.items() if key in text), None)
        messages = {
            "seat_number": pgettext("exams.final_center.room_admin", "Bu yer nömrəsi artıq tutulub: %(seat)s")
            % {"seat": seat},
            "mac_address": pgettext("exams.final_center.room_admin", "Bu MAC artıq bu zalda qeydlidir: %(mac)s")
            % {"mac": mac_norm},
            "label": pgettext("exams.final_center.room_admin", "Bu adla kompüter artıq var: %(label)s")
            % {"label": label},
        }
        if field is None:
            raise
        raise RoomAdminError(messages[field], field=field) from exc


def add_computer(
    *, room: ExamRoom, label: str, mac: str, seat_number=None, ip_address: str = "", notes: str = "", user=None
) -> ExamRoomComputer:
    """Zala bir kompüter əlavə edir (MAC normalizə + dublikat yoxlaması)."""
    label, mac_norm, ip_norm, seat = _validate_computer(
        room, label=label, mac=mac, seat_number=seat_number, ip_address=ip_address
    )
    return _save_or_field_error(
        lambda: ExamRoomComputer.objects.create(
            organization_id=room.organization_id,
            room=room,
            label=label,
            mac_address=mac_norm,
            ip_address=ip_norm or None,
            seat_number=seat,
            notes=(notes or "").strip(),
            created_by=user if getattr(user, "pk", None) else None,
        ),
        label=label,
        mac_norm=mac_norm,
        seat=seat,
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
    label, mac_norm, ip_norm, seat = _validate_computer(
        computer.room,
        label=label,
        mac=mac,
        seat_number=seat_number,
        ip_address=ip_address,
        exclude_pk=computer.pk,
    )
    computer.label = label
    computer.mac_address = mac_norm
    computer.ip_address = ip_norm or None
    computer.seat_number = seat
    computer.notes = (notes or "").strip()
    if is_active is not None:
        computer.is_active = bool(is_active)
    _save_or_field_error(computer.save, label=label, mac_norm=mac_norm, seat=seat)
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
def bulk_add_computers(*, room: ExamRoom, text: str, user=None, failed_lines=None) -> tuple[int, list[str]]:
    """Sətir-sətir kompüter əlavə edir.

    Format (hər sətir): ``AD, MAC[, YER][, IP]`` — vergül və ya tab ilə.
    Ad və MAC məcburidir; yer nömrəsi və IP seçimlidir. Qalan sahələr
    məzmununa görə avtomatik tanınır (nöqtə/iki-nöqtə olan token = IP,
    sırf rəqəm = yer nömrəsi), ona görə sıra çevik saxlanır və IP boş
    buraxılanda («AD, MAC, YER») xəta vermir. Boş/``#``-şərh sətirləri
    ötürülür. Uğursuz sətirlər ATLANIR və mesajları qaytarılır (qismən
    uğur). Yaradılan sayı + xəta siyahısı qaytarır.

    ``failed_lines`` (seçimli siyahı) verilibsə uğursuz sətirlərin ÖZÜ ora yazılır — dialoq onları
    textarea-da saxlayır ki, istifadəçi yalnız səhv sətirləri düzəldib yenidən göndərsin (2026-10-21).
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
            if failed_lines is not None:
                failed_lines.append(line)
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
            if failed_lines is not None:
                failed_lines.append(line)
    return created, errors


__all__ = [
    "RoomAdminError",
    "add_computer",
    "bulk_add_computers",
    "delete_room",
    "update_computer",
]
