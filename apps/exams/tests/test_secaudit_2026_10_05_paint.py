"""Təhlükəsizlik auditi 2026-10-05 — rəsm (paint) cavabının fayl adı təxmin olunmamalıdır.

Əvvəl fayl ``exam_paints/<il>/<ay>/paint_answer_<answer_id>.png`` idi: ardıcıl id ilə
başqa tələbələrin rəsm cavablarının yolunu qurmaq olurdu (media icazəsi də geniş idi).
"""

from __future__ import annotations

import base64
import re
import tempfile
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.exams.services.utils import _save_paint_png_to_answer

_PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
).decode()


class _FakeField:
    def __init__(self):
        self.saved = []

    def save(self, name, content, save=False):
        self.saved.append(name)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class PaintFilenameTest(SimpleTestCase):
    def test_paint_filename_is_random_and_not_answer_id(self):
        field = _FakeField()
        answer = SimpleNamespace(id=4242, paint_image=field)
        self.assertTrue(_save_paint_png_to_answer(answer, f"data:image/png;base64,{_PNG}"))
        self.assertTrue(_save_paint_png_to_answer(answer, f"data:image/png;base64,{_PNG}"))
        first, second = field.saved
        self.assertNotIn("4242", first)
        self.assertRegex(first, re.compile(r"^paint_[0-9a-f]{32}\.png$"))
        self.assertNotEqual(first, second)
