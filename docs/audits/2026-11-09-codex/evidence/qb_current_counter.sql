-- NOT EXECUTED: fresh complete target/source closure and credit/reversal rows required.
-- Mirrors current gradebook_marks + guest_merge canonical hours; it does not authorize changing a cache.
-- Parameters: org_id UUID, period_id UUID. No academic policy/eligibility decision is inferred from drift.
WITH rows AS (
 SELECT e.*,o.subject_id,o.period_id,o.organization_id offering_org
 FROM registrar_enrollment e JOIN registrar_courseoffering o ON o.id=e.offering_id
 WHERE e.organization_id=%(org_id)s AND o.organization_id=%(org_id)s AND o.period_id=%(period_id)s
), raw AS (
 SELECT e.id,coalesce(sum(l.hours) FILTER(WHERE m.status='absent'),0) hours
 FROM rows e LEFT JOIN registrar_lessonmark m ON m.enrollment_id=e.id AND m.organization_id=%(org_id)s
 LEFT JOIN registrar_lesson l ON l.id=m.lesson_id AND l.organization_id=%(org_id)s
 GROUP BY e.id
), credit AS (
 SELECT c.enrollment_id,sum(c.hours) hours
 FROM registrar_absencecredit c JOIN rows e ON e.id=c.enrollment_id
 WHERE c.organization_id=%(org_id)s AND c.reverses_id IS NULL
 AND NOT EXISTS(SELECT 1 FROM registrar_absencecredit reversal WHERE reversal.reverses_id=c.id)
 GROUP BY c.enrollment_id
), carry AS (
 SELECT target.id,sum(greatest(0,source_raw.hours-coalesce(source_credit.hours,0))) hours
 FROM rows source JOIN rows target ON target.id=source.superseded_by_id
 JOIN raw source_raw ON source_raw.id=source.id
 LEFT JOIN credit source_credit ON source_credit.enrollment_id=source.id
 WHERE source.id<>target.id AND source.status='dropped'
 AND source.organization_id=target.organization_id AND source.student_id=target.student_id
 AND source.subject_id=target.subject_id AND source.period_id=target.period_id
 GROUP BY target.id
), result AS (
 SELECT e.id enrollment_id,e.student_id,e.offering_id,e.status,e.absence_hours cached_hours,
 raw.hours own_hours,coalesce(carry.hours,0) carry_hours,coalesce(credit.hours,0) active_credit_hours,
 greatest(0,raw.hours+coalesce(carry.hours,0)-coalesce(credit.hours,0)) derived_hours
 FROM rows e JOIN raw ON raw.id=e.id LEFT JOIN credit ON credit.enrollment_id=e.id LEFT JOIN carry ON carry.id=e.id
)
SELECT *,cached_hours-derived_hours cache_minus_canonical FROM result ORDER BY enrollment_id;
