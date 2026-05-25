"""
Organization views package.

Split out of a single ~1,400-line ``organization.py`` module. Each of the four
views now lives in its own module; this ``__init__`` re-exports them so
existing imports (``from .organization import ...`` in ``views/__init__.py``,
``views.student_organization_management`` in the URLConf) keep working
unchanged.

Modules:
* ``management``  — ``student_organization_management``
* ``requests``    — ``student_organization_request``
* ``invitations`` — ``student_org_invitation_action``
* ``leave``       — ``student_leave_organization``
"""

from .invitations import student_org_invitation_action
from .leave import student_leave_organization
from .management import student_organization_management
from .requests import student_organization_request

__all__ = [
    "student_organization_management",
    "student_organization_request",
    "student_org_invitation_action",
    "student_leave_organization",
]
