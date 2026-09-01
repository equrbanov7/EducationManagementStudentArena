#!/usr/bin/env bash
#
# load_legacy_grade_evidence.sh
# =============================
#
# Köçürülmüş qiymət SÜBUT QATINI repetisiya bazasından lokal dev bazasına
# köçürür: `registrar_legacygradefact` + `registrar_legacygradeartifact`.
#
# NİYƏ LAZIMDIR
# -------------
# Köçürülmüş qiymətin GÖRÜNƏN nişanı (`_legacy_grade_mark.html`) və
# «Köçürülmüş nəticələrin dəqiqləşdirilməsi» bölməsi (`legacy-grade-review`)
# hər ikisi `LegacyGradeFact` sətirlərindən qidalanır — nişan üçün AYRICA
# bayraq sütunu YOXDUR (bax `apps/registrar/legacy_grade_read.py` şərhi).
# Lokal dev bazasında bu iki cədvəl boş olduğu üçün nişan görünmür və
# dəqiqləşdirmə siyahısı boş qalır.  Bu skript həmin boşluğu doldurur.
#
# NİYƏ SADƏ `pg_dump | psql` DEYİL
# ---------------------------------
# İki baza eyni MariaDB mənbəyinin İKİ AYRI materializasiyasıdır; UUID-lər hər
# qaçışda təzədən doğulur.  Ölçülüb: `enrollment_id` və `organization_id` üçün
# xam UUID uyğunluğu 0.00 %-dir.  Xam köçürmə ona görə FK pozuntusu + trigger
# rəddi ilə bitər.  Skript iki sütunu YENİDƏN AÇARLAYIR:
#
#   1) organization_id — sabit əvəzləmə (hər iki bazada tək org, slug eyni)
#   2) enrollment_id   — natural açar üzərindən xəritə:
#        username | subject.code | period.academic_year | period.name
#                 | orgunit.code | orgunit.name | enrollment.kind
#      Açar hər iki bazada UNİKALDIR (148,020 sətir = 148,020 açar) və
#      faktların bağlı olduğu 120,516 qeydiyyatın 100 %-i həll olunur.
#
# Qalan bütün sütunlar (provenance, digest, mətn proyeksiyaları, payload)
# OLDUĞU KİMİ qalır.  `fact_materialization_digest` qəsdən `enrollment_id`-ni
# digest-ə daxil etmir, ona görə remap digest-i POZMUR.
#
# TƏHLÜKƏSİZLİK
# -------------
#   * YALNIZ ƏLAVƏ — mövcud cədvəllərə toxunmur, DROP/TRUNCATE etmir.
#   * İDEMPOTENT — `ON CONFLICT DO NOTHING`; təkrar işlədiləndə dublikat olmur.
#     (unikal açar: organization_id, source_system, source_table, source_pk)
#   * Bütün iş TƏK tranzaksiyadadır; hər hansı yoxlama sınarsa ROLLBACK olur.
#   * Staging cədvəlləri ayrıca `legacy_xfer` sxemindədir — `public`-ə dəymir.
#   * Yazma `app.bypass_rls='on'` altında gedir (RLS + trigger aktor yoxlaması).
#     Struktur trigger yoxlamaları (mapping_status uyğunluğu, enrollment↔org
#     eyniliyi) YERİNDƏ QALIR və qəsdən keçilmir.
#
# QEYD: cədvəllər append-only trigger-lə qorunur (UPDATE/DELETE bloklanır).
# Geri qaytarmaq üçün superuser TRUNCATE lazımdır — bax `--rollback`.
#
# İSTİFADƏ
# --------
#   ./scripts/load_legacy_grade_evidence.sh            # köçür + doğrula
#   ./scripts/load_legacy_grade_evidence.sh --verify   # yalnız doğrulama
#   ./scripts/load_legacy_grade_evidence.sh --rollback # sübut qatını boşalt
#
set -euo pipefail

# ── Bağlantılar ──────────────────────────────────────────────────────────────
DEV_CONTAINER="${DEV_CONTAINER:-emsarena-postgres}"
DEV_USER="${DEV_USER:-emsarena_user}"
DEV_DB="${DEV_DB:-emsarena_db}"

REH_HOST="${REH_HOST:-127.0.0.1}"
REH_PORT="${REH_PORT:-55433}"
REH_USER="${REH_USER:-emsarena_app}"
REH_DB="${REH_DB:-emsarena_rehearsal_52ea0301808c}"
REH_PASSWORD="${REH_PASSWORD:-emsarena_staging_app_password}"

