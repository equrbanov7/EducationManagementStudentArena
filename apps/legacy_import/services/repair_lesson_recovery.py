"""J12 təmiri — ARTIQ köçürülmüş hədəf üçün itən dərs slotlarının bərpası (plan qatı).

Problem (ölçülüb, prod nüsxəsi 2026-09-25)
------------------------------------------
Production 2026-08-27 run-undan (``rehearsal-identity-v1``, 17 faza) qurulub;
J12 (``journal_lesson_recovery``) o vaxt registrdə YOX idi.  Nəticə:
``registrar_lesson.is_legacy_synthesised`` = **0 sətir** — köhnə sistemdə dərs
cədvəli sətri olmayan günlərin xanaları (rəqəmli bal, qayıb, iştirak) heç bir
ekranda görünmür (``BAL_PROBLEMLERI.md`` K10/K10b).  HANDOFF §8.5 P1-1 «ayrıca
təmir əmri yazılmadı, tam repetisiya lazımdır» deyirdi — amma production artıq
canlıdır (2026/2027 datası, ad.soyad hesabları), tam repetisiya ilə əvəz edilə
bilməz.

Niyə fazanın özü sadəcə «təkrar işə salınmır»
---------------------------------------------
J12-nin hər oxu indeksi (açılış, qeydiyyat, dərs xəritəsi) ``run_id``-yə bağlı
ledger müşahidələrindən qurulur, möhür isə yalnız RUNNING run-a yazıla bilər
(``ledger._require_active_run``).  Hədəfi qurmuş run ``succeeded``-dir.  Ona
görə:

* ATILABİLƏN klonda yeni «plan run»-u açılır (möhürlər ora yazılır);
* J12-nin ÖZ kodu dəyişmədən işləyir — yeganə fərq ``_resolution`` hook-udur:
  J4-ün həll indeksləri hədəfi QURAN orijinal import run-una bağlanır;
* faza bitəndən sonra klonda YENİ yaranan sətirlər (bərpa dərsləri, xanalar,
  uduzan-dəyər sübutları) plan faylına çıxarılır (``repair_plan_file``).

Serverdə mənbə lazım deyil: plan ``repair_lesson_recovery_apply`` ilə canlı
bazaya qarşı yenidən yoxlanılaraq tətbiq olunur.

Qapılar
-------
* Plan qurmaq YALNIZ ``emsarena.rehearsal_target='disposable'`` markerli bazada
  mümkündür — ``--i-know-this-is-production`` bu addımda QƏBUL EDİLMİR, çünki
  faza klona real yazır.
* Mənbə ``default_source_factory`` ilə (``LEGACY_MARIADB_SOURCE_*`` opt-in),
  ``@@GLOBAL.read_only=1`` və sətir sayları table-plan ilə dəqiq tutuşmalıdır
  (``attested_rows`` fail-closed).  Dump faylı verilirsə sha256-sı da yoxlanılır.
"""

from __future__ import annotations

import dataclasses
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.apps import apps as django_apps
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue, LegacyMigrationRun

from .ledger import create_run, finish_run, start_run
from .rehearsal_authorizer import build_bulk_target_validators, build_rehearsal_authorizer, build_target_validators
from .rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    SOURCE_SYSTEM,
    EmailTrustPolicy,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from .rehearsal_journal_lessons_phase import JOURNAL_LESSONS_PHASE_KEY
from .rehearsal_journal_marks_phase import JOURNAL_MARKS_PHASE_KEY, build_resolution
from .rehearsal_journal_points_source import POINT_ARCHIVE_TABLE, POINT_SOURCE_TABLE
from .rehearsal_lesson_recovery_phase import JOURNAL_LESSON_RECOVERY_PHASE_KEY, JournalLessonRecoveryPhase
from .rehearsal_lesson_recovery_targets import LESSON_SYNTH_ENTITY_TYPE
from .repair_plan_file import RepairPlanError, write_plan
from .repair_support import database_is_disposable_target, disable_parallel_query
from .table_plan import SOURCE_SNAPSHOT_SHA256, TABLE_PLAN_VERSION, load_legacy_table_plan

