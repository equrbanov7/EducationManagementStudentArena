"""Boş legacy qiymətləndirmə konfiqurasiyası saxlanılır; yazılmış tarixçə gizlədilmir."""

from django.core.exceptions import ValidationError

from . import ke233_alias_spec as spec
from . import ke233_alias_state as state


def component_ids():
    return (
        state.model("registrar.AssessmentComponent")
        .objects.filter(
            organization_id=spec.ORG,
            offering_id__in=[item[key] for item in spec.COLLISIONS for key in ("source", "target")],
        )
        .values_list("pk", flat=True)
    )


def references(ids, *, lock=False):
    """Yeni reverse relation da avtomatik bloklanır; soft-deleted tarixçə də gizlənmir."""
    result = {}
    for relation in state.model("registrar.AssessmentComponent")._meta.get_fields(include_hidden=True):
        if not relation.auto_created or relation.concrete or not relation.related_model:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        key = f"{relation.related_model._meta.label}.{field.name}"
        result[key] = state.records(relation.related_model._base_manager.filter(**{f"{lookup}__in": ids}), lock=lock)
    return result


def validate_collision(item):
    """Heç nə köçürmür: original komponent/sxem ID-si və bütün dəyərlər öz FK-sində qalır."""
    components = list(
        state.model("registrar.AssessmentComponent").objects.filter(
            organization_id=spec.ORG, offering_id=item["source"]
        )
    )
    if not components:
        return
    for key, rows in references([component.pk for component in components]).items():
        if rows:
            raise state.RepairError("collision_component_has_history_" + key.replace(".", "_").lower())
    target = (
        state.model("registrar.AssessmentScheme")
        .objects.filter(organization_id=spec.ORG, offering_id=item["target"])
        .first()
    )
    if target is None:
        raise state.RepairError("collision_component_target_scheme_missing")
    # Targetin öz qiymətləndirmə siyasəti qalır: onun mövcud jurnalı yeni boş legacy
    # komponentlərlə qarışdırılmır. Mənbənin fərqli ad/çəki/rubrikası silinmir.
    try:
        target.full_clean()
        for component in components:
            component.full_clean()
    except ValidationError:
        raise state.RepairError("collision_component_configuration_invalid") from None
