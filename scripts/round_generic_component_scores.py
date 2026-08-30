"""Kəsirli GENERIC ``ComponentScore``-ları YARIM-YUXARI tam ədədə yuvarlaqlaşdırır.

Nə üçün var (2026-08-30, sahibin qaydası: qiymətlər tam ədəddir — 72.5 → 73)
---------------------------------------------------------------------------
J5b fazası köhnə MyEdu FLOAT ``yekun.girish`` sütunundan arxiv qalığını
(``residual = clamp(girish − Σkollokvium − checklist, 0, 50)``) yuvarlaqlaşdırMAdan
yazırdı → staging bazasında ~49k kəsirli GENERIC ``ComponentScore`` qaldı.
Faza artıq düzəldilib (``rehearsal_journal_entry_scores_source.round_half_up``);
bu skript isə MÖVCUD bazadakı qalıqları eyni qayda ilə (Decimal ROUND_HALF_UP,
72.5 → 73, 72.4 → 72) tam ədədə gətirir.

⚠️ Ledger-ə QƏSDƏN toxunulmur: staging bazası birdəfəlikdir və növbəti tam
repetisiya düzəldilmiş faza ilə eyni (yuvarlaqlaşdırılmış) dəyərləri özü
yazacaq — bu skript yalnız sahibin İNDİ baxdığı bazanı düzəldir.  Ledger
möhürlərinin dəyər barmaq izləri köhnə (kəsirli) dəyərləri xatırladır; replay
onsuz da möhürlü dilimləri yenidən yazmır, yeni run isə yeni ledger qurur.

İdempotentdir: ikinci icrada kəsirli sətir tapılmır → heç nə yazılmır.
DEFAULT DRY-RUN — ``--apply`` verilmədən heç nə yazılmır.

İstifadə::

    DATABASE_URL="postgres://…/hedef_baza" \
        python scripts/round_generic_component_scores.py            # dry-run
    DATABASE_URL="postgres://…/hedef_baza" \
        python scripts/round_generic_component_scores.py --apply    # yazır
"""

import argparse
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from apps.registrar.models import ComponentScore  # noqa: E402
from core.rls import bypass_rls, journal_unlock  # noqa: E402

INTEGER = Decimal("1")
QUANTUM = Decimal("0.01")  # ``ComponentScore.score`` sahə forması (2 onluq)
CHUNK = 1000
SAMPLE = 5


def round_half_up(value: Decimal) -> Decimal:
    """72.5 → 73, 72.4 → 72.  ⚠️ Python ``round()`` yox — o, bankir qaydasıdır."""

    return value.quantize(INTEGER, rounding=ROUND_HALF_UP).quantize(QUANTUM)


def fractional_generic_scores():
    """GENERIC komponentli, kəsir hissəsi olan balların sorğusu (Python süzgəci)."""

    rows = ComponentScore.objects.filter(component__kind="generic").only("id", "score")
    for row in rows.iterator(chunk_size=CHUNK):
        score = Decimal(row.score)
        if score != score.to_integral_value():
            yield row, round_half_up(score)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
    args = parser.parse_args()

    with bypass_rls():
        total_generic = ComponentScore.objects.filter(component__kind="generic").count()
        pending = list(fractional_generic_scores())

        print(f"GENERIC komponentli ComponentScore cəmi : {total_generic}")
        print(f"Kəsirli (yuvarlaqlaşdırılacaq) sətir     : {len(pending)}")
        for row, rounded in pending[:SAMPLE]:
            print(f"  nümunə: id={row.id}  {row.score} → {rounded}")

        if not args.apply:
            print("DRY-RUN: heç nə yazılmadı (--apply ilə yazılır).")
            return 0

        updated = 0
        # 2 saatlıq ``registrar_journal_mark_guard`` trigger-i köhnə sətrin
        # UPDATE-ini bloklayır → GUC ilə tranzaksiya daxilində açılır.
        with transaction.atomic(), journal_unlock():
            batch = []
            for row, rounded in pending:
                row.score = rounded
                batch.append(row)
                if len(batch) >= CHUNK:
                    ComponentScore.objects.bulk_update(batch, ["score"])
                    updated += len(batch)
                    batch = []
            if batch:
                ComponentScore.objects.bulk_update(batch, ["score"])
                updated += len(batch)

        remaining = sum(1 for _row in fractional_generic_scores())
        print(f"Yeniləndi                                : {updated}")
        print(f"Qalan kəsirli sətir (gözlənilən 0)       : {remaining}")
        return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
