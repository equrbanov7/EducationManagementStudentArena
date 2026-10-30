"""Optional canonical assignment source; absent workload integration grants nothing."""

_provider = None


def register_teacher_journal_assignments(provider):
    global _provider
    _provider = provider


def teacher_journal_assignments(*, organization, teacher_id):
    return _provider(organization=organization, teacher_id=teacher_id) if _provider is not None else {}
