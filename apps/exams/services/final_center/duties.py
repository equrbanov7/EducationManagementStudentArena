"""final_center paketi — vaxtla məhdud zal nəzarətçisi növbələri (2026-10-13, gecə).

Sahib: «təyin olunandan sonra onun da müəyyən accessləri olması kabinetində, amma
imtahan sessiyası ya da gün bitəndə onun itməsi». Bu modul nəzarətçinin HANSI
zallara İNDİ çıxışı olduğunu sorğu anında hesablayır — cron/süpürgə lazım deyil:
növbə bitən kimi növbəti sorğu artıq rədd olunur, kabinet bəndi də itir.

Mənbələr (hamısı vaxtla məhdud):

1. ``InvigilatorDuty`` (əsas, yeni) — rəhbərin zal + vaxt aralığı üçün təyinatı.
   Açılır: ``starts_at − DUTY_LEAD_MINUTES``. Bağlanır: başlanğıc gününün sonu
   (Asia/Baku) HƏMİŞƏ; ``ends_at + DUTY_GRACE_MINUTES``-dan sonra zalda canlı
   oturum yoxdursa — DƏRHAL; ``revoked_at`` → dərhal.
2. Köhnə daimi ``ExamRoom.invigilators`` M2M — artıq daimi DEYİL: yalnız zalda
   canlı oturum olanda (və ya bu gün başlayacaq hazır oturumun ön pəncərəsində)
   işləyir. Yeni UI M2M-ə yazmır; mövcud sətirlər geriyə-uyğunluq üçündür.
3. Köhnə oturum-səviyyəli ``invigilator`` / ``staff`` — yalnız HƏMİN oturum canlı
   olanda (və ya bu gün başlayacaq hazır oturumun ön pəncərəsində).

İmtahan mərkəzi (rəhbər/işçi) bu məhdudiyyətdən kənardır — onların çıxışı roldan gəlir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_PREPARED,
)

#: Növbə planlaşdırılmış başlanğıcdan bu qədər əvvəl açılır (zalı hazırlamaq, girişi açmaq).
DUTY_LEAD_MINUTES = 30
#: Planlaşdırılmış sondan sonra (canlı oturum qalmayıbsa) bu qədər əlavə — qeydləri bitirmək üçün.
DUTY_GRACE_MINUTES = 15
#: Rəhbər ən çox bu qədər gün irəli növbə yaza bilər (səhv tarixlə «daimi» çıxışın qarşısı).
DUTY_MAX_DAYS_AHEAD = 60

BAKU_TZ = ZoneInfo("Asia/Baku")
LIVE_STATES = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)

DUTY_STATUS_UPCOMING = "upcoming"
DUTY_STATUS_ACTIVE = "active"
DUTY_STATUS_EXPIRED = "expired"
DUTY_STATUS_REVOKED = "revoked"


def _now(now=None):
    return now or timezone.now()


def baku_day_start(moment) -> datetime:
    local = moment.astimezone(BAKU_TZ)
    return datetime.combine(local.date(), time.min, tzinfo=BAKU_TZ)


def baku_day_end(moment) -> datetime:
    """Bakı vaxtı ilə həmin günün son anı (23:59:59.999999)."""
    local = moment.astimezone(BAKU_TZ)
    return datetime.combine(local.date(), time.max, tzinfo=BAKU_TZ)


def duty_opens_at(duty) -> datetime:
    return duty.starts_at - timedelta(minutes=DUTY_LEAD_MINUTES)


def duty_hard_close(duty) -> datetime:
    """Növbənin ən gec bağlanma anı — başlanğıc gününün sonu (Asia/Baku)."""
    return baku_day_end(duty.starts_at)


def duty_soft_close(duty) -> datetime:
    """Planlaşdırılmış son + ehtiyat; bundan sonra yalnız canlı oturum çıxışı saxlayır."""
    return min(duty.ends_at + timedelta(minutes=DUTY_GRACE_MINUTES), duty_hard_close(duty))


def duty_status(duty, *, now=None, room_is_live: bool | None = None) -> str:
    """Növbənin cari statusu. ``room_is_live`` verilməyibsə lazım olanda sorğulanır."""
    now = _now(now)
    if duty.revoked_at is not None:
        return DUTY_STATUS_REVOKED
    if now < duty_opens_at(duty):
        return DUTY_STATUS_UPCOMING
    if now > duty_hard_close(duty):
        return DUTY_STATUS_EXPIRED
    if now <= duty_soft_close(duty):
        return DUTY_STATUS_ACTIVE
    if room_is_live is None:
        room_is_live = bool(live_room_ids([duty.room_id]))
    return DUTY_STATUS_ACTIVE if room_is_live else DUTY_STATUS_EXPIRED


def duty_effective_until(duty, *, now=None, room_is_live: bool | None = None) -> datetime:
    """Kabinetdə göstərilən «bitir» anı (aktiv növbə üçün)."""
    now = _now(now)
    soft = duty_soft_close(duty)
    if now <= soft:
        return soft
    return duty_hard_close(duty)


def live_room_ids(room_ids) -> set:
    from apps.exams.models import ExamRoomSession

    ids = [room_id for room_id in set(room_ids) if room_id]
    if not ids:
        return set()
    return set(ExamRoomSession.objects.filter(room_id__in=ids, state__in=LIVE_STATES).values_list("room_id", flat=True))


def _window_session_q(now) -> Q:
    """Köhnə təyinatlar üçün «indi işləyən» oturum: canlı, YA bu gün başlayacaq hazır
    oturumun ön pəncərəsi (``scheduled_start − lead ≤ now``)."""
    lead = timedelta(minutes=DUTY_LEAD_MINUTES)
    return Q(state__in=LIVE_STATES) | Q(
        state=ROOM_SESSION_STATE_PREPARED,
        scheduled_start__lte=now + lead,
        scheduled_start__gte=baku_day_start(now),
    )


def candidate_duties(user, *, organization_id=None, now=None):
    """İndi açıq ola biləcək (ləğv olunmamış, pəncərəsi başlamış, günü bitməmiş) növbələr."""
    from apps.exams.models import InvigilatorDuty

    now = _now(now)
    qs = InvigilatorDuty.objects.filter(
        user=user,
        revoked_at__isnull=True,
        starts_at__lte=now + timedelta(minutes=DUTY_LEAD_MINUTES),
        starts_at__gte=baku_day_start(now),
    )
    if organization_id is not None:
        qs = qs.filter(organization_id=organization_id)
    return qs


def active_duties(user, *, organization_id=None, now=None) -> list:
    """İndi AKTİV növbələr (zal ilə birlikdə) — kabinet zolağı və icazə üçün."""
    if not getattr(user, "is_authenticated", False):
        return []
    now = _now(now)
    duties = list(candidate_duties(user, organization_id=organization_id, now=now).select_related("room"))
    overtime_rooms = {d.room_id for d in duties if now > duty_soft_close(d)}
    live = live_room_ids(overtime_rooms) if overtime_rooms else set()
    return [d for d in duties if duty_status(d, now=now, room_is_live=d.room_id in live) == DUTY_STATUS_ACTIVE]


@dataclass(frozen=True)
class SupervisionScope:
    """İstifadəçinin İNDİ nəzarət edə bildiyi zallar/oturumlar (mərkəz istisna).

    ``room_ids`` — zal səviyyəli çıxış (növbə / köhnə zal M2M): zaldakı bütün oturumlar.
    ``session_ids`` — köhnə oturum-səviyyəli çıxış (yalnız həmin oturum);
    ``session_room_ids`` — həmin oturumların zalları (zal siyahısında görünsün deyə).
    """

    room_ids: frozenset = field(default_factory=frozenset)
    session_ids: frozenset = field(default_factory=frozenset)
    session_room_ids: frozenset = field(default_factory=frozenset)

    @property
    def is_empty(self) -> bool:
        return not self.room_ids and not self.session_ids

    @property
    def visible_room_ids(self) -> frozenset:
        return self.room_ids | self.session_room_ids

    def allows_room(self, room_id) -> bool:
        return room_id in self.room_ids

    def allows_session(self, session) -> bool:
        return session.room_id in self.room_ids or session.pk in self.session_ids

    def sessions_q(self) -> Q:
        return Q(room_id__in=list(self.room_ids)) | Q(pk__in=list(self.session_ids))


def supervision_scope(user, *, organization_id=None, now=None) -> SupervisionScope:
    """Nəzarətçinin indiki əhatəsi — 3 kiçik sorğu (növbə + köhnə zal + köhnə oturum)."""
    if not getattr(user, "is_authenticated", False):
        return SupervisionScope()
    from apps.exams.models import ExamRoomSession

    now = _now(now)
    room_ids = {d.room_id for d in active_duties(user, organization_id=organization_id, now=now)}

    window = _window_session_q(now)
    legacy_room_sessions = ExamRoomSession.objects.filter(room__invigilators=user).filter(window)
    if organization_id is not None:
        legacy_room_sessions = legacy_room_sessions.filter(organization_id=organization_id)
    room_ids.update(legacy_room_sessions.values_list("room_id", flat=True))

    legacy_sessions = ExamRoomSession.objects.filter(Q(invigilator=user) | Q(staff=user)).filter(window)
    if organization_id is not None:
        legacy_sessions = legacy_sessions.filter(organization_id=organization_id)
    session_rows = list(legacy_sessions.values_list("pk", "room_id").distinct())
    return SupervisionScope(
        room_ids=frozenset(room_ids),
        session_ids=frozenset(pk for pk, _room in session_rows),
        session_room_ids=frozenset(room for _pk, room in session_rows),
    )


def duty_cards(user, organization, *, now=None) -> list:
    """Nəzarətçinin kabinet zolağı: indi aktiv növbələr (zal, pəncərə, «bitir» anı).

    Zal başına bir kart (eyni zala iki növbə üst-üstə düşsə ən gec bitəni).
    """
    now = _now(now)
    duties = active_duties(user, organization_id=getattr(organization, "pk", None), now=now)
    live = live_room_ids({d.room_id for d in duties})
    by_room = {}
    for duty in duties:
        until = duty_effective_until(duty, now=now, room_is_live=duty.room_id in live)
        current = by_room.get(duty.room_id)
        if current is None or until > current["until"]:
            by_room[duty.room_id] = {
                "room": duty.room,
                "starts_at": duty.starts_at,
                "ends_at": duty.ends_at,
                "until": until,
                "overtime": now > duty_soft_close(duty),
            }
    return sorted(by_room.values(), key=lambda card: (card["starts_at"], card["room"].name))


def duty_rows_for_room(room, *, now=None, include_past_days: int = 0) -> list:
    """Zal monitorunun «Nəzarətçi növbələri» paneli: bu gün + gələcək növbələr (status ilə)."""
    from apps.exams.models import InvigilatorDuty

    now = _now(now)
    since = baku_day_start(now) - timedelta(days=include_past_days)
    duties = list(
        InvigilatorDuty.objects.filter(room=room, starts_at__gte=since)
        .select_related("user", "assigned_by")
        .order_by("starts_at", "id")[:200]
    )
    room_live = bool(live_room_ids([room.pk])) if duties else False
    rows = []
    for duty in duties:
        status = duty_status(duty, now=now, room_is_live=room_live)
        rows.append(
            {
                "duty": duty,
                "status": status,
                "opens_at": duty_opens_at(duty),
                "until": duty_effective_until(duty, now=now, room_is_live=room_live),
            }
        )
    return rows


__all__ = [
    "BAKU_TZ",
    "DUTY_GRACE_MINUTES",
    "DUTY_LEAD_MINUTES",
    "DUTY_MAX_DAYS_AHEAD",
    "DUTY_STATUS_ACTIVE",
    "DUTY_STATUS_EXPIRED",
    "DUTY_STATUS_REVOKED",
    "DUTY_STATUS_UPCOMING",
    "SupervisionScope",
    "active_duties",
    "baku_day_end",
    "baku_day_start",
    "candidate_duties",
    "duty_cards",
    "duty_effective_until",
    "duty_hard_close",
    "duty_opens_at",
    "duty_rows_for_room",
    "duty_soft_close",
    "duty_status",
    "live_room_ids",
    "supervision_scope",
]
