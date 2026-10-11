"""Sillabus test dəstinin ortaq fixture-ları."""

import pytest


@pytest.fixture(autouse=True)
def selfwork_rule(settings):
    """Sahib 2026-10-11: sillabus qaydası semestrdən asılı deyil — defoltda sərbəst iş SÖNDÜRÜLÜDÜR və
    ``self`` bölməsi redaktorda yoxdur (ona yazı ``section.unknown`` verir). Bu dəstin fixture-ları 8
    bölməni (sərbəst iş daxil) doldurur, ona görə RİM «Sistem tənzimləmələri» sərbəst işi yandırmış
    kimi işləyir. Söndürülü (defolt) qaydanı ``test_*selfwork_rule_2026_10_10.py`` dəstləri yoxlayır.

    Söndürülü qaydanı yoxlayan modul bu fixture-u eyni adla əvəzləyir (``test_selfwork_rule_2026_10_10.py``);
    ayrı-ayrı testlər ``settings.ACADEMIC_SELFWORK_ENABLED`` ilə öz dəyərini yazır."""
    settings.ACADEMIC_SELFWORK_ENABLED = True
