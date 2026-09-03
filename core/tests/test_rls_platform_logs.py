"""Audit / təhlükəsizlik / AI jurnallarının tenant izolyasiyası (RLS).

2026-09-02 auditinin D bölməsi canlı klonda ``pg_class``/``pg_policy``-dən oxudu:
``organization_id`` daşıyan 79 cədvəldən **75-inin** siyasəti var idi.  Qalan
dördündən üçü bu modulda bağlanır:

* ``audit_auditlog`` (klonda 22 301 sətir — tenantlararası kim-nə-etdi izi),
* ``monitoring_securityevent`` (təhlükəsizlik telemetriyası),
* ``ai_assistant_aiassistantlog`` (istifadəçi prompt mətnləri).

Dördüncü — ``accounts_userprofile`` — QƏSDƏN toxunulmur; səbəb və təklif
``docs/audits/2026-09-02/PHASE23_SECURITY_FIXES.md``-dədir.

Testlər ``emsarena_agent`` kimi superuser altında MƏNASIZ olardı (superuser
RLS-i qeyd-şərtsiz bypass edir), ona görə hər assert tranzaksiya daxilində
``SET LOCAL ROLE rls_app_role`` ilə NOBYPASSRLS roluna keçir — ``registrar``,
``organizations`` və ``syllabus`` RLS suitləri ilə eyni naxış.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection, transaction

import pytest

from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

pytestmark = pytest.mark.postgres

RLS_ROLE = "rls_app_role"


def _skip_if_not_pg():
    if connection.vendor != "postgresql":
        pytest.skip("RLS testləri PostgreSQL tələb edir")


def _set(name, value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _as_tenant(org_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cursor:
        cursor.execute(f"SET LOCAL ROLE {RLS_ROLE}")


def _reset():
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")


@pytest.fixture()
def two_orgs(db):
    _skip_if_not_pg()
    with bypass_rls():
        owner = User.objects.create_user("plog_owner", "plog_owner@qku.edu.az", "pw")
        orgs = []
        for tag in ("a", "b"):
            orgs.append(
                Organization.objects.create(
                    name=f"PLOG {tag.upper()}",
                    slug=f"plog-{tag}",
                    org_type=OrganizationType.UNIVERSITY,
                    owner=owner,
                    status="active",
                    is_active=True,
                )
            )
    return orgs[0], orgs[1], owner


def _visible_ids(model, org_id):
    with transaction.atomic():
        _as_tenant(org_id)
        ids = set(model.objects.values_list("pk", flat=True))
    _reset()
    return ids


def test_audit_log_is_tenant_isolated(two_orgs):
    from apps.audit.models import AuditLog

    org_a, org_b, _owner = two_orgs
    with bypass_rls():
        row_a = AuditLog.objects.create(action="view", organization=org_a, resource_type="plog")
        row_b = AuditLog.objects.create(action="view", organization=org_b, resource_type="plog")
        row_global = AuditLog.objects.create(action="login", organization=None, resource_type="plog")

    visible = _visible_ids(AuditLog, org_a.pk)

    assert row_a.pk in visible
    assert row_b.pk not in visible, "yad tenantın audit sətri görünür"
    # Org-suz sətir QƏSDƏN görünür: login/logout kimi platforma hadisələri.
    assert row_global.pk in visible


def test_security_event_is_tenant_isolated(two_orgs):
    from apps.monitoring.models import SecurityEvent

    org_a, org_b, _owner = two_orgs
    with bypass_rls():
        row_a = SecurityEvent.objects.create(event_type="login_failed", organization=org_a)
        row_b = SecurityEvent.objects.create(event_type="login_failed", organization=org_b)
        row_global = SecurityEvent.objects.create(event_type="login_failed", organization=None)

    visible = _visible_ids(SecurityEvent, org_a.pk)

    assert row_a.pk in visible
    assert row_b.pk not in visible
    assert row_global.pk in visible


def test_ai_assistant_log_is_tenant_isolated(two_orgs):
    from apps.ai_assistant.models import AIAssistantLog

    org_a, org_b, owner = two_orgs
    with bypass_rls():
        row_a = AIAssistantLog.objects.create(user=owner, organization=org_a, prompt="a")
        row_b = AIAssistantLog.objects.create(user=owner, organization=org_b, prompt="b")

    visible = _visible_ids(AIAssistantLog, org_a.pk)

    assert row_a.pk in visible
    assert row_b.pk not in visible


def test_audit_writes_are_not_blocked_by_the_policy(two_orgs):
    """``WITH CHECK`` qəsdən permissivdir — iz itkisi qorumadan pisdir.

    ``core.audit.log_action`` ``bypass_rls()`` ilə sarınmır və çağıranların
    çoxu xətanı udur; sərt yazı yoxlaması auditi SƏSSİZCƏ dayandırardı.
    Sətirlərin dəyişməzliyi onsuz da trigger ilə təmin olunur
    (``organizations.0019_audit_log_append_only``).
    """
    from apps.audit.models import AuditLog

    org_a, org_b, _owner = two_orgs
    with transaction.atomic():
        _as_tenant(org_a.pk)
        # Cari tenant A ikən B üçün sətir yazmaq (cross-org superadmin qeydi).
        created = AuditLog.objects.create(action="view", organization=org_b, resource_type="plog-write")
        assert created.pk is not None
    _reset()
