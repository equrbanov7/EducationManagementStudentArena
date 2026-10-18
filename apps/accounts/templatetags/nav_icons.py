"""Kabinet naviqasiya ikonları — self-hosted SVG sprite (sahib 2026-10-11).

Sahib: «sidebardakı ikonları dəyişək, daha rəsmi görüntü olsun». Font Awesome-un
qarışıq «solid» qlifləri (robot, süpürgə, gözətçi qülləsi …) əvəzinə bir üslubda,
eyni xətt qalınlığında xətti ikonlar: Lucide v1.8.0 (ISC), yalnız istifadə olunanlar
``static/vendor/lucide/ems-nav.svg`` sprite-ındadır (CDN yoxdur — CSP yalnız `self`).

İşlətmə::

    {% load nav_icons %}
    {% nav_icon "notebook-text" "sidebar-menu-icon" %}

Nəticə ``<svg class="ems-nav-icon …" aria-hidden="true"><use href="…/ems-nav.svg#…">``
— ikon dekorativdir, bəndin adı yanındakı mətndədir (rels rejimində tooltip də
ondan oxunur). Xətt/rəng ``sidebar_icons.css``-dədir (``currentColor``).
Yeni ikon lazım olsa: adı sprite-a əlavə edin (``SPRITE_PATH`` faylının başlığına
bax); ``test_sidebar_icons.py`` şablondakı hər adın sprite-da olduğunu yoxlayır.
"""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()

#: Sprite faylı (``static/`` altında) və keş-buster (dev-də manifest heşi yoxdur).
SPRITE_PATH = "vendor/lucide/ems-nav.svg"
SPRITE_VERSION = "20261018-calculator"


def sprite_url():
    """Sprite-ın URL-i (prod-da manifest heşli ad + ``?v=``)."""
    return f"{static(SPRITE_PATH)}?v={SPRITE_VERSION}"


@register.simple_tag
def nav_icon(name, css_class=""):
    """Sprite-dan bir ikon: dekorativ (`aria-hidden`), klaviatura fokusu almır."""
    classes = f"ems-nav-icon {css_class}".strip()
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="{}#{}"></use></svg>',
        classes,
        sprite_url(),
        name,
    )
