"""Source-verified one-target syllabus recovery, default dry-run, atomic and undoable."""

from apps.legacy_import.services import genetics_syllabus_recovery

from .recover_mr46_syllabus import Command as ExactSourceCommand


class Command(ExactSourceCommand):
    help = "İnsan genetikası jurnalının öz-mənbə sillabusu; mövcud məzmun dəyişmir."
    output_prefix = "genetics_syllabus"
    recovery = genetics_syllabus_recovery
    undo_pattern = r"gensyl-\d{8}-\d{6}-[a-f0-9]{4}"
