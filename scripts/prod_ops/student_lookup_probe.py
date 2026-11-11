"""Tələbə axtarışı (YALNIZ OXU) — ad tokenləri ilə bütün hesablar (arxivlənmiş daxil), qeydlər, jurnallar.

2026-11-11: bərpa olunan tələbə (534 T) axtarışda tapılmırdı — yeni hesab «aqsin quliyev» kimi yaradılıb. Köhnə hesabı
(köhnə jurnal məlumatı ilə) və yenisini yan-yana göstərir. FİN tam çap olunmur (yalnız son 2 simvol).
Parametr: PROBE_STUDENTS (hər sətir bir ad, tokenlər diakritiksiz müqayisə olunur), PROBE_GROUPS (qrup adı).
"""

import os
import unicodedata

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_MAP = str.maketrans({"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u", "İ": "i", "Ə": "e"})


def _fold(text):
    text = (text or "").lower().translate(_MAP)
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _lines(name):
    return [ln.strip() for ln in (os.environ.get(name) or "").splitlines() if ln.strip()]


@rls_worker_atomic()
@bypass_rls()
def main():
    User = get_user_model()
    SAR = apps.get_model("registrar", "StudentAcademicRecord")
    Enrollment = apps.get_model("registrar", "Enrollment")
    LessonMark = apps.get_model("registrar", "LessonMark")
    Membership = apps.get_model("organizations", "Membership")
    Movement = apps.get_model("registrar", "StudentMovement")
    Legacy = apps.get_model("legacy_import", "LegacyEntityMap")
    for query in _lines("PROBE_STUDENTS"):
        tokens = [_fold(t) for t in query.split() if len(t) >= 3]
        print(f"=== axtarış: {query!r} tokenlər={tokens}")
        cond = Q()
        for token in tokens[:2]:
            stem = token[:5]
            cond &= Q(first_name__iregex=stem[:3]) | Q(last_name__icontains=stem) | Q(username__icontains=stem)
        hits = []
        for user in User.objects.filter(cond).select_related("profile")[:400]:
            hay = _fold(
                " ".join([user.first_name, user.last_name, user.username, getattr(user.profile, "patronymic", "")])
            )
            if all(t[:4] in hay for t in tokens):
                hits.append(user)
        print(f"tapılan hesab: {len(hits)}")
        for user in hits:
            prof = getattr(user, "profile", None)
            fin = getattr(prof, "fin", "") or ""
            print(
                f"--- user={user.pk} username={user.username} ad={user.first_name!r} soyad={user.last_name!r} "
                f"ata={getattr(prof, 'patronymic', '')!r} fin=..{fin[-2:]} aktiv={user.is_active} "
                f"access={getattr(prof, 'access_state', '')} joined={user.date_joined:%Y-%m-%d} "
                f"last_login={user.last_login and user.last_login.strftime('%Y-%m-%d')}"
            )
            for m in Membership.objects.filter(user=user).select_related("role", "scope_unit"):
                print(f"    üzvlük role={m.role.name} aktiv={m.is_active} scope={getattr(m.scope_unit, 'name', '')}")
            for r in SAR.objects.filter(student=user).select_related("group"):
                print(
                    f"    SAR {r.pk} status={r.status} qrup={getattr(r.group, 'name', '')} qəbul={r.admission_year} "
                    f"aktiv={getattr(r, 'is_active', '')} yaradılıb={r.created_at:%Y-%m-%d}"
                )
            for mv in Movement.objects.filter(record__student=user).order_by("created_at")[:20]:
                print(f"    hərəkət {mv.order_date} kind={mv.kind} əmr={mv.order_number}")
            rows = (
                Enrollment.objects.filter(student=user)
                .select_related("offering__subject", "offering__group", "offering__period")
                .annotate(n=Count("lesson_marks"))
                .order_by("offering__period__start_date", "offering__subject__name")
            )
            for e in rows:
                o = e.offering
                print(
                    f"    jurnal {o.pk} {getattr(o.period, 'name', '')} | {o.subject.name} ({o.subject.code}) | "
                    f"qrup={getattr(o.group, 'name', '')} | status={e.status} | xana={e.n} | aktiv_jurnal={o.is_active}"
                )
            for lm in Legacy.objects.filter(target_pk=str(user.pk))[:10]:
                print(
                    f"    legacy {lm.entity_type} legacy_pk=..{str(lm.legacy_pk)[-4:]} target={lm.target_model_label}"
                )
            print(f"    xana cəmi: {LessonMark.objects.filter(enrollment__student=user).count()}")
    Offering = apps.get_model("registrar", "CourseOffering")
    for name in _lines("PROBE_GROUPS"):
        offs = Offering.objects.filter(group__name__iexact=name, period__is_current=True, is_active=True)
        print(f"=== qrup {name!r}: cari dövrün aktiv jurnalları {offs.count()}")
        for o in offs.select_related("subject").annotate(
            n=Count("enrollments", filter=Q(enrollments__status="enrolled"))
        ):
            print(f"    {o.pk} {o.subject.name} ({o.subject.code}) tələbə={o.n}")


main()
