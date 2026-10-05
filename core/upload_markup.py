"""Brauzerdə skript icra edə bilən markup tiplərinin uzantıdan tanınması.

2026-10-05 təhlükəsizlik auditi: ``core.media_views`` serve zamanı ``Content-Type``-ı
``mimetypes.guess_type`` ilə təyin edir. ``core.upload_security`` block-list-ində
unudulmuş hər ``+xml`` / HTML / JavaScript uzantısı (``.xht``, ``.rdf``, ``.rss`` …)
müştəri ``Content-Type: text/plain`` göndərəndə ``text/`` prefiksi ilə keçirdi və
öz origin-imizdə XHTML kimi icra olunurdu. Bu yoxlama həmin ikinci qatdır.
"""

from __future__ import annotations

import mimetypes

#: ``mimetypes`` bunları XHTML / ``+xml`` kimi tanıyır — serve zamanı brauzer
#: XML/XHTML sənədində skripti icra edir (``upload_security`` block-list-inə qatılır).
MARKUP_EXTENSIONS = frozenset({".xht", ".xpdl", ".rdf", ".wsdl", ".rss", ".atom", ".xul", ".dtd", ".xbl", ".xsd"})

_MARKUP_TYPES = frozenset({"application/xml", "text/xml", "text/xsl", "text/html", "application/xml-dtd"})


def guessed_type_is_markup(file_name: str) -> bool:
    """Uzantıdan təxmin edilən MIME brauzerdə skript icra edə bilən markup-dırmı."""
    guessed = (mimetypes.guess_type(file_name or "")[0] or "").lower()
    if not guessed:
        return False
    return guessed.endswith("+xml") or guessed in _MARKUP_TYPES or "javascript" in guessed or "ecmascript" in guessed


__all__ = ["MARKUP_EXTENSIONS", "guessed_type_is_markup"]
