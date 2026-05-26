"""
Role management views package.

Split out of a single ~1,250-line ``roles.py`` module. Each of the three RBAC
views now lives in its own module; this ``__init__`` re-exports them so
existing imports (``from .roles import ...`` in ``views/__init__.py``,
``views.role_assignment`` in the URLConf) keep working unchanged.

Modules:
* ``manage``      — ``manage_roles``
* ``assignment``  — ``role_assignment``
* ``permissions`` — ``permission_editor``
"""

from .assignment import role_assignment
from .manage import manage_roles
from .permissions import permission_editor

__all__ = [
    "manage_roles",
    "role_assignment",
    "permission_editor",
]
