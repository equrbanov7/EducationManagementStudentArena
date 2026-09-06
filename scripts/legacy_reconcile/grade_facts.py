"""Legacy qiymət sübutu üçün PII-siz, sətir-səviyyəli uzlaşdırma.

Sorğular yalnız texniki mənbə açarlarını və qiymət payload-unu oxuyur; ad, FİN,
e-poçt və əlaqə məlumatı seçilmir. Fərdi açarlar hesabatda göstərilmir: yalnız
saylar, status paylanmaları və yekun PASS/FAIL qaytarılır.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.legacy_import.services.rehearsal_contracts import encoded_part, stable_source_value

from .analysis import fmt_int, md_table

SOURCE_SYSTEM = "myedu_mariadb"
FACT_MODEL_LABEL = "registrar.legacygradefact"
SOURCE_TABLES = (
    "yekun",
    "journals_dates_points",
    "journals_dates_points_archive",
    "imthngrscxsblr",
)

_NON_GRADE_MONTHS = tuple(f"{month:02d}" for month in range(1, 13)) + ("k1", "k2", "k3", "si")
_NON_GRADE_SQL = ", ".join(f"'{value}'" for value in _NON_GRADE_MONTHS)

# Sütun sırası SOURCE_GRADE_FACT_ROWS_SQL və TARGET_GRADE_FACT_ROWS_SQL üçün
# ortaq müqavilədir. İlk 25 sütun eyni semantik payload-u ifadə edir.
PAYLOAD_WIDTH = 25
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MATERIALIZATION_DIGEST_NAMESPACE = b"legacy-grade-fact-materialization-v2\x00"

SOURCE_GRADE_FACT_ROWS_SQL = f"""
SELECT source_table, source_pk, evidence_kind, score_code, is_archive,
       source_student_ref, source_journal_ref, source_lesson_ref, source_group_ref,
       source_enrollment_ref,
       entry_score_text, exam_score_text, resit_score_text, final_score_text,
       raw_score_text, entry_score, exam_score, resit_score, final_score,
       legacy_kesr, legacy_level, legacy_guzest_girish_text, legacy_guzest_artim_text,
       legacy_attempt_type, legacy_recorded_at_text
  FROM (
        SELECT 'yekun' AS source_table, y.id AS source_pk,
               'summary' AS evidence_kind, 'yekun' AS score_code, 0 AS is_archive,
               CAST(y.student_id AS CHAR) AS source_student_ref,
               CAST(y.journal_id AS CHAR) AS source_journal_ref,
               CAST(y.lesson_id AS CHAR) AS source_lesson_ref,
               CAST(y.group_id AS CHAR) AS source_group_ref,
               CASE WHEN COALESCE(j.uniqid, '') = '' THEN ''
                    ELSE CONCAT(j.uniqid, ':', CAST(y.student_id AS CHAR)) END AS source_enrollment_ref,
               CAST(y.girish AS CHAR) AS entry_score_text,
               CAST(y.imtahanda AS CHAR) AS exam_score_text,
               '' AS resit_score_text,
               CAST(y.yekun AS CHAR) AS final_score_text,
               '' AS raw_score_text,
               CAST(y.girish AS CHAR) AS entry_score,
               CAST(y.imtahanda AS CHAR) AS exam_score,
               NULL AS resit_score,
               CAST(y.yekun AS CHAR) AS final_score,
               y.kesr AS legacy_kesr, y.level AS legacy_level,
               CAST(y.guzest_girish AS CHAR) AS legacy_guzest_girish_text,
               CAST(y.guzest_artim AS CHAR) AS legacy_guzest_artim_text,
               NULL AS legacy_attempt_type, '' AS legacy_recorded_at_text
          FROM yekun y
          LEFT JOIN journals j ON j.id = y.journal_id
        UNION ALL
        SELECT 'journals_dates_points', p.id,
               CASE WHEN COALESCE(p.month_id, '') = 'im' THEN 'exam'
                    WHEN COALESCE(p.month_id, '') = 'im2' THEN 'resit'
                    ELSE 'other' END,
               COALESCE(p.month_id, ''), 0,
               CAST(COALESCE(p.student_id, 0) AS CHAR),
               COALESCE(p.journal_uniqid, ''), '', '',
               CONCAT(COALESCE(p.journal_uniqid, ''), ':', CAST(COALESCE(p.student_id, 0) AS CHAR)),
               '',
               CASE WHEN COALESCE(p.month_id, '') = 'im' THEN COALESCE(p.point, '') ELSE '' END,
               CASE WHEN COALESCE(p.month_id, '') = 'im2' THEN COALESCE(p.point, '') ELSE '' END,
               '', COALESCE(p.point, ''),
               NULL,
               CASE WHEN COALESCE(p.month_id, '') = 'im' AND COALESCE(p.point, '') REGEXP '^[0-9]+$'
                    THEN p.point ELSE NULL END,
               CASE WHEN COALESCE(p.month_id, '') = 'im2' AND COALESCE(p.point, '') REGEXP '^[0-9]+$'
                    THEN p.point ELSE NULL END,
               NULL, NULL, NULL, '', '', NULL, ''
          FROM journals_dates_points p
         WHERE COALESCE(p.month_id, '') NOT IN ({_NON_GRADE_SQL})
        UNION ALL
        SELECT 'journals_dates_points_archive', p.id,
               CASE WHEN COALESCE(p.month_id, '') = 'im' THEN 'exam'
                    WHEN COALESCE(p.month_id, '') = 'im2' THEN 'resit'
                    ELSE 'other' END,
               COALESCE(p.month_id, ''), 1,
               CAST(COALESCE(p.student_id, 0) AS CHAR),
               COALESCE(p.journal_uniqid, ''), '', '',
               CONCAT(COALESCE(p.journal_uniqid, ''), ':', CAST(COALESCE(p.student_id, 0) AS CHAR)),
               '',
               CASE WHEN COALESCE(p.month_id, '') = 'im' THEN COALESCE(p.point, '') ELSE '' END,
               CASE WHEN COALESCE(p.month_id, '') = 'im2' THEN COALESCE(p.point, '') ELSE '' END,
               '', COALESCE(p.point, ''),
               NULL,
               CASE WHEN COALESCE(p.month_id, '') = 'im' AND COALESCE(p.point, '') REGEXP '^[0-9]+$'
                    THEN p.point ELSE NULL END,
               CASE WHEN COALESCE(p.month_id, '') = 'im2' AND COALESCE(p.point, '') REGEXP '^[0-9]+$'
                    THEN p.point ELSE NULL END,
               NULL, NULL, NULL, '', '', NULL, ''
          FROM journals_dates_points_archive p
         WHERE COALESCE(p.month_id, '') NOT IN ({_NON_GRADE_SQL})
        UNION ALL
        SELECT 'imthngrscxsblr', a.id,
               'exam_entry_exit', 'exam_entry_exit', 0,
               CAST(a.student_id AS CHAR), '', CAST(a.lesson_id AS CHAR), '', '',
               CAST(a.giris_point AS CHAR), CAST(a.cixis_point AS CHAR), '', '', '',
               CAST(a.giris_point AS CHAR), CAST(a.cixis_point AS CHAR), NULL, NULL,
               NULL, NULL, '', '', a.type, CAST(a.added_date AS CHAR)
          FROM imthngrscxsblr a
       ) grade_facts
 ORDER BY source_table, source_pk;
