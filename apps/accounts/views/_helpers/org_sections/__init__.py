"""org_sections — student-org section builder-ləri (god-file refaktoru)."""

from .management import _build_student_org_management_section  # noqa: F401

# URL auditi A7 (2026-10-10): `request_section` («Təşkilata qoşul» bölməsi) silindi.
__all__ = ["_build_student_org_management_section"]
