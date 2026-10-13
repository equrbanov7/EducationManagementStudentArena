"""examphoto 2026-10-13 (gecə) — imtahan ekranında tələbənin ÖZ şəkli olan kimlik kartı.

Sahib: «test imtahanı zamanı solda ya da sağda tələbənin öz şəklinin görünməsi … ordakı performans
və təhlükəsizlik problemlərinə bax». Yoxlanır:

* take_exam / take_coding_exam kartı render edir (şəkil + ad + qrup), şəkil URL-i icazəli marşrutdur,
  kimlik bir dəfə hesablanır (başlıq çipi + kart eyni URL);
* şəkil marşrutu: başqa tələbə 404 (IDOR yox), keş yalnız `private`, `Vary: Cookie`, 304, SVG rədd;
* gizli slaydların şəkilləri `loading="lazy"`; şablonlarda inline skript/stil yoxdur;
* səhifədə düzgün cavab (is_correct) və xam option id-ləri yoxdur.
"""

import re
from datetime import timedelta
from pathlib import Path

from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from django.utils.http import http_date

from apps.exams.models import ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption, ExamSupervisionConfig
from apps.exams.tests.test_proc_2026_10_01_monitor import _PNG, _MonitorBase

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "exams" / "student"


class _TakeExamBase(_MonitorBase):
    def _test_attempt(self, *, user=None, with_image=False):
        exam = self.exam.__class__.objects.create(
            title="Photo card exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            start_datetime=timezone.now() - timedelta(minutes=5),
            end_datetime=timezone.now() + timedelta(hours=1),
        )
        ExamSupervisionConfig.objects.create(exam=exam, enabled=True)
        attempt = ExamAttempt.objects.create(user=user or self.student, exam=exam, status="in_progress")
        for order in (1, 2):
            question = ExamQuestion.objects.create(exam=exam, text=f"Sual {order}?", order=order)
            if with_image:
                question.image.save(f"q{order}.png", ContentFile(_PNG), save=True)
            self.correct = ExamQuestionOption.objects.create(question=question, text="Bəli", is_correct=True)
            ExamQuestionOption.objects.create(question=question, text="Xeyr", is_correct=False)
            ExamAnswer.objects.create(attempt=attempt, question=question)
        return exam, attempt


