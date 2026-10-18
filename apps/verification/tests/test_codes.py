"""Yoxlama kodu və publik ad maskası — DB-siz vahid testləri."""

from __future__ import annotations

import math
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.verification import codes
from apps.verification.qr import qr_matrix
from apps.verification.services import canonical_json, mask_holder_name


class CodeFormatTest(SimpleTestCase):
    def test_generated_code_has_prefix_four_groups_and_at_least_80_bits(self):
        code = codes.generate("qku")
        prefix, *groups = code.split("-")
        self.assertEqual(prefix, "QKU")
        self.assertEqual([len(g) for g in groups], [4, 4, 4, 4])
        body = "".join(groups)
        self.assertTrue(set(body) <= set(codes.ALPHABET))
        self.assertGreaterEqual(len(body) * math.log2(len(codes.ALPHABET)), 80)
        self.assertLessEqual(len(code), codes.CODE_MAX_LENGTH)

    def test_codes_are_random(self):
        self.assertEqual(len({codes.generate("qku") for _ in range(200)}), 200)

    def test_prefix_falls_back_for_unusable_slug(self):
        self.assertTrue(codes.generate("").startswith("EMS-"))
        self.assertEqual(codes.org_prefix("wcu-baku-campus"), "WCUBAK")

    def test_normalize_accepts_spacing_case_and_crockford_lookalikes(self):
        code = "QKU-7F3K-9M2P-XA4Q-1B20"
        self.assertEqual(codes.normalize(code), code)
        self.assertEqual(codes.normalize(" qku 7f3k 9m2p xa4q 1b2o "), code)  # O → 0
        self.assertEqual(codes.normalize("QKU7F3K9M2PXA4QLB20"), code)  # L → 1

    def test_normalize_rejects_garbage_without_db(self):
        for raw in ("", None, "QKU-1234", "<script>", "QKU-7F3K-9M2P-XA4Q-1B2U", "TOOLONGPREFIX-7F3K-9M2P-XA4Q-1B20"):
            self.assertIsNone(codes.normalize(raw), raw)


class MaskTest(SimpleTestCase):
    def test_full_name_is_masked_to_first_name_and_initial(self):
        user = SimpleNamespace(first_name="Elvin", last_name="Qurbanov", username="elvin.qurbanov")
        self.assertEqual(mask_holder_name(user), "Elvin Q.")

    def test_missing_names_never_reveal_the_username(self):
        self.assertEqual(mask_holder_name(SimpleNamespace(first_name="", last_name="", username="elvin.q")), "el***")
        self.assertEqual(mask_holder_name(SimpleNamespace(first_name="", last_name="Əliyeva", username="x")), "Ə.")


class CanonicalTest(SimpleTestCase):
    def test_canonical_json_is_key_order_independent(self):
        self.assertEqual(canonical_json({"b": 1, "a": "ə"}), canonical_json({"a": "ə", "b": 1}))

    def test_qr_matrix_is_square_and_deterministic(self):
        url = "https://ems.wcu.edu.az/yoxla/QKU-7F3K-9M2P-XA4Q-1B20/"
        matrix = qr_matrix(url)
        self.assertEqual(len(matrix), len(matrix[0]))
        self.assertEqual(matrix, qr_matrix(url))
