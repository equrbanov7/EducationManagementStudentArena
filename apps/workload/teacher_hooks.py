"""Müəllim adı → hesab həlledicisinin QEYDİYYATI (sahib 2026-10-23, «Dərs yükü faylı»).

Ad tutuşdurması və FİN-siz müəllim hesabının yaradılması ``accounts`` tətbiqindədir
(``accounts.services.teacher_roster.chair_teachers.ChairTeacherResolver``). ``workload → accounts`` importu modul
qapısında DÖVR yaradır (``accounts`` artıq ``workload.public``-i işlədir) — ona görə həlledici
``accounts.apps.ready()``-də buraya qeydiyyatdan keçir (``organizations.register_cabinet_section_resolver`` naxışı).
Qeydiyyat yoxdursa yükləmə FAIL-CLOSED dayanır (səssiz «müəllimsiz» idxal olmasın).
"""

from __future__ import annotations

_FACTORY = None


def register_chair_teacher_resolver(factory) -> None:
    """``factory(organization, chair, *, actor_user, apply, tag)`` → ``.resolve(text)`` olan obyekt."""
    global _FACTORY
    _FACTORY = factory


def chair_teacher_resolver(organization, chair, *, actor_user, apply: bool, tag: str = ""):
    if _FACTORY is None:
        from .services.scoping import WorkloadDenied

        raise WorkloadDenied("workload.teacher_resolver_missing", "Müəllim tutuşdurma xidməti qeydiyyatda deyil.")
    return _FACTORY(organization, chair, actor_user=actor_user, apply=apply, tag=tag)


__all__ = ["chair_teacher_resolver", "register_chair_teacher_resolver"]
