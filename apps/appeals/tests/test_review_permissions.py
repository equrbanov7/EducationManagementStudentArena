"""Appeal review/decide icazələri.

İmtahan mərkəzi bu platformada imtahan məzmununu da mərkəzi olaraq yaradır, ona
görə öz yaratdığı imtahana gələn apellyasiyaya da qərar verə bilir — köhnə
"reviewer müstəqilliyi" (müəllif öz işinə qərar verə bilməz) qadağası
qaldırılıb; imtahan mərkəzi rolu onsuz da tək qərar səlahiyyətidir. Tenant
kənarı və qeyri-mərkəz istifadəçilər üçün icazə bağlı qalır.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.appeals.services.permissions import can_decide_appeal, can_review_appeal


def _request(user):
    return SimpleNamespace(user=user)


def _appeal(author_id, org_id=1):
    return SimpleNamespace(exam=SimpleNamespace(author_id=author_id), organization_id=org_id)


class AppealReviewPermissionTests(SimpleTestCase):
    @patch("apps.appeals.services.permissions.is_exam_center_user", return_value=True)
    @patch("apps.appeals.services.permissions._same_tenant", return_value=True)
    def test_exam_center_author_can_review_and_decide(self, _tenant, _center):
        # Yeni davranış: imtahanı yaradan mərkəz istifadəçisi öz imtahanına da qərar verə bilir.
        author = SimpleNamespace(id=7, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7)
        self.assertTrue(can_review_appeal(_request(author), appeal))
        self.assertTrue(can_decide_appeal(_request(author), appeal))

    @patch("apps.appeals.services.permissions.is_exam_center_user", return_value=True)
    @patch("apps.appeals.services.permissions._same_tenant", return_value=True)
    def test_independent_exam_center_user_can_review_and_decide(self, _tenant, _center):
        reviewer = SimpleNamespace(id=99, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7)
        self.assertTrue(can_review_appeal(_request(reviewer), appeal))
        self.assertTrue(can_decide_appeal(_request(reviewer), appeal))

    @patch("apps.appeals.services.permissions.is_exam_center_user", return_value=False)
    @patch("apps.appeals.services.permissions._same_tenant", return_value=True)
    def test_non_exam_center_user_denied(self, _tenant, _center):
        teacher = SimpleNamespace(id=7, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7)
        self.assertFalse(can_review_appeal(_request(teacher), appeal))
        self.assertFalse(can_decide_appeal(_request(teacher), appeal))

    @patch("apps.appeals.services.permissions.is_exam_center_user", return_value=True)
    @patch("apps.appeals.services.permissions._same_tenant", return_value=False)
    def test_cross_tenant_denied(self, _tenant, _center):
        reviewer = SimpleNamespace(id=99, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7, org_id=2)
        self.assertFalse(can_review_appeal(_request(reviewer), appeal))
        self.assertFalse(can_decide_appeal(_request(reviewer), appeal))
