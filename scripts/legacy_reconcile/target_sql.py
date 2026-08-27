"""Hədəf (PostgreSQL / EMS Arena) tərəfin OXU sorğuları.

Ledger cədvəlləri (``legacy_import_*``) mənbə ilə hədəf arasındakı KÖRPÜdür:
``legacy_pk`` → ``target_pk``.  Hesabat həmin körpünü oxuyur, amma sayları
ledger-dən DEYİL, registrar cədvəllərinin özündən götürür — iki müstəqil sübut
mənbəyi qarşılaşdırılsın deyə.
"""

from __future__ import annotations

# ── Ledger (sətir mühasibatı) ────────────────────────────────────────────────

LEDGER_STATE_SQL = """
SELECT entity_type, state, COUNT(*)
  FROM legacy_import_legacyentitymap
 GROUP BY entity_type, state
 ORDER BY entity_type, state;
"""

LEDGER_BATCH_SQL = """
SELECT entity_type, source_table, SUM(source_row_count), SUM(migrated_count),
       SUM(skipped_count), SUM(quarantined_count)
  FROM legacy_import_legacyimportbatch
 GROUP BY entity_type, source_table
 ORDER BY entity_type;
"""

LEDGER_ISSUE_SQL = """
SELECT source_table, rule_code, severity, COUNT(*)
  FROM legacy_import_legacymigrationissue
 GROUP BY source_table, rule_code, severity
 ORDER BY COUNT(*) DESC;
"""

RUN_SQL = """
SELECT mode, status, snapshot_sha256, source_row_count, started_at, finished_at,
       migrated_count, skipped_count, quarantined_count
  FROM legacy_import_legacymigrationrun
 ORDER BY created_at DESC
 LIMIT 1;
"""

MIGRATED_MAP_SQL = """
SELECT legacy_pk, target_pk
  FROM legacy_import_legacyentitymap
 WHERE entity_type = %s AND state = 'migrated' AND target_pk <> '';
"""

# ── Varlıq sayları (registrar/organizations cədvəllərindən birbaşa) ──────────

ENTITY_COUNTS_SQL = """
SELECT 'orgunit_faculty', COUNT(*) FROM organizations_orgunit WHERE unit_type = 'faculty'
UNION ALL SELECT 'orgunit_department', COUNT(*) FROM organizations_orgunit WHERE unit_type = 'department'
UNION ALL SELECT 'orgunit_specialty', COUNT(*) FROM organizations_orgunit WHERE unit_type = 'specialty'
UNION ALL SELECT 'orgunit_group', COUNT(*) FROM organizations_orgunit WHERE unit_type = 'group'
UNION ALL SELECT 'orgunit_total', COUNT(*) FROM organizations_orgunit
UNION ALL SELECT 'program', COUNT(*) FROM registrar_program
UNION ALL SELECT 'curriculum', COUNT(*) FROM registrar_curriculum
UNION ALL SELECT 'curriculum_subject', COUNT(*) FROM registrar_curriculumsubject
UNION ALL SELECT 'subject', COUNT(*) FROM registrar_subject
UNION ALL SELECT 'student_record', COUNT(*) FROM registrar_studentacademicrecord
UNION ALL SELECT 'course_offering', COUNT(*) FROM registrar_courseoffering
UNION ALL SELECT 'offering_no_instructor', COUNT(*) FROM registrar_courseoffering WHERE instructor_id IS NULL
UNION ALL SELECT 'enrollment', COUNT(*) FROM registrar_enrollment
UNION ALL SELECT 'lesson', COUNT(*) FROM registrar_lesson
UNION ALL SELECT 'lessonmark', COUNT(*) FROM registrar_lessonmark
UNION ALL SELECT 'lessonmark_scored', COUNT(*) FROM registrar_lessonmark WHERE score IS NOT NULL
UNION ALL SELECT 'lessonmark_present', COUNT(*) FROM registrar_lessonmark WHERE status = 'present'
UNION ALL SELECT 'lessonmark_absent', COUNT(*) FROM registrar_lessonmark WHERE status = 'absent'
UNION ALL SELECT 'lessonmark_excused', COUNT(*) FROM registrar_lessonmark WHERE status = 'excused'
UNION ALL SELECT 'componentscore', COUNT(*) FROM registrar_componentscore
UNION ALL SELECT 'componentscore_kollokvium', COUNT(*) FROM registrar_componentscore cs
    JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id WHERE ac.kind = 'kollokvium'
UNION ALL SELECT 'componentscore_selfwork', COUNT(*) FROM registrar_componentscore cs
    JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id WHERE ac.kind = 'self_work'
UNION ALL SELECT 'finalgrade', COUNT(*) FROM registrar_finalgrade
UNION ALL SELECT 'finalgrade_scored', COUNT(*) FROM registrar_finalgrade WHERE exam_score IS NOT NULL
UNION ALL SELECT 'resit_scored', COUNT(*) FROM registrar_resitrecord WHERE resit_score IS NOT NULL
UNION ALL SELECT 'membership', COUNT(*) FROM organizations_membership
UNION ALL SELECT 'membership_active', COUNT(*) FROM organizations_membership WHERE is_active
UNION ALL SELECT 'membership_inactive', COUNT(*) FROM organizations_membership WHERE NOT is_active
UNION ALL SELECT 'auth_user', COUNT(*) FROM auth_user;
"""

