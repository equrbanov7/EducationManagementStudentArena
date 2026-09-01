exec(open("/private/tmp/claude-501/-Users-elvin-Desktop-Programming-Folders-EMSArena-EMSArena/9bc7dd1d-6bb0-4ca3-b2c4-8c779904d299/scratchpad/e2e/sweep.py").read().split("PAT10 = ")[0])
para=0; lost=0
for uid in uniqids:
    sections = tuple((table, tuple(distilled_section_row(pk, v) for pk, v in sorted(raw.get(table, {}).get(uid, [])))) for table in SYLLABUS_SECTION_CONTRACTS)
    doc = SyllabusDocument(header=SyllabusHeaderRow(legacy_pk=1,uniqid=uid,lesson_id=1,teacher_id=1,lesson_hours=45,language="az",active=True,issues=()),week=(),sections=sections)
    data,_ = build_section_data(doc)
    n = data["assess"]["note"]
    if "\n\n" in n:
        para+=1
        if "\n\n" not in build_preview_blocks(data)[5]["body"]: lost+=1
print("assess notes with a preserved paragraph break:", para, "| break gone in reader:", lost)
