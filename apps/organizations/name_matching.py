"""Locale-independent comparison for the faculty and kafedra registry."""

from contextlib import contextmanager

from django.db import IntegrityError, models, transaction
from django.db.models.functions import Collate
from django.utils.translation import pgettext

from core.constants import OrgUnitType

# Whitespace stripped by the registry forms (str.strip).
_TRIM_CHARS = (
    "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)
REGISTRY_NAME_CONSTRAINT = "orgunit_active_registry_name_uniq"


def registry_name_key(expression):
    # Azerbaijani has two separate letter pairs: İ/i and I/ı. NFC also
    # handles equivalent keyboard spellings before performing the case mapping.
    nfc = models.Func(
        models.Func(expression, models.Value(_TRIM_CHARS), function="BTRIM"),
        function="NORMALIZE",
        output_field=models.TextField(),
    )
    return Collate(models.Func(nfc, template='LOWER(%(expressions)s COLLATE "az-x-icu")'), "C")


def registry_name_constraint():
    # chair and department both represent kafedra in the registry.
    faculty = models.Case(models.When(unit_type=OrgUnitType.FACULTY, then=1), default=0)
    return models.UniqueConstraint(
        "organization",
        faculty,
        registry_name_key("name"),
        condition=models.Q(
            is_active=True, unit_type__in=(OrgUnitType.FACULTY, OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
        ),
        name=REGISTRY_NAME_CONSTRAINT,
    )


def name_exists(queryset, name):
    return (
        queryset.alias(registry_name=registry_name_key("name"))
        .filter(registry_name=registry_name_key(models.Value(name)))
        .exists()
    )


def is_registry_name_collision(exc):
    return getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) == REGISTRY_NAME_CONSTRAINT


class RegistryNameTaken(Exception):
    def __str__(self):
        return pgettext("organizations.registry", "Bu adda bölmə artıq var.")


@contextmanager
def registry_unit_write(organization):
    """Allocate names and slugs consistently across the registry and structure forms."""
    from .models import Organization

    try:
        with transaction.atomic():
            Organization.objects.select_for_update(no_key=True).only("pk").get(pk=organization.pk)
            yield
    except IntegrityError as exc:
        if is_registry_name_collision(exc):
            raise RegistryNameTaken() from exc
        raise
