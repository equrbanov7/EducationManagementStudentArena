"""
Organization views package.

Split out of a single ~1,400-line ``organization.py`` module. Each view lives in
its own module; this ``__init__`` re-exports them so existing imports
(``from .organization import ...`` in ``views/__init__.py``,
``views.student_organization_management`` in the URLConf) keep working
unchanged.

Modules:
* ``management``  — ``student_organization_management``
* ``invitations`` — ``student_org_invitation_action``

URL auditi B3/A7 (2026-10-10): ``leave`` (``student_leave_organization``) və
``requests`` (``student_organization_request``) silindi — modellər qalır.
"""

from .invitations import student_org_invitation_action
from .management import student_organization_management

__all__ = [
    "student_organization_management",
    "student_org_invitation_action",
]
