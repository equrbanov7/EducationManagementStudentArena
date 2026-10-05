"""Təhlükəsizlik auditi 2026-10-05 — laboratoriya fayl ölçüsü tavanı.

``Lab.max_file_size_mb`` müəllim tərəfindən yuxarı sərhədsiz təyin olunurdu
(``max(1, int(...))``): 100000 MB yazan müəllim tələbələrə istənilən ölçüdə
yükləməyə icazə verirdi (disk/yaddaş DoS). İndi server tərəfdə layihənin ümumi
yükləmə tavanına (``LAB_MAX_FILE_SIZE_MB``) sıxılır.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.courses.models import Course
from apps.labs.models import LAB_MAX_FILE_SIZE_MB, Lab
from apps.labs.views.shared._helpers import _parse_max_size_mb, _validate_and_prepare_lab_upload
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LabMaxFileSizeParseTest(SimpleTestCase):
    def test_ceiling_is_fifty_megabytes(self):
        self.assertEqual(LAB_MAX_FILE_SIZE_MB, 50)

    def test_huge_teacher_value_is_clamped(self):
        self.assertEqual(_parse_max_size_mb("100000", fallback=50), LAB_MAX_FILE_SIZE_MB)

    def test_valid_and_invalid_values(self):
        self.assertEqual(_parse_max_size_mb("10", fallback=50), 10)
        self.assertEqual(_parse_max_size_mb("0", fallback=50), 1)
        self.assertEqual(_parse_max_size_mb("abc", fallback=25), 25)

    def test_upload_validation_never_exceeds_ceiling(self):
        """Köhnə sətirdə 100000 MB qalsa belə yoxlama tavanla aparılır."""
        upload = SimpleUploadedFile("a.txt", b"x", content_type="text/plain")
        with mock.patch("apps.labs.views.shared._helpers.validate_uploaded_file") as validator:
            _validate_and_prepare_lab_upload(upload, allowed_extensions={".txt"}, max_size_mb=100000)
        self.assertEqual(validator.call_args.kwargs["max_size_mb"], LAB_MAX_FILE_SIZE_MB)


class LabMaxFileSizeModelTest(TestCase):
    def test_model_save_clamps_value(self):
        teacher = User.objects.create_user("lab_cap_t", "lab_cap_t@example.com", "StrongPass123!")
        org = Organization.objects.create(
            name="Lab Cap Org", org_type=OrganizationType.SCHOOL, owner=teacher, status="active", is_active=True
        )
        course = Course.objects.create(owner=teacher, title="Lab Cap", status="published", organization=org)
        lab = Lab.objects.create(
            course=course,
            title="Cap",
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=1),
            created_by=teacher,
            max_file_size_mb=100000,
        )
        lab.refresh_from_db()
        self.assertEqual(lab.max_file_size_mb, LAB_MAX_FILE_SIZE_MB)
