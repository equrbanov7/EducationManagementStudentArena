"""RİM müraciətləri 2026-11-16 — üç düzəliş, hər biri öz savepoint-ində (``repair_applications_20261116``).

* **A — MR-000393** (2132T): qrupun seçmə bloku «Genderin tarixi» əvəzinə «Sosial tarix». Qrupun qərarı RƏSMİ yolla
  dəyişir (``registrar.services.choose_group_elective``), sonra «Sosial tarix» + 2132T yük sətrinin jurnal sinxronu
  (``offering_sync.sync_row_offerings``) jurnalı sətrin müəllimi ilə açır; köhnə «Genderin tarixi» jurnalı YALNIZ dərsi
  yoxdursa passiv olur. Bax :mod:`.applications_repair_2026_11_16_elective`.
* **B — MR-000395** (505/6 MB): tələbə qeydlərinin proqramı «Genetika» → «Malekulyar biologiya» (magistr) + qəbul ilinin
  planı — məlumat girişi düzəlişi (hərəkət əmri deyil), qeyd başına audit. Bax :mod:`.applications_repair_2026_11_16_people`.
* **C — MR-000396** (935 BM): tələbə Günay Əmirovanın «İXD-2» jurnalından Aytac Salmanlının «935 … ing» jurnalına —
  jurnalın «Alt qrupdan tələbə əlavə et» aləti ilə EYNİ servis (``add_guest_student``, ``release_source``), superadmin
  sənəd azadlığı ilə. Köhnə xanalar, giriş balı mənbə qeydiyyatda qalır (varis jurnal onları zəncirlə göstərir), qayıb
  saatı daşınır.

Prod id-ləri koda yazılmır (prefiks axtarışı da yoxdur): hər obyekt AD + ƏLAQƏ ilə tapılır və təkliyi yoxlanılır.
Canlı vəziyyət gözləniləndən fərqlidirsə hissə ATLANIR və sayılır (``a_…`` / ``b_…`` / ``c_…``). Hər yazının audit
sətri ``resource_type`` + ``new_values.batch`` daşıyır; ``undo`` yalnız həmin paketi geri qaytarır.
"""

from __future__ import annotations

import re
import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.constants import OrgUnitType

RESOURCE = "workload.applications_repair_20261116"
RES_ELECTIVE = f"{RESOURCE}.elective"
RES_PROGRAM = f"{RESOURCE}.program"
RES_MOVE = f"{RESOURCE}.move"
RES_PLAN_ROW = f"{RESOURCE}.plan_row"
RES_PLAN_CLONE = f"{RESOURCE}.plan_clone"
RESOURCES = (RES_ELECTIVE, RES_PROGRAM, RES_MOVE, RES_PLAN_ROW, RES_PLAN_CLONE)
BATCH_PREFIX = "apps16"

#: Cari payız semestri («Payız 2026/2027», ``import_timetable_docx.resolve_period`` formatı).
PERIOD = "Payız 2026/2027"

# A — MR-000393
A_GROUP = "2132T"
A_OLD_SUBJECT = "Genderin tarixi"
A_NEW_SUBJECT = "Sosial tarix"

# B — MR-000395
B_GROUP = "505/6 MB"
B_PEER_GROUP = "505/5 MB"
B_FROM_PROGRAM = "Genetika"
B_TO_SPECIALTY = "Malekulyar biologiya"
B_DEGREE = "master"

# C — MR-000396
C_SOURCE_GROUP = "935 BM"
C_SOURCE_TEACHER = ("Günay", "Əmirova")
C_TARGET_TEACHER = ("Aytac", "Salmanlı")
C_TARGET_GROUP_TOKENS = ("935", "ing")
C_STUDENT = ("Kərimli", "Mədinə")

REASONS = {
    "a": "MR-000393: 2132T qrupunun seçmə fənni «Genderin tarixi» əvəzinə «Sosial tarix»",
    "b": "MR-000395: 505/6 MB tələbələrinin ixtisası «Malekulyar biologiya» (məlumat girişi düzəlişi)",
    "c": "MR-000396: tələbə «935 BM İXD-2» jurnalından «935 ing» jurnalına köçürüldü",
}


