"""Phase: ``journal_components`` (J5) — ``k1``/``k2``/``k3``/``si`` → komponent balları.

J0 (``journal_periods``) kimi tək modulludur: mənbə axını ``rehearsal_journal_cells``
sürücüsündən gəlir, hədəf yazısı və möhür isə buradadır.

J-V6 hədəfləri:
* ``k1``/``k2``/``k3`` → ``AssessmentComponent(kind=KOLLOKVIUM)`` "Kollokvium 1..3"
  (``journal_extras.ensure_kollokviums`` ilə EYNİ ad və tavan — köhnə sətri ADLA
  mənimsəyən servis onu heç vaxt təkrar yaratmır);
* ``si`` → ``AssessmentComponent(kind=SELF_WORK)`` "Sərbəst iş"
  (``journal_extras.ensure_selfwork_component`` güzgüsü).

``gradebook_components.save_component_scores(bypass_edit_window=True)``
semantikası güzgülənir, İMPORT EDİLMİR (J1/J3/J4 ilə eyni modul-sərhəd qərarı).
Qorunan invariantlar: xana açarı ``(component, enrollment)`` unikaldır →
həmişə ``get_or_create``; mövcud xana ÜSTÜNDƏN YAZILMIR (2 saat trigger-i
``registrar_componentscore``-a da şamildir və yalnız ``UPDATE``-i tutur, yəni
import xalis ``INSERT`` axını qalır — ``journal_unlock`` GUC-una ehtiyac yoxdur);
``entered_by=None``; jurnal J7-dən əvvəl struktur olaraq kilidsizdir.

Bilinən davranış qeydi (J-V12 seçiminin nəticəsi): ``entry_score_for``
SELF_WORK komponenti üçün balı DEYİL, ``SelfWorkMark`` çeklist sayını oxuyur —
yəni ``si`` balı saxlanılır və komponent bölgüsündə görünür, amma giriş balına
avtomatik əlavə OLUNMUR.  Legacy dəyər qorunur; hesablama qaydası dəyişdirilmir.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import JOURNAL_POINT_FIELDS
from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_cells import JournalCellLedger, drive_cells
from .rehearsal_journal_enrollments_phase import (
    JOURNAL_ENROLLMENT_ENTITY_TYPE,
    JOURNAL_ENROLLMENTS_PHASE_KEY,
)
from .rehearsal_journal_offerings_phase import JOURNAL_OFFERINGS_PHASE_KEY
from .rehearsal_journal_offerings_source import migrated_target_index, validated_uniqid
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_points_source import (
    COMPONENT_MONTHS,
    COMPONENT_SCORE_MAX,
    KOLLOKVIUM_MONTHS,
    SELF_WORK_MONTH,
    legacy_text,
    migrated_index,
    parse_cell_score,
)
from .rehearsal_journal_seal import JournalSealer, state_for, tally_parts
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_COMPONENTS_PHASE_KEY = "journal_components"
JOURNAL_COMPONENTS_PHASE_ORDER = 42  # journal_marks-dan (40) sonra
COMPONENTS_ENTITY_TYPE = "journal_components"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-components-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_OFFERINGS_PHASE_KEY, JOURNAL_ENROLLMENTS_PHASE_KEY})

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

# ``journal_extras`` sabitlərinin güzgüsü: ad, kind və tavan EYNİ olmalıdır.
KOLLOKVIUM_MAX = 10
SELF_WORK_MAX_TOPICS = 10
COMPONENT_PLANS = MappingProxyType(
    {
        "k1": ("Kollokvium 1", "kollokvium", KOLLOKVIUM_MAX, 1),
        "k2": ("Kollokvium 2", "kollokvium", KOLLOKVIUM_MAX, 2),
        "k3": ("Kollokvium 3", "kollokvium", KOLLOKVIUM_MAX, 3),
        SELF_WORK_MONTH: ("Sərbəst iş", "self_work", SELF_WORK_MAX_TOPICS, 4),
    }
)

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "journal_components_materialised",
        _STATE.SKIPPED: "journal_components_skipped",
        _STATE.QUARANTINED: "journal_components_unresolved",
    }
)

# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "legacy_journal_component_code_unknown",
                "legacy_journal_component_score_out_of_range",
                "legacy_journal_component_enrollment_unresolved",
                "legacy_journal_component_target_conflict",
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                "legacy_journal_component_orphan",
                "legacy_journal_component_duplicate",
                "legacy_journal_component_empty",
                "legacy_journal_component_archive_overlap",
            ),
            _SEVERITY.INFO,
        ),
    }
)

OUTCOME_RULES = MappingProxyType(
    {
        "orphan": ("legacy_journal_component_orphan", False),
        "duplicate": ("legacy_journal_component_duplicate", False),
        "empty": ("legacy_journal_component_empty", False),
        "unknown": ("legacy_journal_component_code_unknown", True),
        "range": ("legacy_journal_component_score_out_of_range", True),
        "enrollment": ("legacy_journal_component_enrollment_unresolved", False),
        "conflict": ("legacy_journal_component_target_conflict", False),
        "archive_overlap": ("legacy_journal_component_archive_overlap", False),
    }
)
QUARANTINE_KEYS = tuple(key for key, (_code, fatal) in OUTCOME_RULES.items() if fatal)
WRITTEN_KEYS = ("written", "archive_written")

COMPONENT_SEALER = JournalSealer(
    entity_type=COMPONENTS_ENTITY_TYPE,
    source_table=JOURNAL_POINT_FIELDS.source_table,
    derivation_prefix=b"legacy-rehearsal-journal-components-derivation-v1\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


@dataclass(frozen=True)
class ComponentCell:
    """Bir psevdo-kod xanasının distillə olunmuş forması."""

    legacy_pk: int
    uniqid: str
    student_id: int
    month_id: str
    point: str
    from_archive: bool


def classify_component_cell(point_text: str):
    """``(nəticə, bal)`` — J-V2 üzrə şkala çevrilməsi YOXDUR.

    ``nəticə`` ∈ {empty, scored, unknown, range}.  Canlı mənbədə ``k*``/``si``
    xanalarında ``qb``/``ie``/``l`` kimi davamiyyət kodları da rast gəlinir —
    onlar bal deyil, ona görə ``unknown`` (karantin) olur: heç bir dəyər
    təxminlə bala çevrilmir.
    """

    if point_text == "":
        return "empty", None
    score = parse_cell_score(point_text)
    if score is None:
        return "unknown", None
    if score > COMPONENT_SCORE_MAX:
        return "range", None
    return "scored", Decimal(score)


def is_component_month(month_id: str) -> bool:
    return month_id in COMPONENT_MONTHS


def distill_component_cell(legacy_pk: int, row, from_archive: bool) -> ComponentCell:
    student_id = row["student_id"]
    if type(student_id) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return ComponentCell(
        legacy_pk=legacy_pk,
        uniqid=validated_uniqid(row["journal_uniqid"]),
        student_id=student_id,
        month_id=legacy_text(row["month_id"]),
        point=legacy_text(row["point"]),
        from_archive=from_archive,
    )


def ensure_component(context, *, offering_pk: str, month_id: str, cache) -> str:
    """Komponenti lazy/idempotent yarat — ``journal_extras`` güzgüsü."""

    key = (offering_pk, month_id)
    component_pk = cache.get(key)
    if component_pk is not None:
        return component_pk
    name, kind, max_score, order = COMPONENT_PLANS[month_id]
    model = django_apps.get_model("registrar", "AssessmentComponent")
    with transaction.atomic():
        component, _created = model.objects.get_or_create(
            organization=context.organization,
            offering_id=offering_pk,
            name=name,
            defaults={"kind": kind, "max_score": max_score, "order": order, "held_on": None},
        )
    cache[key] = str(component.pk)
    return cache[key]


def write_component_score(context, *, component_pk: str, enrollment_pk: str, score, allow_existing: bool) -> str:
    """``(component, enrollment)`` xanası — mövcud sətir üstündən yazılmır."""

    model = django_apps.get_model("registrar", "ComponentScore")
    with transaction.atomic():
        row, created = model.objects.get_or_create(
            organization=context.organization,
            component_id=component_pk,
            enrollment_id=enrollment_pk,
            defaults={"score": score, "entered_by": None},
        )
    if created:
        return "written"
    if not allow_existing:
        return "superseded"
    return "written" if Decimal(row.score) == Decimal(score) else "conflict"


class JournalComponentsPhase:
    """J5: kollokvium/sərbəst iş xanaları, jurnal başına bir möhür."""

    phase_key = JOURNAL_COMPONENTS_PHASE_KEY
    order = JOURNAL_COMPONENTS_PHASE_ORDER
    source_tables = ()
    entity_types = (COMPONENTS_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    derived_ledger_sort_key = staticmethod(str)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        offerings = migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE)
        enrollments = migrated_index(context, JOURNAL_ENROLLMENT_ENTITY_TYPE)
        ledger = JournalCellLedger(recorded=COMPONENT_SEALER.recorded_decisions(context))
        components: dict[tuple[str, str], str] = {}
        drive_cells(
            context,
            ledger=ledger,
            domain=is_component_month,
            distill=distill_component_cell,
            decide=lambda cell: self._decide(
                context,
                cell=cell,
                offerings=offerings,
                enrollments=enrollments,
                components=components,
                ledger=ledger,
            ),
            overlap_key="archive_overlap",
        )

        issue_counts: Counter[tuple[str, str]] = Counter()
        decisions = list(ledger.recorded.items())
        for uniqid, tally in sorted(ledger.tallies.items()):
            state = state_for(
                written=sum(tally[key] for key in WRITTEN_KEYS),
                quarantined=sum(tally[key] for key in QUARANTINE_KEYS),
            )
            digest = COMPONENT_SEALER.derivation_hash(
                seal_key=uniqid, outcome_token=str(state), parts=tally_parts(tally)
            )
            label = COURSE_OFFERING_MODEL_LABEL if state == _STATE.MIGRATED else ""
            entity_map = COMPONENT_SEALER.seal(
                context,
                seal_key=uniqid,
                digest=digest,
                state=state,
                label=label,
                target_pk=offerings.get(uniqid, "") if label else "",
            )
            COMPONENT_SEALER.write_issues(
                context,
                seal_key=uniqid,
                digest=digest,
                entity_map=entity_map,
                rule_codes=tuple(OUTCOME_RULES[key][0] for key in sorted(OUTCOME_RULES) if tally[key]),
                issue_counts=issue_counts,
            )
            decisions.append((uniqid, (state, digest, label)))

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for uniqid, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(uniqid, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_COMPONENTS_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    def _decide(self, context, *, cell: ComponentCell, offerings, enrollments, components, ledger) -> None:
        """orphan → dəyər → qeydiyyat → komponent → yazı nərdivanı."""

        offering_pk = offerings.get(cell.uniqid, "")
        if not offering_pk:
            ledger.count(cell.uniqid, "orphan")
            return
        outcome, score = classify_component_cell(cell.point)
        if outcome != "scored":
            ledger.count(cell.uniqid, outcome)
            return
        enrollment_pk = enrollments.get(f"{cell.uniqid}:{cell.student_id}", "")
        if not enrollment_pk:
            ledger.count(cell.uniqid, "enrollment")
            return
        component_pk = ensure_component(context, offering_pk=offering_pk, month_id=cell.month_id, cache=components)
        result = write_component_score(
            context,
            component_pk=component_pk,
            enrollment_pk=enrollment_pk,
            score=score,
            allow_existing=not cell.from_archive,
        )
        if result == "written":
            ledger.count(cell.uniqid, "archive_written" if cell.from_archive else "written")
        elif result == "superseded":
            ledger.count(cell.uniqid, "archive_overlap")
        else:
            ledger.count(cell.uniqid, "conflict")


# ``KOLLOKVIUM_MONTHS`` yalnız sənədləşmə/testlər üçün yenidən ixrac olunur.
__all__ = [
    "COMPONENT_PLANS",
    "COMPONENTS_ENTITY_TYPE",
    "COMPONENT_SEALER",
    "DERIVED_DIGEST_NAMESPACE",
    "ISSUE_SEVERITY",
    "JOURNAL_COMPONENTS_PHASE_KEY",
    "JOURNAL_COMPONENTS_PHASE_ORDER",
    "KOLLOKVIUM_MONTHS",
    "JournalComponentsPhase",
    "classify_component_cell",
    "is_component_month",
]
