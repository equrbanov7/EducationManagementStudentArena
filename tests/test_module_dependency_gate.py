"""Architecture gate regressions; synthetic source and graphs, no app database."""

import json

import pytest

from scripts import module_deps


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests():
    yield


def test_import_parser_reads_all_aliases_and_ignores_strings():
    source = """
import os, apps.exams.public as exams
from apps import registrar, organizations as orgs
from apps.accounts.public import helper
from .apps.ignored import thing
# from apps.comment import something
text = "from apps.example import something"
"""
    assert module_deps.imported_apps(source) == {"exams", "registrar", "organizations", "accounts"}


def test_import_parser_fails_on_invalid_python():
    with pytest.raises(SyntaxError):
        module_deps.imported_apps("from apps.exams import (")


def test_long_cycle_edges_exclude_incoming_and_outgoing_branches():
    graph = {"a": {"b"}, "b": {"c", "leaf"}, "c": {"a"}, "hub": {"a"}}
    assert module_deps.cyclic_edges(graph) == {("a", "b"), ("b", "c"), ("c", "a")}


def test_gate_rejects_new_three_module_cycle(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"cycles": [], "core_to_apps": [], "edges": {"a": ["b"], "b": ["c"]}}))
    monkeypatch.setattr(module_deps, "BASELINE_PATH", baseline)
    snapshot = {"cycles": [], "core_to_apps": [], "edges": {"a": ["b"], "b": ["c"], "c": ["a"]}}
    assert module_deps.cmd_check(snapshot) == 1


def test_gate_allows_healing_but_not_expanding_existing_cycle(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"cycles": ["a<->b"], "core_to_apps": [], "edges": {"a": ["b"], "b": ["a"]}}))
    monkeypatch.setattr(module_deps, "BASELINE_PATH", baseline)
    assert module_deps.cmd_check({"cycles": [], "core_to_apps": [], "edges": {"a": ["b"]}}) == 0
    expanded = {"cycles": ["a<->b"], "core_to_apps": [], "edges": {"a": ["b"], "b": ["a", "c"], "c": ["a"]}}
    assert module_deps.cmd_check(expanded) == 1


def test_gate_rejects_new_core_app_dependency(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"cycles": [], "core_to_apps": [], "edges": {}}))
    monkeypatch.setattr(module_deps, "BASELINE_PATH", baseline)
    assert module_deps.cmd_check({"cycles": [], "core_to_apps": ["registrar"], "edges": {}}) == 1


def test_relative_sibling_import_contributes_to_graph():
    assert module_deps.imported_apps("from ...exams.public import score", package="apps.accounts.views") == {"exams"}
