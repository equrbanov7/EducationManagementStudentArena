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

#: legacy_rooms fazası / seed_qku_campuses_rooms.py ilə eyni prefiks.
LEGACY_ROOM_CODE_PREFIX = "myedu-room-"

#
# Otaq reyestri təşkilata məxsusdur: ``organizations.Organization.exam_rooms``
# (yəni ``exams.ExamRoom``). Buradan REVERSE accessor ilə oxunur — beləcə
# registrar → exams Python idxal asılılığı yaranmır (modul-sərhəd gate-i).
# "Korpus" ayrıca model DEYİL: otağın öz ``building`` sahəsidir, ona görə UI-da
# korpus sadəcə otaq siyahısını daraldan süzgəcdir.


def lesson_room_choices(offering):
    """Dərs modalı üçün otaqlar — təşkilatın AKTİV otaqları, korpusu ilə birlikdə.

    Qaytarır ``[{"id", "name", "building", "capacity"}]``; JS seçilmiş korpusa görə
    süzür. Siyahı kiçikdir (universitetdə onlarla/yüzlərlə otaq), ona görə modala
    JSON kimi yerləşdirilir — ayrıca AJAX kaskadı və gözləmə olmur."""
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
            }
        )
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
