"""Find the role's permitted practical lessons for a shown menu chapter."""

EXTERNAL = {
    "external-language": ("language-cohort", "language-group-create"),
    "external-journal": ("journal-entry", "locked-mark", "missing-journal", "laborant-journal", "laborant-components"),
    "external-rooms": ("room-monitor",),
    "external-seals": ("sealed-register",),
    "faq": ("faq-video-editor",),
}
PRACTICAL = {
    "my-subjects": ("student-material", "student-syllabus", "grades"),
    "my-subject-folders": ("student-material", "homework"),
    "my-results": ("grades", "grade-reconciliation", "request-transcript"),
    "my-journal": ("journal-limit", "student-journal-correction"),
    "my-schedule": ("schedule-excel-personal",),
    "unit-subject-folders": ("laborant-department",),
    "lab-groups": ("lab-group-create", "laborant-department"),
    "syllabus-list": ("student-syllabus", "laborant-department"),
}


def linked_lessons(role, chapter, model):
    if not chapter.get("menu") or role not in model["roles"]:
        return []
    section = chapter["section"]
    allowed = set(model["roles"][role]["ids"])
    guides = {g["key"]: g for g in model["guides"] if g["key"] in allowed}
    preferred = list(PRACTICAL.get(section, ())) + list(EXTERNAL.get(section, ()))
    if role == "lab_assistant" and section == "external-journal":
        preferred = ["laborant-journal", "laborant-components"] + preferred
    preferred += [
        g["key"] for g in guides.values() if g.get("section") == section and not g["key"].startswith("section-")
    ]
    preferred += [chapter.get("guide")]
    seen_videos = set()
    result = []
    for key in preferred:
        if key not in guides:
            continue
        guide = guides[key]
        marker = (guide["video"], guide["start"])
        if marker in seen_videos:
            continue
        seen_videos.add(marker)
        result.append({"key": key, "title": guide["title"]})
    return result
