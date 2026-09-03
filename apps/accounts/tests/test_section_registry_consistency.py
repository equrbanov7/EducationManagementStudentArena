"""Şablonun AJAX bölmə siyahısı ilə backend qeydiyyatı UYĞUN olmalıdır.

2026-08-27 QA süpürgəsi belə bir sinif xəta tapdı: ``profile.html``-in
``data-ajax-sections`` atributunda ``unit-exams`` və ``superadmin-org-inspector``
VAR idi, ``sections_api.SECTION_PARTIALS``-da isə YOX.  Nəticədə dekan menyuda
«Bölmə imtahanları»nı görürdü, klikləyəndə ön tərəf fraqment sorğusu atırdı və
``_ensure_section_allowed`` 403 qaytarırdı.

Tələ məhz ona görə uzun müddət gizli qaldı ki, **tam səhifə yolu**
(``/accounts/profile/?section=unit-exams``) işləyirdi — yalnız AJAX yolu sınırdı.

Bu modul iki istiqamətdə uyğunluğu kilidləyir ki, siyahılar bir daha ayrılmasın.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

_PROFILE_TEMPLATE = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile.html"
_AJAX_ATTR = re.compile(r'data-ajax-sections="([^"]+)"')


def _template_ajax_sections() -> set[str]:
    match = _AJAX_ATTR.search(_PROFILE_TEMPLATE.read_text(encoding="utf-8"))
    assert match is not None, "profile.html-də `data-ajax-sections` atributu tapılmadı"
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


class SectionRegistryConsistencyTest(SimpleTestCase):
    def test_every_ajax_section_has_a_registered_partial(self):
        """Şablon AJAX ilə yükləyəcəyini deyirsə, backend onu tanımalıdır."""
        missing = sorted(_template_ajax_sections() - set(SECTION_PARTIALS))
        self.assertEqual(
            missing,
            [],
            "Bu bölmələr `data-ajax-sections`-dadır, amma `SECTION_PARTIALS`-da yoxdur — "
            "menyuda görünəcək, klikləndikdə isə 403 verəcək: " + ", ".join(missing),
        )

    def test_every_ajax_section_is_marked_ajax_safe(self):
        """Fraqment endpoint-i `AJAX_SAFE_SECTIONS`-ı ayrıca yoxlayır."""
        missing = sorted(_template_ajax_sections() - set(AJAX_SAFE_SECTIONS))
        self.assertEqual(
            missing,
            [],
            "Bu bölmələr `data-ajax-sections`-dadır, amma `AJAX_SAFE_SECTIONS`-da yoxdur "
            "(yəni fraqment endpoint-i onları rədd edəcək): " + ", ".join(missing),
        )

    def test_ajax_safe_sections_are_a_subset_of_registered_partials(self):
        """`AJAX_SAFE_SECTIONS`-da şablonu olmayan ad qalmasın."""
        orphan = sorted(set(AJAX_SAFE_SECTIONS) - set(SECTION_PARTIALS))
        self.assertEqual(
            orphan,
            [],
            "AJAX-safe elan olunub, amma partial şablonu qeydiyyatda yoxdur: " + ", ".join(orphan),
        )

    def test_registered_partial_templates_exist_on_disk(self):
        """Qeydiyyatdakı hər şablon yolu HƏQİQƏTƏN mövcud olsun."""
        template_dirs = [Path(settings.BASE_DIR) / "apps/accounts/templates"]
        template_dirs += [Path(directory) for directory in settings.TEMPLATES[0].get("DIRS", [])]
        missing = []
        for section, template_name in sorted(SECTION_PARTIALS.items()):
            if not any((directory / template_name).is_file() for directory in template_dirs):
                missing.append(f"{section} → {template_name}")
        self.assertEqual(missing, [], "Qeydiyyatda olan, amma diskdə tapılmayan şablonlar: " + ", ".join(missing))
