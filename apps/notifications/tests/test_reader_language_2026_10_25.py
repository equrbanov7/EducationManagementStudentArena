"""Sahib 2026-10-25: «gələn bildirişlərin dilini düzəlt — hərəsi bir dildə göstərir».

Bildiriş mətni oxuyanın CARİ dilində göstərilməlidir (tetikləyənin dilində yox). Bax ``apps/notifications/i18n.py``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import translation
from django.utils.translation import pgettext

from apps.accounts.views.profile._sections.notifications_ui import decorate
from apps.notifications.i18n import (
    META_KEY,
    LText,
    all_languages,
    build_i18n_metadata,
    describe,
    lformat,
    localize_notification,
    render,
)
from apps.notifications.management.commands.backfill_notification_i18n import describe_activation_message
from apps.notifications.models import InAppNotification
from apps.notifications.public import create_notification, create_notification_for_users
from core.rls import bypass_rls

User = get_user_model()

ACTIVATION = "Profilini aktivləşdirdi: %(name)s"
ACTIVATION_CTX = "accounts.rim_activation"


def _user(name):
    return User.objects.create_user(username=name, password="pw-12345-Abc!")


class DescribeRenderTests(TestCase):
    def test_percent_style_template_roundtrips_into_every_language(self):
        for lang, text in (
            ("ru", "Профиль активирован: Aygün Bayramova"),
            ("tr", "Profilini etkinleştirdi: SƏMA SƏMƏDOVA"),
            ("az", "Profilini aktivləşdirdi: Nicat Mahmudov"),
            ("en", "Profile activated: Nicat Mahmudov"),
        ):
            with translation.override(lang):
                descriptor = describe(text)
            self.assertIsNotNone(descriptor, text)
            self.assertEqual(descriptor["m"], ACTIVATION)
            self.assertEqual(render(descriptor, lang), text)
            name = text.split(": ", 1)[1]
            self.assertEqual(render(descriptor, "az"), f"Profilini aktivləşdirdi: {name}")
            self.assertEqual(render(descriptor, "ru"), f"Профиль активирован: {name}")

    def test_brace_style_template(self):
        with translation.override("en"):
            descriptor = describe("New exam assigned: Cloud Tech")
        self.assertEqual(descriptor["p"], {"title": "Cloud Tech"})
        self.assertEqual(render(descriptor, "az"), "Yeni imtahan təyin olundu: Cloud Tech")
        self.assertEqual(render(descriptor, "ru"), "Назначен новый экзамен: Cloud Tech")

    def test_unknown_text_has_no_descriptor(self):
        with translation.override("az"):
            self.assertIsNone(describe("Diqqət!"))
            self.assertIsNone(describe("Yeni elektron universitet sisteminə keçidlə əlaqədar olaraq"))
            self.assertIsNone(describe(""))
            self.assertIsNone(describe(None))

    def test_render_of_broken_descriptor_is_none(self):
        self.assertIsNone(render({"m": ACTIVATION, "c": ACTIVATION_CTX, "p": {"wrong": "x"}}, "az"))
        self.assertIsNone(render("not a dict", "az"))

    def test_catalog_label_parameter_follows_reader_language(self):
        descriptor = {"m": "Elektron jurnal — %(subject)s", "c": "registrar.notify", "p": {"subject": "Fizika"}}
        self.assertEqual(render(descriptor, "en"), "Electronic journal — Fizika")
        self.assertEqual(render(descriptor, "ru"), "Электронный журнал — Fizika")


class CreateStoresDescriptorTests(TestCase):
    def test_trigger_language_does_not_leak_to_reader(self):
        recipient = _user("reader.one")
        with translation.override("ru"):
            note = create_notification(
                recipient=recipient,
                title="Профиль активирован: Aygün Bayramova",
                message="",
                metadata={"kind": "profile_activated"},
            )
        # Sütun tetikləyənin dilində qalır (davranış dəyişmir), amma deskriptor var.
        self.assertEqual(note.title, "Профиль активирован: Aygün Bayramova")
        self.assertIn("title", note.metadata[META_KEY])
        for lang, expected in (
            ("az", "Profilini aktivləşdirdi: Aygün Bayramova"),
            ("tr", "Profilini etkinleştirdi: Aygün Bayramova"),
            ("en", "Profile activated: Aygün Bayramova"),
        ):
            stored = InAppNotification.objects.get(pk=note.pk)
            with translation.override(lang):
                decorate([stored])
            self.assertEqual(stored.title, expected)
            # Yaddaşdakı dəyişiklik DB-yə YAZILMIR.
            self.assertEqual(InAppNotification.objects.get(pk=note.pk).title, "Профиль активирован: Aygün Bayramova")

    def test_same_event_from_different_languages_reads_identically(self):
        recipient = _user("reader.two")
        for lang, text in (
            ("ru", "Профиль активирован: Nicat Mahmudov"),
            ("tr", "Profilini etkinleştirdi: Nicat Mahmudov"),
            ("en", "Profile activated: Nicat Mahmudov"),
            ("az", "Profilini aktivləşdirdi: Nicat Mahmudov"),
        ):
            with translation.override(lang):
                create_notification(recipient=recipient, title=text)
        with bypass_rls():
            rows = list(InAppNotification.objects.filter(recipient=recipient))
        with translation.override("az"):
            decorate(rows)
        self.assertEqual({row.title for row in rows}, {"Profilini aktivləşdirdi: Nicat Mahmudov"})

    def test_bulk_create_shares_descriptor(self):
        users = [_user("bulk.a"), _user("bulk.b")]
        with translation.override("tr"):
            created = create_notification_for_users(
                recipients=users,
                title="Profilini etkinleştirdi: Ali Veli",
                metadata={"link_label": "Profilini etkinleştirdi: Ali Veli"},
            )
        self.assertEqual(len(created), 2)
        for row in created:
            with translation.override("ru"):
                localize_notification(row)
            self.assertEqual(row.title, "Профиль активирован: Ali Veli")
            self.assertEqual(row.metadata["link_label"], "Профиль активирован: Ali Veli")

    def test_untranslatable_text_is_left_untouched(self):
        recipient = _user("reader.three")
        note = create_notification(recipient=recipient, title="Diqqət!", message="Salam, bu istifadəçi mətnidir.")
        self.assertNotIn(META_KEY, note.metadata)
        with translation.override("ru"):
            localize_notification(note)
        self.assertEqual(note.title, "Diqqət!")

    def test_caller_metadata_is_preserved(self):
        recipient = _user("reader.four")
        with translation.override("en"):
            note = create_notification(
                recipient=recipient, title="New exam assigned: Cloud Tech", metadata={"exam_id": 7, "kind": "x"}
            )
        self.assertEqual(note.metadata["exam_id"], 7)
        self.assertEqual(note.metadata["kind"], "x")


class LTextTests(TestCase):
    def test_ltext_is_stored_canonical_and_read_in_reader_language(self):
        recipient = _user("reader.five")
        with translation.override("ru"):
            note = create_notification(
                recipient=recipient,
                title=LText(ACTIVATION, ACTIVATION_CTX, name="Aygün Bayramova"),
                metadata={"link_label": LText("RİM mərkəzində aç", ACTIVATION_CTX)},
            )
        self.assertEqual(note.title, "Profilini aktivləşdirdi: Aygün Bayramova")  # kanonik (az) sütun
        self.assertIsInstance(note.metadata["link_label"], str)
        with translation.override("en"):
            localize_notification(note)
        self.assertEqual(note.title, "Profile activated: Aygün Bayramova")
        self.assertNotEqual(note.metadata["link_label"], "RİM mərkəzində aç")

    def test_lformat_composes_parts_per_language(self):
        text = lformat(
            "{0} · {1}", LText("Profilini aktivləşdirdi: %(name)s", ACTIVATION_CTX, name="Ali Veli"), "@ali.veli"
        )
        with translation.override("ru"):
            self.assertEqual(str(text), "Профиль активирован: Ali Veli · @ali.veli")
        with translation.override("tr"):
            self.assertEqual(str(text), "Profilini etkinleştirdi: Ali Veli · @ali.veli")

    def test_title_is_truncated_to_column_length(self):
        recipient = _user("reader.six")
        note = create_notification(recipient=recipient, title=LText(ACTIVATION, ACTIVATION_CTX, name="A" * 400))
        self.assertEqual(len(note.title), 255)

    def test_build_metadata_accepts_lazy_strings(self):
        from django.utils.translation import pgettext_lazy

        title, _message, meta = build_i18n_metadata(
            pgettext_lazy("notifications.event", "Your request was approved"), "", {}
        )
        self.assertIsInstance(title, str)
        self.assertIn("title", meta[META_KEY])


class LegacyActivationMessageTests(TestCase):
    @staticmethod
    def _old_message(lang):
        """Köhnə kodun (``_message``) bu dildə yığdığı mətn."""
        with translation.override(lang):
            summary = pgettext(ACTIVATION_CTX, "Cəmi aktivləşdirən: %(done)d / %(total)d (%(pct)s%%)") % {
                "done": 12,
                "total": 40,
                "pct": "30",
            }
            kinds = pgettext(
                ACTIVATION_CTX, "tələbə %(s)d / %(st)d, müəllim %(t)d / %(tt)d, əməkdaş %(e)d / %(et)d"
            ) % {
                "s": 5,
                "st": 20,
                "t": 4,
                "tt": 10,
                "e": 3,
                "et": 10,
            }
            head = " · ".join((pgettext(ACTIVATION_CTX, "Tələbə"), "@vaqif.seferli"))
        return f"{head}. {summary} — {kinds}."

    def test_old_composite_message_is_recognised_and_localised(self):
        az_text = self._old_message("az")
        for lang in ("az", "ru", "tr", "en", "de"):
            descriptor = describe_activation_message(self._old_message(lang), all_languages())
            self.assertIsNotNone(descriptor, lang)
            self.assertEqual(render(descriptor, "az"), az_text, lang)
            self.assertEqual(render(descriptor, lang), self._old_message(lang), lang)

    def test_unrelated_text_is_not_recognised(self):
        self.assertIsNone(describe_activation_message("Sadə mətn", all_languages()))
