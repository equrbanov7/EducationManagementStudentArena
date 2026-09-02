"""``legacy_repair_demographics`` — P1: doğum tarixi, cins, profil qrup nömrəsi.

Dry-run DEFAULT-dur.  Qayda ``services.repair_demographics`` sənədindədir.

    manage.py legacy_repair_demographics --organization myedu-univ
    manage.py legacy_repair_demographics --organization myedu-univ --apply
    manage.py legacy_repair_demographics --organization myedu-univ --from-source --apply
"""

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand, CommandError

from apps.audit.public import log_action
from apps.legacy_import.services import repair_demographics
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)
from core.constants import AuditAction
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Profil demoqrafiyasını (doğum tarixi/cins) və qrup nömrəsini doldurur — yalnız BOŞ sahələri."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--from-source",
            action="store_true",
            help="Doğum tarixi/cinsi legacy MariaDB mənbəsindən oxu (settings-dəki opt-in konfiqurasiya ilə)",
        )
        parser.add_argument("--skip-group-number", action="store_true", help="student_group_number doldurulmasın")

    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1): bütün DB işi bir
        # worker-atomic sərhədi içindədir. Sətir-səviyyəli fail-open semantikası
        # dəyişmir — servislərdəki daxili ``transaction.atomic()`` savepoint olur.
        with rls_worker_atomic():
            context = build_context(options)
            before = repair_demographics.target_coverage(context.organization)

            candidates = []
            if not options["skip_group_number"]:
                candidates = repair_demographics.group_number_candidates(context.organization, limit=context.limit)

            source_seen = source_written = 0
            group_written = 0
            if context.apply:
                if candidates:
                    group_written = repair_demographics.write_group_numbers(context.organization, candidates)
                if options["from_source"]:
                    from apps.legacy_import.services.rehearsal_phase_a import default_source_factory

                    try:
                        factory = default_source_factory(django_settings)
                    except Exception as error:  # noqa: BLE001
                        raise CommandError(f"legacy_repair_source_unavailable: {error}") from None
                    source_seen, source_written = repair_demographics.apply_source_demographics(
                        context.organization, connection_factory=factory, limit=context.limit
                    )
                if group_written or source_written:
                    log_action(
                        action=AuditAction.UPDATE,
                        user=context.actor,
                        organization=context.organization,
                        obj=context.organization,
                        new_values={
                            "student_group_number_written": group_written,
                            "demographics_written": source_written,
                        },
                        reason=repair_demographics.AUDIT_REASON,
                    )
            elif options["from_source"]:
                self.stdout.write("[dry-run] mənbə oxunuşu atlandı (--apply olmadan bağlantı açılmır)")

            after = repair_demographics.target_coverage(context.organization)
            rows = [
                ("birth_date", before["birth_date"], "mənbə" if options["from_source"] else "—", after["birth_date"]),
                ("gender", before["gender"], "mənbə" if options["from_source"] else "—", after["gender"]),
                (
                    "student_group_number",
                    before["student_group_number"],
                    len(candidates),
                    after["student_group_number"],
                ),
            ]
            self.stdout.write(render_table(repair_demographics.TABLE_HEADERS, rows))
            self.stdout.write(
                render_summary(
                    "legacy_repair_demographics",
                    context,
                    {
                        "profil sayı": before["profil"],
                        "qrup nömrəsi namizədi": len(candidates),
                        "qrup nömrəsi yazıldı": group_written,
                        "mənbədən oxunan demoqrafiya": source_seen,
                        "demoqrafiya yazıldı": source_written,
                    },
                )
            )
