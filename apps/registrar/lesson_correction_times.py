"""Lossless optional clock snapshots; legacy empty/empty edits retain current partial clocks."""

from datetime import time


def snapshot(lesson):
    def clock(value):
        return (
            value.isoformat(timespec="microseconds" if value.microsecond else "seconds" if value.second else "minutes")
            if value
            else ""
        )

    start, end = clock(lesson.start_time), clock(lesson.end_time)
    return f"{start}–{end}" if start or end else ""


def matches(lesson, correction):
    current = snapshot(lesson)
    if current == correction.new_time:
        return True
    # Historical writers omitted a lone endpoint even on an hours-only edit.
    return correction.old_time == correction.new_time == "" and bool(lesson.start_time) != bool(lesson.end_time)


def restore(correction):
    if correction.old_time == correction.new_time == "":
        return None, None  # No attested clock change: never erase an existing partial clock.
    if not correction.old_time:
        return "", ""
    if correction.old_time.count("–") != 1:
        raise ValueError("invalid_lesson_correction_clock")
    start, end = correction.old_time.split("–")
    return time.fromisoformat(start) if start else "", time.fromisoformat(end) if end else ""
