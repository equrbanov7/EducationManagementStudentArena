"""«Fənn təhvili» panelinin 2026-09-09 yenidənqurması — performans + müqavilə.

Bu dəst redizaynın DÖRD vədini kilidləyir:

1. **Sorğu sayı sətir sayı ilə BÖYÜMÜR** — 5 sətirlik səhifə ilə 50 sətirlik
   səhifə EYNİ sayda sorğu işlədir (əvvəl dekan aktorunda hər sətir +1 sorğu idi:
   ölçülmüş 24 → 69).
2. **Tab-lar LAZY** — «Təhvil» açıqdırsa tarixçə HEÇ sorğulanmır və əksinə.
3. **Ekran müqaviləsi** — panelin öz `<h1>`-i yoxdur (qabıq verir), inline
   `style="…"` yoxdur, bloker səbəbi sətirdə AÇIQ yazılır.
4. **Əməl hələ də auditlidir** — yeni forma yolu (`offering_ids` + tək hədəf)
   eyni servisdən keçir, audit sətri və bildiriş yerindədir.
"""

import json
import re
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Subject, TeachingHandover
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_teaching_handover import HandoverBase

FRAGMENT = "accounts:profile_section_fragment"
PAGE_SIZE_PATH = "apps.accounts.views.profile._sections.handover_ui.PAGE_SIZE"


class HandoverPanelBase(HandoverBase):
    """Səhifələmə fərqini ölçmək üçün kifayət qədər açılış yaradır."""

    def _make_bulk(self, count=60):
        with bypass_rls():
            groups = [
                OrgUnit.objects.create(
                    organization=self.org,
                    name=f"Perf {index}",
                    slug=f"th-perf-g{index}",
                    unit_type=OrgUnitType.GROUP,
                    parent=self.chair_a,
                )
                for index in range(4)
            ]
            for index in range(count):
                subject = Subject.objects.create(organization=self.org, code=f"PERF{index}", name=f"Perf fənn {index}")
                CourseOffering.objects.create(
                    organization=self.org,
                    subject=subject,
                    period=self.period,
                    group=groups[index % len(groups)],
                    instructor=self.old_teacher,
                )

    def _fragment(self, client, query=""):
        return client.get(
            reverse(FRAGMENT, args=["teaching-handover"]) + query,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def _html(self, client, query=""):
        """Fraqment endpoint-i JSON zərfi qaytarır — panelin ÖZ markup-u lazımdır."""
        response = self._fragment(client, query)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        return payload["html"]


class QueryBudgetTest(HandoverPanelBase):
    """N+1 qapısı — sorğu sayı SƏTİR SAYINDAN asılı olmamalıdır."""

    def _count_for(self, client, page_size):
        with mock.patch(PAGE_SIZE_PATH, page_size):
            self._fragment(client)  # keşi qızdır (icazə/sessiya)
            with CaptureQueriesContext(connection) as captured:
                response = self._fragment(client)
        self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries), json.loads(response.content.decode())["html"]

    def test_the_panel_costs_the_same_for_5_and_50_rows(self):
        """Dekan (unit-scope) aktoru — məhz burada hər sətir bir sorğu idi."""
        self._make_bulk()
        client = self._login(self.dean)
        small, small_body = self._count_for(client, 5)
        large, large_body = self._count_for(client, 50)
        # Səhifə həqiqətən böyüyüb (test boş cavabı ölçmür).
        self.assertGreater(len(large_body), len(small_body) * 3)
        self.assertEqual(
            small,
            large,
            f"sətir başına sorğu qalıb: 5 sətir={small}, 50 sətir={large}",
        )

    def test_the_json_endpoint_costs_the_same_for_5_and_50_rows(self):
        """Köhnə JSON müqaviləsi də eyni büdcəyə tabedir (xarici istehlakçılar)."""
        self._make_bulk()
        client = self._login(self.dean)
        url = reverse("accounts:handover_offerings")
        client.get(url + "?page_size=5")
        with CaptureQueriesContext(connection) as small:
            five = client.get(url + "?page_size=5")
        with CaptureQueriesContext(connection) as large:
            fifty = client.get(url + "?page_size=50")
        self.assertEqual(len(five.json()["results"]), 5)
        self.assertEqual(len(fifty.json()["results"]), 50)
        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            f"5 sətir={len(small.captured_queries)}, 50 sətir={len(large.captured_queries)}",
        )


class LazyTabTest(HandoverPanelBase):
    """Açıq OLMAYAN tabın qiyməti ödənilmir."""

    def test_transfer_tab_does_not_touch_the_history_table(self):
        client = self._login(self.rim)
        with bypass_rls():
            self._reassign()
        self._fragment(client)
        with CaptureQueriesContext(connection) as captured:
            self._fragment(client)
        sql = " ".join(query["sql"] for query in captured.captured_queries)
        self.assertNotIn("teachinghandover", sql.lower())

    def test_history_tab_does_not_build_the_offering_table(self):
        client = self._login(self.rim)
        with bypass_rls():
            self._reassign()
        self._fragment(client, "?handover_tab=history")
        with CaptureQueriesContext(connection) as captured:
            response = self._fragment(client, "?handover_tab=history")
        body = json.loads(response.content.decode())["html"]
        self.assertIn("teachinghandover", " ".join(q["sql"] for q in captured.captured_queries).lower())
        # Təhvil tabının aqreqatı (bloker faseti) hesablanmır — «Seçilmiş fənn»
        # KPI kartı yalnız təhvil tabında var.
        self.assertNotIn('data-ems-kpi-key="selected"', body)


