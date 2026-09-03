"""Sillabus redaktorunun RENDER müqaviləsi — şablon ↔ JS data-hook-ları.

Nəyi qoruyur
------------
Redaktorun davranışı tamamilə xarici JS-dədir
(``accounts/js/profile/syllabus_editor.js`` + ``…_fields.js``), çünki CSP
şablonda inline script-ə icazə vermir. JS isə Django template engine-dən
KEÇMİR — bütün dinamik dəyəri yalnız ``data-*`` atributlarından oxuya bilir.

Ona görə şablon ilə JS arasındakı yeganə bağ bu atributlardır və onlar səssizcə
sınır: atribut adı dəyişəndə nə şablon, nə JS xəta vermir — autosave sadəcə
işləməyi dayandırır və müəllim yazdığını itirir. Bu modul həmin bağı kilidləyir.

⚠️ Buradakı selektorlar JS-dəki ilə HƏRFƏN eyni olmalıdır. Birini dəyişəndə
o birini də dəyişin.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.syllabus import services
from apps.syllabus.constants import SECTION_ORDER
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()

PASSWORD = "StrongPass123!"

#: `syllabus_editor.js` mühərrikinin bağlandığı köklər.
ENGINE_HOOKS = (
    "data-syllabus-editor",
    "data-save-url",
    "data-action-url",
    "data-syl-save",
    "data-syl-toast",
    "data-syl-editor-modal",
    "data-syl-i18n",
    "data-syl-progress-fill",
    "data-syl-submit",
    "data-syl-save-now",
    "data-syl-retry",
    "data-syl-reload",
)

#: `syllabus_editor_fields.js` toplayıcılarının oxuduğu sahələr.
FIELD_HOOKS = (
    "data-field=",
    "data-field-lines=",
    "data-outcome",
    "data-week=",
    "data-syl-method=",
    "data-syl-midterm",
    "data-syl-selfwork=",
    "data-selfwork-title",
    "data-syl-slot=",
)


class SyllabusEditorRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-editor")
        cls.teacher = User.objects.create_user("syl_edit_teacher", "syl_edit_teacher@x.test", PASSWORD)
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            # `grade.input` sillabus üçün deyil: `registrar_guard_active_member`
            # PG trigger-i `CourseOffering.instructor` üçün məhz onu tələb edir.
            permissions=["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"],
            level=60,
        )
        stack = make_academic_stack(cls.org, code="SYLED1")
        offering = make_offering(cls.org, stack, cls.teacher)
        actor = services.resolve_actor(cls.teacher, cls.org)
        syllabus, version = services.create_draft(
            organization=cls.org,
            subject=stack["subject"],
            period=stack["period"],
            actor=actor,
            offering=offering,
            program=stack["program"],
            chair_unit=stack["chair"],
            author=cls.teacher,
            plan_hours=dict(PLAN_HOURS),
        )
        # Bölmələri tam doldururuq ki, «tamamlanıb» qolları da render olunsun.
        for section_id, data in complete_section_data().items():
            if section_id in {"prev", "send"}:
                continue
            services.save_section(version=version, section_id=section_id, data=data, actor=actor)
        cls.syllabus = syllabus
        cls.version = version

    def _editor_html(self) -> str:
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(
            reverse("accounts:profile"),
            {"section": "syllabus-editor", "version": str(self.version.pk)},
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    # ── Sol sidebar QALIR (sahibin açıq tələbi) ─────────────────────────────

    def test_editor_renders_inside_the_profile_shell_with_the_sidebar(self):
        """Redaktor ayrıca tam səhifə DEYİL — profil shell-inin bölməsidir."""
        html = self._editor_html()

        self.assertIn('data-profile-section-panel="syllabus-editor"', html)
        # Sidebar-ın sillabus qeydi profil shell-i ilə birlikdə render olunur.
        self.assertIn('data-section="syllabus-list"', html)

    def test_header_and_locked_row_show_the_official_program_code(self):
        """Redaktorun başlığı və kilidli «Təhsil proqramı» sətri ŞİFRLİDİR.

        Bloker idi: hər iki yer ``program.name``-i çılpaq çap edirdi. Kilidli
        sətir tədris planından gələn RƏSMİ dəyəri təmsil edir, ona görə şifrsiz
        ad kifayət etmir. Nümunə QƏSDƏN yalnız-köhnə-şifrlidir — ``display_label``
        cari şifr yoxdursa köhnəyə geri çəkilir.
        """
        program = self.syllabus.program
        program.name = "Dünya iqtisadiyyatı"
        program.official_code = ""
        program.legacy_official_code = "050401"
        program.save(update_fields=["name", "official_code", "legacy_official_code"])

        html = self._editor_html()

        self.assertEqual(program.display_label, "Dünya iqtisadiyyatı · 050401")
        # Başlıq + kilidli sətir — İKİ ayrı yer, ona görə say da yoxlanılır.
        self.assertGreaterEqual(html.count("Dünya iqtisadiyyatı · 050401"), 2)

    def _meta_line(self, html) -> str:
        """Başlıq altındakı `syl-meta` sətri — normalizə olunmuş MƏTN."""
        match = re.search(r'<p class="syl-meta">(.*?)</p>', html, re.S)
        self.assertIsNotNone(match, "`syl-meta` sətri render olunmadı")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()

    def test_meta_line_has_no_dangling_separator_when_the_period_is_missing(self):
        """REQRESSİYA: `period` boş olanda ayırıcı ŞİFRİN QUYRUĞUNDA asılı qalmır.

        Əlçatandır: köçürülmüş sillabusların əsas kütləsi `period=None` ilə
        yaradılır (`drafts.py` import_migrated_version), ona görə bu «nadir»
        hal deyil. Əvvəl render belə idi:
        «Dünya iqtisadiyyatı · 050401 · » (asılı quyruq).
        """
        program = self.syllabus.program
        program.name = "Dünya iqtisadiyyatı"
        program.official_code = ""
        program.legacy_official_code = "050401"
        program.save(update_fields=["name", "official_code", "legacy_official_code"])
        self.syllabus.period = None
        self.syllabus.save(update_fields=["period"])

        meta = self._meta_line(self._editor_html())

        self.assertIn("Dünya iqtisadiyyatı · 050401", meta)
        self.assertFalse(meta.endswith("·"), f"Asılı ayırıcı qaldı: [{meta}]")
        self.assertNotIn("· ·", meta, f"İKİQAT ayırıcı: [{meta}]")
        self.assertNotIn("None", meta, f"Boş `period` «None» kimi sızdı: [{meta}]")

    def test_meta_line_keeps_every_separator_when_all_parts_are_present(self):
        """Düzəliş ayırıcıları TAMAMİLƏ söndürmür — dolu halda hamısı yerindədir."""
        meta = self._meta_line(self._editor_html())

        self.assertGreaterEqual(meta.count("·"), 2, f"Ayırıcılar itdi: [{meta}]")
        self.assertFalse(meta.startswith("·"), f"Öndə asılı ayırıcı: [{meta}]")
        self.assertFalse(meta.endswith("·"), f"Sonda asılı ayırıcı: [{meta}]")
        self.assertNotIn("· ·", meta, f"İKİQAT ayırıcı: [{meta}]")

    # ── 10 bölmə ───────────────────────────────────────────────────────────

    def test_all_ten_design_sections_render_with_their_exact_ids(self):
        """Bölmə `id`-ləri dizayn paketi və domen `SectionKey`-i ilə eynidir."""
        html = self._editor_html()

        for section_id in SECTION_ORDER:
            with self.subTest(section=section_id):
                self.assertIn(f'data-syl-panel="{section_id}"', html)
        self.assertEqual(len(SECTION_ORDER), 10)

    # ── JS bağları ─────────────────────────────────────────────────────────

    def test_engine_hooks_are_present(self):
        html = self._editor_html()

        for hook in ENGINE_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, html)

    def test_field_collector_hooks_are_present(self):
        html = self._editor_html()

        for hook in FIELD_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, html)

    def test_autosave_chip_carries_all_six_state_texts(self):
        """`saveState` altı vəziyyətdir — mətnlər şablonda, JS-də deyil."""
        html = self._editor_html()

        for state in ("saving", "saved", "failed", "offline", "conflict", "stale"):
            with self.subTest(state=state):
                self.assertIn(f"data-t-{state}=", html)

    def test_four_save_state_banners_render_hidden(self):
        html = self._editor_html()

        for state in ("failed", "offline", "conflict", "stale"):
            with self.subTest(state=state):
                self.assertIn(f'data-syl-banner="{state}"', html)

    # ── Arxiv/qiymət müqaviləsi (silmə qadağası) ───────────────────────────

    def test_selfwork_slots_expose_graded_state_for_the_collector(self):
        """Qiyməti olan tapşırıq SİLİNMİR — JS bunu `data-graded`-dən bilir."""
        html = self._editor_html()

        self.assertIn("data-graded=", html)
        self.assertIn("data-graded-count=", html)

    def test_archive_container_renders_even_when_empty(self):
        """Arxiv boş olanda da konteyner qalmalıdır.

        Autosave göndərişi mövcud arxiv sətirlərini məhz oradan oxuyur; konteyner
        yalnız dolu halda render olunsaydı, ilk arxivləmə əvvəlki qeydləri
        silərdi.
        """
        html = self._editor_html()

        self.assertIn("data-syl-archived", html)

    def test_selfwork_options_expose_their_slot_count(self):
        """Struktur dəyişikliyi qiymətlənmiş tapşırığa toxunursa bloklanır."""
        html = self._editor_html()

        self.assertIn("data-count=", html)

    def test_hour_note_carries_both_texts_for_live_switching(self):
        html = self._editor_html()

        self.assertIn("data-syl-hours-note", html)
        self.assertIn("data-t-ok=", html)
        self.assertIn("data-t-warn=", html)


class SyllabusEditorAssetWiringTest(TestCase):
    """Şablon ↔ statik fayl bağı: istinad edilən hər JS diskdə OLMALIDIR.

    2026-08-30-da məhz bu sınmışdı: ``profile.html`` ``syllabus_editor.js``-i
    yükləyirdi, fayl isə heç yazılmamışdı — redaktorda autosave, addım
    naviqasiyası və dialoqlar tamamilə ölü idi, konsolda yalnız 404 vardı.

    2026-09-03: qabıq modul ölçüsü qapısına görə BÖLÜNDÜ — bölmə CSS-i
    ``profile/_section_assets.html``-ə köçdü (JS ``profile.html``-də qaldı).
    Skan ikisini də oxuyur: yer dəyişikliyi bağı qırmamalıdır.
    """

    #: Qabığın asset daşıyan faylları (CSS ayrıca include-a çıxarılıb).
    _SHELL_TEMPLATES = (
        "apps/accounts/templates/accounts/profile.html",
        "apps/accounts/templates/accounts/profile/_section_assets.html",
    )

    def _shell_body(self) -> str:
        return "\n".join((Path(settings.BASE_DIR) / name).read_text("utf-8") for name in self._SHELL_TEMPLATES)

    #: `{% static '…' %}` istinadları — həm JS, həm CSS (ikisi də bölünüb).
    _ASSET_PATTERNS = (
        r"\{%\s*static\s*'(accounts/js/profile/syllabus[^']+)'",
        r"\{%\s*static\s*'(accounts/css/profile/sections/syllabus[^']+)'",
    )

    def test_every_syllabus_asset_referenced_by_the_shell_exists(self):
        static_root = Path(settings.BASE_DIR) / "apps/accounts/static"
        body = self._shell_body()

        for pattern in self._ASSET_PATTERNS:
            referenced = re.findall(pattern, body)
            with self.subTest(pattern=pattern):
                self.assertTrue(referenced, "qabıq sillabus assetini yükləmir")
                missing = [name for name in referenced if not (static_root / name).is_file()]
                self.assertEqual(missing, [], f"İstinad edilən, amma diskdə olmayan fayl: {missing}")

    def test_the_fields_module_loads_before_the_engine(self):
        """Mühərrik init anında ``window.EMSSyllabusFields``-i oxuyur."""
        template = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile.html"
        body = template.read_text("utf-8")

        self.assertLess(
            body.index("syllabus_editor_fields.js"),
            body.index("syllabus_editor.js'"),
            "sahə modulu redaktor mühərrikindən SONRA yüklənir",
        )
