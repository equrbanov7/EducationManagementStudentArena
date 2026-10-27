"""``restore_archived_students`` — konkret səhv arxivlənmiş tələbənin girişi (sahib 2026-10-27)."""

from django.core.management import call_command

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.tests import test_repair_commands as base

pytestmark = pytest.mark.django_db
actor = base.actor
organization = base.organization
run = base.run
archived_cohort = base.archived_cohort


def _run(capsys, *args):
    call_command("restore_archived_students", "--org", base._SLUG, "--actor", "repair_actor", *args)
    out = capsys.readouterr().out
    return dict(line.split(" ", 1)[1].split("=") for line in out.splitlines() if line.startswith("restore_archived:"))


def test_archived_account_without_an_active_record_is_never_restored(archived_cohort, capsys):
    user = archived_cohort[1970]
    counts = _run(capsys, "--usernames", f"{user.username},yoxdur.bele", "--apply")
    assert counts == {"skip_no_active_record": "1", "skip_unknown": "1"}
    assert UserProfile.objects.get(user=user).access_state == UserProfile.AccessState.ARCHIVED


def test_dry_run_is_the_default(archived_cohort, capsys):
    counts = _run(capsys, "--usernames", archived_cohort[999].username)
    assert counts["dry_run"] == "1"
