"""
Proses səviyyəli WebSocket koordinasiyası — host keçidləri oyunçu sayı ilə böyüməsin.

Yük testi 2026-10-05 (300 oyunçu, «start» 30 s): hər keçid N socket-də N reaksiya doğururdu.

* **Auto-reveal taymeri (LXBE-08)** — əvvəl HƏR play socket-i öz taymerini qururdu: sual başına
  N asyncio task-ı, N keş iddiası (``cache.add``) və iddia uğursuz olanda (keş xətası → fail-open)
  sessiya sətrinə N ``FOR UPDATE`` tranzaksiyası. İndi bir prosesdə PIN başına BİR taymer var
  (``AutoRevealTimers``); proseslər arası tək qalib yenə ``cache.add`` + DB-dəki şərtli keçiddir.
  Zaman səlahiyyəti serverdə qalır: taymer yalnız ``auto_reveal_if_due``-nu çağırır, o isə kilid
  altında vəziyyəti, ``autoplay``-i və ``question_ends_at + güzəşt``-i yenidən yoxlayır.
* **Host-a gedən sayğaclar** — «seen» (``delivery_progress``) hər telefondan host qrupuna ayrıca
  ``group_send`` idi (sual başına N kanal-qatı göndərişi, host socket-inə N kadr; in-memory qatın
  100 tutumunda host hadisələri itirdi). ``HostProgressCoalescer`` prosesdə (PIN, sual) üzrə ön
  kənarı dərhal, sonrakıları ``HOST_PROGRESS_COALESCE_SECONDS``-da bir dəfə ən böyük dəyərlə
  göndərir — host JS onsuz da maksimumu saxlayır.
* **Lobby roster-i (yük testi 2026-10-07)** — ``LobbyRosterFanout``: hər qoşulmanın roster-i prosesə
  BİR dəfə çatır və oyunçu socket-lərinə yaddaşda paylanır (əvvəl socket başına kanal çatdırılması
  idi — qoşulma axınında O(N²)). Oyunçu yalnız say + öz sətrini alır (wait room başqa adları
  göstərmir); tam siyahı host socket-lərinədir.

Bütün reyestrlər event loop-a bağlıdır (``WeakKeyDictionary``) — testlərdə hər ``async_to_sync``
yeni loop açır, köhnə loop-un task-ları yeni loop-a qarışmır.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from dataclasses import dataclass, field
from typing import Any

from django.core.cache import cache

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer

from apps.live_exam import consumer_support as support
from apps.live_exam.services import auto_reveal_if_due
from apps.live_exam.transport import bundle_events, lobby_roster_group, roster_index
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

logger = logging.getLogger("live_exam.ws.coordination")

#: Host-a gedən sayğac hadisələrinin (prosesdə) birləşdirilmə aralığı.
HOST_PROGRESS_COALESCE_SECONDS = 0.25
#: Proseslər arası auto-reveal iddiasının ömrü (s).
AUTO_REVEAL_CLAIM_TTL_SECONDS = 60


def _claim_auto_reveal(pin: str, question_id: int) -> bool:
    # ``cache`` çağırış anında həll olunur (modul yüklənəndəki backend-ə bağlanmır).
    return bool(cache.add(f"live_exam:auto_reveal:{pin}:{question_id}", "1", AUTO_REVEAL_CLAIM_TTL_SECONDS))


def _reveal_if_due(pin: str, question_id: int):
    with rls_worker_atomic(), bypass_rls():
        return auto_reveal_if_due(pin, question_id)


_claim = sync_to_async(_claim_auto_reveal, thread_sensitive=False)
_reveal = database_sync_to_async(_reveal_if_due, thread_sensitive=False)


async def _send_events(events: list[tuple[str, dict[str, Any]]]) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    for group, event in events:
        await layer.group_send(group, event)


# ── Auto-reveal: prosesdə PIN başına bir taymer ─────────────────────────────


@dataclass
class _RevealTimer:
    question_id: int
    ends_at: str
    task: asyncio.Task | None = None


@dataclass
class _PinState:
    sockets: set[str] = field(default_factory=set)
    timer: _RevealTimer | None = None


class AutoRevealTimers:
    def __init__(self) -> None:
        self._loops: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def _pins(self) -> dict[str, _PinState]:
        loop = asyncio.get_running_loop()
        pins = self._loops.get(loop)
        if pins is None:
            pins = self._loops[loop] = {}
        return pins

    def attach(self, pin: str, socket_id: str) -> None:
        """Play socket-i qoşuldu — taymer ən azı bir socket qaldıqca yaşayır."""
        self._pins().setdefault(pin, _PinState()).sockets.add(socket_id)

    def detach(self, pin: str, socket_id: str) -> bool:
        """Socket bağlandı; prosesdə bu PIN-in socket-i qalmayıbsa taymer ləğv olunur (``True``)."""
        pins = self._pins()
        state = pins.get(pin)
        if state is None:
            return False
        state.sockets.discard(socket_id)
        if state.sockets:
            return False
        self._cancel_timer(state)
        pins.pop(pin, None)
        return True

    def schedule(self, pin: str, question: dict[str, Any] | None) -> None:
        """``question_published`` — eyni sual + eyni ``ends_at`` üçün təkrar çağırış heç nə etmir."""
        due = support.auto_reveal_delay(question)
        if due is None:
            return
        question_id, delay = due
        ends_at = str((question or {}).get("ends_at") or "")
        state = self._pins().setdefault(pin, _PinState())
        timer = state.timer
        if timer is not None and timer.question_id == question_id and timer.ends_at == ends_at:
            if timer.task is not None and not timer.task.done():
                return
        self._cancel_timer(state)
        timer = _RevealTimer(question_id=question_id, ends_at=ends_at)
        timer.task = asyncio.ensure_future(self._fire(pin, state, timer, delay))
        state.timer = timer

    def cancel(self, pin: str, question_id: int | None = None) -> None:
        """reveal/finished gəldi — həmin sualın (``None`` → istənilən) taymeri dayanır."""
        state = self._pins().get(pin)
        if state is None or state.timer is None:
            return
        if question_id is not None and state.timer.question_id != question_id:
            return
        self._cancel_timer(state)

    def pending(self, pin: str) -> int | None:
        """Gözləyən taymerin sual id-si (test/diaqnostika)."""
        state = self._pins().get(pin)
        timer = state.timer if state is not None else None
        if timer is None or timer.task is None or timer.task.done():
            return None
        return timer.question_id

    @staticmethod
    def _cancel_timer(state: _PinState) -> None:
        timer, state.timer = state.timer, None
        if timer is not None and timer.task is not None and not timer.task.done():
            timer.task.cancel()

    async def _fire(self, pin: str, state: _PinState, timer: _RevealTimer, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            try:
                claimed = await _claim(pin, timer.question_id)
            except Exception:
                claimed = True  # keş əlçatmazdır — DB-dəki şərtli keçid onsuz da tək qalibdir
            if not claimed:
                return
            bundle = await _reveal(pin, timer.question_id)
            if bundle is not None:
                await _send_events(bundle_events(pin, bundle))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("live auto-reveal failed", extra={"pin": pin, "question_id": timer.question_id})
        finally:
            if state.timer is timer:
                state.timer = None


# ── Host sayğacları: prosesdə (PIN, sual) üzrə birləşdirmə ─────────────────


@dataclass
class _Pending:
    payload: dict[str, Any] | None = None
    best: int = -1
    last_sent: float = -1e9
    handle: asyncio.TimerHandle | None = None


class HostProgressCoalescer:
    """Ön kənar dərhal; sonra ən çox ``interval``-da bir dəfə ən böyük ``value``-lu son yük."""

    def __init__(self, interval: float = HOST_PROGRESS_COALESCE_SECONDS) -> None:
        self.interval = interval
        self._loops: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def _slots(self) -> dict[tuple, _Pending]:
        loop = asyncio.get_running_loop()
        slots = self._loops.get(loop)
        if slots is None:
            slots = self._loops[loop] = {}
        return slots

    async def offer(self, pin: str, key: tuple, value: int, payload: dict[str, Any]) -> None:
        loop = asyncio.get_running_loop()
        slots = self._slots()
        slot_key = (pin, *key)
        slot = slots.setdefault(slot_key, _Pending())
        if value <= slot.best:
            return  # köhnə (kiçik) sayğac — host-da artıq daha böyüyü var/olacaq
        slot.best = value
        elapsed = loop.time() - slot.last_sent
        if slot.handle is None and elapsed >= self.interval:
            slot.last_sent = loop.time()
            await _send_events([(f"live_{pin}_play_host", {"type": "play_event", "data": payload})])
            return
        slot.payload = payload
        if slot.handle is None:
            slot.handle = loop.call_later(
                max(0.0, self.interval - elapsed), lambda: asyncio.ensure_future(self._flush(pin, slot_key))
            )

    async def _flush(self, pin: str, slot_key: tuple) -> None:
        slot = self._slots().get(slot_key)
        if slot is None:
            return
        slot.handle = None
        payload, slot.payload = slot.payload, None
        if payload is None:
            return
        slot.last_sent = asyncio.get_running_loop().time()
        try:
            await _send_events([(f"live_{pin}_play_host", {"type": "play_event", "data": payload})])
        except Exception:
            logger.exception("live host progress flush failed", extra={"pin": pin})

    def forget(self, pin: str, keep_question_id: int | None = None) -> None:
        """Köhnə sualların slotlarını at (yaddaş sızmasın); cari sualınkı qalır."""
        slots = self._slots()
        for slot_key in [k for k in slots if k[0] == pin and (keep_question_id is None or k[2] != keep_question_id)]:
            slot = slots.pop(slot_key)
            if slot.handle is not None:
                slot.handle.cancel()


# ── Lobby roster: prosesdə PIN başına BİR abunəçi ─────────────────────────


@dataclass
class _RosterPin:
    sockets: set = field(default_factory=set)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


class LobbyRosterFanout:
    """Oyunçu lobby socket-lərinə roster — kanal qatından prosesə BİR çatdırılma, sonra yerli paylama.

    Əvvəl hər qoşulmanın roster-i (``lobby_state``) ``live_<pin>_lobby`` qrupunda HƏR oyunçu socket-inə
    ayrıca çatdırılırdı: qoşulma axınında O(N²) kanal-qatı çatdırılması (channels_redis ``receive``-də
    hər çatdırılma bütün gözləyən consumer-ləri oyadır). İndi roster ``live_<pin>_lobby_roster``
    qrupuna gedir; orada host socket-ləri və hər prosesdə PIN başına bir abunəçi kanal var. Abunəçi
    hadisəni bu prosesin oyunçu socket-lərinə yaddaşda paylayır (hər socket-in öz 250 ms birləşdirməsi
    qalır). ``attach`` abunəçi qrupa qoşulandan SONRA qayıdır — consumer ilkin vəziyyəti ondan sonra
    oxuduğu üçün arada roster itmir.
    """

    def __init__(self) -> None:
        self._loops: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def _pins(self) -> dict[str, _RosterPin]:
        loop = asyncio.get_running_loop()
        pins = self._loops.get(loop)
        if pins is None:
            pins = self._loops[loop] = {}
        return pins

    async def attach(self, pin: str, socket) -> None:
        pins = self._pins()
        state = pins.get(pin)
        if state is None:
            state = pins[pin] = _RosterPin()
        if state.task is None or state.task.done():
            state.ready = asyncio.Event()
            state.task = asyncio.ensure_future(self._run(pin, state))
        state.sockets.add(socket)
        await state.ready.wait()

    async def detach(self, pin: str, socket) -> None:
        pins = self._pins()
        state = pins.get(pin)
        if state is None:
            return
        state.sockets.discard(socket)
        if state.sockets:
            return
        pins.pop(pin, None)
        task = state.task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait([task], timeout=2)

    def subscribers(self, pin: str) -> int:
        """Bu prosesdə PIN-in oyunçu socket sayı (test/diaqnostika)."""
        state = self._pins().get(pin)
        return len(state.sockets) if state is not None else 0

    async def _run(self, pin: str, state: _RosterPin) -> None:
        layer = get_channel_layer()
        group = lobby_roster_group(pin)
        channel = None
        try:
            channel = await layer.new_channel()
            await layer.group_add(group, channel)
            state.ready.set()
            while True:
                await self._deliver(pin, state, await layer.receive(channel))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("live lobby roster subscriber failed", extra={"pin": pin})
        finally:
            state.ready.set()
            if channel is not None:
                try:
                    await layer.group_discard(group, channel)
                except Exception:
                    logger.warning("live lobby roster discard failed", extra={"pin": pin})

    @staticmethod
    async def _deliver(pin: str, state: _RosterPin, message: dict[str, Any]) -> None:
        data = message.get("data") or {}
        if message.get("type") != "lobby_event" or data.get("type") != "lobby_state":
            return
        index = roster_index(data)
        for socket in list(state.sockets):
            try:
                await socket.deliver_lobby_state(data, index)
            except Exception:
                logger.exception("live lobby roster delivery failed", extra={"pin": pin})


auto_reveal_timers = AutoRevealTimers()
host_progress = HostProgressCoalescer()
lobby_rosters = LobbyRosterFanout()
