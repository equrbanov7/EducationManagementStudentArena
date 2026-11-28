"""Build screen sequences from actual browser interactions with the synthetic role."""

import json
import re
from functools import lru_cache
from pathlib import Path

if __package__:
    from .recorded_permissions import chapter_flags
else:
    from recorded_permissions import chapter_flags


EXTERNAL = {
    "/jurnal/": (
        "external-journal",
        "Elektron jurnalda dövrü və qrupu yoxlayın, sonra fənnin jurnalını açın.",
        "missing-journal",
    ),
    "/jurnal/seviyye/": (
        "external-language",
        "Səviyyə qruplarını açın. Qrupun adını, səviyyəsini və aid olduğu kafedranı yoxlayın.",
        "language-group-create",
    ),
    "/exams/center/rooms/": (
        "external-rooms",
        "Zal siyahısında otağı seçib həmin zalın məlumatlarına keçin.",
        "room-monitor",
    ),
    "/sened-yoxlamasi/": (
        "external-seals",
        "Sənədin üzərindəki yoxlama kodunu yoxlama sahəsinə yazın.",
        "sealed-register",
    ),
}
INSTRUCTIONS = {
    "dashboard": "Ana səhifədə cari dövrü və sizin üçün göstərilən kartları yoxlayın. Kartdakı keçid onun aid olduğu bölməni açır.",
    "faq": "Axtarışa sualınızı yazın. Nəticədə üstəgəl işarəsi ilə izahı açın. Videoda istədiyiniz fəslin vaxtına keçə bilərsiniz.",
    "applications": "Müraciətin növünü və statusunu yoxlayın. Yeni müraciət formasını açanda tələb edilən sahələr seçdiyiniz növə uyğun dəyişir.",
    "notifications": "Bildirişləri oxunma vəziyyətinə görə seçin. Növü və tarixi yoxlayın.",
    "my-journal": "Fənnin jurnalını açın. Qayıb sayını və limiti görün, sonra dərs tarixçəsində günün iştirak qeydini və balını oxuyun.",
    "my-subjects": "Semestr üzrə fənni seçin. Kartdan dərsin jurnalına və müəllimin paylaşdığı materiallara keçə bilərsiniz.",
    "my-subject-folders": "Müəllimin sizə açdığı fənni seçin. Mövzunun altında faylları və varsa tapşırığın şərtini açın.",
    "my-results": "Nəticənin növünü, dərs ilini və semestri seçin. Fənnin bal bölgüsünü kartdan oxuyun.",
    "profile-info": "Profil məlumatlarını açın. Adı və əlaqə məlumatlarını yoxlayın.",
    "edit-profile": "Profilin redaktə formasını açın. Dəyişiklik edilə bilən sahələr burada göstərilir.",
    "surveys-inbox": "Gözləyən və tamamlanmış sorğuların siyahılarına baxın. Sorğu açıqdırsa, kartdan formasına keçin.",
    "academic-calendar": "Təqvimdə dövrü seçin. Semestrin və qeydiyyat pəncərələrinin başlanğıc və bitmə tarixlərinə baxın.",
    "my-schedule": "Həftəni seçin. Günün dərsini, saatını və auditoriyasını cədvəldə tapın.",
    "lab-groups": "Jurnalı və əsas qrupu seçin. Laboratoriya alt qruplarının tərkibinə baxın.",
}


def clean(value):
    label = re.sub(r"\s+", " ", value).strip(" ·→:")
    return re.sub(r"\s+[0-9]+$", "", label) or value.strip()


def short_instruction(step):
    first = re.split(r"(?<=[.!?])\s+", step)[0]
    return first if 12 < len(first) <= 220 else ""


