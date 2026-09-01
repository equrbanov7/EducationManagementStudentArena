"""Hədəf (PostgreSQL / EMS Arena) tərəfin OXU sorğuları.

Ledger cədvəlləri (``legacy_import_*``) mənbə ilə hədəf arasındakı KÖRPÜdür:
``legacy_pk`` → ``target_pk``.  Hesabat həmin körpünü oxuyur, amma sayları
ledger-dən DEYİL, registrar cədvəllərinin özündən götürür — iki müstəqil sübut
mənbəyi qarşılaşdırılsın deyə.
"""

from __future__ import annotations

# ── Ledger (sətir mühasibatı) ────────────────────────────────────────────────

LEDGER_STATE_SQL = """
SELECT m.entity_type, o.state, COUNT(*)
  FROM legacy_import_legacyentityobservation o
  JOIN legacy_import_legacyentitymap m ON m.id = o.entity_map_id
 WHERE o.run_id = %s
   AND o.organization_id = %s
   AND m.organization_id = %s
 GROUP BY m.entity_type, o.state
 ORDER BY m.entity_type, o.state;
"""

LEDGER_BATCH_SQL = """
SELECT entity_type, source_table, SUM(source_row_count), SUM(migrated_count),
       SUM(skipped_count), SUM(quarantined_count)
  FROM legacy_import_legacyimportbatch
 WHERE run_id = %s AND organization_id = %s
 GROUP BY entity_type, source_table
 ORDER BY entity_type;
"""

LEDGER_ISSUE_SQL = """
SELECT source_table, rule_code, severity, COUNT(*)
  FROM legacy_import_legacymigrationissue
 WHERE run_id = %s AND organization_id = %s
 GROUP BY source_table, rule_code, severity
 ORDER BY COUNT(*) DESC;
"""

RUN_SQL = """
SELECT mode, status, snapshot_sha256, source_row_count, started_at, finished_at,
       migrated_count, skipped_count, quarantined_count, organization_id::text
  FROM legacy_import_legacymigrationrun
 WHERE id = %s AND organization_id = %s AND status = 'succeeded';
"""

MIGRATED_MAP_SQL = """
SELECT m.legacy_pk, o.target_pk
  FROM legacy_import_legacyentitymap m
  JOIN legacy_import_legacyentityobservation o ON o.entity_map_id = m.id
 WHERE o.run_id = %s AND m.entity_type = %s
   AND o.organization_id = %s AND m.organization_id = %s
   AND o.state = 'migrated' AND o.target_pk <> '';
"""

# ── Varlıq sayları (registrar/organizations cədvəllərindən birbaşa) ──────────

