"""Compose the cabinet player from exactly the effective guides authorized for this request."""

from functools import lru_cache

from django.utils.translation import gettext

from .faq_catalog import PUBLIC_LOGIN_GUIDES, Guide, media_metadata
from .faq_tours import tour_catalog, tour_key

# Existing portal actions with a recorded, unambiguous button/panel in the role film.
# Other operations use their focused recording's authored start, never a guessed offset.
_ACTION_CHAPTERS = {
    "open-application": ("applications", "Yeni müraciət"),
    "section-question-bank": ("question-bank", "Yeni bank"),
    "appeal": ("my-appeals", "Yeni apellyasiya müraciəti"),
}
_SECTION_NAVIGATION = {"section-dashboard", "section-my-schedule", "section-academic-calendar", "section-faq"}


def _duration(guide):
    if hasattr(guide, "duration_seconds"):
        return guide.duration_seconds
    return media_metadata().get(guide.video, {}).get("duration", 0)


def chapter_details(chapter):
    seconds = int(chapter["start"])
    return {
        "title": chapter["title"],
        "start": chapter["start"],
        "time": chapter.get("time") or f"{seconds // 60}:{seconds % 60:02d}",
    }


def _chapters(rows):
    # Role navigation, raw editor data and related guide keys stay server-side.
    # The player formats these local offsets on its continuous timeline.
    return [{"title": chapter["title"], "start": chapter["start"]} for chapter in rows]


@lru_cache(maxsize=256)
def _stock_chapters(video):
    return _chapters(media_metadata()[video]["chapters"])


def _recording(guide):
    if type(guide) is Guide:
        return "stock", guide.video
    if (
        guide.video
        and not guide.video_file
        and not guide.subtitle_file
        and not guide.omit_subtitles
        and tuple(guide.chapters) == tuple(media_metadata()[guide.video]["chapters"])
    ):
        return "stock", guide.video
    return "tenant", guide.key


def _source(guide, duration):
    return {
        "key": guide.key,
        "title": guide.topic if guide.key.startswith("tour-") else guide.title,
        "src": guide.video_url,
        "track": guide.subtitle_url if guide.has_subtitles else "",
        "duration": duration,
        "chapters": _stock_chapters(guide.video) if type(guide) is Guide else _chapters(guide.chapters),
    }


def _tour_targets(tours, allowed):
    result = {}
    for tour in tours:
        # A replacement recording has its own chapter timings and content.
        if type(tour) is not Guide:
            continue
        for chapter in tour.chapters:
            section = chapter.get("section")
            title = chapter["title"].partition(" · ")[2]
            key = chapter.get("guide")
            if chapter.get("menu") and key in _SECTION_NAVIGATION and key in allowed:
                result.setdefault(key, (tour.key, chapter["start"]))
            for guide_key, match in _ACTION_CHAPTERS.items():
                if guide_key in allowed and (section, title) == match:
                    result.setdefault(guide_key, (tour.key, chapter["start"]))
    return result


def featured_player(guides, roles, role_label):
    """Guide order and permissions are resolved before this function, independent of search."""
    playable = {g.key: g for g in guides if g.video in media_metadata() or getattr(g, "video_file", None)}
    if not playable:
        return None
    tours = [playable[tour_key(role)] for role in roles if tour_key(role) in playable]
    menu_order = {}
    for role in roles:
        for section in tour_catalog().get(role, {}).get("sections", ()):
            menu_order.setdefault(section, len(menu_order))

    def order(g):
        return (
            g.key in PUBLIC_LOGIN_GUIDES,
            g.key == "section-faq",
            g.key != "section-dashboard",
            menu_order.get(g.section, len(menu_order)),
            not g.key.startswith("section-"),
        )

    focused = sorted((g for g in playable.values() if not g.key.startswith("tour-")), key=order)
    # Aliases and text-only edits share a recording. Distinct chapter tracks,
    # captions and replacement uploads keep their own playable source.
    by_recording, sources, source_keys = {}, {}, {}
    for guide in (*tours, *focused):
        identity = _recording(guide)
        key = by_recording.setdefault(identity, guide.key)
        source_keys[guide.key] = key
        if key not in sources:
            sources[key] = _source(guide, _duration(guide))
    if not sources:
        return None
    # Orientation is followed by every distinct authorized worked example, including
    # operations that the role film only introduces through its menu.
    playlist = list(sources)
    mappings = _tour_targets(tours, playable.keys())
    targets = {}
    for key, source in source_keys.items():
        guide = playable[key]
        mapped = mappings.get(key) if type(guide) is Guide and not guide.start else None
        media, start = mapped or (source, guide.start)
        targets[key] = {"key": media, "start": start, "source": source}
    return {
        "title": gettext("Kabinet üzrə tam video təlimat"),
        "role_label": role_label,
        "mode": "tour" if tours else "playlist",
        "sources": list(sources.values()),
        "playlist": playlist,
        "targets": targets,
    }
