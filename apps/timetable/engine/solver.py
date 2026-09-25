"""Həlledici interfeysi + standart saf-Python həlledici (``local_search``).

Mərhələlər (vaxt büdcəsinin payı):

1. ``construct``     — prioritetli acgöz qurma (IFS-in «irəli» addımı);
2. ``anneal``        — SA + ejection (büdcənin ~85%-i);
3. ``make_feasible`` — təhlükəsizlik qatı: qalan sərt pozuntuları çıxarır;
   ``reinsert``      — çıxarılanları pozuntusuz yerə qaytarır;
4. ``polish``        — aşağı temperaturda qısa SA (qalan büdcə);
5. otaq təyini (vaxtdan sonra) + müstəqil yoxlayıcı (``verify.check``).

``Solver`` protokolu sabitdir: gələcəkdə OR-Tools CP-SAT arxa ucu
(``ortools>=9.12``, protobuf-5 uyğun) eyni imza ilə ``SOLVERS``-ə əlavə olunur —
Django tərəfi (mənbələr, UI, dərc) dəyişmir. Asılılıq İNDİ əlavə edilmir.
"""

from __future__ import annotations

import random
import time
from typing import Protocol

from .construct import construct
from .repair import chain_insert, make_feasible, reinsert, unplaced_reasons
from .rooms import assign_rooms
from .search import anneal
from .state import State
from .types import Result
from .verify import check


class Solver(Protocol):
    name: str

    def solve(self, instance, params, *, progress=None) -> Result: ...


class LocalSearchSolver:
    """Saf-Python konstruktiv + SA/IFS həlledici (yeni asılılıq tələb etmir)."""

    name = "local_search"
    search_share = 0.85

    def __init__(self, clock=time.monotonic):
        self.clock = clock

    def solve(self, instance, params, *, progress=None) -> Result:
        clock = self.clock
        started = clock()
        rng = random.Random(int(params.seed or 0))
        budget = max(0.0, float(params.time_limit or 0))
        iterations = max(0, int(params.max_iterations or 0))
        log = []

        def report(payload):
            if progress is not None:
                progress(payload)

        report({"phase": "construct", "frac": 0.0})
        state = State(instance, params.weights)
        built = construct(state, rng)
        log.append(
            f"construct: placed={built['placed']} skipped={built['skipped']} "
            f"fixed_clashes={len(built['fixed_clashes'])} cost={state.cost}"
        )

        search = anneal(
            state,
            rng,
            clock=clock,
            budget_seconds=budget * self.search_share,
            max_iterations=int(iterations * 0.9) if iterations else 0,
            t_start=params.t_start,
            t_end=params.t_end,
            progress=report,
        )
        log.append(
            f"anneal: iterations={search['iterations']} accepted={search['accepted']} "
            f"elapsed={search['elapsed']}s cost={state.cost}"
        )

        report({"phase": "repair", "frac": 0.9})
        feasible = make_feasible(state)
        placed_back = reinsert(state, rng)
        placed_back += chain_insert(state, rng, clock=clock, deadline=started + budget * 0.95 if budget else None)
        log.append(
            f"repair: ejected={len(feasible['ejected'])} reinserted={placed_back} stuck={len(feasible['stuck'])}"
        )

        remaining = max(0.0, budget - (clock() - started)) * 0.8 if budget else 0.0
        polish = anneal(
            state,
            rng,
            clock=clock,
            budget_seconds=remaining,
            max_iterations=int(iterations * 0.1) if iterations else 0,
            t_start=min(params.t_start, 3.0),
            t_end=params.t_end,
        )
        final = make_feasible(state)
        placed_back += reinsert(state, rng)
        placed_back += chain_insert(state, rng, clock=clock, deadline=started + budget if budget else None)
        log.append(f"polish: iterations={polish['iterations']} ejected={len(final['ejected'])} cost={state.cost}")

        report({"phase": "rooms", "frac": 0.97})
        values = list(state.val)
        rooms, room_stats = assign_rooms(instance, values)
        kpis = check(instance, values, rooms)
        kpis["rooms"] = room_stats
        kpis["cost"] = state.cost
        kpis["stuck_violations"] = len(final["stuck"])
        elapsed = round(clock() - started, 3)
        stats = {
            "solver": self.name,
            "seed": int(params.seed or 0),
            "elapsed": elapsed,
            "iterations": search["iterations"] + polish["iterations"],
            "accepted": search["accepted"] + polish["accepted"],
            "construct": {"placed": built["placed"], "skipped": built["skipped"]},
            "fixed_clashes": [instance.events[i].key for i in built["fixed_clashes"]],
        }
        kpis["elapsed"] = elapsed
        kpis["iterations"] = stats["iterations"]
        log.append(f"done: {elapsed}s placed={kpis['placed']}/{kpis['events']} hard={kpis['hard_total']}")
        return Result(values=values, rooms=rooms, unplaced=unplaced_reasons(state), kpis=kpis, log=log, stats=stats)


#: Qeydiyyatlı həlledicilər. CP-SAT əlavə ediləndə: ``SOLVERS["cp_sat"] = CpSatSolver``
#: (``ortools`` tənbəl import olunmalıdır ki, paket olmayanda tətbiq sınmasın).
SOLVERS = {LocalSearchSolver.name: LocalSearchSolver}
DEFAULT_SOLVER = LocalSearchSolver.name


def get_solver(name: str | None = None):
    return SOLVERS.get(name or DEFAULT_SOLVER, LocalSearchSolver)()


def solve(instance, params, *, solver: str | None = None, progress=None) -> Result:
    return get_solver(solver).solve(instance, params, progress=progress)


__all__ = ["DEFAULT_SOLVER", "SOLVERS", "LocalSearchSolver", "Solver", "get_solver", "solve"]
