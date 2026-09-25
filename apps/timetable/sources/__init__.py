"""Baza → mühərrik: əhatə, qruplar/ailələr, kurs vahidləri, axınlar, kontekst.

Bu paket YALNIZ OXUYUR. Registrar modellərinə ``django.apps.get_model`` ilə,
registrar servislərinə ``apps.registrar.public`` fasadı ilə müraciət olunur
(kontekst qapısı: ``scripts/context_map.py``).
"""

from .problem import Problem, build_problem, normalize_weekdays
from .scope import normalize_scope, scope_groups, scope_label, scope_options

__all__ = [
    "Problem",
    "build_problem",
    "normalize_scope",
    "normalize_weekdays",
    "scope_groups",
    "scope_label",
    "scope_options",
]
