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

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import JOURNAL_FIELDS
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
from .rehearsal_journal_batch import Decision, JournalBatchWriter, TargetMaterialiser
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
                # 2026-08-28 (Rehearsal #7): tələbə map-dadır, LAKİN hesabı hələ
                # aktivləşməyib (``sar_materialisation`` onu deferred saxlayıb —
                # məsələn qəbul ili tapılmayan kohort).  PG ``registrar_guard_
                # active_member`` belə ``Enrollment``-i rədd edir, ona görə sətir
                # ÖNCƏDƏN atlanır: fail-closed, run çökmür, qeyd itmir.
                "legacy_journal_student_inactive",
            ),
            _SEVERITY.WARNING,
        ),
        # Jurnal-səviyyə qərarın (V6/karantin) nəticəsi — yeni anomaliya deyil.
        "legacy_journal_enrollment_orphan": _SEVERITY.INFO,
    }
)


def active_member_ids(context) -> frozenset[str]:
    """Bu tenantda AKTİV üzvlüyü olan istifadəçi açarları.

    ``registrar_guard_active_member`` (PG) ``Enrollment.student`` üçün aktiv
    üzvlük + aktiv rol + aktiv hesab tələb edir.  Staged (aktivləşməmiş) hesab
    üçün yazı DB səviyyəsində rədd olunur — faza bunu ÖNCƏDƏN bilməlidir, əks
    halda tutulmamış ``IntegrityError`` bütün run-u dayandırır (Rehearsal #7).
    """

    membership_model = django_apps.get_model("organizations", "Membership")
    rows = membership_model.objects.filter(
        organization=context.organization,
        is_active=True,
        role__is_active=True,
        user__is_active=True,
    ).values_list("user_id", flat=True)
    return frozenset(str(pk) for pk in rows)


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


def recorded_decisions(context: RehearsalContext) -> dict[str, tuple[str, str, str]]:
    """Bu run-un BÜTÜN qeydiyyat möhürləri — resume üçün BİR sorğu.

    Əvvəl hər sətir üçün ayrıca ``.first()`` sorğusu gedirdi (172 471 sorğu);
    açar sayı jurnal klasterinin ölçüsündədir, ona görə tam indeks yaddaşa
    sığır (``JournalSealer.recorded_decisions`` ilə eyni prinsip).
    """

    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id, entity_map__entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE
    ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
    return {
        legacy_pk: (state, row_hash, label) for legacy_pk, state, row_hash, label in rows.iterator(chunk_size=10_000)
    }


