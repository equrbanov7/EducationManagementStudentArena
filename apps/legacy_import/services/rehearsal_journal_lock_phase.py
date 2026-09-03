"""Phase: ``journal_lock`` (J7) — dövrü bitmiş semestrlərin jurnallarını kilidlə.

J-V8/V10(F): tarixi nəticələr dəyişməz olmalıdır, ona görə dövrü ARTIQ BİTMİŞ
semestrlərin ``AssessmentScheme``-i ``approval_status=APPROVED`` +
``is_published=True`` olur; cari (və gələcək) dövrün jurnalı DRAFT qalır.
Kilid redaktəni bağlayır, GÖRÜNÜŞÜ yox — istifadəçi tələbi.

Sıra qəsdən 46-dır: J4-J6 tam bitmədən kilid qoyulsa,
``gradebook.journal_is_locked`` bütün sonrakı bal yazılarını bloklardı.

``approval.py`` zənciri (müəllim → kafedra → dekan) ÇAĞIRILMIR — o, canlı
qərar axınıdır və hər addımda aktiv istifadəçi tələb edir; import isə tarixi
vəziyyəti simulyasiya edir.  Modelin öz ``registrar_scheme_publish_state_valid``
CheckConstraint-i (publish ⟺ approved) hər iki sahənin BİRGƏ yazılmasını
zəmanət altına alır.

Determinizm qeydi: "dövr bitibmi" qərarı ``timezone.localdate()``-dən asılıdır.
Digest-ə həm qərar, həm dövrün ``end_date``-i qatlanır — yəni eyni gün ərzində
iki rehearsal bayt-bəbayt eynidir, dövr sərhədi keçiləndə isə fərq GÖRÜNƏN
şəkildə digest-də özünü göstərir (səssiz sürüşmə mümkün deyil).
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import JOURNAL_FIELDS
from .rehearsal_authorizer import ASSESSMENT_SCHEME_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_components_phase import JOURNAL_COMPONENTS_PHASE_KEY
from .rehearsal_journal_finals_phase import JOURNAL_FINALS_PHASE_KEY
from .rehearsal_journal_marks_phase import JOURNAL_MARKS_PHASE_KEY
from .rehearsal_journal_offerings_source import JOURNAL_SOURCE_TABLE, migrated_target_index
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_seal import JournalSealer
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_LOCK_PHASE_KEY = "journal_lock"
JOURNAL_LOCK_PHASE_ORDER = 46  # journal_finals-dan (44) sonra
LOCK_ENTITY_TYPE = "journal_lock"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-lock-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_MARKS_PHASE_KEY, JOURNAL_COMPONENTS_PHASE_KEY, JOURNAL_FINALS_PHASE_KEY})

APPROVED_STATUS = "approved"
DRAFT_STATUS = "draft"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "journal_locked",
        _STATE.SKIPPED: "journal_left_open",
        _STATE.QUARANTINED: "journal_lock_unresolved",
    }
)

ISSUE_SEVERITY = MappingProxyType(
    {
        # Dövrün ``end_date``-i yoxdur → kilid qərarı verilə bilmir.
        "legacy_journal_lock_period_unknown": _SEVERITY.WARNING,
        # V10: bitmiş dövr kilidləndi / cari dövr qəsdən açıq qaldı.
        "legacy_journal_lock_applied": _SEVERITY.INFO,
        "legacy_journal_lock_deferred": _SEVERITY.INFO,
    }
)

LOCK_SEALER = JournalSealer(
    entity_type=LOCK_ENTITY_TYPE,
    source_table=JOURNAL_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-journal-lock-derivation-v1\x00",
    contract_fingerprint=JOURNAL_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


def offering_period_end(context: RehearsalContext, offering_pks) -> dict[str, object]:
    """Açılış → dövrün ``end_date``-i (kilid qərarının yeganə mənbəyi)."""

    model = django_apps.get_model("registrar", "CourseOffering")
    rows = model.objects.filter(organization=context.organization, pk__in=set(offering_pks)).values_list(
        "pk", "period__end_date"
    )
    return {str(pk): end_date for pk, end_date in rows}


def apply_lock(context, *, offering_pk: str) -> str:
    """Sxemi kilidlə — publish ⟺ approved cütü BİRGƏ yazılır."""

    model = django_apps.get_model("registrar", "AssessmentScheme")
    with transaction.atomic():
        scheme, _created = model.objects.get_or_create(organization=context.organization, offering_id=offering_pk)
        if not (scheme.is_published and scheme.approval_status == APPROVED_STATUS):
            scheme.approval_status = APPROVED_STATUS
            scheme.is_published = True
            scheme.save(update_fields=["approval_status", "is_published", "updated_at"])
    return str(scheme.pk)


def ensure_open(context, *, offering_pk: str) -> str:
    """Cari dövr: sxem yalnız mövcud olmalıdır — heç bir status dəyişmir."""

    model = django_apps.get_model("registrar", "AssessmentScheme")
    with transaction.atomic():
        scheme, _created = model.objects.get_or_create(organization=context.organization, offering_id=offering_pk)
    return str(scheme.pk)


class JournalLockPhase:
    """J7: bitmiş semestrlərin jurnal kilidi, jurnal başına bir qərar."""

    phase_key = JOURNAL_LOCK_PHASE_KEY
    order = JOURNAL_LOCK_PHASE_ORDER
    source_tables = ()
    entity_types = (LOCK_ENTITY_TYPE,)
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
        period_ends = offering_period_end(context, offerings.values())
        recorded = LOCK_SEALER.recorded_decisions(context)
        today = timezone.localdate()

        issue_counts: Counter[tuple[str, str]] = Counter()
        decisions = list(recorded.items())
        for uniqid, offering_pk in sorted(offerings.items()):
            probe_cancellation(context)
            if uniqid in recorded:
                continue
            decisions.append(
                (
                    uniqid,
                    self._decide(
                        context,
                        uniqid=uniqid,
                        offering_pk=offering_pk,
                        end_date=period_ends.get(offering_pk),
                        today=today,
                        issue_counts=issue_counts,
                    ),
                )
            )

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for uniqid, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(uniqid, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_LOCK_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    def _decide(self, context, *, uniqid, offering_pk, end_date, today, issue_counts):
        """Dövrün sonu keçibsə kilidlə, yoxsa qəsdən açıq saxla."""

        if end_date is None:
            digest = LOCK_SEALER.derivation_hash(seal_key=uniqid, outcome_token="unresolved", parts=("period_end=",))
            entity_map = LOCK_SEALER.seal(context, seal_key=uniqid, digest=digest, state=_STATE.QUARANTINED)
            LOCK_SEALER.write_issues(
                context,
                seal_key=uniqid,
                digest=digest,
                entity_map=entity_map,
                rule_codes=("legacy_journal_lock_period_unknown",),
                issue_counts=issue_counts,
            )
            return _STATE.QUARANTINED, digest, ""

        finished = end_date < today
        outcome = "locked" if finished else "open"
        digest = LOCK_SEALER.derivation_hash(
            seal_key=uniqid,
            outcome_token=outcome,
            parts=(f"period_end={end_date.isoformat()}",),
        )
        scheme_pk = (
            apply_lock(context, offering_pk=offering_pk) if finished else ensure_open(context, offering_pk=offering_pk)
        )
        state = _STATE.MIGRATED if finished else _STATE.SKIPPED
        label = ASSESSMENT_SCHEME_MODEL_LABEL if finished else ""
        entity_map = LOCK_SEALER.seal(
            context,
            seal_key=uniqid,
            digest=digest,
            state=state,
            label=label,
            target_pk=scheme_pk if finished else "",
        )
        LOCK_SEALER.write_issues(
            context,
            seal_key=uniqid,
            digest=digest,
            entity_map=entity_map,
            rule_codes=("legacy_journal_lock_applied" if finished else "legacy_journal_lock_deferred",),
            issue_counts=issue_counts,
        )
        return state, digest, label
