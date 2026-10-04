"""«Təhlükəsizlik» tabının IP filtri (sahib 2026-10-05).

Yoxlanır:
* ``?ip=`` hadisələri daraldır (tək IPv4/IPv6 və CIDR şəbəkəsi), ``type`` ilə birləşir, cavabda
  ``ip_filter`` meta-sı var;
* yararsız IP → 400 JSON (``status=error``, ``error=invalid_ip``, tərcümə olunmuş ``detail``) — heç vaxt 500;
* IP verilibsə ``data.logins`` — həmin IP-dən UĞURLU girişlər (AuditLog ``action=login``), (IP, hesab,
  cihaz) qrupları, ən yenisi əvvəl; IP yoxdursa açar da yoxdur;
* RİM rəhbəri yalnız ÖZ təşkilatının AKTİV üzvlərinin girişlərini görür (login sətirləri org-suzdur —
  RLS onları hamıya açır, ona görə açıq filtr var); superadmin hamısını;
* icazə: müəllim 403 (yararsız IP ilə də — qapı doğrulamadan ƏVVƏL), anonim 401;
* qısa user-agent etiketi; şəbəkə filtri PostgreSQL-siz rədd olunur; ön tərəf faylları və mətn adası.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.monitoring.models import SecurityEvent
from apps.monitoring.permissions import MonitoringScope
from apps.monitoring.security_ip import InvalidIpFilter, parse_ip_filter, short_user_agent, successful_logins
from apps.organizations.models import Membership, Organization
from core.constants import AuditAction, OrganizationType

User = get_user_model()

CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Mobile/15E148 Safari/604.1"
)
SAFARI_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Safari/605.1.15"
)
CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Mobile Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
BASE_TIME = datetime(2026, 10, 5, 8, 0, tzinfo=dt_timezone.utc)

ACCOUNTS = Path(__file__).resolve().parents[2] / "accounts"
SECTIONS = ACCOUNTS / "templates" / "accounts" / "profile" / "sections" / "superadmin"
MONITORING_JS = ACCOUNTS / "static" / "accounts" / "js" / "monitoring"


def _reset_rate_limits():
    from core import rate_limit

    rate_limit._RATE_LIMIT_FALLBACK_CACHE.clear()


def _login_row(user, ip, *, minutes=0, user_agent=CHROME_WINDOWS, organization=None, action=AuditAction.LOGIN):
    """``log_user_login`` ilə eyni formada sətir; ``created_at`` (auto_now_add) idarə olunan anla."""
    with mock.patch("django.utils.timezone.now", return_value=BASE_TIME + timedelta(minutes=minutes)):
        return AuditLog.objects.create(
            user=user, organization=organization, action=action, ip_address=ip, user_agent=user_agent
        )


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ipf_owner", "ipf_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="IPF University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.other_owner = User.objects.create_user("ipf_owner2", "ipf_owner2@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="IPF Other University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.rim = User.objects.create_user("ipf_rim", "ipf_rim@test.az", PASSWORD)
        _assign_user_to_org(cls.rim, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        cls.teacher = User.objects.create_user(
            "ipf_teacher", "ipf_teacher@test.az", PASSWORD, first_name="Aysel", last_name="Məmmədova"
        )
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("ipf_student", "ipf_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.foreign = User.objects.create_user("ipf_foreign", "ipf_foreign@test.az", PASSWORD)
        _assign_user_to_org(cls.foreign, cls.other_org, ProfileRole.TEACHER, "teacher")
        cls.outsider = User.objects.create_user("ipf_outsider", "ipf_outsider@test.az", PASSWORD)
        cls.superadmin = User.objects.create_superuser("ipf_super", "ipf_super@test.az", PASSWORD)

    def setUp(self):
        _reset_rate_limits()

    def api(self, user, **params):
        client = Client()
        client.force_login(user)
        return client.get(reverse("monitoring:security_events"), params)


class SecurityEventsIpFilterTests(_Base):
    def test_exact_ip_narrows_events_and_reports_the_filter(self):
        SecurityEvent.objects.create(event_type="login_failed", ip_address="10.20.0.1", message="hit")
        SecurityEvent.objects.create(event_type="login_failed", ip_address="10.20.0.2", message="neighbour")
        SecurityEvent.objects.create(event_type="login_failed", ip_address="2001:db8::7", message="v6")

        response = self.api(self.superadmin, ip=" 10.20.0.1 ")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([row["message"] for row in data["items"]], ["hit"])
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["ip_filter"], {"query": "10.20.0.1", "normalized": "10.20.0.1", "kind": "address"})
        self.assertIn("logins", data)

    def test_cidr_network_matches_only_addresses_inside_it(self):
        for ip, message in (("10.20.0.1", "a"), ("10.20.0.254", "b"), ("10.21.0.1", "outside"), ("2001:db8::7", "v6")):
            SecurityEvent.objects.create(event_type="login_failed", ip_address=ip, message=message)

        data = self.api(self.superadmin, ip="10.20.0.77/24").json()["data"]

        self.assertEqual(sorted(row["message"] for row in data["items"]), ["a", "b"])
        self.assertEqual(data["ip_filter"], {"query": "10.20.0.77/24", "normalized": "10.20.0.0/24", "kind": "network"})

    def test_ipv6_input_is_normalised_before_matching(self):
        SecurityEvent.objects.create(event_type="login_failed", ip_address="2001:db8::7", message="v6")

        data = self.api(self.superadmin, ip="2001:DB8:0:0::7").json()["data"]

        self.assertEqual([row["message"] for row in data["items"]], ["v6"])
        self.assertEqual(data["ip_filter"]["normalized"], "2001:db8::7")

    def test_type_and_ip_filters_combine(self):
        SecurityEvent.objects.create(event_type="login_failed", ip_address="10.20.0.1", message="failed")
        SecurityEvent.objects.create(event_type="login_brute_force", ip_address="10.20.0.1", message="brute")
        SecurityEvent.objects.create(event_type="login_brute_force", ip_address="10.20.0.9", message="other ip")

        data = self.api(self.superadmin, ip="10.20.0.1", type="login_brute_force").json()["data"]

        self.assertEqual([row["message"] for row in data["items"]], ["brute"])

    def test_invalid_ip_is_a_clear_400_never_a_500(self):
        client = Client()
        client.force_login(self.superadmin)
        for value in (
            "abc",
            "999.1.1.1",
            "1.2.3",
            "01.2.3.4",
            "10.0.0.0/33",
            "10.0.0.1/",
            "1.2.3.4; DROP TABLE monitoring_securityevent",
            "' OR 1=1 --",
            "fe80::1%eth0",
            "1" * 80,
        ):
            response = client.get(reverse("monitoring:security_events"), {"ip": value})
            self.assertEqual(response.status_code, 400, value)
            payload = response.json()
            self.assertEqual((payload["status"], payload["error"]), ("error", "invalid_ip"), value)
            self.assertIn("10.0.0.0/24", payload["detail"], value)
            self.assertNotIn("data", payload, value)

    def test_blank_ip_means_no_filter_and_no_logins_block(self):
        SecurityEvent.objects.create(event_type="login_failed", ip_address="10.20.0.1", message="any")
        for params in ({}, {"ip": "   "}):
            data = self.api(self.superadmin, **params).json()["data"]
            self.assertNotIn("logins", data)
            self.assertNotIn("ip_filter", data)
            self.assertIn("any", [row["message"] for row in data["items"]])

    def test_rim_head_ip_filtered_events_stay_org_scoped(self):
        ip = "10.60.0.4"
        SecurityEvent.objects.create(event_type="login_failed", organization=self.org, ip_address=ip, message="own")
        SecurityEvent.objects.create(event_type="login_failed", organization=None, ip_address=ip, message="platform")
        SecurityEvent.objects.create(
            event_type="login_failed", organization=self.other_org, ip_address=ip, message="foreign"
        )

        rim_rows = self.api(self.rim, ip=ip).json()["data"]["items"]
        super_rows = self.api(self.superadmin, ip=ip).json()["data"]["items"]

        self.assertEqual(sorted(row["message"] for row in rim_rows), ["own", "platform"])
        self.assertEqual(sorted(row["message"] for row in super_rows), ["foreign", "own", "platform"])


class SuccessfulLoginsTests(_Base):
    def test_logins_from_the_ip_are_grouped_by_account_and_device_newest_first(self):
        _login_row(self.teacher, "10.30.0.5", minutes=1, user_agent=CHROME_WINDOWS)
        _login_row(self.student, "10.30.0.5", minutes=2, user_agent=SAFARI_IPHONE)
        _login_row(self.teacher, "10.30.0.5", minutes=3, user_agent=CHROME_WINDOWS)
        _login_row(self.teacher, "10.30.0.9", minutes=4)  # başqa IP
        _login_row(self.student, "10.30.0.5", minutes=5, action=AuditAction.LOGOUT)  # çıxış — giriş deyil

        logins = self.api(self.superadmin, ip="10.30.0.5").json()["data"]["logins"]

        self.assertEqual(
            (logins["total"], logins["accounts"], logins["truncated"], logins["org_scoped"]), (3, 2, False, False)
        )
        first, second = logins["items"]
        self.assertEqual(
            (first["user"], first["full_name"], first["count"], first["device"], first["ip"]),
            ("ipf_teacher", "Aysel Məmmədova", 2, "Chrome 129 · Windows", "10.30.0.5"),
        )
        self.assertLess(first["first_seen"], first["last_seen"])
        self.assertEqual(
            (second["user"], second["count"], second["device"], second["user_agent"]),
            ("ipf_student", 1, "Safari 17 · iOS", SAFARI_IPHONE),
        )

    def test_network_filter_lists_each_address_separately(self):
        _login_row(self.teacher, "10.31.0.5", minutes=1)
        _login_row(self.teacher, "10.31.0.6", minutes=2)
        _login_row(self.student, "10.32.0.1", minutes=3)  # şəbəkədən kənar

        logins = self.api(self.superadmin, ip="10.31.0.0/16").json()["data"]["logins"]

        self.assertEqual(
            [(row["user"], row["ip"]) for row in logins["items"]],
            [
                ("ipf_teacher", "10.31.0.6"),
                ("ipf_teacher", "10.31.0.5"),
            ],
        )
        self.assertEqual((logins["total"], logins["accounts"]), (2, 1))

    def test_a_real_login_is_found_by_its_ip(self):
        response = Client().post(
            reverse("accounts:staff_login"),
            {"username": "ipf_teacher", "password": PASSWORD},
            REMOTE_ADDR="10.40.0.8",
            HTTP_USER_AGENT=FIREFOX_LINUX,
        )
        self.assertEqual(response.status_code, 302)

        logins = self.api(self.superadmin, ip="10.40.0.8").json()["data"]["logins"]

        self.assertEqual(
            [(row["user"], row["device"], row["count"]) for row in logins["items"]],
            [("ipf_teacher", "Firefox 131 · Linux", 1)],
        )

    def test_rim_head_sees_only_logins_of_own_active_members(self):
        former = User.objects.create_user("ipf_former", "ipf_former@test.az", PASSWORD)
        Membership.objects.create(
            user=former, organization=self.org, role=self.org.roles.get(name="teacher"), is_active=False
        )
        guest = User.objects.create_user("ipf_guest", "ipf_guest@test.az", PASSWORD)
        ip = "10.50.0.3"
        _login_row(self.teacher, ip, minutes=1)  # öz aktiv üzvü → görünür
        _login_row(self.foreign, ip, minutes=2)  # başqa təşkilatın üzvü → GİZLİ
        _login_row(self.outsider, ip, minutes=3)  # heç bir üzvlük yox → GİZLİ
        _login_row(former, ip, minutes=4)  # deaktiv üzvlük → GİZLİ
        _login_row(guest, ip, minutes=5, organization=self.org)  # öz təşkilatına yazılmış sətir → görünür
        _login_row(self.foreign, ip, minutes=6, organization=self.other_org)  # yad təşkilata yazılmış → GİZLİ

        rim = self.api(self.rim, ip=ip).json()["data"]["logins"]
        everything = self.api(self.superadmin, ip=ip).json()["data"]["logins"]

        self.assertTrue(rim["org_scoped"])
        self.assertEqual([row["user"] for row in rim["items"]], ["ipf_guest", "ipf_teacher"])
        self.assertEqual((rim["total"], rim["accounts"]), (2, 2))
        self.assertFalse(everything["org_scoped"])
        self.assertEqual(
            sorted(row["user"] for row in everything["items"]),
            ["ipf_foreign", "ipf_former", "ipf_guest", "ipf_outsider", "ipf_teacher"],
        )
        self.assertEqual(everything["total"], 6)

    def test_logins_are_capped_and_flagged_as_truncated(self):
        for minute, user in enumerate((self.teacher, self.student, self.outsider), start=1):
            _login_row(user, "10.70.0.1", minutes=minute)
        scope = MonitoringScope(platform=True, organization_id=None, can_manage=True)

        result = successful_logins(scope, parse_ip_filter("10.70.0.1"), limit=2)

        self.assertTrue(result["truncated"])
        self.assertEqual([row["user"] for row in result["items"]], ["ipf_outsider", "ipf_student"])
        self.assertEqual((result["total"], result["limit"]), (3, 2))

    def test_unknown_scope_is_fail_closed(self):
        _login_row(self.teacher, "10.70.0.2")
        ip_filter = parse_ip_filter("10.70.0.2")
        for scope in (None, MonitoringScope(platform=False, organization_id=None, can_manage=False)):
            result = successful_logins(scope, ip_filter)
            self.assertEqual((result["items"], result["total"], result["org_scoped"]), ([], 0, True))


class IpFilterPermissionTests(_Base):
    def test_teacher_gets_403_even_with_an_invalid_ip(self):
        _login_row(self.student, "10.80.0.1")
        client = Client()
        client.force_login(self.teacher)
        for value in ("10.80.0.1", "not-an-ip"):
            response = client.get(reverse("monitoring:security_events"), {"ip": value})
            self.assertEqual(response.status_code, 403, value)
            self.assertNotIn(b"ipf_student", response.content)

    def test_anonymous_gets_401(self):
        response = Client().get(reverse("monitoring:security_events"), {"ip": "10.80.0.1"})
        self.assertEqual(response.status_code, 401)


class IpFilterParsingTests(SimpleTestCase):
    def test_blank_means_no_filter(self):
        for raw in (None, "", "   "):
            self.assertIsNone(parse_ip_filter(raw))

    def test_addresses_and_networks_are_normalised(self):
        cases = {
            "10.0.0.1": ("10.0.0.1", "address"),
            "10.0.0.1/32": ("10.0.0.1", "address"),
            "10.0.5.9/16": ("10.0.0.0/16", "network"),
            "10.0.0.0/255.255.255.0": ("10.0.0.0/24", "network"),
            "2001:DB8::0:7": ("2001:db8::7", "address"),
            "::ffff:5.191.1.1": ("::ffff:5.191.1.1", "address"),
            "2001:db8::/32": ("2001:db8::/32", "network"),
        }
        for raw, (normalized, kind) in cases.items():
            ip_filter = parse_ip_filter(raw)
            self.assertEqual((ip_filter.normalized, ip_filter.as_dict()["kind"]), (normalized, kind), raw)

    def test_network_condition_is_an_inclusive_address_range(self):
        self.assertEqual(
            parse_ip_filter("5.191.0.0/16").q().children, [("ip_address__range", ("5.191.0.0", "5.191.255.255"))]
        )
        self.assertEqual(parse_ip_filter("5.191.1.1").q().children, [("ip_address", "5.191.1.1")])

    def test_garbage_raises_with_a_translated_hint(self):
        for raw in ("abc", "1.2.3", "01.2.3.4", "10.0.0.0/33", "fe80::1%eth0", "1.2.3.4 /24", "x" * 65):
            with self.assertRaises(InvalidIpFilter, msg=raw) as caught:
                parse_ip_filter(raw)
            self.assertIn("10.0.0.0/24", str(caught.exception))

    def test_networks_need_postgres_but_single_addresses_do_not(self):
        with mock.patch("apps.monitoring.security_ip.connection", mock.Mock(vendor="sqlite")):
            self.assertEqual(parse_ip_filter("10.0.0.1").normalized, "10.0.0.1")
            with self.assertRaises(InvalidIpFilter) as caught:
                parse_ip_filter("10.0.0.0/8")
        self.assertIn("CIDR", str(caught.exception))


class ShortUserAgentTests(SimpleTestCase):
    def test_common_browsers_get_a_short_label(self):
        cases = {
            CHROME_WINDOWS: "Chrome 129 · Windows",
            CHROME_WINDOWS + " Edg/129.0.2792.79": "Edge 129 · Windows",
            SAFARI_IPHONE: "Safari 17 · iOS",
            SAFARI_MAC: "Safari 17 · macOS",
            CHROME_ANDROID: "Chrome 129 · Android",
            FIREFOX_LINUX: "Firefox 131 · Linux",
        }
        for agent, label in cases.items():
            self.assertEqual(short_user_agent(agent), label, agent)

    def test_unknown_agents_are_truncated_not_guessed(self):
        self.assertEqual(short_user_agent("curl/8.4.0"), "curl/8.4.0")
        self.assertEqual(short_user_agent(""), "")
        self.assertEqual(short_user_agent(None), "")
        label = short_user_agent("x" * 100)
        self.assertEqual((len(label), label[-1]), (60, "…"))


class IpFilterFrontendContractTests(SimpleTestCase):
    NEW_KEYS = (
        "ipLabel",
        "ipPlaceholder",
        "ipClear",
        "ipFilterBy",
        "loginsTitle",
        "loginsTitleNet",
        "loginsEmpty",
        "loginsEmptyNet",
        "loginsMeta",
        "loginsTruncated",
        "loginsOrgNote",
        "colLastLogin",
        "colDevice",
        "firstSeen",
        "eventsEmptyIp",
    )

    def test_section_loads_security_module_and_css_after_renderers(self):
        template = (SECTIONS / "_system_monitoring.html").read_text(encoding="utf-8")
        for asset in (
            "css/profile/sections/system_monitoring_security.css' %}?v=20261005-ipf",
            "js/monitoring/system_monitoring_renderers.js' %}?v=20261005-ipf",
            "js/monitoring/system_monitoring_security.js' %}?v=20261005-ipf",
            "js/monitoring/system_monitoring.js' %}?v=20261005-ipf",
        ):
            self.assertIn(asset, template)
        renderers = template.index("js/monitoring/system_monitoring_renderers.js'")
        security = template.index("js/monitoring/system_monitoring_security.js'")
        controller = template.index("js/monitoring/system_monitoring.js'")
        self.assertLess(renderers, security)
        self.assertLess(security, controller)

    def test_every_new_text_key_is_in_the_island_and_used_by_the_module(self):
        island = (SECTIONS / "_system_monitoring_i18n.html").read_text(encoding="utf-8")
        module = (MONITORING_JS / "system_monitoring_security.js").read_text(encoding="utf-8")
        for key in self.NEW_KEYS:
            self.assertIn(f'"{key}": "{{% filter escapejs %}}', island, key)
            self.assertIn(f'"{key}"', module, key)

    def test_module_escapes_attributes_and_controller_keeps_the_filter_bar_on_400(self):
        module = (MONITORING_JS / "system_monitoring_security.js").read_text(encoding="utf-8")
        controller = (MONITORING_JS / "system_monitoring.js").read_text(encoding="utf-8")
        renderers = (MONITORING_JS / "system_monitoring_renderers.js").read_text(encoding="utf-8")
        self.assertIn('.replace(/"/g, "&quot;")', module)
        self.assertIn('.replace(/\'/g, "&#39;")', module)
        self.assertNotIn("style=", module)
        self.assertIn("response.status === 400", controller)
        self.assertIn("data: { invalid:", controller)
        self.assertIn('ip: ""', controller)
        self.assertIn("namespace.security.render(body, data, context)", renderers)
