"""Review the whole reachable relation schema, including currently empty tables."""

from .reviewed_leyla_catalog_graph import digest, model

ROOTS = ("registrar.CourseOffering", "workload.TeachingTaskRow", "syllabus.Syllabus")


def fingerprints():
    pending, result = set(ROOTS), {}
    while pending:
        label = pending.pop()
        if label in result:
            continue
        cls = model(label)
        concrete = []
        for field in cls._meta.concrete_fields:
            concrete.append(
                (
                    field.attname,
                    field.get_internal_type(),
                    field.null,
                    field.primary_key,
                    field.related_model._meta.label if field.is_relation else None,
                    field.target_field.attname if field.is_relation else None,
                )
            )
        reverse = []
        for rel in cls._meta.get_fields(include_hidden=True):
            child = rel.related_model
            if rel.auto_created and not rel.concrete and child is not None:
                reverse.append(
                    (
                        child._meta.label,
                        rel.field.name if rel.many_to_many else rel.field.attname,
                        rel.many_to_many,
                        rel.hidden,
                    )
                )
                pending.add(child._meta.label)
        result[label] = digest({"fields": sorted(concrete), "reverse": sorted(reverse)})
    return dict(sorted(result.items()))