MEMBERSHIP_BY_ROLE_SQL = """
SELECT r.name, COUNT(*) FILTER (WHERE m.is_active), COUNT(*) FILTER (WHERE NOT m.is_active)
  FROM organizations_membership m JOIN organizations_role r ON r.id = m.role_id
 GROUP BY r.name ORDER BY COUNT(*) DESC;
"""

# ── Keyfiyyət yoxlamaları ────────────────────────────────────────────────────

QUALITY_SQL = """
SELECT 'user_no_name', COUNT(*) FROM auth_user
 WHERE btrim(COALESCE(first_name, '')) = '' OR btrim(COALESCE(last_name, '')) = ''
UNION ALL SELECT 'student_no_record', COUNT(*) FROM organizations_membership m
    JOIN organizations_role r ON r.id = m.role_id
   WHERE r.name = 'student'
     AND NOT EXISTS (SELECT 1 FROM registrar_studentacademicrecord sar WHERE sar.student_id = m.user_id)
UNION ALL SELECT 'record_no_group', COUNT(*) FROM registrar_studentacademicrecord WHERE group_id IS NULL
UNION ALL SELECT 'offering_no_instructor', COUNT(*) FROM registrar_courseoffering WHERE instructor_id IS NULL
UNION ALL SELECT 'lesson_no_offering', COUNT(*) FROM registrar_lesson WHERE offering_id IS NULL
UNION ALL SELECT 'mark_orphan_enrollment', COUNT(*) FROM registrar_lessonmark lm
   WHERE NOT EXISTS (SELECT 1 FROM registrar_enrollment e WHERE e.id = lm.enrollment_id)
UNION ALL SELECT 'mark_orphan_lesson', COUNT(*) FROM registrar_lessonmark lm
   WHERE NOT EXISTS (SELECT 1 FROM registrar_lesson l WHERE l.id = lm.lesson_id)
UNION ALL SELECT 'score_orphan_component', COUNT(*) FROM registrar_componentscore cs
   WHERE NOT EXISTS (SELECT 1 FROM registrar_assessmentcomponent ac WHERE ac.id = cs.component_id)
UNION ALL SELECT 'enrollment_dup', COUNT(*) FROM (
     SELECT offering_id, student_id FROM registrar_enrollment
      GROUP BY offering_id, student_id HAVING COUNT(*) > 1) d
UNION ALL SELECT 'record_dup', COUNT(*) FROM (
     SELECT student_id FROM registrar_studentacademicrecord WHERE is_active
      GROUP BY student_id HAVING COUNT(*) > 1) d2
UNION ALL SELECT 'subject_dup_name', COUNT(*) FROM (
     SELECT lower(name) FROM registrar_subject GROUP BY lower(name) HAVING COUNT(*) > 1) d3
UNION ALL SELECT 'offering_dup', COUNT(*) FROM (
     SELECT subject_id, group_id, period_id FROM registrar_courseoffering
      GROUP BY subject_id, group_id, period_id HAVING COUNT(*) > 1) d4
UNION ALL SELECT 'mark_dup', COUNT(*) FROM (
     SELECT enrollment_id, lesson_id FROM registrar_lessonmark
      GROUP BY enrollment_id, lesson_id HAVING COUNT(*) > 1) d5;
"""

