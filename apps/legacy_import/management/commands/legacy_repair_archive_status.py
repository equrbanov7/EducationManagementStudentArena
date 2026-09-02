"""``legacy_repair_archive_status`` — P0-1: səhv arxivlənmiş tələbələri bərpa et.

Dry-run DEFAULT-dur.  Qərar qaydası və nəyin yazıldığı
``apps.legacy_import.services.repair_archive`` modulunun sənədindədir.

    manage.py legacy_repair_archive_status --organization myedu-univ
    manage.py legacy_repair_archive_status --organization myedu-univ --apply
"""

from collections import Counter

from django.core.management.base import BaseCommand

from apps.legacy_import.services.repair_archive import TABLE_HEADERS, apply_decision, plan_decisions
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)


class Command(BaseCommand):
    help = "Səhvən arxivlənmiş (məzun sayılmış) cari tələbələri aktiv tələbəyə qaytarır."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--require-activity",
            action="store_true",
            help="Yalnız ən azı bir yazılışı olan tələbəni bərpa et (daha sərt qayda)",
        )
        parser.add_argument(
            "--fix-admission-year",
            action="store_true",
            help="Qəbul ilini ən erkən yazılışın akademik ilindən düzəlt (default: sentinel qalır)",
        )
        parser.add_argument("--show", type=int, default=25, help="Cədvəldə göstəriləcək sətir sayı")

    def handle(self, *args, **options):
        context = build_context(options)
        decisions = plan_decisions(
            context.organization, limit=context.limit, require_activity=bool(options.get("require_activity"))
        )
        counters = Counter(decision.action for decision in decisions)
        reasons = Counter(decision.reason for decision in decisions)

        self.stdout.write(render_table(TABLE_HEADERS, [d.as_row() for d in decisions], max_rows=int(options["show"])))

        changed = 0
        failed: list[tuple[str, str]] = []
        if context.apply:
            for decision in decisions:
                if decision.action != "restore":
                    continue
                try:
                    changed += (
                        1
                        if apply_decision(
                            organization=context.organization,
                            actor=context.actor,
                            decision=decision,
                            fix_admission_year=bool(options.get("fix_admission_year")),
                        )
                        else 0
                    )
                except Exception as error:  # noqa: BLE001 — sətir-səviyyə fail-open hesabatı
                    failed.append((decision.username, type(error).__name__ + ":" + str(error)[:80]))

        summary = {
            "arxivdə olan profil": len(decisions),
            "bərpa namizədi (restore)": counters.get("restore", 0),
            "toxunulmur (keep_archived)": counters.get("keep_archived", 0),
            **{f"  səbəb: {key}": value for key, value in sorted(reasons.items())},
            "FAKTİKİ bərpa olunan": changed,
            "uğursuz": len(failed),
        }
        self.stdout.write(render_summary("legacy_repair_archive_status", context, summary))
        for username, error in failed[:20]:
            self.stderr.write(f"  ✗ {username}: {error}")
