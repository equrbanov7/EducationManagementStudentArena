"""Separate frozen 135 Sİ source, sharing the canonical roster implementation."""

from ...services.tspx_roster_plan import read_si135_plan
from .repair_tspx_legacy_roster import Command as FixedRosterCommand


class Command(FixedRosterCommand):
    help = "MyEdu üzrə 135 Sİ reyestrini dəqiq 23/22+1 bölgüsü ilə bərpa edir; defolt atomik dry-run."
    output_prefix = "si135_roster"

    def load_plan(self, options):
        return read_si135_plan(options["manifest"], options["manifest_sha256"])
