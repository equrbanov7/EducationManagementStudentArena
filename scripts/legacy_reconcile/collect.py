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


def collect_source_facts(source, *, deep: bool) -> dict:
    """MariaDB tərəfin bütün aqreqatları."""

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

    facts["cells_by_enrollment"] = (
        [
            (uniqid, _int(student_id), domain, _int(count))
            for uniqid, student_id, domain, count in source.query("xana → (jurnal, tələbə)", S.cell_by_enrollment_sql())
        ]
        if deep
        else []
    )
    return facts


def collect_target_facts(target) -> dict:
    """PostgreSQL tərəfin sayları + ledger körpüləri."""

    facts: dict = {}
    facts["entity_counts"] = {row[0]: _int(row[1]) for row in target.query("varlıq sayları", T.ENTITY_COUNTS_SQL)}
    facts["quality"] = {row[0]: _int(row[1]) for row in target.query("keyfiyyət", T.QUALITY_SQL)}
    facts["ledger_states"] = [
        (entity_type, state, _int(count)) for entity_type, state, count in target.query("ledger", T.LEDGER_STATE_SQL)
    ]
    facts["ledger_batches"] = target.query("ledger batch", T.LEDGER_BATCH_SQL)
    facts["issues"] = target.query("ledger problemləri", T.LEDGER_ISSUE_SQL)
    facts["roles"] = target.query("üzvlük rolları", T.MEMBERSHIP_BY_ROLE_SQL)
    run_rows = target.query("run", T.RUN_SQL)
    facts["run"] = run_rows[0] if run_rows else None
    facts["offerings"] = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in target.query("offering körpüsü", T.MIGRATED_MAP_SQL, ("course_offering",))
    }
    facts["enrollments"] = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in target.query("enrollment körpüsü", T.MIGRATED_MAP_SQL, ("journal_enrollment",))
    }
    facts["students"] = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in target.query("tələbə körpüsü", T.MIGRATED_MAP_SQL, ("student",))
    }
    return facts


# ── §1 nərdivan ──────────────────────────────────────────────────────────────


def build_ladders(source_facts: dict, target_facts: dict) -> dict[str, Ladder]:
    """Hər domen üçün «mənbə → hədəf» nərdivanını qur."""

    classification = source_facts["classification"]
    entity_counts = target_facts["entity_counts"]
    offerings = target_facts["offerings"]
    enrollments = target_facts["enrollments"]

    # Açılış möhürünün açarı 2026-08-dən (qrup-başına bölgü) `uniqid:<qrup_pk>`
    # formasındadır; ondan əvvəl sadəcə `uniqid` idi.  Nərdivan «bu jurnalın
    # ÜMUMİYYƏTLƏ açılışı varmı» sualına cavab verdiyi üçün HƏR İKİ formanı
    # tanımalıdır — əks halda bölünmüş run-da BÜTÜN xanalar «orphan jurnal»
    # sayılır və nərdivan mənfi «izahsız fərq» verir (2026-08-27-də məhz belə
    # oldu: 4.4 M xana səhvən orphan göstərildi).
    #
    # Tam açar da dəstə salınır ki, `uniqid`-in özündə «:» olsa belə (ledger
    # OPAQUE_KEY_PATTERN buna icazə verir) dəqiq uyğunluq itməsin.
    offering_journals: set[str] = set()
    for key in offerings:
        offering_journals.add(key)
        head, separator, _ = key.partition(":")
        if separator:
            offering_journals.add(head)

    attribution = {domain: {"orphan": 0, "unresolved": 0, "expected": 0} for domain in DOMAINS}
    for uniqid, student_id, domain, count in source_facts["cells_by_enrollment"]:
        if domain not in attribution:
            continue
        bucket = attribution[domain]
        if uniqid not in offering_journals:
            bucket["orphan"] += count
        elif f"{uniqid}:{student_id}" not in enrollments:
            bucket["unresolved"] += count
        else:
            bucket["expected"] += count

    ladders: dict[str, Ladder] = {}
    for domain in DOMAINS:
        source_total = sum(count for key, count in classification.items() if key[2] == domain)
        target_total = sum(entity_counts.get(key, 0) for key in TARGET_OF_DOMAIN[domain])
        ladder = Ladder(name=domain, source_total=source_total, target=target_total)
        ladder.deduct("boş xana (mənbədə dəyər yoxdur)", _sum_outcome(classification, domain, OUTCOME_EMPTY))
        ladder.deduct("oxunmayan xana (karantin)", _sum_outcome(classification, domain, OUTCOME_UNREADABLE))
        ladder.deduct("arxiv örtüşməsi (J-V7 kəsimindən sonra)", _archive_overlap(classification, domain))
        raw = source_facts["raw_writable"].get(domain, 0)
        deduped = sum(bucket for bucket in attribution[domain].values())
        if source_facts["cells_by_enrollment"]:
            ladder.deduct("dublikat xana (J-V4 uduzanları)", max(0, raw - deduped))
            ladder.deduct("orphan jurnal (açılış yaradılmayıb)", attribution[domain]["orphan"])
            ladder.deduct("həll olunmayan yazılış (tələbə jurnalda aktiv deyil)", attribution[domain]["unresolved"])
        ladders[domain] = ladder
    return ladders


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
        for row in target.query("yekun güzgüsü", T.FINAL_MIRROR_SQL, (list(linked),)):
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
