"""``legacy_repair_pseudo_groups`` — P2-8: köçürmə psevdo-qrupları («Level …»,
«Xaric ол(un)anlar»).

Dry-run DEFAULT-dur.  Qərar qaydası və audit hesabatı
``apps.legacy_import.services.repair_pseudo_groups`` / ``docs/audits
/2026-09-05/LEVEL_GROUPS.md``-dədir.

    manage.py legacy_repair_pseudo_groups --organization myedu-univ
    manage.py legacy_repair_pseudo_groups --organization myedu-univ --apply
    manage.py legacy_repair_pseudo_groups --organization myedu-univ \\
        --include-level-2025-2026 --apply
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.legacy_import.services.repair_pseudo_groups import (
    TABLE_HEADERS_RECORDS,
    TABLE_HEADERS_UNITS,
    apply_expel,
    apply_mark_service,
    plan_record_decisions,
    plan_unit_decisions,
)
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)
from core.rls_pooling import rls_worker_atomic

#: Rəsmi hərəkət sənədinin default nömrəsi/səbəbi — operator real əmr
#: nömrəsi/tarixi ilə əvəz edə bilər (``--order-number`` / ``--order-date``).
DEFAULT_ORDER_NUMBER = "P2-8-LEGACY-REPAIR"
DEFAULT_EXPEL_REASON = (
    "Köçürmə auditi (P2-8): tələbə mənbədə 'Xaric olunanlar/olanlar' konteynerində "
    "idi, akademik status səhvən 'enrolled' qalmışdı — bax docs/audits/2026-09-05/LEVEL_GROUPS.md."
)


class Command(BaseCommand):
    help = (
        "Köçürmədən gələn psevdo-qrupları («Level …», «Xaric ол(un)anlar») texniki "
        "bölmə kimi işarələyir və konteynerdəki tələbələrin statusunu rəsmi EXPULSION "
        "hərəkəti ilə düzəldir."
    )

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--include-level-2025-2026",
            action="store_true",
            help=(
                "Naxış C (bax audit §3) — 228 tələbəli 'Level 2025-2026' tutucu qrupunu "
                "da 'mark_service' hədəfinə daxil et (default: İSTİSNA olunur)."
            ),
        )
        parser.add_argument(
            "--skip-mark-service",
            action="store_true",
            help="Yalnız 'expel' əməlini icra et — vahidləri texniki bölmə kimi işarələmə.",
        )
        parser.add_argument(
            "--skip-expel",
            action="store_true",
            help="Yalnız 'mark_service' əməlini icra et — tələbə statusuna toxunma.",
        )
        parser.add_argument("--order-number", default=DEFAULT_ORDER_NUMBER, help="EXPULSION əmrinin rəsmi nömrəsi.")
        parser.add_argument("--order-date", default="", help="Əmrin tarixi (YYYY-MM-DD) — boşdursa bugün.")
        parser.add_argument("--reason", default=DEFAULT_EXPEL_REASON, help="EXPULSION hərəkətinin səbəbi (≥20 simvol).")
        parser.add_argument("--show", type=int, default=40, help="Cədvəldə göstəriləcək sətir sayı")

    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1): bütün DB işi bir
        # worker-atomic sərhədi içindədir. Sətir-səviyyəli fail-open semantikası
        # dəyişmir — ``movements.create_movement`` daxili ``transaction.atomic()``
        # savepoint olur.
        with rls_worker_atomic():
            context = build_context(options)
            include_large_holding = bool(options.get("include_level_2025_2026"))

            order_date_raw = str(options.get("order_date") or "").strip()
            order_date = parse_date(order_date_raw) if order_date_raw else timezone.localdate()
            if order_date_raw and order_date is None:
                self.stderr.write(f"✗ --order-date yanlış formatdır: {order_date_raw!r} (gözlənilən: YYYY-MM-DD)")
                order_date = timezone.localdate()

            unit_decisions = plan_unit_decisions(
                context.organization, include_large_holding=include_large_holding, limit=context.limit
            )
            record_decisions = plan_record_decisions(context.organization, limit=context.limit)

            self.stdout.write("— Vahidlər (mark_service) —")
            self.stdout.write(
                render_table(TABLE_HEADERS_UNITS, [d.as_row() for d in unit_decisions], max_rows=int(options["show"]))
            )
            self.stdout.write("")
            self.stdout.write("— Tələbə qeydləri (expel) —")
            self.stdout.write(
                render_table(
                    TABLE_HEADERS_RECORDS, [d.as_row() for d in record_decisions], max_rows=int(options["show"])
                )
            )

            unit_counters = Counter(d.action for d in unit_decisions)
            record_counters = Counter(d.action for d in record_decisions)

            marked = 0
            expelled = 0
            failed: list[tuple[str, str]] = []
            if context.apply:
                if not options.get("skip_mark_service"):
                    for decision in unit_decisions:
                        if decision.action != "mark_service":
                            continue
                        try:
                            marked += (
                                1
                                if apply_mark_service(
                                    organization=context.organization, actor=context.actor, decision=decision
                                )
                                else 0
                            )
                        except Exception as error:  # noqa: BLE001 — sətir-səviyyə fail-open hesabatı
                            failed.append((decision.name, type(error).__name__ + ":" + str(error)[:80]))
                if not options.get("skip_expel"):
                    for decision in record_decisions:
                        if decision.action != "expel":
                            continue
                        try:
                            expelled += (
                                1
                                if apply_expel(
                                    organization=context.organization,
                                    actor=context.actor,
                                    decision=decision,
                                    order_number=str(options["order_number"]),
                                    order_date=order_date,
                                    reason=str(options["reason"]),
                                )
                                else 0
                            )
                        except Exception as error:  # noqa: BLE001 — sətir-səviyyə fail-open hesabatı
                            failed.append((decision.student_username, type(error).__name__ + ":" + str(error)[:80]))

            summary = {
                "namizəd vahid (Level/Xaric)": len(unit_decisions),
                "mark_service namizədi": unit_counters.get("mark_service", 0),
                "artıq texniki (already_service)": unit_counters.get("already_service", 0),
                "istisna (skip_large_holding)": unit_counters.get("skip_large_holding", 0),
                "FAKTİKİ işarələnən": marked,
                "namizəd tələbə qeydi (xaric konteyneri)": len(record_decisions),
                "expel namizədi": record_counters.get("expel", 0),
                "artıq xaric (already_expelled)": record_counters.get("already_expelled", 0),
                "FAKTİKİ xaric edilən": expelled,
                "uğursuz": len(failed),
            }
            self.stdout.write(render_summary("legacy_repair_pseudo_groups", context, summary))
            for label, error in failed[:20]:
                self.stderr.write(f"  ✗ {label}: {error}")
