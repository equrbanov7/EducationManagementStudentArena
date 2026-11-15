"""``reinstate_part_time_graduates_20261115`` — səhvən «Məzun» edilmiş qiyabi tələbələri bərpa edir (sahib 2026-11-15).

Hal: köçürmənin ``graduation`` fazası (``MZN-SINX-2026``) proqram müddətini hamı üçün 4 il saydı — 2022 qəbulu
qiyabi bakalavrlar (qrup adında 4 rəqəm, məs. «2032P») «müddəti bitib» deyə məzun edildi. Sahib: «onlar məzun
deyillər … 2021-ci il daxil olmaqla qiyabilər 5 il, bəlkə 6 il təhsil ala bilər». Fazanın qaydası düzəldildi
(``legacy_import.services.delta.graduation.study_years``); bu əmr artıq yazılmış məzun etmələri geri qaytarır.

NAMİZƏD (hamısı birlikdə): akademik qeyd ``graduated``; onu məzun edən SON əmr köçürmənin toplu əmridir
(``MZN-SINX-2026`` — əl ilə verilmiş məzun etmələrə toxunulmur); bakalavr (magistr deyil); qiyabi (qeydin forması
və ya qrup adının qaydası, ``group_rule_form``); qəbul ili ``--min-year``-dən (defolt 2021) kiçik deyil;
qrupu var və qrup aktivdir (arxivdəki qrup → ``skip_group_inactive``, hesabatda qrup adı ilə).

Hər namizəd üçün RİM-in «Bərpa et» düyməsi ilə EYNİ rəsmi axın: ``reinstatement`` əmri (``BRP-SINX-2026``, bu
günün tarixi) eyni qrupa → hesabın girişi açılır (``_reopen_access``, sübut = əmr) → tələbə qrupun cari semestr
jurnallarına əlavə olunur (``registrar.student_group_journals`` — yalnız əlavə edir).

* DEFOLT DRY-RUN; ``--apply`` yazır; paket ``ptgrad-YYYYMMDD-HHMMSS-xxxx`` audit sətrindədir (qeyd id-ləri).
* ``--undo <paket> --apply`` — paketdəki hələ ``enrolled`` olan qeydləri yenidən ``MZN-SINX-2026`` ilə məzun edir.
* Stdout-a YALNIZ saylar və qrup adları (``pt_grad: açar=dəyər …``) — tələbə adı çap olunmur.

    manage.py reinstate_part_time_graduates_20261115 --org qku --actor <superadmin> [--min-year 2021] [--apply]
"""

from __future__ import annotations

import datetime
import re
import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

BATCH_RE = re.compile(r"^ptgrad-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
RESOURCE = "registrar.part_time_reinstate_batch"
PREFIX = "pt_grad:"
SYNC_ORDER = "MZN-SINX-2026"
SYNC_ORDER_DATE = datetime.date(2026, 7, 1)
#: Köçürmənin «qəbul ili bilinmir» sentineli (``legacy_import`` ``UNKNOWN_ADMISSION_YEAR``).
UNKNOWN_ADMISSION_YEAR = 1950
ORDER_NUMBER = "BRP-SINX-2026"
REASON = "Bərpa — köçürmədə qiyabi tələbə səhvən məzun edilmişdi (qiyabi təhsil 5–6 ildir; sahibin 2026-11-15 qərarı)"
UNDO_REASON = "reinstate_part_time_graduates_20261115 geri qaytarma — yenidən məzun"


class _DryRunRollback(Exception):
    pass


def new_batch() -> str:
    return f"ptgrad-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _last_graduation(movement_model, organization, record_ids) -> dict:
    last = {}
    for movement in (
        movement_model.objects.filter(organization=organization, record_id__in=record_ids, kind="graduation")
        .only("record_id", "order_number", "created_at")
        .order_by("-created_at")
    ):
        last.setdefault(movement.record_id, movement)
    return last


def candidates(
    organization, *, min_year: int, counts: Counter, skipped_groups: Counter, include_unknown: bool = False
) -> list:
    from apps.organizations.public import group_rule_form

    PART_TIME = "part_time"

    def record_education_form(record) -> str:
        # ``legacy_import.services.delta.graduation.record_education_form`` ilə eyni qayda (modul dövrü olmasın deyə).
        if record.education_form == PART_TIME:
            return PART_TIME
        if record.group is not None and group_rule_form(record.group)[0] == PART_TIME:
            return PART_TIME
        return record.education_form

    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    movement_model = django_apps.get_model("registrar", "StudentMovement")
    records = list(
        record_model.objects.filter(organization=organization, status="graduated")
        .select_related("student", "program", "group")
        .order_by("pk")
    )
    last = _last_graduation(movement_model, organization, [record.pk for record in records])
    chosen = []
    for record in records:
        movement = last.get(record.pk)
        if movement is None or movement.order_number != SYNC_ORDER:
            continue
        if getattr(record.program, "degree_level", "") == "master":
            continue
        if record_education_form(record) != PART_TIME:
            continue
        counts["part_time_sync_graduated"] += 1
        year = int(record.admission_year or 0)
        # Sahib 2026-11-15: qəbul ili bilinməyən (köçürmə sentineli 1950 və ya boş) qiyabilər də məzun deyil — bərpa.
        unknown = year <= UNKNOWN_ADMISSION_YEAR
        if year < min_year and not (include_unknown and unknown):
            counts[f"skip_year_{year or 'unknown'}"] += 1
            continue
        if record.group is None:
            counts["skip_no_group"] += 1
            continue
        if not record.group.is_active:
            counts["skip_group_inactive"] += 1
            skipped_groups[record.group.name] += 1
            continue
        chosen.append(record)
    return chosen


def reinstate(
    organization,
    *,
    actor,
    min_year: int,
    batch: str,
    groups: Counter,
    skipped_groups: Counter,
    include_unknown: bool = False,
) -> Counter:
    from apps.accounts.services.people.movements import _reopen_access
    from apps.registrar.public import movements as domain
    from apps.registrar.public import student_group_journals

    profile_model = django_apps.get_model("accounts", "UserProfile")
    counts = Counter(reinstated=0)
    period = student_group_journals.current_period(organization)
    today = timezone.localdate()
    done = []
    for record in candidates(
        organization, min_year=min_year, counts=counts, skipped_groups=skipped_groups, include_unknown=include_unknown
    ):
        try:
            with transaction.atomic():
                movement = domain.create_movement(
                    record=record,
                    kind=domain.MovementKind.REINSTATEMENT,
                    order_number=ORDER_NUMBER,
                    order_date=today,
                    reason=REASON,
                    actor=actor,
                    period=period,
                    new_group=record.group,
                )
        except Exception as exc:  # noqa: BLE001 — bir tələbənin rəddi paketi dayandırmır
            code = getattr(exc, "code", "") or type(exc).__name__
            counts[f"failed_{code}"] += 1
            continue
        _reopen_access(record, order_number=movement.order_number, order_date=movement.order_date, actor=actor)
        state = (
            profile_model.objects.filter(user_id=record.student_id)
            .order_by("-organization_id")
            .values_list("access_state", flat=True)
            .first()
        )
        counts["access_still_archived" if state == "archived" else "access_open"] += 1
        journal_counts = Counter()
        student_group_journals.sync_student(
            organization=organization, actor=actor, student_id=record.student_id, counts=journal_counts, period=period
        )
        for key, value in journal_counts.items():
            counts[f"journal_{key}"] += value
        counts["reinstated"] += 1
        counts[f"year_{record.admission_year}"] += 1
        groups[record.group.name] += 1
        done.append(str(record.pk))
    if done:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"records": done},
            reason=f"reinstate_part_time_graduates_20261115 {batch}",
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=batch,
        )
    return counts


