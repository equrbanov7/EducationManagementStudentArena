"""«Audit jurnalı» kabinet bölməsi (2026-09-08 yenidən qurulub) — əhatə,
filtrlər, səhifələmə büdcəsi, JSON detal, CSV ixrac və superadmin cross-tenant.

Nəyi qoruyur
------------
1. **Qapı.** `audit.view` daşıyıcısı (burada `teaching_office_head`) və təşkilat
   sahibi bölməni görür; müəllim/tələbə fraqment API-sindən **403** alır. Eyni
   qapı JSON detal (`audit:detail`) və CSV (`audit:export`) üçün də keçərlidir.
2. **Tenant əhatəsi.** Başqa təşkilatın qeydi siyahıda, detalda (404) və CSV-də
   GÖRÜNMÜR; `al_org` parametri qeyri-superadmin üçün nəzərə alınmır.
3. **Filtrlər** (`al_` prefiksi): dövr presetləri + seçilmiş aralıq, əməliyyat,
   resurs tipi, icraçı (o cümlədən «anonim»), «yalnız» bayraqları, axtarış
   (mətn və sorğu ID).
4. **Səhifələmə** server tərəfdədir və sorğu sayı səhifə ölçüsündən ASILI DEYİL.
5. **Detal JSON** oxunaqlı əvvəl → sonra fərqini (`added/removed/changed/same`)
   və metadata-nı qaytarır.
6. **CSV** UTF-8 BOM ilə başlayır, cari filtri tətbiq edir, ixracın özü auditə
   düşür.
7. **Superadmin** müstəqil səhifədə bütün tenantları görür və `al_org` ilə
   daraldır.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.views import RANGE_30D, RANGE_ALL, RANGE_CUSTOM, RANGE_TODAY, build_diff, resolve_range
from apps.organizations.models import Organization
from core.constants import AuditAction, OrganizationType

from .test_teaching_office_stage2 import PASSWORD, Stage2BaseTest

User = get_user_model()

SECTION = "audit-log"
VIEWER = "teaching_office_head"
UPDATE_REPR = "QA-DS2 plan v1"
OLD_REPR = "KÖHNƏ-QEYD"
OTHER_REPR = "OTHER-ORG-SECRET"
UPDATE_REASON = "Səhv kredit düzəldildi"


class AuditLogSectionBaseTest(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        role = cls.roles[VIEWER]
        role.permissions = [*role.permissions, "audit.view"]
        role.save(update_fields=["permissions"])

        cls.other_owner = User.objects.create_user("ds2_other_owner", "ds2_other_owner@qku.edu.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="Başqa Univ",
            slug="ds2-other-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.superadmin = User.objects.create_superuser("ds2_superadmin", "ds2_superadmin@qku.edu.az", PASSWORD)

        cls.request_id = uuid.uuid4()
        cls.log_update = AuditLog.objects.create(
            user=cls.owner,
            organization=cls.org,
            action=AuditAction.UPDATE,
            resource_type="curriculum",
            resource_id="7",
            resource_repr=UPDATE_REPR,
            old_values={"credits": 5, "name": "A", "note": "x"},
            new_values={"credits": 6, "name": "A", "tag": "t"},
            changes={"credits": {"old": 5, "new": 6}, "name": {"old": "A", "new": "A"}},
            reason=UPDATE_REASON,
            ip_address="10.0.0.7",
            user_agent="pytest/1.0",
            request_id=cls.request_id,
        )
        cls.log_noreason = AuditLog.objects.create(
            user=cls.users[VIEWER],
            organization=cls.org,
            action=AuditAction.UPDATE,
            resource_type="subject",
            resource_id="3",
            resource_repr="SƏBƏBSİZ-DƏYİŞİKLİK",
            reason="",
        )
        cls.log_login = AuditLog.objects.create(user=cls.owner, organization=cls.org, action=AuditAction.LOGIN)
        cls.log_anon = AuditLog.objects.create(
            user=None, organization=cls.org, action=AuditAction.DELETE, resource_repr="ANONİM-SİLİNMƏ", reason="sistem"
        )
        # Jurnal append-only-dir (PG triggeri UPDATE-i də bloklayır) — köhnə qeyd
        # `created_at`-ı yazılarkən `timezone.now` ilə verilir.
        cls.old_day = timezone.localdate() - timedelta(days=60)
        old_moment = timezone.make_aware(datetime.combine(cls.old_day, time(hour=12)))
        with patch("django.utils.timezone.now", return_value=old_moment):
            cls.log_old = AuditLog.objects.create(
                user=cls.owner, organization=cls.org, action=AuditAction.CREATE, resource_repr=OLD_REPR
            )
        cls.log_other = AuditLog.objects.create(
            user=cls.other_owner, organization=cls.other_org, action=AuditAction.CREATE, resource_repr=OTHER_REPR
        )

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _client_for(self, user, org=None):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = (org or self.org).slug
        session.save()
        return client

    def _html(self, role_name, **params):
        response = self._fragment(role_name, SECTION, **params)
        self.assertEqual(response.status_code, 200, response.content[:300])
        payload = response.json()
        self.assertTrue(payload["ok"])
        return payload["html"]

    @staticmethod
    def _row_count(html: str) -> int:
        return html.count("data-al-open")


class AuditLogSectionAccessTest(AuditLogSectionBaseTest):
    def test_viewer_sees_section_and_denied_roles_get_403(self):
        self.assertIn(SECTION, self._sections(VIEWER))
        for role in ("teacher", "student", "chair_head"):
            with self.subTest(role=role):
                self.assertEqual(self._fragment(role, SECTION).status_code, 403)

    def test_fragment_renders_shell_kpis_filters_and_assets(self):
        html = self._html(VIEWER)
        self.assertIn("data-al-root", html)
        self.assertIn("audit/css/audit_log.css", html)
        self.assertIn('data-ems-kpi-filter="noreason"', html)
        self.assertIn('data-ems-kpi-filter="failed"', html)
        self.assertIn('data-param-prefix="al_"', html)
        self.assertIn('name="al_range"', html)
        self.assertIn('name="al_from"', html)
        self.assertIn('name="al_actor"', html)
        self.assertIn(reverse("audit:export"), html)
        self.assertIn('id="alDetailDrawer"', html)
        # Superadmin-ə məxsus «Təşkilat» filtri adi istifadəçiyə açılmır.
        self.assertNotIn('name="al_org"', html)
        self.assertNotIn("<style", html)
        self.assertNotIn('style="', html)

    def test_rows_are_org_scoped(self):
        html = self._html(VIEWER, al_range=RANGE_ALL)
        self.assertIn(UPDATE_REPR, html)
        self.assertIn(OLD_REPR, html)
        self.assertNotIn(OTHER_REPR, html)
        self.assertIn(reverse("audit:detail", kwargs={"pk": self.log_update.pk}), html)

    def test_org_param_is_ignored_for_non_superadmin(self):
        html = self._html(VIEWER, al_range=RANGE_ALL, al_org=str(self.other_org.pk))
        self.assertIn(UPDATE_REPR, html)
        self.assertNotIn(OTHER_REPR, html)

    def test_owner_can_open_standalone_page(self):
        response = self._client_for(self.owner).get(reverse("audit:list"), {"al_range": RANGE_ALL})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "audit/list.html")
        html = response.content.decode()
        self.assertIn(UPDATE_REPR, html)
        self.assertNotIn(OTHER_REPR, html)
        self.assertIn("audit/js/audit_log.js", html)

    def test_teacher_gets_403_on_standalone_page(self):
        response = self._client("teacher").get(reverse("audit:list"))
        self.assertEqual(response.status_code, 403)


class AuditLogSectionFilterTest(AuditLogSectionBaseTest):
    def test_default_range_hides_old_entries_and_all_time_shows_them(self):
        self.assertNotIn(OLD_REPR, self._html(VIEWER))
        self.assertIn(OLD_REPR, self._html(VIEWER, al_range=RANGE_ALL))

    def test_custom_range_uses_inclusive_local_days(self):
        iso = self.old_day.isoformat()
        html = self._html(VIEWER, al_range=RANGE_CUSTOM, al_from=iso, al_to=iso)
        self.assertIn(OLD_REPR, html)
        self.assertNotIn(UPDATE_REPR, html)
        self.assertEqual(self._row_count(html), 1)

    def test_action_filter(self):
        html = self._html(VIEWER, al_action=AuditAction.DELETE)
        self.assertIn("ANONİM-SİLİNMƏ", html)
        self.assertNotIn(UPDATE_REPR, html)
        self.assertEqual(self._row_count(html), 1)

    def test_no_reason_flag(self):
        html = self._html(VIEWER, al_flag="noreason")
        self.assertIn("SƏBƏBSİZ-DƏYİŞİKLİK", html)
        self.assertIn("Səbəb göstərilməyib", html)
        self.assertNotIn(UPDATE_REPR, html)

    def test_anonymous_actor_filter(self):
        html = self._html(VIEWER, al_actor="none")
        self.assertIn("ANONİM-SİLİNMƏ", html)
        self.assertIn("Anonim / sistem", html)
        self.assertNotIn(UPDATE_REPR, html)

    def test_actor_filter_by_user_pk(self):
        html = self._html(VIEWER, al_actor=str(self.users[VIEWER].pk))
        self.assertIn("SƏBƏBSİZ-DƏYİŞİKLİK", html)
        self.assertNotIn(UPDATE_REPR, html)

    def test_resource_type_filter(self):
        html = self._html(VIEWER, al_resource="rt:curriculum")
        self.assertIn(UPDATE_REPR, html)
        self.assertNotIn("SƏBƏBSİZ-DƏYİŞİKLİK", html)

    def test_search_matches_reason_and_request_id(self):
        html = self._html(VIEWER, al_q=UPDATE_REASON)
        self.assertIn(UPDATE_REPR, html)
        self.assertEqual(self._row_count(html), 1)
        html = self._html(VIEWER, al_range=RANGE_ALL, al_q=str(self.request_id))
        self.assertIn(UPDATE_REPR, html)
        self.assertEqual(self._row_count(html), 1)

    def test_applied_chips_and_empty_state(self):
        html = self._html(VIEWER, al_action=AuditAction.VERIFY)
        self.assertIn("ems-applied__chip", html)
        self.assertIn("Filtrə uyğun hadisə yoxdur", html)
        self.assertEqual(self._row_count(html), 0)

    def test_invalid_values_fall_back_to_defaults(self):
        html = self._html(VIEWER, al_range="bogus", al_action="bogus", al_size="7", al_actor="not-a-pk")
        self.assertIn(UPDATE_REPR, html)
        self.assertNotIn(OLD_REPR, html)

    def test_resolve_range_presets(self):
        today = date(2026, 9, 8)
        self.assertEqual(resolve_range(RANGE_TODAY, "", "", today=today), (RANGE_TODAY, today, today))
        self.assertEqual(resolve_range(RANGE_30D, "", "", today=today), (RANGE_30D, date(2026, 8, 10), today))
        self.assertEqual(resolve_range(RANGE_ALL, "", "", today=today), (RANGE_ALL, None, None))
        # Tərs verilmiş aralıq düzəldilir; boş «custom» defolta düşür.
        self.assertEqual(
            resolve_range(RANGE_CUSTOM, "2026-09-05", "2026-09-01", today=today),
            (RANGE_CUSTOM, date(2026, 9, 1), date(2026, 9, 5)),
        )
        self.assertEqual(resolve_range(RANGE_CUSTOM, "", "", today=today)[0], RANGE_30D)


class AuditLogSectionPaginationTest(AuditLogSectionBaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        AuditLog.objects.bulk_create(
            [
                AuditLog(
                    user=cls.owner,
                    organization=cls.org,
                    action=AuditAction.VIEW,
                    resource_type="bulkprobe",
                    resource_id=str(index),
                    resource_repr=f"BULK-{index:02d}",
                )
                for index in range(30)
            ]
        )

    def test_page_size_and_second_page(self):
        first = self._html(VIEWER, al_resource="rt:bulkprobe")
        self.assertEqual(self._row_count(first), 25)
        self.assertIn("al_page=2", first)
        second = self._html(VIEWER, al_resource="rt:bulkprobe", al_page="2")
        self.assertEqual(self._row_count(second), 5)
        wide = self._html(VIEWER, al_resource="rt:bulkprobe", al_size="50")
        self.assertEqual(self._row_count(wide), 30)
        self.assertNotIn("al_page=2", wide)

    def test_query_count_is_independent_of_page_size(self):
        client = self._client(VIEWER)
        url = reverse("accounts:profile_section_fragment", kwargs={"section": SECTION})
        # İlk sorğu keşləri (ContentType, icazə keşi) isidir — büdcə ondan sonra ölçülür.
        self.assertEqual(client.get(url, {"al_resource": "rt:bulkprobe"}).status_code, 200)
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(client.get(url, {"al_resource": "rt:bulkprobe", "al_size": "25"}).status_code, 200)
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(client.get(url, {"al_resource": "rt:bulkprobe", "al_size": "100"}).status_code, 200)
        self.assertEqual(
            len(small),
            len(large),
            "\n".join(
                sorted(
                    {q["sql"][:160] for q in large.captured_queries} ^ {q["sql"][:160] for q in small.captured_queries}
                )
            ),
        )


class AuditLogDetailEndpointTest(AuditLogSectionBaseTest):
    def _url(self, log):
        return reverse("audit:detail", kwargs={"pk": log.pk})

    def test_viewer_gets_readable_diff_and_metadata(self):
        response = self._client(VIEWER).get(self._url(self.log_update))
        self.assertEqual(response.status_code, 200)
        entry = response.json()["entry"]
        self.assertEqual(entry["id"], str(self.log_update.pk))
        self.assertEqual(entry["action"], AuditAction.UPDATE)
        self.assertEqual(entry["actor"]["username"], self.owner.username)
        self.assertEqual(entry["resource"]["repr"], UPDATE_REPR)
        self.assertEqual(entry["reason"], UPDATE_REASON)
        self.assertTrue(entry["reason_required"])
        self.assertEqual(entry["ip_address"], "10.0.0.7")
        self.assertEqual(entry["user_agent"], "pytest/1.0")
        self.assertEqual(entry["request_id"], str(self.request_id))
        states = {item["key"]: item["state"] for item in entry["diff"]}
        self.assertEqual(states, {"credits": "changed", "name": "same"})
        self.assertEqual(entry["changed_count"], 1)
        self.assertIn("al_actor=", entry["filter_links"]["actor"])
        self.assertIn(str(self.request_id), entry["filter_links"]["request"])
        self.assertEqual(entry["raw"]["changes"], self.log_update.changes)

    def test_diff_falls_back_to_old_and_new_values(self):
        rows = {item["key"]: item for item in build_diff({"a": 1, "b": 2, "c": None}, {"a": 1, "b": 3, "d": 4}, None)}
        self.assertEqual(rows["a"]["state"], "same")
        self.assertEqual(rows["b"]["state"], "changed")
        self.assertEqual(rows["c"]["state"], "removed")
        self.assertEqual(rows["d"]["state"], "added")
        self.assertEqual(build_diff(None, None, None), [])

    def test_teacher_gets_403(self):
        response = self._client("teacher").get(self._url(self.log_update))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_other_tenant_entry_is_404_for_org_viewer(self):
        self.assertEqual(self._client(VIEWER).get(self._url(self.log_other)).status_code, 404)

    def test_anonymous_is_redirected(self):
        response = Client().get(self._url(self.log_update))
        self.assertEqual(response.status_code, 302)

    def test_superadmin_reads_any_tenant(self):
        response = self._client_for(self.superadmin, org=self.other_org).get(self._url(self.log_other))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entry"]["resource"]["repr"], OTHER_REPR)


class AuditLogExportTest(AuditLogSectionBaseTest):
    def _rows(self, response):
        body = b"".join(response.streaming_content).decode("utf-8")
        self.assertTrue(body.startswith("\ufeff"), "CSV UTF-8 BOM ilə başlamalıdır")
        return list(csv.reader(io.StringIO(body.lstrip("\ufeff"))))

    def test_teacher_gets_403(self):
        self.assertEqual(self._client("teacher").get(reverse("audit:export")).status_code, 403)

    def test_export_is_org_scoped_and_filtered(self):
        before = AuditLog.objects.filter(action=AuditAction.EXPORT, resource_type="audit_log").count()
        response = self._client(VIEWER).get(reverse("audit:export"), {"al_range": RANGE_ALL})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn(".csv", response["Content-Disposition"])
        rows = self._rows(response)
        header, body = rows[0], rows[1:]
        self.assertIn("Vaxt", header)
        self.assertIn("Sorğu ID", header)
        reprs = {row[6] for row in body}
        self.assertIn(UPDATE_REPR, reprs)
        self.assertIn(OLD_REPR, reprs)
        self.assertNotIn(OTHER_REPR, reprs)
        self.assertEqual(int(response["X-Audit-Export-Rows"]), len(body))
        self.assertEqual(response["X-Audit-Export-Truncated"], "0")
        update_row = next(row for row in body if row[6] == UPDATE_REPR)
        self.assertEqual(update_row[1], self.owner.username)
        self.assertEqual(update_row[8], UPDATE_REASON)
        self.assertEqual(update_row[10], str(self.request_id))
        self.assertIn('"credits"', update_row[11])
        # İxracın özü auditə düşür.
        self.assertEqual(
            AuditLog.objects.filter(action=AuditAction.EXPORT, resource_type="audit_log").count(), before + 1
        )

        filtered = self._client(VIEWER).get(reverse("audit:export"), {"al_range": RANGE_ALL, "al_action": "login"})
        reprs = {row[6] for row in self._rows(filtered)[1:]}
        self.assertNotIn(UPDATE_REPR, reprs)

    def test_anonymous_is_redirected(self):
        self.assertEqual(Client().get(reverse("audit:export")).status_code, 302)


class AuditLogSuperadminTest(AuditLogSectionBaseTest):
    def test_superadmin_sees_all_tenants_and_can_narrow_by_org(self):
        client = Client()
        client.force_login(self.superadmin)
        response = client.get(reverse("audit:list"), {"al_range": RANGE_ALL})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(UPDATE_REPR, html)
        self.assertIn(OTHER_REPR, html)
        self.assertIn('name="al_org"', html)

        narrowed = client.get(reverse("audit:list"), {"al_range": RANGE_ALL, "al_org": str(self.other_org.pk)})
        html = narrowed.content.decode()
        self.assertIn(OTHER_REPR, html)
        self.assertNotIn(UPDATE_REPR, html)

    def test_superadmin_export_spans_tenants(self):
        client = Client()
        client.force_login(self.superadmin)
        response = client.get(reverse("audit:export"), {"al_range": RANGE_ALL})
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn(OTHER_REPR, body)
        self.assertIn(UPDATE_REPR, body)
