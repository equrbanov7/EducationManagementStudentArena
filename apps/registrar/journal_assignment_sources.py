"""Optional canonical assignment source; absent workload integration grants nothing."""

_provider = None
_joint_provider = None
_plan_provider = None


def register_teacher_journal_assignments(provider):
    global _provider
    _provider = provider


def teacher_journal_assignments(*, organization, teacher_id):
    from .language_cohort_journal import teacher_assignments

    result = dict(_provider(organization=organization, teacher_id=teacher_id)) if _provider is not None else {}
    result.update(teacher_assignments(organization=organization, teacher_id=teacher_id))
    return result


def register_joint_journal_candidates(provider):
    global _joint_provider
    _joint_provider = provider


def joint_journal_candidates(*, organization, teacher_id):
    """Official row identities only; registrar must independently check access and timetable."""
    if _joint_provider is None:
        return []
    return _joint_provider(organization=organization, teacher_id=teacher_id)


def register_teacher_journal_plan_hours(provider):
    global _plan_provider
    _plan_provider = provider


def teacher_journal_plan_hours(*, organization, teacher_id):
    if _plan_provider is None:
        return {}
    return _plan_provider(organization=organization, teacher_id=teacher_id)
