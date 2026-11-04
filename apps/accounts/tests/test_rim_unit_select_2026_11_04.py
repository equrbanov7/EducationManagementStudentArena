"""RİM «yeni hesab» — «Kafedra / bölmə» axtarışlı seçicidir (sahib 2026-11-04).

«bu yeni user yaradanda kafedra adları select option kimi gəlsin, search etmək də olsun»:
  * forma kafedraları layihənin axtarışlı seçicisində (``data-bootstrap-select`` + ``data-live-search``) verir,
    mətn type-ahead-i yoxdur; variant hansı hesab növündə göründüyünü (``data-rimc-unit-for``) daşıyır;
  * qrup / ixtisas siyahıya düşmür; kafedraya bağlı yaradıcı yalnız öz əhatəsini görür;
  * server seçimi yenidən yoxlayır: əhatədən kənar kafedra ilə müəllim hesabı YARANMIR.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from apps.accounts.services.rim import create as rim_create
from apps.accounts.services.rim.create_units import teacher_units, unit_picker_options
from apps.organizations.models import Membership, OrgUnit, Role
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .test_rim_account_create import RimCreateBase, base_payload

User = get_user_model()


@override_settings(RATELIMIT_ENABLE=False)
class RimUnitSelectTest(RimCreateBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.other_chair = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Riyaziyyat kafedrası",
                slug="unit-select-other-chair",
                unit_type=OrgUnitType.CHAIR,
            )

    def scoped_actor(self, permissions, scope_unit):
        user = User.objects.create_user("unit_select_actor_" + str(User.objects.count()))
        role = Role.objects.create(
            organization=self.org,
            name="unit_select_creator_" + str(user.pk),
            display_name="Unit select creator",
            level=60,
            permissions=permissions,
            scope_type=RoleScopeType.UNIT,
        )
        Membership.objects.create(organization=self.org, user=user, role=role, scope_unit=scope_unit)
        user.profile.organization = self.org
        user.profile.save(update_fields=["organization"])
        return self.actor_for(user)

    def test_form_renders_a_searchable_chair_select(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile"), {"section": "rim-center"})
        html = response.content.decode()
        start = html.index('id="rimc-unit"')
        select = html[html.rindex("<select", 0, start) : html.index("</select>", start)]
        self.assertIn("data-bootstrap-select", select)
        self.assertIn('data-live-search="true"', select)
        self.assertIn('data-rimc-field="unit"', select)
        self.assertIn(f'value="{self.chair.pk}"', select)
        self.assertIn(f'value="{self.other_chair.pk}"', select)
        self.assertIn(f'data-subtext="{self.faculty.name}"', select)
        self.assertIn('data-rimc-unit-for="teacher staff"', select)
        self.assertNotIn(f'value="{self.group.pk}"', select)
        # Köhnə mətn type-ahead-i (kafedra üçün) yoxdur.
        self.assertNotIn('data-rimc-combo="unit"', html)

    def test_picker_lists_chairs_per_kind_without_groups(self):
        options = {item["id"]: item for item in unit_picker_options(self.actor_for(self.rim), ("teacher", "staff"))}
        self.assertEqual(options[str(self.chair.pk)]["kinds"], "teacher staff")
        self.assertEqual(options[str(self.chair.pk)]["parent"], self.faculty.name)
        self.assertNotIn(str(self.group.pk), options)
        teacher_only = unit_picker_options(self.actor_for(self.rim), ("teacher",))
        self.assertTrue(all(item["kinds"] == "teacher" for item in teacher_only))

    def test_chair_scoped_creator_sees_and_may_use_only_own_chair(self):
        actor = self.scoped_actor(["user.import_staff"], self.chair)
        self.assertEqual(set(teacher_units(actor).values_list("pk", flat=True)), {self.chair.pk})
        self.assertEqual([item["id"] for item in unit_picker_options(actor, ("teacher",))], [str(self.chair.pk)])

        count = User.objects.count()
        with self.assertRaises(rim_create.RimCreateError) as caught:
            rim_create.create_account(
                actor, kind="teacher", data=base_payload(fin="3UUUUU3", unit=str(self.other_chair.pk))
            )
        self.assertIn("unit", caught.exception.fields)
        self.assertEqual(User.objects.count(), count)

        result = rim_create.create_account(
            actor, kind="teacher", data=base_payload(fin="4UUUUU4", unit=str(self.chair.pk))
        )
        membership = Membership.objects.get(user_id=result["user_id"], organization=self.org)
        self.assertEqual(membership.scope_unit_id, self.chair.pk)

    def test_out_of_scope_chair_is_rejected_by_the_endpoint(self):
        response = self.client_for(self.rim).post(
            reverse("accounts:rim_create_account"),
            {"kind": "teacher", **base_payload(fin="5UUUUU5", unit=str(self.group.pk))},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("unit", response.json()["fields"])
