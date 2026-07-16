from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2] / "accounts"
TEMPLATE = ROOT / "templates" / "accounts" / "profile" / "sections" / "superadmin" / "_system_monitoring.html"
CSS = ROOT / "static" / "accounts" / "css" / "profile" / "sections" / "system_monitoring.css"
JS = ROOT / "static" / "accounts" / "js" / "monitoring" / "system_monitoring.js"
RENDERERS_JS = ROOT / "static" / "accounts" / "js" / "monitoring" / "system_monitoring_renderers.js"


class MonitoringFrontendTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")
        cls.js = JS.read_text(encoding="utf-8")
        cls.renderers = RENDERERS_JS.read_text(encoding="utf-8")

    def test_profile_fragment_owns_static_assets_and_ajax_panel(self):
        self.assertIn('data-profile-section-panel="system-monitoring"', self.template)
        self.assertIn("system_monitoring.css", self.template)
        self.assertIn("system_monitoring_renderers.js", self.template)
        self.assertIn("system_monitoring.js", self.template)

    def test_chart_has_bounded_responsive_frame(self):
        self.assertIn(".smx-chart {", self.css)
        self.assertIn("height: 260px;", self.css)
        self.assertIn("height: 100% !important;", self.css)
        self.assertIn("width: 100% !important;", self.css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", self.css)

    def test_chart_does_not_require_date_adapter_and_handles_empty_data(self):
        self.assertNotIn('type: "time"', self.js)
        self.assertIn('type: "linear"', self.js)
        self.assertIn("smx-chart-empty", self.js)
        self.assertIn("decimation:", self.js)
        self.assertIn("spanGaps: true", self.js)
        self.assertIn("suggestedMax", self.js)

    def test_ajax_script_order_is_fail_soft(self):
        self.assertIn("namespace.pendingRoots", self.js)
        self.assertIn("namespace.bootPending", self.js)
        self.assertIn("namespace.createRenderers", self.renderers)
        self.assertIn('typeof namespace.bootPending === "function"', self.renderers)

    def test_loading_is_lazy_deduplicated_and_visibility_aware(self):
        self.assertIn("IntersectionObserver", self.js)
        self.assertIn("requestIdleCallback", self.js)
        self.assertIn("AbortController", self.js)
        self.assertIn("inFlight.key === requestKey", self.js)
        self.assertIn("document.hidden", self.js)
        self.assertIn("}, 60000);", self.js)

    def test_paginated_tabs_send_page_and_page_size(self):
        self.assertIn("page_size: 20", self.js)
        self.assertIn("data-smx-page", self.js)
        self.assertIn("source.total_pages", self.js)
        self.assertIn("params.before_ns = logCursors[states.logs.page]", self.js)
        self.assertIn("data.next_cursor_ns", self.js)
        self.assertIn("states.logs.page > 1", self.js)
        self.assertIn('rowsFrom(data, "containers")', self.renderers)
        self.assertIn('rowsFrom(data, "events")', self.renderers)
        self.assertIn('rowsFrom(data, "lines")', self.renderers)
        self.assertIn('rowsFrom(data, "incidents")', self.renderers)
