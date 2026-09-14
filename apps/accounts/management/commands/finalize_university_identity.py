"""``finalize_university_identity`` — deploy hazırlığı: «MyEdu» izlərini real ada keçir.

Sahibin qərarı (2026-09-14): bu Qərbi Kaspi Universitetinin real sistemidir —
«my.edu» adı/prefiksi heç yerdə görünməməlidir. Bu komanda İKİ şeyi düzəldir
(istifadəçi adları ayrıca ``rename_legacy_usernames`` ilə):

1. Təşkilat: ``name`` → «Qərbi Kaspi Universiteti», ``slug`` → ``qku``
   (sessiyalardakı ``active_organization`` köhnə slug-dursa ``core.tenancy``
   fallback ilə yenidən seçir; deploy-dan əvvəl sessiya onsuz da yoxdur).
2. Tələbə nömrəsi (``UserProfile.institutional_identifier``): ``myedu-student-<N>``
   → ``<N>`` (legacy sistemdəki tələbə nömrəsi; prefiks yox). Unikal indeks
   (org, NFKC identifier) qorunur — ``N`` legacy pk-dır, təkrarsızdır.
3. Fənn kodu (``registrar.Subject.code``, transkript/jurnal/«Fənlərim»də görünür):
   ``MYEDU-L<N>`` → ``QKU-<N>``. Legacy sistemdə real fənn kodu yox idi
   (``lessons.lesson_code`` zibildir), ``N`` legacy fənn id-sidir. İdxal
   sabiti ``SUBJECT_CODE_PREFIX`` toxunulmur — köçürmə bitib, kodla axtarış yoxdur.

Toxunulmayan: ``OrgUnit.slug`` ``myedu-dep-<N>`` (yalnız daxili açar, UI-da yoxdur),
``Program.code`` ``MYEDU-<N>`` (UI rəsmi şifri göstərir; idxal açarıdır).

Dry-run DEFAULT-dur; ``--apply`` yazır. İdempotentdir.

    manage.py finalize_university_identity --org-slug myedu-univ
    manage.py finalize_university_identity --org-slug myedu-univ --apply
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Func, Value

from apps.accounts.models import UserProfile
from apps.organizations.models import Organization
from apps.registrar.models import Subject
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

UNIVERSITY_NAME = "Qərbi Kaspi Universiteti"
UNIVERSITY_SLUG = "qku"
_LEGACY_STUDENT_PREFIX = "myedu-student-"
_LEGACY_ID_RE = re.compile(r"^myedu-student-(\d+)$")
_LEGACY_SUBJECT_PREFIX = "MYEDU-L"
_SUBJECT_PREFIX = "QKU-"
_LEGACY_SUBJECT_RE = re.compile(r"^MYEDU-L(\d+)$")


class Command(BaseCommand):
    help = "Təşkilat adı/slug-ı və `myedu-student-N` tələbə nömrələrini real formaya keçirir (dry-run defolt)."

    def add_arguments(self, parser):
        parser.add_argument("--org-slug", default="myedu-univ", help="Dəyişəcək təşkilatın cari slug-ı")
        parser.add_argument("--new-name", default=UNIVERSITY_NAME)
        parser.add_argument("--new-slug", default=UNIVERSITY_SLUG)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org_slug"]).first()
            if organization is None:
                organization = Organization.objects.filter(slug=options["new_slug"]).first()
                if organization is None:
                    raise CommandError(f"organization_not_found: {options['org_slug']}")
            if (
                options["new_slug"] != organization.slug
                and Organization.objects.filter(slug=options["new_slug"]).exists()
            ):
                raise CommandError(f"slug_taken: {options['new_slug']}")

            legacy_ids = UserProfile.objects.filter(institutional_identifier__startswith=_LEGACY_STUDENT_PREFIX)
            bad = [
                v for v in legacy_ids.values_list("institutional_identifier", flat=True) if not _LEGACY_ID_RE.match(v)
            ]
            if bad:
                raise CommandError(f"unexpected_identifier_format: {bad[:5]}")
            identifier_count = legacy_ids.count()
            legacy_subjects = Subject.objects.filter(code__startswith=_LEGACY_SUBJECT_PREFIX)
            bad_codes = [c for c in legacy_subjects.values_list("code", flat=True) if not _LEGACY_SUBJECT_RE.match(c)]
            if bad_codes:
                raise CommandError(f"unexpected_subject_code_format: {bad_codes[:5]}")
            subject_count = legacy_subjects.count()

            self.stdout.write(
                f"Təşkilat: «{organization.name}» ({organization.slug}) → «{options['new_name']}» ({options['new_slug']})"
            )
            self.stdout.write(f"Tələbə nömrəsi: {identifier_count} × `{_LEGACY_STUDENT_PREFIX}N` → `N`")
            self.stdout.write(f"Fənn kodu: {subject_count} × `{_LEGACY_SUBJECT_PREFIX}N` → `{_SUBJECT_PREFIX}N`")
            if not options["apply"]:
                self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
                return

            if organization.name != options["new_name"] or organization.slug != options["new_slug"]:
                organization.name = options["new_name"]
                organization.slug = options["new_slug"]
                organization.save(update_fields=["name", "slug"])
            updated = legacy_ids.update(
                institutional_identifier=Func(
                    F("institutional_identifier"),
                    Value(_LEGACY_STUDENT_PREFIX),
                    Value(""),
                    function="REPLACE",
                )
            )
            subjects_updated = legacy_subjects.update(
                code=Func(F("code"), Value(_LEGACY_SUBJECT_PREFIX), Value(_SUBJECT_PREFIX), function="REPLACE")
            )
            remaining = UserProfile.objects.filter(institutional_identifier__istartswith="myedu").count()
            remaining += Subject.objects.filter(code__istartswith="myedu").count()
            if remaining:
                raise CommandError(f"legacy_identifiers_remaining: {remaining}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Yazıldı: təşkilat yeniləndi, {updated} tələbə nömrəsi, {subjects_updated} fənn kodu düzəldildi."
                )
            )
