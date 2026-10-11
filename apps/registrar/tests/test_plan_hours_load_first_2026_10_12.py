"""Sahib 2026-10-12: sillabusun dərs saatı YÜKDƏN gəlir — yük sətri varsa plan ikinci mənbədir."""

from __future__ import annotations

from types import SimpleNamespace

from apps.registrar import plan_hours


def test_workload_hours_win_over_the_curriculum(monkeypatch):
    offering = SimpleNamespace(organization=None, subject=object(), group_id=None)
    monkeypatch.setattr(plan_hours, "workload_hours_for_offering", lambda o: {"lecture": 30, "lab": 30})
    monkeypatch.setattr(plan_hours, "plan_hours_for_subject", lambda **kw: {"lecture": 45, "seminar": 15})
    monkeypatch.setattr(plan_hours, "program_for_offering", lambda o: None)
    assert plan_hours.plan_hours_for_offering(offering) == {"lecture": 30, "lab": 30}


def test_curriculum_is_the_fallback_without_a_load_row(monkeypatch):
    offering = SimpleNamespace(organization=None, subject=object(), group_id=None)
    monkeypatch.setattr(plan_hours, "workload_hours_for_offering", lambda o: {})
    monkeypatch.setattr(plan_hours, "plan_hours_for_subject", lambda **kw: {"lecture": 45, "seminar": 15})
    monkeypatch.setattr(plan_hours, "program_for_offering", lambda o: None)
    assert plan_hours.plan_hours_for_offering(offering) == {"lecture": 45, "seminar": 15}
    assert plan_hours.plan_hours_for_offering(None) == {}