ENTITY_COUNTS_SQL = """
WITH scope AS (SELECT %s::uuid AS organization_id)
SELECT 'orgunit_faculty', COUNT(*) FROM organizations_orgunit
 WHERE organization_id = (SELECT organization_id FROM scope) AND unit_type = 'faculty'
UNION ALL SELECT 'orgunit_department', COUNT(*) FROM organizations_orgunit
 WHERE organization_id = (SELECT organization_id FROM scope) AND unit_type = 'department'
UNION ALL SELECT 'orgunit_specialty', COUNT(*) FROM organizations_orgunit
 WHERE organization_id = (SELECT organization_id FROM scope) AND unit_type = 'specialty'
UNION ALL SELECT 'orgunit_group', COUNT(*) FROM organizations_orgunit
 WHERE organization_id = (SELECT organization_id FROM scope) AND unit_type = 'group'
UNION ALL SELECT 'orgunit_total', COUNT(*) FROM organizations_orgunit
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'program', COUNT(*) FROM registrar_program
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'curriculum', COUNT(*) FROM registrar_curriculum
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'curriculum_subject', COUNT(*) FROM registrar_curriculumsubject
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'subject', COUNT(*) FROM registrar_subject
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'student_record', COUNT(*) FROM registrar_studentacademicrecord
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'course_offering', COUNT(*) FROM registrar_courseoffering
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'offering_no_instructor', COUNT(*) FROM registrar_courseoffering
 WHERE organization_id = (SELECT organization_id FROM scope) AND instructor_id IS NULL
UNION ALL SELECT 'enrollment', COUNT(*) FROM registrar_enrollment
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'lesson', COUNT(*) FROM registrar_lesson
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'lessonmark', COUNT(*) FROM registrar_lessonmark
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'lessonmark_scored', COUNT(*) FROM registrar_lessonmark
 WHERE organization_id = (SELECT organization_id FROM scope) AND score IS NOT NULL
UNION ALL SELECT 'lessonmark_present', COUNT(*) FROM registrar_lessonmark
 WHERE organization_id = (SELECT organization_id FROM scope) AND status = 'present'
UNION ALL SELECT 'lessonmark_absent', COUNT(*) FROM registrar_lessonmark
 WHERE organization_id = (SELECT organization_id FROM scope) AND status = 'absent'
UNION ALL SELECT 'lessonmark_excused', COUNT(*) FROM registrar_lessonmark
 WHERE organization_id = (SELECT organization_id FROM scope) AND status = 'excused'
UNION ALL SELECT 'componentscore', COUNT(*) FROM registrar_componentscore
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'componentscore_kollokvium', COUNT(*) FROM registrar_componentscore cs
    JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
   WHERE cs.organization_id = (SELECT organization_id FROM scope)
     AND ac.organization_id = (SELECT organization_id FROM scope) AND ac.kind = 'kollokvium'
UNION ALL SELECT 'componentscore_selfwork', COUNT(*) FROM registrar_componentscore cs
    JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
   WHERE cs.organization_id = (SELECT organization_id FROM scope)
     AND ac.organization_id = (SELECT organization_id FROM scope) AND ac.kind = 'self_work'
UNION ALL SELECT 'finalgrade', COUNT(*) FROM registrar_finalgrade
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'finalgrade_scored', COUNT(*) FROM registrar_finalgrade
 WHERE organization_id = (SELECT organization_id FROM scope) AND exam_score IS NOT NULL
UNION ALL SELECT 'resit_scored', COUNT(*) FROM registrar_resitrecord
 WHERE organization_id = (SELECT organization_id FROM scope) AND resit_score IS NOT NULL
UNION ALL SELECT 'membership', COUNT(*) FROM organizations_membership
 WHERE organization_id = (SELECT organization_id FROM scope)
UNION ALL SELECT 'membership_active', COUNT(*) FROM organizations_membership
 WHERE organization_id = (SELECT organization_id FROM scope) AND is_active
UNION ALL SELECT 'membership_inactive', COUNT(*) FROM organizations_membership
 WHERE organization_id = (SELECT organization_id FROM scope) AND NOT is_active
UNION ALL SELECT 'auth_user', COUNT(DISTINCT user_id) FROM organizations_membership
 WHERE organization_id = (SELECT organization_id FROM scope);
"""

MEMBERSHIP_BY_ROLE_SQL = """
WITH scope AS (SELECT %s::uuid AS organization_id)
SELECT r.name, COUNT(*) FILTER (WHERE m.is_active), COUNT(*) FILTER (WHERE NOT m.is_active)
  FROM organizations_membership m JOIN organizations_role r ON r.id = m.role_id
 WHERE m.organization_id = (SELECT organization_id FROM scope)
   AND r.organization_id = (SELECT organization_id FROM scope)
 GROUP BY r.name ORDER BY COUNT(*) DESC;
"""

# ── Keyfiyyət yoxlamaları ────────────────────────────────────────────────────

