"""Database-level RLS tenant-isolation tests for the registrar tables.

Mirrors apps/organizations/tests/test_rls.py: data is created as the bypass
superuser, then the connection switches to the non-superuser ``rls_app_role``
(``SET LOCAL ROLE``) inside the test transaction so the RLS policies are
enforced. Each test asserts a tenant only sees its own
Program/Subject/Curriculum/CurriculumSubject rows.
"""

from django.contrib.auth import get_user_model
from django.db import connection

import pytest

from apps.organizations.models import Organization
from apps.registrar.models import Curriculum, CurriculumSubject, Program, Subject
from core.constants import OrganizationType

User = get_user_model()

pytestmark = pytest.mark.postgres


def _is_pg():
    return connection.vendor == "postgresql"


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enable_rls_for_tenant(org_id):
    """Disable bypass, pin the tenant, and drop to the restricted app role.

    The role switch is transaction-scoped (``SET LOCAL``); the surrounding
    ``db`` fixture wraps the whole test in one transaction, so it stays in
    effect for every subsequent query in the test and reverts on rollback.
    """
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    if not _is_pg():
        yield
        return
    _set("app.bypass_rls", "on")
    _set("app.current_org_id", "")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


@pytest.fixture()
def two_org_curricula():
    if not _is_pg():
        pytest.skip("registrar RLS tests require PostgreSQL")
    owner_a = User.objects.create_user("reg_a", "reg_a@x.test", "pw")
    owner_b = User.objects.create_user("reg_b", "reg_b@x.test", "pw")
    org_a = Organization.objects.create(
        name="Reg Org A",
        slug="reg-org-a",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner_a,
        status="active",
        is_active=True,
    )
    org_b = Organization.objects.create(
        name="Reg Org B",
        slug="reg-org-b",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner_b,
        status="active",
        is_active=True,
    )
    for org, code in ((org_a, "A"), (org_b, "B")):
        prog = Program.objects.create(organization=org, code=f"P-{code}", name=f"Program {code}")
        subj = Subject.objects.create(organization=org, code=f"S-{code}", name=f"Subject {code}")
        cur = Curriculum.objects.create(organization=org, program=prog, admission_year=2024)
        CurriculumSubject.objects.create(organization=org, curriculum=cur, subject=subj, semester_number=1)
    return org_a, org_b


def test_program_isolation(two_org_curricula):
    org_a, _org_b = two_org_curricula
    _enable_rls_for_tenant(org_a.pk)
    codes = set(Program.objects.values_list("code", flat=True))
    assert codes == {"P-A"}, f"tenant A saw cross-tenant programs: {codes}"


def test_subject_and_curriculum_isolation(two_org_curricula):
    _org_a, org_b = two_org_curricula
    _enable_rls_for_tenant(org_b.pk)
    subject_codes = set(Subject.objects.values_list("code", flat=True))
    curricula_years = list(Curriculum.objects.values_list("admission_year", flat=True))
    rows = CurriculumSubject.objects.count()
    assert subject_codes == {"S-B"}
    assert curricula_years == [2024]
    assert rows == 1, "tenant B must only see its own curriculum rows"


def test_missing_tenant_context_denies_all(two_org_curricula):
    _enable_rls_for_tenant("")  # no tenant → deny-all (secure default)
    assert Program.objects.count() == 0
    assert Subject.objects.count() == 0
    assert CurriculumSubject.objects.count() == 0