class TakeExamIdentityCardTests(_TakeExamBase):
    def test_take_exam_renders_side_identity_card_with_own_photo(self):
        exam, attempt = self._test_attempt()
        response = self._client_for(self.student).get(reverse("exams:take_exam", args=[exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-exam-id-card", html)
        self.assertIn("exam-workspace--id", html)
        self.assertIn("id_card.css", html)
        self.assertIn("identity_photo.js", html)
        photo = reverse("exams:proctor_student_photo", args=[self.student.pk])
        # Başlıq çipi + yan kart — eyni (versiyalı) URL, brauzer bir dəfə yükləyir.
        self.assertEqual(html.count(f'src="{photo}?v='), 2)
        self.assertIn("634 ing", html)
        self.assertNotIn("/media/avatars/", html)
        self.assertNotIn(self.student2.username, html)

    def test_no_photo_shows_initials_and_document_hint(self):
        self.student.profile.avatar.delete(save=True)
        exam, attempt = self._test_attempt()
        response = self._client_for(self.student).get(reverse("exams:take_exam", args=[exam.slug, attempt.id]))
        html = response.content.decode()
        self.assertIn("data-exam-id-card", html)
        self.assertNotIn(reverse("exams:proctor_student_photo", args=[self.student.pk]), html)
        self.assertRegex(html, r"<p class=\"exam-id-card__nophoto\" data-id-nophoto>")

    def test_identity_is_computed_once_per_page(self):
        exam, attempt = self._test_attempt()
        url = reverse("exams:take_exam", args=[exam.slug, attempt.id])
        client = self._client_for(self.student)
        client.get(url)  # isinmə (sessiya / keşlər)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            client.get(url)
        profile_queries = [
            q for q in ctx.captured_queries if "institutional_identifier" in q["sql"] and " IN (" in q["sql"]
        ]
        self.assertEqual(len(profile_queries), 1, [q["sql"] for q in profile_queries])

    def test_page_has_no_answer_key_or_raw_option_ids(self):
        exam, attempt = self._test_attempt()
        response = self._client_for(self.student).get(reverse("exams:take_exam", args=[exam.slug, attempt.id]))
        html = response.content.decode()
        self.assertNotIn("is_correct", html)
        self.assertNotIn(f'value="{self.correct.pk}"', html)

    def test_hidden_slide_images_are_lazy(self):
        exam, attempt = self._test_attempt(with_image=True)
        response = self._client_for(self.student).get(reverse("exams:take_exam", args=[exam.slug, attempt.id]))
        html = response.content.decode()
        # 2-ci slayd lazy; ilk slayd dərhal yüklənir.
        self.assertEqual(len(re.findall(r'<img src="[^"]+" loading="lazy" decoding="async" alt=', html)), 1)
        self.assertEqual(len(re.findall(r'<img src="[^"]+" decoding="async" alt=', html)), 1)

    def test_other_student_cannot_open_attempt_page(self):
        exam, attempt = self._test_attempt()
        response = self._client_for(self.student2).get(reverse("exams:take_exam", args=[exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 404)


class PhotoRouteHardeningTests(_MonitorBase):
    def _url(self, target=None):
        return reverse("exams:proctor_student_photo", args=[(target or self.student).pk])

    def test_own_photo_private_cache_and_vary_cookie(self):
        response = self._client_for(self.student).get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])
        self.assertNotIn("public", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("Last-Modified", response)

    def test_conditional_get_returns_304_only_after_permission_check(self):
        since = http_date(self.student.profile.updated_at.timestamp() + 60)
        own = self._client_for(self.student).get(self._url(), HTTP_IF_MODIFIED_SINCE=since)
        self.assertEqual(own.status_code, 304)
        self.assertIn("private", own["Cache-Control"])
        # Başqa tələbə If-Modified-Since ilə də heç nə öyrənmir (304 yox, 404).
        other = self._client_for(self.student2).get(self._url(), HTTP_IF_MODIFIED_SINCE=since)
        self.assertEqual(other.status_code, 404)

    def test_stale_conditional_get_streams_file(self):
        since = http_date(self.student.profile.updated_at.timestamp() - 3600)
        response = self._client_for(self.student).get(self._url(), HTTP_IF_MODIFIED_SINCE=since)
        self.assertEqual(response.status_code, 200)

    def test_student_cannot_read_classmate_photo(self):
        self.student2.profile.avatar.save("other.png", ContentFile(_PNG), save=True)
        response = self._client_for(self.student).get(self._url(self.student2))
        self.assertEqual(response.status_code, 404)

    def test_svg_avatar_is_never_served(self):
        profile = self.student.profile
        profile.avatar.save("evil.svg", ContentFile(b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>"))
        response = self._client_for(self.student).get(self._url())
        self.assertEqual(response.status_code, 404)


class CodingExamTemplateTests(_MonitorBase):
    def test_coding_template_includes_card_and_script(self):
        source = (_TEMPLATES / "take_coding_exam.html").read_text(encoding="utf-8")
        self.assertIn("_proctor_id_card.html", source)
        self.assertIn("identity_photo.js", source)
        self.assertIn("id_card.css", source)


class NoInlineAssetsTests(_MonitorBase):
    def test_new_partial_has_no_inline_script_style_or_handlers(self):
        for name in ("partials/_proctor_id_card.html", "partials/_proctor_identity.html"):
            source = (_TEMPLATES / name).read_text(encoding="utf-8")
            self.assertNotIn("<script", source, name)
            self.assertNotIn("<style", source, name)
            self.assertNotIn("style=", source, name)
            self.assertNotRegex(source, r"\son[a-z]+=", name)
