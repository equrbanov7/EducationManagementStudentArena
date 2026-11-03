"""Dublikat fənlərin birləşdirilməsi — RİM üçün idarə əmri (2026-10-19). Default: DRY-RUN.

İstifadə::

    python manage.py merge_subjects --org qku --target QKU-12 --source QKU-48
    python manage.py merge_subjects --org qku --target QKU-12 --source QKU-48,QKU-77 \\
        --apply --reason "Tədris şöbəsinin 2026-10-19 təklifi: eyni fənnin iki kartı"

Məntiq veb dialoqu ilə EYNİDİR (:mod:`apps.registrar.subject_merge` /
:mod:`apps.registrar.subject_merge_apply`): önizləmə izi tətbiqdə yenidən yoxlanılır, toqquşma
varsa heç nə yazılmır. Geri qaytarma: ``undo_subject_merge --audit-id <id>``.

PLAN rejimi (sahib 2026-11-04, ~95 dublikat kart — BİR backup): ``--plan "QKU-934:SAYT-0004;QKU-1746:QKU-1801,QKU-1829"``
— hər cüt öz tranzaksiyasında, toqquşan cüt atlanır (:mod:`apps.registrar.subject_merge_plan`).

K2/K3 (sahib 2026-11-04): ləğv olunmuş BOŞ əkiz jurnal snapshot-la silinir, qiymətsiz təkrar qeydiyyat bağlanır
(«Həll olunur» sətirləri). ``--drop-attendance-only`` — «yalnız davamiyyət» qeydiyyatını da bağlamaq (açıq qərar).
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...subject_merge import MergeError, preview
from ...subject_merge_apply import apply
from ...subject_merge_plan import parse_plan, run_plan


def _organization(value):
    from django.apps import apps as django_apps

    Organization = django_apps.get_model("organizations", "Organization")
    found = Organization.objects.filter(slug=value).first()
    if found is None:
        raise CommandError(f"Təşkilat tapılmadı: {value}")
    return found


class Command(BaseCommand):
    help = "Dublikat fənləri birləşdirir (default dry-run; yazı üçün --apply --reason)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--target", default="", help="saxlanılacaq fənnin kodu")
        parser.add_argument("--source", default="", help="birləşdiriləcək fənn kod(lar)ı, vergüllə")
        parser.add_argument(
            "--plan",
            default="",
            help="PLAN rejimi: «QKU-K:MƏNBƏ1,MƏNBƏ2;QKU-K2:MƏNBƏ3» — hər cüt öz tranzaksiyasında (--target/--source əvəzinə)",
        )
        parser.add_argument("--apply", action="store_true", help="yaz (yoxdursa yalnız önizləmə)")
        parser.add_argument("--reason", default="", help="səbəb (≥20 simvol; --apply ilə məcburi)")
        parser.add_argument("--json", action="store_true", help="önizləməni JSON kimi çap et")
        parser.add_argument(
            "--drop-attendance-only",
            action="store_true",
            help="K3: «yalnız davamiyyət» (balsız xanalar) olan təkrar qeydiyyatı da bağla — qalan qeydiyyatın yekun "
            "qiyməti varsa (xanalar silinmir)",
        )

    def _plan(self, options):
        pairs = parse_plan(options["plan"])
        with rls_worker_atomic(), bypass_rls():
            organization = _organization(options["org"])
        run_plan(
            self,
            organization,
            pairs,
            do_apply=options["apply"],
            reason=options["reason"],
            drop_attendance_only=options["drop_attendance_only"],
        )
        if not options["apply"]:
            self.stdout.write('DRY-RUN: heç nə yazılmadı. Yazmaq üçün --apply --reason "…".')

    def _print(self, payload):
        self.stdout.write(f"Saxlanılan: {payload['target']['code']} — {payload['target']['name']}")
        for source in payload["sources"]:
            self.stdout.write(f"Birləşdirilən: {source['code']} — {source['name']} ({source['ects']} ECTS)")
        self.stdout.write("\nKöçəcək sətirlər:")
        for table in payload["tables"]:
            if table["count"]:
                mark = " [qalır]" if table["strategy"] == "keep" else ""
                self.stdout.write(f"  {table['title']}: {table['count']}{mark}")
        for title, items in (("Xəbərdarlıq", payload["warnings"]), ("Qeyd", payload["info"])):
            for text in items:
                self.stdout.write(f"{title}: {text}")
        for item in payload["resolvable"]:
            self.stdout.write(f"Həll olunur: {item['message']}")
        if payload["resolvable_total"] > len(payload["resolvable"]):
            self.stdout.write(f"Həll olunur: … və daha {payload['resolvable_total'] - len(payload['resolvable'])}")
        for item in payload["blocking"]:
            self.stdout.write(self.style.ERROR(f"TOQQUŞMA: {item['message']}"))
        self.stdout.write(f"\nİz: {payload['digest']}")

    def handle(self, *args, **options):
        if options["apply"] and len((options["reason"] or "").strip()) < 20:
            raise CommandError("--apply üçün --reason ən azı 20 simvol olmalıdır.")
        if options["plan"]:
            if options["target"] or options["source"] or options["json"]:
                raise CommandError("--plan --target/--source/--json ilə birlikdə işlədilmir.")
            self._plan(options)
            return
        if not options["target"] or not options["source"]:
            raise CommandError("--target və --source (və ya --plan) məcburidir.")
        with rls_worker_atomic(), bypass_rls():
            organization = _organization(options["org"])
            try:
                payload = preview(
                    organization,
                    options["target"],
                    options["source"],
                    by_code=True,
                    drop_attendance_only=options["drop_attendance_only"],
                )
            except MergeError as exc:
                raise CommandError(exc.message) from exc
            if options["json"]:
                self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            else:
                self._print(payload)
            if payload["blocking_total"]:
                raise CommandError(f"{payload['blocking_total']} toqquşma — birləşdirmə mümkün deyil.")
            if not options["apply"]:
                self.stdout.write('DRY-RUN: heç nə yazılmadı. Yazmaq üçün --apply --reason "…".')
                return
            try:
                result = apply(
                    organization=organization,
                    actor=None,
                    target_ref=options["target"],
                    source_refs=options["source"],
                    reason=options["reason"],
                    expected_digest=payload["digest"],
                    by_code=True,
                    drop_attendance_only=options["drop_attendance_only"],
                )
            except MergeError as exc:
                raise CommandError(exc.message) from exc
        self.stdout.write(self.style.SUCCESS(f"Birləşdirildi. Audit id: {result['audit_id']}"))
        self.stdout.write(f"Geri qaytarma (dry-run): manage.py undo_subject_merge --audit-id {result['audit_id']}")