QUALITY_SQL = """
WITH scope AS (SELECT %s::uuid AS organization_id)
SELECT 'user_no_name', COUNT(DISTINCT u.id) FROM auth_user u
 WHERE (btrim(COALESCE(u.first_name, '')) = '' OR btrim(COALESCE(u.last_name, '')) = '')
   AND EXISTS (
       SELECT 1 FROM organizations_membership m
        WHERE m.user_id = u.id AND m.organization_id = (SELECT organization_id FROM scope)
   )
UNION ALL SELECT 'student_no_record', COUNT(DISTINCT m.user_id) FROM organizations_membership m
    JOIN organizations_role r ON r.id = m.role_id
   WHERE m.organization_id = (SELECT organization_id FROM scope)
     AND r.organization_id = (SELECT organization_id FROM scope) AND r.name = 'student'
     AND NOT EXISTS (
         SELECT 1 FROM registrar_studentacademicrecord sar
          WHERE sar.student_id = m.user_id AND sar.organization_id = (SELECT organization_id FROM scope)
     )
UNION ALL SELECT 'record_no_group', COUNT(*) FROM registrar_studentacademicrecord
 WHERE organization_id = (SELECT organization_id FROM scope) AND group_id IS NULL
UNION ALL SELECT 'offering_no_instructor', COUNT(*) FROM registrar_courseoffering
 WHERE organization_id = (SELECT organization_id FROM scope) AND instructor_id IS NULL
UNION ALL SELECT 'lesson_no_offering', COUNT(*) FROM registrar_lesson
 WHERE organization_id = (SELECT organization_id FROM scope) AND offering_id IS NULL
UNION ALL SELECT 'mark_orphan_enrollment', COUNT(*) FROM registrar_lessonmark lm
   WHERE lm.organization_id = (SELECT organization_id FROM scope)
     AND NOT EXISTS (SELECT 1 FROM registrar_enrollment e
          WHERE e.id = lm.enrollment_id AND e.organization_id = (SELECT organization_id FROM scope))
UNION ALL SELECT 'mark_orphan_lesson', COUNT(*) FROM registrar_lessonmark lm
   WHERE lm.organization_id = (SELECT organization_id FROM scope)
     AND NOT EXISTS (SELECT 1 FROM registrar_lesson l
          WHERE l.id = lm.lesson_id AND l.organization_id = (SELECT organization_id FROM scope))
UNION ALL SELECT 'score_orphan_component', COUNT(*) FROM registrar_componentscore cs
   WHERE cs.organization_id = (SELECT organization_id FROM scope)
     AND NOT EXISTS (SELECT 1 FROM registrar_assessmentcomponent ac
          WHERE ac.id = cs.component_id AND ac.organization_id = (SELECT organization_id FROM scope))
UNION ALL SELECT 'enrollment_dup', COUNT(*) FROM (
     SELECT offering_id, student_id FROM registrar_enrollment
      WHERE organization_id = (SELECT organization_id FROM scope)
      GROUP BY offering_id, student_id HAVING COUNT(*) > 1) d
UNION ALL SELECT 'record_dup', COUNT(*) FROM (
     SELECT student_id FROM registrar_studentacademicrecord
      WHERE organization_id = (SELECT organization_id FROM scope) AND is_active
      GROUP BY student_id HAVING COUNT(*) > 1) d2
UNION ALL SELECT 'subject_dup_name', COUNT(*) FROM (
     SELECT lower(name) FROM registrar_subject
      WHERE organization_id = (SELECT organization_id FROM scope)
      GROUP BY lower(name) HAVING COUNT(*) > 1) d3
UNION ALL SELECT 'offering_dup', COUNT(*) FROM (
     SELECT subject_id, group_id, period_id FROM registrar_courseoffering
      WHERE organization_id = (SELECT organization_id FROM scope)
      GROUP BY subject_id, group_id, period_id HAVING COUNT(*) > 1) d4
UNION ALL SELECT 'mark_dup', COUNT(*) FROM (
     SELECT enrollment_id, lesson_id FROM registrar_lessonmark
      WHERE organization_id = (SELECT organization_id FROM scope)
      GROUP BY enrollment_id, lesson_id HAVING COUNT(*) > 1) d5;
"""

# ── Yekun balı güzgüsü ───────────────────────────────────────────────────────

FINAL_MIRROR_SQL = """
WITH scope AS (SELECT %s::uuid AS organization_id)
SELECT e.id::text,
       COALESCE(lm.total, 0) AS lesson_sum,
       COALESCE(kk.total, 0) AS kollokvium_sum,
       fg.exam_score, COALESCE(fg.bonus, 0), rr.resit_score,
       COALESCE(sch.entry_score_max, 50)
  FROM registrar_enrollment e
  LEFT JOIN (SELECT enrollment_id, SUM(score) AS total FROM registrar_lessonmark
              WHERE organization_id = (SELECT organization_id FROM scope) AND score IS NOT NULL
              GROUP BY enrollment_id) lm ON lm.enrollment_id = e.id
  LEFT JOIN (SELECT cs.enrollment_id, SUM(cs.score) AS total FROM registrar_componentscore cs
               JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
              WHERE cs.organization_id = (SELECT organization_id FROM scope)
                AND ac.organization_id = (SELECT organization_id FROM scope)
                AND ac.kind = 'kollokvium' GROUP BY cs.enrollment_id) kk ON kk.enrollment_id = e.id
  LEFT JOIN registrar_finalgrade fg ON fg.enrollment_id = e.id
       AND fg.organization_id = (SELECT organization_id FROM scope)
  LEFT JOIN registrar_resitrecord rr ON rr.enrollment_id = e.id
       AND rr.organization_id = (SELECT organization_id FROM scope) AND rr.resit_score IS NOT NULL
  LEFT JOIN registrar_assessmentscheme sch ON sch.offering_id = e.offering_id
       AND sch.organization_id = (SELECT organization_id FROM scope)
 WHERE e.organization_id = (SELECT organization_id FROM scope) AND e.id::text = ANY(%s);
"""

