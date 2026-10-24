"""``link_lesson_syllabus_weeks`` — mövcud dərsləri sillabusun həftəlik plan sətrinə bağlayır (sahib 2026-10-25).

«Sillabuslar götürüləndən sonra jurnalda müəllimin keçdiyi dərslər — hansı mövzunu keçib-keçməyib
göstərmir». Yeni dərs plandan seçiləndə ``Lesson.syllabus_week`` avtomatik dolur; bu əmr ƏVVƏLKİ dərslər
üçündür: ``topic`` mətni açılışın TƏSDİQLƏNMİŞ sillabus planındakı hansısa sətrin mövzusu ilə DƏQİQ
(boşluq sıxılmış, registr nəzərə alınmadan) eynidirsə və ``syllabus_week`` boşdursa → həmin sətrin nömrəsi
(eyni başlıqlı bir neçə sətir varsa İLKİ). Uyğunluq yoxdursa heç nə yazılmır — uydurma bağ yoxdur.

* DEFOLT DRY-RUN — bazaya heç nə yazılmır; ``--apply`` ilə bir tranzaksiyada.
* Yalnız ``syllabus_week IS NULL`` sətirlərə yazılır, ``topic`` toxunulmur → idempotent (təkrar 0 yazır).
* Stdout-a YALNIZ saylar (``syllabus_week_link: açar=say …``) — mövzu / ad çap edilmir.

İstifadə::

    manage.py link_lesson_syllabus_weeks --org qku [--apply]
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.registrar import journal_topics
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "syllabus_week_link:"
CHUNK = 400


def _line(pairs) -> str:
    return PREFIX + " " + " ".join(f"{key}={value}" for key, value in pairs)


class Command(BaseCommand):
    help = "Mövzusu sillabus planının sətri ilə dəqiq eyni olan dərslərə syllabus_week yazır (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("syllabus_week_link_organization_unknown")
            if options["apply"]:
                with transaction.atomic():
                    counts = link_weeks(organization, apply=True)
            else:
                counts = link_weeks(organization, apply=False)
        mode = "apply" if options["apply"] else "dry_run"
        self.stdout.write(_line([("mode", mode)]))
        self.stdout.write(_line(counts.items()))


def link_weeks(organization, *, apply: bool) -> dict:
    """Sayları qaytarır; ``apply=True`` olduqda bağları yazır (çağıran tranzaksiyanı açır)."""
    from apps.syllabus import public as syllabus_public

    Lesson = django_apps.get_model("registrar", "Lesson")
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    pending = Lesson.objects.filter(organization=organization, syllabus_week__isnull=True).exclude(topic="")
    offering_ids = sorted(set(pending.values_list("offering_id", flat=True)), key=str)
    counts = {
        "lessons_candidate": 0,
        "offerings": len(offering_ids),
        "offerings_with_plan": 0,
        "lessons_no_plan": 0,
        "lessons_matched": 0,
        "lessons_unmatched": 0,
        "written": 0,
    }
    for start in range(0, len(offering_ids), CHUNK):
        chunk = offering_ids[start : start + CHUNK]
        offerings = list(
            CourseOffering.objects.filter(pk__in=chunk).only("id", "organization", "subject", "period", "instructor")
        )
        plans = syllabus_public.approved_week_rows_for_offerings(offerings)
        week_rows = {
            offering_id: journal_topics.syllabus_week_rows(None, plan_rows=rows) for offering_id, rows in plans.items()
        }
        counts["offerings_with_plan"] += sum(1 for rows in week_rows.values() if rows)
        by_week = defaultdict(list)
        for lesson_id, offering_id, topic in pending.filter(offering_id__in=chunk).values_list(
            "id", "offering_id", "topic"
        ):
            counts["lessons_candidate"] += 1
            rows = week_rows.get(offering_id) or []
            if not rows:
                counts["lessons_no_plan"] += 1
                continue
            week = journal_topics.resolve_syllabus_week(None, topic, week_rows=rows)
            if week is None:
                counts["lessons_unmatched"] += 1
                continue
            counts["lessons_matched"] += 1
            by_week[week].append(lesson_id)
        if apply:
            for week, ids in by_week.items():
                counts["written"] += Lesson.objects.filter(pk__in=ids, syllabus_week__isnull=True).update(
                    syllabus_week=week
                )
    return counts
