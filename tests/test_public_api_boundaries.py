import pytest

from scripts.public_api_boundaries import check, inventory, private_imports


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests():
    yield


def test_public_models_and_own_implementation_are_allowed():
    assert (
        private_imports(
            "from apps.exams.public import score\nfrom apps.exams import models, public\nfrom apps.accounts.services import own",
            "accounts",
        )
        == set()
    )


def test_aliases_multiline_and_multiple_imports_cannot_hide_private_access():
    assert private_imports(
        "import os, apps.exams.services as service\nfrom apps.exams.services import (score as s, grade)\nfrom apps import registrar",
        "accounts",
    ) == {"apps.exams.services", "apps.exams.services:score", "apps.exams.services:grade", "apps.registrar"}


def test_comments_and_relative_imports_are_not_cross_app_dependencies():
    assert (
        private_imports(
            '# from apps.exams.private import x\ntext="import apps.exams.private"\nfrom .service import x', "accounts"
        )
        == set()
    )


def test_new_debt_rejected_and_debt_reduction_allowed():
    baseline = {"a -> old"}
    assert check({"a -> old", "a -> new"}, baseline) == 1
    assert check(set(), baseline) == 0


def test_inventory_excludes_migrations_and_tests_but_checks_management(tmp_path):
    app = tmp_path / "apps" / "accounts"
    for relative in ["tests/test_x.py", "migrations/0001_x.py", "management/commands/demo.py"]:
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("from apps.exams.services import score")
    assert inventory(tmp_path) == {"apps/accounts/management/commands/demo.py -> apps.exams.services:score"}


def test_relative_sibling_service_import_is_checked():
    assert private_imports("from ...exams.services import score", "accounts", package="apps.accounts.views") == {
        "apps.exams.services:score"
    }
    assert private_imports("from ...exams.public import score", "accounts", package="apps.accounts.views") == set()
