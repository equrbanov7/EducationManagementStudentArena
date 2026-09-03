"""P1-4: «RLS gate»-in ÖZÜNÜ yoxlayan meta-test.

2026-09-02 auditinin tapıntısı: `.github/workflows/_rls-txn-pool.yml` `-m postgres`
dəstini `test_user` ilə işlədir və həmin rol PostgreSQL SUPERUSER olmalıdır
(`apps/legacy_import/migrations/0003_security_hardening.py` TRUNCATE mühafizini
superuser üçün açır, əks halda `transaction=True` testləri teardown-da flush edə
bilmir).  Superuser isə RLS-i QEYD-ŞƏRTSİZ bypass edir — nəticədə həmin işdəki
hər cross-tenant assert VAKUUM keçir və gate izolyasiya reqressiyasına görə
ÇÖKƏ BİLMİR.

Bu modul iki şeyi bağlayır:

1. **Mexanizm mövcuddur** — `rls_app_role` var, NOSUPERUSER + NOBYPASSRLS-dir.
   Rol yoxa çıxsa (miqrasiya geri alınsa) test SƏSSİZCƏ keçmir, ÇÖKÜR.
2. **Mexanizm işləyir** — həmin rola `SET LOCAL ROLE` ilə keçəndə yad tenantın
   sətri GÖRÜNMÜR, halbuki bağlantı rolu (superuser) onu görür.  Yəni suitlərin
   işlətdiyi rol-dəyişmə naxışı həqiqətən siyasətləri tətbiq edir.

Buradan çıxan CI tələbi (dəyişikliyin özü təklif kimi hesabatdadır, `.github/`
bu işdə redaktə OLUNMUR): `-m postgres` işi ya ayrıca NOBYPASSRLS rolu ilə
işləməlidir, ya da TRUNCATE-siz teardown yolu almalıdır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection, transaction

import pytest

from apps.organizations.models import Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

pytestmark = pytest.mark.postgres

RLS_ROLE = "rls_app_role"


def _skip_if_not_pg():
    if connection.vendor != "postgresql":
        pytest.skip("RLS gate integrity requires PostgreSQL")


def _scalar(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
    return row[0] if row else None


def _set(name, value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


@pytest.mark.django_db
def test_rls_enforcement_role_exists_and_cannot_bypass():
    """`rls_app_role` mövcuddur və RLS-i bypass EDƏ BİLMİR.

    Rol yoxdursa bu test ÇÖKÜR — «rol yoxdur, ona görə skip» səssiz deqradasiya
    olardı və gate-i yenidən vakuum edərdi.
    """
    _skip_if_not_pg()

    row = _scalar(
        "SELECT rolsuper::text || '/' || rolbypassrls::text FROM pg_roles WHERE rolname = %s",
        [RLS_ROLE],
    )
    assert row is not None, (
        f"{RLS_ROLE} yoxdur — RLS suitləri `SET LOCAL ROLE` edə bilmir və hər "
        "cross-tenant assert vakuum keçər (organizations/0003_rls_policies)."
    )
    assert row == "false/false", f"{RLS_ROLE} NOSUPERUSER + NOBYPASSRLS olmalıdır, indi: {row}"


@pytest.mark.django_db(transaction=False)
def test_connection_role_alone_would_make_the_gate_vacuous():
    """Bağlantı rolu superuser/BYPASSRLS-dirsə, rol-dəyişməsiz assert-lər yalançıdır.

    Test bunu ÇÖKMƏ ilə deyil, AÇIQ SƏNƏD kimi qeyd edir: superuser altında
    izolyasiya iddiası yalnız `SET LOCAL ROLE` ilə mənalıdır.  Bağlantı rolu
    onsuz da NOBYPASSRLS-dirsə (arzuolunan CI konfiqurasiyası) assert triviallaşır.
    """
    _skip_if_not_pg()

    can_bypass = _scalar("SELECT (rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname = current_user")
    if not can_bypass:
        pytest.skip("bağlantı rolu onsuz da NOBYPASSRLS — gate real işləyir")
    # Superuser altında işləyirik: aşağıdakı test rol dəyişməsinin işlədiyini sübut edir.
    assert can_bypass is True


@pytest.mark.django_db(transaction=False)
def test_set_local_role_actually_enforces_tenant_isolation():
    """Rol dəyişməsi HƏQİQƏTƏN siyasətləri tətbiq edir (mexanizmin canlı sübutu)."""
    _skip_if_not_pg()

    with bypass_rls():
        owner = User.objects.create_user("rls_gate_owner", "rls_gate_owner@qku.edu.az", "pw")
        units = {}
        for tag in ("a", "b"):
            org = Organization.objects.create(
                name=f"RLS Gate {tag.upper()}",
                slug=f"rls-gate-{tag}",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            units[tag] = OrgUnit.objects.create(
                organization=org,
                name=f"Gate unit {tag}",
                slug=f"rls-gate-unit-{tag}",
                unit_type=OrgUnitType.GROUP,
            )

    with transaction.atomic():
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", str(units["a"].organization_id))
        _set("app.current_user_id", "")
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL ROLE {RLS_ROLE}")
        visible = set(OrgUnit.objects.values_list("pk", flat=True))

    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")

    assert units["a"].pk in visible
    assert units["b"].pk not in visible, (
        "Yad tenantın bölməsi görünür — ya siyasət pozulub, ya da " f"{RLS_ROLE} artıq RLS-i bypass edir."
    )
