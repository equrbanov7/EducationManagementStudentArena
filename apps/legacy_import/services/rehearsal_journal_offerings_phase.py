"""Phase: ``journal_offerings`` (J1) — ``journals`` → registrar.CourseOffering.

Derived faza (``source_tables = ()``): mənbə ``rehearsal_journal_offerings_source``
ilə axıdılır, hədəflər ``rehearsal_journal_offerings_targets`` ilə yazılır; bu
modul qərar nərdivanına, indeks keşlərinə və digest zəncirinə sahibdir.

Qərar nərdivanı (yuxarıdan aşağı, hər pillə öz sətrini möhürləyir):

* J-V6 — ``fake=1`` VƏ YA ``sonra_sil=1`` → SKIPPED
  ``legacy_journal_discarded_source`` (uniqid ledger-də qalır).
* J-V7 — ``groups_id`` parse xətası / boş massiv → jurnal-səviyyə QUARANTINED
  ``legacy_journal_groups_invalid``.  Fənn/dövr istinadı tapılmasa yenə
  jurnal-səviyyə QUARANTINED (offering onlarsız mövcud deyil).
* J-V7 (2026-08-28, sahibin qərarı) — qalan jurnal QRUP-BAŞINA DİLİMLƏRƏ
  bölünür: ``groups_id`` massivinin HƏR üzvü öz ``CourseOffering``-ini alır,
  möhür açarı ``uniqid:<qrup>``dur (``rehearsal_journal_slices.slice_key``).
  Qrupu EntityMap-da tapılmayan dilim QUARANTINED
  ``legacy_journal_group_unresolved`` olur, jurnalın qalan dilimləri davam edir.
  Çoxqruplu jurnal hər dilimdə İNFO ``legacy_journal_multi_group`` alır — kod
  köhnədir, mənası artıq «N dilimə bölündü»dür.
* J-V5 — ``teacher_id`` həlli tapılmasa ``instructor=NULL`` + İNFO
  ``legacy_journal_instructor_unresolved`` (legacy teacher_id qərar kimliyində).

Birləşmə (C6): legacy-də eyni fənn üçün həm BİRLƏŞMİŞ (çoxqruplu), həm də QRUP
jurnalı ola bilər.  Bölmədən sonra ikisi EYNİ ``(subject, period, group)``
açarına düşür və ``get_or_create`` onları BİR açılışa qatlayır — bu qəsdəndir:
davamiyyət birləşmiş jurnaldan, ballar qrup jurnalından gəlsə də tələbə tək
jurnal səhifəsi görür.  İkinci gələn dilim İNFO ``legacy_journal_offering_merged``
alır və qərar kimliyində BİRİNCİ sahibin ``uniqid``-ini daşıyır (``merged_text``),
yəni «hansı jurnal açılışı açdı» sualı ledger-dən cavablanır.  Skalyar sahələr
(müəllim) ilk sahibindir; xanalar isə əlavə olunur, mövcud yazı üzərinə yalnız
arxiv qaydası (``allow_existing``) ilə yazılır.

Ledger kimlik açarı mətndir, ona görə SA-2 zənciri LEKSİKOQRAFİK sırada yeriyir:
canlı keçid qərarları yığıb sıralayır, ``derived_ledger_sort_key`` hook-u isə
ledger rebuild-inə eyni sıranı verir — iki tərəf bayt-bəbayt üst-üstə düşür.
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
from .rehearsal_journal_batch import Decision, JournalBatchWriter
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
from .rehearsal_journal_slices import slice_key
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
    """J1: jurnal başlıqlarının fənn açılışına çevrilməsi, QRUP başına bir qərar."""

    phase_key = JOURNAL_OFFERINGS_PHASE_KEY
    order = JOURNAL_OFFERINGS_PHASE_ORDER
    source_tables = ()
    entity_types = (COURSE_OFFERING_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # Açar mətndir (``uniqid`` və ya ``uniqid:qrup``): rebuild leksikoqrafik sıralayır.
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

        indexes = {
            "subjects": migrated_target_index(context, SUBJECT_ENTITY_TYPE),
            "periods": migrated_target_index(context, ACADEMIC_PERIOD_ENTITY_TYPE),
            "groups": migrated_target_index(context, GROUP_ENTITY_TYPE),
            "instructors": migrated_target_index(context, WORKER_ENTITY_TYPE),
        }

        recorded = recorded_decisions(context)
        # V5: açılışın müəllimi qərar anında bəllidir, materialiser isə onu
        # təbii açardan deyil, bu xəritədən oxuyur (açar (subject, period, group)).
        instructor_for_key: dict[tuple, str] = {}
        # Açar → açılışın dərs saatı (``journals.fenn_saati``); birləşmədə
        # İLK QEYRİ-SIFIR dəyər qalır — sıfır saatlı jurnal dolu olanı
        # üstələməsin, qərar isə mənbə sırasında deterministik olsun.
        hours_for_key: dict[tuple, int] = {}
        writer = JournalBatchWriter(
            context,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            source_table=JOURNAL_SOURCE_TABLE,
            severity_for=severity_for,
            materialiser=offering_materialiser(
                lambda key: instructor_for_key.get(key, ""),
                lambda key: hours_for_key.get(key, 0),
            ),
        )

        decisions: list[tuple[str, str, str, str]] = []
        seen_uniqids: set[str] = set()
        state_counts: Counter[str] = Counter()
        # Açar → onu İLK tutan jurnalın ``uniqid``-i (birləşmə sahibi, C6).
        claimed_keys: dict[tuple[str, str, str], str] = {}
        for legacy_pk, row in journal_rows(context):
            probe_cancellation(context)
            uniqid = validated_uniqid(row["uniqid"])
            if uniqid in seen_uniqids:
                # Mənbə attestasiyası "dublikatsız" deyir — ziddiyyət fataldır.
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_journal_uniqid_duplicate")
            seen_uniqids.add(uniqid)
            for seal_key, outcome in self._journal_entries(
                legacy_pk=legacy_pk,
                row=row,
                uniqid=uniqid,
                indexes=indexes,
                recorded=recorded,
                claimed_keys=claimed_keys,
                instructor_for_key=instructor_for_key,
                hours_for_key=hours_for_key,
            ):
                if isinstance(outcome, Decision):
                    writer.add(outcome)
                    entry = (seal_key, str(outcome.state), outcome.digest, outcome.label)
                else:
                    entry = (seal_key, *outcome)  # resume: möhür artıq bu run-dadır
                decisions.append(entry)
                state_counts[self.derived_state_key(entry[1])] += 1
        writer.flush()

        # SA-2: zəncir möhür açarının LEKSİKOQRAFİK sırasında — rebuild ilə eyni.
        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        for seal_key, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, state, digest, label)

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

    def _journal_entries(
        self, *, legacy_pk, row, uniqid, indexes, recorded, claimed_keys, instructor_for_key, hours_for_key
    ):
        """Bir jurnalın BÜTÜN möhürləri: jurnal-səviyyə qərar VƏ YA dilimlər."""

        row_hash = source_row_hash(contract=JOURNAL_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        if legacy_int(row["fake"]) == 1 or legacy_int(row["sonra_sil"]) == 1:
            previous = recorded.get(uniqid)
            yield uniqid, previous if previous is not None else discarded_decision(uniqid=uniqid, row_hash=row_hash)
            return

        members = parse_group_ids(row["groups_id"])
        base, info_codes = self._request(row=row, uniqid=uniqid, row_hash=row_hash, members=members, indexes=indexes)
        blocking = self._blocking_codes(members=members, subject_pk=base.subject_pk, period_pk=base.period_pk)
        if blocking:
            previous = recorded.get(uniqid)
            if previous is not None:
                yield uniqid, previous
                return
            request = replace(base, group_state="invalid" if members is None else "unread")
            yield uniqid, unresolved_decision(request=request, rule_codes=(*blocking, *info_codes))
            return

        for member in members:
            yield self._slice_entry(
                base=base,
                info_codes=(*info_codes, *(("legacy_journal_multi_group",) if len(members) > 1 else ())),
                uniqid=uniqid,
                member=member,
                multi=len(members) > 1,
                indexes=indexes,
                recorded=recorded,
                claimed_keys=claimed_keys,
                instructor_for_key=instructor_for_key,
                hours_for_key=hours_for_key,
            )

    def _blocking_codes(self, *, members, subject_pk, period_pk) -> tuple[str, ...]:
        """Bütün jurnalı karantinə atan istinad boşluqları (dilimlərdən əvvəl)."""

        codes = []
        if members is None:
            codes.append("legacy_journal_groups_invalid")
        if not subject_pk:
            codes.append("legacy_journal_subject_unresolved")
        if not period_pk:
            codes.append("legacy_journal_period_unresolved")
        return tuple(codes)

    def _request(self, *, row, uniqid, row_hash, members, indexes) -> tuple[OfferingRequest, tuple[str, ...]]:
        """Dilimlərin paylaşdığı sabit hissə + jurnal-səviyyə İNFO kodları."""

        teacher_id = legacy_int(row["teacher_id"])
        instructor_pk = indexes["instructors"].get(str(teacher_id), "")
        request = OfferingRequest(
            uniqid=uniqid,
            seal_key=uniqid,
            slice_ref="",
            row_hash=row_hash,
            subject_pk=indexes["subjects"].get(str(legacy_int(row["lesson_id"])), ""),
            period_pk=indexes["periods"].get(str(legacy_int(row["semestr"])), ""),
            group_pk="",
            instructor_pk=instructor_pk,
            subject_ref=str(legacy_int(row["lesson_id"])),
            period_ref=str(legacy_int(row["semestr"])),
            groups_token="" if members is None else ",".join(str(member) for member in members),
            group_state="unread",
            # V5: legacy teacher_id qərar kimliyində saxlanılır (İNFO payload-ı).
            instructor_state=f"resolved:{teacher_id}" if instructor_pk else f"unresolved:{teacher_id}",
            merged_text="0",
            lesson_hours=max(0, legacy_int(row["fenn_saati"])),
        )
        codes = () if instructor_pk else ("legacy_journal_instructor_unresolved",)
        # Qayıb limitinin məxrəci: mənbədə 0/boşdursa TƏXMİN EDİLMİR, açılış
        # 0 saatla qalır və sətir İNFO ilə işarələnir.
        if legacy_int(row["fenn_saati"]) <= 0:
            codes = (*codes, "legacy_journal_lesson_hours_missing")
        return request, codes

    def _slice_entry(self, *, base, info_codes, uniqid, member, multi, indexes, recorded, claimed_keys, **rest):
        """Bir qrup dilimi: resume → qrup həlli → birləşmə → materialise."""

        instructor_for_key = rest["instructor_for_key"]
        hours_for_key = rest["hours_for_key"]
        group_ref = str(member)
        seal_key = slice_key(uniqid, group_ref)
        group_pk = indexes["groups"].get(group_ref, "")
        key = (base.subject_pk, base.period_pk, group_pk)

        previous = recorded.get(seal_key)
        if previous is not None:
            if previous[0] == _STATE.MIGRATED and group_pk:
                # Resume olunan MIGRATED dilim də birləşmə açarını tutur ki,
                # yarımçıq keçiddən sonrakı davam eyni İNFO-nu törətsin.
                claimed_keys.setdefault(key, uniqid)
                instructor_for_key.setdefault(key, base.instructor_pk)
                _claim_hours(hours_for_key, key, base.lesson_hours)
            return seal_key, previous

        request = replace(
            base,
            seal_key=seal_key,
            slice_ref=group_ref,
            group_pk=group_pk,
            group_state="split" if multi else "resolved",
        )
        if not group_pk:
            request = replace(request, group_state="unresolved")
            return seal_key, unresolved_decision(
                request=request, rule_codes=("legacy_journal_group_unresolved", *info_codes)
            )

        owner = claimed_keys.get(key)
        if owner is None:
            claimed_keys[key] = uniqid
        else:
            # C6: açarı əvvəlki jurnal (və ya bu jurnalın əvvəlki dilimi) tutub —
            # ``get_or_create`` eyni açılışa qatlayır, sahib dəyişmir.
            info_codes = (*info_codes, "legacy_journal_offering_merged")
            request = replace(request, merged_text=f"1:{owner}")
        # İlk qalib açılışın müəllimi qalır: merge olunan jurnal mövcud sətri
        # dəyişmir (``get_or_create`` semantikasının eynisi).
        instructor_for_key.setdefault(key, base.instructor_pk)
        _claim_hours(hours_for_key, key, base.lesson_hours)
        return seal_key, offering_decision(request=request, rule_codes=info_codes)


def _claim_hours(hours_for_key, key, lesson_hours: int) -> None:
    """Birləşmiş açılışın dərs saatı: İLK QEYRİ-SIFIR dəyər qalır.

    C6-da eyni açara qatlanan jurnallardan biri 0 saatlıdırsa (mənbədə sütun
    boşdur), o, dolu olanı ÜSTƏLƏMƏMƏLİDİR; mənbə sırası sabit olduğundan
    qərar deterministikdir.
    """

    if lesson_hours > 0 and not hours_for_key.get(key):
        hours_for_key[key] = lesson_hours
