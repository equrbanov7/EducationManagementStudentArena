"""Render chaptered Azerbaijani guides from approved text and synthetic screenshots.

Usage: python faq_movie.py JOBS.json OUTPUT_DIR CACHE_DIR
Each job contains key, title, topic and scenes with text, chapter and an optional
image. Supply synthetic captures. Speech is cached by text, voice and model.
"""

import base64
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import accumulate
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
DEFAULTS = json.loads((ROOT / "scenarios/_defaults.json").read_text())


def font(size, bold=False):
    choice = "Arial Bold.ttf" if bold else "Arial.ttf"
    candidates = (
        Path("/System/Library/Fonts/Supplemental") / choice,
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    )
    return ImageFont.truetype(str(next(path for path in candidates if path.is_file())), size)


def wrap(draw, text, face, width):
    lines = []
    for word in text.split():
        if lines and draw.textlength(lines[-1] + " " + word, font=face) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def frame(job, scene, page, output):
    canvas = Image.new("RGB", (1280, 800), "#f3f6fa")
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, 1280, 79), fill="#162c45")
    d.text((34, 13), job["topic"], font=font(19), fill="#a7d8ef")
    heading = scene["chapter"]
    hfont = font(29, True)
    while d.textlength(heading, font=hfont) > 1132:
        hfont = font(hfont.size - 1, True)
    d.text((33, 37), heading, font=hfont, fill="white")
    d.text((1215, 28), f"{page}/{len(job['scenes'])}", font=font(20), fill="#dfebf2", anchor="mm")
    source = scene.get("image")
    if source:
        img = Image.open(source).convert("RGB")
        if scene.get("focus"):
            x, y, width, height = scene["focus"]
            marker = ImageDraw.Draw(img)
            marker.rounded_rectangle(
                (max(0, x - 4), max(0, y - 3), min(img.width - 1, x + width + 4), min(img.height - 1, y + height + 3)),
                radius=4,
                outline="#126d9a",
                width=3,
            )
        scale = min(1200 / img.width, 504 / img.height, 1.5)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
        ox, oy = (1280 - img.width) // 2, 91 + (504 - img.height) // 2
        canvas.paste(img, (ox, oy))
        y = 615
    else:
        title_lines = wrap(d, job["title"], font(43, True), 1160)
        d.multiline_text((56, 162), "\n".join(title_lines), font=font(43, True), fill="#162c45", spacing=7)
        y = max(360, 195 + len(title_lines) * 55)
    d.rectangle((0, y, 1280, 800), fill="white")
    d.rectangle((32, y + 26, 36, min(y + 106, 776)), fill="#146184")
    face = font(28)
    lines = wrap(d, scene["text"], face, 1170)
    while len(lines) * (face.size + 8) > 768 - (y + 21):
        face = font(face.size - 1)
        lines = wrap(d, scene["text"], face, 1170)
    d.multiline_text((55, y + 21), "\n".join(lines), font=face, fill="#172e46", spacing=7)
    canvas.save(output)


def speech(job, key, cache):
    texts = [s["text"] for s in job["scenes"]]
    spoken = " ".join(texts)
    voice, model = DEFAULTS["elevenVoice"], DEFAULTS["elevenModel"][0]
    sig = hashlib.sha256((voice + model + spoken).encode()).hexdigest()
    data_file, mp3 = cache / (sig + ".json"), cache / (sig + ".mp3")
    if not (data_file.is_file() and mp3.is_file()):
        request = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
            data=json.dumps({"text": spoken, "model_id": model, "language_code": "az"}).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json"},
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=110) as response:
                    result = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
        mp3.write_bytes(base64.b64decode(result["audio_base64"]))
        data_file.write_text(json.dumps(result["alignment"]))
    alignment = json.loads(data_file.read_text())
    chars = "".join(alignment["characters"])
    starts, pos = [], 0
    for text in texts:
        index = chars.find(text, pos)
        if index < 0:
            raise ValueError(f"Provider alignment mismatch for {job['key']}")
        starts.append(alignment["character_start_times_seconds"][index])
        pos = index + len(text)
    starts[0] = 0.0
    return mp3, starts


