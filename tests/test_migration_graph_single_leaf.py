"""Migrasiya qrafı — hər app üçün TƏK yarpaq (audit 2026-09-13, F-T5 / H10).

Paralel işləyən agentlər eyni nömrəli iki migrasiya yaratdı (`0074_*` ×2) və
20 dəqiqə ərzində hər `pytest`/`migrate` çalışması `CommandError: Conflicting
migrations` ilə bloklandı; tam dəstdə isə bir test teardown-da
`NodeNotFoundError` verdi. `migrate` bunu YALNIZ DB-yə çatanda deyir — bu test
isə DB-siz, diskdəki qrafdan, saniyənin altında, xdist worker-lərindən əvvəl
tutur (`MigrationLoader(connection=None)` yalnız faylları oxuyur).

Qayda `django.db.migrations.loader.MigrationLoader.detect_conflicts` ilə
eynidir (bir app-da birdən çox yarpaq = konflikt); əlavə olaraq sintetik qraf
üzərində yoxlayıcının özünün konflikti GÖRDÜYÜ sübut olunur ki, test boş
(vacuous) olmasın. Tarixi dublikat nömrələr (`contact/0002_*` ×2 + `0003_merge`)
merge ilə həll olunduğu üçün konflikt DEYİL — test məhz yarpaqlara baxır.
"""

from __future__ import annotations

from collections import Counter

from django.db.migrations.graph import MigrationGraph
from django.db.migrations.loader import MigrationLoader

import pytest


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests():
    # DB-siz test: `tests/conftest.py`-dəki autouse fixture-un `db` tələbini ləğv et.
    yield


def conflicting_leaves(graph: MigrationGraph) -> dict[str, list[str]]:
    """app_label → yarpaq migrasiya adları (yalnız birdən çox yarpağı olan app-lar)."""
    leaves_by_app: dict[str, list[str]] = {}
    for app_label, name in graph.leaf_nodes():
        leaves_by_app.setdefault(app_label, []).append(name)
    return {app: sorted(names) for app, names in leaves_by_app.items() if len(names) > 1}


def _disk_loader() -> MigrationLoader:
    # `connection=None` → `applied_migrations` boş qalır, DB-yə heç bir sorğu getmir.
    return MigrationLoader(None, ignore_no_migrations=True)


def test_every_app_has_exactly_one_leaf_migration():
    loader = _disk_loader()
    conflicts = conflicting_leaves(loader.graph)
    lines = [
        f"  {app}: {', '.join(names)}  → `manage.py makemigrations --merge` və ya faylı yenidən nömrələ"
        for app, names in sorted(conflicts.items())
    ]
    assert not conflicts, "Bir app-da birdən çox yarpaq migrasiya (konflikt):\n" + "\n".join(lines)


def test_matches_django_detect_conflicts():
    """Yoxlayıcı Django-nun öz `detect_conflicts` nəticəsi ilə eyni cavabı verir."""
    loader = _disk_loader()
    django_view = {app: sorted(names) for app, names in loader.detect_conflicts().items()}
    assert conflicting_leaves(loader.graph) == django_view == {}


def test_every_migrated_app_has_a_leaf():
    """Qrafda düyünü olan hər app-ın ən azı bir yarpağı var (qraf qırıq deyil)."""
    loader = _disk_loader()
    apps_with_nodes = {app for app, _name in loader.graph.nodes}
    apps_with_leaf = {app for app, _name in loader.graph.leaf_nodes()}
    assert apps_with_nodes == apps_with_leaf
    assert "exams" in apps_with_nodes and "registrar" in apps_with_nodes


def test_checker_reports_two_leaves_for_same_app():
    """Sintetik qraf: F-T5 ssenarisi (`0074_a` və `0074_b` hər ikisi `0073`-dən) tutulur."""
    graph = MigrationGraph()
    for node in (("registrar", "0073_base"), ("registrar", "0074_a"), ("registrar", "0074_b"), ("exams", "0001_x")):
        graph.add_node(node, None)
    graph.add_dependency(None, ("registrar", "0074_a"), ("registrar", "0073_base"))
    graph.add_dependency(None, ("registrar", "0074_b"), ("registrar", "0073_base"))

    assert conflicting_leaves(graph) == {"registrar": ["0074_a", "0074_b"]}
    assert Counter(app for app, _ in graph.leaf_nodes()) == {"registrar": 2, "exams": 1}

    # Merge migrasiyası hər ikisini birləşdirəndə konflikt yox olur.
    graph.add_node(("registrar", "0075_merge"), None)
    graph.add_dependency(None, ("registrar", "0075_merge"), ("registrar", "0074_a"))
    graph.add_dependency(None, ("registrar", "0075_merge"), ("registrar", "0074_b"))
    assert conflicting_leaves(graph) == {}
