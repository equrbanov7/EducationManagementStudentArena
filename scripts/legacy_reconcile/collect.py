"""Sorğuları icra edib hesabat üçün xam faktları toplayan qat (yazı YOXDUR)."""

from __future__ import annotations

from decimal import Decimal

from . import source_sql as S
from . import target_sql as T
from .analysis import (
    DOMAIN_COMPONENTS,
    DOMAIN_FINALS,
    DOMAIN_MARKS,
    DOMAINS,
    OUTCOME_EMPTY,
    OUTCOME_OUT_OF_SCOPE,
    OUTCOME_UNREADABLE,
    OUTCOME_WRITABLE,
    Ladder,
    bucket_deltas,
    entry_score,
    total_score,
)
from .write_replay import (
    LABEL_ARCHIVE_SUPERSEDED,
    LABEL_COLLISION_OTHER,
    LABEL_COLLISION_SAME,
    LABEL_LESSON_SOURCE_ABSENT,
    LABEL_LESSON_SOURCE_PRESENT,
    STEP_ARCHIVE_SUPERSEDED,
    STEP_COLLISION_OTHER,
    STEP_COLLISION_SAME,
    STEP_DEDUPED,
    STEP_LESSON_SOURCE_ABSENT,
    STEP_LESSON_SOURCE_PRESENT,
    STEP_ORPHAN,
    STEP_UNRESOLVED,
    multi_key_enrollment_targets,
    replay_writes,
)

# Hər domenin hədəf tərəfdəki qarşılığı (registrar sayları ilə üzləşdirilir).
TARGET_OF_DOMAIN = {
    DOMAIN_MARKS: ("lessonmark",),
    DOMAIN_COMPONENTS: ("componentscore_kollokvium", "componentscore_selfwork"),
    DOMAIN_FINALS: ("finalgrade_scored", "resit_scored"),
}


def _int(value) -> int:
    return int(value) if value not in (None, "", "NULL") else 0


def _dec(value):
    """``-1`` sentineli (legacy NULL) → ``None``; qalanı ``Decimal``."""

    if value in (None, "", "NULL"):
        return None
    number = Decimal(str(value))
    return None if number < 0 else number


def collect_source_facts(source) -> dict:
    """MariaDB tərəfin bütün aqreqatları (sətir-sətir axın BURADA DEYİL)."""

    facts: dict = {}
    facts["table_counts"] = {row[0]: _int(row[1]) for row in source.query("cədvəl sayları", S.table_counts_sql())}

    classification: dict = {}
    for src, eligible, domain, outcome, count in source.query("xana təsnifatı", S.cell_classification_sql()):
        classification[(src, _int(eligible), domain, outcome)] = _int(count)
    facts["classification"] = classification

    facts["raw_writable"] = {row[0]: _int(row[1]) for row in source.query("xam yazıla bilən", S.raw_writable_sql())}

    values: dict = {}
    for src, domain, shape, count in source.query("dəyər paylanması", S.value_distribution_sql()):
        values[(src, domain, shape)] = _int(count)
    facts["values"] = values

    facts["quality"] = {row[0]: _int(row[1]) for row in source.query("keyfiyyət", S.QUALITY_SQL)}

    facts["yekun"] = [
        (_int(student_id), uniqid, _dec(girish), _dec(exam), _dec(total))
        for student_id, uniqid, girish, exam, total in source.query("yekun sətirləri", S.YEKUN_JOINED_SQL)
    ]

    return facts


