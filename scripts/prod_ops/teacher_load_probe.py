"""Müəllimin yük bölgüsü ↔ jurnal sahibliyi (YALNIZ OXU, sahib 2026-11-11).

«Yük bölgüsündə müəllimi dəyişəndə fənn jurnalda ona keçmir» şikayəti üçün: PROBE_STUDENTS-dəki hər müəllim (ad
tokenləri) üçün cari dövrün bölgü sətirləri (fəaliyyət, saat, qrup/alt qrup) və həmin sətrin qruplarının cari
açılışları — jurnal sahibi (instructor) və aktiv JournalShare-lər (müəllim + növlər). Heç nə yazmır, FİN çap etmir.
"""

import os
import re
import unicodedata

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_MAP = str.maketrans({"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u", "İ": "i", "Ə": "e"})


def _fold(text):
    text = (text or "").lower().translate(_MAP)
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _re_escape(ch):
    return "[iİı]" if _fold(ch) == "i" else re.escape(ch)


def _name(user):
    return f"{user.first_name} {user.last_name} ({user.username})" if user else "—"


@rls_worker_atomic()
@bypass_rls()
def main():
    User = get_user_model()
    Assignment = apps.get_model("workload", "TeacherAssignment")
    Offering = apps.get_model("registrar", "CourseOffering")
    Share = apps.get_model("registrar", "JournalShare")
    queries = [ln.strip() for ln in (os.environ.get("PROBE_STUDENTS") or "").splitlines() if ln.strip()]
    for query in queries:
        tokens = [_fold(t) for t in query.split() if len(t) >= 3]
        cond = Q()
        for token in tokens[:2]:
            cond &= Q(username__icontains=token[:5]) | Q(last_name__icontains=token[:4])
        hits = [
            u
            for u in User.objects.filter(cond)[:200]
            if all(t[:4] in _fold(f"{u.first_name} {u.last_name} {u.username}") for t in tokens)
        ]
        print(f"=== müəllim {query!r}: {len(hits)} hesab")
        for teacher in hits:
            print(f"--- {_name(teacher)} user={teacher.pk}")
            rows = (
                Assignment.objects.filter(teacher=teacher, row__period__is_current=True)
                .select_related("row__subject", "row__period", "group", "row__task__chair")
                .prefetch_related("row__groups")
            )
            for a in rows:
                row = a.row
                groups = [a.group] if a.group_id else list(row.groups.all())
                print(
                    f"  bölgü {a.pk} {a.activity} {a.hours}s alt={a.sub_number or ''} | {row.subject_label} "
                    f"({getattr(row.subject, 'code', '')}) | kafedra={getattr(row.task.chair, 'name', '')} | "
                    f"qruplar={', '.join(g.name for g in groups)} | dəyişib={a.updated_at:%Y-%m-%d %H:%M}"
                )
                offs = Offering.objects.filter(
                    subject_id=row.subject_id, period_id=row.period_id, group__in=groups, is_active=True
                ).select_related("instructor", "group")
                for o in offs:
                    shares = Share.objects.filter(offering=o, is_active=True).select_related("teacher")
                    share_txt = "; ".join(f"{_name(s.teacher)} {s.kinds}" for s in shares) or "—"
                    mine = o.instructor_id == teacher.pk or any(s.teacher_id == teacher.pk for s in shares)
                    print(
                        f"    jurnal {o.pk} qrup={o.group.name if o.group_id else ''} sahib={_name(o.instructor)} "
                        f"paylar=[{share_txt}] müəllimdə={'BƏLİ' if mine else 'YOX'}"
                    )
                if not offs:
                    print("    jurnal YOXDUR (bu fənn + dövr + qrup)")
            owned = Offering.objects.filter(instructor=teacher, period__is_current=True, is_active=True).count()
            shared = Share.objects.filter(teacher=teacher, is_active=True, offering__period__is_current=True).count()
            print(f"  cəmi: sahib olduğu jurnal={owned} pay={shared}")
    Subject = apps.get_model("registrar", "Subject")
    for code in [
        c.strip() for c in (os.environ.get("PROBE_SUBJECTS") or "").replace(",", "\n").splitlines() if c.strip()
    ]:
        for subj in Subject.objects.filter(code__iexact=code):
            n = Offering.objects.filter(subject=subj, period__is_current=True, is_active=True).count()
            print(f"=== fənn {subj.code} «{subj.name}» ects={getattr(subj, 'ects', '')} cari_jurnal={n}")
    for name in [ln.strip() for ln in (os.environ.get("PROBE_GROUPS") or "").splitlines() if ln.strip()]:
        pattern = r"^\s*" + r"\s*".join(map(_re_escape, name.replace(" ", ""))) + r"\s*$"
        offs = Offering.objects.filter(group__name__iregex=pattern, period__is_current=True, is_active=True)
        print(f"=== qrup {name!r}: cari jurnal {offs.count()}")
        for o in offs.select_related("subject", "group", "instructor"):
            print(f"    {o.pk} {o.group.name} | {o.subject.code} {o.subject.name} | sahib={_name(o.instructor)}")


main()
