"""«Yük bölgüsü»ndə müəllim dəyişikliyi → jurnal köçürməsi (sahib 2026-11-11).

Sahib: «Yük bölgüsündən müəllimi dəyişəndə fənn də təhvil olsun — Fənn təhvili ilə eyni nəticə: yeni müəllim
jurnalı bütün balları ilə görür, köhnə müəllim başqa növü qalmırsa onu itirir.» Yazı TƏK yoldadır:
``apps.registrar.journal_transfer.transfer`` («Fənn təhvili» də onu çağırır). Burada yalnız «nə vaxt» qərarı var:

* SAHİBLİK — ``decide_instructor`` ``replaced`` deyəndə (əvvəlki yük sahibi bilinir və dəyişib) tam köçürmə;
* SEMİNAR / LAB — növün əvvəlki müəllimi(ləri) VAR idi və indi TƏK başqa müəllimdir → həmin növün köçürməsi
  (əvvəlki «Fənn təhvili» payını da əvəzləyir). Vakant → müəllim (ilk bölgü) TƏHVİL deyil: yük sinxronu payı
  özü açır; yalnız növü «Fənn təhvili» payı tutubsa o növ yeni müəllimə köçürülür.

Xəta (registrar qoruyucusu, paralel dəyişiklik) əsas əməli dayandırmır — ``transfer_blocked`` sayılır.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from django.db import IntegrityError, transaction

from .offering_shares import KINDS, _assignment_group

logger = logging.getLogger(__name__)

#: Hesabat sayğacları (``offering_sync.COUNTER_KEYS``-ə qoşulur).
TRANSFER_COUNTER_KEYS = ("journal_transferred", "kind_transferred", "transfer_blocked")


class Snapshot(dict):
    """``owner_snapshot`` nəticəsi: ``{açar: sahib id}`` + ``kinds`` — ``{açar: {növ: frozenset(müəllim)}}``."""

    def __init__(self, owners=(), kinds=None):
        super().__init__(owners)
        self.kinds = kinds or {}


def kind_teachers(rows, group) -> dict:
    """Bu qrupun növ üzrə yük müəllimləri (strukturlu qrup bağı və ya qeyd ilə, ``offering_shares`` qaydası)."""
    teachers = defaultdict(set)
    for row in rows:
        for assignment in row.assignments.all():
            if not (assignment.teacher_id and assignment.activity in KINDS and assignment.hours > 0):
                continue
            if _assignment_group(assignment, row, group) is True:
                teachers[assignment.activity].add(assignment.teacher_id)
    return {kind: frozenset(ids) for kind, ids in teachers.items()}


def kind_moves(before, after) -> dict:
    """``{növ: yeni müəllim}`` — yalnız AÇIQ dəyişiklik: əvvəl müəllim var idi, indi TƏK başqa müəllimdir."""
    moves = {}
    for kind in KINDS:
        old, new = before.get(kind) or frozenset(), after.get(kind) or frozenset()
        if old and len(new) == 1 and not new <= old:
            moves[kind] = next(iter(new))
    return moves


def _locked(offering):
    model = type(offering)
    return model.objects.select_for_update(of=("self",)).select_related("organization").get(pk=offering.pk)


def _user(user_id):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=user_id, is_active=True).first()


def _run(sync, offering, target_id, kinds):
    """Ortaq servis savepoint içində; uğurda qeyd, xətada ``None``."""
    from apps.registrar.public import journal_transfer

    target = _user(target_id)
    if target is None:
        return None
    try:
        with transaction.atomic():
            locked = _locked(offering)
            record = journal_transfer.transfer(
                offering=locked,
                target=target,
                kinds=kinds,
                actor=sync.actor_user,
                reason=journal_transfer.WORKLOAD_REASON,
                origin=journal_transfer.ORIGIN_WORKLOAD,
            )
    except (IntegrityError, journal_transfer.TransferRejected) as exc:
        logger.warning("workload: journal transfer to %s blocked on %s (%s)", target_id, offering.pk, exc)
        sync.counters["transfer_blocked"] += 1
        return None
    offering.instructor_id = locked.instructor_id
    journal_transfer.notify_on_commit([record], organization=sync.task.organization)
    return record


def hand_over_owner(sync, offering, new_id) -> bool:
    """Sahibliyin açıq dəyişikliyi — tam köçürmə (köhnə sahibin qalan növləri yük sinxronunda pay olur)."""
    record = _run(sync, offering, new_id, None)
    if record is None:
        return False
    sync.counters["journal_transferred"] += 1
    return True


def transfer_kinds(sync, offering, key, entry, *, owner_id, eligible_ids) -> None:
    """Seminar / lab müəllimi açıq dəyişibsə həmin növü ortaq servislə köçür (bax modul başlığı)."""
    from apps.registrar.public import journal_transfer

    before = getattr(sync.previous, "kinds", {}).get(key)
    if before is None:
        return
    after = kind_teachers(entry["rows"], entry["group"])
    moves = {kind: teacher for kind, teacher in kind_moves(before, after).items() if kind != "lecture"}
    claimed = _handover_claimed(offering)
    for kind in KINDS - {"lecture"}:
        new = after.get(kind) or frozenset()
        if kind not in moves and not before.get(kind) and len(new) == 1 and kind in claimed:
            moves[kind] = next(iter(new))  # vakant → müəllim, amma növ «Fənn təhvili» payındadır
    for kind, teacher_id in sorted(moves.items()):
        if teacher_id == owner_id and owner_id != sync.previous.get(key):
            continue  # yeni sahib — sahiblik köçürməsi onsuz da gəlir
        if teacher_id not in eligible_ids(teacher_id):
            continue
        if journal_transfer.current_holders(offering).get(kind) == {teacher_id}:
            continue
        if _run(sync, offering, teacher_id, {kind}) is not None:
            sync.counters["kind_transferred"] += 1


def _handover_claimed(offering) -> set:
    from apps.registrar.public import journal_transfer

    model = offering.shares.model
    kinds = set()
    for share in model.objects.filter(offering_id=offering.pk, is_active=True):
        if journal_transfer.is_handover_share(share):
            kinds |= set(share.kinds or ()) or set(KINDS)
    return kinds


__all__ = ["TRANSFER_COUNTER_KEYS", "Snapshot", "hand_over_owner", "kind_moves", "kind_teachers", "transfer_kinds"]
