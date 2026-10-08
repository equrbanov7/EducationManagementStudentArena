"""Ehtimal olunan dublikat fənlərin hesabatı — YALNIZ OXU (müəllim rəyi Q1, 2026-10-08).

Normallaşdırılmış adı eyni olan fənləri (məs. «VoIP sistemlərinin …» / «Vo İP
sistemlərinin …») təşkilat üzrə qruplaşdırıb çap edir; hər fənnin kodu, aktivliyi və
açılış (jurnal) sayı göstərilir ki, admin hansının saxlanacağına qərar versin.

⚠️ Komanda HEÇ NƏ YAZMIR — birləşdirmə/silmə yoxdur (sahib qərarı tələb edir).

İstifadə::

    python manage.py report_duplicate_subjects                       # bütün aktiv təşkilatlar
    python manage.py report_duplicate_subjects --organization qku    # slug və ya id
    python manage.py report_duplicate_subjects --include-inactive --format json
"""

from __future__ import annotations

import csv
import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.rls import bypass_rls

from ...subject_duplicates import find_duplicate_subject_groups


class Command(BaseCommand):
    help = "Normallaşdırılmış adı eyni olan (ehtimal dublikat) fənlərin hesabatı. Yalnız oxu — heç nə yazmır."

    def add_arguments(self, parser):
        parser.add_argument("--organization", default=None, help="təşkilatın slug-ı və ya id-si")
        parser.add_argument("--include-inactive", action="store_true", help="arxivlənmiş fənləri də daxil et")
        parser.add_argument("--format", choices=("text", "json", "csv"), default="text")

    def _organizations(self, value):
        from django.apps import apps as django_apps

        Organization = django_apps.get_model("organizations", "Organization")
        if not value:
            return list(Organization.objects.filter(is_active=True).order_by("name"))
        found = Organization.objects.filter(slug=value).first()
        if found is None:
            try:
                found = Organization.objects.filter(pk=value).first()
            except (ValueError, TypeError, ValidationError):  # pk formatı uyğun deyil
                found = None
        if found is None:
            raise CommandError(f"Təşkilat tapılmadı: {value}")
        return [found]

    def handle(self, *args, **options):
        with bypass_rls():
            organizations = self._organizations(options["organization"])
            groups = find_duplicate_subject_groups(
                organizations=organizations, include_inactive=options["include_inactive"]
            )
        output_format = options["format"]
        if output_format == "json":
            payload = [
                {"organization": group.organization.slug, "key": group.key, "subjects": group.subjects}
                for group in groups
            ]
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        if output_format == "csv":
            writer = csv.writer(self.stdout)
            writer.writerow(["organization", "group_key", "subject_id", "code", "name", "is_active", "offerings"])
            for group in groups:
                for subject in group.subjects:
                    writer.writerow(
                        [
                            group.organization.slug,
                            group.key,
                            subject["id"],
                            subject["code"],
                            subject["name"],
                            subject["is_active"],
                            subject["offerings"],
                        ]
                    )
            return
        if not groups:
            self.stdout.write("Ehtimal olunan dublikat fənn tapılmadı.")
            return
        current = None
        for group in groups:
            if group.organization is not current:
                current = group.organization
                self.stdout.write(f"\n== {current.name} ({current.slug}) ==")
            self.stdout.write(f"\n• {group.key}  ({len(group.subjects)} fənn)")
            for subject in group.subjects:
                state = "" if subject["is_active"] else "  [arxiv]"
                self.stdout.write(
                    f"    {subject['code']:<14} {subject['name']}  — açılış: {subject['offerings']}{state}"
                    f"  (id {subject['id']})"
                )
        self.stdout.write(f"\nCəmi {len(groups)} qrup. Komanda heç nə dəyişmədi — birləşdirmə ayrıca qərar tələb edir.")
