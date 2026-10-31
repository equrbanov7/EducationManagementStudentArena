"""Source-verified fifteen-target syllabus recovery, default dry-run, atomic and undoable."""

from apps.legacy_import.services import empty_syllabus_recovery

from .recover_mr46_syllabus import Command as ExactSourceCommand


class Command(ExactSourceCommand):
    help = "On beş boş yük jurnalının öz-mənbə sillabusları; mövcud məzmun dəyişmir."
    output_prefix = "empty_syllabi"
    recovery = empty_syllabus_recovery
    undo_pattern = r"emptysyl-\d{8}-\d{6}-[a-f0-9]{4}"
