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

    def test_real_role_renders_localized_label(self):
        # PHASE21 U-2 (2026-09-03): seed-dəki İngiliscə "Dean" AZ-a çevrilir —
        # bax `core.roles.resolve_seeded_role_label`.
        self.assertEqual(role_badge_label(_FakeRole("dean", "Dean")), "Dekan")

    def test_customized_display_name_is_untouched(self):
        # Admin display_name-i fərqli bir mətnə dəyişibsə TOXUNULMUR.
        self.assertEqual(role_badge_label(_FakeRole("dean", "Baş Dekan")), "Baş Dekan")

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
        self.assertEqual(real, "<span>Müəllim</span>")
