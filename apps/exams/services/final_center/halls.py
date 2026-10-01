"""final_center paketi — İMTAHAN ZALI bayrağı (sahib 2026-10-01).

``ExamRoom`` təşkilatın YEGANƏ otaq reyestridir (jurnal dərs modalı, cədvəl);
legacy idxal bütün sinif otaqlarını ora yazdığı üçün imtahan mərkəzinin
«İmtahan zalları» siyahısında 150+ adi otaq görünürdü. İndi zal = otaq +
``is_exam_hall`` bayrağı. Bu modul:

* kim bayrağı dəyişə bilər (``can_designate_exam_halls``);
* hansı otaqlar zal siyahısına düşür (``exam_hall_scope_q`` — bayraqlı zallar +
  HAZIRDA canlı oturumu olan otaqlar; gedən imtahan heç vaxt gizlənmir);
* bayrağın təhlükəsiz dəyişməsi (``set_exam_hall`` — kilid, qaydalar, audit).

Final girişi (kompüter IP/MAC → zal) bu bayrağa QƏSDƏN baxmır: bayraqsız
otağın qeydli kompüterini «tapılmadı» saymaq PIN yolunu nəzarətsiz birbaşa
başlamaya salardı. Əvəzində invariant idarə qatında saxlanır — aktiv kompüteri
olan zal çıxarılmır (``active_computers``), kompüter qeydiyyatı UI-da yalnız
zallar üçün təklif olunur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils.translation import pgettext

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_PREPARED,
)
from apps.exams.models import ExamRoom, ExamRoomComputer, ExamRoomSession
from apps.exams.services.access_policy import can_manage_exam_rooms
from core.audit import log_action
from core.constants import AuditAction

_CTX = "exams.final_center.halls"

#: Zalda imtahan GEDİR (giriş açıq / aktiv) — çıxarmaq qadağandır.
LIVE_STATES = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
#: Planlaşdırılmış (hələ açılmamış) oturum — çıxarmaq təsdiq tələb edir.
UPCOMING_STATES = (ROOM_SESSION_STATE_PREPARED,)

ERROR_LIVE_SESSION = "live_session"
ERROR_ACTIVE_COMPUTERS = "active_computers"
ERROR_NEEDS_CONFIRM = "needs_confirm"


def can_designate_exam_halls(user) -> bool:
    """Otağı imtahan zalı kimi kim qeyd edə / çıxara bilər?

    Zal infrastrukturunun idarəçiləri (``can_manage_exam_rooms`` — superadmin,
    RİM rəhbəri, bayraqlı zal idarəçisi) VƏ imtahan mərkəzinin rəhbəri
    (``is_exam_center_head``). Mərkəz əməkdaşı və nəzarətçi — YOX (onlar yalnız
    zalları görür). Kompüter/MAC qeydiyyatı bundan asılı deyil — o, yenə də
    yalnız ``can_manage_exam_rooms``-dadır.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if can_manage_exam_rooms(user):
        return True
    return bool(getattr(user, "is_exam_center_head", False))


def live_session_exists():
    """``ExamRoom`` sətri üçün «hazırda canlı oturumu var» alt-sorğusu (JOIN yox)."""
    return Exists(ExamRoomSession.objects.filter(room_id=OuterRef("pk"), state__in=LIVE_STATES))


def exam_hall_scope_q() -> Q:
    """Zal siyahısının əhatəsi: bayraqlı zallar + canlı oturumu olan istənilən otaq.

    ``Exists`` alt-sorğusudur — ``Count("sessions")`` annotasiyaları ilə bir
    sorğuda işlədilə bilər (sətir partlayışı yoxdur).
    """
    return Q(is_exam_hall=True) | Q(live_session_exists())


@dataclass(frozen=True)
class HallUsage:
    live: int
    upcoming: int
    active_computers: int


def hall_usage(room) -> HallUsage:
    sessions = ExamRoomSession.objects.filter(room_id=room.pk)
    return HallUsage(
        live=sessions.filter(state__in=LIVE_STATES).count(),
        upcoming=sessions.filter(state__in=UPCOMING_STATES).count(),
        active_computers=ExamRoomComputer.objects.filter(room_id=room.pk, is_active=True).count(),
    )


class ExamHallChangeError(Exception):
    """Bayraq dəyişməsi rədd edildi — ``code`` UI/komanda üçün maşın açarıdır."""

    def __init__(self, message, code, usage=None):
        super().__init__(message, code, usage)
        self.message = message
        self.code = code
        self.usage = usage

    def __str__(self):
        return str(self.message)