WORKDIR="${WORKDIR:-$(mktemp -d -t legacy_grade_xfer)}"

dev() { docker exec -i "$DEV_CONTAINER" psql -U "$DEV_USER" -d "$DEV_DB" "$@"; }
reh() { PGPASSWORD="$REH_PASSWORD" psql -h "$REH_HOST" -p "$REH_PORT" -U "$REH_USER" -d "$REH_DB" "$@"; }

# Sütun siyahıları AÇIQ yazılır: `SELECT *` sütun sırası sürüşəndə səssizcə
# məlumatı korlaya bilər, açıq siyahı isə səhv olanda dərhal xəta verir.
FACT_COLS="created_at, updated_at, id, source_system, source_table, source_pk,
 source_snapshot_sha256, source_row_hash, materialization_digest, transform_version,
 evidence_kind, score_code, is_archive, mapping_status, mapping_issue_code,
 source_student_ref, source_journal_ref, source_lesson_ref, source_group_ref,
 source_enrollment_ref, entry_score_text, exam_score_text, resit_score_text,
 final_score_text, raw_score_text, entry_score, exam_score, resit_score, final_score,
 legacy_kesr, legacy_level, legacy_guzest_girish_text, legacy_guzest_artim_text,
 requires_exam_center_review, enrollment_id, organization_id, legacy_attempt_type,
 legacy_recorded_at_text"

# Eyni siyahı `f.` prefiksi ilə (ixracdakı JOIN-lar üçün) — sed ilə törədilmir,
# çünki səssiz sürüşmə riski var; açıq yazılır və QAPI 3 sayı yoxlayır.
FACT_COLS_F="f.created_at, f.updated_at, f.id, f.source_system, f.source_table, f.source_pk,
 f.source_snapshot_sha256, f.source_row_hash, f.materialization_digest, f.transform_version,
 f.evidence_kind, f.score_code, f.is_archive, f.mapping_status, f.mapping_issue_code,
 f.source_student_ref, f.source_journal_ref, f.source_lesson_ref, f.source_group_ref,
 f.source_enrollment_ref, f.entry_score_text, f.exam_score_text, f.resit_score_text,
 f.final_score_text, f.raw_score_text, f.entry_score, f.exam_score, f.resit_score, f.final_score,
 f.legacy_kesr, f.legacy_level, f.legacy_guzest_girish_text, f.legacy_guzest_artim_text,
 f.requires_exam_center_review, f.enrollment_id, f.organization_id, f.legacy_attempt_type,
 f.legacy_recorded_at_text"

ART_COLS="created_at, updated_at, id, source_system, source_table, source_pk,
 source_snapshot_sha256, source_row_hash, materialization_digest, transform_version,
 artifact_kind, source_owner_ref, source_journal_ref, source_exported_at_text,
 payload_sha256, payload_size_bytes, payload_zlib, requires_exam_center_review,
 organization_id"

# Qeydiyyatın natural açarı — hər iki bazada EYNİ ifadə işlədilməlidir.
NKEY_SQL="u.username || '|' || s.code || '|' || p.academic_year || '|' || p.name
       || '|' || COALESCE(g.code,'') || '|' || COALESCE(g.name,'') || '|' || e.kind"

NKEY_FROM="FROM registrar_enrollment e
  JOIN registrar_courseoffering o ON o.id = e.offering_id
  JOIN registrar_subject s ON s.id = o.subject_id
  JOIN organizations_academicperiod p ON p.id = o.period_id
  LEFT JOIN organizations_orgunit g ON g.id = o.group_id
  JOIN auth_user u ON u.id = e.student_id"

# ── Doğrulama ────────────────────────────────────────────────────────────────
verify() {
  echo "── Sübut qatı örtüyü (dev) ──────────────────────────────────────────"
  dev -v ON_ERROR_STOP=1 <<SQL
SELECT 'fakt sətri' AS metrik, count(*)::text AS deyer FROM registrar_legacygradefact
UNION ALL SELECT 'artefakt sətri', count(*)::text FROM registrar_legacygradeartifact
UNION ALL SELECT 'faktı olan qeydiyyat', count(DISTINCT enrollment_id)::text
  FROM registrar_legacygradefact WHERE enrollment_id IS NOT NULL
UNION ALL SELECT 'yekun qiymət (cəmi)', count(*)::text FROM registrar_finalgrade
UNION ALL SELECT 'nişan ALAN yekun qiymət', count(*)::text
  FROM registrar_finalgrade fg
  WHERE EXISTS (SELECT 1 FROM registrar_legacygradefact f WHERE f.enrollment_id = fg.enrollment_id)
UNION ALL SELECT 'nişanSIZ yekun qiymət', count(*)::text
  FROM registrar_finalgrade fg
  WHERE NOT EXISTS (SELECT 1 FROM registrar_legacygradefact f WHERE f.enrollment_id = fg.enrollment_id)
UNION ALL SELECT 'örtük %', round(100.0 * count(*) FILTER (
    WHERE EXISTS (SELECT 1 FROM registrar_legacygradefact f WHERE f.enrollment_id = fg.enrollment_id)
  ) / NULLIF(count(*),0), 2)::text
  FROM registrar_finalgrade fg;

SELECT mapping_status, count(*) AS sətir, count(enrollment_id) AS qeydiyyatlı
  FROM registrar_legacygradefact GROUP BY 1 ORDER BY 2 DESC;
SQL
}

