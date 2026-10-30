"""Two reviewed fixed families, never an arbitrary student/group transfer API."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    name: str
    parent: str
    legacy_parent: int
    children: tuple
    manifest_sha: str
    label_prefix: str
    batch_prefix: str
    resource: str
    display_name: str

    @property
    def targets(self):
        return {legacy: gid for legacy, gid, count in self.children}

    @property
    def counts(self):
        return {legacy: count for legacy, gid, count in self.children}

    @property
    def group_ids(self):
        return (self.parent, *self.targets.values())

    @property
    def moves(self):
        return sum(self.counts.values())


TSPX = Family(
    "tspx",
    "a163b409-dc4f-4454-91fb-9f09309e50df",
    798,
    ((927, "14afed62-6d55-4cdc-b58d-c1407a909859", 23), (929, "cc3dc2da-f694-4674-965f-2857c3fa7ac3", 26)),
    "c6eb79792406c3ddc51d842cae767f88a9035a26a3c29eb3696870f560af23bb",
    "135tspx",
    "tspx-roster",
    "workload.tspx_legacy_roster",
    "135 TSPX",
)
SI135 = Family(
    "si135",
    "24612646-7df4-4df6-a808-1c62b71ef92f",
    797,
    ((932, "a2823ece-f60e-4d06-8b6b-83552e2baa52", 23), (933, "dd4a2787-69b5-4cb3-848c-4be4c9b440aa", 22)),
    "3369a1b8c4504ae390e331e86f292d1374f513868c3750a581290d797057913a",
    "135si",
    "si135-roster",
    "workload.si135_legacy_roster",
    "135 Sİ",
)
