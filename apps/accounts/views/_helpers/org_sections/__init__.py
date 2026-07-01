"""org_sections — student-org section builder-ləri (god-file refaktoru)."""

from .management import _build_student_org_management_section  # noqa: F401
from .request_section import _build_student_org_request_section  # noqa: F401

__all__ = ["_build_student_org_management_section", "_build_student_org_request_section"]
