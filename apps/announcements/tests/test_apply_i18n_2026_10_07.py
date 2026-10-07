"""Elandan müraciət: ``applications`` modulunun rədd mətni istifadəçinin dilindədir (2026-10-07)."""

from __future__ import annotations

import json

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.applications.models import Application, ApplicationKind, ApplicationUnit
from core.rls import bypass_rls

from .world import build_world, client_for, days, make_announcement

EXPECTED = {
    "az": "Bu müraciət növü sizin üçün açıq deyil.",
    "en": "This application type is not available to you.",
    "ru": "Этот тип заявки вам недоступен.",
    "tr": "Bu başvuru türü sizin için açık değil.",
}


class ApplyDeniedMessageLanguageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("anni18n")
        with bypass_rls():
            cls.kind = ApplicationKind.objects.get(organization=cls.w["org"], code="arayis")
            dean_unit = ApplicationUnit.objects.get(organization=cls.w["org"], code="dekan")
        cls.item = make_announcement(
            cls.w,
            title="Təqaüd müsabiqəsi",
            apply_mode="internal",
            apply_kind=cls.kind.pk,
            apply_unit=dean_unit.pk,
            deadline_at=days(5),
        )
        with bypass_rls():
            # Elan dərc olunandan sonra növ bağlanıb → `submit` `kind.not_allowed` ilə rədd edir.
            ApplicationKind.objects.filter(pk=cls.kind.pk).update(is_active=False)

    def test_transition_denied_text_is_translated(self):
        for language, expected in EXPECTED.items():
            client = client_for(self.w["org"], self.w["s1"])
            client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            response = client.post(
                reverse("announcements:apply", args=[self.item.pk]),
                data=json.dumps({}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 409, language)
            self.assertIn(expected, json.dumps(response.json(), ensure_ascii=False), language)
        with bypass_rls():
            self.assertFalse(Application.objects.filter(created_by=self.w["s1"]).exists())
