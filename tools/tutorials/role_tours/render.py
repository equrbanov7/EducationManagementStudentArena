"""Render narrated role tours from recorded clicks. Use python -m tools.tutorials.role_tours.render."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..faq_movie import speech, stamp
from .scenes import role_scenes

ROOT = Path(__file__).resolve().parents[1]
RATE = 24000


def wav_name(text):
    return hashlib.sha256(text.encode()).hexdigest() + ".wav"


def prepare_speech(texts, cache):
    missing = sorted(t for t in set(texts) if not (cache / wav_name(t)).exists())
    if not missing:
        return
    key = (
        os.environ.get("TUTORIAL_ELEVEN_KEY")
        or subprocess.check_output(
            ["security", "find-generic-password", "-s", "wcu-tutorials-elevenlabs", "-w"], text=True
        ).strip()
    )
    batches = [[]]
    for text in missing:
        if sum(map(len, batches[-1])) + len(text) > 1800:
            batches.append([])
        batches[-1].append(text)

    def prepare(batch):
        job = {"key": "role-navigation", "scenes": [{"text": t} for t in batch]}
        mp3, starts = speech(job, key, cache)
        pcm = subprocess.check_output(
            ["ffmpeg", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"]
        )
        indexes = [round(t * RATE) * 2 for t in starts] + [len(pcm)]
        for i, text in enumerate(batch):
            file = cache / wav_name(text)
            with wave.open(str(file.with_suffix(".part")), "wb") as stream:
                stream.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                stream.writeframes(pcm[indexes[i] : indexes[i + 1]])
            file.with_suffix(".part").replace(file)

    with ThreadPoolExecutor(3) as workers:
        list(workers.map(prepare, batches))


def ffmeta(value):
    for char in ("\\", "=", ";", "#", "\n"):
        value = value.replace(char, "\\" + char)
    return value


def build(role, label, scenes, captures, cache, dest):
    name = "tour-" + role.replace("_", "-")
    folder = dest / name
    folder.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=folder)
    work = Path(tmp.name)
    images, subtitles, chapters, pos = [], [], [], 0
    with wave.open(str(work / "voice.wav"), "wb") as out:
        out.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        for i, scene in enumerate(scenes, start=1):
            with wave.open(str(cache / wav_name(scene["text"])), "rb") as clip:
                audio = clip.readframes(clip.getnframes())
            hold = max(round(0.5 * RATE), round(2.4 * RATE) - len(audio) // 2)
            samples = len(audio) // 2 + hold
            start, end = pos / RATE, (pos + samples) / RATE
            chapters.append(dict(start=round(start, 3), title=scene["title"], section=scene["section"]))
            if scene.get("menu"):
                chapters[-1]["menu"] = True
            if scene.get("guide"):
                chapters[-1]["guide"] = scene["guide"]
            first = min(1.35, (end - start) / 3)
            for key, seconds in (("before", first), ("after", end - start - first)):
                source = captures / role / scene[key]
                if "'" in str(source):
                    raise ValueError("Capture paths must be machine-generated")
                images.extend((f"file '{source}'", f"duration {seconds:.6f}"))
            subtitles.append(f"{i}\n{stamp(start)} --> {stamp(end - 0.03)}\n{scene['text']}\n")
            out.writeframes(audio)
            out.writeframes(bytes(2 * hold))
            pos += samples
    duration = pos / RATE
    images.append(images[-2])
    (work / "slides.ffconcat").write_text("ffconcat version 1.0\n" + "\n".join(images) + "\n")
    (work / "caption.srt").write_text("\n".join(subtitles))
    meta = [";FFMETADATA1"]
    for i, chapter in enumerate(chapters):
        start = round(chapter["start"] * 1000)
        end = round(1000 * (chapters[i + 1]["start"] if i + 1 < len(chapters) else duration))
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", "title=" + ffmeta(chapter["title"])]
    (work / "chapters.ffmeta").write_text("\n".join(meta) + "\n")
    # CFR keeps the final shown screen seekable through the full narration.
    encode = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "slides.ffconcat",
        "-i",
        "voice.wav",
        "-i",
        "caption.srt",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-map",
        "2:s",
        "-vf",
        "fps=3,tpad=stop_mode=clone:stop_duration=1",
        "-t",
        f"{duration:.4f}",
        "-c:v",
        "libx264",
        "-threads",
        "2",
        "-preset",
        "veryfast",
        "-crf",
        "27",
        "-g",
        "15",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ac",
        "1",
        "-b:a",
        "56k",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=aze",
        "encoded.mp4",
    ]
    subprocess.run(encode, cwd=work, check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            "encoded.mp4",
            "-i",
            "chapters.ffmeta",
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "0:s",
            "-map_chapters",
            "1",
            "-movie_timescale",
            "1000",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "ready.mp4",
        ],
        cwd=work,
        check=True,
    )
    mp4, srt = folder / (name + ".mp4"), folder / (name + ".srt")
    (work / "ready.mp4").replace(mp4)
    (work / "caption.srt").replace(srt)
    (folder / (name + ".vtt")).write_text(webvtt(srt.read_text()))
    # The last CFR frame may extend slightly past the narration.
    media_duration = float(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
            text=True,
        ).strip()
    )
    audience = {
        "telebe": "Tələbə üçün",
        "muellim": "Müəllim üçün",
        "lab_assistant": "Laborant üçün",
        "chair_head": "Kafedra müdiri üçün",
        "dean": "Dekanlıq üçün",
        "ikt_rehber": "RİM üçün",
        "hr": "HR üçün",
        "tutor": "Tyutor üçün",
        "accountant": "Mühasib üçün",
    }.get(role, label + " üçün")
    result = dict(
        name=name,
        title=label + " kabinetində menyu və tablar",
        audience=audience,
        section="00 Kabinetdə keçidlər",
        order="00.10",
        summary="Sol menyudakı bölmələrin açılışı və kabinetdəki keçidlər. Vaxtı seçərək istədiyiniz əməliyyata keçin.",
        duration=round(media_duration, 3),
        chapters=chapters,
        mp4=str(mp4.resolve()),
        srt=str(srt.resolve()),
        shortGuide=False,
    )
    (folder / "meta.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    tmp.cleanup()
    print(name, len(chapters), round(duration), mp4.stat().st_size, flush=True)


def webvtt(text):
    import re

    return "WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d{3})", r"\1.\2", text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--roles", nargs="+", required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 7), default=3)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    examples = json.loads((ROOT / "scenarios/faq-role-examples.json").read_text())
    model = json.loads((ROOT / "out/faq-model.json").read_text())
    jobs = {
        role: role_scenes(
            role,
            json.loads((args.captures / role / "progress.json").read_text()),
            [guide for guide in model["guides"] if guide["key"] in model["roles"][role]["ids"]],
            example=examples[role],
        )
        for role in args.roles
    }
    prepare_speech([s["text"] for scenes in jobs.values() for s in scenes], args.cache)
    with ThreadPoolExecutor(args.workers) as workers:
        list(
            workers.map(
                lambda role: build(role, examples[role]["label"], jobs[role], args.captures, args.cache, ROOT / "out"),
                jobs,
            )
        )


if __name__ == "__main__":
    main()
