exec(open("/private/tmp/claude-501/-Users-elvin-Desktop-Programming-Folders-EMSArena-EMSArena/9bc7dd1d-6bb0-4ca3-b2c4-8c779904d299/scratchpad/e2e/sweep.py").read().split("PAT10 = ")[0])
ml=0; lit_ml=0; shown=0
for uid in uniqids:
    sections = tuple((table, tuple(distilled_section_row(pk, v) for pk, v in sorted(raw.get(table, {}).get(uid, [])))) for table in SYLLABUS_SECTION_CONTRACTS)
    doc = SyllabusDocument(header=SyllabusHeaderRow(legacy_pk=1,uniqid=uid,lesson_id=1,teacher_id=1,lesson_hours=45,language="az",active=True,issues=()),week=(),sections=sections)
    data,_ = build_section_data(doc)
    b = build_preview_blocks(data)
    if "\n" in data["assess"]["note"]: ml+=1
    if len(b[7]["body"].split("\n"))>1: lit_ml+=1
    if shown<1 and len(b[5]["body"].split("\n"))>4:
        print("SAMPLE uniqid",uid); print(b[5]["body"][:700]); shown=1
print("multiline assess notes:", ml, "| multi-entry literature blocks:", lit_ml)