"""

TARGET_GRADE_FACT_ROWS_SQL = """
WITH selected_run AS (
    SELECT id, organization_id, source_system, snapshot_sha256, transform_version
      FROM legacy_import_legacymigrationrun
     WHERE id = %s AND status = 'succeeded'
)
SELECT f.source_table, f.source_pk::text, f.evidence_kind, f.score_code, f.is_archive,
       f.source_student_ref, f.source_journal_ref, f.source_lesson_ref, f.source_group_ref,
       f.source_enrollment_ref,
       f.entry_score_text, f.exam_score_text, f.resit_score_text, f.final_score_text,
       f.raw_score_text, f.entry_score, f.exam_score, f.resit_score, f.final_score,
       f.legacy_kesr, f.legacy_level, f.legacy_guzest_girish_text, f.legacy_guzest_artim_text,
       f.legacy_attempt_type, f.legacy_recorded_at_text,
       f.requires_exam_center_review, f.mapping_status, f.mapping_issue_code,
       f.enrollment_id::text,
       (f.enrollment_id IS NULL OR e.organization_id = f.organization_id) AS enrollment_org_matches,
       f.source_row_hash, f.materialization_digest, f.source_snapshot_sha256,
       f.transform_version, f.id::text,
       m.id::text, m.state, m.target_model_label, m.target_pk, m.source_row_hash,
       o.id::text, o.state, o.target_model_label, o.target_pk, o.source_row_hash,
       expected_enrollment.id::text, expected_enrollment.state, expected_enrollment.target_pk
  FROM registrar_legacygradefact f
 CROSS JOIN selected_run r
  LEFT JOIN registrar_enrollment e ON e.id = f.enrollment_id
  LEFT JOIN legacy_import_legacyentitymap m
    ON m.organization_id = f.organization_id
   AND m.source_system = f.source_system
   AND m.entity_type = CASE
       WHEN f.source_table IN ('journals_dates_points', 'journals_dates_points_archive')
        AND f.mapping_status = 'conflict'
        AND (f.score_code ~ '^(0[1-9]|1[0-2])$' OR f.score_code IN ('k1','k2','k3','si'))
         THEN 'legacy_mark_conflict'
       WHEN f.source_table IN ('journals_dates_points', 'journals_dates_points_archive')
        AND f.mapping_status = 'unresolved'
        AND f.score_code ~ '^(0[1-9]|1[0-2])$'
         THEN 'legacy_mark_unresolved'
       ELSE 'legacy_grade_fact'
       END
   AND m.legacy_pk = CASE
       WHEN f.source_table IN ('journals_dates_points', 'journals_dates_points_archive')
        AND f.mapping_status = 'conflict'
        AND (f.score_code ~ '^(0[1-9]|1[0-2])$' OR f.score_code IN ('k1','k2','k3','si'))
         THEN 'cf:' || CASE WHEN f.is_archive THEN 'a' ELSE 'p' END || ':' || f.source_pk::text
       WHEN f.source_table IN ('journals_dates_points', 'journals_dates_points_archive')
        AND f.mapping_status = 'unresolved'
        AND f.score_code ~ '^(0[1-9]|1[0-2])$'
         THEN 'uf:' || CASE WHEN f.is_archive THEN 'a' ELSE 'p' END || ':' || f.source_pk::text
       ELSE f.source_table || ':' || f.source_pk::text
       END
  LEFT JOIN legacy_import_legacyentityobservation o
    ON o.run_id = r.id AND o.entity_map_id = m.id
  LEFT JOIN legacy_import_legacyentitymap expected_enrollment
    ON expected_enrollment.organization_id = f.organization_id
   AND expected_enrollment.source_system = f.source_system
   AND expected_enrollment.entity_type = 'journal_enrollment'
   AND expected_enrollment.legacy_pk = f.source_enrollment_ref
 WHERE f.organization_id = r.organization_id
   AND f.source_system = r.source_system
   AND f.source_snapshot_sha256 = r.snapshot_sha256
   AND f.transform_version = r.transform_version
 ORDER BY f.source_table, f.source_pk;
