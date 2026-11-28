"""Audit published FAQ media and role-tour masters. Run directly or with -m.

The default requires every role from faq-role-examples.json to be rendered and
installed. During rendering, --scope masters --available checks finished masters.
Exit 1 means at least one media, metadata, subtitle, or copy check failed.
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MASTERS = ROOT / "tools/tutorials/out"
PRIVATE = ROOT / "apps/accounts/guide_media"
PROFILE = ROOT / "apps/accounts/views/profile"
ROLES = ROOT / "tools/tutorials/scenarios/faq-role-examples.json"
CHAPTER_TOLERANCE = 0.005  # MP4 chapter times and source manifests use millisecond precision.
DURATION_TOLERANCE = 0.30  # Last video frame/encoded audio packet may extend beyond the narration.
TIMESTAMP = re.compile(r"^(\d{2,}):(\d\d):(\d\d)[.,](\d{3}) --> ", re.MULTILINE)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def timeline(row):
    return [(float(c["start"]), c["title"]) for c in row["chapters"]]


def check_times(actual, expected, tolerance, label):
    if len(actual) != len(expected):
        raise ValueError(f"{label}: {len(actual)} entries, expected {len(expected)}")
    for index, (value, target) in enumerate(zip(actual, expected), 1):
        if not math.isclose(value, target, rel_tol=0, abs_tol=tolerance):
            raise ValueError(f"{label} {index}: {value:.3f}s, expected {target:.3f}s")


def check_video(path, meta, tour):
    duration = float(meta["duration"])
    expected = timeline(meta)
    if not expected or not 0 <= expected[0][0] < duration or not all(title.strip() for _, title in expected):
        raise ValueError("invalid chapter or duration in manifest")
    starts, titles = zip(*expected)
    if any(b <= a for a, b in pairwise((*starts, duration))):
        raise ValueError("non-increasing chapter times in manifest")

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_chapters",
            "-show_entries",
            "chapter=start_time,end_time:chapter_tags=title:format=duration:"
            "stream=codec_type,codec_name,codec_tag_string,time_base,duration,nb_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    if probe.stderr.strip():
        raise ValueError(probe.stderr.strip())
    info = json.loads(probe.stdout)
    streams = {s["codec_type"]: s for s in info["streams"]}
    if streams["video"]["codec_name"] != "h264" or streams["audio"]["codec_name"] != "aac":
        raise ValueError("expected H.264 video and AAC audio")
    if float(streams["audio"]["duration"]) - float(streams["video"]["duration"]) > DURATION_TOLERANCE:
        raise ValueError("video ends before the final 0.3 seconds of audio")
    check_times([float(info["format"]["duration"])], [duration], DURATION_TOLERANCE, "container duration")
    chapters = info["chapters"]
    check_times([float(c["start_time"]) for c in chapters], starts, CHAPTER_TOLERANCE, "chapter start")
    check_times([float(c["end_time"]) for c in chapters[:-1]], starts[1:], CHAPTER_TOLERANCE, "chapter end")
    for i, (chapter, title) in enumerate(zip(chapters, titles), 1):
        if chapter["tags"]["title"] != title:
            raise ValueError(f"chapter {i}: {chapter['tags']['title']!r}, expected {title!r}")
    # Nero chapters may look correct while the QuickTime chapter track ends early.
    track = streams.get("data", {})
    if (
        track.get("codec_tag_string") != "text"
        or track.get("time_base") != "1/1000"
        or int(track.get("nb_frames", 0)) != len(chapters)
    ):
        raise ValueError("missing/incomplete QuickTime chapter track")
    check_times([float(chapters[-1]["end_time"]), float(track["duration"])], [duration] * 2, DURATION_TOLERANCE, "end")

    vtt = path.with_suffix(".vtt").read_text(encoding="utf-8-sig")
    if not vtt.startswith("WEBVTT") or not TIMESTAMP.search(vtt):
        raise ValueError("empty/invalid WebVTT captions")
    if tour:
        if streams.get("subtitle", {}).get("codec_name") != "mov_text":
            raise ValueError("role tour has no embedded captions")
        times = [int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in TIMESTAMP.findall(vtt)]
        check_times(times, starts, CHAPTER_TOLERANCE, "WebVTT cue start")
    return len(chapters)


def check_copy(src, dest):
    for path in (src, src.with_suffix(".vtt")):
        with path.open("rb") as original, (dest.parent / path.name).open("rb") as published:
            if hashlib.file_digest(original, "sha256").digest() != hashlib.file_digest(published, "sha256").digest():
                raise ValueError(f"published {path.suffix} differs from master")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["all", "masters", "private"], default="all")
    parser.add_argument("--available", action="store_true", help="skip roles still rendering or awaiting installation")
    args = parser.parse_args()
    expected_roles = {"tour-" + role.replace("_", "-") for role in read_json(ROLES)}
    jobs, errors, missing = [], [], []
    if args.scope in ("all", "masters"):
        for key in sorted(expected_roles | {p.parent.name for p in MASTERS.glob("tour-*/meta.json")}):
            folder = MASTERS / key
            if key not in expected_roles:
                errors.append(f"unexpected master {key}")
            elif (folder / "meta.json").is_file():
                jobs.append(("master", folder / f"{key}.mp4", folder / "meta.json"))
            else:
                missing.append(f"master/{key}")
    if args.scope in ("all", "private"):
        manifest = read_json(PROFILE / "faq_media.json")
        menu_catalog = {
            "tour-" + role.replace("_", "-"): item["sections"]
            for role, item in read_json(PROFILE / "faq_tours.json").items()
        }
        installed_tours = {key for key in manifest if key.startswith("tour-")}
        for key in sorted(set(menu_catalog) ^ installed_tours):
            errors.append(f"private/{key}: role menu and media catalogue differ")
        for key in sorted(installed_tours & set(menu_catalog)):
            menu = {c["section"]: c["title"] for c in manifest[key]["chapters"] if c.get("menu")}
            if menu != menu_catalog[key]:
                errors.append(f"private/{key}: role section links differ from menu chapters")
        files = {p.stem for p in PRIVATE.glob("*.mp4")} | {p.stem for p in PRIVATE.glob("*.vtt")}
        for key in sorted(expected_roles | set(manifest) | files):
            if key in manifest:
                jobs.append(("private", PRIVATE / f"{key}.mp4", manifest[key]))
            elif key in files:
                errors.append(f"private/{key}: file missing from catalogue")
            else:
                missing.append(f"private/{key}")
    if not args.available:
        errors.extend(missing)

    def verify(job):
        kind, path, source = job
        try:
            meta = read_json(source) if isinstance(source, Path) else source
            tour = path.stem.startswith("tour-")
            count = check_video(path, meta, tour)
            if kind == "master":
                if meta["name"] != path.stem or Path(meta["mp4"]).name != path.name:
                    raise ValueError("invalid master metadata/file name")
                srt = path.with_suffix(".srt").read_text(encoding="utf-8-sig")
                webvtt = "WEBVTT\n\n" + re.sub(r"(\d{2,}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)
                if webvtt != path.with_suffix(".vtt").read_text(encoding="utf-8-sig"):
                    raise ValueError("master SRT and VTT differ")
            if kind == "private" and tour:
                directory = MASTERS / path.stem
                master = read_json(directory / "meta.json")
                if timeline(master) != timeline(meta) or master["duration"] != meta["duration"]:
                    raise ValueError("published chapter metadata differs from master")
                check_copy(directory / path.name, path)
            return count, ""
        except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as error:
            detail = (
                (error.stderr or str(error)).strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
            )
            return 0, f"{kind}/{path.stem}: {detail}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(verify, jobs))
    errors.extend(error for _, error in results if error)
    for item in errors:
        print(item, file=sys.stderr)
    print(
        f"{sum(kind == 'master' for kind, *_ in jobs)} masters, {sum(kind == 'private' for kind, *_ in jobs)} private"
        f" videos, {sum(n for n, _ in results)} verified chapters; {len(missing)} pending; {len(errors)} errors."
    )
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
