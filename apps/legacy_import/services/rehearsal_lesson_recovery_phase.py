"""Phase: ``journal_lesson_recovery`` (J12) — çatışmayan dərsi xanadan BƏRPA et.

Niyə var (ölçülmüş, sübutlu)
----------------------------
J4 bir bal xanasını yalnız MÖVCUD ``Lesson``-a bağlaya bilir və dərs indeksi
``journals_dates_added_by_teacher``-dən qurulur.  Canlı mənbədə 570 jurnalın
həmin cədvəli boşdur/qismən boşdur (183-ündə SIFIR sətir), halbuki bal cədvəli
doludur — ona görə **164,747 xana** (11,057 slot · 1,984 tələbə · 567 fənn)
hədəfə heç cür düşmür:

===========================  ========  =========================================
məzmun                          xana   ağırlıq
===========================  ========  =========================================
iştirak (``ie``)              133,215   davamiyyət sübutu
qayıb (``qb``)                 19,108   ``absence_hours`` və buraxılış həddi
rəqəmli bal 1-10               12,029   AKADEMİK QİYMƏT
bal 0                             395   akademik qiymət
===========================  ========  =========================================

Bağlanma artefaktı deyil: mənbədə cəmi 28 orphan dərs sətri var və ``journals``-də
təkrar ``uniqid`` yoxdur.  İtən dərsin ``(ay, gün, saat)`` üçlüyü isə XANANIN
ÖZÜNDƏDİR, yəni dərs uydurulmur — mövcud balın daşıyıcısı BƏRPA olunur.

Sahibin qaydası pozulmur: heç bir mövcud dəyər dəyişmir, yalnız hədəfə çatmayan
sətirlər əlavə olunur.

Nə edir
-------
1. **A keçidi (kəşfiyyat).** J4-ün nərdivanını olduğu kimi yeriyir və yalnız
   ``lesson`` pilləsində ilişən xanaların slotlarını toplayır.
2. **Materiallaşma.** Həmin slotlar üçün ``Lesson`` yaradılır:
   ``is_legacy_synthesised=True`` + ledger kodu ``legacy_lesson_synthesised``.
   Növ J3-ün öz ``LessonKindIndex``-i ilə (bal daşıyan xana LECTURE-un altında
   gizlənməsin), saat/mövzu/otaq isə J11-in ``journals_dates_rooms``
   metadatasından — dövr-şüurlu saat qaydası ilə (bax recovery_source).
3. **B keçidi (yazı).** Eyni nərdivan genişlənmiş dərs indeksi ilə təkrarlanır;
   xanalar J4-ün öz ``LessonMarkWriter``-i ilə yazılır (xalis INSERT, mövcud
   xana ÜSTÜNDƏN YAZILMIR).  Sonra ``recompute_absence_hours``.
4. **Toqquşma sübutu.** Hədəf açarı ``(lesson, enrollment)`` jurnal
   ``uniqid``-ini daxil etmir, J-V4 dedup açarı isə edir — 13,875 jurnal 11,115
   açılışa birləşir.  Dəyərlər eynidirsə itki yoxdur; FƏRQLİDİRSƏ uduzan indiyə
   qədər heç yerdə saxlanmırdı.  B (təqvim) və C (komponent) keçidləri uduzanı
   ``registrar.LegacyGradeFact``-a append-only yazır.  **Qalib DƏYİŞMİR.**

Nə ETMİR
--------
* Mövcud ``Lesson`` sətrinə toxunmur (nə saat, nə mövzu, nə otaq, nə növ).
* Mövcud ``LessonMark``/``ComponentScore`` dəyərini üstündən yazmır.
* ``im``/``im2`` toqquşmalarına toxunmur: onların uduzanı ARTIQ
  ``LegacyGradeFact``-dədir (J-facts bütün ``im``/``im2`` sətirlərini yazır) —
  ikinci sətir ``registrar_legacy_grade_source_uniq``-a dəyərdi.  20 sətirlik
  əl-baxış siyahısı ``docs/migration/BERPA_SINTETIK_DERSLER.md``-dədir.

Niyə sıra 41 (J4=40 ilə J5=42 arasında)
---------------------------------------
J4-dən SONRA: J4 yaza biləcəyini artıq yazıb, ona görə bu faza YALNIZ
çatışmayanı əlavə edir və J4-ün toqquşmalarını dəyişmədən yenidən görür.
C keçidi (komponent) hədəfə heç bir sorğu vermir — qərar tamamilə mənbənin öz
sırasındadır (birinci gələn qalibdir, J5-in yazacağı dəyər budur), ona görə
J5-dən ƏVVƏL işləməsi nəticəni dəyişmir.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun

from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_cells import JournalCellLedger, drive_cells
from .rehearsal_journal_components_phase import (
    classify_component_cell,
    is_component_month,
)
from .rehearsal_journal_lesson_kinds import build_lesson_kind_index, slot_key
from .rehearsal_journal_lessons_phase import journal_index  # noqa: E402  (bax modul qeydi)
from .rehearsal_journal_lessons_phase import JOURNAL_LESSONS_PHASE_KEY
from .rehearsal_journal_marks_phase import (
    JOURNAL_MARKS_PHASE_KEY,
    build_resolution,
    classify_mark_cell,
    distill_mark_cell,
    is_calendar_month,
)
from .rehearsal_journal_marks_targets import (
    ABSENT_STATUS,
    EXCUSED_STATUS,
    LessonMarkWriter,
    MarkWrite,
    recompute_absence_hours,
)
from .rehearsal_journal_offerings_source import migrated_target_index
from .rehearsal_journal_points_source import POINT_SOURCE_TABLE, is_excused
from .rehearsal_journal_seal import JournalSealEntry, state_for, tally_parts
from .rehearsal_lesson_meta_source import syllabus_topic_index
from .rehearsal_lesson_recovery_evidence import (
    MARK_UNRESOLVED_ENTITY_TYPE,
    MARK_UNRESOLVED_SEALER,
    UnresolvedFactWriter,
    unresolved_fact_for,
)
from .rehearsal_lesson_recovery_scan import (
    SlotPlan,
    distill_recovery_cell,
    distill_recovery_component_cell,
    journal_year_index,
    offering_instructors,
    recovered_schedule,
    resolve_cell_target,
    slice_group_ref,
)
from .rehearsal_lesson_recovery_source import (
    DEFAULT_LESSON_HOURS,
    build_recovered_slot_metadata,
    metadata_payload,
)
from .rehearsal_lesson_recovery_targets import (
    DATE_INVALID_RULE_CODE,
    LESSON_SYNTH_ENTITY_TYPE,
    LESSON_SYNTH_SEALER,
    MARK_CONFLICT_ENTITY_TYPE,
    MARK_CONFLICT_SEALER,
    MARK_RECOVERY_ENTITY_TYPE,
    MARK_RECOVERY_SEALER,
    TIME_UNKNOWN_RULE_CODE,
    ConflictFact,
    ConflictFactWriter,
    SynthLessonRequest,
    SynthLessonWriter,
    conflict_seal_key,
    lesson_seal_key,
    mark_seal_key,
)
from .rehearsal_lesson_rooms_phase import LEGACY_ROOM_ENTITY_TYPE
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_LESSON_RECOVERY_PHASE_KEY = "journal_lesson_recovery"
JOURNAL_LESSON_RECOVERY_PHASE_ORDER = 41  # journal_marks (40) ilə journal_components (42) arasında
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-lesson-recovery-v2"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_LESSONS_PHASE_KEY, JOURNAL_MARKS_PHASE_KEY})

#: ``mr:`` prefiksinin uzunluğu — resume qapısı BARE ``uniqid`` gözləyir.
_MARK_PREFIX_LENGTH = len(mark_seal_key(""))

_STATE = LegacyEntityMap.State

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "lesson_recovery_materialised",
        _STATE.SKIPPED: "lesson_recovery_skipped",
        _STATE.QUARANTINED: "lesson_recovery_unresolved",
    }
)

#: Hesabat açarı → (issue kodu, karantin sayılırmı) — J4 taksonomiyasının bərpa
#: güzgüsü.  Açar adları möhür digest-inə qatlandığı üçün bu cədvəl həm
#: taksonomiya, həm də onun resepti sayılır.
OUTCOME_RULES = MappingProxyType(
    {
        "orphan": ("legacy_journal_mark_recovered_orphan", False),
        "duplicate": ("legacy_journal_mark_recovered_duplicate", False),
        "empty": ("legacy_journal_mark_recovered_empty", False),
        "unknown": ("legacy_journal_mark_recovered_point_unknown", True),
        "range": ("legacy_journal_mark_recovered_score_out_of_range", True),
        "enrollment": ("legacy_journal_mark_recovered_enrollment_unresolved", False),
        "lesson": ("legacy_journal_mark_recovered_lesson_unresolved", False),
        "conflict": ("legacy_journal_mark_recovered_target_conflict", False),
        "component_conflict": ("legacy_journal_component_target_conflict", False),
        "excused": ("legacy_journal_mark_recovered_excused", False),
        "lab": ("legacy_journal_mark_recovered_lab", False),
        "archive_overlap": ("legacy_journal_archive_overlap", False),
        "date_invalid": (DATE_INVALID_RULE_CODE, True),
        "synthesised": ("legacy_lesson_synthesised", False),
    }
)
QUARANTINE_KEYS = tuple(key for key, (_code, fatal) in OUTCOME_RULES.items() if fatal)
WRITTEN_KEYS = ("written", "archive_written")


class JournalLessonRecoveryPhase:
    """J12: çatışmayan dərsin bərpası + toqquşma uduzanının sübutu."""

    phase_key = JOURNAL_LESSON_RECOVERY_PHASE_KEY
    order = JOURNAL_LESSON_RECOVERY_PHASE_ORDER
    source_tables = ()
    entity_types = (
        LESSON_SYNTH_ENTITY_TYPE,
        MARK_CONFLICT_ENTITY_TYPE,
        MARK_UNRESOLVED_ENTITY_TYPE,
        MARK_RECOVERY_ENTITY_TYPE,
    )
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # Açarlar ``cf:``/``mr:``/``sl:`` prefiksli mətndir → LEKSİKOQRAFİK sıra.
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

        run = LegacyMigrationRun.objects.only("snapshot_sha256", "transform_version").get(pk=context.run_id)
        resolution = build_resolution(context)
        years = journal_year_index(context)
        recorded = {
            seal_key[_MARK_PREFIX_LENGTH:]: value
            for seal_key, value in MARK_RECOVERY_SEALER.recorded_decisions(context).items()
        }

        plans = self._plan_slots(context, resolution=resolution, years=years, recorded=recorded)
        lessons = self._materialise(context, plans=plans, recorded=LESSON_SYNTH_SEALER.recorded_decisions(context))
        resolution.lessons.update(lessons.index)

        ledger = JournalCellLedger(recorded=dict(recorded))
        conflicts = ConflictFactWriter(context, run=run, recorded=MARK_CONFLICT_SEALER.recorded_decisions(context))
        unresolved = UnresolvedFactWriter(context, run=run, recorded=MARK_UNRESOLVED_SEALER.recorded_decisions(context))
        writer = LessonMarkWriter(
            context,
            ledger,
            on_conflict=lambda **fields: self._calendar_conflict(conflicts, **fields),
        )
        drive_cells(
            context,
            ledger=ledger,
            domain=is_calendar_month,
            distill=distill_recovery_cell,
            decide=lambda cell: self._decide(
                cell=cell, resolution=resolution, ledger=ledger, writer=writer, unresolved=unresolved, years=years
            ),
            overlap_key="archive_overlap",
            # J-V7: arxiv keçidinə başlamazdan əvvəl əsas cədvəl hədəfə düşməlidir.
            flush=writer.flush,
        )
        unresolved.flush()
        conflicts.flush()
        absence_updated = recompute_absence_hours(context, ledger.touched_targets)
        self._component_conflicts(context, ledger=ledger, conflicts=conflicts, resolution=resolution)
        conflicts.flush()

        for uniqid, count in lessons.per_journal.items():
            ledger.tallies.setdefault(uniqid, Counter())["synthesised"] += count

        return self._report(
            context,
            ledger=ledger,
            lessons=lessons,
            recovered_marks=writer.created_count,
            conflicts=conflicts,
            unresolved=unresolved,
            resolution=resolution,
            absence_updated=absence_updated,
        )

    # ── A keçidi: hansı slotlar çatışmır ────────────────────────────────────

    def _plan_slots(self, context, *, resolution, years, recorded) -> dict[tuple, SlotPlan]:
        """J4-ün nərdivanını yerit; yalnız ``lesson`` pilləsində ilişəni topla."""

        plans: dict[tuple, SlotPlan] = {}
        scout = JournalCellLedger(recorded=dict(recorded))
        drive_cells(
            context,
            ledger=scout,
            domain=is_calendar_month,
            distill=distill_mark_cell,
            decide=lambda cell: self._scout(cell, resolution=resolution, years=years, plans=plans),
            overlap_key="archive_overlap",
        )
        context.stdout_note(f"{JOURNAL_LESSON_RECOVERY_PHASE_KEY}.slots.{len(plans)}")
        return plans

    def _scout(self, cell, *, resolution, years, plans) -> None:
        target = resolve_cell_target(cell, resolution=resolution)
        if target is None or target[1] is not None:
            return  # xana ya yazıla bilmir, ya da dərsi ARTIQ var
        offering_pk = target[0]
        first_year = years.get(cell.uniqid)
        if first_year is None:
            return  # semestri parse olunmayan jurnal — J0/J1 onsuz da karantindədir
        schedule = recovered_schedule(first_year=first_year, month=cell.month, day=cell.day, time_text=cell.time_text)
        if schedule is None:
            return  # tarix qurulmur — B keçidi onu ``date_invalid`` sayacaq
        lesson_date, lesson_time = schedule
        key = (offering_pk, cell.month, cell.day, cell.time_text)
        plan = plans.get(key)
        if plan is None:
            plans[key] = SlotPlan(
                uniqid=cell.uniqid,
                group_ref=slice_group_ref(resolution, cell.uniqid, offering_pk),
                offering_pk=offering_pk,
                date=lesson_date,
                start_time=lesson_time,
                first_cell=(cell.from_archive, cell.legacy_pk),
            )
            return
        plan.cell_count += 1
        plan.first_cell = min(plan.first_cell, (cell.from_archive, cell.legacy_pk))

    # ── Dərslərin materiallaşması ───────────────────────────────────────────

    def _materialise(self, context, *, plans, recorded) -> SynthLessonWriter:
        """Planlanan slotları ``Lesson`` sətirlərinə çevir (nişanlı, idempotent)."""

        writer = SynthLessonWriter(context, recorded=recorded)
        if not plans:
            return writer
        kinds = build_lesson_kind_index(context)
        topics = syllabus_topic_index(context)
        rooms = migrated_target_index(context, LEGACY_ROOM_ENTITY_TYPE)
        metadata = build_recovered_slot_metadata(
            context, journal_index(context), {plan.metadata_key for plan in plans.values()}
        )
        instructors = offering_instructors(context, {plan.offering_pk for plan in plans.values()})
        # Sıra möhür açarı üzrə deterministikdir → dəstələr cross-run eynidir.
        for plan in sorted(plans.values(), key=lambda item: (item.first_cell, item.group_ref)):
            probe_cancellation(context)
            kind, _kind_code = kinds.resolve(
                slot_key(uniqid=plan.uniqid, month=plan.date.month, day=plan.date.day, time_text=plan.time_text)
            )
            topic, room_pk, hours, codes = metadata_payload(
                metadata.get(plan.metadata_key), lesson_date=plan.date, topics=topics, rooms=rooms
            )
            if plan.start_time is None:
                codes = (*codes, TIME_UNKNOWN_RULE_CODE)
            writer.add(
                SynthLessonRequest(
                    seal_key=lesson_seal_key(
                        from_archive=plan.from_archive,
                        first_cell_pk=plan.first_cell_pk,
                        group_ref=plan.group_ref,
                    ),
                    uniqid=plan.uniqid,
                    group_ref=plan.group_ref,
                    offering_pk=plan.offering_pk,
                    date=plan.date,
                    start_time=plan.start_time,
                    kind=kind,
                    # Metadata tapılmayanda J3-ün spec defoltu qalır (2 saat =
                    # bir cüt); heç bir dəyər təxmin edilmir.
                    hours=hours or DEFAULT_LESSON_HOURS,
                    topic=topic,
                    room_pk=room_pk,
                    instructor_pk=instructors.get(plan.offering_pk, ""),
                    first_cell_pk=plan.first_cell_pk,
                    cell_count=plan.cell_count,
                    rule_codes=codes,
                )
            )
            writer.per_journal[plan.uniqid] += 1
        writer.flush()
        context.stdout_note(f"{JOURNAL_LESSON_RECOVERY_PHASE_KEY}.lessons.{writer.created_count}")
        return writer

    # ── B keçidi: xanaların yazılması ───────────────────────────────────────

    def _decide(self, *, cell, resolution, ledger, writer, unresolved, years) -> None:
        """J4-ün nərdivanı, EYNİ sırada — indi genişlənmiş dərs indeksi ilə."""

        if not resolution.slices.has_offering(cell.uniqid):
            ledger.count(cell.uniqid, "orphan")
            return
        outcome, status, score = classify_mark_cell(cell.point)
        if outcome in ("empty", "unknown", "range"):
            ledger.count(cell.uniqid, outcome)
            return
        enrollment_pk = resolution.enrollments.get(f"{cell.uniqid}:{cell.student_id}", "")
        if not enrollment_pk:
            ledger.count(cell.uniqid, "enrollment")
            return
        offering_pk = resolution.offerings.get(enrollment_pk, "")
        slot = resolution.lessons.get((offering_pk, cell.month, cell.day, cell.time_text)) if offering_pk else None
        if slot is None:
            # Bərpadan SONRA hələ də dərsi yoxdursa, tək izahlı səbəb tarixin
            # ümumiyyətlə qurula bilməməsidir (məs. 31 noyabr) — o, KARANTİNdir.
            first_year = years.get(cell.uniqid)
            unbuildable = first_year is None or (
                recovered_schedule(first_year=first_year, month=cell.month, day=cell.day, time_text=cell.time_text)
                is None
            )
            reason = "date_invalid" if unbuildable else "lesson"
            ledger.count(cell.uniqid, reason)
            unresolved.add(unresolved_fact_for(cell, issue_code=OUTCOME_RULES[reason][0]))
            return
        lesson_pk, lesson_date = slot
        if status == ABSENT_STATUS and is_excused(
            excusable=cell.excusable,
            student_id=cell.student_id,
            lesson_date=lesson_date,
            windows=resolution.windows,
        ):
            status = EXCUSED_STATUS
            ledger.count(cell.uniqid, "excused")
            ledger.note(cell.uniqid, f"{cell.legacy_pk}|{cell.why}|{cell.description}")
        if cell.lab == 1:
            ledger.count(cell.uniqid, "lab")
        writer.enqueue(
            uniqid=cell.uniqid,
            from_archive=cell.from_archive,
            request=MarkWrite(
                lesson_pk=lesson_pk,
                enrollment_pk=enrollment_pk,
                status=status,
                score=score,
                allow_existing=not cell.from_archive,
                legacy_pk=cell.legacy_pk,
                point_text=cell.point,
                row_hash=cell.row_hash,
                student_ref=str(cell.student_id),
                month_id=f"{cell.month:02d}",
                source_lesson_ref=f"calendar:{cell.month:02d}:{cell.day}:{cell.time_text}",
            ),
        )

    # ── Toqquşma sübutu ─────────────────────────────────────────────────────

    def _calendar_conflict(self, conflicts, *, uniqid, request, existing) -> None:
        """Təqvim toqquşmasında UDUZAN dəyər; qalibə TOXUNULMUR.

        Toqquşma yalnız ƏSAS cədvəldə mümkündür: arxiv xanası
        ``allow_existing=False`` ilə gəlir və mövcud sətri görəndə ``superseded``
        olur (J-V7 «əsas cədvəl udur»), ``conflict`` yox.
        """

        stored_status, stored_score = existing if existing else ("", None)
        conflicts.add(
            ConflictFact(
                seal_key=conflict_seal_key(from_archive=False, legacy_pk=request.legacy_pk),
                source_table=POINT_SOURCE_TABLE,
                legacy_pk=request.legacy_pk,
                source_row_hash=request.row_hash,
                uniqid=uniqid,
                student_ref=request.student_ref,
                enrollment_pk=request.enrollment_pk,
                month_id=request.month_id,
                source_lesson_ref=request.source_lesson_ref,
                losing_text=request.point_text,
                winning_text=stored_status if stored_score is None else f"{Decimal(stored_score):f}",
                issue_code=OUTCOME_RULES["conflict"][0],
            )
        )

    def _component_conflicts(self, context, *, ledger, conflicts, resolution) -> None:
        """C keçidi: komponent (``k1``/``k2``/``k3``/``si``) toqquşmasının uduzanı.

        Hədəfə heç bir sorğu getmir: J5-in ``get_or_create`` semantikasında
        BİRİNCİ gələn xana qalibdir, ona görə qərar tamamilə mənbənin öz
        sırasındadır.  Arxiv sətri heç vaxt toqquşmur — J5 onu ``superseded``
        sayır (J-V7), ona görə burada da yalnız əsas cədvəl hesaba alınır.
        """

        seen: dict[tuple[str, str], tuple[int, str]] = {}
        scout = JournalCellLedger(recorded=dict(ledger.recorded))
        drive_cells(
            context,
            ledger=scout,
            domain=is_component_month,
            distill=distill_recovery_component_cell,
            decide=lambda cell: self._component_cell(
                cell, seen=seen, conflicts=conflicts, ledger=ledger, resolution=resolution
            ),
            overlap_key="archive_overlap",
        )

    def _component_cell(self, cell, *, seen, conflicts, ledger, resolution) -> None:
        outcome, score = classify_component_cell(cell.point)
        if outcome != "scored":
            return
        enrollment_pk = resolution.enrollments.get(f"{cell.uniqid}:{cell.student_id}", "")
        if not enrollment_pk or not resolution.offerings.get(enrollment_pk, ""):
            return
        pair = (enrollment_pk, cell.month_id)
        kept = seen.get(pair)
        if kept is None:
            seen[pair] = (score, cell.point)
            return
        # Müqayisə J5-in ``Decimal(row.score) == Decimal(score)`` yoxlaması kimi
        # RƏQƏMSALDIR: "07" və "7" eyni baldır, mətn kimi isə fərqli görünərdi.
        if kept[0] == score or cell.from_archive:
            return  # eyni dəyər (itki yox) və ya arxiv (J-V7: əsas cədvəl udur)
        ledger.count(cell.uniqid, "component_conflict")
        conflicts.add(
            ConflictFact(
                seal_key=conflict_seal_key(from_archive=False, legacy_pk=cell.legacy_pk),
                source_table=POINT_SOURCE_TABLE,
                legacy_pk=cell.legacy_pk,
                source_row_hash=cell.row_hash,
                uniqid=cell.uniqid,
                student_ref=str(cell.student_id),
                enrollment_pk=enrollment_pk,
                month_id=cell.month_id,
                source_lesson_ref="",
                losing_text=cell.point,
                winning_text=kept[1],
                issue_code=OUTCOME_RULES["component_conflict"][0],
            )
        )

    # ── Hesabat ─────────────────────────────────────────────────────────────

    def _report(
        self, context, *, ledger, lessons, conflicts, unresolved, resolution, absence_updated, recovered_marks
    ) -> PhaseReport:
        issue_counts: Counter = Counter()
        issue_counts.update(lessons.issue_counts)
        issue_counts.update(conflicts.issue_counts)
        issue_counts.update(unresolved.issue_counts)

        entries: list[JournalSealEntry] = []
        # Möhür açarı → qərar.  Resume-da bu run-ın ARTIQ yazdığı möhürlər
        # ledger-dən gəlir (faza onları yenidən törətmir), bu keçidin qərarları
        # isə üstünə yazılır — zəncir hər iki halda EYNİ dəsti yeriyir.
        decisions: dict[str, tuple[str, str, str]] = {}
        decisions.update(lessons.recorded)
        decisions.update(conflicts.recorded)
        decisions.update(unresolved.recorded)
        decisions.update({mark_seal_key(uniqid): value for uniqid, value in ledger.recorded.items()})
        for uniqid, tally in sorted(ledger.tallies.items()):
            state = state_for(
                written=sum(tally[key] for key in WRITTEN_KEYS),
                quarantined=sum(tally[key] for key in QUARANTINE_KEYS),
            )
            seal_key = mark_seal_key(uniqid)
            digest = MARK_RECOVERY_SEALER.derivation_hash(
                seal_key=seal_key,
                outcome_token=str(state),
                parts=(*tally_parts(tally), *ledger.evidence_part(uniqid)),
            )
            label = COURSE_OFFERING_MODEL_LABEL if state == _STATE.MIGRATED else ""
            entries.append(
                JournalSealEntry(
                    seal_key=seal_key,
                    digest=digest,
                    state=state,
                    label=label,
                    target_pk=resolution.slices.primary_offering(uniqid) if label else "",
                    rule_codes=tuple(OUTCOME_RULES[key][0] for key in sorted(OUTCOME_RULES) if tally[key]),
                )
            )
            decisions[seal_key] = (state, digest, label)
        MARK_RECOVERY_SEALER.seal_many(context, entries, issue_counts=issue_counts)

        decisions.update(lessons.sealed)
        decisions.update(conflicts.sealed)
        decisions.update(unresolved.sealed)
        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter = Counter()
        for seal_key, (state, digest, label) in sorted(decisions.items()):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_LESSON_RECOVERY_PHASE_KEY}.marks.{recovered_marks}")
        context.stdout_note(f"{JOURNAL_LESSON_RECOVERY_PHASE_KEY}.absence_updated.{absence_updated}")
        context.stdout_note(f"{JOURNAL_LESSON_RECOVERY_PHASE_KEY}.conflicts.{conflicts.written}")
        context.stdout_note(f"{JOURNAL_LESSON_RECOVERY_PHASE_KEY}.unresolved_facts.{unresolved.written}")
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


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "JOURNAL_LESSON_RECOVERY_PHASE_KEY",
    "JOURNAL_LESSON_RECOVERY_PHASE_ORDER",
    "OUTCOME_RULES",
    "JournalLessonRecoveryPhase",
]
