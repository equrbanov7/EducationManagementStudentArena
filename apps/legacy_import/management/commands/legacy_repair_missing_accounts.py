"""``legacy_repair_missing_accounts`` — P0-2: hesabı olmayan 114 insanı bərpa et.

Dry-run DEFAULT-dur.  Qayda və qalıq işin dəqiq siyahısı
``apps.legacy_import.services.repair_accounts`` sənədindədir.

Mənbə bağlantısı ŞƏRTDİR: hesabın adı/soyadı yalnız legacy MariaDB-dən oxunur
(uydurulmur).  Bağlantı ``settings``-dəki opt-in konfiqurasiyadan qurulur — eyni
yol ``legacy_import_rehearse`` üçün də istifadə olunur.

    manage.py legacy_repair_missing_accounts --organization myedu-univ
    manage.py legacy_repair_missing_accounts --organization myedu-univ --apply
"""

from collections import Counter

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.services import repair_accounts, repair_sar
from apps.legacy_import.services.repair_support import (
    add_repair_arguments,
    build_context,
    render_summary,
    render_table,
)
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "E-poçt qüsuruna görə hesabı yaradılmamış legacy tələbə/işçilər üçün hesab + üzvlük qurur."

    def add_arguments(self, parser):
        add_repair_arguments(parser)
        parser.add_argument("--show", type=int, default=40, help="Cədvəldə göstəriləcək sətir sayı")
        parser.add_argument(
            "--with-sar",
            action="store_true",
            help="Hesabla birlikdə akademik qeydi (SAR: qrup/proqram/kurikulum/qəbul ili) də yarat (R-9)",
        )
        parser.add_argument(
            "--skip-journal-reattach",
            action="store_true",
            help="Yeni müəllim hesablarını müəllimsiz açılışlara bağlamaq addımını atla",
        )

    def handle(self, *args, **options):
        # RLS transaction-pooling təhlükəsizliyi (FAZA 4/Task 1): bütün DB işi bir
        # worker-atomic sərhədi içindədir. Sətir-səviyyəli fail-open semantikası
        # dəyişmir — servislərdəki daxili ``transaction.atomic()`` savepoint olur.
        with rls_worker_atomic():
            context = build_context(options)
            from apps.legacy_import.services.rehearsal_phase_a import default_source_factory

            try:
                factory = default_source_factory(django_settings)
            except Exception as error:  # noqa: BLE001
                raise CommandError(f"legacy_repair_source_unavailable: {error}") from None

            plan = repair_accounts.plan_missing(context.organization, connection_factory=factory, limit=context.limit)
            counters = Counter(item.action for item in plan)
            by_type = Counter(item.entity_type for item in plan if item.action == "create")
            self.stdout.write(
                render_table(
                    repair_accounts.TABLE_HEADERS, [item.as_row() for item in plan], max_rows=int(options["show"])
                )
            )

            created = 0
            teacher_users: dict[int, int] = {}
            student_rows: list[tuple[int, int, str, object]] = []
            failed: list[tuple[str, str]] = []
            attached = 0
            sar_created = 0
            sar_sources: Counter = Counter()
            if context.apply:
                for item in plan:
                    if item.action != "create":
                        continue
                    try:
                        user = repair_accounts.create_account(
                            organization=context.organization, actor=context.actor, item=item
                        )
                    except Exception as error:  # noqa: BLE001
                        failed.append((item.username, type(error).__name__ + ":" + str(error)[:80]))
                        continue
                    created += 1
                    if item.entity_type == "worker":
                        teacher_users[item.legacy_pk] = user.pk
                    else:
                        student_rows.append((item.legacy_pk, user.pk, item.username, item.projected_row))
                if teacher_users and not options["skip_journal_reattach"]:
                    attached = repair_accounts.reattach_journals(
                        context.organization, connection_factory=factory, teacher_users=teacher_users
                    )

            # R-9: SAR mərhələsi hesabdan SONRA gəlir — ``registrar_guard_active_member``
            # aktiv hesab + aktiv üzvlük tələb edir, əks halda sətri rədd edir.
            sar_rows = []
            if options["with_sar"]:
                # Bu icrada yaradılanlar + ƏVVƏLKİ icradan qalan hesablar: R-9
                # məhz artıq mövcud 100 hesabın SAR-sız qalmasıdır, ona görə
                # "already_present" sətirlər də namizəddir (SAR-ı olanları
                # ``repair_sar.plan_records`` özü kənara qoyur).
                known = dict(student_rows and [(row[0], row[1]) for row in student_rows] or [])
                if not context.apply:
                    known = {}
                resolved = repair_accounts.resolve_student_user_pks(
                    context.organization,
                    [item for item in plan if item.entity_type == "student"],
                    known=known,
                )
                sar_rows = [
                    (item.legacy_pk, resolved[item.legacy_pk], item.username, item.projected_row)
                    for item in plan
                    if item.entity_type == "student" and item.legacy_pk in resolved
                ]
                if context.apply and sar_rows:
                    sar_created, sar_sources = repair_sar.materialise(
                        context.organization,
                        sar_rows,
                        fin_occurrences=repair_accounts.student_fin_occurrences(factory),
                    )

            summary = {
                "hesabsız legacy sətri": len(plan),
                "yaradılacaq (create)": counters.get("create", 0),
                "  tələbə": by_type.get("student", 0),
                "  işçi": by_type.get("worker", 0),
                "onsuz da var": counters.get("already_present", 0),
                "FAKTİKİ yaradılan": created,
                "müəllim bağlanan açılış": attached,
                **(
                    {
                        "SAR namizədi": len(sar_rows),
                        "SAR yaradıldı": sar_created,
                        **{f"  SAR {key}": value for key, value in sorted(sar_sources.items())},
                    }
                    if options["with_sar"]
                    else {}
                ),
                "uğursuz": len(failed),
            }
            self.stdout.write(render_summary("legacy_repair_missing_accounts", context, summary))
            self.stdout.write(
                "\nQALIQ İŞ: Enrollment və jurnal xanaları bu əmrlə YARADILMIR — onlar faza\n"
                "zəncirinin (J1…J9) məhsuludur və yalnız növbəti TAM repetisiyada hədəfə\n"
                "düşür. --with-sar yalnız akademik qeydi (qrup/proqram/kurikulum/il) qurur."
            )
            for username, error in failed[:20]:
                self.stderr.write(f"  ✗ {username}: {error}")
