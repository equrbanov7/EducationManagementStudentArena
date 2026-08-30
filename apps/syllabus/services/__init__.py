"""Sillabus servis qatı — modulun YEGANƏ yazı/oxu giriş nöqtəsi.

View, API və management əmrləri buradan istifadə edir; modelə birbaşa
``status = ...`` yazan kod OLMAMALIDIR (state maşını
:mod:`apps.syllabus.state_machine`-dədir).
"""

from .drafts import (  # noqa: F401
    SectionConflict,
    blank_section_data,
    copy_from_previous,
    create_draft,
    create_next_version,
    import_migrated_version,
    recompute_completion,
    save_section,
    section_data_map,
)
from .queries import (  # noqa: F401
    audit_entries,
    list_syllabi,
    review_queue,
    status_counts,
    version_diff,
    version_timeline,
)
from .scoping import SyllabusActor, can_view, is_author, resolve_actor  # noqa: F401
from .workflow import (  # noqa: F401
    approve,
    archive,
    available_actions,
    reject,
    request_revision,
    resume_editing,
    start_review,
    submit,
    withdraw,
)

__all__ = [
    "SectionConflict",
    "SyllabusActor",
    "approve",
    "archive",
    "audit_entries",
    "available_actions",
    "blank_section_data",
    "can_view",
    "copy_from_previous",
    "create_draft",
    "create_next_version",
    "import_migrated_version",
    "is_author",
    "list_syllabi",
    "recompute_completion",
    "reject",
    "request_revision",
    "resolve_actor",
    "resume_editing",
    "review_queue",
    "save_section",
    "section_data_map",
    "start_review",
    "status_counts",
    "submit",
    "version_diff",
    "version_timeline",
    "withdraw",
]