REPAIR_KEY = "lesson_recovery"
AUDIT_REASON = "legacy_repair:lesson_recovery"
#: Plan run-unun transform ailəsi — sübut faktlarında «bu sətri təmir yazıb» izi.
REPAIR_TRANSFORM_FAMILY = "legacy-repair-j12-v1"
PLAN_RUN_END_CODE = "legacy_repair_plan_extracted"
PLAN_RUN_FAILED_CODE = "legacy_repair_plan_failed"
REPAIR_PHASE_KEYS = (JOURNAL_LESSONS_PHASE_KEY, JOURNAL_MARKS_PHASE_KEY, JOURNAL_LESSON_RECOVERY_PHASE_KEY)
#: Hədəfi quran import run-unun məqbul statusu (production-da yalnız ``succeeded``).
SOURCE_RUN_STATUSES = (LegacyMigrationRun.Status.SUCCEEDED,)

_FACT_FIELDS = (
    "source_system",
    "source_table",
    "source_pk",
    "source_snapshot_sha256",
    "source_row_hash",
    "materialization_digest",
    "transform_version",
    "evidence_kind",
    "score_code",
    "is_archive",
    "mapping_status",
    "mapping_issue_code",
    "source_student_ref",
    "source_journal_ref",
    "source_lesson_ref",
    "source_group_ref",
    "source_enrollment_ref",
    "entry_score_text",
    "exam_score_text",
    "resit_score_text",
    "final_score_text",
    "raw_score_text",
    "entry_score",
    "exam_score",
    "resit_score",
    "final_score",
    "legacy_kesr",
    "legacy_level",
    "legacy_guzest_girish_text",
    "legacy_guzest_artim_text",
    "requires_exam_center_review",
    "enrollment_id",
    "legacy_attempt_type",
    "legacy_recorded_at_text",
)


class RealTargetLessonRecoveryPhase(JournalLessonRecoveryPhase):
    """J12 — dəyişməz; yalnız J4 həll indeksləri ORİJİNAL import run-undan oxunur."""

    def __init__(self, *, source_run_id) -> None:
        self._source_run_id = source_run_id

    def _resolution(self, context):
        return build_resolution(dataclasses.replace(context, run_id=self._source_run_id))


@dataclass(frozen=True)
class PlanBuildResult:
    manifest: object
    report: object
    notes: tuple[str, ...]
    planning_run_id: str
    source_run_id: str


def resolve_source_run(organization, run_id: str = "") -> LegacyMigrationRun:
    """Hədəfi QURAN import run-u: bu tenant, bu snapshot, ``succeeded``, tək."""

    runs = LegacyMigrationRun.objects.filter(
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=SOURCE_SNAPSHOT_SHA256,
        status__in=SOURCE_RUN_STATUSES,
    ).exclude(transform_version__startswith=f"{REPAIR_TRANSFORM_FAMILY}.")
    if run_id:
        runs = runs.filter(pk=run_id)
    found = list(runs.order_by("created_at")[:2])
    if not found:
        raise RepairPlanError("legacy_repair_source_run_missing")
    if len(found) > 1:
        raise RepairPlanError("legacy_repair_source_run_ambiguous")
    return found[0]


def repair_policy() -> RehearsalPolicy:
    """J12-nin tələb etdiyi minimal siyasət (hesab/identity addımı yoxdur)."""

    return RehearsalPolicy(
        phase_keys=REPAIR_PHASE_KEYS,
        username_policy=UsernamePolicy.LEGACY_KEY,
        student_identifier_policy=StudentIdentifierPolicy.LEGACY_PK,
        email_trust_policy=EmailTrustPolicy.DENY_ALL,
        email_trust_manifest_digest="",
        batch_rows=DEFAULT_BATCH_ROWS,
        source_chunk_size=1_000,
        max_staged_accounts=0,
        student_role_name="",
        worker_role_name="",
    )


