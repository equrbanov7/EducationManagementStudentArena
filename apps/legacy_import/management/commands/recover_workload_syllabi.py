"""Canlı mənbə yoxlaması ilə təsdiqlənmiş tək sillabus bərpası; standart dry-run."""

from apps.legacy_import.services import workload_syllabi
from core.rls_pooling import rls_worker_atomic

from .recover_mr46_syllabus import Command as ExactSourceCommand


class Command(ExactSourceCommand):
    help = "Rəsmi yük yoxlaması: yalnız Bilal müəllimin legacy8430 sillabusunu öz jurnalına bərpa et."
    output_prefix = "workload_syllabi"
    recovery = workload_syllabi
    undo_pattern = r"wksyl-\d{8}-\d{6}-[a-f0-9]{4}"

    @rls_worker_atomic()
    def handle(self, *args, **options):
        # Parent handle owns the pooled RLS transaction and all DB access.
        return super().handle(*args, **options)
