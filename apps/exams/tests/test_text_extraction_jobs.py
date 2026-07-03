"""P3: asinxron mətn-çıxarma job axını üçün testlər.

Test settings-də CELERY_TASK_ALWAYS_EAGER=True — .delay() dərhal icra olunur,
ona görə start endpointi eager rejimdə birbaşa yekun statusu verə bilər.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import pytest

from apps.exams.models import TextExtractionJob
from apps.exams.tasks import run_text_extraction_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def org(django_user_model):
    from apps.organizations.models import Organization
    from core.constants import OrganizationType

    owner = django_user_model.objects.create_user(username="extract-org-owner", password="x")
    return Organization.objects.create(
        name="Extract Org",
        slug="extract-org",
        org_type=OrganizationType.SCHOOL,
        status="active",
        is_active=True,
        owner=owner,
    )


def _make_member(django_user_model, org, *, username, profile_role, role_name):
    from apps.organizations.models import Membership

    user = django_user_model.objects.create_user(username=username, password="x")
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"role": org.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )
    return user


@pytest.fixture
def teacher(django_user_model, org):
    return _make_member(django_user_model, org, username="extract-teacher", profile_role="teacher", role_name="teacher")


@pytest.fixture
def teacher_client(client, teacher, org):
    client.force_login(teacher)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _upload(name="questions.txt", content=b"1. Sual metni?\nA) a\nB) b\n"):
    return SimpleUploadedFile(name, content, content_type="text/plain")


class TestStartEndpoint:
    def test_txt_upload_extracts_text(self, teacher_client, teacher):
        resp = teacher_client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()})
        assert resp.status_code in (200, 202)
        data = resp.json()
        assert data["ok"] is True

        job = TextExtractionJob.objects.get(pk=data["job_id"])
        assert job.user == teacher
        # Eager Celery: task artıq bitib
        assert job.status == TextExtractionJob.STATUS_SUCCESS
        assert "Sual metni" in job.text
        # Müvəqqəti fayl silinib
        assert not job.file

    def test_missing_file_rejected(self, teacher_client):
        resp = teacher_client.post(reverse("exams:start_text_extraction"), {})
        assert resp.status_code == 400

    def test_blocked_extension_fails_job(self, teacher_client):
        resp = teacher_client.post(
            reverse("exams:start_text_extraction"),
            {"source_file": _upload(name="virus.exe", content=b"MZ...")},
        )
        data = resp.json()
        job = TextExtractionJob.objects.get(pk=data["job_id"])
        assert job.status == TextExtractionJob.STATUS_FAILED
        assert job.error

    def test_anonymous_redirected(self, client):
        resp = client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()})
        assert resp.status_code == 302

    def test_student_forbidden(self, client, django_user_model, org):
        student = _make_member(
            django_user_model, org, username="extract-student", profile_role="student", role_name="student"
        )
        client.force_login(student)
        session = client.session
        session["active_organization"] = org.slug
        session.save()
        resp = client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()})
        assert resp.status_code in (302, 403)


class TestStatusEndpoint:
    def test_owner_sees_result(self, teacher_client, teacher):
        start = teacher_client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()}).json()
        resp = teacher_client.get(reverse("exams:text_extraction_status", kwargs={"job_id": start["job_id"]}))
        data = resp.json()
        assert data["status"] == TextExtractionJob.STATUS_SUCCESS
        assert "Sual metni" in data["text"]

    def test_other_teacher_gets_404(self, teacher_client, client, django_user_model, org):
        start = teacher_client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()}).json()

        other = _make_member(
            django_user_model, org, username="extract-other", profile_role="teacher", role_name="teacher"
        )
        client.force_login(other)
        session = client.session
        session["active_organization"] = org.slug
        session.save()
        resp = client.get(reverse("exams:text_extraction_status", kwargs={"job_id": start["job_id"]}))
        assert resp.status_code == 404


class TestTaskDirect:
    def test_missing_job_is_noop(self):
        assert run_text_extraction_job("00000000-0000-0000-0000-000000000000") == "missing"


class TestAiGenerationJob:
    """P4: AI generasiya job axını (eager rejimdə köhnə cavab forması)."""

    def _post_ai(self, client, exam_slug, extra=None):
        data = {"prompt": "Python funksiyaları", "question_count": "2", "difficulty": "hard"}
        data.update(extra or {})
        return client.post(
            reverse("exams:ai_generate_question_bank", args=[exam_slug]),
            data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    @pytest.fixture
    def exam(self, teacher, org):
        from apps.exams.models import Exam

        return Exam.objects.create(
            title="AI Job Exam",
            exam_type="test",
            author=teacher,
            organization=org,
        )

    def test_eager_success_returns_classic_payload(self, teacher_client, exam, monkeypatch):
        from apps.exams.views.teacher import question_bank as qb_facade

        def fake_generate(**kwargs):
            assert kwargs["prompt_text"] == "Python funksiyaları"
            assert kwargs["difficulty"] == "hard"
            return {"ok": True, "text": "1. Sual\nA) a", "question_count": 1, "remaining": 4, "limit": 5}

        monkeypatch.setattr(qb_facade, "generate_question_bank_text", fake_generate)
        resp = self._post_ai(teacher_client, exam.slug)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True and data["question_count"] == 1 and data["remaining"] == 4
        assert "1. Sual" in data["text"]

        job = TextExtractionJob.objects.latest("created_at")
        assert job.kind == TextExtractionJob.KIND_AI_GENERATE
        assert job.result_meta["limit"] == 5

    def test_eager_service_refusal_maps_to_400(self, teacher_client, exam, monkeypatch):
        from apps.exams.views.teacher import question_bank as qb_facade

        monkeypatch.setattr(
            qb_facade,
            "generate_question_bank_text",
            lambda **kw: {"ok": False, "error": "limit doldu", "remaining": 0, "limit": 5},
        )
        resp = self._post_ai(teacher_client, exam.slug)
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False and data["error"] == "limit doldu" and data["limit"] == 5

    def test_eager_service_exception_maps_to_500(self, teacher_client, exam, monkeypatch):
        from apps.exams.views.teacher import question_bank as qb_facade

        def boom(**kw):
            raise RuntimeError("gemini down")

        monkeypatch.setattr(qb_facade, "generate_question_bank_text", boom)
        resp = self._post_ai(teacher_client, exam.slug)
        assert resp.status_code == 500
        assert resp.json()["ok"] is False

    def test_uploaded_file_text_reaches_service(self, teacher_client, exam, monkeypatch):
        from apps.exams.views.teacher import question_bank as qb_facade

        seen = {}

        def fake_generate(**kwargs):
            seen.update(kwargs)
            return {"ok": True, "text": "x", "question_count": 0}

        monkeypatch.setattr(qb_facade, "generate_question_bank_text", fake_generate)
        resp = self._post_ai(
            teacher_client,
            exam.slug,
            extra={"source_file": _upload(name="lecture.txt", content=b"Funksiyalar movzusu")},
        )
        assert resp.status_code == 200
        assert "Funksiyalar movzusu" in seen["source_text"]
        job = TextExtractionJob.objects.latest("created_at")
        assert not job.file  # müvəqqəti fayl silinib


class TestStashMathFlag:
    """P3-b: workbench import yolu üçün stash_math bayrağı."""

    def test_txt_with_stash_flag_succeeds_without_token(self, teacher_client):
        # TXT üçün stash yalnız PDF-də işə düşür — flag zərərsizdir.
        resp = teacher_client.post(
            reverse("exams:start_text_extraction"),
            {"source_file": _upload(), "stash_math": "1"},
        )
        data = resp.json()
        job = TextExtractionJob.objects.get(pk=data["job_id"])
        assert job.status == TextExtractionJob.STATUS_SUCCESS
        assert job.payload == {"stash_math": True}
        assert "math_token" not in job.result_meta

    def test_pdf_stash_failure_is_non_fatal(self, teacher_client, monkeypatch):
        # stash xətası mətni bloklamamalıdır (qeyri-fatal) — PDF-i real parse
        # etməmək üçün extract-i də mock-layırıq.
        import apps.exams.services.parsing as parsing_facade

        monkeypatch.setattr(parsing_facade, "extract_text_from_upload", lambda f: "PDF mətni")

        import apps.exams.services.import_media as import_media

        def boom(f):
            raise RuntimeError("stash down")

        monkeypatch.setattr(import_media, "stash_math_images", boom)

        resp = teacher_client.post(
            reverse("exams:start_text_extraction"),
            {"source_file": _upload(name="notes.pdf", content=b"%PDF-1.4 fake"), "stash_math": "1"},
        )
        job = TextExtractionJob.objects.get(pk=resp.json()["job_id"])
        assert job.status == TextExtractionJob.STATUS_SUCCESS
        assert job.text == "PDF mətni"
        assert "math_token" not in job.result_meta


class TestExportJobs:
    """C2: böyük export-ların job axını (eager rejimdə köhnə attachment UX)."""

    @pytest.fixture
    def exam(self, teacher, org):
        from apps.exams.models import Exam

        return Exam.objects.create(title="Export Exam", exam_type="test", author=teacher, organization=org)

    def test_small_dataset_stays_sync(self, teacher_client, exam):
        resp = teacher_client.get(reverse("exams:export_exam_results_xlsx", args=[exam.slug]))
        assert resp.status_code == 200
        assert "attachment" in resp["Content-Disposition"]
        # sinxron yol job YARATMIR
        assert not TextExtractionJob.objects.filter(kind=TextExtractionJob.KIND_EXPORT).exists()

    def test_large_dataset_goes_through_job_eager(self, teacher_client, exam, settings):
        settings.EXPORT_SYNC_MAX_ROWS = -1  # hər şey "böyük" sayılsın
        resp = teacher_client.get(reverse("exams:export_exam_results_xlsx", args=[exam.slug]))
        # eager Celery: job dərhal bitir → fayl birbaşa endirilir (köhnə UX)
        assert resp.status_code == 200
        assert "attachment" in resp["Content-Disposition"]
        job = TextExtractionJob.objects.get(kind=TextExtractionJob.KIND_EXPORT)
        assert job.status == TextExtractionJob.STATUS_SUCCESS
        assert job.result_file
        assert job.result_meta["filename"].endswith(".xlsx")

    def test_pending_job_redirects_to_waiting_page(self, teacher_client, teacher, org, exam, settings, monkeypatch):
        settings.EXPORT_SYNC_MAX_ROWS = -1
        settings.JOB_WORKER_PICKUP_TIMEOUT = 0  # watchdog söndürülür — real-broker pending ssenarisi
        # delay-i no-op et → job pending qalır → waiting səhifəsinə redirect
        from apps.exams import tasks as exams_tasks

        monkeypatch.setattr(exams_tasks.run_export_job, "delay", lambda *a, **kw: None)
        resp = teacher_client.get(reverse("exams:export_exam_results_xlsx", args=[exam.slug]))
        assert resp.status_code == 302
        job = TextExtractionJob.objects.get(kind=TextExtractionJob.KIND_EXPORT)
        assert reverse("exams:export_job_waiting", kwargs={"job_id": job.pk}) in resp["Location"]

        waiting = teacher_client.get(resp["Location"])
        assert waiting.status_code == 200

        # task-ı əl ilə işlət → download endpointi faylı verir
        from apps.exams.tasks import run_export_job

        assert run_export_job(str(job.pk)) == TextExtractionJob.STATUS_SUCCESS
        download = teacher_client.get(reverse("exams:export_job_download", kwargs={"job_id": job.pk}))
        assert download.status_code == 200
        assert "attachment" in download["Content-Disposition"]

    def test_download_is_owner_only(self, teacher_client, client, django_user_model, org, exam, settings):
        settings.EXPORT_SYNC_MAX_ROWS = -1
        teacher_client.get(reverse("exams:export_exam_results_xlsx", args=[exam.slug]))
        job = TextExtractionJob.objects.get(kind=TextExtractionJob.KIND_EXPORT)

        other = _make_member(
            django_user_model, org, username="export-other", profile_role="teacher", role_name="teacher"
        )
        client.force_login(other)
        session = client.session
        session["active_organization"] = org.slug
        session.save()
        resp = client.get(reverse("exams:export_job_download", kwargs={"job_id": job.pk}))
        assert resp.status_code == 404

    def test_registry_org_mismatch_fails_closed(self, teacher, org, django_user_model, exam):
        from apps.exams.export_registry import run_export
        from apps.organizations.models import Organization

        other_owner = django_user_model.objects.create_user(username="other-org-owner", password="x")
        other_org = Organization.objects.create(
            name="Başqa Org",
            slug="basqa-org",
            org_type=org.org_type,
            status="active",
            is_active=True,
            owner=other_owner,
        )
        with pytest.raises(ValueError):
            run_export(
                "exam_results_xlsx",
                user=teacher,
                organization=other_org,
                params={"exam_id": exam.pk, "filters": {}},
            )


class TestWorkerDeadFallback:
    """Codex blocking fix: broker sağ, worker ölü → pickup-watchdog inline icra."""

    @pytest.fixture(autouse=True)
    def _fast_watchdog(self, settings):
        settings.JOB_WORKER_PICKUP_TIMEOUT = 0.1

    @pytest.fixture
    def _dead_worker(self, monkeypatch):
        # delay uğurla "qəbul edir" (broker sağ) amma heç nə icra olunmur (worker ölü)
        from apps.exams import tasks as exams_tasks

        monkeypatch.setattr(exams_tasks.run_text_extraction_job, "delay", lambda *a, **kw: None)
        monkeypatch.setattr(exams_tasks.run_ai_generation_job, "delay", lambda *a, **kw: None)
        monkeypatch.setattr(exams_tasks.run_export_job, "delay", lambda *a, **kw: None)

    def test_extract_falls_back_to_sync(self, teacher_client, _dead_worker):
        resp = teacher_client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == TextExtractionJob.STATUS_SUCCESS
        assert "Sual metni" in data["text"]

    def test_ai_falls_back_to_classic_response(self, teacher_client, teacher, org, _dead_worker, monkeypatch):
        from apps.exams.models import Exam
        from apps.exams.views.teacher import question_bank as qb_facade

        exam = Exam.objects.create(title="Dead Worker Exam", exam_type="test", author=teacher, organization=org)
        monkeypatch.setattr(
            qb_facade,
            "generate_question_bank_text",
            lambda **kw: {"ok": True, "text": "1. S", "question_count": 1, "remaining": 9, "limit": 10},
        )
        resp = teacher_client.post(
            reverse("exams:ai_generate_question_bank", args=[exam.slug]),
            {"prompt": "x", "question_count": "1", "difficulty": "easy"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        # Codex-in tələb etdiyi davranış: 202 YOX, klassik sinxron cavab
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True and data["text"] == "1. S" and data["remaining"] == 9

    def test_export_falls_back_to_attachment(self, teacher_client, teacher, org, _dead_worker, settings):
        from apps.exams.models import Exam

        settings.EXPORT_SYNC_MAX_ROWS = -1
        exam = Exam.objects.create(title="Dead Worker Export", exam_type="test", author=teacher, organization=org)
        resp = teacher_client.get(reverse("exams:export_exam_results_xlsx", args=[exam.slug]))
        assert resp.status_code == 200
        assert "attachment" in resp["Content-Disposition"]


class TestCasClaim:
    """PENDING→PROCESSING keçidi atomikdir — ikinci icra no-op qayıdır."""

    def test_second_run_is_noop(self, teacher_client, monkeypatch):
        start = teacher_client.post(reverse("exams:start_text_extraction"), {"source_file": _upload()}).json()
        job_id = start["job_id"]
        assert TextExtractionJob.objects.get(pk=job_id).status == TextExtractionJob.STATUS_SUCCESS

        # İkinci çağırış parse-a girməməlidir: parse partlasa belə status qayıtmalıdır
        import apps.exams.services.parsing as parsing_facade

        def boom(f):
            raise AssertionError("ikinci icra parse-a girdi!")

        monkeypatch.setattr(parsing_facade, "extract_text_from_upload", boom)
        assert run_text_extraction_job(job_id) == TextExtractionJob.STATUS_SUCCESS


class TestMathTokenPropagation:
    """P3-b: stash token status meta-sına düşür (Codex smoke-da formula-suz PDF ilə görünməmişdi)."""

    def test_token_reaches_status_meta(self, teacher_client, monkeypatch):
        import apps.exams.services.import_media as import_media
        import apps.exams.services.parsing as parsing_facade

        monkeypatch.setattr(parsing_facade, "extract_text_from_upload", lambda f: "PDF mətni")
        monkeypatch.setattr(import_media, "stash_math_images", lambda f: "tok123")

        start = teacher_client.post(
            reverse("exams:start_text_extraction"),
            {"source_file": _upload(name="formulali.pdf", content=b"%PDF-1.4 fake"), "stash_math": "1"},
        ).json()
        resp = teacher_client.get(reverse("exams:text_extraction_status", kwargs={"job_id": start["job_id"]}))
        data = resp.json()
        assert data["status"] == TextExtractionJob.STATUS_SUCCESS
        assert data["meta"]["math_token"] == "tok123"
