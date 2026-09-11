"""View-as sessiyasının «1-2 iş görən kimi» bitməsi — 2026-09-12 (sahib şikayəti).

Sahib: «Başqa səhifəyə RİM rəhbəri kimi keçəndə 1-2 iş görən kimi atır, öz
səhifəmə çıxardır məni… “Bu bölməyə icazəniz yoxdur” yazır».

İki ayrı qüsur var idi:

1. **Kök səbəb — RLS.** ``resolve_view_as_request`` 60 saniyədən bir aktorun
   icazəsini tam yenidən yoxlayır (``validate_target`` → üzvlük sorğuları).
   Bu yoxlama ``ViewAsMiddleware``-də, yəni ``OrganizationMiddleware``-dən
   ƏVVƏL — tenant konteksti hələ BOŞ ikən — işləyir. ``organizations_membership``
   RLS ilə qorunduğundan sorğu sıfır sətir qaytarırdı → aktor «icazəsiz»
   sayılıb sessiya ``view_as_permission_revoked`` ilə bitirilirdi. Superuser
   olmayan bağlantı rolunda (prod ``emsarena_app``, QA klonu) hər 60 saniyədən
   sonrakı ilk sorğu məhz bunu edirdi.

2. **Nəticənin gizlədilməsi.** Sessiya bitəndən sonra sorğu ƏSL istifadəçi kimi
   davam etdirilirdi: AJAX bölmə sorğusu əsl istifadəçinin bölməsini köhnə
   qabığa yerləşdirirdi (tələbə qabığında müəllimin jurnal siyahısı), tam
   səhifə isə hədəfin bölməsinə icazəsi olmadığından «icazəniz yoxdur» yazırdı;
   yazma sorğusu (POST) isə əsl istifadəçinin adından İCRA olunurdu.

Bu testlər hər ikisini kilidləyir.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection, transaction
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

import pytest

from apps.accounts.models import ProfileRole
from apps.accounts.services.view_as import (
    MODE_FULL,
    VIEW_AS_SESSION_KEY,
    actor_limited_write_url_names,
    resolve_view_as_request,
)
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"
#: `organizations/0003_rls_policies` — NOSUPERUSER + NOBYPASSRLS test rolu.
RLS_ROLE = "rls_app_role"


def _make_role(organization, name, level, permissions=None):
    role, _ = Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": permissions or [],
        },
    )
    return role


def _add_member(user, organization, role):
    return Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": role, "is_active": True, "is_primary": True},
    )[0]


def _build_org(tag="va"):
    owner = User.objects.create_user(f"{tag}_owner", f"{tag}_owner@example.com", PASSWORD)
    org = Organization.objects.create(
        name=f"View-as {tag}",
        slug=f"view-as-{tag}",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    admin_role = _make_role(org, ProfileRole.ORG_ADMIN, 80)
    ikt_role = _make_role(org, ProfileRole.IKT_REHBER, 88)
    student_role = _make_role(org, ProfileRole.STUDENT, 10)
    admin = User.objects.create_user(f"{tag}_admin", f"{tag}_admin@example.com", PASSWORD)
    ikt = User.objects.create_user(f"{tag}_ikt", f"{tag}_ikt@example.com", PASSWORD)
    student = User.objects.create_user(f"{tag}_student", f"{tag}_student@example.com", PASSWORD)
    _add_member(admin, org, admin_role)
    _add_member(ikt, org, ikt_role)
    _add_member(student, org, student_role)
    return org, admin, ikt, student


def _stale_state(actor, target, org, mode=MODE_FULL, *, age_seconds=600):
    """60 saniyəlik yenidən-yoxlama pəncərəsi ÇOXDAN keçmiş sessiya vəziyyəti."""
    old = (datetime.now(dt_timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    return {
        "target_id": str(target.pk),
        "org_id": str(org.pk),
        "org_slug": org.slug,
        "mode": mode,
        "real_id": str(actor.pk),
        "prev_org_slug": org.slug,
        "started_at": old,
        "checked_at": old,
    }


# ── 1. Kök səbəb: RLS altında yenidən-yoxlama ─────────────────────────────────


def _skip_if_not_pg():
    if connection.vendor != "postgresql":
        pytest.skip("RLS testləri PostgreSQL tələb edir")


def _set(name, value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enter_empty_tenant_context_as_app_role():
    """Middleware-in vəziyyəti: bypass söndürülüb, tenant BOŞ, NOBYPASSRLS rolu."""
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")
    _set("app.current_user_id", "")
    with connection.cursor() as cursor:
        cursor.execute(f"SET LOCAL ROLE {RLS_ROLE}")


def _request_with_session(user, path, state, org):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    request.session["active_organization"] = org.slug
    request.session[VIEW_AS_SESSION_KEY] = state
    request.user = user
    return request


@pytest.mark.django_db(transaction=False)
def test_full_recheck_survives_empty_tenant_context_under_rls():
    """60 saniyədən sonrakı ilk sorğu — RLS altında sessiya YAŞAMALIDIR."""
    _skip_if_not_pg()
    with bypass_rls():
        org, admin, _ikt, student = _build_org("rls1")
    request = _request_with_session(
        admin, "/accounts/profile/?section=my-transcript", _stale_state(admin, student, org), org
    )

    with transaction.atomic():
        _enter_empty_tenant_context_as_app_role()
        target, mode = resolve_view_as_request(request)
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")

    assert target is not None and target.pk == student.pk, "aktor RLS boşluğu üzündən «icazəsiz» sayıldı"
    assert mode == MODE_FULL
    state = request.session.get(VIEW_AS_SESSION_KEY)
    assert state is not None, "sessiya səhvən bitirildi"
    assert state["checked_at"] != _stale_state(admin, student, org)["checked_at"]


@pytest.mark.django_db(transaction=False)
def test_limited_write_allowlist_survives_empty_tenant_context_under_rls():
    """İKT-nin LIMITED yazma siyahısı da middleware-də (boş tenant) hesablanır."""
    _skip_if_not_pg()
    with bypass_rls():
        org, _admin, ikt, _student = _build_org("rls2")

    with transaction.atomic():
        _enter_empty_tenant_context_as_app_role()
        allowed = actor_limited_write_url_names(ikt, org)
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")

    assert allowed, "İKT-nin icazə siyahısı boş qayıtdı — hər yazma «əhatədən kənar» kimi bloklanardı"


# ── 2. Sessiya bitəndə sorğu əsl istifadəçi kimi DAVAM ETMİR ─────────────────


class ViewAsSessionEndedRequestTests(TestCase):
    """Middleware sessiyanı bitirəndə: JSON → 409 + yönləndirmə; səhifə → panel; POST → icra olunmur."""

    def setUp(self):
        self.client = Client()
        self.org, self.admin, self.ikt, self.student = _build_org("end")
        self.client.force_login(self.admin)
        self._install_broken_state()

    def _install_broken_state(self):
        """`real_id` uyğunsuzluğu — middleware sessiyanı `view_as_invalid_real_user` ilə bitirir."""
        session = self.client.session
        session["active_organization"] = self.org.slug
        state = _stale_state(self.admin, self.student, self.org)
        state["real_id"] = "0"
        session[VIEW_AS_SESSION_KEY] = state
        session.save()

    def test_ajax_section_fragment_gets_409_with_redirect(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "my-transcript"})
        response = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertTrue(payload["view_as_ended"])
        self.assertEqual(payload["redirect"], reverse("accounts:profile"))
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_full_page_section_request_redirects_to_own_dashboard(self):
        response = self.client.get(reverse("accounts:profile") + "?section=my-transcript")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:profile"))

        followed = self.client.get(response["Location"])
        self.assertEqual(followed.status_code, 200)
        self.assertNotContains(followed, 'data-section-denied="1"')

    def test_dashboard_get_renders_with_session_ended_message(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-section-denied="1"')
        texts = [str(m.message) for m in get_messages(response.wsgi_request)]
        self.assertTrue(texts, "«sessiya bitdi» mesajı yoxdur")

    def test_post_is_not_executed_as_the_real_user(self):
        response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile", "first_name": "Ələ-keçirilmiş", "last_name": "X"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:profile"))
        self.admin.refresh_from_db()
        self.assertNotEqual(self.admin.first_name, "Ələ-keçirilmiş")