# ── Yekun balı güzgüsü ───────────────────────────────────────────────────────

FINAL_MIRROR_SQL = """
SELECT e.id::text,
       COALESCE(lm.total, 0) AS lesson_sum,
       COALESCE(kk.total, 0) AS kollokvium_sum,
       fg.exam_score, COALESCE(fg.bonus, 0), rr.resit_score,
       COALESCE(sch.entry_score_max, 50)
  FROM registrar_enrollment e
  LEFT JOIN (SELECT enrollment_id, SUM(score) AS total FROM registrar_lessonmark
              WHERE score IS NOT NULL GROUP BY enrollment_id) lm ON lm.enrollment_id = e.id
  LEFT JOIN (SELECT cs.enrollment_id, SUM(cs.score) AS total FROM registrar_componentscore cs
               JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
              WHERE ac.kind = 'kollokvium' GROUP BY cs.enrollment_id) kk ON kk.enrollment_id = e.id
  LEFT JOIN registrar_finalgrade fg ON fg.enrollment_id = e.id
  LEFT JOIN registrar_resitrecord rr ON rr.enrollment_id = e.id AND rr.resit_score IS NOT NULL
  LEFT JOIN registrar_assessmentscheme sch ON sch.offering_id = e.offering_id
 WHERE e.id::text = ANY(%s);
"""

# ── Nümunə-yoxlama ───────────────────────────────────────────────────────────

SAMPLE_IDENTITY_SQL = """
SELECT u.id, btrim(COALESCE(u.last_name, '') || ' ' || COALESCE(u.first_name, '')),
       COALESCE(g.name, ''), COALESCE(p.name, ''), COALESCE(sar.status, ''),
       COALESCE(m.is_active, false)
  FROM auth_user u
  LEFT JOIN registrar_studentacademicrecord sar ON sar.student_id = u.id AND sar.is_active
  LEFT JOIN organizations_orgunit g ON g.id = sar.group_id
  LEFT JOIN registrar_program p ON p.id = sar.program_id
  LEFT JOIN organizations_membership m ON m.user_id = u.id AND m.is_primary
 WHERE u.id = ANY(%s);
"""

SAMPLE_ENROLLMENT_SQL = """
SELECT e.student_id, e.id::text, s.name,
       COALESCE(mk.absent, 0), COALESCE(mk.excused, 0), COALESCE(mk.score_sum, 0),
       COALESCE(kk.total, 0), COALESCE(sw.total, 0),
       fg.exam_score, rr.resit_score, COALESCE(fg.bonus, 0),
       COALESCE(sch.entry_score_max, 50), e.status
  FROM registrar_enrollment e
  JOIN registrar_courseoffering co ON co.id = e.offering_id
  JOIN registrar_subject s ON s.id = co.subject_id
  LEFT JOIN (SELECT enrollment_id,
                    COUNT(*) FILTER (WHERE status = 'absent') AS absent,
                    COUNT(*) FILTER (WHERE status = 'excused') AS excused,
                    SUM(score) AS score_sum
               FROM registrar_lessonmark GROUP BY enrollment_id) mk ON mk.enrollment_id = e.id
  LEFT JOIN (SELECT cs.enrollment_id, SUM(cs.score) AS total FROM registrar_componentscore cs
               JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
              WHERE ac.kind = 'kollokvium' GROUP BY cs.enrollment_id) kk ON kk.enrollment_id = e.id
  LEFT JOIN (SELECT cs.enrollment_id, SUM(cs.score) AS total FROM registrar_componentscore cs
               JOIN registrar_assessmentcomponent ac ON ac.id = cs.component_id
              WHERE ac.kind = 'self_work' GROUP BY cs.enrollment_id) sw ON sw.enrollment_id = e.id
  LEFT JOIN registrar_finalgrade fg ON fg.enrollment_id = e.id
  LEFT JOIN registrar_resitrecord rr ON rr.enrollment_id = e.id AND rr.resit_score IS NOT NULL
  LEFT JOIN registrar_assessmentscheme sch ON sch.offering_id = e.offering_id
 WHERE e.student_id = ANY(%s);
"""
