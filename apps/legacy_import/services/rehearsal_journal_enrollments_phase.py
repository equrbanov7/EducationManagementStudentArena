"""Phase: ``journal_enrollments`` (J2) — ``journals.students_id`` → registrar.Enrollment.

Derived faza (``source_tables = ()``): ``journals`` EYNİ audited kontrakt
(``JOURNAL_FIELDS``) üzərindən J1-dəki axınla YENİDƏN oxunur (kontrakt
``students_id``-i məhz bu genişlətmə üçün İNDİDƏN daşıyırdı — barmaq izi və
yazılmış ``source_row_hash``-lər dəyişmir).

Qərar nərdivanı (yuxarıdan aşağı, hər pillə öz sətrini möhürləyir):

* ``students_id`` ciddi parse alınmasa / boş massiv → jurnal-səviyyə
  QUARANTINED ``legacy_journal_students_invalid`` (seal açarı = uniqid;
  tələbə açarları hamısı ``uniqid:student`` formasında olduğundan toqquşma
  struktur olaraq mümkün deyil).
* Jurnal J1-də MIGRATED deyilsə (V6 süzgəci və ya karantin) → hər tələbə
  sətri SKIPPED ``legacy_journal_enrollment_orphan`` (jurnal-səviyyə qərarın
  nəticəsi, yeni anomaliya deyil).
* Tələbə EntityMap-da (bu run-un MIGRATED ``student`` müşahidələri) həll
  olunmasa → o TƏLƏBƏ sətri SKIPPED ``legacy_journal_student_unresolved``,
  jurnalın qalan tələbələri davam edir (spec J2).
* Qalanı: ``Enrollment`` get_or_create (org, student, offering) —
  ``kind=mandatory`` (A.2, V-qərarsız defolt).  V7 merge nəticəsində iki
  jurnal eyni offering-i bölüşürsə eyni (student, offering) cütü EYNİ
  Enrollment-ə qatlanır — modelin öz unikallıq açarı qoruyucudur.

Ledger kimlik açarı mətndir (``uniqid:student``), ona görə SA-2 zənciri J1
kimi LEKSİKOQRAFİK sırada yeriyir (``derived_ledger_sort_key = str``).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import JOURNAL_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_authorizer import ENROLLMENT_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    encoded_part,
    source_row_hash,
)
from .rehearsal_identity_phase import STUDENT_ENTITY_TYPE
from .rehearsal_journal_offerings_phase import JOURNAL_OFFERINGS_PHASE_KEY
from .rehearsal_journal_offerings_source import (
    JOURNAL_SOURCE_TABLE,
    journal_rows,
    migrated_target_index,
    parse_group_ids,
    validated_uniqid,
)
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_placement_phase import PLACEMENT_PHASE_KEY
from .rehearsal_sar_phase import SAR_PHASE_KEY
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_ENROLLMENTS_PHASE_KEY = "journal_enrollments"
JOURNAL_ENROLLMENTS_PHASE_ORDER = 36  # journal_offerings-dən (34) sonra
JOURNAL_ENROLLMENT_ENTITY_TYPE = "journal_enrollment"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-enrollments-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_OFFERINGS_PHASE_KEY, PLACEMENT_PHASE_KEY, SAR_PHASE_KEY})

_DERIVATION_PREFIX = b"legacy-rehearsal-journal-enrollment-derivation-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# ``students_id`` ``groups_id`` ilə EYNİ formadadır (JSON-mətn massivi), ona
# görə parse qəsdən paylaşılır — iki ayrı, sakit-sapan parser saxlanmır.
parse_student_ids = parse_group_ids

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "enrollment_materialised",
        _STATE.SKIPPED: "enrollment_skipped",
        _STATE.QUARANTINED: "enrollment_unresolved",
    }
)

# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                # Ciddi parse alınmayan students_id — jurnal bütövlükdə karantinə.
                "legacy_journal_students_invalid",
                # Spec J2: tələbə EntityMap-da yoxdur — sətir SKIPPED, amma anomaliyadır.
                "legacy_journal_student_unresolved",
            ),
            _SEVERITY.WARNING,
        ),
        # Jurnal-səviyyə qərarın (V6/karantin) nəticəsi — yeni anomaliya deyil.
        "legacy_journal_enrollment_orphan": _SEVERITY.INFO,
    }
)


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def enrollment_derivation_hash(
    *,
    seal_key: str,
    row_hash: str,
    outcome_token: str,
    student_ref: str,
    offering_state: str,
    student_state: str,
) -> str:
    """Cross-run-sabit qeydiyyat qərar kimliyi; heç bir UUID/target pk daxil olmur."""

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        JOURNAL_FIELDS.fingerprint,
        seal_key,
        row_hash,
        outcome_token,
        student_ref,
        offering_state,
        student_state,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def _recorded_decision(context: RehearsalContext, seal_key: str):
    """Resume qısayolu: möhürlənmiş qərarı yenidən törətmək əvəzinə oxu."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
            entity_map__legacy_pk=seal_key,
        )
        .values_list("state", "source_row_hash", "target_model_label")
        .first()
    )


