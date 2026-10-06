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

Hər iki reyestr event loop-a bağlıdır (``WeakKeyDictionary``) — testlərdə hər ``async_to_sync``
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
from apps.live_exam.transport import bundle_events
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


auto_reveal_timers = AutoRevealTimers()
host_progress = HostProgressCoalescer()
