"""Official Tarix row39, three contacts, two genuine seminar teachers."""

from . import reviewed_two_catalog_spec as common

SCHEMA = common.SCHEMA
PINS = common._load("reviewed_history636_pins.json", "c25893adc1d1b901c4dc657ed21c3f9a335cf5ff71a286d1d8270fc326f2c638")
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
FORMAT = "reviewed-history636-partition/1"
RESOURCE = "workload.reviewed_history636_partition_v1"
