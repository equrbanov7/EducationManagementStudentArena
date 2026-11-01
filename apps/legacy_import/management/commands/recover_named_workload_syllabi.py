"""Four exact own-source proofs; default dry-run and atomic compensating undo."""

from apps.legacy_import.services import named_syllabus_recovery

from .recover_mr46_syllabus import Command as ExactSourceCommand


class Command(ExactSourceCommand):
    help = "Tam ad və rəsmi mənbə ilə təsdiqlənmiş dörd öz sillabusu; mövcud məzmun dəyişmir."
    output_prefix = "named_syllabi"
    recovery = named_syllabus_recovery
    undo_pattern = r"namesyl-\d{8}-\d{6}-[a-f0-9]{4}"
