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
