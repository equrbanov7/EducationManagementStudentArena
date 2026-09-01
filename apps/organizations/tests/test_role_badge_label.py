"""`role_badge_label` şablon süzgəci — «Üzv» doldurucusu nişan kimi çıxmır.

Təşkilat idarəetmə səthlərində (dashboard, vahid detalı, üzvlər cədvəli) rol
nişanı ``Role`` obyektindən birbaşa oxunurdu; vəzifəsiz hesabda bu «Member»
(AZ interfeysdə «Üzv») kimi görünürdü. Süzgəc həmin dəyəri boş sətrə çevirir,
şablon isə boş nişanı gizlədir.
"""

from django.template import Context, Template
from django.test import SimpleTestCase

from ..templatetags.org_tags import role_badge_label


class _FakeRole:
    def __init__(self, name, display_name):
        self.name = name
        self.display_name = display_name


class RoleBadgeLabelTest(SimpleTestCase):
    def test_placeholder_member_role_renders_nothing(self):
        self.assertEqual(role_badge_label(_FakeRole("member", "Member")), "")

    def test_real_role_renders_its_display_name(self):
        self.assertEqual(role_badge_label(_FakeRole("dean", "Dean")), "Dean")

    def test_missing_role_is_safe(self):
        self.assertEqual(role_badge_label(None), "")

    def test_template_usage_hides_empty_badge(self):
        template = Template(
            "{% load org_tags %}{% with badge=role|role_badge_label %}"
            "{% if badge %}<span>{{ badge }}</span>{% endif %}{% endwith %}"
        )
        placeholder = template.render(Context({"role": _FakeRole("member", "Member")}))
        real = template.render(Context({"role": _FakeRole("teacher", "Teacher")}))
        self.assertEqual(placeholder, "")
        self.assertEqual(real, "<span>Teacher</span>")