# ── Geri qaytarma ────────────────────────────────────────────────────────────
rollback() {
  echo "!! Sübut qatı BOŞALDILIR (append-only trigger superuser TRUNCATE ilə keçilir)"
  dev -v ON_ERROR_STOP=1 <<SQL
BEGIN;
TRUNCATE registrar_legacygradereview, registrar_legacygradefact, registrar_legacygradeartifact;
COMMIT;
SQL
  echo "Boşaldıldı."
}

case "${1:-}" in
  --verify)   verify; exit 0 ;;
  --rollback) rollback; verify; exit 0 ;;
esac

# ── 1. Preflight ─────────────────────────────────────────────────────────────
echo "── Preflight ────────────────────────────────────────────────────────"
DEV_ORG=$(dev -t -A -c "SELECT id FROM organizations_organization ORDER BY created_at LIMIT 1;")
REH_ORG=$(reh -t -A -c "SET app.bypass_rls='on'; SELECT id FROM organizations_organization ORDER BY created_at LIMIT 1;" | tail -1)
echo "dev org        : $DEV_ORG"
echo "repetisiya org : $REH_ORG"
[ -n "$DEV_ORG" ] && [ -n "$REH_ORG" ] || { echo "XƏTA: org tapılmadı"; exit 1; }
echo "iş qovluğu     : $WORKDIR"

# ── 2. Repetisiyadan ixrac ───────────────────────────────────────────────────
# Faktlar mənbə qeydiyyatının natural açarı ilə birlikdə ixrac olunur ki, dev
# tərəfdə bütöv `registrar_enrollment` cədvəlini köçürməyə ehtiyac qalmasın.
echo "── İxrac (repetisiya) ───────────────────────────────────────────────"
reh -q -v ON_ERROR_STOP=1 <<SQL > "$WORKDIR/facts.tsv"
SET app.bypass_rls='on';
COPY (
  SELECT $FACT_COLS_F,
         CASE WHEN f.enrollment_id IS NULL THEN NULL ELSE ($NKEY_SQL) END AS src_nkey
    FROM registrar_legacygradefact f
    LEFT JOIN registrar_enrollment e ON e.id = f.enrollment_id
    LEFT JOIN registrar_courseoffering o ON o.id = e.offering_id
    LEFT JOIN registrar_subject s ON s.id = o.subject_id
    LEFT JOIN organizations_academicperiod p ON p.id = o.period_id
    LEFT JOIN organizations_orgunit g ON g.id = o.group_id
    LEFT JOIN auth_user u ON u.id = e.student_id
) TO STDOUT;
SQL
echo "faktlar    : $(wc -l < "$WORKDIR/facts.tsv") sətir"

reh -q -v ON_ERROR_STOP=1 <<SQL > "$WORKDIR/artifacts.tsv"
SET app.bypass_rls='on';
COPY (SELECT $ART_COLS FROM registrar_legacygradeartifact) TO STDOUT;
SQL
echo "artefaktlar: $(wc -l < "$WORKDIR/artifacts.tsv") sətir"

# ── 3. Staging-ə yükləmə ─────────────────────────────────────────────────────
echo "── Staging (dev.legacy_xfer) ────────────────────────────────────────"
dev -v ON_ERROR_STOP=1 <<SQL
CREATE SCHEMA IF NOT EXISTS legacy_xfer;
DROP TABLE IF EXISTS legacy_xfer.fact_stage;
DROP TABLE IF EXISTS legacy_xfer.artifact_stage;
CREATE TABLE legacy_xfer.fact_stage (LIKE public.registrar_legacygradefact);
ALTER TABLE legacy_xfer.fact_stage ADD COLUMN src_nkey text;
CREATE TABLE legacy_xfer.artifact_stage (LIKE public.registrar_legacygradeartifact);
SQL

