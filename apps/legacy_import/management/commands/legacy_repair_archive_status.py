"""``legacy_repair_archive_status`` — P0-1: səhv arxivlənmiş tələbələri bərpa et.

Dry-run DEFAULT-dur.  Qərar qaydası və nəyin yazıldığı
``apps.legacy_import.services.repair_archive`` modulunun sənədindədir.

    manage.py legacy_repair_archive_status --organization myedu-univ
    manage.py legacy_repair_archive_status --organization myedu-univ --apply

Yalnız HAZIRDA OXUYANLAR (sahib 2026-09-25) — siyahı yazılış bərpası planının
möhürlənmiş başlığından gəlir::

    manage.py legacy_repair_archive_status --organization qku --actor <superadmin> \
        --current-plan <enroll plan>.jsonl.gz --current-plan-sha256 <sha256> \
        [--apply --i-know-this-is-production]
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services.repair_archive import TABLE_HEADERS, apply_decision, plan_decisions
from apps.legacy_import.services.repair_plan_file import RepairPlanError, read_plan_header
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)
from core.rls_pooling import rls_worker_atomic


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
        parser.add_argument(
            "--active-period",
            action="append",
            default=[],
            help='Yalnız bu dövrdə yazılışı olanları bərpa et, məs. "2025/2026 Yaz" (təkrarlana bilər)',
        )
        parser.add_argument(
            "--current-plan",
            default="",
            help="Hazırda oxuyanlar siyahısı: legacy_repair_journal_enrollments planı (.jsonl.gz)",
        )
        parser.add_argument("--current-plan-sha256", default="", help="--current-plan faylının sha256-sı (MƏCBURİ)")
        parser.add_argument("--show", type=int, default=25, help="Cədvəldə göstəriləcək sətir sayı")

    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1): bütün DB işi bir
        # worker-atomic sərhədi içindədir. Sətir-səviyyəli fail-open semantikası
        # dəyişmir — servislərdəki daxili ``transaction.atomic()`` savepoint olur.
        current = self._current_legacy(options)
        with rls_worker_atomic():
            context = build_context(options)
            decisions = plan_decisions(
                context.organization,
                limit=context.limit,
                require_activity=bool(options.get("require_activity")),
                active_periods=tuple(options.get("active_period") or ()),
                current_legacy=current,
            )
            counters = Counter(decision.action for decision in decisions)
            reasons = Counter(decision.reason for decision in decisions)

            self.stdout.write(
                render_table(TABLE_HEADERS, [d.as_row() for d in decisions], max_rows=int(options["show"]))
            )

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
                **({"hazırda oxuyan (plan siyahısı)": len(current)} if current is not None else {}),
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

    @staticmethod
    def _current_legacy(options):
        """``--current-plan`` → planın möhürlənmiş başlığındakı hazırda oxuyan legacy id-ləri."""

        if not options.get("current_plan"):
            return None
        try:
            header = read_plan_header(
                options["current_plan"],
                expected_sha256=options.get("current_plan_sha256") or "",
                repair="journal_enrollments",
            )
        except RepairPlanError as error:
            raise CommandError(error.code) from None
        listed = header.get("current_legacy_students")
        if not isinstance(listed, dict) or not listed:
            raise CommandError("legacy_repair_current_list_missing")
        return {str(legacy) for legacy in listed}
