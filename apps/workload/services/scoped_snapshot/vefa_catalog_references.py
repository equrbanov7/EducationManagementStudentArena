"""Encrypted-only fixed Vefa14733 full graph; no additional capture workflow."""

from .. import reviewed_vefa_catalog_spec as spec
from .two_catalog_references import collect_two_catalog_references


def collect_vefa_catalog_references():
    return collect_two_catalog_references(contract=spec, prefix="vefa_catalog")
