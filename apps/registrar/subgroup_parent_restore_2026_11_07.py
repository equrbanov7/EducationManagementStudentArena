"""Alt qrupa keçiddə ana jurnaldan GİZLƏNƏN sətirlərin bərpası (sahib 2026-11-07).

Sahib: «alt qrupa keçirmək heç bir jurnalda nəyisə gizlətməli deyil … heç bir tələbənin nəticəsi, jurnal qeydləri
itməməlidir, müəllim jurnalını açanda nə yazıbsa onu da görsün». Köçürmə xidməti (:mod:`.transfer`) tələbə öz
qrupunun alt qrupuna keçəndə ana qrupun jurnalındakı sətri ``dropped`` + ``superseded_by`` edirdi — dərsləri və
qeydləri olan jurnal müəllimə «tələbəsiz» görünürdü (536 MU «Xətti cəbr»: 31 → 8). Kod düzəldi; bu modul əvvəlki
keçidlərin izini geri qaytarır:

* namizəd — ``dropped`` sətir, varisi AKTİVDİR və varisin qrupu sətrin qrupunun qeydiyyatlı alt qrupudur
  (``settings.parent_group``), tələbənin cari qrupu varisin qrupudur, ana jurnalda dərs var;
* sətir yenidən ``enrolled`` olur (qeydləri olduğu kimi); varisin qeydi yoxdursa o tarixçəyə keçir
  (``superseded_by`` = bərpa olunan sətir — köçürmənin tərsi ilə eyni forma), qeydi varsa ikisi də aktiv qalır
  (heç nə gizlənmir — ``*_both_kept`` sayılır).

Silmə yoxdur. İdempotentdir (bərpa olunmuş sətir namizəd deyil). Geri qaytarma: audit sətrindəki id-lər.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

REASON = "Sahib 2026-11-07: alt qrupa keçid ana jurnaldakı qeydləri gizlətməməlidir — sətir bərpası"
RESOURCE = "registrar.subgroup_parent_restore"
DATA_MODELS = ("LessonMark", "ComponentScore", "CriterionScore", "FinalGrade", "ResitRecord", "CourseWork")


def _model(name):
    return django_apps.get_model("registrar", name)


def _has_data(enrollment_id) -> bool:
    return any(_model(name).objects.filter(enrollment_id=enrollment_id).exists() for name in DATA_MODELS)


def _is_child(child, parent) -> bool:
    settings = child.settings if isinstance(getattr(child, "settings", None), dict) else {}
    return child is not None and parent is not None and str(settings.get("parent_group") or "") == str(parent.pk)


def candidates(organization):
    Enrollment = _model("Enrollment")
    Record = _model("StudentAcademicRecord")
    rows = (
        Enrollment.objects.select_for_update(of=("self",))
        .filter(
            organization=organization,
            status=Enrollment.Status.DROPPED,
            superseded_by__isnull=False,
            superseded_by__status=Enrollment.Status.ENROLLED,
            offering__group__isnull=False,
        )
        .select_related("offering__group", "superseded_by__offering__group")
    )
    for row in rows:
        successor = row.superseded_by
        parent, child = row.offering.group, successor.offering.group
        if not _is_child(child, parent):
            continue
        if not parent_journal_in_use(row):
            continue
        if not Record.objects.filter(
            organization=organization, student_id=row.student_id, group=child, is_active=True
        ).exists():
            continue
        yield row, successor


def parent_journal_in_use(enrollment) -> bool:
    """Ana qrupun jurnalında dərs var — müəllim orada yazır."""
    return _model("Lesson").objects.filter(offering_id=enrollment.offering_id).exists()


def restore_pair(row, successor, *, actor, organization, counts) -> None:
    """``row`` (ana jurnal) yenidən aktiv; qeydsiz ``successor`` tarixçəyə, qeydlisi aktiv qalır."""
    Enrollment = _model("Enrollment")
    row.status = Enrollment.Status.ENROLLED
    row.superseded_by = None
    row.save(update_fields=["status", "superseded_by", "updated_at"])
    counts["restored"] += 1
    if _has_data(successor.pk):
        counts["both_kept"] += 1
        changed = {"successor_kept": str(successor.pk)}
    else:
        successor.status = Enrollment.Status.DROPPED
        successor.superseded_by = row
        successor.save(update_fields=["status", "superseded_by", "updated_at"])
        counts["successor_retired"] += 1
        changed = {"successor_retired": str(successor.pk)}
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=row,
        old_values={"status": "dropped", "superseded_by": str(successor.pk)},
        new_values={"status": "enrolled", **changed},
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(row.pk),
    )


def keep_parent_journals(pairs, *, actor, organization) -> Counter:
    """Köçürmə xidmətinin alt qrup keçidi: dərsli ana jurnal sətirləri dərhal geri aktivləşir."""
    counts = Counter()
    for row, successor in pairs:
        if parent_journal_in_use(row):
            row.refresh_from_db(fields=["status", "superseded_by"])
            restore_pair(row, successor, actor=actor, organization=organization, counts=counts)
    return counts


def run(*, organization, actor, counts) -> None:
    pairs = list(candidates(organization))
    counts["candidates"] += len(pairs)  # boş qaçışda da say sətri çıxsın (prod-data-ops süzgəci)
    for row, successor in pairs:
        restore_pair(row, successor, actor=actor, organization=organization, counts=counts)


__all__ = ["REASON", "candidates", "keep_parent_journals", "parent_journal_in_use", "restore_pair", "run"]
