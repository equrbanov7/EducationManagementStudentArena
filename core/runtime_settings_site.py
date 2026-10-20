"""«Açıq səhifələr» — «Sistem tənzimləmələri» açarları (sahib 2026-10-20).

Sahib: «contact deyilən url-i sil, sistem tənzimləmələrində saxla — istəyəndə yenidən yandırım, indilik gizlət».
Oxu nöqtəsi YALNIZ ``core.academic_rules.contact_page_enabled`` (şablonlarda ``academic_rules.contact_page``).
Söndürüləndə ``/contact/`` 404 qaytarır, menyu/footer/«Haqqımızda» keçidləri və sitemap sətri gizlənir;
gələn mesajlar (kabinetdəki «Əlaqə mesajları») silinmir.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("site", pgettext_lazy(_CTX, "Açıq səhifələr"))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            "site.contact_page", "site", "bool", lambda: bool(getattr(settings, "CONTACT_PAGE_ENABLED", False)),
            pgettext_lazy(_CTX, "«Əlaqə» səhifəsi (/contact/)"),
            pgettext_lazy(
                _CTX,
                "Söndürüləndə /contact/ ünvanı açılmır (404), menyu, footer və «Haqqımızda» səhifəsindəki «Əlaqə» "
                "keçidləri gizlənir. Əvvəl gəlmiş mesajlar silinmir. Yandırılanda səhifə və keçidlər geri qayıdır.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """``runtime_settings``-ə qrup və açarları əlavə edir; yeni ``GROUPS``-u qaytarır (idempotent)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    if any(code == GROUP[0] for code, _label in groups):
        return groups
    return groups + (GROUP,)


__all__ = ["GROUP", "build_specs", "register"]
