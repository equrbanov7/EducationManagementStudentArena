"""One teacher-authoritative522h allocation; all released capacities remain vacant."""

from . import reviewed_two_catalog_spec as common

PINS = common._load("reviewed_kamile_pins.json", "c63b32b4e385fdd1831484b46c752d0da1327666988cc97e104202849a191c0a")
ORG = PINS["organization_id"]
SCHEMA = common.SCHEMA
FORMAT = "reviewed-kamile-source522/1"
RESOURCE = "workload.reviewed_kamile_source522_v1"
