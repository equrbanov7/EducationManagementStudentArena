"""``legacy_repair_current_period`` — P0-3: tenant-ın cari akademik dövrü.

Dry-run DEFAULT-dur.  Qərar qaydası ``services.repair_periods`` sənədindədir.

    manage.py legacy_repair_current_period --organization myedu-univ
    manage.py legacy_repair_current_period --organization myedu-univ \\
        --period "2025/2026 Payız" --apply
    manage.py legacy_repair_current_period --organization myedu-univ \\
        --create-year 2026/2027 --period "2026/2027 Payız" --apply
"""

from django.core.management.base import BaseCommand

from apps.legacy_import.services import repair_periods
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)


class Command(BaseCommand):
    help = "Cari akademik dövrü (AcademicPeriod.is_current) təyin edir; lazım olsa yeni tədris ilini yaradır."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--period",
            default="",
            help='Hansı dövr cari olsun: id, "2025/2026 Payız" və ya fəsil adı. Boşdursa qayda tətbiq olunur.',
        )
        parser.add_argument(
            "--create-year",
            default="",
            help='Yoxdursa bu tədris ilinin üç fəslini yarat (məs. "2026/2027") — cari elan ETMİR.',
        )

    def handle(self, *args, **options):
        context = build_context(options)
        created = []
        if options["create_year"]:
            if context.apply:
                created = repair_periods.create_year(context.organization, options["create_year"])
            else:
                self.stdout.write(f"[dry-run] yaradılacaq tədris ili: {options['create_year']} (Payız/Yaz/Yay)")

        rows = repair_periods.period_rows(context.organization)
        today = repair_periods.today()
        target, reason = repair_periods.select_period(rows, selector=options["period"], today=today)
        self.stdout.write(render_table(repair_periods.TABLE_HEADERS, [row.as_row() for row in rows], max_rows=60))

        changed = False
        if target is not None and context.apply:
            changed = repair_periods.set_current(context.organization, target, actor=context.actor)

        summary = {
            "bugün": today,
            "dövr sayı": len(rows),
            "yaradılan dövr": len(created),
            "seçilən dövr": f"{target.academic_year} {target.name}" if target is not None else "—",
            "seçim səbəbi": reason,
            "bugünü əhatə edən dövr": (
                "var" if repair_periods.containing_period(rows, today) is not None else "YOXDUR"
            ),
            "is_current dəyişdi": "bəli" if changed else "xeyr",
        }
        self.stdout.write(render_summary("legacy_repair_current_period", context, summary))
