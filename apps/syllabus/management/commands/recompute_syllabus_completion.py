"""AÇIQ sillabus versiyalarının tamamlanmasını CARİ qayda ilə yenidən hesablayır (sahib 2026-10-10).

Niyə lazımdır
-------------
``SyllabusVersion.completion_percent`` (və bölmə ``is_complete``) KEŞDİR. RİM «Sistem tənzimləmələri»
sərbəst işi söndürəndə/yandıranda yeni qayda dövrlərinin (2026/2027+) sillabusunda ``self`` bölməsi
faizə daxil olmur/olur (8 ↔ 7 bölmə), qiymətləndirmə standartı isə dəyişir (midterm 20 ↔ 30). Redaktə
və göndərmə yolları onsuz da CARİ qayda ilə yenidən hesablayır — bu əmr isə toxunulmamış qaralamaların
və növbədəki versiyaların siyahıdakı faizini dərhal düzəldir.

Nə edir
-------
* Yalnız AÇIQ versiyalar (qaralama / düzəliş / təqdim / baxış). **Təsdiqlənmiş və arxiv versiyalar
  DƏYİŞMİR** — onlar kilidli sənəddir.
* ``assess`` bölməsinin SİSTEMİN yazdığı bal bölgüsü (``midterm``/``project``) versiyanın qaydasının
  standartına gətirilir (``note`` və digər açarlar toxunulmur, ``revision`` artırılmır — müəllim bu
  açarları onsuz da göndərmir).
* ``self`` bölməsinin datası HEÇ VAXT dəyişmir.
* **Quru icra defoltdur** — yazı yalnız ``--apply`` ilə; **idempotentdir** — ikinci icra 0 sətir toxunur;
  hər dəyişiklik ``audit_auditlog``-a düşür.

İstifadə::

    python manage.py recompute_syllabus_completion              # quru icra (nə dəyişəcəyini göstərir)
    python manage.py recompute_syllabus_completion --apply
    python manage.py recompute_syllabus_completion --org qku --apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ... import completion as completion_rules
from ...constants import OPEN_STATUSES, SectionKey
from ...models import SyllabusSection, SyllabusVersion
from ...policy import assessment_weights, standard_splits
from ...rules import for_version as rule_for_version
from ...services.drafts import default_assess_data, recompute_completion

_SPLIT_KEYS = ("midterm", "project")


def _split(data) -> tuple:
    data = data if isinstance(data, dict) else {}
    return tuple(data.get(key) for key in _SPLIT_KEYS)


class Command(BaseCommand):
    help = "Açıq sillabus versiyalarının tamamlanmasını cari qayda ilə yenidən hesablayır (idempotent, auditli)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", help="Yalnız bu təşkilatın slug-ı üzrə işlə")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Dəyişikliyi YAZ (defolt: quru icra — heç nə yazılmır)",
        )

    def handle(self, *args, **options):
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        with rls_worker_atomic(), bypass_rls():
            self._run(**options)

    def _plan(self, version):
        """``(assess_row, standard_split | None, new_percent)`` — quru icrada da eyni hesab."""
        organization = version.organization
        rule = rule_for_version(version, organization)
        sections = {row.section_id: row for row in version.sections.all()}
        section_map = {key: (row.data or {}) for key, row in sections.items()}
        assess = sections.get(SectionKey.ASSESS.value)
        standard = default_assess_data(organization, selfwork=rule.selfwork)
        target = None
        if assess is not None and _split(assess.data) != _split(standard):
            target = {key: standard[key] for key in _SPLIT_KEYS}
            section_map[SectionKey.ASSESS.value] = {**section_map[SectionKey.ASSESS.value], **target}
        report = completion_rules.evaluate(
            section_map,
            version.plan_hours or {},
            assessment_weights(organization, selfwork=rule.selfwork),
            selfwork=rule.selfwork,
            accepted_splits=standard_splits(organization),
        )
        return assess, target, report.percent

    def _run(self, *, org_slug=None, apply=False, **_options):
        queryset = (
            SyllabusVersion.objects.filter(status__in=sorted(OPEN_STATUSES))
            .select_related("organization", "syllabus", "syllabus__period", "applies_to_period")
            .prefetch_related("sections")
            .order_by("organization_id", "pk")
        )
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)

        scanned, planned = 0, []
        for version in queryset.iterator(chunk_size=200):
            scanned += 1
            assess, target, percent = self._plan(version)
            if target is not None or percent != version.completion_percent:
                planned.append((version, assess, target, percent))

        for version, _assess, target, percent in planned[:20]:
            split = f" · bölgü ⇒ {target['midterm']}/{target['project']}" if target else ""
            self.stdout.write(f"  → {version.pk} ({version.label}): {version.completion_percent}% ⇒ {percent}%{split}")
        if len(planned) > 20:
            self.stdout.write(f"  … və daha {len(planned) - 20} versiya")

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    f"QURU İCRA: {scanned} açıq versiyadan {len(planned)}-i yenilənəcəkdi (--apply verin)."
                )
            )
            return

        for version, assess, target, _percent in planned:
            with transaction.atomic():
                old_percent, old_split = version.completion_percent, _split(assess.data) if assess else None
                if target is not None:
                    SyllabusSection.objects.filter(pk=assess.pk).update(data={**(assess.data or {}), **target})
                # Təzə oxu: yuxarıdakı ``prefetch_related`` keşi köhnə bölgünü saxlayır.
                fresh = SyllabusVersion.objects.select_related(
                    "organization", "syllabus", "syllabus__period", "applies_to_period"
                ).get(pk=version.pk)
                recompute_completion(fresh)
                log_action(
                    AuditAction.UPDATE,
                    organization=fresh.organization,
                    obj=fresh,
                    old_values={"completion_percent": old_percent, "assess_split": old_split},
                    new_values={
                        "completion_percent": fresh.completion_percent,
                        "assess_split": _split(target) if target else old_split,
                    },
                    reason="recompute_syllabus_completion (sahib 2026-10-10)",
                    resource_type="syllabus.version",
                    resource_id=str(version.pk),
                    resource_repr=f"{version.syllabus_id} {version.label}",
                )

        self.stdout.write(self.style.SUCCESS(f"✅ {len(planned)} açıq versiya yeniləndi ({scanned} yoxlanıldı)."))
