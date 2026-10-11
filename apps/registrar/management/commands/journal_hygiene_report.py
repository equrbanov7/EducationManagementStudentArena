"""``journal_hygiene_report`` — «Jurnal təmizliyi»nin CLI əkizi (sahib 2026-10-10).

Kabinet bölməsi ilə EYNİ qaydalar (:mod:`apps.registrar.journal_hygiene` aşkarlayır,
:mod:`apps.registrar.journal_hygiene_actions` yazır): heç nə silinmir, hər sətir qərar jurnalına və audit-ə
düşür, hər paket (≤500) öz tranzaksiyasında önizləmə izi ilə yenidən yoxlanılır.

Qapılar: DEFOLT DRY-RUN; ``--apply`` ilə səbəb (≥20 simvol) MƏCBURİDİR; repetisiya markeri
(``emsarena.rehearsal_target='disposable'``) olmayan bazada ``--i-know-this-is-production`` tələb olunur
(``legacy_import/services/repair_support.py`` ilə eyni qayda). RLS: əmr tenant + aktor kontekstini özü qurur.

İstifadə::

    manage.py journal_hygiene_report --organization qku                          # hər iki kateqoriya, hesabat
    manage.py journal_hygiene_report --organization qku --category empty --code strong --show 60
    manage.py journal_hygiene_report --organization qku --category left --code expelled \\
        --apply --target suspend --reason "Xaric əmrləri əsasında jurnallardan çıxarılır (RİM)" \\
        --actor <rim.istifadəçi> --i-know-this-is-production
    manage.py journal_hygiene_report --organization qku --category not_held --code strong   # açılış üzrə hesabat
    manage.py journal_hygiene_report --organization qku --category not_held --code strong \\
        --apply --reason "Qrupda keçirilməyən fənn: heç kimin imtahan balı yoxdur (RİM)" --i-know-this-is-production

``not_held`` (sahib 2026-10-11) açılış səviyyəlidir: hesabat açılış başına bir sətir çap edir (fənn, qrup, dövr,
tələbə sayı, niyə), tətbiq isə paketləri AÇILIŞ sərhədində bölür (açılış heç vaxt yarımçıq çıxarılmır).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.rls import apply_rls_request_context
from core.rls_pooling import rls_worker_atomic

from ... import journal_hygiene as hygiene
from ... import journal_hygiene_actions as actions
from ... import journal_hygiene_rows as rows_service
from ...models import CourseOffering

CATEGORY_ARGS = {"left": hygiene.LEFT, "empty": hygiene.EMPTY, "not_held": hygiene.NOT_HELD}

REHEARSAL_GUC = "emsarena.rehearsal_target"
REHEARSAL_VALUE = "disposable"


def _disposable_database() -> bool:
    if connection.vendor != "postgresql":
        return True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting(%s, true)", [REHEARSAL_GUC])
            row = cursor.fetchone()
    except Exception:  # noqa: BLE001 — marker oxuna bilmirsə baza «real» sayılır (fail-closed)
        return False
    return bool(row) and str(row[0] or "").strip() == REHEARSAL_VALUE


class Command(BaseCommand):
    help = "Jurnal təmizliyi: ayrılmış tələbələr və boş fənlər — hesabat (defolt) və ya auditli tətbiq."

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--category", choices=(*CATEGORY_ARGS, "all"), default="all")
        parser.add_argument("--period", default="", help="Dövr id-si (UUID)")
        parser.add_argument("--faculty", default="", help="Fakültə id-si (UUID)")
        parser.add_argument("--group", default="", help="Qrup id-si (UUID)")
        parser.add_argument("--code", default="", help="Səbəb/etiket kodu və ya strong|review")
        parser.add_argument("--show", type=int, default=30, help="Çap olunan sətir sayı")
        parser.add_argument("--apply", action="store_true", help="Dəyişiklikləri YAZ (defolt: yalnız hesabat)")
        parser.add_argument("--target", choices=actions.TARGETS, default="", help="left: suspend|drop; empty: drop")
        parser.add_argument("--reason", default="", help="Qərarın səbəbi (≥20 simvol) — --apply ilə məcburi")
        parser.add_argument("--actor", default="", help="Aktorun istifadəçi adı (defolt: təşkilatın sahibi)")
        parser.add_argument("--limit", type=int, default=0, help="Ən çox bu qədər sətir tətbiq et (0 = hamısı)")
        parser.add_argument("--i-know-this-is-production", action="store_true", help="Markersiz bazada icazə")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization")
            .objects.filter(slug=str(options["organization"]).strip())
            .first()
        )
        if organization is None:
            raise CommandError(f"journal_hygiene_organization_unknown: {options['organization']!r}")
        actor = self._actor(organization, options["actor"])
        filters = {key: options[key] for key in ("period", "faculty", "group")}
        filters["category"] = options["code"]
        with rls_worker_atomic():
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            if options["apply"]:
                self._apply(organization, actor, filters, options)
                return
            for name, category in CATEGORY_ARGS.items():
                if options["category"] in ("all", name):
                    if category == hygiene.NOT_HELD:
                        self._report_not_held(organization, filters, options["show"])
                    else:
                        self._report(organization, category, filters, options["show"])
            self.stdout.write("\n(DRY-RUN — heç nə yazılmadı. Yazmaq üçün --apply verin.)")

    def _actor(self, organization, username):
        user_model = django_apps.get_model("auth", "User")
        username = str(username or "").strip()
        actor = user_model._default_manager.filter(username=username).first() if username else organization.owner
        if actor is None:
            raise CommandError(f"journal_hygiene_actor_unknown: {username!r}")
        return actor

    def _report(self, organization, category, filters, show):
        queryset = hygiene.candidates(organization, category, filters)
        chip = {**filters, "category": ""}
        totals = hygiene.counts(hygiene.candidates(organization, category, chip), category)
        title = "AYRILMIŞ TƏLƏBƏLƏR" if category == hygiene.LEFT else "BOŞ FƏNLƏR"
        self.stdout.write(f"\n=== {title} — {organization.slug} ===")
        for key, value in totals.items():
            self.stdout.write(f"  {hygiene.label(key) if key not in ('total', 'strong', 'empty') else key:40s} {value}")
        for row in rows_service.rows_for(queryset[: max(0, int(show or 0))], category):
            tags = ",".join(tag["code"] for tag in row["tags"])
            self.stdout.write(
                f"  {row['id']}  {row['student'][:32]:32s}  {row['subject'][:36]:36s}  {row['group'][:12]:12s}  "
                f"{row['period'][:24]:24s}  {row['status']:9s}  {row['reason']:18s}  "
                f"{'GÜCLÜ' if row['strong'] else 'yoxla'}  {tags}"
            )

    def _report_not_held(self, organization, filters, show):
        """Açılış başına bir sətir: fənn, qrup, dövr, tələbə, güc və «niyə» (qrupun digər fənlərində imtahan)."""
        scan = hygiene.not_held.scan(organization)
        queryset = hygiene.candidates(organization, hygiene.NOT_HELD, filters)
        totals = hygiene.counts(queryset, hygiene.NOT_HELD)
        self.stdout.write(f"\n=== KEÇİRİLMƏYƏN FƏNLƏR — {organization.slug} ===")
        for key, value in totals.items():
            self.stdout.write(f"  {hygiene.label(key) if key in hygiene.LABELS else key:40s} {value}")
        per_offering = {}
        for offering_id, strong, evidence in queryset.values_list("offering_id", "jh_strong", "jh_has_evidence"):
            item = per_offering.setdefault(offering_id, {"rows": 0, "strong": bool(strong), "entry": 0})
            item["rows"] += 1
            item["entry"] += int(bool(evidence))
        offerings = CourseOffering.objects.filter(pk__in=list(per_offering)).select_related(
            "subject", "group", "period"
        )
        by_period = {}
        lines = []
        for offering in offerings:
            item, info = per_offering[offering.pk], scan.offerings.get(offering.pk, {})
            period = rows_service.period_label(offering.period.name, offering.period.academic_year)
            bucket = by_period.setdefault(
                period, {"offerings": 0, "strong": 0, "rows": 0, "date": offering.period.start_date}
            )
            bucket["offerings"] += 1
            bucket["strong"] += int(item["strong"])
            bucket["rows"] += item["rows"]
            why = (
                f"qrupun {info.get('siblings_exam', 0)}/{info.get('siblings', 0)} digər fənnində imtahan var; "
                f"giriş balı {item['entry']}/{item['rows']}; {'dərs izi VAR' if info.get('taught') else 'dərs izi yox'}"
            )
            lines.append((not item["strong"], -offering.period.start_date.toordinal(), offering, period, item, why))
        self.stdout.write("  — dövr üzrə (açılış / güclü / sətir):")
        for period, bucket in sorted(by_period.items(), key=lambda pair: pair[1]["date"]):
            self.stdout.write(f"    {period:28s} {bucket['offerings']:5d} {bucket['strong']:5d} {bucket['rows']:6d}")
        lines.sort(
            key=lambda line: (line[0], line[1], line[2].group.name if line[2].group else "", line[2].subject.code)
        )
        for _weak, _date, offering, period, item, why in lines[: max(0, int(show or 0))]:
            subject = f"{offering.subject.code} {offering.subject.name}"
            self.stdout.write(
                f"  {offering.pk}  {subject[:48]:48s}  {(offering.group.name if offering.group else '—')[:14]:14s}  "
                f"{period[:22]:22s}  {item['rows']:3d} tələbə  {'GÜCLÜ' if item['strong'] else 'yoxla'}  {why}"
            )

    def _apply(self, organization, actor, filters, options):
        category = CATEGORY_ARGS.get(options["category"])
        if category is None:
            raise CommandError("journal_hygiene_category_required: --apply üçün --category left|empty|not_held verin")
        if not (_disposable_database() or options["i_know_this_is_production"]):
            raise CommandError(
                f"journal_hygiene_target_not_disposable: bazada {REHEARSAL_GUC}='{REHEARSAL_VALUE}' markeri yoxdur — "
                "real bazada --i-know-this-is-production verin."
            )
        target = options["target"] or (actions.TARGET_SUSPEND if category == hygiene.LEFT else actions.TARGET_DROP)
        try:
            reason = actions.clean_reason(options["reason"])
            to_status = actions.target_status(category, target)
        except actions.HygieneError as error:
            raise CommandError(f"journal_hygiene_{error.code}: {error.message}") from None
        queryset = hygiene.candidates(organization, category, filters)
        if category == hygiene.LEFT and to_status == "dropped":
            queryset = queryset.filter(jh_has_evidence=False)  # məlumatlı sətir yalnız dondurulur
        pairs = list(queryset.values_list("pk", "offering_id"))
        if options["limit"] and options["limit"] > 0:
            pairs = pairs[: options["limit"]]
        changed = 0
        for batch in _batches(pairs, whole_offerings=category == hygiene.NOT_HELD):
            try:
                preview = actions.preview(
                    organization=organization, actor=actor, category=category, enrollment_ids=batch, target=target
                )
                result = actions.apply(
                    organization=organization,
                    actor=actor,
                    category=category,
                    enrollment_ids=batch,
                    target=target,
                    reason=reason,
                    expected_digest=preview["digest"],
                )
            except actions.HygieneError as error:
                raise CommandError(f"journal_hygiene_{error.code}: {error.message} (yazılan: {changed})") from None
            changed += result["changed"]
            self.stdout.write(f"  paket {result['batch']}: {result['changed']} sətir → {to_status}")
        self.stdout.write(f"\nYAZILDI: {changed} sətir ({category} → {to_status}). Geri qaytarma: kabinet → Tarixçə.")


def _batches(pairs, *, whole_offerings: bool):
    """``(id, offering_id)`` → ≤500-lük paketlər; ``whole_offerings`` olduqda açılış paketlər arasında bölünmür."""
    if not whole_offerings:
        for start in range(0, len(pairs), rows_service.MAX_BATCH):
            yield [str(pk) for pk, _offering in pairs[start : start + rows_service.MAX_BATCH]]
        return
    groups = {}
    for pk, offering_id in pairs:
        groups.setdefault(offering_id, []).append(str(pk))
    batch = []
    for ids in groups.values():
        if batch and len(batch) + len(ids) > rows_service.MAX_BATCH:
            yield batch
            batch = []
        batch.extend(ids)
    if batch:
        yield batch