def stamp(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def build(job, key, output, cache):
    dest = output / job["key"]
    dest.mkdir(parents=True, exist_ok=True)
    name = job["key"]
    marker = dest / "metadata.json"
    digest = hashlib.sha256(json.dumps(job, ensure_ascii=False, sort_keys=True).encode())
    digest.update(b"hold-last-frame-v3")
    for image_path in sorted({scene["image"] for scene in job["scenes"] if scene.get("image")}):
        digest.update(hashlib.sha256(Path(image_path).read_bytes()).digest())
    signature = digest.hexdigest()
    if marker.is_file() and (dest / (name + ".mp4")).is_file():
        if json.loads(marker.read_text()).get("signature") == signature:
            return
    mp3, starts = speech(job, key, cache)
    duration = float(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3], text=True
        )
    )
    concat = []
    subs = []
    chapters = []
    for i, (scene, start, end) in enumerate(zip(job["scenes"], starts, starts[1:] + [duration])):
        image = dest / f"frame-{i}.png"
        frame(job, scene, i + 1, image)
        concat.extend([f"file '{image.name}'", f"duration {end-start:.3f}"])
        chapters.append({"start": round(start, 3), "title": scene["chapter"]})
        # Break long lines into subtitle-sized phrases at punctuation or word boundaries.
        tokens = re.findall(r"\S+", scene["text"])
        chunks = []
        for word in tokens:
            if chunks and len(chunks[-1]) + len(word) < 86 and not re.search(r"[.!?]$", chunks[-1]):
                chunks[-1] += " " + word
            else:
                chunks.append(word)
        lengths = [len(x) for x in chunks]
        offsets = [start] + [start + (end - start) * n / sum(lengths) for n in accumulate(lengths)]
        for line, begin, finish in zip(chunks, offsets, offsets[1:]):
            subs.append(f"{len(subs)+1}\n{stamp(begin)} --> {stamp(finish-0.012)}\n{line}\n")
    concat.append(f"file 'frame-{len(chapters)-1}.png'")
    ff = dest / "frames.ffconcat"
    ff.write_text("\n".join(concat) + "\n")
    srt = dest / (name + ".srt")
    srt.write_text("\n".join(subs))
    (dest / (name + ".vtt")).write_text("WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d{3})", r"\1.\2", srt.read_text()))
    metadata = dest / "chapters.ffmeta"
    chapter_lines = [";FFMETADATA1"]
    for chapter, end in zip(chapters, starts[1:] + [duration]):
        title = re.sub(r"([\\=;#])", r"\\\1", chapter["title"])
        chapter_lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={round(chapter['start']*1000)}",
                f"END={round(end*1000)}",
                f"title={title}",
            ]
        )
    metadata.write_text("\n".join(chapter_lines) + "\n")
    video = dest / (name + ".mp4")
    encoded = dest / "encoded.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            ff,
            "-i",
            mp3,
            "-i",
            srt,
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            "-vf",
            f"tpad=stop_mode=clone:stop_duration={duration:.3f},fps=5",
            "-t",
            str(math.ceil(duration * 5) / 5),
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "112k",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=aze",
            "-movflags",
            "+faststart",
            encoded,
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            encoded,
            "-f",
            "ffmetadata",
            "-i",
            metadata,
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-map",
            "0:s",
            "-map_chapters",
            "1",
            "-c",
            "copy",
            "-movie_timescale",
            "1000",
            "-movflags",
            "+faststart",
            video,
        ],
        check=True,
    )
    encoded.unlink()
    marker.write_text(
        json.dumps({"chapters": chapters, "duration": duration, "signature": signature}, ensure_ascii=False)
    )
    for png in dest.glob("frame-*.png"):
        png.unlink()
    ff.unlink()
    metadata.unlink()
    print(f"{name} {duration:.1f}s", flush=True)


def main():
    jobs_path, output, cache = map(Path, sys.argv[1:])
    cache.mkdir(parents=True, exist_ok=True)
    key = (
        os.environ.get("TUTORIAL_ELEVEN_KEY")
        or subprocess.check_output(
            ["security", "find-generic-password", "-s", "wcu-tutorials-elevenlabs", "-w"], text=True
        ).strip()
    )
    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(lambda job: build(job, key, output, cache), json.loads(jobs_path.read_text())))


if __name__ == "__main__":
    main()