def _refusal(room, usage: HallUsage, *, confirmed: bool):
    """Zalı çıxarmaq olarmı? Olmursa ``ExamHallChangeError`` qaytarır (atmır)."""
    if usage.live:
        return ExamHallChangeError(
            pgettext(
                _CTX,
                "«%(room)s» zalında hazırda imtahan gedir — oturum bitənə qədər zalı imtahan "
                "zallarından çıxarmaq olmaz.",
            )
            % {"room": room.name},
            code=ERROR_LIVE_SESSION,
            usage=usage,
        )
    if usage.active_computers:
        return ExamHallChangeError(
            pgettext(
                _CTX,
                "«%(room)s» zalında %(n)d aktiv kompüter qeydiyyatdadır — onlardan final imtahanına "
                "giriş mümkündür. Əvvəlcə kompüterləri deaktiv edin və ya silin (zal idarəetməsi).",
            )
            % {"room": room.name, "n": usage.active_computers},
            code=ERROR_ACTIVE_COMPUTERS,
            usage=usage,
        )
    if usage.upcoming and not confirmed:
        return ExamHallChangeError(
            pgettext(
                _CTX,
                "«%(room)s» zalında %(n)d planlaşdırılmış oturum var. Zal imtahan zallarından "
                "çıxarılsın? Oturumlar silinmir, zal monitoru onlar üçün açıq qalır.",
            )
            % {"room": room.name, "n": usage.upcoming},
            code=ERROR_NEEDS_CONFIRM,
            usage=usage,
        )
    return None


def set_exam_hall(room, value: bool, *, by=None, request=None, confirmed: bool = False, source: str = "ui") -> bool:
    """Otağın zal bayrağını təyin edir; dəyişdisə ``True`` (idempotent).

    Çıxarma qaydaları: canlı oturum → rədd; aktiv kompüter → rədd; planlaşdırılmış
    oturum → ``confirmed=True`` olmadan rədd (``needs_confirm``). Otaq sətri
    ``select_for_update`` ilə kilidlənir ki, paralel iki klik ikiqat audit
    yazmasın. Hər dəyişiklik audit jurnalına düşür.
    """
    value = bool(value)
    with transaction.atomic():
        locked = ExamRoom.objects.select_for_update(of=("self",)).select_related("organization").get(pk=room.pk)
        if locked.is_exam_hall == value:
            room.is_exam_hall = value
            return False
        if not value:
            refusal = _refusal(locked, hall_usage(locked), confirmed=confirmed)
            if refusal is not None:
                raise refusal
        locked.is_exam_hall = value
        locked.save(update_fields=["is_exam_hall", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=by,
            organization=locked.organization,
            obj=locked,
            old_values={"is_exam_hall": not value},
            new_values={"is_exam_hall": value},
            changes={"is_exam_hall": [not value, value], "source": source},
            reason="exam_hall_marked" if value else "exam_hall_unmarked",
            request=request,
            resource_type="exam_room",
            resource_id=str(locked.pk),
            resource_repr=str(locked)[:200],
        )
    room.is_exam_hall = value
    return True


# ─── Sıralama / qruplaşdırma (UI) ───────────────────────────────────────────


def natural_key(value) -> list:
    """«2», «10», «03/2», «Korpus A» — rəqəm hissələri say kimi sıralanır."""
    return [(0, int(part)) if part.isdigit() else (1, part.lower()) for part in re.split(r"(\d+)", value or "") if part]


def room_sort_key(room) -> tuple:
    """Korpus (boş korpus SONDA) → otaq adı (təbii) → id."""
    building = (room.building or "").strip()
    return (building == "", natural_key(building), natural_key(room.name), room.pk)


def group_by_building(page_rooms, all_rooms, *, empty_label: str) -> list[dict]:
    """Səhifədəki otaqları korpus qruplarına bölür; saylar BÜTÜN süzülmüş siyahıdandır.

    ``page_rooms`` artıq ``room_sort_key`` ilə sıralanmış olmalıdır (qruplar ardıcıldır).
    """
    totals: dict[str, list[int]] = {}
    for room in all_rooms:
        bucket = totals.setdefault((room.building or "").strip(), [0, 0])
        bucket[0] += 1
        bucket[1] += 1 if room.is_exam_hall else 0
    groups: list[dict] = []
    for room in page_rooms:
        key = (room.building or "").strip()
        if not groups or groups[-1]["key"] != key:
            rooms_total, halls_total = totals.get(key, (0, 0))
            groups.append(
                {
                    "key": key,
                    "label": key or empty_label,
                    "rooms": [],
                    "room_total": rooms_total,
                    "hall_total": halls_total,
                }
            )
        groups[-1]["rooms"].append(room)
    return groups


__all__ = [
    "ERROR_ACTIVE_COMPUTERS",
    "ERROR_LIVE_SESSION",
    "ERROR_NEEDS_CONFIRM",
    "ExamHallChangeError",
    "HallUsage",
    "LIVE_STATES",
    "UPCOMING_STATES",
    "can_designate_exam_halls",
    "exam_hall_scope_q",
    "group_by_building",
    "hall_usage",
    "live_session_exists",
    "natural_key",
    "room_sort_key",
    "set_exam_hall",
]