def undo(organization, batch, *, actor) -> Counter:
    from apps.registrar.public import movements as domain

    audit_model = django_apps.get_model("audit", "AuditLog")
    entry = audit_model.objects.filter(resource_type=RESOURCE, resource_id=batch).order_by("-pk").first()
    if entry is None:
        raise CommandError("batch_not_found")
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    counts = Counter(regraduated=0)
    ids = (entry.new_values or {}).get("records", [])
    for record in record_model.objects.filter(organization=organization, pk__in=ids, status="enrolled"):
        try:
            with transaction.atomic():
                domain.create_movement(
                    record=record,
                    kind=domain.MovementKind.GRADUATION,
                    order_number=SYNC_ORDER,
                    order_date=SYNC_ORDER_DATE,
                    reason=UNDO_REASON,
                    actor=actor,
                )
        except Exception as exc:  # noqa: BLE001
            counts[f"failed_{getattr(exc, 'code', '') or type(exc).__name__}"] += 1
            continue
        counts["regraduated"] += 1
    counts["skipped_not_enrolled"] = (
        len(ids) - counts["regraduated"] - sum(value for key, value in counts.items() if key.startswith("failed_"))
    )
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"undo": batch, "regraduated": counts["regraduated"]},
        reason=f"reinstate_part_time_graduates_20261115 undo {batch}",
        resource_type=RESOURCE,
        resource_id=f"{batch}-undo",
        resource_repr=batch,
    )
    return counts


def failure_code(exc) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"pt_grad_failed_{text}"[:120]


def _groups_line(label: str, groups: Counter) -> str:
    return f"{PREFIX} {label}=" + ",".join(f"{name}:{count}" for name, count in sorted(groups.items()))


class Command(BaseCommand):
    help = "Səhvən məzun edilmiş qiyabi tələbələri bərpa edir və cari jurnallara salır — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--min-year", type=int, default=2021, help="Bu qəbul ilindən (daxil) bərpa et")
        parser.add_argument(
            "--include-unknown-year",
            action="store_true",
            help="Qəbul ili bilinməyən (1950 sentineli) qiyabiləri də bərpa et (sahib 2026-11-15)",
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
        )
        if organization is None:
            raise CommandError("organization_not_found")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        min_year = int(options["min_year"])
        if min_year < 2001 or min_year > 2030:
            raise CommandError("bad_min_year")
        undo_batch = (options["undo"] or "").strip()
        if undo_batch and not BATCH_RE.match(undo_batch):
            raise CommandError("bad_batch")
        batch = new_batch()
        counts, groups, skipped_groups = Counter(), Counter(), Counter()
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo_batch:
                    counts = undo(organization, undo_batch, actor=actor)
                else:
                    counts = reinstate(
                        organization,
                        actor=actor,
                        min_year=min_year,
                        include_unknown=bool(options["include_unknown_year"]),
                        batch=batch,
                        groups=groups,
                        skipped_groups=skipped_groups,
                    )
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız kodu göstərir
            raise CommandError(failure_code(exc)) from exc
        mode = "apply" if options["apply"] else "dry_run"
        shown = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        self.stdout.write(f"{PREFIX} mode={mode} {shown}")
        if groups:
            self.stdout.write(_groups_line("groups", groups))
        if skipped_groups:
            self.stdout.write(_groups_line("inactive_groups", skipped_groups))
        if options["apply"] and not undo_batch and counts.get("reinstated"):
            self.stdout.write(f"{PREFIX} batch={batch}")
