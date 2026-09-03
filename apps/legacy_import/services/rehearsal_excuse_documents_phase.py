"""Phase: ``journal_excuse_documents`` (J13, sıra 50) — ÜZRLÜ QAYIB SƏNƏDİ.

Niyə var (sahib şikayəti, 2026-08-31)
-------------------------------------
«Köhnə datadan, əgər köçməyibsə, kiminsə qayıbı düzələrkən yüklənən
təqdimat/izahat varsa, onu da üzərinə əlavə et; sarı ilə göstərən dizayn
orada olmuş olsun.»

Ölçülmüş vəziyyət: ``allowed_qb`` cədvəli hədəfə YALNIZ QAYDA kimi çatırdı —
J4 (``journal_marks``) onun tarix aralıqlarını oxuyub qayıbı ``excused`` (üq)
yazır (``rehearsal_journal_points_source.is_excused``), amma SƏNƏDİN ÖZÜ
(kim göndərib, nə vaxt, hansı izahla, hansı fayl) heç yerə köçmürdü.  2,964
sətrin hamısında fayl adı, 2,927-də izah mətni var idi və hamısı itirdi.

Bu faza həmin sətirləri ``registrar.LegacyExcuseDocument``-ə köçürür.  Heç bir
mövcud dəyər DƏYİŞMİR: nə bir ``LessonMark``-a toxunulur, nə ``absence_hours``
yenidən hesablanır — J4-ün artıq yazdığı ``excused`` statusu olduğu kimi qalır.
Bu faza YALNIZ sübut əlavə edir.

Niyə ``JournalCorrection`` DEYİL
--------------------------------
Modelin öz şərhində (``registrar/models/legacy_excuse.py``) səbəb yazılıb:
``JournalCorrection`` bir dəyişikliyin qeydidir (köhnə → yeni), burada isə
dəyişiklik YOXDUR.  Saxta düzəliş sətri həm audit tarixçəsini, həm də
müəllim kilidini yalanla doldurardı.  UI isə paralel sistem qurmur — mövcud
SARI xana + ✎ tarixçə modalını təkrar işlədir (``registrar/legacy_excuse.py``).

Niyə sıra 50 (sonuncu)
----------------------
Yeganə asılılıq kimlikdir (J-identity, 20): tələbə hesabı olmalıdır ki, qeyd
ona bağlansın.  Faza heç bir bal/dərs/qayıb hesabına girmir, ona görə jurnal
zəncirinin SONUNA qoyulur — mövcud fazaların heç birinin nəticəsini
dəyişdirmək ehtimalı struktur olaraq sıfırdır.

Fail-closed hallar
------------------
* tələbəsi tapılmayan qeyd → ``mapping_status=student_unresolved`` +
  ``legacy_excuse_student_unresolved`` (canlıda 8 sətir); sətir SAXLANIR,
  yalnız kanonik tələbəyə bağlanmır;
* tarix aralığı pozuq qeyd → ``mapping_status=window_invalid`` +
  ``legacy_excuse_window_invalid`` (canlıda 0 sətir, amma qapı açıq qalır);
* naməlum issue kodu → ``legacy_rehearsal_issue_severity_unmapped``;
* hədəf sətri yaradıla bilmirsə → ``legacy_rehearsal_batch_target_unresolved``.

Sətir HEÇ VAXT atılmır və ledger vəziyyəti hər halda ``MIGRATED``-dır
(J-facts ilə eyni: xam sübut materiallaşır, mapping problemi metadatadır).
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue, LegacyMigrationRun

from .rehearsal_authorizer import LEGACY_EXCUSE_DOCUMENT_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_excuse_documents import (
    EXCUSE_ENTITY_TYPE,
    EXCUSE_SOURCE_TABLE,
    RULE_DOCUMENT_ABSENT,
    RULE_DOCUMENT_NAME_INVALID,
    RULE_NOTE_EMPTY,
    RULE_NOTE_TRUNCATED,
    RULE_STUDENT_UNRESOLVED,
    RULE_WINDOW_INVALID,
    LegacyExcuseMaterialiser,
    excuse_materialization_digest,
    excuse_requests,
    excuse_rows,
)
from .rehearsal_identity_phase import IDENTITY_PHASE_KEY, STUDENT_ENTITY_TYPE
from .rehearsal_journal_batch import Decision, JournalBatchWriter
from .rehearsal_journal_offerings_source import migrated_target_index
from .rehearsal_structure_phase import probe_cancellation

EXCUSE_DOCUMENTS_PHASE_KEY = "journal_excuse_documents"
EXCUSE_DOCUMENTS_PHASE_ORDER = 50  # legacy_grade_artifacts (49) sonrası
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-excuse-documents-v1"
REQUIRED_PHASE_KEYS = frozenset({IDENTITY_PHASE_KEY})

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "legacy_excuse_materialised",
        _STATE.SKIPPED: "legacy_excuse_skipped",
        _STATE.QUARANTINED: "legacy_excuse_unresolved",
    }
)

# Heç biri ERROR deyil: bu faza yalnız SÜBUT əlavə edir, run-u bloklamamalıdır.
ISSUE_SEVERITY = MappingProxyType(
    {
        # Tələbə hesabı bu run-da yaranmayıb — qeyd saxlanır, bağlanmır.
        RULE_STUDENT_UNRESOLVED: _SEVERITY.WARNING,
        # ``allowed_date_end < allowed_date_start`` və ya tip drift-i.
        RULE_WINDOW_INVALID: _SEVERITY.WARNING,
        # Faylın ÖZÜ hədəfdə yoxdur (köhnə serverdə) — hər sətirdə gözlənilir.
        RULE_DOCUMENT_ABSENT: _SEVERITY.INFO,
        RULE_DOCUMENT_NAME_INVALID: _SEVERITY.INFO,
        RULE_NOTE_EMPTY: _SEVERITY.INFO,
        RULE_NOTE_TRUNCATED: _SEVERITY.INFO,
    }
)


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def recorded_decisions(context) -> dict[str, tuple[str, str, str]]:
    """Resume qısayolu: bu run-un artıq möhürlədiyi qərarlar."""

    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id,
        entity_map__entity_type=EXCUSE_ENTITY_TYPE,
    ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
    return {legacy_pk: (state, digest, label) for legacy_pk, state, digest, label in rows.iterator(chunk_size=10_000)}


class JournalExcuseDocumentsPhase:
    """J13: ``allowed_qb`` sətri → dəyişdirilməz üzrlü-qayıb sənəd qeydi."""

    phase_key = EXCUSE_DOCUMENTS_PHASE_KEY
    order = EXCUSE_DOCUMENTS_PHASE_ORDER
    # Cədvəl İDDİA edilmir: J4 onu qayda üçün oxuyur, bu faza sənəd üçün.
    # İddia batch mühasibatına aiddir, oxumağa yox (seam qeydi).
    source_tables = ()
    entity_types = (EXCUSE_ENTITY_TYPE,)
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

        run = LegacyMigrationRun.objects.only("snapshot_sha256", "transform_version").get(pk=context.run_id)
        students = migrated_target_index(context, STUDENT_ENTITY_TYPE)
        recorded = recorded_decisions(context)
        materialiser = LegacyExcuseMaterialiser()
        writer = JournalBatchWriter(
            context,
            entity_type=EXCUSE_ENTITY_TYPE,
            source_table=EXCUSE_SOURCE_TABLE,
            severity_for=severity_for,
            materialiser=materialiser,
        )
        decisions: list[tuple[str, str, str, str]] = []

        for request in excuse_requests(context, rows=excuse_rows(context), students=students):
            probe_cancellation(context)
            previous = recorded.get(request.seal_key)
            if previous is not None:
                decisions.append((request.seal_key, *previous))
                continue
            payload = {
                **request.payload,
                "source_snapshot_sha256": run.snapshot_sha256,
                "source_row_hash": request.source_row_hash,
                "transform_version": run.transform_version,
            }
            digest = excuse_materialization_digest(
                natural_key=request.natural_key,
                source_row_hash=request.source_row_hash,
                payload=payload,
            )
            payload["materialization_digest"] = digest
            materialiser.stage(request.natural_key, payload, student_target_pk=request.student_target_pk)
            # J-facts ilə eyni qayda: XAM SÜBUT hər halda MIGRATED olur, mapping
            # problemi (tələbə tapılmadı / pəncərə pozuq) METADATA-dır — sətir
            # ``mapping_status`` + issue kodları ilə saxlanır, ATILMIR.
            writer.add(
                Decision(
                    seal_key=request.seal_key,
                    state=_STATE.MIGRATED,
                    digest=digest,
                    label=LEGACY_EXCUSE_DOCUMENT_MODEL_LABEL,
                    rule_codes=request.rule_codes,
                    natural_key=request.natural_key,
                )
            )
            decisions.append((request.seal_key, str(_STATE.MIGRATED), digest, LEGACY_EXCUSE_DOCUMENT_MODEL_LABEL))
        writer.flush()

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, state, digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{self.phase_key}.records.{sum(state_counts.values())}")
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


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "EXCUSE_DOCUMENTS_PHASE_KEY",
    "EXCUSE_DOCUMENTS_PHASE_ORDER",
    "ISSUE_SEVERITY",
    "JournalExcuseDocumentsPhase",
    "recorded_decisions",
    "severity_for",
]
