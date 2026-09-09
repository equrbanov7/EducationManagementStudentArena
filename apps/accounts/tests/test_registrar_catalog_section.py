"""«Registrar (kataloq)» — akademik kataloq konsolu KABİNET BÖLMƏSİ kimi.

Sahibin 2026-09-09 tələbi: «registrar kataloq yeni səhifəyə atmamalıdı, sidebar
solda qalıb sağda bu açmalıdı». Bu modul həmin müqaviləni qoruyur:

* bölmə `?section=registrar-catalog` fraqmenti kimi açılır (qabıq qalır);
* sidebar keçidi SPA-dır (`js-profile-section-link`), müstəqil səhifəyə deyil;
* tab-lar LAZY — yalnız seçilmiş tabın sətirləri hesablanır;
* sütun başlıqları sətir xanaları ilə ÜST-ÜSTƏ düşür (fakültə reyestrindəki
  sürüşmə səhvi burada təkrarlanmasın);
* yaratma/redaktə TƏK JSON son nöqtəsindən gedir və mövcud `registrar/forms.py`
  validasiyasını işlədir; silmə YOXDUR — «Aktiv» bayrağı ilə deaktiv edilir;
* icazəsiz aktor nə bölməni, nə də son nöqtəni görür (fail-closed).
"""

from django.urls import reverse

from apps.registrar.models import Subject

from .test_org_units_sections import _OrgUnitsBase

SECTION = "registrar-catalog"


