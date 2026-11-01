"""Metadata-only projection of bounded academic reverse graphs."""

from ..reviewed_leyla_catalog_graph import digest, model

LIFECYCLE = {"is_active", "status", "state", "version_number"}


def _relations(cls):
    return [
        {
            "field": field.attname,
            "target": field.related_model._meta.label,
            "target_field": field.target_field.attname,
            "nullable": field.null,
        }
        for field in cls._meta.concrete_fields
        if field.is_relation and field.related_model is not None
    ]


def reference_metadata(rows, *, named_offerings=(), allowed_named=()):
    Offering = model("registrar.CourseOffering")
    named_enrollments = {
        row["id"] for row in rows.get("registrar.Enrollment", []) if row["offering_id"] in named_offerings
    }
    output = []
    for label, values in rows.items():
        cls = model(label)
        relations = _relations(cls)
        offering_fields = [r["field"] for r in relations if r["target"] == Offering._meta.label]
        identities = []
        for row in values:
            identity = {
                "pk": row[cls._meta.pk.attname],
                "fk": {r["field"]: row[r["field"]] for r in relations},
                "lifecycle": {key: row[key] for key in LIFECYCLE if key in row},
                "row_sha256": digest(row),
                "named_reference_hold": label not in allowed_named
                and any(row.get(field) in named_offerings for field in offering_fields),
                "named_enrollment_content_hold": row.get("enrollment_id") in named_enrollments,
            }
            identities.append(identity)
        reverse = [
            {
                "child": rel.related_model._meta.label,
                "field": rel.field.name if rel.many_to_many else rel.field.attname,
                "hidden": rel.hidden,
                "many_to_many": rel.many_to_many,
            }
            for rel in cls._meta.get_fields(include_hidden=True)
            if rel.auto_created and not rel.concrete and rel.related_model is not None
        ]
        output.append(
            {
                "model": label,
                "count": len(values),
                "sha256": digest(values),
                "relations": relations,
                "reverse_relations": reverse,
                "rows": identities,
            }
        )
    return output
