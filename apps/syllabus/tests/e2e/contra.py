import re

exec(open("/private/tmp/claude-501/-Users-elvin-Desktop-Programming-Folders-EMSArena-EMSArena/9bc7dd1d-6bb0-4ca3-b2c4-8c779904d299/scratchpad/e2e/sweep.py").read().split("PAT10 = ")[0])
from apps.syllabus.document import _WEIGHTS_UNSPECIFIED

UNS = str(_WEIGHTS_UNSPECIFIED)
zero_bal = 0; contra = 0; unspec = 0; note_only_ws = 0
BAL = re.compile(r"\(?\s*0?\s*[-–]?\s*\d+\s*bal")
for uid in uniqids:
    sections = tuple((table, tuple(distilled_section_row(pk, v) for pk, v in sorted(raw.get(table, {}).get(uid, [])))) for table in SYLLABUS_SECTION_CONTRACTS)
    doc = SyllabusDocument(header=SyllabusHeaderRow(legacy_pk=1,uniqid=uid,lesson_id=1,teacher_id=1,lesson_hours=45,language="az",active=True,issues=()),week=(),sections=sections)
    data,_ = build_section_data(doc)
    blocks = build_preview_blocks(data)
    whole = "\n".join(b["body"] for b in blocks)
    zero_bal += len(re.findall(r"\(0 bal\)", whole))
    a = blocks[5]["body"]
    if a.startswith(UNS):
        unspec += 1
        if BAL.search(a[len(UNS):]): contra += 1
print("literal '(0 bal)' occurrences:", zero_bal)
print("blocks starting with '%s': %d" % (UNS, unspec))
print("  ... of which the text below DOES state a bal split:", contra)
