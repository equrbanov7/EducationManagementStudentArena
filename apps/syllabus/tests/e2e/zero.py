import re
import sys

exec(open("/private/tmp/claude-501/-Users-elvin-Desktop-Programming-Folders-EMSArena-EMSArena/9bc7dd1d-6bb0-4ca3-b2c4-8c779904d299/scratchpad/e2e/sweep.py").read().split("PAT10 = ")[0])
PAT_ZERO = re.compile(r"\(0 ")
from collections import Counter

c = Counter(); ex = []
for uid in uniqids:
    sections = tuple((table, tuple(distilled_section_row(pk, v) for pk, v in sorted(raw.get(table, {}).get(uid, [])))) for table in SYLLABUS_SECTION_CONTRACTS)
    doc = SyllabusDocument(header=SyllabusHeaderRow(legacy_pk=1,uniqid=uid,lesson_id=1,teacher_id=1,lesson_hours=45,language="az",active=True,issues=()),week=(),sections=sections)
    data,_ = build_section_data(doc)
    for b in build_preview_blocks(data):
        for m in PAT_ZERO.finditer(b["body"]):
            c[str(b["title"])] += 1
            if len(ex) < 6: ex.append((str(b["title"]), b["body"][max(0,m.start()-90):m.start()+60]))
print(c)
for t,s in ex: print("---",t,"::",repr(s))