class RegistrarCatalogSectionTest(_OrgUnitsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        role = cls.roles["teaching_office_head"]
        role.permissions = sorted(set(list(role.permissions) + ["course.edit"]))
        role.save(update_fields=["permissions"])

    def _section(self, role="teaching_office_head", **params):
        return self._fragment(role, SECTION, **params)

    def _action(self, role, payload):
        return self._client(role).post(
            reverse("accounts:registrar_catalog_action"),
            data=payload,
            content_type="application/json",
        )

    # ── Görünürlük ──────────────────────────────────────────────────────────
    def test_section_opens_inside_the_cabinet_shell(self):
        response = self._section()
        self.assertEqual(response.status_code, 200)
        section = response.context["registrar_catalog_section"]
        self.assertTrue(section["has_access"])
        html = response.json()["html"]
        # Başlıq YALNIZ qabıqdan gəlir — panelin öz `<h1>`-i yoxdur.
        self.assertNotIn("<h1", html)
        self.assertIn('data-profile-section-panel="registrar-catalog"', html)
        self.assertIn("data-rcat-root", html)

    def test_sidebar_link_is_a_section_link_not_a_page(self):
        html = self._client("teaching_office_head").get(reverse("accounts:profile")).content.decode()
        self.assertIn('data-section="registrar-catalog"', html)
        self.assertIn("?section=registrar-catalog", html)
        # Köhnə müstəqil səhifəyə keçid sidebar-dan çıxarılıb.
        self.assertNotIn('href="/registrar/idareetme/"', html)

    def test_actor_without_the_catalogue_key_sees_neither_section_nor_endpoint(self):
        # Fraqment API-si icazəsiz bölmə üçün 403 verir (kontekst ümumiyyətlə qurulmur).
        self.assertEqual(self._fragment("teacher", SECTION).status_code, 403)
        self.assertEqual(self._action("teacher", {"action": "save", "tab": "subjects"}).status_code, 403)
        # Sidebar-da da keçid yoxdur.
        html = self._client("teacher").get(reverse("accounts:profile")).content.decode()
        self.assertNotIn('data-section="registrar-catalog"', html)

    # ── Tab-lar ─────────────────────────────────────────────────────────────
    def test_every_tab_is_offered_and_only_the_active_one_is_computed(self):
        section = self._section().context["registrar_catalog_section"]
        keys = [tab["key"] for tab in section["tabs"]]
        self.assertEqual(keys, ["programs", "subjects", "curricula", "offerings", "rubrics", "students"])
        self.assertEqual(section["tab"], "programs")
        self.assertTrue(all("count" in tab for tab in section["tabs"]))

        subjects = self._section(rc_tab="subjects").context["registrar_catalog_section"]
        self.assertEqual(subjects["tab"], "subjects")

    def test_table_headers_match_the_row_cells_on_every_tab(self):
        """Fakültə reyestrindəki sütun sürüşməsi burada təkrarlanmır."""
        for tab in ("programs", "subjects", "curricula", "offerings", "rubrics", "students"):
            with self.subTest(tab=tab):
                section = self._section(rc_tab=tab).context["registrar_catalog_section"]
                self.assertEqual(section["columns"][-1]["key"], "actions")
                for row in section["table_rows"]:
                    # +1 sətir başlığı (`th scope="row"`), +1 əməllər xanası.
                    self.assertEqual(len(section["columns"]), len(row["cells"]) + 2)

    def test_search_on_a_tab_stays_on_that_tab(self):
        """Sahib (2026-09-10): «Tələbə təyinatları»nda ad yazanda ekran birinci
        taba atırdı. Server tərəfdə tab + axtarış BİRLİKDƏ oxunmalıdır (JS
        tərəfdəki qapı: `test_filter_bar_state_params`)."""
        section = self._section(rc_tab="students", rc_q="Aysel").context["registrar_catalog_section"]
        self.assertEqual(section["tab"], "students")
        self.assertTrue(next(tab for tab in section["tabs"] if tab["key"] == "students")["current"])
        search_field = next(field for field in section["filter_fields"] if field["name"] == "q")
        self.assertEqual(search_field["value"], "Aysel")

    def test_student_tab_is_read_only_and_points_at_the_registry(self):
        section = self._section(rc_tab="students").context["registrar_catalog_section"]
        self.assertTrue(section["readonly_tab"])
        self.assertFalse(section["can_create"])
        self.assertIn("section=student-registry", section["registry_url"])

    # ── Yazı ────────────────────────────────────────────────────────────────
    def test_create_and_edit_a_subject_through_the_dialog_endpoint(self):
        created = self._action(
            "teaching_office_head",
            {
                "action": "save",
                "tab": "subjects",
                "name": "Kataloq testi",
                "code": "RCAT-1",
                "ects": "5",
                "is_active": "on",
            },
        )
        self.assertEqual(created.status_code, 200)
        subject = Subject.objects.get(organization=self.org, code="RCAT-1")
        self.assertEqual(subject.ects, 5)
        self.assertTrue(subject.is_active)

        edited = self._action(
            "teaching_office_head",
            {
                "action": "save",
                "tab": "subjects",
                "id": str(subject.id),
                "name": "Kataloq testi",
                "code": "RCAT-1",
                "ects": "7",
                "is_active": "",
            },
        )
        self.assertEqual(edited.status_code, 200)
        subject.refresh_from_db()
        self.assertEqual(subject.ects, 7)
        # Silmə yoxdur — sətir qalır, yalnız deaktiv olur (yumşaq silmə).
        self.assertFalse(subject.is_active)
        self.assertTrue(Subject.objects.filter(pk=subject.pk).exists())

    def test_values_action_prefills_the_edit_dialog(self):
        subject = Subject.objects.create(organization=self.org, code="RCAT-2", name="Doldurma", ects=4)
        response = self._action("teaching_office_head", {"action": "values", "tab": "subjects", "id": str(subject.id)})
        self.assertEqual(response.status_code, 200)
        values = response.json()["values"]
        self.assertEqual(values["code"], "RCAT-2")
        self.assertEqual(values["name"], "Doldurma")

    def test_invalid_row_returns_field_errors_not_a_crash(self):
        response = self._action("teaching_office_head", {"action": "save", "tab": "subjects", "name": "", "code": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    def test_unknown_action_or_tab_is_rejected(self):
        self.assertEqual(self._action("teaching_office_head", {"action": "drop", "tab": "subjects"}).status_code, 400)
        self.assertEqual(self._action("teaching_office_head", {"action": "save", "tab": "hackers"}).status_code, 400)
