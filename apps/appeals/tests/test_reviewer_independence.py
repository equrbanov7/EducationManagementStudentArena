"""EXAM-P1-18 — appeal reviewer independence (conflict-of-interest).

İmtahanın müəllifi öz imtahanına qarşı apellyasiyaya baxa/qərar verə bilməz;
superadmin bu qadağadan azaddır.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.appeals.services.permissions import (
    _is_conflicted_reviewer,
    can_decide_appeal,
    can_review_appeal,
)


def _request(user):
    return SimpleNamespace(user=user)


def _appeal(author_id, org_id=1, graded_by_id=None):
    return SimpleNamespace(
        exam=SimpleNamespace(author_id=author_id),
        organization_id=org_id,
        attempt=SimpleNamespace(graded_by_id=graded_by_id),
    )


class ReviewerIndependenceTests(SimpleTestCase):
    def test_author_is_conflicted(self):
        user = SimpleNamespace(id=7, is_superuser=False, is_superadmin=False)
        self.assertTrue(_is_conflicted_reviewer(_request(user), _appeal(author_id=7)))

    def test_non_author_is_not_conflicted(self):
        user = SimpleNamespace(id=8, is_superuser=False, is_superadmin=False)
        self.assertFalse(_is_conflicted_reviewer(_request(user), _appeal(author_id=7)))

    def test_original_grader_is_conflicted(self):
        # Seq1: müəllif olmasa da, ilk qiymətləndirən grader konfliktlidir.
        user = SimpleNamespace(id=42, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7, graded_by_id=42)
        self.assertTrue(_is_conflicted_reviewer(_request(user), appeal))

    def test_independent_reviewer_not_grader_not_author(self):
        user = SimpleNamespace(id=99, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7, graded_by_id=42)
        self.assertFalse(_is_conflicted_reviewer(_request(user), appeal))

    def test_missing_author_is_not_conflicted(self):
        user = SimpleNamespace(id=8, is_superuser=False, is_superadmin=False)
        self.assertFalse(_is_conflicted_reviewer(_request(user), _appeal(author_id=None)))

    @patch("apps.appeals.services.permissions.is_superadmin_user", return_value=True)
    def test_superadmin_is_never_conflicted(self, _mock):
        user = SimpleNamespace(id=7, is_superuser=True, is_superadmin=True)
        self.assertFalse(_is_conflicted_reviewer(_request(user), _appeal(author_id=7)))

    @patch("apps.appeals.services.permissions.is_exam_center_user", return_value=True)
    @patch("apps.appeals.services.permissions._same_tenant", return_value=True)
    def test_can_review_and_decide_denied_for_author(self, _tenant, _center):
        author = SimpleNamespace(id=7, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7)
        self.assertFalse(can_review_appeal(_request(author), appeal))
        self.assertFalse(can_decide_appeal(_request(author), appeal))

    @patch("apps.appeals.services.permissions.is_exam_center_user", return_value=True)
    @patch("apps.appeals.services.permissions._same_tenant", return_value=True)
    def test_can_review_and_decide_allowed_for_independent_center_user(self, _tenant, _center):
        reviewer = SimpleNamespace(id=99, is_superuser=False, is_superadmin=False)
        appeal = _appeal(author_id=7)
        self.assertTrue(can_review_appeal(_request(reviewer), appeal))
        self.assertTrue(can_decide_appeal(_request(reviewer), appeal))
