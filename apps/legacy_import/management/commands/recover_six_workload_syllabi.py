"""Source-verified six-target syllabus recovery, default dry-run, atomic and undoable."""

from apps.legacy_import.services import six_syllabus_recovery

from .recover_mr46_syllabus import Command as ExactSourceCommand


class Command(ExactSourceCommand):
    help = "Altı sabit yük jurnalının öz-mənbə sillabusları; mövcud məzmun dəyişmir."
    output_prefix = "six_syllabi"
    recovery = six_syllabus_recovery
    undo_pattern = r"sixsyl-\d{8}-\d{6}-[a-f0-9]{4}"
