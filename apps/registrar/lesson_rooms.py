"""Dərs otağı (korpus → otaq) — jurnal modalı üçün seçimlər və həlli.

``journal_extras.py`` modul-ölçü büdcəsinə görə bu konsern ayrıca modula
çıxarılıb; ictimai adlar ``journal_extras``-dan re-eksport olunur.

Otaq reyestri təşkilata məxsusdur: ``organizations.Organization.exam_rooms``
(yəni ``exams.ExamRoom``). REVERSE accessor ilə oxunur — beləcə registrar → exams
Python idxal asılılığı YARANMIR (modul-sərhəd gate-i). "Korpus" ayrıca model
DEYİL: otağın öz ``building`` sahəsidir, ona görə UI-da korpus sadəcə otaq
siyahısını daraldan süzgəcdir və POST-a yalnız otaq gedir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import pgettext

#: legacy_rooms fazası / seed_qku_campuses_rooms.py ilə eyni prefiks.
LEGACY_ROOM_CODE_PREFIX = "myedu-room-"

#
# Otaq reyestri təşkilata məxsusdur: ``organizations.Organization.exam_rooms``
# (yəni ``exams.ExamRoom``). Buradan REVERSE accessor ilə oxunur — beləcə
# registrar → exams Python idxal asılılığı yaranmır (modul-sərhəd gate-i).
# "Korpus" ayrıca model DEYİL: otağın öz ``building`` sahəsidir, ona görə UI-da
# korpus sadəcə otaq siyahısını daraldan süzgəcdir.


def _disambiguation_texts(room: dict) -> dict:
    """Bir otağın fərqləndirici mətnləri: korpus, mərtəbə, tutum, kod (boş sahə yoxdur)."""
    ctx = "registrar.journal_room"
    texts = {}
    if room["building"]:
        texts["building"] = pgettext(ctx, "korpus %(value)s") % {"value": room["building"]}
    if room["floor"]:
        texts["floor"] = pgettext(ctx, "mərtəbə %(value)s") % {"value": room["floor"]}
    if room["capacity"]:
        texts["capacity"] = pgettext(ctx, "%(value)s yer") % {"value": room["capacity"]}
    if room["code"]:
        texts["code"] = pgettext(ctx, "kod %(value)s") % {"value": room["code"]}
    return texts


def _disambiguate(rooms: list[dict]) -> None:
    """Eyni etiketli otaqlara (məs. bir korpusda iki «102») fərqləndirici şəkilçi əlavə edir (QA-1 F5).

    Yalnız toqquşan etiketlər dəyişir (təkrarsız «102» olduğu kimi qalır). Qrupu ayıran sahələr
    (korpus → mərtəbə → tutum → kod) qrup tam ayrılana qədər ardıcıl əlavə olunur; sonda da eyni
    qalanlara sıra nömrəsi qoyulur — iki otaq HEÇ VAXT eyni görünmür."""
    groups: dict[str, list[dict]] = {}
    for room in rooms:
        groups.setdefault(room["name"].casefold(), []).append(room)
    for group in (members for members in groups.values() if len(members) > 1):
        texts = {id(room): _disambiguation_texts(room) for room in group}
        suffixes = {id(room): [] for room in group}
        for kind in ("building", "floor", "capacity", "code"):
            if len({texts[id(room)].get(kind, "") for room in group}) <= 1:
                continue  # bu sahə qrupu ayırmır
            for room in group:
                if texts[id(room)].get(kind):
                    suffixes[id(room)].append(texts[id(room)][kind])
            if len({tuple(suffixes[id(room)]) for room in group}) == len(group):
                break
        seen: dict[str, int] = {}
        for room in group:
            label = room["name"] + (" · " + ", ".join(suffixes[id(room)]) if suffixes[id(room)] else "")
            seen[label] = seen.get(label, 0) + 1
            room["name"] = label if seen[label] == 1 else f"{label} #{seen[label]}"


def lesson_room_choices(offering):
    """Dərs modalı üçün otaqlar — təşkilatın AKTİV otaqları, korpusu ilə birlikdə.

    Qaytarır ``[{"id", "name", "building", "capacity"}]``; JS seçilmiş korpusa görə
    süzür. Siyahı kiçikdir (universitetdə onlarla/yüzlərlə otaq), ona görə modala
    JSON kimi yerləşdirilir — ayrıca AJAX kaskadı və gözləmə olmur. Eyni etiketli otaqlar
    (iki «102») korpus / mərtəbə / tutum şəkilçisi ilə ayırd edilir (``_disambiguate``)."""
    rooms = offering.organization.exam_rooms.filter(is_active=True).order_by("building", "name", "code")
    out = []
    for room in rooms:
        label = (room.name or "").strip() or (room.code or "").strip() or str(room.pk)
        code = (room.code or "").strip()
        # Legacy açar («myedu-room-<id>») texniki kimlikdir, müəllimə göstərilmir.
        if code and code != label and not code.startswith(LEGACY_ROOM_CODE_PREFIX):
            label = f"{label} ({code})"
        out.append(
            {
                "id": str(room.pk),
                "name": label,
                "building": (room.building or "").strip(),
                "capacity": room.capacity or 0,
                "floor": (room.floor or "").strip(),
                "code": "" if code.startswith(LEGACY_ROOM_CODE_PREFIX) else code,
            }
        )
    _disambiguate(out)
    for room in out:  # köməkçi sahələr cavabda yoxdur (JS-in oxuduğu forma dəyişmir)
        room.pop("floor", None)
        room.pop("code", None)
    return out


def lesson_building_choices(rooms):
    """Otaq siyahısından korpus seçimləri — təkrarsız, əlifba sırası ilə."""
    return sorted({room["building"] for room in rooms if room["building"]})


def resolve_lesson_room(organization, room_id):
    """POST-dan gələn otaq id-sini TƏŞKİLAT daxilində həll edir.

    Fail-closed: boş / naməlum / deaktiv / BAŞQA təşkilatın otağı → ``None``
    (otaq seçilməyib). Beləcə başqa tenant-ın otağını dərsə bağlamaq cəhdi
    səssizcə bağlanır."""
    room_id = (room_id or "").strip()
    if not room_id:
        return None
    try:
        return organization.exam_rooms.filter(pk=room_id, is_active=True).first()
    except (ValueError, TypeError, ValidationError):  # yararsız UUID mətni
        return None


def slot_room_ids(organization, texts) -> dict:
    """Cədvəl slotlarının sərbəst mətnli otağı (``ScheduleSlot.room``) → reyestr otağının id-si, BİR sorğu ilə.

    ``journal_activation.resolve_slot_room`` qaydası: ad və ya kod, böyük/kiçik hərf fərqsiz, yalnız
    TƏK dəqiq uyğunluq; tapılmasa və ya bir neçə otaq uyğun gəlsə — açar yoxdur (çağıran yaddaşa keçir)."""
    texts = {(text or "").strip() for text in texts} - {""}
    if not texts:
        return {}
    query = Q()
    for text in texts:
        query |= Q(name__iexact=text) | Q(code__iexact=text)
    rooms = list(organization.exam_rooms.filter(is_active=True).filter(query).values_list("pk", "name", "code"))
    found = {}
    for text in texts:
        key = text.upper()
        matches = [pk for pk, name, code in rooms if (name or "").upper() == key or (code or "").upper() == key]
        if len(matches) == 1:
            found[text] = str(matches[0])
    return found


def remembered_rooms(offering) -> dict:
    """Müəllimin bu açılış üçün əvvəl seçdiyi otaqlar — «Yeni dərs» modalının defoltu (sahib 2026-09-27).

    «Müəllim bir dəfə korpus və otağı seçibsə, bu qrupun eyni dərs günü üçün yadda qalsın,
    gələn dəfə avtomatik dolu görünsün; istəsə dəyişə bilər.» Ayrıca «yaddaş» cədvəli YOXDUR —
    mənbə dərslərin özüdür (``Lesson.room``), ona görə yaddaş hər dəyişiklikdə təbii yenilənir.

    Qaytarır ``{"<növ>|<həftə günü 1..7>": room_id, "<növ>": room_id}`` — hər açar üçün ƏN SON
    dərsin otağı (yalnız hələ aktiv otaqlar). JS əvvəl «növ + gün»ü, tapılmasa «növ»ü götürür."""
    rows = (
        offering.lessons.filter(room__isnull=False, room__is_active=True)
        .order_by("-date", "-created_at")
        .values_list("kind", "date", "room_id")
    )
    memory: dict = {}
    for kind, day, room_id in rows:
        memory.setdefault(f"{kind}|{day.isoweekday()}", str(room_id))
        memory.setdefault(kind, str(room_id))
    return memory


def remembered_room(offering, kind, day):
    """Cədvəldən «Aktivləşdir» ilə açılan dərs üçün: slotun otağı tapılmayanda eyni növ + gün yaddaşı."""
    room_id = remembered_rooms(offering).get(f"{kind}|{day.isoweekday()}")
    return resolve_lesson_room(offering.organization, room_id) if room_id else None
