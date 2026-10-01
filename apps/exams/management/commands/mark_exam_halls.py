"""Otaqları imtahan zalı kimi qeyd edir / çıxarır (sahib 2026-10-01).

    manage.py mark_exam_halls --org qku --building "B" --rooms 03,28,38            # DRY-RUN (defolt)
    manage.py mark_exam_halls --org qku --building "B" --rooms 03,28,38 --apply    # yazır
    manage.py mark_exam_halls --org qku --building "B" --rooms 03 --unmark --apply # çıxarır

* DRY-RUN defoltdur — nə dəyişəcəyini çap edir, heç nə yazmır.
* İdempotentdir: artıq istənilən vəziyyətdə olan otaq «dəyişməz» sayılır.
* Korpus/otaq uyğunlaşdırması ``hall_matching`` modulundadır: «B» həm
  «Korpus B (Yüksək texnologiyalar)», həm də «B»; «03» həm «03», həm «3»,
  tək namizəd olduqda «03/2» ilə (≈ işarəsi) uyğunlaşır. Qeyri-müəyyən və ya
  tapılmayan token ATLANIR (namizədlər çap olunur) — təxmini yazı yoxdur.
* Çıxarma ``set_exam_hall`` qaydalarına tabedir: canlı oturum / aktiv kompüter
  → atlanır; planlaşdırılmış oturum komandada təsdiqlənmiş sayılır.
* Hər yazı audit jurnalına düşür (``source=command``).
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.exams.models import ExamRoom
from apps.exams.services.final_center.hall_matching import (
    TIER_BASE_NUMBER,
    building_matches,
    match_room_tokens,
    parse_room_tokens,
)
from apps.exams.services.final_center.halls import ExamHallChangeError, set_exam_hall
from apps.organizations.models import Organization
from core.rls import bypass_rls


def _room_line(room) -> str:
    state = "zal" if room.is_exam_hall else "otaq"
    return f"#{room.pk} «{room.name}» [{room.code}] korpus=«{room.building or '—'}» ({state})"


class Command(BaseCommand):
    help = "Korpus + otaq nömrələri ilə otaqları imtahan zalı kimi qeyd edir (defolt DRY-RUN; --apply yazır)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-u (məs. qku).")
        parser.add_argument("--building", required=True, help="Korpus: «B», «Korpus B» və ya tam ad.")
        parser.add_argument("--rooms", required=True, help="Vergüllə otaq adları/nömrələri: 03,28,38")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri YAZ (olmasa DRY-RUN).")
        parser.add_argument("--unmark", action="store_true", help="Qeyd etmək əvəzinə zallardan ÇIXAR.")

    def handle(self, *args, **options):
        tokens = parse_room_tokens(options["rooms"])
        if not tokens:
            raise CommandError("--rooms boşdur (nümunə: --rooms 03,28,38).")
        target = not options["unmark"]
        apply = options["apply"]
        with bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"Təşkilat tapılmadı: slug={options['org']!r}")
            org_rooms = list(ExamRoom.objects.filter(organization=organization).order_by("building", "name", "id"))
            rooms = [room for room in org_rooms if building_matches(room.building, options["building"])]
            if not rooms:
                raise CommandError(self._no_building_message(options["building"], org_rooms))
            self._report_buildings(rooms)
            summary = self._run(tokens, rooms, target=target, apply=apply)
        verb = "qeyd" if target else "çıxarış"
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(
            f"[{mode}] {verb}: dəyişən={summary['changed']} dəyişməz={summary['unchanged']} "
            f"rədd={summary['refused']} tapılmadı={summary['missing']} qeyri-müəyyən={summary['ambiguous']}"
        )
        if not apply:
            self.stdout.write("DRY-RUN — heç nə yazılmadı. Yazmaq üçün --apply əlavə edin.")

    def _report_buildings(self, rooms):
        labels = Counter((room.building or "—") for room in rooms)
        for label, count in sorted(labels.items()):
            self.stdout.write(f"Korpus «{label}»: {count} otaq")

    def _no_building_message(self, wanted, org_rooms):
        labels = Counter((room.building or "—") for room in org_rooms)
        listing = ", ".join(f"«{label}» ({count})" for label, count in sorted(labels.items()))
        return f"«{wanted}» korpusuna uyğun otaq yoxdur. Mövcud korpuslar: {listing or '—'}"

    def _run(self, tokens, rooms, *, target, apply):
        summary = Counter(changed=0, unchanged=0, refused=0, missing=0, ambiguous=0)
        handled = set()
        for match in match_room_tokens(rooms, tokens):
            if match.room is None:
                if match.ambiguous:
                    summary["ambiguous"] += 1
                    names = "; ".join(_room_line(room) for room in match.candidates)
                    self.stdout.write(f"  ? «{match.token}» qeyri-müəyyən — namizədlər: {names}")
                else:
                    summary["missing"] += 1
                    self.stdout.write(f"  ✗ «{match.token}» bu korpusda tapılmadı")
                continue
            room = match.room
            approx = " ≈" if match.tier == TIER_BASE_NUMBER else ""
            if room.pk in handled:
                self.stdout.write(f"  = «{match.token}»{approx} → #{room.pk} «{room.name}» — təkrar (yuxarıda)")
                continue
            if room.is_exam_hall == target:
                summary["unchanged"] += 1
                self.stdout.write(f"  = «{match.token}»{approx} → {_room_line(room)} — dəyişməz")
                handled.add(room.pk)
                continue
            handled.add(room.pk)
            if not apply:
                summary["changed"] += 1
                self.stdout.write(f"  → «{match.token}»{approx} → {_room_line(room)} → {'zal' if target else 'otaq'}")
                continue
            try:
                changed = set_exam_hall(room, target, by=None, confirmed=True, source="command")
            except ExamHallChangeError as exc:
                summary["refused"] += 1
                self.stdout.write(f"  ! «{match.token}» → {_room_line(room)} — rədd: {exc}")
                continue
            summary["changed" if changed else "unchanged"] += 1
            self.stdout.write(f"  ✓ «{match.token}»{approx} → {_room_line(room)}")
        return summary
