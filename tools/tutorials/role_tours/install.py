"""Install completed role tours and the dedicated lab operations into the private FAQ catalogue."""

import json
import shutil
from pathlib import Path

from .recorded_permissions import chapter_flags
from .related import linked_lessons
from .render import webvtt

ROOT = Path(__file__).resolve().parents[3]
MASTERS = ROOT / "tools/tutorials/out"
PROFILE = ROOT / "apps/accounts/views/profile"
MEDIA = ROOT / "apps/accounts/guide_media"

ADDITIONAL = {
    "laborant-journal": "L01-01-laborant-jurnal",
    "laborant-department": "L01-02-laborant-kafedra",
    "laborant-components": "L01-03-laborant-komponentler",
    "faq-video-editor": "RIM-FAQ-video-redaktor",
    "journal-watch": "RIM-02-journal-watch",
}


def replace_json(path, data):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(path)


def required_flags(role, sections, model, example, chapters):
    # The tour is a single seekable file. A later restriction on a demonstrated
    # operation must close the whole file, even if its sidebar section remains.
    permitted = set(model["roles"][role]["ids"])
    candidate_sections = set(sections)
    if "external-journal" in candidate_sections:
        candidate_sections.add("my-journal")
    linked = {link["key"] for chapter in chapters for link in chapter.get("related", ())}
    flags = {
        flag
        for guide in model["guides"]
        if guide["key"] in permitted and (guide.get("section") in candidate_sections or guide["key"] in linked)
        for flag in guide.get("flags", ())
        if not flag.startswith("tour_member_")
    }
    # Preserve capability-dependent panels and actions within shared sections.
    # These were recorded in the reference account with the listed capabilities.
    if "can_manage_faq_videos" in example["capabilities"]:
        flags.add("can_manage_faq_videos")
    if "external-language" in candidate_sections and "can_manage_language_cohorts" in example["capabilities"]:
        flags.add("can_manage_language_cohorts")
    return sorted(flags | chapter_flags(chapters))


def main():
    roles = json.loads((ROOT / "tools/tutorials/scenarios/faq-role-examples.json").read_text())
    model = json.loads((MASTERS / "faq-model.json").read_text())
    tours = {}
    media = json.loads((PROFILE / "faq_media.json").read_text())
    sources = {}
    for role, item in roles.items():
        key = "tour-" + role.replace("_", "-")
        if (MASTERS / key / "meta.json").is_file():
            sources[key] = key
            tours[role] = {"label": item["label"], "sections": {}}
    for key, name in {**sources, **ADDITIONAL}.items():
        path = MASTERS / name / "meta.json"
        if not path.is_file():
            continue
        master = json.loads(path.read_text())
        target = MEDIA / (key + ".mp4")
        source = Path(master["mp4"])
        if (
            not target.exists()
            or source.stat().st_mtime_ns != target.stat().st_mtime_ns
            or source.stat().st_size != target.stat().st_size
        ):
            shutil.copy2(source, target)
        (MEDIA / (key + ".vtt")).write_text(webvtt(Path(master["srt"]).read_text()))
        chapters = []
        for chapter in master["chapters"]:
            seconds = int(chapter["start"])
            chapters.append({**chapter, "time": f"{seconds // 60}:{seconds % 60:02d}"})
            if chapter.get("menu"):
                role = key.removeprefix("tour-").replace("-", "_")
                tours[role]["sections"][chapter["section"]] = chapter["title"]
                related = linked_lessons(role, chapter, model)
                if related:
                    chapters[-1]["related"] = related
                    chapters[-1]["guide"] = related[0]["key"]
        media[key] = {"duration": master["duration"], "chapters": chapters}
    for role, tour in tours.items():
        chapters = media["tour-" + role.replace("_", "-")]["chapters"]
        tour["required_flags"] = required_flags(role, tour["sections"], model, roles[role], chapters)
        missing = set(tour["required_flags"]) - set(roles[role]["capabilities"])
        if missing:
            raise ValueError(f"{role}: recorded operations exceed the reference account: {sorted(missing)}")
    replace_json(PROFILE / "faq_tours.json", tours)
    replace_json(PROFILE / "faq_media.json", media)
    print(len(tours), "rol üçün video,", len(media), "FAQ media faylı")


if __name__ == "__main__":
    main()