def collect_target_facts(target, *, run_id) -> dict:
    """PostgreSQL tərəfin tenant-məhdud sayları + ledger körpüləri.

    Geniş registrar/auth sorğularından ƏVVƏL run, reader-də açıq verilmiş
    təşkilat və ``succeeded`` statusu birlikdə attestasiya edilir. Beləliklə
    səhv run UUID-si və ya başqa tenant-a aid run heç bir geniş sorğu aça
    bilməz.
    """

    organization_id = str(getattr(target, "organization_id", "") or "")
    if not organization_id:
        raise RuntimeError("legacy_reconcile_target_organization_required")
    run_key = str(run_id)
    run_rows = target.query("run attestasiyası", T.RUN_SQL, (run_key, organization_id))
    if len(run_rows) != 1:
        raise RuntimeError("legacy_reconcile_run_attestation_failed")

    facts: dict = {
        "run": run_rows[0],
        "organization_id": organization_id,
        "attested": True,
    }
    facts["entity_counts"] = {
        row[0]: _int(row[1]) for row in target.query("varlıq sayları", T.ENTITY_COUNTS_SQL, (organization_id,))
    }
    facts["quality"] = {row[0]: _int(row[1]) for row in target.query("keyfiyyət", T.QUALITY_SQL, (organization_id,))}
    facts["ledger_states"] = [
        (entity_type, state, _int(count))
        for entity_type, state, count in target.query(
            "ledger", T.LEDGER_STATE_SQL, (run_key, organization_id, organization_id)
        )
    ]
    facts["ledger_batches"] = target.query("ledger batch", T.LEDGER_BATCH_SQL, (run_key, organization_id))
    facts["issues"] = target.query("ledger problemləri", T.LEDGER_ISSUE_SQL, (run_key, organization_id))
    facts["roles"] = target.query("üzvlük rolları", T.MEMBERSHIP_BY_ROLE_SQL, (organization_id,))
    facts["offerings"] = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in target.query(
            "offering körpüsü",
            T.MIGRATED_MAP_SQL,
            (run_key, "course_offering", organization_id, organization_id),
        )
    }
    facts["enrollments"] = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in target.query(
            "enrollment körpüsü",
            T.MIGRATED_MAP_SQL,
            (run_key, "journal_enrollment", organization_id, organization_id),
        )
    }
    facts["students"] = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in target.query(
            "tələbə körpüsü",
            T.MIGRATED_MAP_SQL,
            (run_key, "student", organization_id, organization_id),
        )
    }
    facts["recovery"] = collect_recovery_facts(target, organization_id)
    return facts


def collect_recovery_facts(target, organization_id: str) -> dict:
    """J12 dərs bərpasının hədəfdəki İZİ — 1-ci pillənin proqnozunu yoxlamaq üçün.

    1-ci pillə («dərs slotu MƏNBƏDƏ yoxdur») bərpanın hədəfidir: dərs hədəfdə
    yarananda slot xəritəsinə düşür və pillə boşalır.  Nərdivan bunu heç bir
    xüsusi bilik olmadan görür (pillə sadəcə sıfırlanır), amma hesabat oxucunun
    «bərpa buradadırmı?» sualını təxminə buraxmamalıdır — ona görə iz ÖLÇÜLÜR.

    Üç fərqli hal ayrılır və heç biri o birinin yerinə keçmir:

    * ``present=False`` — nüsxənin sxemi bərpanı ümumiyyətlə TANIMIR
      (``registrar.0059`` miqrasiyası tətbiq olunmayıb);
    * ``present=True, lessons=0`` — sxem tanıyır, bərpa İŞLƏDİLMƏYİB;
    * ``lessons>0`` — bərpa tətbiq olunub, pillə 1 SIFIR olmalıdır.

    ⚠️ Sütun yoxdursa sayğac sorğusu göndərilmir: ``SELECT`` özü
    ``UndefinedColumn`` ilə çökər və bütöv hesabatı aparardı.
    """

    column_rows = target.query("bərpa sütunu", T.LESSON_SYNTH_COLUMN_SQL, (organization_id,))
    present = bool(column_rows) and _int(column_rows[0][0]) > 0
    facts = {"present": present, "lessons": 0, "all_lessons": 0, "marks": 0}
    if not present:
        return facts
    count_rows = target.query("bərpa olunmuş dərslər", T.LESSON_SYNTH_COUNT_SQL, (organization_id,))
    if count_rows:
        facts["lessons"] = _int(count_rows[0][0])
        facts["all_lessons"] = _int(count_rows[0][1])
    if facts["lessons"]:
        mark_rows = target.query(
            "bərpa dərslərindəki xanalar",
            T.LESSON_SYNTH_MARK_SQL,
            (organization_id, organization_id),
        )
        if mark_rows:
            facts["marks"] = _int(mark_rows[0][0])
    return facts


# ── §1 nərdivan ──────────────────────────────────────────────────────────────


def offering_journal_keys(offerings) -> set[str]:
    """Açılışı OLAN jurnalların açar dəsti (orphan qapısı üçün).

    Açılış möhürünün açarı 2026-08-dən (qrup-başına bölgü) `uniqid:<qrup_pk>`
    formasındadır; ondan əvvəl sadəcə `uniqid` idi.  Nərdivan «bu jurnalın
    ÜMUMİYYƏTLƏ açılışı varmı» sualına cavab verdiyi üçün HƏR İKİ formanı
    tanımalıdır — əks halda bölünmüş run-da BÜTÜN xanalar «orphan jurnal»
    sayılır və nərdivan mənfi «izahsız fərq» verir (2026-08-27-də məhz belə
    oldu: 4.4 M xana səhvən orphan göstərildi).

    Tam açar da dəstə salınır ki, `uniqid`-in özündə «:» olsa belə (ledger
    OPAQUE_KEY_PATTERN buna icazə verir) dəqiq uyğunluq itməsin.
    """

    keys: set[str] = set()
    for key in offerings:
        keys.add(key)
        # Dilim açarının son hissəsi legacy qrup pk-sıdır; ``uniqid`` özü
        # ``:`` daşıya bilər, ona görə soldan bölmək jurnalı kəsirdi.
        head, separator, _ = key.rpartition(":")
        if separator:
            keys.add(head)
    return keys