def _captured_scenes(role, records, guides):
    by_section = {g["key"]: g for g in guides}
    scenes = []
    for row in sorted(records, key=lambda r: r["id"]):
        if not row["ok"]:
            continue
        key = row["key"]
        label = clean(row["label"])
        guide_id = "section-" + key
        article = by_section.get(guide_id, {})
        instruction = INSTRUCTIONS.get(key) or short_instruction((article.get("steps") or [""])[0])
        if not key:
            key, instruction, guide_id = EXTERNAL.get(row["href"], ("external-" + row["id"], "", ""))
            if key == "external-journal" and role == "lab_assistant":
                guide_id = "laborant-journal"
        if row.get("subGroup") and row.get("subLabel"):
            label += " · " + clean(row["subLabel"])
            key += "-" + row["subGroup"]
            instruction = ""
        group = Path(row.get("frameFolder", row["id"]))
        spoken = f"«{label}» bölməsini açın."
        if instruction:
            spoken = instruction if label.lower() in instruction[:55].lower() else spoken + " " + instruction
        scenes.append(
            dict(
                section=key,
                title=label,
                text=spoken,
                guide=guide_id,
                menu=True,
                before=str(group / "menu.jpg"),
                after=str(group / "open.jpg"),
            )
        )
        for ctrl in row["opened"]:
            if ctrl.get("initial") or ctrl.get("frame") == "open.jpg":
                continue
            title = clean(ctrl["label"])
            if not title:
                continue
            parts = [label]
            if ctrl.get("parent"):
                parts.append(clean(ctrl["parent"]))
            parts.append(title)
            text = f"«{title}» seçimini açın." if ctrl.get("tab") else f"«{title}» düyməsini seçin."
            scenes.append(
                dict(
                    section=key,
                    title=" · ".join(parts),
                    text=text,
                    menu=False,
                    before=str(group / ctrl.get("before", ctrl["frame"])),
                    after=str(group / ctrl["frame"]),
                )
            )
    return scenes


@lru_cache(maxsize=1)
def role_examples():
    path = Path(__file__).resolve().parents[1] / "scenarios/faq-role-examples.json"
    return json.loads(path.read_text(encoding="utf-8"))


def section_key(row):
    key = row["key"] or EXTERNAL.get(row["href"], ("external-" + row["id"], "", ""))[0]
    if row.get("subGroup") and row.get("subLabel"):
        key += "-" + row["subGroup"]
    return key


def role_scenes(role, records, guides, *, example=None, excluded=None):
    """Select scenes and both transition frames from the actual tenant's operation snapshot."""
    if example is None:
        example = role_examples()[role]
    capabilities, sections = set(example["capabilities"]), set(example["sections"])
    captured = _captured_scenes(role, records, guides)
    if excluded is not None:
        for row in records:
            excluded.extend(row.get("withdrawnScenes", ()))
    kept, blocked_frames = [], set()
    omitted_sections = {
        section_key(row)
        for row in records
        if (row["key"] and row["key"] not in sections)
        or (row["key"] == "workload-center" and "faq_manage_workload_row" not in capabilities)
        or (
            row["key"] == "workload-distribution"
            and not capabilities & {"faq_manage_workload_row", "faq_distribute_workload"}
        )
    }
    for scene in captured:
        missing = chapter_flags([scene]) - capabilities
        if missing or scene["section"] in omitted_sections:
            blocked_frames.update((scene["before"], scene["after"]))
            if excluded is not None:
                excluded.append(dict(section=scene["section"], title=scene["title"], missing=sorted(missing)))
            continue
        kept.append(scene)
    # A child or the next clicked item may reuse its predecessor's image. Do
    # not hand such a transition image to ffmpeg even if it survived under a
    # different caption. A scene with no clean image is excluded as well.
    result = []
    for scene in kept:
        before, after = scene["before"], scene["after"]
        if before in blocked_frames and after in blocked_frames:
            if excluded is not None:
                excluded.append(dict(section=scene["section"], title=scene["title"], missing=["capture"]))
            continue
        if before in blocked_frames:
            scene["before"] = after
        elif after in blocked_frames:
            scene["after"] = before
        result.append(scene)
    return result
