-- NOT EXECUTED: verified fresh PostgreSQL source and complete Nov8 group fields required.
-- Parameters: org_id UUID, period_id UUID, as_of_date DATE. Run inside an already read-only transaction.
-- Own physical journal lessons, ENROLLED roster; actor UI scope is not an all-org denominator.
WITH offerings AS (
 SELECT id,is_active FROM registrar_courseoffering
 WHERE organization_id=%(org_id)s AND period_id=%(period_id)s
), roster AS (
 SELECT e.id,e.offering_id,e.lab_group,e.seminar_group
 FROM registrar_enrollment e JOIN offerings o ON o.id=e.offering_id
 WHERE e.organization_id=%(org_id)s AND e.status='enrolled'
), lessons AS (
 SELECT l.id,l.offering_id,l.date,l.lab_group,l.seminar_group
 FROM registrar_lesson l JOIN offerings o ON o.id=l.offering_id
 WHERE l.organization_id=%(org_id)s
), grid AS (
 SELECT e.offering_id,e.id enrollment_id,l.id lesson_id,l.date,
   ((l.lab_group IS NULL OR l.lab_group=e.lab_group)
    AND (l.seminar_group IS NULL OR l.seminar_group=e.seminar_group)) IS TRUE applicable,
   EXISTS(SELECT 1 FROM registrar_lessonmark m
     WHERE m.organization_id=%(org_id)s AND m.enrollment_id=e.id AND m.lesson_id=l.id) filled
 FROM roster e JOIN lessons l ON l.offering_id=e.offering_id
), counts AS (
 SELECT offering_id,count(*) structural,
   count(*) FILTER(WHERE applicable) applicable,
   count(*) FILTER(WHERE NOT applicable) off_group,
   count(*) FILTER(WHERE applicable AND filled) filled,
   count(*) FILTER(WHERE applicable AND NOT filled) blank,
   count(*) FILTER(WHERE applicable AND NOT filled AND date>%(as_of_date)s) future_blank,
   count(*) FILTER(WHERE NOT applicable AND filled) off_group_filled
 FROM grid GROUP BY offering_id
), rosters AS (SELECT offering_id,count(*) n FROM roster GROUP BY offering_id),
lesson_counts AS (SELECT offering_id,count(*) n FROM lessons GROUP BY offering_id)
SELECT o.id offering_id,o.is_active,coalesce(r.n,0) enrolled_count,coalesce(l.n,0) lesson_count,
 coalesce(c.structural,0) structural,coalesce(c.applicable,0) applicable,
 coalesce(c.off_group,0) off_group,coalesce(c.filled,0) filled,coalesce(c.blank,0) blank,
 coalesce(c.future_blank,0) future_blank,coalesce(c.off_group_filled,0) off_group_filled
FROM offerings o LEFT JOIN counts c ON c.offering_id=o.id
LEFT JOIN rosters r ON r.offering_id=o.id LEFT JOIN lesson_counts l ON l.offering_id=o.id
ORDER BY o.id;
