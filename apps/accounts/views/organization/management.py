"""Student organization management view — nazik giriş nöqtəsi (god-file refaktoru, FAZA 3.5).

Bütün məntiq `_management_flow._StudentOrgManagementFlow`-dadır. İmport yolu
(`from .management import student_organization_management`) dəyişməyib."""

from django.contrib.auth.decorators import login_required

from ._management_flow import _StudentOrgManagementFlow


@login_required
def student_organization_management(request):
    """Manage student membership add/remove operations for high-level organization roles."""
    return _StudentOrgManagementFlow(request).run()
