"""Role-assignment view — nazik giriş nöqtəsi (god-file refaktoru, FAZA 3.5).

Bütün məntiq `_assignment_flow._RoleAssignmentFlow`-dadır. İmport yolu
(`from .assignment import role_assignment`) dəyişməyib."""

from django.contrib.auth.decorators import login_required

from ._assignment_flow import _RoleAssignmentFlow


@login_required
def role_assignment(request):
    """Organization-scoped role assignment UI (strict server-side permission checks)."""
    return _RoleAssignmentFlow(request).run()