# ── Nümunə-yoxlama ───────────────────────────────────────────────────────────

SAMPLE_IDENTITY_SQL = """
WITH scope AS (SELECT %s::uuid AS organization_id),
primary_membership AS (
    SELECT DISTINCT ON (m.user_id) m.user_id, m.is_active
      FROM organizations_membership m
     WHERE m.organization_id = (SELECT organization_id FROM scope) AND m.is_primary
     ORDER BY m.user_id, m.created_at, m.id
)
SELECT u.id, btrim(COALESCE(u.last_name, '') || ' ' || COALESCE(u.first_name, '')),
       COALESCE(g.name, ''), COALESCE(p.name, ''), COALESCE(sar.status, ''),
       COALESCE(m.is_active, false)
  FROM auth_user u
  JOIN primary_membership m ON m.user_id = u.id
  LEFT JOIN registrar_studentacademicrecord sar ON sar.student_id = u.id
       AND sar.organization_id = (SELECT organization_id FROM scope) AND sar.is_active
  LEFT JOIN organizations_orgunit g ON g.id = sar.group_id
       AND g.organization_id = (SELECT organization_id FROM scope)
  LEFT JOIN registrar_program p ON p.id = sar.program_id
       AND p.organization_id = (SELECT organization_id FROM scope)
 WHERE u.id = ANY(%s);
"""

SAMPLE_ENROLLMENT_SQL = """
WITH scope AS (SELECT %s::uuid AS organization_id)
SELECT e.student_id, e.id::text, s.name,
       COALESCE(mk.absent, 0), COALESCE(mk.excused, 0), COALESCE(mk.score_sum, 0),
       COALESCE(kk.total, 0), COALESCE(sw.total, 0),
       fg.exam_score, rr.resit_score, COALESCE(fg.bonus, 0),
       COALESCE(sch.entry_score_max, 50), e.status
  FROM registrar_enrollment e
  JOIN registrar_courseoffering co ON co.id = e.offering_id
       AND co.organization_id = (SELECT organization_id FROM scope)
  JOIN registrar_subject s ON s.id = co.subject_id
       AND s.organization_id = (SELECT organization_id FROM scope)
  LEFT JOIN (SELECT enrollment_id,
                    COUNT(*) FILTER (WHERE status = 'absent') AS absent,
                    COUNT(*) FILTER (WHERE status = 'excused') AS excused,
                    SUM(score) AS score_sum
               FROM registrar_lessonmark
              WHERE organization_id = (SELECT organization_id FROM scope)
              GROUP BY enrollment_id) mk ON mk.enrollment_id = e.id
  LEFT JOIN (SELECT cs.enrollment_id, SUM(cs.score) AS total FROM registrar_componentscore cs
               JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
              WHERE cs.organization_id = (SELECT organization_id FROM scope)
                AND ac.organization_id = (SELECT organization_id FROM scope)
                AND ac.kind = 'kollokvium' GROUP BY cs.enrollment_id) kk ON kk.enrollment_id = e.id
  LEFT JOIN (SELECT cs.enrollment_id, SUM(cs.score) AS total FROM registrar_componentscore cs
               JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
              WHERE cs.organization_id = (SELECT organization_id FROM scope)
                AND ac.organization_id = (SELECT organization_id FROM scope)
                AND ac.kind = 'self_work' GROUP BY cs.enrollment_id) sw ON sw.enrollment_id = e.id
  LEFT JOIN registrar_finalgrade fg ON fg.enrollment_id = e.id
       AND fg.organization_id = (SELECT organization_id FROM scope)
  LEFT JOIN registrar_resitrecord rr ON rr.enrollment_id = e.id
       AND rr.organization_id = (SELECT organization_id FROM scope) AND rr.resit_score IS NOT NULL
  LEFT JOIN registrar_assessmentscheme sch ON sch.offering_id = e.offering_id
       AND sch.organization_id = (SELECT organization_id FROM scope)
 WHERE e.organization_id = (SELECT organization_id FROM scope) AND e.student_id = ANY(%s);
"""

