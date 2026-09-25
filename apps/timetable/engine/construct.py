"""İlkin həll — prioritet sırası ilə «ən məhdud əvvəl» acgöz (greedy) qurma.

Sıra (UniTime/FET təcrübəsi):

1. kilidlənmiş (sabit) hadisələr — öz yerlərinə dərhal qoyulur;
2. qalanlar: yüksək prioritet → kiçik domen (az seçim) → çox qruplu axın
   (mühazirə potoku) → yüklü müəllim.

Hər hadisə üçün bütün icazəli dəyərlər delta ilə qiymətləndirilir və ən ucuzu
seçilir; bərabərlikdə toxum (seed) ilə qarışdırılmış sıra qərar verir. Dəyər
sərt qaydanı pozacaqsa (toqquşma, qrupda boşluq, korpus dolu) hadisə HƏLƏLİK
yerləşdirilmir — onu lokal axtarış (ejection) sonra yerləşdirməyə çalışır.

Dərc olunmuş cədvəldən gələn ``hint`` varsa və pozuntusuzdursa ilk olaraq o
sınanır (minimal dəyişiklik — «minimal perturbation»).
"""

from __future__ import annotations


def construction_order(state, rng) -> list:
    """Sabit olmayan hadisələrin yerləşdirmə sırası (deterministik)."""
    inst = state.inst
    teacher_load: dict = {}
    for event in inst.events:
        if event.teacher is not None:
            teacher_load[event.teacher] = teacher_load.get(event.teacher, 0) + 1
    tie = list(range(state.N))
    rng.shuffle(tie)
    rank = {i: pos for pos, i in enumerate(tie)}

    def key(i):
        event = inst.events[i]
        return (
            -int(event.priority or 1),
            len(state.values[i]),
            -len(event.cohorts),
            -teacher_load.get(event.teacher, 0),
            rank[i],
        )

    return sorted((i for i in range(state.N) if not state.fixed[i]), key=key)


def adds_hard(state, i, delta) -> bool:
    """Yerləşdirmə (``None`` → dəyər) yeni sərt pozuntu yaradırmı?"""
    return delta + state.ev_unplaced[i] >= state.H // 2


def best_value(state, i, rng, *, allow_hard=False):
    """``i`` üçün ən ucuz dəyər və onun deltası (vəziyyət dəyişmir)."""
    values = list(state.values[i])
    if not values:
        return None, None
    rng.shuffle(values)
    hint = state.ev_hint[i]
    if hint is not None and hint in values:
        values.remove(hint)
        values.insert(0, hint)
    best = None
    best_delta = None
    for v in values:
        delta = state.try_changes([(i, v)])
        state.undo()
        if best_delta is None or delta < best_delta:
            best, best_delta = v, delta
    if best is None:
        return None, None
    if not allow_hard and state.val[i] is None and adds_hard(state, i, best_delta):
        return None, best_delta
    return best, best_delta


def place_fixed(state) -> list:
    """Kilidlənmiş hadisələri yerinə qoy; toqquşanların siyahısını qaytar."""
    clashes = []
    for i in range(state.N):
        if state.fixed[i] and state.values[i]:
            delta = state.set_value(i, state.values[i][0])
            if delta + state.ev_unplaced[i] >= state.H // 2:
                clashes.append(i)
    return clashes


def construct(state, rng, *, deadline=None, clock=None) -> dict:
    """Acgöz qurma; qaytarır ``{"placed", "skipped", "fixed_clashes"}``."""
    fixed_clashes = place_fixed(state)
    placed = skipped = 0
    for step, i in enumerate(construction_order(state, rng)):
        if deadline is not None and clock is not None and step % 64 == 0 and clock() > deadline:
            skipped += 1
            continue
        best, _delta = best_value(state, i, rng)
        if best is None:
            skipped += 1
            continue
        state.set_value(i, best)
        placed += 1
    return {"placed": placed, "skipped": skipped, "fixed_clashes": fixed_clashes}


__all__ = ["adds_hard", "best_value", "construct", "construction_order", "place_fixed"]
