"""One exact legacy-source fallback after official-source batches; load FK only."""

from ...services import reviewed_vefa_catalog_spec as spec
from .repair_reviewed_two_catalog import Command as LoadCommand


class Command(LoadCommand):
    help = "Only Vefa234KE source14733 load FK; preserve credits, all cells, original exam graph and source6138 body."
    contract = spec
    resource = spec.RESOURCE
    prefix = "reviewed_vefa_catalog"
