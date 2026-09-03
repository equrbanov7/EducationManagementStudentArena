"""Phase: ``syllabus_migration`` (J12) — 8,248 köhnə sillabus → ``apps.syllabus``.

Niyə var: köhnə MyEdu-da 8,248 sillabus (12 cədvəl, canlı ölçü ilə 285,780
peyk sətri) var; yeni sillabus modulu isə boşdur.  Bu faza onları «baza
sillabus» dosyeləri kimi gətirir — sahibin tələbi ilə TƏSDİQLƏNMİŞ, amma saxta
insan imzası olmadan (``approval_source="migration"``).

Niyə sıra 30
------------
Sillabus iki hədəfə söykənir: fənn (``lesson_subject``, J-catalog, sıra 12) və
müəllim (``worker``, ``identity_cohort``, sıra 20).  Hər ikisi bu fazadan
ƏVVƏL materiallaşmalıdır, çünki ``Syllabus.subject`` PROTECT FK-dır və
``Syllabus.author`` istifadəçi açarıdır.  Registry-də 30 məhz «jurnaldan ASILI
OLMAYAN sillabus işi» üçün rezerv saxlanılmışdı (bax
``rehearsal_contracts._EXPECTED_PHASE_REGISTRY_FINGERPRINT`` şərhi); J9
(``journal_selfwork``, 45) açılışa bağlı olduğu üçün oradadır, bu faza isə
açılışa toxunmur — ona görə rezervin yerinə, ``worker_materialisation``-dan
(26) və ``sar_materialisation``-dan (28) sonra, ``journal_periods``-dan (32)
əvvəl oturur.

Mənbə qapısı
------------
12 cədvəlin hamısı plan-da ``design_gated``-dir → faza onları batch zəncirinə
İDDİA ETMİR (``source_tables = ()``).  Gated olmaq iddiaya qadağadır, oxumağa
yox (J9/J11 presedenti); sübut bütövlüklə fazanın öz möhürlərində yaşayır.

HƏDƏF DOSYESİ üzrə qruplaşma (mənbə cütü ilə EYNİ DEYİL)
========================================================
Mənbənin təbii açarı (``lesson_id``, ``teacher_id``) cütüdür, hədəfin «baza
sillabus» açarı isə (``subject``, ``author``) cütüdür — və bu ikisi BİR-BİRİNƏ
TAM UYĞUN DEYİL:

* iki fərqli legacy müəllim eyni hədəf istifadəçisinə həll oluna bilər
  (kimlik fazasının dedup-u), yəni iki nərdivan EYNİ dosyeyə düşür.

⚠️ MÜƏLLİMİ HƏLL OLUNMAYAN 956 BAŞLIQ YAZILMIR (sahibin 2026-08-31 qərarı)
==========================================================================
Canlı ölçü (2026-08-30): 956 başlığın ``teacher_id``-si silinmiş işçiyə baxır
(112 fərqli id, 518 fərqli fənn).  Əvvəlki plan onları ``author=NULL`` ilə
köçürürdü; sahib isə açıq dedi: «o sillabuslar lazım deyil, onları sil getsin,
dəymə heç» (spec §9).  Ona görə həmin nərdivanlar HƏDƏFƏ YAZILMIR.

Nə DƏYİŞMİR — qəsdən: ledger qeydi qalır.  «Sil getsin» = hədəfə yazılmasın;
mənbə sətrinin qərarı yenə möhürlənir (``state=SKIPPED`` +
``legacy_syllabus_instructor_unresolved``) ki, uzlaşdırma nərdivanında
8,248 → hədəf sayı İZAHSIZ qalıq verməsin.  Yazılmayan nərdivan dosye də
AÇMIR, ona görə 518 müəllimsiz fənn dosyesi və onlarla gələn 193
``dossier_merged`` birləşməsi ARTIQ YARANMIR (yenilənmiş proqnoz: ≈4,935 hədəf
dosyesi).

``Syllabus`` modelində «bir dosyedə YALNIZ BİR APPROVED» və «versiya nömrəsi
təkrarlanmaz» unikal məhdudiyyətləri var, ona görə qruplaşma məhz HƏDƏF açarı
üzrə aparılır: bir dosyeyə düşən bütün nərdivanlar ardıcıl birləşdirilir,
versiyalar v1.0…v1.N kimi yenidən nömrələnir və TƏK bir APPROVED seçilir (ən
sonuncu aktiv pillə).  Belə hər birləşmə ``legacy_syllabus_dossier_merged``
ilə sayılır — səssiz birləşdirmə yoxdur.

Resume
------
Bir dosyenin bütün versiyaları və möhürləri BİR ``transaction.atomic()``
içindədir, yəni dosye ya tam möhürlənib, ya heç.  Yarımçıq möhürlənmiş dosye
məntiqən mümkün deyil; görünərsə fail-closed dayanılır
(``legacy_syllabus_dossier_partially_sealed``).
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap

from .rehearsal_catalog_phase import CATALOG_PHASE_KEY
from .rehearsal_catalog_targets import SUBJECT_ENTITY_TYPE
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_identity_phase import IDENTITY_PHASE_KEY, WORKER_ENTITY_TYPE
from .rehearsal_journal_offerings_source import migrated_target_index
from .rehearsal_structure_phase import probe_cancellation
from .rehearsal_syllabus_documents import (
    INSTRUCTOR_UNRESOLVED,
    VERSION_FOLDED,
    build_syllabus_snapshot,
)
from .rehearsal_syllabus_source import AMBIGUOUS_UNIQID, ORPHAN_UNIQID
from .rehearsal_syllabus_targets import (
    DOSSIER_MERGED,
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    SUBJECT_UNRESOLVED,
    SYLLABUS_ENTITY_TYPE,
    SYLLABUS_SEALER,
    SyllabusDossierWriter,
    SyllabusWriteRequest,
    build_section_data,
    resolved_entry,
)

SYLLABUS_MIGRATION_PHASE_KEY = "syllabus_migration"
SYLLABUS_MIGRATION_PHASE_ORDER = 30  # sar_materialisation (28) ilə journal_periods (32) arasında
#: ⚠️ ``v2``: ``content_digest`` TƏMİZLƏNMİŞ mətn üzərində hesablanır, təmizləmə
#: resepti isə dəyişdi — peyklərin ``name`` sütunu artıq ``clean_multiline_text``
#: ilə gəlir (sətir sonları saxlanılır, canlı: 23,574 sətir).  Eyni mənbə
#: sətri ona görə ``v1``-dəkindən BAŞQA derivation hash verir; nömrəni
#: artırmamaq köhnə möhürü yeni kodla təkrar törədilə bilməz edərdi.
#: ``v3``: sahibin qərarı ilə müəllimi həll olunmayan nərdivanın QƏRARI dəyişdi
#: (``imported`` → ``teacher_unresolved``, ``MIGRATED`` → ``SKIPPED``), yəni
#: eyni mənbə sətri yenə BAŞQA derivation hash verir — eyni səbəbdən yenə
#: nömrələnir.
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-syllabus-migration-v3"
REQUIRED_PHASE_KEYS = frozenset({CATALOG_PHASE_KEY, IDENTITY_PHASE_KEY})
#: Yetim ``uniqid`` möhürünün açar prefiksi (``OPAQUE_KEY_PATTERN``-ə uyğun).
ORPHAN_SEAL_PREFIX = "orphan:"

_STATE = LegacyEntityMap.State

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "syllabus_versions_written",
        _STATE.SKIPPED: "syllabus_rows_represented",
        _STATE.QUARANTINED: "syllabus_unresolved",
    }
)


def dossier_key(ladder, *, subjects, instructors) -> tuple[str, str]:
    """Nərdivanın HƏDƏF dosyesi açarı: ``(subject_pk, author_pk)``.

    HƏR İKİ yarı boş ola bilər və hər ikisi «hədəfə yazılmır» deməkdir, amma
    SƏBƏBLƏRİ fərqlidir və ona görə nəticələri də fərqlidir:

    * boş ``subject_pk`` — fənn bu run-da materiallaşmayıb, yəni köçürmə onu
      HƏLL EDƏ BİLMİR → ``QUARANTINED`` (baxılmalı qalıq);
    * boş ``author_pk`` — müəllim köhnə sistemdə silinib və sahib həmin 956
      sillabusu istəmir (spec §9) → ``SKIPPED`` (qərar verilmiş qalıq).
    """

    return (
        subjects.get(str(ladder.lesson_id), ""),
        instructors.get(str(ladder.teacher_id), ""),
    )


def _header_codes(document, *, ambiguous, author_pk: str) -> tuple[str, ...]:
    """Başlığın öz qeydləri: dil, ambiqü ``uniqid``, həll olunmayan müəllim."""

    codes = list(document.header.issues)
    if document.header.uniqid in ambiguous:
        codes.append(AMBIGUOUS_UNIQID)
    if not author_pk:
        codes.append(INSTRUCTOR_UNRESOLVED)
    return tuple(codes)


class SyllabusMigrationPhase:
    """J12: köhnə sillabusların «baza sillabus» dosyeləri kimi köçürülməsi."""

    phase_key = SYLLABUS_MIGRATION_PHASE_KEY
    order = SYLLABUS_MIGRATION_PHASE_ORDER
    source_tables = ()
    entity_types = (SYLLABUS_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # Möhür açarı həm ``<sillabus.id>``, həm ``orphan:<uniqid>`` ola bilir.
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

        snapshot = build_syllabus_snapshot(context)
        probe_cancellation(context)
        subjects = migrated_target_index(context, SUBJECT_ENTITY_TYPE)
        instructors = migrated_target_index(context, WORKER_ENTITY_TYPE)
        recorded = SYLLABUS_SEALER.recorded_decisions(context)

        writer = SyllabusDossierWriter(context)
        self._write_dossiers(
            context,
            snapshot=snapshot,
            subjects=subjects,
            instructors=instructors,
            recorded=recorded,
            writer=writer,
        )
        self._write_orphans(snapshot=snapshot, recorded=recorded, writer=writer)

        decisions = list(recorded.items())
        decisions.extend(writer.sealed)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{SYLLABUS_MIGRATION_PHASE_KEY}.records.{sum(state_counts.values())}")
        context.stdout_note(f"{SYLLABUS_MIGRATION_PHASE_KEY}.versions.{writer.written_versions}")
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

    # ── Qərar qatı ──────────────────────────────────────────────────────────

    def _write_dossiers(self, context, *, snapshot, subjects, instructors, recorded, writer) -> None:
        """Nərdivanları hədəf dosyesinə görə qrupla və dosye-dosye yaz."""

        # Qruplaşma açarı sıra üçündür; həll olunmuş açarlar isə DƏYƏRDƏ qalır,
        # çünki fənni həll olunmayan qrupun açarı ARTIQ hədəf açarı deyil.
        grouped: dict[tuple[str, str], tuple[str, str, list]] = {}
        for ladder in snapshot.ladders:
            subject_pk, author_pk = dossier_key(ladder, subjects=subjects, instructors=instructors)
            if not subject_pk or not author_pk:
                # HƏDƏFƏ YAZILMAYAN nərdivan dosye AÇMIR, ona görə başqa
                # nərdivanla da birləşmir — hər biri təkbaşına qərar alır
                # (``dossier_merged`` səs-küyü yaranmasın).  Açarın həll olunmuş
                # yarısı İTMİR: qərar sətri yalnız ÖZ səbəbini daşımalıdır.
                grouped[("", f"{ladder.lesson_id}:{ladder.teacher_id}")] = (subject_pk, author_pk, [ladder])
                continue
            grouped.setdefault((subject_pk, author_pk), (subject_pk, author_pk, []))[2].append(ladder)

        for _group_key, (subject_pk, author_pk, ladders) in sorted(grouped.items()):
            probe_cancellation(context)
            requests, resolved = self._plan_dossier(
                ladders,
                subject_pk=subject_pk,
                author_pk=author_pk,
                ambiguous=snapshot.ambiguous_uniqids,
            )
            if self._already_sealed(requests, resolved, recorded=recorded):
                continue
            writer.write(requests, resolved=resolved)

    def _already_sealed(self, requests, resolved, *, recorded) -> bool:
        """Dosye artıq bu run-da möhürlənibmi (hamısı və ya heç biri)."""

        keys = [request.seal_key for request in requests]
        keys.extend(entry.seal_key for entry in resolved)
        if not keys:
            return True
        sealed = sum(1 for key in keys if key in recorded)
        if sealed == 0:
            return False
        if sealed != len(keys):
            # Dosye TƏK tranzaksiyada yazılır; yarımçıq möhür məntiqən mümkün
            # deyil, görünürsə ledger başqa kodla yazılıb — fail closed.
            raise LegacyRehearsalEvidenceError("legacy_syllabus_dossier_partially_sealed")
        return True

    def _plan_dossier(self, ladders, *, subject_pk: str, author_pk: str, ambiguous):
        """Bir hədəf dosyesinin bütün pillələri + hədəfsiz qərarları."""

        merged = len(ladders) > 1
        steps: list[tuple[object, tuple[str, ...], bool]] = []
        resolved = []
        for ladder in ladders:
            for version in ladder.versions:
                codes = [
                    *_header_codes(version.document, ambiguous=ambiguous, author_pk=author_pk),
                    *version.issues,
                ]
                if merged:
                    codes.append(DOSSIER_MERGED)
                steps.append((version, tuple(codes), version.approved))
                resolved.extend(
                    self._folded_entries(
                        version,
                        subject_pk=subject_pk,
                        author_pk=author_pk,
                        merged=merged,
                        ambiguous=ambiguous,
                    )
                )

        if not subject_pk:
            return [], [*resolved, *self._unwritten(steps, outcome="subject_unresolved", extra=(SUBJECT_UNRESOLVED,))]
        if not author_pk:
            # Sahibin qərarı (spec §9): müəllimi silinmiş 956 sillabus YAZILMIR.
            # Kod ``_header_codes``-dan onsuz da gəlir, ona görə ``extra`` boşdur.
            return [], [*resolved, *self._unwritten(steps, outcome="teacher_unresolved", extra=())]

        # Birləşən dosyedə pillələr QLOBAL xronologiyaya düzülür: mənbənin
        # yeganə real zaman siqnalı ``sillabus.id`` auto-increment-idir, ona görə
        # iki nərdivan bir-birinin ardına yapışdırılmır, ID sırasında hörülür.
        steps.sort(key=lambda step: step[0].document.header.legacy_pk)
        approved_index = -1
        for index, (_version, _codes, approved) in enumerate(steps):
            if approved:
                approved_index = index  # dosyedə YALNIZ sonuncu aktiv pillə qalib gəlir
        requests = [
            self._request(
                version,
                subject_pk=subject_pk,
                author_pk=author_pk,
                minor=index,
                status=STATUS_APPROVED if index == approved_index else STATUS_ARCHIVED,
                codes=codes,
            )
            for index, (version, codes, _approved) in enumerate(steps)
        ]
        return requests, resolved

    def _folded_entries(self, version, *, subject_pk: str, author_pk: str, merged: bool, ambiguous):
        """Məzmunu eyni olduğu üçün qatlanan mənbə sətirlərinin möhürləri.

        Qatlanan sətir onsuz da ``SKIPPED``-dir; fənn həll olunmayanda isə
        nərdivanın ÖZÜ karantindədir, ona görə qatlananı da karantinə düşür.
        Müəllimsiz nərdivan karantin DEYİL — qərar verilib (spec §9).
        """

        codes = [VERSION_FOLDED]
        if merged:
            codes.append(DOSSIER_MERGED)
        if not subject_pk:
            codes.append(SUBJECT_UNRESOLVED)
        elif not author_pk:
            codes.append(INSTRUCTOR_UNRESOLVED)
        if version.document.header.uniqid in ambiguous:
            codes.append(AMBIGUOUS_UNIQID)
        return [
            resolved_entry(
                seal_key=str(folded_pk),
                outcome="folded",
                parts=(f"into={version.document.header.legacy_pk}", f"content={version.content_digest}"),
                rule_codes=tuple(codes),
                quarantined=not subject_pk,
            )
            for folded_pk in version.folded_source_pks
        ]

    def _unwritten(self, steps, *, outcome: str, extra: tuple[str, ...]):
        """Hədəfə YAZILMAYAN nərdivan: heç nə yazılmır, hər sətir SAYILIR.

        İki səbəb var və ikisi FƏRQLİ qalıq sinfidir (bax :func:`dossier_key`):
        fənn həll olunmayıb → ``QUARANTINED`` (baxılmalı), müəllim silinib →
        ``SKIPPED`` (sahibin qərarı, spec §9).
        """

        quarantined = outcome == "subject_unresolved"
        return [
            resolved_entry(
                seal_key=str(version.document.header.legacy_pk),
                outcome=outcome,
                parts=(f"lesson={version.document.header.lesson_id}", f"content={version.content_digest}"),
                rule_codes=(*codes, *extra),
                quarantined=quarantined,
            )
            for version, codes, _approved in steps
        ]

    def _request(self, version, *, subject_pk, author_pk, minor, status, codes) -> SyllabusWriteRequest:
        header = version.document.header
        section_data, section_codes = build_section_data(version.document)
        return SyllabusWriteRequest(
            seal_key=str(header.legacy_pk),
            subject_pk=subject_pk,
            author_pk=author_pk,
            minor=minor,
            status=status,
            content_digest=version.content_digest,
            section_data=section_data,
            folded_source_pks=version.folded_source_pks,
            rule_codes=(*codes, *section_codes),
            uniqid=header.uniqid,
            lesson_id=header.lesson_id,
            teacher_id=header.teacher_id,
            lesson_hours=header.lesson_hours,
            language=header.language,
            active=header.active,
        )

    def _write_orphans(self, *, snapshot, recorded, writer) -> None:
        """Başlığı olmayan bölmə ``uniqid``-ləri — atılır, amma SAYILIR."""

        entries = [
            resolved_entry(
                seal_key=f"{ORPHAN_SEAL_PREFIX}{uniqid}",
                outcome="orphan",
                parts=tuple(f"{table}={count}" for table, count in sorted(tables.items())),
                rule_codes=(ORPHAN_UNIQID,),
            )
            for uniqid, tables in sorted(snapshot.orphans.items())
            if f"{ORPHAN_SEAL_PREFIX}{uniqid}" not in recorded
        ]
        writer.write([], resolved=entries)


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "DERIVED_STATE_KEYS",
    "ORPHAN_SEAL_PREFIX",
    "REQUIRED_PHASE_KEYS",
    "SYLLABUS_MIGRATION_PHASE_KEY",
    "SYLLABUS_MIGRATION_PHASE_ORDER",
    "SyllabusMigrationPhase",
    "dossier_key",
]
