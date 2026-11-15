"""Sahib 2026-11-16: «etirazlar aşağı düşür, görmək olmur» — «Yük bölgüsü»ndə etirazlar süzgəclərdən ƏVVƏL.

Açıq etiraz yuxarıda sayı ilə görünür, bağlanmışlar yığılmış siyahıdadır.
"""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

TEMPLATE = "accounts/profile/sections/_workload_distribution.html"


def _item(pk, is_open):
    return {
        "id": pk,
        "subject": "Həyat fəaliyyətinin təhlükəsizliyi",
        "teacher": "Test Müəllim",
        "reason_label": "Qrup/tələbə sayı səhvdir",
        "text": f"etiraz-{pk}",
        "status_label": "Baxılır" if is_open else "Qəbul edilib",
        "is_open": is_open,
    }


class ObjectionsOnTopTest(SimpleTestCase):
    def render(self, items):
        open_count = sum(1 for item in items if item["is_open"])
        section = {
            "has_access": True,
            "can_distribute": True,
            "objections": items,
            "objections_open": open_count,
            "objections_closed": len(items) - open_count,
            "catalog": {},
        }
        return render_to_string(
            TEMPLATE,
            {"allowed_sections": ["workload-distribution"], "workload_distribution_section": section},
        )

    def test_open_objection_rendered_before_filters_with_count(self):
        html = self.render([_item("a1", True), _item("c1", False)])
        self.assertLess(html.index("wl-objections-panel"), html.index("data-wl-filters"))
        self.assertIn("1 açıq", html)
        self.assertLess(html.index("etiraz-a1"), html.index("wl-objections__closed"))
        self.assertGreater(html.index("etiraz-c1"), html.index("wl-objections__closed"))
        self.assertIn('"state": "accepted"', html)

    def test_only_closed_objections_are_collapsed(self):
        html = self.render([_item("c1", False)])
        self.assertNotIn("wl-objections-panel--open", html)
        self.assertNotIn("açıq</span>", html)
        self.assertIn("wl-objections__closed", html)

    def test_no_objections_no_panel(self):
        self.assertNotIn("wl-objections-panel", self.render([]))
