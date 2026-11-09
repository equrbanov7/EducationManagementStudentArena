"""Current dossier bodies and their exact donor lineage; global metadata stays complete."""

from django.db.models.expressions import RawSQL

POLICY = "current-period-all-offerings-nonarchived-and-referenced-lineage/1"


def version_ids(organization, period):
    """Keep all resolver candidates, including inactive journals and old referenced donors.

    Historical dossier/version/share metadata is exported separately without this
    projection. Unreferenced archived section bodies cannot affect current readers;
    native syllabus repair still locks and fingerprints every revision before writes.
    UNION (not UNION ALL) makes the traversal terminate even on corrupt cyclic lineage.
    """
    return RawSQL(
        """
        WITH RECURSIVE
        dossiers AS (
            SELECT * FROM syllabus_syllabus WHERE organization_id = %s
        ), versions AS (
            SELECT * FROM syllabus_syllabusversion WHERE organization_id = %s
        ), courses AS (
            SELECT * FROM registrar_courseoffering WHERE organization_id = %s AND period_id = %s
        ), roots AS (
            SELECT s.id FROM dossiers s WHERE
                s.period_id = %s OR s.offering_id IN (SELECT id FROM courses)
                OR EXISTS (SELECT 1 FROM courses c
                           WHERE c.subject_id = s.subject_id AND c.instructor_id = s.author_id)
                OR s.id IN (SELECT syllabus_id FROM syllabus_syllabusshare
                            WHERE organization_id = %s AND offering_id IN (SELECT id FROM courses))
                OR s.offering_id IN (SELECT source_offering_id FROM registrar_languagelevelcohort
                                    WHERE organization_id = %s AND offering_id IN (SELECT id FROM courses))
        ), edges(kind, id, next_kind, next_id) AS (
            SELECT 's', id, 's', reused_from_id FROM dossiers WHERE reused_from_id IS NOT NULL
            UNION ALL SELECT 's', id, 'v', current_version_id FROM dossiers WHERE current_version_id IS NOT NULL
            UNION ALL SELECT 's', id, 'v', approved_version_id FROM dossiers WHERE approved_version_id IS NOT NULL
            UNION ALL SELECT 's', syllabus_id, 'v', id FROM versions
            UNION ALL SELECT 'v', id, 's', syllabus_id FROM versions
            UNION ALL SELECT 'v', id, 'v', source_version_id FROM versions WHERE source_version_id IS NOT NULL
        ), reachable(kind, id) AS (
            SELECT 's'::text, id FROM roots
            UNION
            SELECT e.next_kind, e.next_id FROM edges e JOIN reachable r ON e.kind = r.kind AND e.id = r.id
        )
        SELECT v.id FROM versions v
        WHERE EXISTS (SELECT 1 FROM reachable r WHERE r.kind = 'v' AND r.id = v.id)
          AND (v.status <> 'archived'
               OR EXISTS (SELECT 1 FROM dossiers s
                          WHERE s.current_version_id = v.id OR s.approved_version_id = v.id)
               OR EXISTS (SELECT 1 FROM versions child JOIN reachable r ON r.kind = 'v' AND r.id = child.id
                          WHERE child.source_version_id = v.id))
        """,
        (organization, organization, organization, period, period, organization, organization),
    )
