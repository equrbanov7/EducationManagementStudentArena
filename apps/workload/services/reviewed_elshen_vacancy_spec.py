"""Source-backed vacancy correction; academic history is immutable."""

from . import reviewed_two_catalog_spec as common

PINS = common._load(
    "reviewed_elshen_vacancy_pins.json", "e962336e773f5c69dd463ba6638b6c22740ea8c8d5a982691ba86bc7a735bd34"
)
ORG = PINS["organization"]
SCHEMA = common.SCHEMA
FORMAT = "reviewed-elshen-vacancies/1"
RESOURCE = "workload.reviewed_elshen_vacancies_v1"
