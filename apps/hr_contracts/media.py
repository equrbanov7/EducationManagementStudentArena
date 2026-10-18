"""Qorunan media — əmək müqaviləsinin faylı (``core.media_policies`` runtime reyestri, default DENY).

Faylı görür: müqavilənin İŞÇİSİ (qaralama / ləğv edilmiş qaralama HEÇ VAXT — rəy A2) və müqaviləni struktur əhatəsində görən heyət
(``hr.contracts_view`` / ``hr.contracts_manage``). Tapılmayan / dublikat yol → ``False`` (``media_views`` 404 verir).
"""

from __future__ import annotations

from .constants import EMPLOYEE_VISIBLE_STATUSES
from .models import EmploymentContract
from .services.access import actor_for


def check_file_access(user, path: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    try:
        contract = EmploymentContract.objects.select_related("organization", "unit").get(file=path)
    except (EmploymentContract.DoesNotExist, EmploymentContract.MultipleObjectsReturned):
        return False
    if contract.employee_id == user.pk and contract.status in EMPLOYEE_VISIBLE_STATUSES:
        return True
    return actor_for(user, contract.organization).sees(contract)


__all__ = ["check_file_access"]