dev -v ON_ERROR_STOP=1 -c "\copy legacy_xfer.fact_stage ($FACT_COLS, src_nkey) FROM STDIN" < "$WORKDIR/facts.tsv"
dev -v ON_ERROR_STOP=1 -c "\copy legacy_xfer.artifact_stage ($ART_COLS) FROM STDIN" < "$WORKDIR/artifacts.tsv"

# ── 4. Remap + əlavə (tək tranzaksiya) ───────────────────────────────────────
echo "── Remap + INSERT (tək tranzaksiya) ─────────────────────────────────"
dev -v ON_ERROR_STOP=1 <<SQL
BEGIN;
SET LOCAL app.bypass_rls = 'on';

-- Dev qeydiyyatlarının natural açar xəritəsi.
CREATE TEMP TABLE dev_nkey ON COMMIT DROP AS
  SELECT e.id AS enrollment_id, ($NKEY_SQL) AS nkey $NKEY_FROM;
CREATE UNIQUE INDEX ON dev_nkey(nkey);
ANALYZE dev_nkey;

-- QAPI 1: açar dev tərəfdə unikal olmalıdır (yuxarıdakı UNIQUE indeks bunu
-- təmin edir; sınarsa tranzaksiya burada dayanır).

-- QAPI 2: qeydiyyata bağlı hər fakt həll olunmalıdır — bir dənə də itki yox.
DO \$\$
DECLARE missing bigint;
BEGIN
  SELECT count(*) INTO missing
    FROM legacy_xfer.fact_stage f
    LEFT JOIN dev_nkey m ON m.nkey = f.src_nkey
   WHERE f.src_nkey IS NOT NULL AND m.enrollment_id IS NULL;
  IF missing > 0 THEN
    RAISE EXCEPTION 'remap natamam: % fakt qeydiyyatı dev-də tapılmadı', missing;
  END IF;
END \$\$;

INSERT INTO public.registrar_legacygradeartifact ($ART_COLS)
SELECT created_at, updated_at, id, source_system, source_table, source_pk,
       source_snapshot_sha256, source_row_hash, materialization_digest, transform_version,
       artifact_kind, source_owner_ref, source_journal_ref, source_exported_at_text,
       payload_sha256, payload_size_bytes, payload_zlib, requires_exam_center_review,
       '$DEV_ORG'::uuid
  FROM legacy_xfer.artifact_stage
ON CONFLICT DO NOTHING;

INSERT INTO public.registrar_legacygradefact ($FACT_COLS)
SELECT f.created_at, f.updated_at, f.id, f.source_system, f.source_table, f.source_pk,
       f.source_snapshot_sha256, f.source_row_hash, f.materialization_digest, f.transform_version,
       f.evidence_kind, f.score_code, f.is_archive, f.mapping_status, f.mapping_issue_code,
       f.source_student_ref, f.source_journal_ref, f.source_lesson_ref, f.source_group_ref,
       f.source_enrollment_ref, f.entry_score_text, f.exam_score_text, f.resit_score_text,
       f.final_score_text, f.raw_score_text, f.entry_score, f.exam_score, f.resit_score, f.final_score,
       f.legacy_kesr, f.legacy_level, f.legacy_guzest_girish_text, f.legacy_guzest_artim_text,
       f.requires_exam_center_review,
       m.enrollment_id,          -- remap
       '$DEV_ORG'::uuid,         -- remap
       f.legacy_attempt_type, f.legacy_recorded_at_text
  FROM legacy_xfer.fact_stage f
  LEFT JOIN dev_nkey m ON m.nkey = f.src_nkey
ON CONFLICT DO NOTHING;

-- QAPI 3: mənbə/hədəf sətir sayı üst-üstə düşməlidir.
DO \$\$
DECLARE src bigint; dst bigint;
BEGIN
  SELECT count(*) INTO src FROM legacy_xfer.fact_stage;
  SELECT count(*) INTO dst FROM public.registrar_legacygradefact;
  IF src <> dst THEN
    RAISE EXCEPTION 'fakt sayı uyğunsuzdur: mənbə=%, hədəf=%', src, dst;
  END IF;
END \$\$;

COMMIT;
SQL

# ── 5. Təmizlik + doğrulama ──────────────────────────────────────────────────
dev -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS legacy_xfer CASCADE;" >/dev/null
rm -rf "$WORKDIR"
verify
