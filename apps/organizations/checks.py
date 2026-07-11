"""Django system check-ləri — DB rolunun RLS-ə tabe olmasının təsdiqi.

Audit EXAM-P0-01: PostgreSQL superuser-i (və ``BYPASSRLS`` atributlu rollar)
``FORCE ROW LEVEL SECURITY`` olsa belə RLS-i mühərrik səviyyəsində yan keçir.
Tətbiq runtime-ı superuser ilə qoşulursa bütün tenant izolyasiya zəmanəti
faktiki olaraq yox olur.

Bu check qoşulmuş rolun ``rolsuper`` / ``rolbypassrls`` atributlarını yoxlayır.
Sərtlik ``EMS_DB_ROLE_ENFORCE`` env dəyişəni ilə idarə olunur:

* ``off``   — heç nə yoxlanmır (məs. release.sh migrate addımı üçün, çünki
  miqrasiyalar qanuni olaraq owner/superuser rolu ilə işləyir);
* ``warn``  — default; superuser aşkarlanarsa checks Warning verir;
* ``error`` — superuser aşkarlanarsa deploy bloklanır (production hədəfi).
"""

import os

from django.core.checks import Error
from django.core.checks import Warning as CheckWarning
from django.core.checks import register
from django.db import connection

W_SUPERUSER_DB_ROLE = "organizations.W011"
E_SUPERUSER_DB_ROLE = "organizations.E011"

_HINT = (
    "Ayrıca LOGIN NOSUPERUSER NOBYPASSRLS tətbiq rolu yaradın "
    "(scripts/provision-app-db-role.sh) və compose-da APP_DATABASE_USER / "
    "APP_DATABASE_PASSWORD təyin edin. Miqrasiyalar MIGRATION_DATABASE_URL "
    "üzərindən owner rolu ilə işləməyə davam edir."
)


def _current_role_bypasses_rls():
    """(bypasses, rolname) — qoşulmuş rol RLS-i yan keçirmi?"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        row = cursor.fetchone()
    if not row:
        return False, ""
    return bool(row[1]), row[0]


@register("database")
def check_db_role_not_superuser(app_configs, databases=None, **kwargs):
    """DB-yə qoşulan rol superuser/BYPASSRLS olmamalıdır (EXAM-P0-01).

    Sərtlik əvvəlcə Django ``EMS_DB_ROLE_ENFORCE`` setting-indən, sonra eyni
    adlı env dəyişənindən oxunur (default ``warn``). Test/CI mühitində DB
    rolu qanuni olaraq superuser olduğu üçün ``off`` təyin edilir ki, strict
    ``check --fail-level WARNING`` addımı yanlış fail verməsin.
    """
    from django.conf import settings

    mode = getattr(settings, "EMS_DB_ROLE_ENFORCE", None) or os.environ.get("EMS_DB_ROLE_ENFORCE") or "warn"
    mode = str(mode).strip().lower()
    if mode == "off":
        return []
    if connection.vendor != "postgresql":
        return []

    try:
        bypasses, rolname = _current_role_bypasses_rls()
    except Exception:  # pragma: no cover — DB hələ hazır deyilsə check bloklamasın
        return []

    if not bypasses:
        return []

    message = (
        f"Tətbiq PostgreSQL-ə '{rolname}' rolu ilə qoşulub və bu rol RLS-i yan keçir "
        "(rolsuper və ya rolbypassrls). Tenant izolyasiyası yalnız tətbiq-qatı "
        "filtrlərə qalır."
    )
    if mode == "error":
        return [Error(message, hint=_HINT, id=E_SUPERUSER_DB_ROLE)]
    return [CheckWarning(message, hint=_HINT, id=W_SUPERUSER_DB_ROLE)]
