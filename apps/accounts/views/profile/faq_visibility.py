"""Keep the same operation-level audience for lists, chapter links and media."""

from .faq_tours import tour_catalog

GENERAL = "@general"


_EXTERNAL_FLAGS = {
    "external-language": "can_view_language_cohorts",
    "external-rooms": "faq_supervise_rooms",
    "external-seals": "can_manage_document_seals",
}


def required_capabilities(guide):
    if not guide:
        return set()
    flags = set(guide.flags)
    if guide.key.startswith("tour-"):
        role = guide.key.removeprefix("tour-").replace("-", "_")
        tour = tour_catalog().get(role, {})
        flags.update(tour.get("required_flags", ()))
        flags.update(_EXTERNAL_FLAGS[name] for name in tour.get("sections", ()) if name in _EXTERNAL_FLAGS)
    return flags


def guide_allowed(guide, sections, capabilities):
    if guide.section and guide.section not in sections:
        return False
    if not all(capabilities.get(flag) for flag in guide.flags):
        return False
    if not guide.key.startswith("tour-"):
        return True
    # One MP4 contains every chapter. It is safe to serve only when the viewer
    # can see the complete recording, including its privileged demonstrations.
    role = guide.key.removeprefix("tour-").replace("-", "_")
    tour = tour_catalog().get(role)
    if not tour:
        return False
    for name in tour["sections"]:
        if name.startswith("external-"):
            if name == "external-journal":
                if "my-journal" not in sections or capabilities.get("is_student"):
                    return False
            else:
                flag = _EXTERNAL_FLAGS.get(name)
                if not flag or not capabilities.get(flag):
                    return False
        elif ("system-settings" if name.startswith("system-settings-") else name) not in sections:
            return False
    return all(capabilities.get(flag) for flag in tour.get("required_flags", ()))


def upload_allowed(record, original, sections, capabilities, builtin_by_key):
    operations = record.required_guides
    if not operations:
        # Pre-existing custom uploads remain editable until classified.
        return original is not None
    if operations == [GENERAL]:
        return True
    if not isinstance(operations, list):
        return False
    for key in operations:
        guide = builtin_by_key.get(key) if isinstance(key, str) else None
        if not guide or not guide_allowed(guide, sections, capabilities):
            return False
    return True
