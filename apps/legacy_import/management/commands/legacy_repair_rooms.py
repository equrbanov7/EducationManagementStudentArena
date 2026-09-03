"""``legacy_repair_rooms`` — R-5: legacy otaq reyestrini hədəfə gətirir.

Dry-run DEFAULT-dur.  Xəritələmə ``legacy_rooms`` (J10) fazasının ÖZ saf
funksiyalarındandır — bax `services.repair_rooms` sənədinə.

    manage.py legacy_repair_rooms --organization myedu-univ --from-source
    manage.py legacy_repair_rooms --organization myedu-univ --from-source --apply
"""

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand, CommandError

from apps.audit.public import log_action
from apps.legacy_import.services import repair_rooms
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)
from core.constants import AuditAction
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Legacy otaq reyestrini (rooms) exams.ExamRoom-a gətirir — dərs modalındakı korpus/otaq seçimi üçün."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument(
            "--from-source",
            action="store_true",
            help="Otaqları legacy MariaDB mənbəsindən oxu (settings-dəki opt-in konfiqurasiya ilə)",
        )
        parser.add_argument("--show", type=int, default=15, help="Cədvəldə göstəriləcək sətir sayı")

    def handle(self, *args, **options):
        with rls_worker_atomic():
            context = build_context(options)
            before = repair_rooms.coverage(context.organization)
            if not options["from_source"]:
                self.stdout.write(
                    render_summary(
                        "legacy_repair_rooms",
                        context,
                        {**{f"hədəfdə {key}": value for key, value in before.items()}, "qeyd": "--from-source verin"},
                    )
                )
                return

            from apps.legacy_import.services.rehearsal_phase_a import default_source_factory

            try:
                factory = default_source_factory(django_settings)
            except Exception as error:  # noqa: BLE001
                raise CommandError(f"legacy_repair_source_unavailable: {error}") from None

            plan = repair_rooms.plan_rooms(context.organization, connection_factory=factory, limit=context.limit)
            self.stdout.write(
                render_table(
                    repair_rooms.TABLE_HEADERS, [item.as_row() for item in plan], max_rows=int(options["show"])
                )
            )

            created = 0
            if context.apply:
                created = repair_rooms.materialise(
                    context.organization, connection_factory=factory, limit=context.limit
                )
                if created:
                    log_action(
                        action=AuditAction.CREATE,
                        user=context.actor,
                        organization=context.organization,
                        obj=context.organization,
                        new_values={"exam_rooms_created": created},
                        reason=repair_rooms.AUDIT_REASON,
                    )

            after = repair_rooms.coverage(context.organization)
            self.stdout.write(
                render_summary(
                    "legacy_repair_rooms",
                    context,
                    {
                        "mənbə otağı": len(plan),
                        "yaradılacaq (create)": sum(1 for item in plan if item.action == "create"),
                        "onsuz da var": sum(1 for item in plan if item.action == "already_present"),
                        "FAKTİKİ yaradılan": created,
                        "hədəf otaq (əvvəl → sonra)": f"{before['otaq']} → {after['otaq']}",
                        "korpus sayı": after["korpus"],
                    },
                )
            )
