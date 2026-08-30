"""Sillabus səthləri — MÜƏLLİM siyahı/redaktoru + KAFEDRA təsdiq ekranı.

⚠️ Bu ekranlar profil shell-inin İÇİNDƏ açılır (``SECTION_PARTIALS``) — SOL
SIDEBAR QALIR, ayrıca tam-səhifə səth DEYİL.

Cross-domain glue accounts-dadır (``apps.syllabus`` registrar/organizations
modullarını import etmir) — modul-sərhəd qrafında yeni dövr yaranmır.
"""

from .api import syllabus_action, syllabus_preview, syllabus_section_save  # noqa: F401
from .editor import build_syllabus_editor_section  # noqa: F401
from .review import build_syllabus_review_section  # noqa: F401
from .review_api import syllabus_decision, syllabus_review_open  # noqa: F401
from .section import build_syllabus_list_section  # noqa: F401

__all__ = [
    "build_syllabus_editor_section",
    "build_syllabus_list_section",
    "build_syllabus_review_section",
    "syllabus_action",
    "syllabus_decision",
    "syllabus_preview",
    "syllabus_review_open",
    "syllabus_section_save",
]
