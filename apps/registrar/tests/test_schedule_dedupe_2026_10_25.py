"""Tələbə cədvəlində ana qrup + bölgü jurnalının eyni dərsi bir kart olur (sahib 2026-10-25)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.registrar.schedule_dedupe import merge_duplicate_slots


def _slot(name, *, subject="s1", teacher=7, room="", kind="seminar", week_type="all", start=(10, 10)):
    offering = SimpleNamespace(subject_id=subject, instructor_id=teacher)
    return SimpleNamespace(
        name=name,
        weekday=2,
        start_time=datetime.time(*start),
        end_time=datetime.time(11, 40),
        week_type=week_type,
        kind=kind,
        room=room,
        instructor_id=None,
        offering=offering,
    )


class MergeDuplicateSlotsTest(SimpleTestCase):
    def test_parent_and_split_group_slot_show_once_with_room(self):
        merged = merge_duplicate_slots([_slot("234 K az"), _slot("234 K-1", room="409")])
        self.assertEqual([slot.name for slot in merged], ["234 K-1"])

    def test_different_lessons_stay(self):
        slots = [
            _slot("a"),
            _slot("b", kind="lecture"),
            _slot("c", week_type="odd"),
            _slot("d", subject="s2"),
            _slot("e", teacher=8),
            _slot("f", start=(8, 30)),
        ]
        self.assertEqual(len(merge_duplicate_slots(slots)), 6)
