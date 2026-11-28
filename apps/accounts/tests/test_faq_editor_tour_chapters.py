"""Role-tour editing retains its section navigation and connected practical guides."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import FaqVideoGuide
from apps.accounts.views.profile.faq_catalog import GUIDES
from apps.accounts.views.profile.faq_editor_forms import GuideForm, chapter_text
from apps.subject_folder.tests import factories as f

from .test_faq_video_editor import editor_url, org_client, video


@override_settings(UNIVERSITY_MODE=True)
class FAQTourChapterEditingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = f.make_org()
        cls.staff = f.make_user("tour-editor")
        cls.org.roles.get(name="rim_staff").memberships.create(organization=cls.org, user=cls.staff, is_active=True)

    def test_title_only_change_preserves_entire_longest_installed_tour(self):
        tour = max((g for g in GUIDES if g.key.startswith("tour-")), key=lambda g: len(g.chapters))
        response = org_client(self.staff, self.org).post(
            editor_url(tour.key),
            {
                "action": "save",
                "version": "0",
                "audience": "rim_staff",
                "title": "Kabinetə baxış",
                "topic": tour.topic,
                "steps": "\n".join(tour.steps),
                "chapters": chapter_text(tour.chapters),
            },
        )
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        self.assertEqual(FaqVideoGuide.objects.get(organization=self.org, key=tour.key).chapters, list(tour.chapters))

    def test_long_form_preserves_navigation_only_for_matching_original_media_and_chapters(self):
        chapters = [
            {
                "start": i,
                "time": f"{i // 60}:{i % 60:02}",
                "title": f"Fənnin materialı və elektron jurnal üzrə kabinet əməliyyatı {i}",
                "menu": True,
                "section": "my-subjects",
                "guide": "grades",
                "related": [{"key": "grades", "title": "Qiymətlərimi yoxlayım"}],
            }
            for i in range(550)
        ]
        chapters[13]["start"] = 13.726
        source = SimpleNamespace(video="test-tour", title="Tur", topic="Kabinet", steps=(), chapters=chapters)
        fields = dict(
            version="0", title="Tur", topic="Kabinet", audience=["rim_staff"], chapters=chapter_text(chapters)
        )
        with patch(
            "apps.accounts.views.profile.faq_editor_forms.media_metadata", return_value={"test-tour": {"duration": 600}}
        ):
            form = GuideForm(fields, org=self.org, row=None, original=source)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["chapters"], chapters)
            changed = GuideForm(dict(fields, chapters="00:00 Dəyişiklik"), org=self.org, row=None, original=source)
            self.assertTrue(changed.is_valid(), changed.errors)
            replacement = GuideForm(
                dict(fields, chapters=chapter_text(chapters[:1])),
                {"video": video()},
                org=self.org,
                row=None,
                original=source,
            )
            self.assertTrue(replacement.is_valid(), replacement.errors)
            for candidate in (changed, replacement):
                self.assertEqual(set(candidate.cleaned_data["chapters"][0]), {"start", "time", "title"})