def _cell_election_key(row) -> tuple[str, str, str, int, str]:
    """SQL sətirini importer-in ``cell_key`` forması ilə eyniləşdir."""

    return (str(row[2]), str(row[4]), str(row[5]), int(row[3]), str(row[6]))


def source_cell_elections(source, table_counts: dict[str, int]):
    """Importer-in bit-bucket namizəd seçkisini mənbədən dəqiq yenidən qur."""

    # CLI (`legacy_reconcile_report.py --help`) Django qaldırmır. Bu importer
    # sinfi model moduluna qədər gedir, ona görə yalnız deep replay başlayanda
    # lazy import edilməlidir.
    from apps.legacy_import.services.rehearsal_journal_points_source import CellElection

    tables = (S.POINT_TABLE, S.ARCHIVE_TABLE)
    elections = {
        (table, domain): CellElection(expected_rows=table_counts[table]) for table in tables for domain in DOMAINS
    }
    for row in source.iter_query("xana seçki açarları", S.cell_election_keys_sql()):
        table, domain = str(row[0]), str(row[7])
        elections[(table, domain)].observe(_cell_election_key(row))
    return elections


def importer_ordered_winners(rows, elections):
    """SQL qaliblərini importer-in həqiqi qərar sırasına qaytar.

    ``CellElection`` hash-bucket toqquşması exact-dublikat olmayan açarı da
    pending-ə sala bilər. SQL qalibi düzgün seçir, bu funksiya isə həmin
    qaliblərin sırasını bərpa edir: qeyri-namizədlər PK sırasında dərhal,
    namizədlər isə cədvəlin sonunda öz PK sırasında.
    """

    current_table = None
    pending = []

    def flush():
        for pending_row in sorted(pending, key=lambda item: int(item[8])):
            yield pending_row
        pending.clear()

    for row in rows:
        table = str(row[7])
        if current_table is not None and table != current_table:
            yield from flush()
        current_table = table
        domain = str(row[2])
        election_row = (table, row[8], row[0], row[1], row[3], row[4], row[5], domain)
        if elections[(table, domain)].is_candidate(_cell_election_key(election_row)):
            pending.append(row)
        else:
            yield row
    yield from flush()


def collect_write_replay(source, target, target_facts: dict, source_facts: dict):
    """J4/J5/J6 yazı qərarını mənbə xanalarının öz axını üzərində təkrar icra et.

    Hədəf tərəfdən yalnız İKİ xəritə oxunur — materiallaşmış dərs slotları və
    yazılış→açılış indeksi — hər ikisi registrar cədvəllərinin özündən, ledger
    sayğacından DEYİL.  Beləliklə nərdivanın son iki pilləsi hadisə deyil, XANA
    sayır (bax ``write_replay`` modul qeydi).

    ⚠️ Axın 5 milyon sətirdir: ``iter_query`` ilə oxunur, yaddaşa yığılmır.
    """

    organization_id = target_facts["organization_id"]
    lesson_slots = {}
    for offering_pk, month, day, time_text, lesson_pk in target.query(
        "dərs slotları", T.LESSON_SLOT_SQL, (organization_id,)
    ):
        key = (str(offering_pk), int(month), int(day), str(time_text))
        target_pk = str(lesson_pk)
        previous = lesson_slots.get(key)
        if previous is not None and previous != target_pk:
            raise RuntimeError("legacy_reconcile_duplicate_target_lesson_slot")
        lesson_slots[key] = target_pk
    enrollment_offerings = {
        str(enrollment_pk): str(offering_pk)
        for enrollment_pk, offering_pk in target.query(
            "yazılış → açılış", T.ENROLLMENT_OFFERING_SQL, (organization_id,)
        )
    }
    enrollments = target_facts["enrollments"]
    elections = source_cell_elections(source, source_facts["table_counts"])
    winners = importer_ordered_winners(
        source.iter_query("dedup edilmiş xana açarları", S.deduped_cell_keys_sql()),
        elections,
    )
    return replay_writes(
        winners,
        offering_journals=offering_journal_keys(target_facts["offerings"]),
        enrollments=enrollments,
        enrollment_offerings=enrollment_offerings,
        lesson_slots=lesson_slots,
        multi_key_enrollments=multi_key_enrollment_targets(enrollments),
        source_lesson_slots=source_lesson_slot_index(source),
    )