class Skip(Exception):
    """Hissə gözlənilən vəziyyətdə deyil — savepoint geri qaytarılır, ``code`` sayılır."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"{BATCH_PREFIX}-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def compact(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def tokens(text) -> set:
    return {part.casefold() for part in str(text or "").split()}


def person_has(user, wanted) -> bool:
    if user is None:
        return False
    full = " ".join(
        [
            str(getattr(user, "first_name", "") or ""),
            str(getattr(user, "last_name", "") or ""),
            str(user.get_full_name() or "") if hasattr(user, "get_full_name") else "",
        ]
    )
    return {item.casefold() for item in wanted} <= tokens(full)


def groups_named(organization, label) -> list:
    """Qrup — ad boşluqdan asılı olmadan (``2132T`` = ``2132 T``)."""
    head = str(label).split()[0][:3]
    rows = model("organizations", "OrgUnit").objects.filter(
        organization=organization, unit_type=OrgUnitType.GROUP, name__istartswith=head
    )
    return [row for row in rows if compact(row.name) == compact(label)]


def one_group(organization, label, code: str):
    found = groups_named(organization, label)
    if len(found) != 1:
        raise Skip(code)
    return found[0]


def resolve_period(organization):
    """``PERIOD`` → ``AcademicPeriod`` (ad + tədris ili, tək olmalıdır)."""
    match = re.fullmatch(r"(.+?)\s+(\d{4})\s*[/-]\s*(\d{4})", " ".join(PERIOD.split()))
    if not match:
        return None
    name, start, end = match.groups()
    found = [
        period
        for period in model("organizations", "AcademicPeriod").objects.filter(
            organization=organization, name__iexact=name.strip()
        )
        if re.sub(r"\D", "", period.academic_year or "") == f"{start}{end}"
    ]
    return found[0] if len(found) == 1 else None


def guarded(key: str, counts: Counter, func, **kwargs) -> None:
    """Bir hissə = bir savepoint. ``Skip`` / servis imtinası → hissənin bütün yazıları və sayları geri qaytarılır."""
    snapshot = Counter(counts)
    try:
        with transaction.atomic():
            func(counts=counts, **kwargs)
    except Skip as exc:
        counts.clear()
        counts.update(snapshot)
        counts[f"{key}_skipped"] += 1
        counts[f"{key}_{exc.code}"] += 1
    except (ValidationError, IntegrityError):
        counts.clear()
        counts.update(snapshot)
        counts[f"{key}_skipped"] += 1
        counts[f"{key}_refused"] += 1


def audit(*, actor, organization, resource_type, resource_id, repr_, reason, old_values, new_values) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=reason,
        resource_type=resource_type,
        resource_id=str(resource_id),
        resource_repr=repr_,
        old_values=old_values,
        new_values=new_values,
    )


def run(*, organization, actor, counts: Counter, batch: str = "") -> str:
    from . import applications_repair_2026_11_16_elective as elective
    from . import applications_repair_2026_11_16_people as people
    from . import applications_repair_2026_11_16_plans as plans

    batch = batch or new_batch()
    period = resolve_period(organization)
    if period is None:
        counts["period_unresolved"] += 1
        return batch
    common = {"organization": organization, "actor": actor, "period": period, "batch": batch}
    # Sahib 2026-11-17 («et»): A / B-dən ƏVVƏL plan hazırlığı (bax ``_plans``) — öz savepoint-ində.
    guarded("pa", counts, plans.prepare_block, **common)
    guarded("pb", counts, plans.prepare_plans, **common)
    guarded("a", counts, elective.apply, **common)
    guarded("b", counts, people.apply_programs, **common)
    guarded("c", counts, people.apply_move, **common)
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from . import applications_repair_2026_11_16_elective as elective
    from . import applications_repair_2026_11_16_people as people
    from . import applications_repair_2026_11_16_plans as plans

    rows = list(
        model("audit", "AuditLog")
        .objects.filter(organization=organization, resource_type__in=RESOURCES, new_values__batch=batch)
        .order_by("-created_at", "-pk")
    )
    handlers = {
        RES_ELECTIVE: elective.undo,
        RES_PROGRAM: people.undo_program,
        RES_MOVE: people.undo_move,
        RES_PLAN_ROW: plans.undo_row,
        RES_PLAN_CLONE: plans.undo_clone,
    }
    keys = {RES_ELECTIVE: "a", RES_PROGRAM: "b", RES_MOVE: "c", RES_PLAN_ROW: "pa", RES_PLAN_CLONE: "pb"}
    for row in rows:
        key = keys[row.resource_type]
        counts[f"{key}_undo_rows"] += 1
        guarded(
            f"{key}_undo",
            counts,
            handlers[row.resource_type],
            organization=organization,
            actor=actor,
            row=row,
            batch=batch,
        )
