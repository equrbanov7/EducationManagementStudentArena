"""RİM müraciətləri 2026-11-06 — sabit id-li düzəlişlər (sahib: «müraciətləri həll et, təsdiq gözləmə»).

* **MR-000236** (Reyhan Əhmədova, 136 Si-2): köhnə sistemdə «Psixologiya 136Si2» jurnalı səhvən «Çapaqədər, çap və
  çapdan sonrakı proseslərdə komputer texnikası…» fənninə bağlanmışdı (köhnə 15136/15137, fənn 1797) — köçürmədə
  jurnal həmin adla gəldi. Onun dərsləri və xanaları qrupun «Psixologiya» jurnalına birləşir (``Merger``, keep).

İdempotentdir. Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

from .twin_merge import Merger

MR236_PAIRS = (
    {
        "source": "45985e6b-0500-42e8-a80c-cfc4243601a3",
        "target": "e2a4155d-8e96-41e8-bc92-d635eb306429",
        "target_marks": "keep",
    },
)


def run(*, organization, actor, counts) -> None:
    Merger(organization=organization, actor=actor, counts=counts).run([dict(pair) for pair in MR236_PAIRS])