def source_lesson_slot_index(source) -> set[tuple[str, int, int, str]]:
    """MƏNBƏNİN dərs indeksi — «slot mənbədə yoxdur» pilləsinin MÜSTƏQİL ölçüsü.

    Bu, hesabatın ledger-dən DƏ, hədəfdən DƏ asılı olmayan yeganə slot mənbəyidir:
    sorğu birbaşa ``journals_dates_added_by_teacher``-ə gedir.  Beləliklə «dərs
    slotu tapılmadı» pilləsi iki müstəqil sübutla bölünür — hədəf (slot
    materiallaşmayıb) və mənbə (slot ümumiyyətlə yoxdur).

    ⚠️ Oxunmayan saat (``80:30`` kimi 24 legacy yazı səhvi) indeksə DÜŞMÜR:
    onlar heç bir xananın saatına bərabər ola bilməz.  Həmin sətirlərin izi
    ``source_slot_substeps`` alt-ölçüsündə (gün var, saat fərqlidir) görünür.
    """

    index: set[tuple[str, int, int, str]] = set()
    for uniqid, month, day, time_text in source.iter_query("mənbə dərs slotları", S.lesson_slot_source_sql()):
        index.add((uniqid, int(month), int(day), str(time_text)))
    if not index:
        raise RuntimeError("legacy_reconcile_source_lesson_slot_index_empty")
    return index


def build_ladders(source_facts: dict, target_facts: dict, replay=None) -> dict[str, Ladder]:
    """Hər domen üçün «mənbə → hədəf» nərdivanını qur.

    ``replay`` ``None``-dursa (``--skip-deep``) nərdivan yalnız mənbə-tərəf
    pillələrini bilir və qalıq süni şəkildə böyük görünür — hesabat bunu açıq
    yazır, gizlətmir.
    """

    classification = source_facts["classification"]
    entity_counts = target_facts["entity_counts"]

    ladders: dict[str, Ladder] = {}
    for domain in DOMAINS:
        source_total = sum(count for key, count in classification.items() if key[2] == domain)
        target_total = sum(entity_counts.get(key, 0) for key in TARGET_OF_DOMAIN[domain])
        ladder = Ladder(name=domain, source_total=source_total, target=target_total)
        ladder.deduct("boş xana (mənbədə dəyər yoxdur)", _sum_outcome(classification, domain, OUTCOME_EMPTY))
        ladder.deduct("oxunmayan xana (karantin)", _sum_outcome(classification, domain, OUTCOME_UNREADABLE))
        ladder.deduct("arxiv örtüşməsi (J-V7 kəsimindən sonra)", _archive_overlap(classification, domain))
        if replay is not None:
            _deduct_write_steps(ladder, domain, source_facts, replay)
        ladders[domain] = ladder
    return ladders


def _deduct_write_steps(ladder: Ladder, domain: str, source_facts: dict, replay) -> None:
    """Yazı nərdivanının pillələri — import-un qapı sırasında."""

    raw = source_facts["raw_writable"].get(domain, 0)
    deduped = replay.step(domain, STEP_DEDUPED)
    ladder.deduct("dublikat xana (J-V4 uduzanları)", max(0, raw - deduped))
    ladder.deduct("orphan jurnal (açılış yaradılmayıb)", replay.step(domain, STEP_ORPHAN))
    ladder.deduct("həll olunmayan yazılış (tələbə jurnalda aktiv deyil)", replay.step(domain, STEP_UNRESOLVED))
    ladder.deduct(LABEL_ARCHIVE_SUPERSEDED, replay.step(domain, STEP_ARCHIVE_SUPERSEDED))
    if domain == DOMAIN_MARKS:
        # Köhnə tək «dərs slotu tapılmadı» pilləsi İKİ ayrı SƏBƏBƏ bölünüb:
        # biri mənbənin öz boşluğudur (J12 bərpasından sonra SIFIRA enir),
        # digəri köçürmə qərarıdır (açıq sual olaraq qalır).
        ladder.deduct(LABEL_LESSON_SOURCE_ABSENT, replay.step(domain, STEP_LESSON_SOURCE_ABSENT))
        ladder.deduct(LABEL_LESSON_SOURCE_PRESENT, replay.step(domain, STEP_LESSON_SOURCE_PRESENT))
    # Toqquşma da bölünüb: «eyni dəyər» izahlı buraxılışdır, «fərqli dəyər»
    # itkidir — bir pillədə qarışdırılması itkinin ölçüsünü gizlədirdi.
    ladder.deduct(LABEL_COLLISION_SAME, replay.step(domain, STEP_COLLISION_SAME))
    ladder.deduct(LABEL_COLLISION_OTHER, replay.step(domain, STEP_COLLISION_OTHER))


