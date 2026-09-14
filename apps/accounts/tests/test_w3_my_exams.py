"""W3 `w3myexams` (2026-09-14) — «İmtahanlarım»: zibil qutusu alt-görünüşü + modal scroll müqaviləsi.

Sahib: «İmtahanlarım hissəsində açılan modalı aşağı sürüşdürəndə hər zaman getmir,
bəzən iç-içə nə isə bir şey var … Oradakı zibil qutusu yerini də düzəlt, daha yaxşı
formada.»

Yoxlanılır:
* başlıqda mətn linki əvəzinə sayğaclı ikon düyməsi + «İmtahanlarım / Zibil qutusu» tabları;
* ``?exam_view=trash`` alt-görünüşü: cədvəl (bərpa formu, birdəfəlik silmə yalnız cəhdsiz
  imtahanda, cəhdli imtahanda kilid), boş vəziyyət, KPI/toolbar gizli;
* sorğu büdcəsi silinmiş imtahan sayından asılı deyil;
* bərpa / birdəfəlik silmə yönləndirməsi alt-görünüşə qayıdır;
* AJAX fragment yolu eyni alt-görünüşü verir;
* sehrbaz modalının TƏK scroll qatı müqaviləsi (CSS/JS regressiya qoruyucusu).
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.accounts.tests.test_profile_views import _assign_user_to_org, _login_with_org
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

TRASH_URL = f"{reverse('accounts:profile')}?section=my-exams&exam_view=trash"
LIST_URL = f"{reverse('accounts:profile')}?section=my-exams"


class MyExamsTrashSubviewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(username="w3_teacher", email="w3t@example.com", password="pass12345")
        self.student = User.objects.create_user(username="w3_student", email="w3s@example.com", password="pass12345")
        self.organization = Organization.objects.create(
            name="W3 MyExams Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        _login_with_org(self.client, self.teacher, self.organization)
        self.active = Exam.objects.create(
            author=self.teacher, organization=self.organization, title="W3 Aktiv imtahan", is_active=True
        )

    def _deleted_exam(self, title, *, with_attempt=False):
        exam = Exam.objects.create(
            author=self.teacher,
            organization=self.organization,
            title=title,
            is_active=False,
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        if with_attempt:
            ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        return exam

    # ── başlıq + tablar ──────────────────────────────────────────────────────
    def test_header_has_trash_icon_button_with_count_and_tabs(self):
        self._deleted_exam("W3 Silinmiş 1")
        self._deleted_exam("W3 Silinmiş 2")

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, 200)
        trash = response.context["my_exams_dashboard"]["trash"]
        self.assertEqual(trash["count"], 2)
        self.assertFalse(trash["is_open"])
        # Sayğaclı ikon düyməsi alt-görünüşə aparır (köhnə ayrıca səhifə linki başlıqda yoxdur).
        self.assertContains(response, "data-tx-trash-link", html=False)
        self.assertContains(response, "data-tx-trash-count>2<", html=False)
        self.assertContains(response, "exam_view=trash", html=False)
        self.assertNotContains(response, f'href="{reverse("exams:deleted_exams_list")}"', html=False)
        # Tablar: aktiv siyahı cari, zibil qutusu sayğaclı.
        self.assertContains(response, "data-tx-tabs", html=False)
        # Siyahı görünüşündə KPI zolağı və toolbar var, zibil paneli yoxdur.
        self.assertContains(response, "data-tx-kpis", html=False)
        self.assertNotContains(response, "data-tx-trash>", html=False)
        # Primary düymə müqaviləsi dəyişməyib (test_profile_views ilə eyni).
        self.assertContains(response, 'class="ems-btn ems-btn--primary js-open-exam-form-modal"', html=False)

    # ── alt-görünüş ──────────────────────────────────────────────────────────
    def test_trash_subview_lists_deleted_exams_with_actions(self):
        empty = self._deleted_exam("W3 Boş silinmiş")
        protected = self._deleted_exam("W3 Nəticəli silinmiş", with_attempt=True)

        response = self.client.get(TRASH_URL)

        self.assertEqual(response.status_code, 200)
        trash = response.context["my_exams_dashboard"]["trash"]
        self.assertTrue(trash["is_open"])
        self.assertEqual(trash["table_state"], "ready")
        self.assertEqual([row["exam"].pk for row in trash["table_rows"]], [protected.pk, empty.pk])
        self.assertContains(response, "data-tx-trash", html=False)
        self.assertContains(response, empty.title)
        self.assertContains(response, protected.title)
        # Bərpa: hər sətirdə POST formu mövcud endpoint-ə.
        self.assertContains(response, f'action="{reverse("exams:restore_exam", args=[empty.slug])}"', html=False)
        self.assertContains(response, f'action="{reverse("exams:restore_exam", args=[protected.slug])}"', html=False)
        # Birdəfəlik silmə YALNIZ cəhdsiz imtahanda; cəhdli imtahanda kilid (disabled).
        self.assertContains(
            response, f'data-purge-url="{reverse("exams:permanent_delete_exam", args=[empty.slug])}"', html=False
        )
        self.assertNotContains(
            response, f'data-purge-url="{reverse("exams:permanent_delete_exam", args=[protected.slug])}"', html=False
        )
        self.assertEqual(response.content.decode().count("js-tx-purge"), 1)
        self.assertContains(response, "fa-lock", html=False)
        # Aktiv imtahan zibil cədvəlində deyil; KPI/toolbar gizli; alt-görünüşdə səhifələmə yoxdur.
        self.assertNotContains(response, self.active.title)
        self.assertNotContains(response, "data-tx-kpis", html=False)
        self.assertNotContains(response, "data-tx-toolbar", html=False)
        self.assertNotContains(response, "data-tx-sections", html=False)

    def test_trash_subview_empty_state(self):
        response = self.client.get(TRASH_URL)

        self.assertEqual(response.status_code, 200)
        trash = response.context["my_exams_dashboard"]["trash"]
        self.assertEqual(trash["count"], 0)
        self.assertEqual(trash["table_state"], "empty")
        self.assertContains(response, 'class="ems-state', html=False)
        self.assertNotContains(response, "js-tx-purge", html=False)

    def test_trash_subview_is_scoped_to_author(self):
        other = User.objects.create_user(username="w3_other", email="w3o@example.com", password="pass12345")
        _assign_user_to_org(other, self.organization, ProfileRole.TEACHER)
        Exam.objects.create(
            author=other,
            organization=self.organization,
            title="W3 Başqasının silinmişi",
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        mine = self._deleted_exam("W3 Mənim silinmişim")

        response = self.client.get(TRASH_URL)

        self.assertContains(response, mine.title)
        self.assertNotContains(response, "W3 Başqasının silinmişi")

    def test_unknown_exam_view_value_falls_back_to_list(self):
        response = self.client.get(f"{LIST_URL}&exam_view=whatever")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["my_exams_dashboard"]["trash"]["is_open"])
        self.assertContains(response, "data-tx-kpis", html=False)

    # ── sorğu büdcəsi ────────────────────────────────────────────────────────
    def test_trash_subview_query_count_is_independent_of_row_count(self):
        self._deleted_exam("W3 Q1")
        # İlk sorğu profil keşlərini (badge sayğacları və s.) isidir — ölçmədən kənar.
        self.client.get(TRASH_URL)
        with CaptureQueriesContext(self._connection()) as one_row:
            response = self.client.get(TRASH_URL)
        self.assertEqual(len(response.context["my_exams_dashboard"]["trash"]["table_rows"]), 1)

        for i in range(4):
            self._deleted_exam(f"W3 Q{i + 2}", with_attempt=(i % 2 == 0))
        with CaptureQueriesContext(self._connection()) as five_rows:
            response = self.client.get(TRASH_URL)
        self.assertEqual(len(response.context["my_exams_dashboard"]["trash"]["table_rows"]), 5)

        self.assertEqual(len(one_row), len(five_rows))

    @staticmethod
    def _connection():
        from django.db import connection

        return connection

    # ── endpoint yönləndirmələri ─────────────────────────────────────────────
    def test_restore_redirects_back_to_trash_subview(self):
        exam = self._deleted_exam("W3 Bərpa")

        response = self.client.post(reverse("exams:restore_exam", args=[exam.slug]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], TRASH_URL)
        exam.refresh_from_db()
        self.assertFalse(exam.is_deleted)

    def test_permanent_delete_redirects_back_to_trash_subview(self):
        exam = self._deleted_exam("W3 Birdəfəlik")

        response = self.client.post(reverse("exams:permanent_delete_exam", args=[exam.slug]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], TRASH_URL)
        self.assertFalse(Exam.objects.filter(pk=exam.pk).exists())

    def test_permanent_delete_of_protected_exam_redirects_with_error(self):
        exam = self._deleted_exam("W3 Qorunan", with_attempt=True)

        response = self.client.post(reverse("exams:permanent_delete_exam", args=[exam.slug]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], TRASH_URL)
        self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())

    # ── AJAX fragment ────────────────────────────────────────────────────────
    def test_section_fragment_renders_trash_subview(self):
        exam = self._deleted_exam("W3 Fragment silinmiş")

        response = self.client.get(
            reverse("accounts:profile_section_fragment", args=["my-exams"]) + "?exam_view=trash",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("data-tx-trash", payload["html"])
        self.assertIn(exam.title, payload["html"])
        self.assertNotIn("data-tx-kpis", payload["html"])


class ExamWizardModalScrollContractTests(TestCase):
    """Sehrbaz modalında TƏK scroll qatı (`.ew-pane-body`) — statik müqavilə.

    1280×800-də `.modal-body{max-height:calc(100vh - 190px)}` sehrbazın 680px-i ilə
    toqquşub ikinci scroll konteyneri yaradırdı; düzəliş CSS/JS-dədir, brauzer
    testi yoxdur — burada faylın müqaviləsi qorunur.
    """

    @staticmethod
    def _static(path):
        return (Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / path).read_text(encoding="utf-8")

    def test_wizard_modal_body_is_not_a_scroll_container(self):
        css = self._static("css/exam_wizard.css")
        rule_start = css.index(".exam-create-edit-modal.exam-wizard-modal .modal-body {")
        rule = css[rule_start : css.index("}", rule_start)]
        self.assertIn("max-height: none", rule)
        self.assertIn("overflow: hidden", rule)
        # Sehrbaz hündürlüyü dialoq kənarları çıxılmaqla viewport-a sığır.
        self.assertIn("height: min(680px, 86vh, calc(100dvh - 3.5rem))", css)

    def test_wheel_and_keys_are_forwarded_to_pane_body(self):
        js = self._static("js/exam_create_edit_modal/entry.js")
        self.assertIn('modalElement.addEventListener(\n            "wheel"', js)
        self.assertIn('querySelector(".ew-pane-body")', js)
        self.assertIn("PageDown", js)
        self.assertIn("{ passive: true }", js)
