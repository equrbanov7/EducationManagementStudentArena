"""Phase: ``journal_offerings`` (J1) — ``journals`` → registrar.CourseOffering.

Derived faza (``source_tables = ()``): mənbə ``rehearsal_journal_offerings_source``
ilə axıdılır, hədəflər ``rehearsal_journal_offerings_targets`` ilə yazılır; bu
modul qərar nərdivanına, indeks keşlərinə və digest zəncirinə sahibdir.

Qərar nərdivanı (yuxarıdan aşağı, hər pillə öz sətrini möhürləyir):

* J-V6 — ``fake=1`` VƏ YA ``sonra_sil=1`` → SKIPPED
  ``legacy_journal_discarded_source`` (uniqid ledger-də qalır).
* J-V7 — ``groups_id`` parse xətası / boş massiv → QUARANTINED
  ``legacy_journal_groups_invalid``; massiv >1 → ``group=NULL`` tək offering +
  İNFO ``legacy_journal_multi_group``; tək qrup EntityMap-da tapılmasa →
  QUARANTINED ``legacy_journal_group_unresolved``.
* Fənn/dövr istinadı tapılmasa → QUARANTINED (offering onlarsız mövcud deyil).
* J-V5 — ``teacher_id`` həlli tapılmasa ``instructor=NULL`` + İNFO
  ``legacy_journal_instructor_unresolved`` (legacy teacher_id qərar kimliyində).

Ledger kimlik açarı ``uniqid``-dir (rəqəm deyil), ona görə SA-2 zənciri
LEKSİKOQRAFİK uniqid sırasında yeriyir: canlı keçid qərarları yığıb sıralayır,
``derived_ledger_sort_key`` hook-u isə ledger rebuild-inə eyni sıranı verir —
iki tərəf bayt-bəbayt üst-üstə düşür.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap

from .field_contracts import JOURNAL_FIELDS
from .rehearsal_catalog_phase import CATALOG_PHASE_KEY
from .rehearsal_catalog_targets import SUBJECT_ENTITY_TYPE
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    source_row_hash,
)
from .rehearsal_identity_phase import IDENTITY_PHASE_KEY, WORKER_ENTITY_TYPE
from .rehearsal_journal_batch import JournalBatchWriter
from .rehearsal_journal_offerings_source import JOURNAL_SOURCE_TABLE  # noqa: F401 — §3.9 re-export (testlər üçün fasad)
from .rehearsal_journal_offerings_source import (
    journal_rows,
    legacy_int,
    migrated_target_index,
    parse_group_ids,
    validated_uniqid,
)
from .rehearsal_journal_offerings_targets import ISSUE_SEVERITY  # noqa: F401 — §3.9 re-export
from .rehearsal_journal_offerings_targets import (
    COURSE_OFFERING_ENTITY_TYPE,
    OfferingRequest,
    discarded_decision,
    offering_decision,
    offering_materialiser,
    recorded_decisions,
    severity_for,
    unresolved_decision,
)
from .rehearsal_journal_periods_phase import ACADEMIC_PERIOD_ENTITY_TYPE, JOURNAL_PERIODS_PHASE_KEY
from .rehearsal_structure_phase import STRUCTURE_PHASE_KEY, probe_cancellation
from .rehearsal_structure_targets import GROUP_ENTITY_TYPE

JOURNAL_OFFERINGS_PHASE_KEY = "journal_offerings"
JOURNAL_OFFERINGS_PHASE_ORDER = 34  # journal_periods-dən (32) sonra
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-offerings-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_PERIODS_PHASE_KEY, STRUCTURE_PHASE_KEY, CATALOG_PHASE_KEY, IDENTITY_PHASE_KEY})

_STATE = LegacyEntityMap.State

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "offering_materialised",
        _STATE.SKIPPED: "offering_discarded",
        _STATE.QUARANTINED: "offering_unresolved",
    }
)


class JournalOfferingsPhase:
    """J1: jurnal başlıqlarının fənn açılışına çevrilməsi, jurnal başına bir qərar."""

    phase_key = JOURNAL_OFFERINGS_PHASE_KEY
    order = JOURNAL_OFFERINGS_PHASE_ORDER
    source_tables = ()
    entity_types = (COURSE_OFFERING_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # ``uniqid`` rəqəm deyil: rebuild ``int()`` əvəzinə leksikoqrafik sıralayır.
    derived_ledger_sort_key = staticmethod(str)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, Config deyil: orkestrator run-u FAILED bitirir.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        subjects = migrated_target_index(context, SUBJECT_ENTITY_TYPE)
        periods = migrated_target_index(context, ACADEMIC_PERIOD_ENTITY_TYPE)
        groups = migrated_target_index(context, GROUP_ENTITY_TYPE)
        instructors = migrated_target_index(context, WORKER_ENTITY_TYPE)

        recorded = recorded_decisions(context)
        # V5: açılışın müəllimi qərar anında bəllidir, materialiser isə onu
        # təbii açardan deyil, bu xəritədən oxuyur (açar (subject, period, group)).
        instructor_for_key: dict[tuple, str] = {}
        writer = JournalBatchWriter(
            context,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            source_table=JOURNAL_SOURCE_TABLE,
            severity_for=severity_for,
            materialiser=offering_materialiser(lambda key: instructor_for_key.get(key, "")),
        )

        decisions: list[tuple[str, str, str, str]] = []
        seen_uniqids: set[str] = set()
        state_counts: Counter[str] = Counter()
        claimed_keys: set[tuple[str, str, str]] = set()
        for legacy_pk, row in journal_rows(context):
            probe_cancellation(context)
            uniqid = validated_uniqid(row["uniqid"])
            if uniqid in seen_uniqids:
                # Mənbə attestasiyası "dublikatsız" deyir — ziddiyyət fataldır.
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_journal_uniqid_duplicate")
            seen_uniqids.add(uniqid)
            previous = recorded.get(uniqid)
            if previous is not None:
                state, digest, label = previous
                if state == _STATE.MIGRATED:
                    # Resume olunan MIGRATED sətir də merge-açarını tutur ki,
                    # yarımçıq keçiddən sonrakı davam eyni İNFO-nu törətsin.
                    self._claim(claimed_keys, row=row, subjects=subjects, periods=periods, groups=groups)
            else:
                decision = self._decide(
                    legacy_pk=legacy_pk,
                    row=row,
                    uniqid=uniqid,
                    subjects=subjects,
                    periods=periods,
                    groups=groups,
                    instructors=instructors,
                    claimed_keys=claimed_keys,
                    instructor_for_key=instructor_for_key,
                )
                writer.add(decision)
                state, digest, label = decision.state, decision.digest, decision.label
            decisions.append((uniqid, str(state), digest, label))
            state_counts[self.derived_state_key(state)] += 1
        writer.flush()

        # SA-2: zəncir uniqid-in LEKSİKOQRAFİK sırasında — rebuild ilə eyni.
        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        for uniqid, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(uniqid, state, digest, label)

        context.stdout_note(f"{JOURNAL_OFFERINGS_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(writer.issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    def _resolved_shape(self, row, *, subjects, periods, groups):
        """Bir sətrin istinad həlli: (subject_pk, period_pk, group_pk, qrup sayı)."""

        subject_pk = subjects.get(str(legacy_int(row["lesson_id"])), "")
        period_pk = periods.get(str(legacy_int(row["semestr"])), "")
        members = parse_group_ids(row["groups_id"])
        if members is None:
            return subject_pk, period_pk, None, ""
        group_pk = groups.get(str(members[0]), "") if len(members) == 1 else ""
        return subject_pk, period_pk, members, group_pk

    def _claim(self, claimed_keys, *, row, subjects, periods, groups) -> None:
        """Resume yolunda merge-açarını bərpa et (canlı qərarla eyni qayda)."""

        subject_pk, period_pk, members, group_pk = self._resolved_shape(
            row, subjects=subjects, periods=periods, groups=groups
        )
        if subject_pk and period_pk and members is not None:
            claimed_keys.add((subject_pk, period_pk, group_pk))

    def _decide(
        self,
        *,
        legacy_pk,
        row,
        uniqid,
        subjects,
        periods,
        groups,
        instructors,
        claimed_keys,
        instructor_for_key,
    ):
        """V6 → V7 → istinad həlli → V5 nərdivanı; hər pillə öz sətrini möhürləyir."""

        row_hash = source_row_hash(contract=JOURNAL_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        if legacy_int(row["fake"]) == 1 or legacy_int(row["sonra_sil"]) == 1:
            return discarded_decision(uniqid=uniqid, row_hash=row_hash)

        subject_pk, period_pk, members, group_pk = self._resolved_shape(
            row, subjects=subjects, periods=periods, groups=groups
        )
        teacher_id = legacy_int(row["teacher_id"])
        instructor_pk = instructors.get(str(teacher_id), "")
        info_codes: list[str] = []
        if members is not None and len(members) > 1:
            info_codes.append("legacy_journal_multi_group")
        if not instructor_pk:
            info_codes.append("legacy_journal_instructor_unresolved")

        quarantine_codes: list[str] = []
        if members is None:
            quarantine_codes.append("legacy_journal_groups_invalid")
        elif len(members) == 1 and not group_pk:
            quarantine_codes.append("legacy_journal_group_unresolved")
        if not subject_pk:
            quarantine_codes.append("legacy_journal_subject_unresolved")
        if not period_pk:
            quarantine_codes.append("legacy_journal_period_unresolved")

        groups_token = "" if members is None else ",".join(str(member) for member in members)
        group_state = "invalid" if members is None else ("merged_null" if len(members) > 1 else "resolved")
        if members is not None and len(members) == 1 and not group_pk:
            group_state = "unresolved"
        request = OfferingRequest(
            uniqid=uniqid,
            row_hash=row_hash,
            subject_pk=subject_pk,
            period_pk=period_pk,
            group_pk=group_pk,
            instructor_pk=instructor_pk,
            subject_ref=str(legacy_int(row["lesson_id"])),
            period_ref=str(legacy_int(row["semestr"])),
            groups_token=groups_token,
            group_state=group_state,
            # V5: legacy teacher_id qərar kimliyində saxlanılır (İNFO payload-ı).
            instructor_state=f"resolved:{teacher_id}" if instructor_pk else f"unresolved:{teacher_id}",
            merged_text="0",
        )
        if quarantine_codes:
            return unresolved_decision(request=request, rule_codes=(*quarantine_codes, *info_codes))

        key = (subject_pk, period_pk, group_pk)
        merged = key in claimed_keys
        claimed_keys.add(key)
        if merged:
            info_codes.append("legacy_journal_offering_merged")
        request = replace(request, merged_text="1" if merged else "0")
        # İlk qalib açılışın müəllimi qalır: merge olunan jurnal mövcud sətri
        # dəyişmir (``get_or_create`` semantikasının eynisi).
        instructor_for_key.setdefault((subject_pk, period_pk, group_pk or None), instructor_pk)
        return offering_decision(request=request, rule_codes=tuple(info_codes))
