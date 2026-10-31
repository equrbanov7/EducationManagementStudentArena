"""Pinned teacher318 source: journals14855/14873 both used own syllabus6591."""

import hashlib
import json
from pathlib import Path

from apps.workload.public import ModellingError

from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data

SOURCE_SHA = "de8001e6a3a31bb3bc98762959c5f8106aa49fc4b667a8102a9e0c442d58e055"


def load(path):
    raw = Path(path).read_bytes()
    if len(raw) > 2000000 or hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ModellingError("pinned_source_package_changed")
    data = json.loads(raw)
    if data["format"] != "qosqar-own-source-evidence/1":
        raise ModellingError("source_format_changed")
    journals = {j["id"]: j for j in data["journals"]}
    for jid, lesson, group in ((14855, 1797, 597), (14873, 868, 601)):
        j = journals[jid]
        if (
            j["teacher_id"],
            j["lesson_id"],
            j["semestr"],
            j["sillabus_id"],
            j["fenn_saati"],
            json.loads(j["groups_id"]),
        ) != (318, lesson, 14, 6591, 90, [str(group)]):
            raise ModellingError("source_journal_identity_changed")
    source = data["unique_sources"]["6591"]
    if (source["id"], source["teacher_id"], source["lesson_id"], source["ders_saati"], source["active"]) != (
        6591,
        318,
        868,
        90,
        1,
    ):
        raise ModellingError("source_own_syllabus_changed")
    sections, codes = build_section_data(document_for(source))
    if TEXT_TRUNCATED in codes or tuple(
        sum(r.get(k, 0) for r in sections["week"]["rows"]) for k in ("lecture", "seminar", "practical", "lab")
    ) != (45, 45, 0, 0):
        raise ModellingError("source_content_or_hours_changed")
    return sections, SOURCE_SHA
