"""One reviewed teacher, four autumn groups; never a generic alias/import API."""

import hashlib
import json
from pathlib import Path

_raw = Path(__file__).with_name("reviewed_solmaz_pins.json").read_bytes()
if hashlib.sha256(_raw).hexdigest() != "e42e18559e19f9b2f845b3ce61e28be5f2b97037dc23c543c95c1847d2fb3cf7":
    raise ValueError("solmaz_compiled_scope_changed")
PINS = json.loads(_raw)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
TEACHER = PINS["teacher_id"]
RESOURCE = "legacy_import.reviewed_solmaz_catalog"
ROW = "e6ee5a21-e700-49cb-99f5-56f8c6379ec4"
ASSIGNMENT = "2184bb8d-fd14-4618-8cda-1bc9fb3c38fe"
COURSE = "8007c2af-0eaa-4094-b768-df71f6c8c4e4"
CORRECT_SUBJECT = "98600bfe-0a86-41e1-8481-73cc56b36250"
SOURCE_COURSE = "32918162-6daa-4df4-91b6-710eb83d980c"
SOURCE_SYLLABUS = "5a0da1e1-4da3-48f4-836e-dea263fed189"
DRAFT = "5ad39977-e79f-43ab-bc37-85bb1f94ee4a"
DONOR = "6f8627ee-b139-4463-9727-f76fb92d2ec1"
DONOR_VERSION = "11ac77f8-2d3f-4b7e-bf42-cfc85e374e02"
SHARES = {"7df6476e-a7aa-40ef-98a8-09a05fe51684": SOURCE_SYLLABUS, COURSE: DONOR}
ROW_CHANGE = {"subject_id": CORRECT_SUBJECT, "union_count": 0, "lecture_total": 0, "total_hours": 30}
GROUP_SOURCES = {
    737: "bf9986dc-1366-4a42-8ba0-f9e7636ec78c",
    738: "aba7f830-e116-4d2f-b0c6-e165da2bd495",
    812: "3e4c8e6c-4049-44cd-a0fe-7d79c02a1a97",
    813: "646c17d7-9b3b-4ac2-8d19-bb262842f5c4",
}
SUBJECT_SOURCES = {
    2075: "254b82d3-dce2-4667-b73b-14eb7ea65dd0",
    2076: CORRECT_SUBJECT,
    2078: "3e8f0362-3762-4975-a060-3dcb026fa9e1",
}