def _code_revision() -> str:
    """Planı quran kodun git HEAD-i (sübut üçün); tapılmasa boş."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _open_planning_run(*, organization, actor, source_run, table_plan, policy, authorize):
    rows = table_plan.entry_for(POINT_SOURCE_TABLE).expected_rows
    rows += table_plan.entry_for(POINT_ARCHIVE_TABLE).expected_rows
    run = create_run(
        actor=actor,
        authorize=authorize,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=source_run.snapshot_sha256,
        snapshot_size_bytes=source_run.snapshot_size_bytes,
        # J12-nin yeridiyi mənbə sətirləri (əsas + arxiv xana cədvəli).
        source_row_count=rows,
        schema_version=f"{TABLE_PLAN_VERSION}.{table_plan.fingerprint[:12]}",
        transform_version=f"{REPAIR_TRANSFORM_FAMILY}.{policy.policy_digest()[:12]}",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=authorize)


def _json_value(value):
    """JSON-yə sadiq forma: Decimal elmi notasiyasız mətn, UUID mətn, qalanı olduğu kimi."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def extract_records(organization, *, since, run):
    """Klonda ``since``-dən sonra YARANAN sətirlər — plan faylının gövdəsi.

    Klon şəxsidir və faza yeganə yazandır; buna baxmayaraq hər bərpa dərsi
    ``is_legacy_synthesised`` daşımalıdır, əks halda plan fail-closed olur.
    """

    lesson_model = django_apps.get_model("registrar", "Lesson")
    mark_model = django_apps.get_model("registrar", "LessonMark")
    fact_model = django_apps.get_model("registrar", "LegacyGradeFact")
    seals = dict(
        LegacyEntityMap.objects.filter(
            organization=organization,
            created_run=run,
            entity_type=LESSON_SYNTH_ENTITY_TYPE,
            state=LegacyEntityMap.State.MIGRATED,
        ).values_list("target_pk", "legacy_pk")
    )
    codes: dict[str, set] = {}
    for legacy_pk, rule_code in LegacyMigrationIssue.objects.filter(
        run=run, entity_type=LESSON_SYNTH_ENTITY_TYPE
    ).values_list("legacy_pk", "rule_code"):
        codes.setdefault(legacy_pk, set()).add(rule_code)

    lessons = lesson_model.objects.filter(organization=organization, created_at__gte=since).order_by(
        "offering_id", "date", "start_time", "id"
    )
    for row in lessons.iterator(chunk_size=5_000):
        if not row.is_legacy_synthesised:
            raise RepairPlanError("legacy_repair_plan_foreign_lesson")
        seal_key = seals.get(str(row.pk), "")
        yield {
            "kind": "lesson",
            "pk": str(row.pk),
            "offering_id": str(row.offering_id),
            "date": row.date.isoformat(),
            "start_time": None if row.start_time is None else row.start_time.isoformat(timespec="minutes"),
            "end_time": None if row.end_time is None else row.end_time.isoformat(timespec="minutes"),
            "lesson_kind": row.kind,
            "hours": int(row.hours),
            "topic": row.topic,
            "room_id": row.room_id,
            "instructor_id": row.instructor_id,
            "seal_key": seal_key,
            "rule_codes": sorted(codes.get(seal_key, ())),
        }
    marks = mark_model.objects.filter(organization=organization, created_at__gte=since).order_by(
        "lesson_id", "enrollment_id"
    )
    for lesson_id, enrollment_id, status, score in marks.values_list(
        "lesson_id", "enrollment_id", "status", "score"
    ).iterator(chunk_size=10_000):
        yield {
            "kind": "mark",
            "lesson_id": str(lesson_id),
            "enrollment_id": str(enrollment_id),
            "status": status,
            "score": _json_value(score),
        }
    facts = fact_model.objects.filter(organization=organization, created_at__gte=since).order_by(
        "source_table", "source_pk"
    )
    for values in facts.values(*_FACT_FIELDS).iterator(chunk_size=5_000):
        yield {"kind": "fact", **{key: _json_value(value) for key, value in values.items()}}


