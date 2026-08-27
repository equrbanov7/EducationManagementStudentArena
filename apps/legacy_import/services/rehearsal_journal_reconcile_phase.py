"""Phase: ``journal_reconcile`` (J8) — say balansı, ``yekun`` güzgüsü, karantin xülasəsi.

J-V9: bu faza HEÇ NƏ yazmır (ona görə heç bir möhür MIGRATED ola bilməz) —
yalnız üç sübutu ledger-ə möhürləyir:

* **(a) say balansı** — hər domen (marks / components / finals) üçün
  ``mənbə = yazılan + boş + oxunmayan + orphan + overlap + delta``; ``delta``
  dublikat uduzanlarını, həll olunmayan istinadları və hədəf toqquşmalarını
  əhatə edir.  Möhür açarı ``a-balance-<domen>``, ``delta != 0`` olduqda
  QUARANTINED (yəni operator baxışına düşür), əks halda SKIPPED;
* **(b) ``yekun`` müqayisəsi** — 17,194 tarixi sətir ``compute_final_result``
  güzgüsü ilə üzləşdirilir; kənarlaşma İNFO-dur (spec J-V9(b)) və sətir
  QUARANTINED möhürlənir ki, hesabatda sayı görünsün;
* **(c) karantin xülasəsi** — jurnal klasterinin bütün fazalarının QUARANTINED
  möhür sayı bir İNFO-da toplanır (``a-quarantine-summary``);
* **(d) imtahan nəticəsi örtüyü** — nə ``FinalGrade.exam_score``, nə
  ``ResitRecord.resit_score`` olan yazılışların sayı (``a-final-coverage``).
  Belə yazılış nə keçir, nə kəsilir, krediti də sayılmır — yəni hesabatlarda
  GÖRÜNMƏZ qalırdı.  İNFO-dur və möhür SKIPPED-dir: bu mənbənin sadiq əksidir,
  ziddiyyət deyil (legacy jurnalda o tələbənin ``im`` xanası yoxdur).

Möhür açarları qəsdən prefiksli və leksikoqrafik sıralanandır: ``a-…`` yoxlama
sətirləri, ``y-<10 rəqəm>`` isə ``yekun`` sətirləridir — ledger rebuild-i eyni
sıranı bayt-bəbayt təkrarlayır.
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import YEKUN_FIELDS
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_components_phase import COMPONENTS_ENTITY_TYPE
from .rehearsal_journal_enrollments_phase import JOURNAL_ENROLLMENT_ENTITY_TYPE
from .rehearsal_journal_entry_scores_phase import ENTRY_SCORES_ENTITY_TYPE
from .rehearsal_journal_finals_phase import FINALS_ENTITY_TYPE
from .rehearsal_journal_lessons_phase import journal_index
from .rehearsal_journal_lock_phase import JOURNAL_LOCK_PHASE_KEY, LOCK_ENTITY_TYPE
from .rehearsal_journal_marks_targets import MARKS_ENTITY_TYPE
from .rehearsal_journal_offerings_source import legacy_int, migrated_target_index
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_points_source import migrated_index, yekun_rows
from .rehearsal_journal_reconcile_source import (
    BALANCE_DOMAINS,
    BALANCE_KEYS,
    DEVIATION_TOLERANCE,
    FinalMirror,
    balance_delta,
    final_coverage,
    legacy_total,
    tally_source_rows,
    tally_target_rows,
)
from .rehearsal_journal_seal import JournalSealer
from .rehearsal_journal_slices import build_offering_slices
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_RECONCILE_PHASE_KEY = "journal_reconcile"
JOURNAL_RECONCILE_PHASE_ORDER = 48  # journal_lock-dan (46) sonra
RECONCILE_ENTITY_TYPE = "journal_reconcile"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-reconcile-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_LOCK_PHASE_KEY})
QUARANTINE_SUMMARY_KEY = "a-quarantine-summary"
FINAL_COVERAGE_KEY = "a-final-coverage"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity
_SUMMARISED_ENTITY_TYPES = (
    MARKS_ENTITY_TYPE,
    COMPONENTS_ENTITY_TYPE,
    ENTRY_SCORES_ENTITY_TYPE,
    FINALS_ENTITY_TYPE,
    LOCK_ENTITY_TYPE,
)

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "reconcile_written",  # struktur olaraq baş vermir
        _STATE.SKIPPED: "reconcile_balanced",
        _STATE.QUARANTINED: "reconcile_deviation",
    }
)

ISSUE_SEVERITY = MappingProxyType(
    {
        # J-V9: hər üç sübut da İNFO-dur — reconciliation bloklamır, göstərir.
        "legacy_journal_reconcile_row_balance": _SEVERITY.INFO,
        "legacy_journal_reconcile_final_deviation": _SEVERITY.INFO,
        "legacy_journal_reconcile_quarantine_summary": _SEVERITY.INFO,
        # B-tapşırığı (2026-08): imtahan NƏTİCƏSİ olmayan yazılışların sayı.
        # İNFO-dur, çünki mənbənin sadiq əksidir — legacy jurnalda həmin
        # tələbənin ``im`` xanası ümumiyyətlə yoxdur, yəni köçürmə heç nə
        # itirməyib.  Blokladıcı deyil, GÖRÜNƏNdir: hədəf tərəfdə eyni say
        # «Akademik qeydlər»-in «Qiymətləndirilməyib» qutusunda oxunur və
        # imtahan mərkəzi məhz o siyahını doldurur.
        "legacy_journal_final_missing": _SEVERITY.INFO,
        # ``yekun`` sətri heç bir jurnala/qeydiyyata bağlanmır.
        "legacy_journal_reconcile_final_unresolved": _SEVERITY.WARNING,
    }
)

RECONCILE_SEALER = JournalSealer(
    entity_type=RECONCILE_ENTITY_TYPE,
    source_table=YEKUN_FIELDS.source_table,
    derivation_prefix=b"legacy-rehearsal-journal-reconcile-derivation-v1\x00",
    contract_fingerprint=YEKUN_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


def yekun_seal_key(legacy_pk: int) -> str:
    """``y-`` prefiksi + sıfır doldurulmuş id → leksikoqrafik = rəqəmsal sıra."""

    return f"y-{legacy_pk:010d}"


def quarantine_summary(run_id) -> dict[str, int]:
    """Jurnal fazalarının QUARANTINED möhür sayları (ledger-dən, faza-faza)."""

    rows = LegacyEntityObservation.objects.filter(
        run_id=run_id,
        state=_STATE.QUARANTINED,
        entity_map__entity_type__in=_SUMMARISED_ENTITY_TYPES,
    ).values_list("entity_map__entity_type", flat=True)
    counter: Counter[str] = Counter(rows)
    return {entity_type: counter.get(entity_type, 0) for entity_type in _SUMMARISED_ENTITY_TYPES}


class JournalReconcilePhase:
    """J8: jurnal klasterinin yekun üzləşdirməsi — heç bir hədəf yazısı yoxdur."""

    phase_key = JOURNAL_RECONCILE_PHASE_KEY
    order = JOURNAL_RECONCILE_PHASE_ORDER
    source_tables = ()
    entity_types = (RECONCILE_ENTITY_TYPE,)
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

        slices = build_offering_slices(context, migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE))
        journal_uniqids = slices.journal_uniqids()
        recorded = RECONCILE_SEALER.recorded_decisions(context)
        issue_counts: Counter[tuple[str, str]] = Counter()
        decisions = list(recorded.items())

        decisions.extend(
            self._balance(context, journal_uniqids=journal_uniqids, recorded=recorded, issue_counts=issue_counts)
        )
        decisions.extend(
            self._finals(context, journal_uniqids=journal_uniqids, recorded=recorded, issue_counts=issue_counts)
        )
        decisions.extend(self._coverage(context, recorded=recorded, issue_counts=issue_counts))
        decisions.extend(self._summary(context, recorded=recorded, issue_counts=issue_counts))

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_RECONCILE_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    # ── (a) say balansı ─────────────────────────────────────────────────────

    def _balance(self, context, *, journal_uniqids, recorded, issue_counts):
        keys = {domain: f"a-balance-{domain}" for domain in BALANCE_DOMAINS}
        if all(key in recorded for key in keys.values()):
            return ()
        source = tally_source_rows(context, journal_uniqids=journal_uniqids)
        target = tally_target_rows(context)
        results = []
        for domain in BALANCE_DOMAINS:
            seal_key = keys[domain]
            if seal_key in recorded:
                continue
            bucket = source[domain]
            delta = balance_delta(bucket, target[domain])
            parts = (
                *(f"{name}={bucket[name]}" for name in BALANCE_KEYS),
                f"target={target[domain]}",
                f"delta={delta}",
            )
            results.append(
                (
                    seal_key,
                    self._seal_check(
                        context,
                        seal_key=seal_key,
                        outcome_token="balanced" if delta == 0 else "delta",
                        parts=parts,
                        state=_STATE.SKIPPED if delta == 0 else _STATE.QUARANTINED,
                        rule_code="legacy_journal_reconcile_row_balance",
                        issue_counts=issue_counts,
                    ),
                )
            )
        return results

    # ── (b) ``yekun`` güzgüsü ───────────────────────────────────────────────

    def _finals(self, context, *, journal_uniqids, recorded, issue_counts):
        journals = journal_index(context)
        enrollments = migrated_index(context, JOURNAL_ENROLLMENT_ENTITY_TYPE)
        mirror = FinalMirror(context)
        results = []
        for legacy_pk, row in yekun_rows(context):
            probe_cancellation(context)
            seal_key = yekun_seal_key(legacy_pk)
            if seal_key in recorded:
                continue
            journal = journals.get(legacy_int(row["journal_id"]))
            uniqid = journal[0] if journal is not None else ""
            enrollment_pk = (
                enrollments.get(f"{uniqid}:{legacy_int(row['student_id'])}", "")
                if uniqid and uniqid in journal_uniqids
                else ""
            )
            expected = legacy_total(row)
            if not enrollment_pk or expected is None:
                results.append(
                    (
                        seal_key,
                        self._seal_check(
                            context,
                            seal_key=seal_key,
                            outcome_token="unresolved",
                            parts=(f"journal={legacy_int(row['journal_id'])}",),
                            state=_STATE.QUARANTINED,
                            rule_code="legacy_journal_reconcile_final_unresolved",
                            issue_counts=issue_counts,
                        ),
                    )
                )
                continue
            computed = mirror.total_score(enrollment_pk)
            deviated = abs(computed - expected) > DEVIATION_TOLERANCE
            results.append(
                (
                    seal_key,
                    self._seal_check(
                        context,
                        seal_key=seal_key,
                        outcome_token="deviation" if deviated else "match",
                        parts=(f"legacy={expected}", f"computed={computed}"),
                        state=_STATE.QUARANTINED if deviated else _STATE.SKIPPED,
                        rule_code="legacy_journal_reconcile_final_deviation" if deviated else "",
                        issue_counts=issue_counts,
                    ),
                )
            )
        return results

    # ── (d) imtahan nəticəsi olmayan yazılışlar ─────────────────────────────

    def _coverage(self, context, *, recorded, issue_counts):
        """Sayı möhürlə: nə keçən, nə kəsilən yazılış hesabatda GÖRÜNSÜN.

        Möhür TƏKdir (say jurnal-başına deyil, tenant-başına aqreqatdır) —
        23 382 yazılış üçün 23 382 ledger sətri qərar dəyəri olmayan yüklə
        olardı.  Say ``derivation_hash``-ə qatlanır: növbəti run-da rəqəm
        dəyişsə möhür kimliyi dəyişir və ``upsert_entity_map`` səssiz sürüşməni
        ``legacy_entity_identity_conflict`` ilə tutur.
        """

        if FINAL_COVERAGE_KEY in recorded:
            return ()
        coverage = final_coverage(context)
        return (
            (
                FINAL_COVERAGE_KEY,
                self._seal_check(
                    context,
                    seal_key=FINAL_COVERAGE_KEY,
                    outcome_token="complete" if not coverage["missing"] else "missing",
                    parts=tuple(f"{name}={count}" for name, count in sorted(coverage.items())),
                    state=_STATE.SKIPPED,
                    rule_code="legacy_journal_final_missing" if coverage["missing"] else "",
                    issue_counts=issue_counts,
                ),
            ),
        )

    # ── (c) karantin xülasəsi ───────────────────────────────────────────────

    def _summary(self, context, *, recorded, issue_counts):
        if QUARANTINE_SUMMARY_KEY in recorded:
            return ()
        summary = quarantine_summary(context.run_id)
        return (
            (
                QUARANTINE_SUMMARY_KEY,
                self._seal_check(
                    context,
                    seal_key=QUARANTINE_SUMMARY_KEY,
                    outcome_token="summary",
                    parts=tuple(f"{name}={count}" for name, count in sorted(summary.items())),
                    state=_STATE.SKIPPED,
                    rule_code="legacy_journal_reconcile_quarantine_summary",
                    issue_counts=issue_counts,
                ),
            ),
        )

    def _seal_check(self, context, *, seal_key, outcome_token, parts, state, rule_code, issue_counts):
        digest = RECONCILE_SEALER.derivation_hash(seal_key=seal_key, outcome_token=outcome_token, parts=parts)
        entity_map = RECONCILE_SEALER.seal(context, seal_key=seal_key, digest=digest, state=state)
        if rule_code:
            RECONCILE_SEALER.write_issues(
                context,
                seal_key=seal_key,
                digest=digest,
                entity_map=entity_map,
                rule_codes=(rule_code,),
                issue_counts=issue_counts,
            )
        return state, digest, ""
