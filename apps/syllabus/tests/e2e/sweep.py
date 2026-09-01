import base64
import collections
import os
import re
import sys

sys.path.insert(0, "/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/sweep.sqlite3")
import django; django.setup()

from apps.legacy_import.services.rehearsal_syllabus_documents import SyllabusDocument
from apps.legacy_import.services.rehearsal_syllabus_source import SyllabusHeaderRow, distilled_section_row
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS
from apps.syllabus.document import build_preview_blocks

D = os.path.dirname(os.path.abspath(__file__))
TABLES = ["sillabus_yoxlama_formasi","sillabus_imtahan_suallari","sillabus_serbest_is",
          "sillabus_derslikler","sillabus_tesviri_ve_meqsedi","sillabus_eldeolunacaq_tecrubeler",
          "sillabus_dersin_islenme_formasi"]
raw = {t: collections.defaultdict(list) for t in TABLES}
for t in TABLES:
    with open(os.path.join(D, t + ".tsv"), encoding="utf-8") as fh:
        for line in fh:
            pk, uniqid, b64 = line.rstrip("\n").split("\t")
            val = bytes.fromhex(b64).decode("utf-8", "replace") if b64 not in ("NULL","") else ""
            raw[t][uniqid].append((int(pk), val))

uniqids = sorted(set().union(*[set(raw[t]) for t in TABLES]))
print("uniqids:", len(uniqids))

PAT10 = re.compile(r"10 \+ 10")
PAT_SPLIT = re.compile(r"\d+ \+ \d+ \+ \d+ \+ \d+ \+ \d+ = ")
PAT_ZERO = re.compile(r"\(0 ")
hits10 = hits_split = hits_zero = 0
note_reached = note_present = 0
q_present = q_reached = 0
empty_assess = 0
samples = []
for uid in uniqids:
    sections = tuple(
        (table, tuple(distilled_section_row(pk, v) for pk, v in sorted(raw.get(table, {}).get(uid, []))))
        for table in SYLLABUS_SECTION_CONTRACTS
    )
    doc = SyllabusDocument(
        header=SyllabusHeaderRow(legacy_pk=1, uniqid=uid, lesson_id=1, teacher_id=1,
                                 lesson_hours=45, language="az", active=True, issues=()),
        week=(), sections=sections)
    data, codes = build_section_data(doc)
    blocks = build_preview_blocks(data)
    whole = "\n".join(b["body"] for b in blocks)
    assess_body = blocks[5]["body"]
    self_body = blocks[6]["body"]
    if PAT10.search(whole): hits10 += 1
    if PAT_SPLIT.search(whole): hits_split += 1
    if PAT_ZERO.search(whole): hits_zero += 1
    note = data["assess"]["note"]
    if note:
        note_present += 1
        if note.split("\n")[0] and note.split("\n")[0] in assess_body:
            note_reached += 1
        elif len(samples) < 3:
            samples.append((uid, note[:200], assess_body[:200]))
    q = data["assess"]["exam_questions"]
    if q:
        q_present += 1
        if all(x in assess_body for x in q): q_reached += 1
    if assess_body.strip().startswith("—"): empty_assess += 1

print("assess note present:", note_present, "reached student:", note_reached)
print("exam questions present:", q_present, "fully reached:", q_reached)
print("BLOCKER '10 + 10':", hits10)
print("BLOCKER any 5-term split:", hits_split)
print("BLOCKER '(0 ':", hits_zero)
print("empty assessment block:", empty_assess)
for s in samples: print("MISMATCH", s)