def build_plan(
    *, organization, actor, source_factory, out_path: str, source_run_id: str = "", note=print, table_plan=None
):
    """Klonda J12-ni işlət, deltanı plan faylına yaz, plan run-unu bağla.

    ``table_plan`` yalnız testlər üçündür (fake mənbənin öz sətir sayları);
    real icrada kodun attested table-plan-ı işlədilir.
    """

    if not database_is_disposable_target():
        # Faza klona REAL yazır — production-a heç bir bayraqla icazə yoxdur.
        raise RepairPlanError("legacy_repair_plan_target_not_disposable")
    # Faza tranzaksiyaları öz-özünə açılır, ona görə söndürmə SESSİYA səviyyəsindədir
    # (klona birbaşa bağlantı — pgbouncer yoxdur).  Səbəb: ``disable_parallel_query``.
    disable_parallel_query(local=False)
    table_plan = table_plan or load_legacy_table_plan()
    source_run = resolve_source_run(organization, source_run_id)
    policy = repair_policy()
    authorize = build_rehearsal_authorizer()
    run = _open_planning_run(
        organization=organization,
        actor=actor,
        source_run=source_run,
        table_plan=table_plan,
        policy=policy,
        authorize=authorize,
    )
    notes: list[str] = []

    def stdout_note(text: str) -> None:
        notes.append(text)
        note(f"  · {text}")

    context = RehearsalContext(
        run_id=run.pk,
        organization=organization,
        actor=actor,
        authorize=authorize,
        target_validators=build_target_validators(),
        policy=policy,
        plan=table_plan,
        source_connection_factory=source_factory,
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=lambda: False,
        stdout_note=stdout_note,
        bulk_target_validators=build_bulk_target_validators(),
    )
    since = timezone.now()
    try:
        report = RealTargetLessonRecoveryPhase(source_run_id=source_run.pk).run(context)
    except Exception:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=authorize,
            outcome=LegacyMigrationRun.Status.FAILED,
            failure_code=PLAN_RUN_FAILED_CODE,
        )
        raise
    finish_run(
        run_id=run.pk,
        actor=actor,
        authorize=authorize,
        outcome=LegacyMigrationRun.Status.CANCELLED,
        failure_code=PLAN_RUN_END_CODE,
    )
    header = {
        "repair": REPAIR_KEY,
        "organization_id": str(organization.pk),
        "organization_slug": organization.slug,
        "source_system": SOURCE_SYSTEM,
        "source_snapshot_sha256": source_run.snapshot_sha256,
        "source_run_id": str(source_run.pk),
        "source_transform_version": source_run.transform_version,
        "planning_run_id": str(run.pk),
        "planning_transform_version": run.transform_version,
        "code_revision": _code_revision(),
        "generated_at": since.isoformat(),
        "phase_notes": list(notes),
    }
    manifest = write_plan(out_path, header=header, records=extract_records(organization, since=since, run=run))
    return PlanBuildResult(
        manifest=manifest,
        report=report,
        notes=tuple(notes),
        planning_run_id=str(run.pk),
        source_run_id=str(source_run.pk),
    )


__all__ = [
    "AUDIT_REASON",
    "PLAN_RUN_END_CODE",
    "REPAIR_KEY",
    "REPAIR_PHASE_KEYS",
    "REPAIR_TRANSFORM_FAMILY",
    "SOURCE_RUN_STATUSES",
    "PlanBuildResult",
    "RealTargetLessonRecoveryPhase",
    "build_plan",
    "extract_records",
    "repair_policy",
    "resolve_source_run",
]
