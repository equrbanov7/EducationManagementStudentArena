"""One official30L30S stream, three existing journals, credits/payment status held."""

from . import reviewed_two_catalog_spec as common

PINS = common._load(
    "reviewed_asef_stream_pins.json", "1c690dd82d12b02e6152259e09c53bba0577a2a2ad5a11126beda9a6dab83edc"
)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
TEACHER = PINS["teacher"]
KEEPER = PINS["keeper"]
DUPLICATE = PINS["duplicate"]
SCHEMA = common.SCHEMA
RESOURCE = "workload.reviewed_asef_stream_v1"
PLAN = {"lecture": 30, "seminar": 30}