class PanelContractTest(HandoverPanelBase):
    """Ekran müqaviləsi: tək başlıq, inline stil yox, bloker səbəbi görünür."""

    def _body(self, client, query=""):
        return self._html(client, query)

    def test_the_panel_has_no_second_h1(self):
        body = self._body(self._login(self.rim))
        self.assertEqual(body.count("<h1"), 0, "bölmə paneli öz h1-ini yazmamalıdır (başlığı qabıq verir)")

    def test_the_panel_has_no_inline_style_attribute(self):
        body = self._body(self._login(self.rim))
        self.assertIsNone(re.search(r'\sstyle="', body), "panel inline style= atributu göndərməməlidir")

    def test_a_blocked_row_says_why_next_to_it(self):
        """Bağlı jurnal sətirdə SƏBƏBİ ilə görünür və seçilə bilmir."""
        from apps.registrar import gradebook
        from apps.registrar.models import ApprovalStatus

        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering_a)
            scheme.is_published = True
            scheme.approval_status = ApprovalStatus.APPROVED
            scheme.save(update_fields=["is_published", "approval_status"])
        body = self._body(self._login(self.rim))
        self.assertIn("Jurnal bağlanıb", body)
        self.assertIn("təhvil verilə bilməz", body.lower())

    def test_the_blocked_count_is_aggregated_in_one_sentence(self):
        with bypass_rls():
            self.offering_past.refresh_from_db()
        body = self._body(self._login(self.rim))
        # «N fənn təhvil verilə bilməz» lenti + səbəb bölgüsü.
        self.assertIn("fənn təhvil verilə bilməz", body)
        self.assertIn("keçmiş semestr", body)

    def test_the_state_filter_uses_the_real_blocker_rules(self):
        """«Yalnız təhvil oluna bilənlər» / «Yalnız bloklananlar» — dəqiq süzgəc.

        Əvvəl bu süzgəc TƏXMİNİ idi (`period__is_current=True`): bağlı jurnallı
        cari semestr sətri «açıq» sayılırdı və istifadəçi onu seçib 409 alırdı.
        """
        client = self._login(self.rim)
        open_body = self._body(client, "?th_state=open")
        blocked_body = self._body(client, "?th_state=blocked")
        self.assertIn(self.offering_a.subject.name, open_body)
        self.assertNotIn(self.offering_past.subject.name, open_body)
        self.assertIn(self.offering_past.subject.name, blocked_body)
        self.assertNotIn(self.offering_a.subject.name, blocked_body)

    def test_history_tab_renders_rows_and_the_revert_button(self):
        client = self._login(self.rim)
        with bypass_rls():
            self._reassign()
        body = self._body(client, "?handover_tab=history")
        self.assertIn("thxRevertDialog", body)
        self.assertIn(self.new_teacher.username, body.replace("&#x27;", "'") or body)


class FormSubmissionTest(HandoverPanelBase):
    """Yeni forma yolu (`offering_ids`) EYNİ servisdən keçir — audit qalır."""

    def test_bulk_form_post_reassigns_and_audits(self):
        from apps.audit.models import AuditLog

        client = self._login(self.rim)
        response = client.post(
            reverse("accounts:handover_action"),
            {
                "action": "reassign",
                "offering_ids": [str(self.offering_a.pk), str(self.offering_b.pk)],
                "new_instructor_id": str(self.new_teacher.pk),
                "reason": "Müəllim işdən çıxdı",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 2)
        with bypass_rls():
            self.offering_a.refresh_from_db()
            self.offering_b.refresh_from_db()
            self.assertEqual(self.offering_a.instructor_id, self.new_teacher.pk)
            self.assertEqual(self.offering_b.instructor_id, self.new_teacher.pk)
            self.assertEqual(TeachingHandover.objects.filter(reverted_at__isnull=True).count(), 2)
            self.assertEqual(
                AuditLog.objects.filter(resource_type="registrar.teaching_handover").count(),
                2,
            )

    def test_an_empty_target_is_a_clean_400_not_a_crash(self):
        """«Yeni müəllim» seçilmədən göndəriş — 500 yox, tərcümə olunmuş 400."""
        client = self._login(self.rim)
        response = client.post(
            reverse("accounts:handover_action"),
            {
                "action": "reassign",
                "offering_ids": [str(self.offering_a.pk)],
                "new_instructor_id": "",
                "reason": "Müəllim işdən çıxdı",
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        payload = response.json()
        self.assertEqual(payload["error"], "no_target")
        self.assertIn("müəllim", payload["message"].lower())
        with bypass_rls():
            self.assertFalse(TeachingHandover.objects.exists())

    def test_a_blocked_row_rolls_the_whole_form_batch_back(self):
        """Atomiklik forma yolunda da qorunur (bir bloker → heç nə yazılmır)."""
        client = self._login(self.rim)
        response = client.post(
            reverse("accounts:handover_action"),
            {
                "action": "reassign",
                "offering_ids": [str(self.offering_a.pk), str(self.offering_past.pk)],
                "new_instructor_id": str(self.new_teacher.pk),
                "reason": "Toplu təhvil",
            },
        )
        self.assertEqual(response.status_code, 409)
        with bypass_rls():
            self.offering_a.refresh_from_db()
            self.assertEqual(self.offering_a.instructor_id, self.old_teacher.pk)
            self.assertFalse(TeachingHandover.objects.exists())
