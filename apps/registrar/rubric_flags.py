"""Rubrik qiymətləndirməsinin görünürlük bayrağı (sahib 2026-10-10: «lazım deyilsə göstərmə»).

``REGISTRAR_RUBRICS_ENABLED`` (defolt ``False``, .env ilə açılır) söndürülü ikən:

* ``registrar:rubric_grade`` səhifəsi 404 verir (GET/POST — bal yazılmır);
* kataloq konsolunun «Rubriklər» tabı, onun siyahı/dəyər/yadda saxla əməlləri yoxdur.

Modellər, ``rubrics.py`` xidməti, mövcud data və komponent balı məntiqi
(``interim_components`` «rubrik sübutu» yoxlamaları) TOXUNULMUR — bayraq açılan kimi
hər şey əvvəlki kimi qayıdır.
"""

from __future__ import annotations

from django.conf import settings


def rubrics_enabled() -> bool:
    return bool(getattr(settings, "REGISTRAR_RUBRICS_ENABLED", False))


__all__ = ["rubrics_enabled"]