def _seal(context, *, seal_key: str, digest: str, state: str, label: str = "", target_pk: str = ""):
    return upsert_entity_map(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
        legacy_pk=seal_key,
        source_row_hash=digest,
        state=state,
        target_model_label=label,
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def _write_issue(context, *, seal_key: str, rule_code: str, digest: str, entity_map, issue_counts) -> None:
    """Issue həmişə öz map-ından sonra: ledger əks sıranı rədd edir."""

    severity = severity_for(rule_code)
    upsert_issue(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        source_table=JOURNAL_SOURCE_TABLE,
        entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
        legacy_pk=seal_key,
        rule_code=rule_code,
        severity=severity,
        payload_digest=digest,
        entity_map_id=entity_map.pk,
    )
    issue_counts[(rule_code, severity)] += 1


class JournalEnrollmentsPhase:
    """J2: jurnal başlıqlarının tələbə siyahısı → Enrollment, tələbə başına bir qərar."""

    phase_key = JOURNAL_ENROLLMENTS_PHASE_KEY
    order = JOURNAL_ENROLLMENTS_PHASE_ORDER
    source_tables = ()
    entity_types = (JOURNAL_ENROLLMENT_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # Açar mətndir (``uniqid:student``): rebuild leksikoqrafik sıralayır.
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

        offerings = migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE)
        students = migrated_target_index(context, STUDENT_ENTITY_TYPE)

        decisions: list[tuple[str, str, str, str]] = []
        seen_uniqids: set[str] = set()
        state_counts: Counter[str] = Counter()
        issue_counts: Counter[tuple[str, str]] = Counter()
        for legacy_pk, row in journal_rows(context):
            probe_cancellation(context)
            uniqid = validated_uniqid(row["uniqid"])
            if uniqid in seen_uniqids:
                # Mənbə attestasiyası "dublikatsız" deyir — ziddiyyət fataldır.
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_journal_uniqid_duplicate")
            seen_uniqids.add(uniqid)
            for seal_key, state, digest, label in self._journal_decisions(
                context,
                legacy_pk=legacy_pk,
                row=row,
                uniqid=uniqid,
                offerings=offerings,
                students=students,
                issue_counts=issue_counts,
            ):
                decisions.append((seal_key, str(state), digest, label))
                state_counts[self.derived_state_key(state)] += 1

        # SA-2: zəncir seal açarının LEKSİKOQRAFİK sırasında — rebuild ilə eyni.
        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        for seal_key, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, state, digest, label)

        context.stdout_note(f"{JOURNAL_ENROLLMENTS_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    def _journal_decisions(self, context, *, legacy_pk, row, uniqid, offerings, students, issue_counts):
        """Bir jurnalın bütün qərarları: parse → jurnal-səviyyə → tələbə-səviyyə."""

        row_hash = source_row_hash(contract=JOURNAL_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        members = parse_student_ids(row["students_id"])
        if members is None:
            recorded = _recorded_decision(context, uniqid)
            if recorded is not None:
                yield (uniqid, *recorded)
                return
            digest = enrollment_derivation_hash(
                seal_key=uniqid,
                row_hash=row_hash,
                outcome_token="unresolved",
                student_ref="",
                offering_state="unread",
                student_state="invalid",
            )
            entity_map = _seal(context, seal_key=uniqid, digest=digest, state=_STATE.QUARANTINED)
            _write_issue(
                context,
                seal_key=uniqid,
                rule_code="legacy_journal_students_invalid",
                digest=digest,
                entity_map=entity_map,
                issue_counts=issue_counts,
            )
            yield uniqid, _STATE.QUARANTINED, digest, ""
            return

        offering_pk = offerings.get(uniqid, "")
        for member in members:
            seal_key = f"{uniqid}:{member}"
            recorded = _recorded_decision(context, seal_key)
            if recorded is not None:
                yield (seal_key, *recorded)
                continue
            yield self._decide_student(
                context,
                seal_key=seal_key,
                row_hash=row_hash,
                student_ref=str(member),
                offering_pk=offering_pk,
                student_pk=students.get(str(member), ""),
                issue_counts=issue_counts,
            )

    def _decide_student(self, context, *, seal_key, row_hash, student_ref, offering_pk, student_pk, issue_counts):
        """Bir tələbə sətrinin qərarı: orphan → unresolved → materialise."""

        if not offering_pk or not student_pk:
            rule_code = "legacy_journal_enrollment_orphan" if not offering_pk else "legacy_journal_student_unresolved"
            digest = enrollment_derivation_hash(
                seal_key=seal_key,
                row_hash=row_hash,
                outcome_token="orphan" if not offering_pk else "unresolved",
                student_ref=student_ref,
                offering_state="resolved" if offering_pk else "missing",
                student_state="resolved" if student_pk else "missing",
            )
            entity_map = _seal(context, seal_key=seal_key, digest=digest, state=_STATE.SKIPPED)
            _write_issue(
                context,
                seal_key=seal_key,
                rule_code=rule_code,
                digest=digest,
                entity_map=entity_map,
                issue_counts=issue_counts,
            )
            return seal_key, _STATE.SKIPPED, digest, ""

        enrollment_model = django_apps.get_model("registrar", "Enrollment")
        with transaction.atomic():
            # V7 merge: iki jurnal eyni offering-i bölüşəndə eyni (student,
            # offering) cütü modelin öz unikallıq açarı ilə EYNİ Enrollment-ə
            # qatlanır — heç vaxt çılpaq ``create`` yoxdur.
            enrollment, _created = enrollment_model.objects.get_or_create(
                organization=context.organization,
                student_id=student_pk,
                offering_id=offering_pk,
                # A.2: ``kind`` defoltu V-qərarsız ``mandatory``; status modelin
                # öz defoltu (enrolled) qalır — J7-dən əvvəl heç nə bağlanmır.
                defaults={"kind": "mandatory"},
            )
            digest = enrollment_derivation_hash(
                seal_key=seal_key,
                row_hash=row_hash,
                outcome_token="materialised",
                student_ref=student_ref,
                offering_state="resolved",
                student_state="resolved",
            )
            entity_map = _seal(
                context,
                seal_key=seal_key,
                digest=digest,
                state=_STATE.MIGRATED,
                label=ENROLLMENT_MODEL_LABEL,
                target_pk=str(enrollment.pk),
            )
        # Materialised sətrin issue-su yoxdur — map onsuz da hədəfi göstərir.
        del entity_map
        return seal_key, _STATE.MIGRATED, digest, ENROLLMENT_MODEL_LABEL