"""


def _text(value) -> str:
    return "" if value in (None, "NULL") else str(value)


def _decimal(value) -> Decimal | None:
    text = _text(value)
    if text == "":
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _integer(value) -> int | None:
    return None if value in (None, "", "NULL") else int(value)


def _boolean(value) -> bool:
    if type(value) is bool:
        return value
    return _text(value).casefold() in {"1", "t", "true"}


def _payload(row) -> tuple:
    """Mənbə və hədəf sətrini eyni, itkisiz qiymət müqaviləsinə sal."""

    if len(row) < PAYLOAD_WIDTH:
        raise ValueError("legacy_grade_reconcile_row_shape_invalid")
    attempt = _text(row[0]) == "imthngrscxsblr"
    return (
        _text(row[2]),
        _text(row[3]),
        _boolean(row[4]),
        _text(row[5]),
        "" if attempt else _text(row[6]),
        _text(row[7]),
        _text(row[8]),
        "" if attempt else _text(row[9]),
        *(_decimal(row[index]) for index in range(10, 14)),
        _text(row[14]),
        *(_decimal(row[index]) for index in range(15, 19)),
        _integer(row[19]),
        _integer(row[20]),
        _decimal(row[21]),
        _decimal(row[22]),
        _integer(row[23]),
        _text(row[24]),
    )


def _key(row) -> tuple[str, int]:
    return (_text(row[0]), int(row[1]))


def _index(rows) -> tuple[dict[tuple[str, int], tuple], int]:
    indexed: dict[tuple[str, int], tuple] = {}
    duplicates = 0
    for row in rows:
        key = _key(row)
        if key in indexed:
            duplicates += 1
        else:
            indexed[key] = row
    return indexed, duplicates


def _materialization_digest(row) -> str:
    """Target payload-dan importer-lə eyni deterministik möhürü yenidən qur."""

    source_table, source_pk = _key(row)
    kind = _text(row[2])
    raw_score = _text(row[14])
    point_number = Decimal(raw_score) if raw_score.isdigit() else None
    if kind == "summary":
        numeric_scores = (_decimal(row[10]), _decimal(row[11]), None, _decimal(row[13]))
    elif kind == "exam":
        numeric_scores = (None, point_number, None, None)
    elif kind == "resit":
        numeric_scores = (None, None, point_number, None)
    elif kind == "exam_entry_exit":
        numeric_scores = (_decimal(row[10]), _decimal(row[11]), None, None)
    else:
        numeric_scores = (None, None, None, None)
    payload = {
        "enrollment_id": _text(row[28]) or None,
        "evidence_kind": _text(row[2]),
        "score_code": _text(row[3]),
        "is_archive": _boolean(row[4]),
        "mapping_status": _text(row[26]),
        "mapping_issue_code": _text(row[27]),
        "source_student_ref": _text(row[5]),
        "source_journal_ref": _text(row[6]),
        "source_lesson_ref": _text(row[7]),
        "source_group_ref": _text(row[8]),
        "source_enrollment_ref": _text(row[9]),
        "entry_score_text": _text(row[10]),
        "exam_score_text": _text(row[11]),
        "resit_score_text": _text(row[12]),
        "final_score_text": _text(row[13]),
        "raw_score_text": _text(row[14]),
        # Digest import vaxtındakı Decimal lexical formasını istifadə edib.
        # PostgreSQL DecimalField isə oxunuşda həmişə 4 sıfır əlavə edə bilər;
        # buna görə orijinal text/raw sahədən eyni Decimal yenidən qurulur.
        "entry_score": numeric_scores[0],
        "exam_score": numeric_scores[1],
        "resit_score": numeric_scores[2],
        "final_score": numeric_scores[3],
        "legacy_kesr": _integer(row[19]),
        "legacy_level": _integer(row[20]),
        "legacy_guzest_girish_text": _text(row[21]),
        "legacy_guzest_artim_text": _text(row[22]),
        "legacy_attempt_type": _integer(row[23]),
        "legacy_recorded_at_text": _text(row[24]),
        "source_snapshot_sha256": _text(row[32]),
        "source_row_hash": _text(row[30]),
        "transform_version": _text(row[33]),
        "requires_exam_center_review": _boolean(row[25]),
    }
    # J12 toqquşma/həll-olunmayan xana faktlarını ayrıca writer yaradır və
    # onun importer payload-u modelin boş default sahələrini daşımır. Digest
    # məhz həmin source-sabit payload-dan qurulub; PostgreSQL-in sonradan
    # doldurduğu default-ları əlavə etsək 1 849 dürüst fakt yalnış pozuntu kimi
    # görünər. Bu forma conflict/unresolved writer-lərin `_payload()` müqaviləsi
    # ilə eynidir. Digər grade-fact növlərində tam payload qalır.
    if _is_j12_evidence(row):
        payload = {
            key: payload[key]
            for key in (
                "enrollment_id",
                "source_snapshot_sha256",
                "source_row_hash",
                "transform_version",
                "evidence_kind",
                "score_code",
                "is_archive",
                "mapping_status",
                "mapping_issue_code",
                "source_student_ref",
                "source_journal_ref",
                "source_lesson_ref",
                "source_enrollment_ref",
                "raw_score_text",
                "requires_exam_center_review",
            )
        }
    deterministic_payload = {key: value for key, value in payload.items() if key != "enrollment_id"}
    deterministic_payload["enrollment_linked"] = payload["enrollment_id"] is not None
    digest = hashlib.sha256(MATERIALIZATION_DIGEST_NAMESPACE)
    for part in (SOURCE_SYSTEM, source_table, source_pk):
        digest.update(encoded_part(str(part)))
    digest.update(encoded_part(_text(row[30])))
    for name in sorted(deterministic_payload):
        digest.update(encoded_part(name))
        digest.update(encoded_part(stable_source_value(deterministic_payload[name])))
    return digest.hexdigest()


def _is_j12_evidence(row) -> bool:
    """Sətir J12-nin xüsusi xana-sübut writer-indən gəlibmi?"""

    source_table = _text(row[0])
    status = _text(row[26])
    score_code = _text(row[3])
    if source_table not in {"journals_dates_points", "journals_dates_points_archive"}:
        return False
    if status == "conflict":
        return bool(re.fullmatch(r"0[1-9]|1[0-2]|k[1-3]|si", score_code))
    return status == "unresolved" and bool(re.fullmatch(r"0[1-9]|1[0-2]", score_code))


def _digest_matches(row) -> bool:
    """Saxlanmış materialization digest yenidən hesablanan möhürlə tutmalıdır."""

    return _materialization_digest(row) == _text(row[31])


def _guard_failures(row) -> tuple[str, ...]:
    failures: list[str] = []
    fact_pk = _text(row[34])
    status = _text(row[26])
    issue = _text(row[27])
    linked = status in {"linked", "conflict"}
    j12_unresolved = status == "unresolved" and _is_j12_evidence(row)
    expected_issue = {
        "linked": "",
        "conflict": "legacy_grade_fact_conflict",
        "group_mismatch": "legacy_grade_fact_group_mismatch",
        "discarded_source": "legacy_grade_fact_discarded_source",
        "unresolved": "legacy_grade_fact_unresolved",
    }.get(status)
    checks = {
        "review_required_false": _boolean(row[25]),
        "enrollment_tenant_mismatch": _boolean(row[29]),
        "mapping_status_invalid": expected_issue is not None,
        "mapping_issue_mismatch": expected_issue == issue,
        "mapping_enrollment_mismatch": bool(_text(row[28])) == linked,
        "source_enrollment_ref_missing": bool(_text(row[9])) or not linked,
        "source_hash_invalid": bool(SHA256_RE.fullmatch(_text(row[30]))),
        "materialization_digest_invalid": _digest_matches(row),
        "ledger_map_missing": bool(_text(row[35])),
        "ledger_map_state_invalid": _text(row[36]) == "migrated",
        "ledger_map_label_invalid": _text(row[37]) == FACT_MODEL_LABEL,
        "ledger_map_target_invalid": _text(row[38]) == fact_pk,
        "ledger_map_digest_invalid": _text(row[39]) == _text(row[31]),
        "ledger_observation_missing": bool(_text(row[40])),
        "ledger_observation_state_invalid": _text(row[41]) == "migrated",
        "ledger_observation_label_invalid": _text(row[42]) == FACT_MODEL_LABEL,
        "ledger_observation_target_invalid": _text(row[43]) == fact_pk,
        "ledger_observation_digest_invalid": _text(row[44]) == _text(row[31]),
        "enrollment_map_missing": bool(_text(row[45])) or not linked,
        "enrollment_map_state_invalid": _text(row[46]) == "migrated" or not linked,
        "enrollment_map_target_mismatch": _text(row[47]) == _text(row[28]) or not linked,
        # J12 unresolved faktında tələbə/yazılış xəritəsi mövcud ola bilər;
        # bağlana bilməyən hissə məhz etibarlı təqvim dərsidir. Writer qəsdən
        # enrollment FK yazmır, xam faktı unresolved saxlayır.
        "nonlinked_migrated_enrollment_map": linked
        or j12_unresolved
        or not (_text(row[45]) and _text(row[46]) == "migrated"),
    }
    for code, passed in checks.items():
        if not passed:
            failures.append(code)
    return tuple(failures)


@dataclass(frozen=True)
class GradeFactReconciliation:
    source_rows: int
    target_rows: int
    source_duplicates: int
    target_duplicates: int
    missing_keys: int
    extra_keys: int
    payload_mismatches: int
    source_hash_mismatches: int
    guard_failures: dict[str, int]
    source_by_table: dict[str, int]
    target_by_table: dict[str, int]
    source_by_code: dict[str, int]
    target_by_code: dict[str, int]
    mapping_statuses: dict[str, int]

    @property
    def passed(self) -> bool:
        return not any(
            (
                self.source_duplicates,
                self.target_duplicates,
                self.missing_keys,
                self.extra_keys,
                self.payload_mismatches,
                self.source_hash_mismatches,
                sum(self.guard_failures.values()),
            )
        )


def reconcile_grade_facts(
    source,
    target,
    *,
    run_id,
    source_hashes=None,
    extra_source_rows=(),
) -> GradeFactReconciliation:
    """Mənbə və immutable target faktlarını sətir-səviyyəsində tutuşdur."""

    source_rows = source.query("legacy qiymət faktları", SOURCE_GRADE_FACT_ROWS_SQL)
    source_rows.extend(list(extra_source_rows))
    target_rows = target.query(
        "immutable legacy qiymət faktları",
        TARGET_GRADE_FACT_ROWS_SQL,
        (str(run_id),),
    )
    source_index, source_duplicates = _index(source_rows)
    target_index, target_duplicates = _index(target_rows)
    source_keys = set(source_index)
    target_keys = set(target_index)
    shared = source_keys & target_keys
    payload_mismatches = sum(_payload(source_index[key]) != _payload(target_index[key]) for key in shared)
    source_hash_mismatches = 0
    if source_hashes is not None:
        source_hash_keys = set(source_hashes)
        source_hash_mismatches += len(source_keys ^ source_hash_keys)
        source_hash_mismatches += sum(
            _text(target_index[key][30]) != source_hashes[key] for key in shared & source_hash_keys
        )
    guard_failures: Counter[str] = Counter()
    for row in target_rows:
        guard_failures.update(_guard_failures(row))

    def counts(rows, index):
        return dict(sorted(Counter(_text(row[index]) for row in rows).items()))

    return GradeFactReconciliation(
        source_rows=len(source_rows),
        target_rows=len(target_rows),
        source_duplicates=source_duplicates,
        target_duplicates=target_duplicates,
        missing_keys=len(source_keys - target_keys),
        extra_keys=len(target_keys - source_keys),
        payload_mismatches=payload_mismatches,
        source_hash_mismatches=source_hash_mismatches,
        guard_failures=dict(sorted(guard_failures.items())),
        source_by_table=counts(source_rows, 0),
        target_by_table=counts(target_rows, 0),
        source_by_code=counts(source_rows, 3),
        target_by_code=counts(target_rows, 3),
        mapping_statuses=counts(target_rows, 26),
    )


def render_grade_fact_reconciliation(result: GradeFactReconciliation) -> str:
    """Fərdi açar göstərmədən stakeholder üçün audit bölməsi render et."""

    verdict = "✅ TAM TUTUR" if result.passed else "🔴 UYĞUNSUZLUQ VAR"
    summary = [
        ["Mənbə qiymət faktı", fmt_int(result.source_rows)],
        ["Immutable hədəf faktı", fmt_int(result.target_rows)],
        ["Mənbədə təkrarlanan `(cədvəl, PK)`", fmt_int(result.source_duplicates)],
        ["Hədəfdə təkrarlanan `(cədvəl, PK)`", fmt_int(result.target_duplicates)],
        ["Hədəfdə çatışmayan mənbə açarı", fmt_int(result.missing_keys)],
        ["Mənbədə qarşılığı olmayan artıq hədəf açarı", fmt_int(result.extra_keys)],
        ["Bal payload-u fərqli olan ortaq açar", fmt_int(result.payload_mismatches)],
        ["Mənbədən müstəqil yenidən hesablanan hash uyğunsuzluğu", fmt_int(result.source_hash_mismatches)],
        ["Ledger / tenant / hash / review guard pozuntusu", fmt_int(sum(result.guard_failures.values()))],
    ]
    table_rows = []
    for table in sorted(set(result.source_by_table) | set(result.target_by_table)):
        source_count = result.source_by_table.get(table, 0)
        target_count = result.target_by_table.get(table, 0)
        table_rows.append(
            [f"`{table}`", fmt_int(source_count), fmt_int(target_count), fmt_int(target_count - source_count)]
        )
    code_rows = []
    for code in sorted(set(result.source_by_code) | set(result.target_by_code)):
        source_count = result.source_by_code.get(code, 0)
        target_count = result.target_by_code.get(code, 0)
        code_rows.append(
            [f"`{code or '(boş)'}`", fmt_int(source_count), fmt_int(target_count), fmt_int(target_count - source_count)]
        )
    mapping_rows = [[f"`{status}`", fmt_int(count)] for status, count in result.mapping_statuses.items()]
    guard_rows = [[f"`{code}`", fmt_int(count)] for code, count in result.guard_failures.items()]
    return "\n".join(
        [
            "## 4A. Legacy qiymət faktlarının itkisizlik sübutu",
            "",
            "> Bu yoxlama ad/FİN/e-poçt çıxarmır və fərdi açarları hesabatda göstərmir.",
            "> Hər `(mənbə cədvəli, PK)` üçün giriş, imtahan, yekun, təkrar və xüsusi",
            "> kod payload-u sətir-səviyyəsində tutuşdurulur; nəticə yalnız aqreqatdır.",
            "",
            md_table(["Invariant", "Say"], summary),
            "",
            f"**Nəticə: {verdict}.**",
            "",
            "### Mənbə cədvəli üzrə",
            "",
            md_table(["Cədvəl", "Mənbə", "Hədəf", "Fərq"], table_rows),
            "",
            "### Qiymət kodu üzrə",
            "",
            md_table(["Kod", "Mənbə", "Hədəf", "Fərq"], code_rows),
            "",
            "### Mapping statusu üzrə (sübut saxlanır, kanonik bağ ayrıca qiymətləndirilir)",
            "",
            md_table(["Status", "Say"], mapping_rows),
            *(["", "### Guard pozuntuları", "", md_table(["Kod", "Say"], guard_rows)] if guard_rows else []),
        ]
    )


__all__ = [
    "GradeFactReconciliation",
    "SOURCE_GRADE_FACT_ROWS_SQL",
    "TARGET_GRADE_FACT_ROWS_SQL",
    "reconcile_grade_facts",
    "render_grade_fact_reconciliation",
]