# ── Yazı təkrar-icrası (nərdivanın son iki pilləsi) ──────────────────────────
#
# Hər ikisi registrar cədvəllərinin ÖZÜNDƏN oxunur — ledger sayğacından deyil.
# Beləliklə pillə «hadisə» yox, MATERİALLAŞMIŞ hədəf ölçür.

# ⚠️ ``start_time IS NULL`` sətirlər SÜZÜLMÜR.  J12 bərpası saatı oxunmayan
# xana üçün dərsi ``start_time = NULL`` ilə yaradır (``legacy_lesson_synth_time_unknown``)
# və ona xanalar bağlanır; həmin dərslər süzülsəydi nərdivan hədəfdə MÖVCUD
# olan sətirləri «yazılmayıb» sayardı (ölçülüb: bərpa nüsxəsində 18 xana).
# Xananın öz saat açarı da oxunmayanda boş sətirdir — açar hər iki tərəfdə eyni.
LESSON_SLOT_SQL = """
SELECT DISTINCT l.offering_id::text,
       EXTRACT(MONTH FROM l.date)::int,
       EXTRACT(DAY FROM l.date)::int,
       COALESCE(to_char(l.start_time, 'HH24:MI'), ''),
       l.id::text
  FROM registrar_lesson l
 WHERE l.organization_id = %s::uuid;
"""

ENROLLMENT_OFFERING_SQL = """
SELECT e.id::text, e.offering_id::text
  FROM registrar_enrollment e
 WHERE e.organization_id = %s::uuid;
"""

# ── J12 bərpasının izi (1-ci pillənin «bərpadan sonra sıfır» proqnozu) ───────
#
# 1-ci pillə («dərs slotu MƏNBƏDƏ yoxdur») bərpanın hədəfidir: J12 xananın öz
# ``(ay, gün, saat)`` açarından dərsi yaradır, yəni slot xəritəsinə düşür və
# pillə boşalır.  Hesabat bunu FƏRZ ETMİR — hədəfdə bərpanın izi VARSA onu
# oxuyur və pilləni həmin izlə üzləşdirir.
#
# ⚠️ Sütun köhnə nüsxələrdə YOXDUR (miqrasiya ``registrar.0059``).  Ona görə
# əvvəlcə sxem soruşulur; sütun yoxdursa sayğac sorğusu ÜMUMİYYƏTLƏ göndərilmir
# (yoxsa bütöv hesabat ``UndefinedColumn`` ilə çökərdi).
# ⚠️ Sxem sorğusu da ATTESTASİYA olunmuş tenant-a bağlanır (``EXISTS``): hesabatın
# müqaviləsi «run attestasiyasından sonra HƏR sorğu təşkilat açarını daşıyır»
# invariantıdır (``test_legacy_reconcile_scope``), sxem probu da istisna deyil.
LESSON_SYNTH_COLUMN_SQL = """
SELECT COUNT(*)
  FROM information_schema.columns c
 WHERE c.table_schema = 'public'
   AND c.table_name = 'registrar_lesson'
   AND c.column_name = 'is_legacy_synthesised'
   AND EXISTS (SELECT 1 FROM organizations_organization o WHERE o.id = %s::uuid);
"""

LESSON_SYNTH_COUNT_SQL = """
SELECT COUNT(*) FILTER (WHERE l.is_legacy_synthesised) AS synthesised_lessons,
       COUNT(*) AS all_lessons
  FROM registrar_lesson l
 WHERE l.organization_id = %s::uuid;
"""

LESSON_SYNTH_MARK_SQL = """
SELECT COUNT(*)
  FROM registrar_lessonmark m
  JOIN registrar_lesson l ON l.id = m.lesson_id
 WHERE l.organization_id = %s::uuid
   AND m.organization_id = %s::uuid
   AND l.is_legacy_synthesised;
"""