def _sum_outcome(classification: dict, domain: str, outcome: str) -> int:
    return sum(count for key, count in classification.items() if key[2] == domain and key[3] == outcome)


def _archive_overlap(classification: dict, domain: str) -> int:
    """Arxivdən gələn, amma J-V7 kəsimindən SONRA yazılmış (təkrarlanan) xanalar.

    Boş/oxunmayan olanlar artıq yuxarıdakı pillələrdə çıxıldığı üçün burada
    yalnız yazıla bilən örtüşmələr sayılır — ikiqat çıxılma olmasın deyə.
    """

    return sum(
        count
        for key, count in classification.items()
        if key[0] == "archive" and key[1] == 0 and key[2] == domain and key[3] == OUTCOME_WRITABLE
    )


def out_of_scope_cells(source_facts: dict) -> int:
    """Naməlum ``month_id`` kodlu xanalar — heç bir domenə düşmür."""

    return sum(count for key, count in source_facts["classification"].items() if key[3] == OUTCOME_OUT_OF_SCOPE)


# ── §4 yekun müqayisəsi ──────────────────────────────────────────────────────


def compare_finals(source_facts: dict, target_facts: dict, target) -> dict:
    """Legacy ``yekun`` sətirlərini hədəfin hesabladığı yekunla üzləşdir."""

    enrollments = target_facts["enrollments"]
    rows = source_facts["yekun"]
    linked: dict[str, tuple] = {}
    unresolved = 0
    linked_rows = 0
    for student_id, uniqid, girish, exam, total in rows:
        enrollment_pk = enrollments.get(f"{uniqid}:{student_id}")
        if enrollment_pk is None:
            unresolved += 1
            continue
        # Birləşən jurnallar səbəbindən bir neçə ``yekun`` sətri EYNİ yazılışa
        # düşə bilər — sonuncu qalır, fərq ayrıca sətir kimi göstərilir.
        linked_rows += 1
        linked[enrollment_pk] = (girish, exam, total)

    mirror = {}
    if linked:
        params = (target_facts["organization_id"], list(linked))
        for row in target.query("yekun güzgüsü", T.FINAL_MIRROR_SQL, params):
            mirror[row[0]] = row

    total_deltas, exam_deltas, entry_deltas, net_deltas = [], [], [], []
    missing_target = 0
    for enrollment_pk, (girish, exam, legacy_total_value) in linked.items():
        row = mirror.get(enrollment_pk)
        if row is None:
            missing_target += 1
            continue
        _pk, lesson_sum, kollokvium_sum, exam_score, bonus, resit_score, cap = row
        computed_entry = entry_score(lesson_sum, kollokvium_sum, cap)
        computed_total = total_score(computed_entry, exam_score, resit_score, bonus)
        if legacy_total_value is not None:
            total_deltas.append(computed_total - legacy_total_value)
            if girish is not None:
                # Giriş balı düsturundan ASILI OLMAYAN hissə: yekun − giriş.
                net_deltas.append((computed_total - computed_entry) - (legacy_total_value - girish))
        if exam is not None:
            effective = resit_score if resit_score is not None else exam_score
            exam_deltas.append(Decimal(str(effective or 0)) - exam)
        if girish is not None:
            entry_deltas.append(computed_entry - girish)

    return {
        "source_rows": len(rows),
        "unresolved": unresolved,
        "missing_target": missing_target,
        "linked_rows": linked_rows,
        "collapsed": linked_rows - len(linked),
        "linked": len(linked),
        "total_hist": bucket_deltas(total_deltas),
        "total_compared": len(total_deltas),
        "exam_hist": bucket_deltas(exam_deltas),
        "exam_compared": len(exam_deltas),
        "entry_hist": bucket_deltas(entry_deltas),
        "entry_compared": len(entry_deltas),
        "net_hist": bucket_deltas(net_deltas),
        "net_compared": len(net_deltas),
    }
