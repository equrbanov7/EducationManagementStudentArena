"""Official Tarix row39, three contacts, two genuine seminar teachers."""

from . import reviewed_two_catalog_spec as common

SCHEMA = common.SCHEMA
PINS = common._load("reviewed_history636_pins.json", "a8c893317105bc075cd9ecf89cec758baa7932e1476cc67c5d859514c48e0350")
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
FORMAT = "reviewed-history636-partition/1"
RESOURCE = "workload.reviewed_history636_partition_v1"
