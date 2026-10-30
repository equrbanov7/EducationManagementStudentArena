"""Canlı mənbə yoxlaması ilə təsdiqlənmiş tək sillabus bərpası; standart dry-run."""

from apps.legacy_import.services import robotics_syllabus, workload_syllabi
from core.rls_pooling import rls_worker_atomic

from .recover_mr46_syllabus import Command as ExactSourceCommand


class Command(ExactSourceCommand):
    help = "Rəsmi yük yoxlaması: sabit Bilal8430 və ya robotics7715 öz-mənbə sillabusunu bərpa et."
    output_prefix = "workload_syllabi"
    recovery = workload_syllabi
    undo_pattern = r"wksyl-\d{8}-\d{6}-[a-f0-9]{4}"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--case", choices=("bilal", "robotics"), default="bilal")

    @rls_worker_atomic()
    def handle(self, *args, **options):
        # Parent handle owns the pooled RLS transaction and all DB access.
        self.recovery = robotics_syllabus if options["case"] == "robotics" else workload_syllabi
        return super().handle(*args, **options)
