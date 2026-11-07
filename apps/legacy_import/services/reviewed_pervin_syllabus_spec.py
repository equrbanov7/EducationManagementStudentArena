"""Two exact own-source syllabi; official45 and original60 remain distinct facts."""

import hashlib
import json
from pathlib import Path

SOURCE_SHA = "e67ab323b47b0c76e67350c80688b82bcf897b019b8af87be8ba15517a12e20b"
SOURCE_DIGEST = "992297a026616c6e60d3cc674625587c2b5694a123bb30b89f8e96f38125ab05"
JOURNAL_DIGEST = "2f4901d88300ad87604e50300fc63f880437f0e11212c65016f9a3498ce0e258"
BODY_SHA = "bb8057e402c5c5cc636733fc1079b9344e7fc9c87985427556f7a0fbe7788d3c"
RAW = Path(__file__).with_name("reviewed_pervin_syllabus_pins.json").read_bytes()
if hashlib.sha256(RAW).hexdigest() != "cb0aca3bc17ba690f75da323294ee8a7dddc7ce85d5d8edb15a3cb6d220c2449":
    raise ValueError("pervin_fixed_contract_changed")
PINS = json.loads(RAW)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
COURSES = tuple(PINS["offerings"])
RESOURCE = "legacy_import.reviewed_pervin_own60_v1"
NOTE = (
    "Müəllimin öz 2026/2027 Payız jurnalının birbaşa8573 mənbəsi dəyişmədən bərpa olunub. "
    "Orijinal sillabus: 30 mühazirə +30 seminar =60 saat; cari rəsmi yük:15 mühazirə +30 seminar =45 saat. "
    "Bu15saat uyğunsuzluğu saxlanılır; mövzu/saat kəsilməyib və cari yük artırılmayıb. "
    "Təsdiq explicit user reviewed own-source migration səlahiyyətidir; köhnə insan təsdiqi iddia edilmir."
)
