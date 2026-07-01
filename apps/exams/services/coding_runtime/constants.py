"""coding_runtime paketi — constants."""

import re

MAX_CODE_BYTES = 256_000


MAX_CAPTURE_BYTES = 64_000


SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")


TRIPLE_QUOTE_RE = re.compile(r"(?<!\\)(\"\"\"|''')")


LANGUAGE_MODES = {
    "javascript": "javascript",
    "python": "python",
    "cpp": "text/x-c++src",
    "java": "text/x-java",
    "html": "htmlmixed",
    "css": "css",
}


DOCKER_IMAGES = {
    "javascript": "node:22-alpine",
    "python": "python:3.12-alpine",
    "cpp": "gcc:14",
    "java": "eclipse-temurin:21",
}


PISTON_LANGUAGES = {
    "python": ("python", "*"),
    "javascript": ("javascript", "*"),
    "cpp": ("c++", "*"),
    "java": ("java", "*"),
}


PISTON_FILE_NAMES = {
    "python": "main.py",
    "javascript": "main.js",
    "cpp": "main.cpp",
    "java": "Main.java",
}