ENROLLMENT_MATERIALISER = TargetMaterialiser(
    app_label="registrar",
    model_name="Enrollment",
    # V7 merge: modelin öz unikallıq açarı — eyni cüt EYNİ sətrə qatlanır.
    key_fields=("student_id", "offering_id"),
    # A.2: ``kind`` defoltu V-qərarsız ``mandatory``; status modelin öz
    # defoltu (enrolled) qalır — J7-dən əvvəl heç nə bağlanmır.
    defaults=MappingProxyType({"kind": "mandatory"}),
)


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
        # Aktiv üzvlük indeksi: hansı tələbə hesabı üçün ``Enrollment``
        # yazısı DB qapısından keçə bilər (bax ``active_member_ids``).
        active_students = active_member_ids(context)
        recorded = recorded_decisions(context)
        writer = JournalBatchWriter(
            context,
            entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
            source_table=JOURNAL_SOURCE_TABLE,
            severity_for=severity_for,
            materialiser=ENROLLMENT_MATERIALISER,
        )

        decisions: list[tuple[str, str, str, str]] = []
        seen_uniqids: set[str] = set()
        state_counts: Counter[str] = Counter()
        for legacy_pk, row in journal_rows(context):
            probe_cancellation(context)
            uniqid = validated_uniqid(row["uniqid"])
            if uniqid in seen_uniqids:
                # Mənbə attestasiyası "dublikatsız" deyir — ziddiyyət fataldır.
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_journal_uniqid_duplicate")
            seen_uniqids.add(uniqid)
            for decision in self._journal_decisions(
                legacy_pk=legacy_pk,
                row=row,
                uniqid=uniqid,
                offerings=offerings,
                students=students,
                active_students=active_students,
                recorded=recorded,
            ):
                if isinstance(decision, Decision):
                    writer.add(decision)
                    entry = (decision.seal_key, str(decision.state), decision.digest, decision.label)
                else:
                    entry = decision  # resume: möhür artıq bu run-dadır
                decisions.append(entry)
                state_counts[self.derived_state_key(entry[1])] += 1
        writer.flush()

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
            issue_counts=MappingProxyType(dict(writer.issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    def _journal_decisions(self, *, legacy_pk, row, uniqid, offerings, students, active_students, recorded):
        """Bir jurnalın bütün qərarları: parse → jurnal-səviyyə → tələbə-səviyyə."""

        row_hash = source_row_hash(contract=JOURNAL_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        members = parse_student_ids(row["students_id"])
        if members is None:
            previous = recorded.get(uniqid)
            if previous is not None:
                yield (uniqid, *previous)
                return
            yield Decision(
                seal_key=uniqid,
                state=_STATE.QUARANTINED,
                digest=enrollment_derivation_hash(
                    seal_key=uniqid,
                    row_hash=row_hash,
                    outcome_token="unresolved",
                    student_ref="",
                    offering_state="unread",
                    student_state="invalid",
                ),
                rule_codes=("legacy_journal_students_invalid",),
            )
            return

        offering_pk = offerings.get(uniqid, "")
        for member in members:
            seal_key = f"{uniqid}:{member}"
            previous = recorded.get(seal_key)
            if previous is not None:
                yield (seal_key, *previous)
                continue
            student_pk = students.get(str(member), "")
            yield self._decide_student(
                seal_key=seal_key,
                row_hash=row_hash,
                student_ref=str(member),
                offering_pk=offering_pk,
                student_pk=student_pk,
                student_is_active=bool(student_pk) and student_pk in active_students,
            )

    def _decide_student(self, *, seal_key, row_hash, student_ref, offering_pk, student_pk, student_is_active):
        """Bir tələbə sətrinin qərarı: orphan → unresolved → inactive → materialise."""

        if not offering_pk or not student_pk:
            rule_code = "legacy_journal_enrollment_orphan" if not offering_pk else "legacy_journal_student_unresolved"
            return Decision(
                seal_key=seal_key,
                state=_STATE.SKIPPED,
                digest=enrollment_derivation_hash(
                    seal_key=seal_key,
                    row_hash=row_hash,
                    outcome_token="orphan" if not offering_pk else "unresolved",
                    student_ref=student_ref,
                    offering_state="resolved" if offering_pk else "missing",
                    student_state="resolved" if student_pk else "missing",
                ),
                rule_codes=(rule_code,),
            )

        if not student_is_active:
            # Hesab map-dadır, amma hələ staged-dir: DB qapısı yazını rədd edərdi.
            # Sətir atlanır, jurnalın qalanı davam edir (fail-closed, itki yox).
            return Decision(
                seal_key=seal_key,
                state=_STATE.SKIPPED,
                digest=enrollment_derivation_hash(
                    seal_key=seal_key,
                    row_hash=row_hash,
                    outcome_token="inactive",
                    student_ref=student_ref,
                    offering_state="resolved",
                    student_state="inactive",
                ),
                rule_codes=("legacy_journal_student_inactive",),
            )

        # Materialised sətrin issue-su yoxdur — map onsuz da hədəfi göstərir.
        return Decision(
            seal_key=seal_key,
            state=_STATE.MIGRATED,
            digest=enrollment_derivation_hash(
                seal_key=seal_key,
                row_hash=row_hash,
                outcome_token="materialised",
                student_ref=student_ref,
                offering_state="resolved",
                student_state="resolved",
            ),
            label=ENROLLMENT_MODEL_LABEL,
            natural_key=(student_pk, offering_pk),
        )
