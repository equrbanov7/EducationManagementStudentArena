"""Whole-account lookup remains a fixed tenant, contact-minimised probe."""

import hashlib
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Organization
from apps.workload.services.scoped_snapshot.worker_identity import ORG, collect_worker1068
from core.rls import apply_rls_request_context, reset_rls_context


class WorkerIdentityProbeTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(username="worker_probe_admin")
        self.org = Organization.objects.create(pk=ORG, name="QKU", slug="qku", owner=self.admin, org_type="university")
        self.user = get_user_model().objects.create_user(
            username="rasoul.rezvanian",
            first_name="RASOUL",
            last_name="REZVANIAN",
            email="PRIVATE_ADDRESS@example.test",
            password="PRIVATE_HASH_SENTINEL",
        )
        profile = self.user.profile
        profile.organization, profile.patronymic = self.org, "a"
        profile.save(update_fields=["organization", "patronymic"])
        apply_rls_request_context(user_id=self.admin.pk, org_id=ORG, bypass=False)

    def tearDown(self):
        reset_rls_context()

    def test_whole_account_candidate_without_teacher_role_is_found_without_contact_export(self):
        data = collect_worker1068()
        self.assertEqual([u["id"] for u in data["worker1068_identity_candidates"]], [self.user.pk])
        encoded = json.dumps(data, default=str)
        self.assertNotIn("PRIVATE_ADDRESS", encoded)
        self.assertNotIn("PRIVATE_HASH_SENTINEL", encoded)
        self.assertNotIn("password", encoded)
        self.assertFalse(data["worker1068_identity_candidates"][0]["email_matches_source"])

    def test_email_digest_lookup_can_find_latin_name_variant_without_exposing_email(self):
        self.user.first_name, self.user.last_name = "Rəsul", "Başqa yazılış"
        self.user.username = "source_exact_email_match"
        self.user.save(update_fields=["first_name", "last_name", "username"])
        sha = hashlib.sha256(self.user.email.strip().casefold().encode()).hexdigest()
        with patch("apps.workload.services.scoped_snapshot.worker_identity.SOURCE_EMAIL_SHA256", sha):
            data = collect_worker1068()
        self.assertEqual([u["id"] for u in data["worker1068_identity_candidates"]], [self.user.pk])
        self.assertTrue(data["worker1068_identity_candidates"][0]["email_matches_source"])
        self.assertNotIn(self.user.email, json.dumps(data, default=str))

    def test_foreign_matching_account_is_counted_but_identity_is_not_exported(self):
        other = get_user_model().objects.create_user(
            username="FOREIGN_PRIVATE", first_name="Rasoul", last_name="Rezvanian"
        )
        data = collect_worker1068()
        summary = data["worker1068_identity_summary"][0]
        self.assertEqual(
            (
                summary["global_candidate_count"],
                summary["tenant_candidate_count"],
                summary["outside_tenant_candidate_count"],
            ),
            (2, 1, 1),
        )
        self.assertNotIn(other.username, json.dumps(data, default=str))
