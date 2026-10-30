"""Jurnal müşahidəsi: kafedra kökü faktiki fənn/yük sahəsinə əsaslanır."""

from django.apps import apps as django_apps
from django.db.models import Q

from .lessons_log_units import kafedra_offering_q


def unit_journal_q(organization, scope, kafedras, *, within=None):
    """Qrup ağacı fakültə/ixtisas üçün, canonical fənn-yük xəritəsi kafedra üçün.

    Qrup kafedranın altında yerləşsə belə başqa kafedranın ona keçdiyi fənn
    həmin kafedranın jurnalı deyil. Chair-root ilə qrup ağacını OR etmək bu
    halda əhatədən kənar jurnal göstərirdi. Digər scope kökləri saxlanılır.
    """
    chair_ids = {chair.pk for chair in kafedras}
    chair_paths = {chair.path for chair in kafedras}
    other_roots = Q(pk__in=set(scope.unit_ids) - chair_ids)
    for path in scope.unit_paths:
        if path not in chair_paths:
            other_roots |= Q(path__startswith=f"{path}/")
    units = django_apps.get_model("organizations.OrgUnit").objects.filter(
        other_roots,
        organization=organization,
    )
    query = Q(group__in=units.values("pk"))
    for chair in kafedras:
        query |= kafedra_offering_q(chair, within=within)
    return Q(organization=organization) & query
