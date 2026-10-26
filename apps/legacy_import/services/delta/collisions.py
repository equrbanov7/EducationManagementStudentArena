"""Fənn KODU toqquşmasının düzəlişi — ``subject_collisions`` fazası (yalnız açıq seçiləndə; sahib 2026-10-26).

Magistr auditi: köhnə sistemdə payızda açılan fənlər (``lessons.id`` 2668+) delta tətbiqində ``QKU-<id>`` kodu ilə
tapılırdı, amma həmin kodlar tapşırıq idxalının ardıcıl verdiyi BAŞQA fənlərindir (bax ``resolve`` docstring-i).
Nəticə: legacy jurnal (dərs, xana, mövzu, sillabus) yanlış adlı fənnin açılışında — məs. 209/5 HP-də «Tədqiqat
analitikası» jurnalı «Quru ərazilərin bioresursları» adı ilə; dərs yükü fazası da həmin yanlış adla sətir açıb.

Faza (yeni sistem qalibdir; yalnız delta-nın ÖZ yaratdığı açılışa toxunulur):

1. Toqquşan legacy fənn (``Catalog.code_collision``) üçün düzgün kart: faza xəritəsi → ``QKU-L<id>`` → TƏK aktiv
   eyni adlı fənn; yoxdursa ehtiyac olanda yeni kart ``QKU-L<id>`` (legacy adı, kafedra legacy şöbəsindən).
2. Jurnalın hər qrupu üçün yanlış açılış W = (kod kartı, dövr, qrup). W delta paketinin manifestində deyilsə
   (rəsmi tapşırığın öz açılışıdır) — TOXUNULMUR. Düzgün fənn üzrə həmin qrupda açılış T artıq VARSA
   («əkiz jurnal»: T rəsmi cədvəl/yük açılışı, W legacy datası) — YAZILMIR, sayılır (sahib qərarı: unikal
   açar (fənn, dövr, qrup) W-nin fənnini dəyişməyə imkan vermir, birləşmə ayrıca qərardır). W başqa modulda
   (imtahan, fənn qovluğu, sorğu, cədvəl qaralaması, intensiv kurs) istinad olunursa və ya jurnal bağlıdırsa — ötürülür.
3. Qalan W-nin fənni düzgün karta keçirilir — fənn birləşdirməsinin rəsmi DB icazəsi ilə
   (``subject_merge_apply.allow_offering_subject_change``, ``audit.0004``); açılışa bağlı sillabus və delta-nın
   həmin qruplar üçün açdığı dərs yükü sətri (yalnız bu qruplar, eyni dövr) da keçirilir. Hər açılış üçün audit.
4. Legacy fənnin BÜTÜN qrupları həll olunubsa xəritə yazılır (``COLLISION_RESOURCE``) — növbəti delta qaçışları
   jurnalı düzgün fənnə bağlayır; əkiz qalan fənn xəritəsiz qalır və növbəti qaçışlarda ötürülür (ikinci nüsxə yox).

İdempotentdir: ikinci qaçış 0 yazı (W qalmır, xəritə var). Dry-run eyni kodu işlədib geri qaytarır.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.utils import timezone

from .extract import parse_id_list
from .resolve import COLLISION_RESOURCE, SUBJECT_ALT_CODE_PREFIX, text

REASON = "legacy_delta {tag}: fənn kodu toqquşması — legacy «{name}» jurnalı yanlış fənn kartındaydı"
#: W-yə bu modellərdən istinad varsa fənn dəyişdirilmir (registrar daxili sübutlar — dərs, xana, qeydiyyat — köçür).
_INTERNAL_APPS = ("registrar", "syllabus")
_MAX_CREDITS = 60


def delta_created_offerings(organization) -> set:
    """Delta paketlərinin manifestində YARADILMIŞ kimi qeyd olunan açılışlar (str pk)."""

    from .apply import BATCH_RESOURCE

    AuditLog = django_apps.get_model("audit", "AuditLog")
    created: set = set()
    for values in AuditLog.objects.filter(organization=organization, resource_type=BATCH_RESOURCE).values_list(
        "new_values", flat=True
    ):
        created.update(str(pk) for pk in ((values or {}).get("created") or {}).get("offerings") or ())
    return created


def fix_subject_collisions(run) -> None:
    full = set((run.bundle.get("snapshot") or {}).get("full_semesters") or [])
    journals_by_subject: dict = defaultdict(list)
    for journal in run.bundle["journals"]:
        if journal.get("fake") or journal.get("sonra_sil") or journal.get("semestr") not in full:
            continue
        journals_by_subject[journal["lesson_id"]].append(journal)
    created = None
    for legacy_id, journals in sorted(journals_by_subject.items()):
        legacy = run.legacy_subjects.get(legacy_id)
        wrong = run.catalog.code_collision(legacy) if legacy else None
        if wrong is None:
            continue
        if created is None:
            created = delta_created_offerings(run.organization)
        run.count("collision.subject")
        _LegacySubject(run, legacy, wrong, journals, created).fix()


class _LegacySubject:
    """Bir toqquşan legacy fənnin bütün jurnal qrupları."""

    def __init__(self, run, legacy, wrong, journals, created):
        self.run = run
        self.legacy = legacy
        self.wrong = wrong
        self.journals = journals
        self.created = created
        self.target = run.catalog.collision_target(legacy)
        self.pending = 0
        self.moved: list = []

    def fix(self) -> None:
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        org = self.run.organization
        seen: set = set()
        for journal in self.journals:
            period = self.run.period_of(journal["semestr"])
            if period is None:
                continue
            for group_id in parse_id_list(journal["groups_id"]):
                legacy_group = self.run.legacy_groups.get(group_id)
                unit = self.run.catalog.group_for(legacy_group)[0] if legacy_group else None
                if unit is None or (period.pk, unit.pk) in seen:
                    continue
                seen.add((period.pk, unit.pk))
                offering = (
                    CourseOffering.objects.filter(organization=org, subject=self.wrong, period=period, group=unit)
                    .select_related("period", "group")
                    .first()
                )
                if offering is None:
                    self.run.count("collision.no_wrong_offering")
                    continue
                self._slice(offering, unit)
        if self.moved:
            self._move_load_rows()
        if not self.pending and self.target is not None and self.moved:
            self._write_mapping()
        elif self.pending:
            self.run.count("collision.subject_pending")

    def _slice(self, offering, unit) -> None:
        from apps.registrar.public import handover

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        if str(offering.pk) not in self.created:
            self.run.count("collision.offering_not_from_delta")
            self.pending += 1
            return
        if self.target is not None and (
            CourseOffering.objects.filter(
                organization=self.run.organization, subject=self.target, period=offering.period, group=unit
            ).exists()
        ):
            self._twin(offering, unit)
            return
        blocked = _linked_elsewhere(offering)
        if blocked or not offering.is_active or handover.closed_offering_ids([offering.pk]):
            self.run.count(f"collision.blocked.{blocked or 'closed_or_inactive'}")
            self.pending += 1
            return
        if self.target is None:
            self.target = self._create_subject()
        self._move_offering(offering)

    def _twin(self, offering, unit) -> None:
        Row = django_apps.get_model("workload", "TeachingTaskRow")
        self.pending += 1
        self.run.count("collision.twin_exists")
        if Row.objects.filter(
            organization=self.run.organization, subject=self.wrong, period=offering.period, groups=unit
        ).exists():
            self.run.count("collision.twin_wrong_load_row")
        self.run.names(
            "subject_collision_twin",
            f"{unit.name} · {text(self.legacy.get('name'))}",
            f"{self.wrong.code} → {self.target.code}",
        )

    def _create_subject(self):
        Subject = django_apps.get_model("registrar", "Subject")
        chair = self.run.catalog.unit_for_department(self.legacy.get("department_id"))
        credits = Counter(
            int(j.get("kredit") or 0) for j in self.journals if 0 < int(j.get("kredit") or 0) <= _MAX_CREDITS
        )
        fields = {"ects": credits.most_common(1)[0][0]} if credits else {}
        subject = Subject.objects.create(
            organization=self.run.organization,
            code=f"{SUBJECT_ALT_CODE_PREFIX}{self.legacy['id']}",
            name=text(self.legacy.get("name")),
            chair_unit=chair if chair is not None and chair.unit_type == "chair" else None,
            is_active=True,
            **fields,
        )
        self.run.catalog.index_subject(subject)
        self.run.created("subjects", subject.pk)
        self.run.count("written.collision_subjects")
        return subject

    def _move_offering(self, offering) -> None:
        from apps.audit.public import log_action
        from apps.registrar.public import subject_merge_apply
        from core.constants import AuditAction

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        Syllabus = django_apps.get_model("syllabus", "Syllabus")
        now = timezone.now()
        subject_merge_apply.allow_offering_subject_change([self.wrong.pk], self.target.pk)
        try:
            CourseOffering.objects.filter(pk=offering.pk, subject=self.wrong).update(
                subject=self.target, updated_at=now
            )
        finally:
            subject_merge_apply.clear_offering_subject_change()
        syllabi = Syllabus.objects.filter(organization=self.run.organization, offering=offering, subject=self.wrong)
        self.run.count("collision.syllabus_reused_kept", syllabi.filter(reused_from__isnull=False).count())
        self.run.count(
            "written.collision_syllabi",
            syllabi.filter(reused_from__isnull=True).update(subject=self.target, updated_at=now),
        )
        log_action(
            action=AuditAction.UPDATE,
            user=self.run.actor,
            organization=self.run.organization,
            obj=offering,
            old_values={"subject": str(self.wrong.pk), "subject_code": self.wrong.code},
            new_values={"subject": str(self.target.pk), "subject_code": self.target.code},
            reason=REASON.format(tag=self.run.tag, name=text(self.legacy.get("name"))),
        )
        self.moved.append(offering)
        self.run.count("written.collision_offerings")

    def _move_load_rows(self) -> None:
        """Delta-nın dərs yükü fazası W üçün YANLIŞ adla sətir açıb — sətir yalnız köçürülən qrupları daşıyırsa
        (eyni dövr) fənni və mətni düzgün karta keçir; başqa qrup da varsa toxunulmur (sayılır)."""

        Row = django_apps.get_model("workload", "TeachingTaskRow")
        units = {offering.group_id for offering in self.moved}
        periods = {offering.period_id for offering in self.moved}
        rows = Row.objects.filter(
            organization=self.run.organization, subject=self.wrong, period_id__in=periods, groups__in=units
        ).distinct()
        now = timezone.now()
        for row in rows:
            groups = set(row.groups.values_list("pk", flat=True))
            if not groups <= units:
                self.run.count("collision.load_row_mixed_kept")
                continue
            Row.objects.filter(pk=row.pk).update(subject=self.target, subject_text=self.target.name, updated_at=now)
            self.run.count("written.collision_load_rows")

    def _write_mapping(self) -> None:
        from apps.audit.public import log_action
        from core.constants import AuditAction

        if self.run.catalog.collision_map.get(str(self.legacy["id"])) == str(self.target.pk):
            return
        log_action(
            action=AuditAction.CREATE,
            user=self.run.actor,
            organization=self.run.organization,
            obj=self.target,
            new_values={
                "legacy_subject": self.legacy["id"],
                "subject": str(self.target.pk),
                "wrong_subject": str(self.wrong.pk),
                "offerings": [str(offering.pk) for offering in self.moved],
            },
            reason=REASON.format(tag=self.run.tag, name=text(self.legacy.get("name"))),
            resource_type=COLLISION_RESOURCE,
            resource_id=str(self.legacy["id"]),
            resource_repr=self.target.code,
        )
        self.run.catalog.collision_map[str(self.legacy["id"])] = str(self.target.pk)
        self.run.count("written.collision_mappings")


def _linked_elsewhere(offering) -> str:
    """W-yə registrar/sillabus xaricindən istinad (imtahan, qovluq, sorğu, cədvəl qaralaması …) — modelin adı."""

    for relation in offering._meta.related_objects:
        model = relation.related_model
        if model._meta.app_label in _INTERNAL_APPS or model._meta.auto_created:
            continue
        if model._base_manager.filter(**{relation.field.name: offering}).exists():
            return model._meta.model_name
    return ""


__all__ = ["delta_created_offerings", "fix_subject_collisions"]
