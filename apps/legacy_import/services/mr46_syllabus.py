"""MR46 sabit bərpa müqaviləsi; əvvəlki public çağırış səthi saxlanır."""

from . import exact_syllabus_recovery as core
from .exact_syllabus_recovery import RestoreError, digest, model  # noqa: F401

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OFFERING = "acc97b99-90bc-4fb3-b01b-b56ff630b7d2"
AUTHOR = 7942
UNIQID = "qVHmrlOPQd3p6Rk4UBsT"
RESOURCE = "legacy_import.mr46_syllabus"
SPEC = core.RecoverySpec(
    ORG,
    PERIOD,
    OFFERING,
    AUTHOR,
    UNIQID,
    RESOURCE,
    15363,
    442,
    1500,
    8891,
    457,
    90,
    23,
    18,
    "mr46-syllabus/1",
    "QKU-1500",
    (7942, 8415),
    "mr46-",
    "MR46",
    "MR46 teacher requests own old journal syllabus; owner authorizes this exact target despite legacy subject-id mismatch",
    "MR-000046: müəllimin legacy8891 sillabusu öz 15363 jurnalına bağlıdır. Mənbədə 457 → jurnalda 1500 fərqi sistem sahibinin bu jurnal üçün açıq bərpa qərarı ilə həll edilib.",
)


def load(path, expected):
    return core.load(path, expected, SPEC)


def scope(org, actor):
    return core.scope(org, actor, SPEC)


def apply(org, actor, loaded):
    return core.apply(org, actor, loaded, SPEC)


def undo(org, actor, batch):
    return core.undo(org, actor, batch, SPEC)


def write_audit(org, actor, batch, values, reason):
    return core.write_audit(org, actor, batch, values, reason, SPEC)
