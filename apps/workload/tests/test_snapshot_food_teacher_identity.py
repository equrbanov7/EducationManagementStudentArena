"""Privacy and scope regression tests for source-pinned identity candidates."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.organizations.models import Membership, Organization
from apps.workload.services.scoped_snapshot import food_teacher_identity as probe
from apps.workload.tests.factories import activate_member, make_org, make_structure

User = get_user_model()


class FoodTeacherIdentityTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("food_probe_owner")
        self.org = Organization.objects.create(id=probe.ORG, name="Probe", slug="food-probe", owner=owner)
        self.foreign = make_org("food-probe-foreign")
        self.pair = probe.identity_hash("İlham", "Əliyev")
        self.triple = probe.identity_hash("İlham", "Əliyev", "Atababa")
        self.pins = patch.object(probe, "SOURCE_PAIRS", {self.pair: self.triple})
        self.pins.start()
        self.addCleanup(self.pins.stop)

    def profile(self, username, *, organization=None, father="Atababa", active=True, state="active", first="İlham"):
        user = User.objects.create_user(username, first_name=first, last_name="Əliyev", is_active=active)
        user.profile.organization = organization or self.org
        user.profile.patronymic = father
        user.profile.access_state = state
        user.profile.save()
        return user

    def collect(self):
        return probe.collect_food_teacher_identity()

    def test_unassigned_and_wrong_role_profiles_included_without_authority(self):
        unassigned = self.profile("unassigned", active=False, state="archived")
        student = self.profile("wrong_role", father="Başqa")
        activate_member(self.org, student, "student", permissions=["course.view"])
        rows = {r["user_id"]: r for r in self.collect()["food_source_identity_candidates"]}
        self.assertEqual(set(rows), {unassigned.id, student.id})
        self.assertEqual(rows[unassigned.id]["memberships"], [])
        self.assertFalse(rows[unassigned.id]["user_is_active"])
        self.assertEqual(rows[unassigned.id]["access_state"], "archived")
        self.assertFalse(rows[student.id]["memberships"][0]["role_has_grade_input"])
        summary = self.collect()["food_source_identity_pairs"][0]
        self.assertEqual(summary["candidate_count"], 2)
        self.assertEqual(summary["full_triple_match_count"], 1)
        self.assertEqual(summary["status"], "ambiguous_pair")
        self.assertNotIn("accepted_user_id", summary)

    def test_other_org_and_inconsistent_membership_scope_excluded(self):
        self.profile("foreign_match", organization=self.foreign)
        own = self.profile("own_match")
        activate_member(self.foreign, own, "foreign_role", permissions=["grade.input"])
        role = activate_member(self.org, own, "own_role", permissions=[])
        foreign_group = make_structure(self.foreign)["group"]
        Membership.objects.filter(user=own, organization=self.org, role=role).update(scope_unit=foreign_group)
        rows = self.collect()["food_source_identity_candidates"]
        self.assertEqual([r["user_id"] for r in rows], [own.id])
        self.assertEqual(rows[0]["memberships"], [])

    def test_missing_father_is_explicit_and_never_invented(self):
        self.profile("missing_father", father="  ")
        row = self.collect()["food_source_identity_candidates"][0]
        self.assertTrue(row["profile_father_missing"])
        self.assertIsNone(row["full_triple_identity_hash"])
        self.assertFalse(row["source_full_triple_matches"])
        with patch.object(probe, "SOURCE_PAIRS", {self.pair: None}):
            row = self.collect()["food_source_identity_candidates"][0]
            self.assertTrue(row["source_father_missing"])
            self.assertIsNone(row["source_full_triple_matches"])

    def test_read_only_and_no_unmatched_or_sensitive_output(self):
        matched = self.profile("MATCH_USERNAME_PRIVATE")
        self.profile("UNMATCHED_USERNAME_PRIVATE", first="UNMATCHED_NAME_PRIVATE")

        def guard(execute, sql, params, many, context):
            self.assertTrue(sql.lstrip().upper().startswith("SELECT"))
            for column in ('"password"', '"email"', '"phone"', '"fin"', '"username"'):
                self.assertNotIn(column, sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(guard):
            payload = self.collect()
        encoded = json.dumps(payload, default=str)
        for secret in ("PRIVATE", "İlham", "Əliyev", "Atababa", "first_name", "patronymic", "password"):
            self.assertNotIn(secret, encoded)
        self.assertEqual([r["user_id"] for r in payload["food_source_identity_candidates"]], [matched.id])
        self.assertFalse(payload["food_source_identity_coverage"]["automatic_authorization"])

    def test_no_match_is_limited_to_scanned_profiles(self):
        self.profile("different_name", first="İlhan")
        payload = self.collect()
        self.assertEqual(payload["food_source_identity_candidates"], [])
        self.assertEqual(payload["food_source_identity_coverage"]["matched_pair_count"], 0)
        self.assertEqual(payload["food_source_identity_pairs"][0]["status"], "no_pair_match_in_scanned_tenant_profiles")

    def test_strict_normalization_preserves_letters_boundaries_and_punctuation(self):
        h = probe.identity_hash
        self.assertEqual(h("  İLHAM&nbsp;", "ƏLİYEV"), h("ilham", "əliyev"))
        for first, last in (("Ilham", "Əliyev"), ("İlham", "Eliyev"), ("İ.", "Əliyev"), ("İlham", "Əli-yev")):
            self.assertNotEqual(h(first, last), self.pair)
        self.assertNotEqual(h("ab", "c"), h("a", "bc"))

    def test_source_pins_are_bounded_and_hash_only(self):
        from apps.workload.services.scoped_snapshot.food_teacher_identity_spec import SOURCE_PAIRS

        self.assertEqual(len(SOURCE_PAIRS), 14)
        for pair, triple in SOURCE_PAIRS.items():
            self.assertRegex(pair, r"^[a-f0-9]{64}$")
            if triple is not None:
                self.assertRegex(triple, r"^[a-f0-9]{64}$")
