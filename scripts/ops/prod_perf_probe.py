"""Prod tətbiq daxili performans + DB zondu (OXU-YALNIZ; sahib 2026-09-21).

`prod_audit.sh` bunu app konteynerində `manage.py shell <` ilə işlədir.
* Verilənlər bazası: ölçü, bağlantı sayı, cache hit ratio, uzun sorğular,
  seq_scan ağır cədvəllər, `pg_stat_statements` varsa ən yavaş 8 sorğu.
* Tətbiq: real superadmin sessiyası ilə (force_login — parol yoxdur) 12 səhifəyə
  GET; sorğu sayı + müddət (DEBUG yalnız bu prosesdə açılır, cavablar atılır).
Heç bir yazı yoxdur; POST edilmir.
"""

import os
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client
from django.urls import reverse

HOST = os.environ.get("PROBE_HOST") or "127.0.0.1"


def q(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


print("== DB")
try:
    print("size:", q("SELECT pg_size_pretty(pg_database_size(current_database()))")[0][0])
    print(
        "connections:",
        q("SELECT count(*), sum((state='active')::int) FROM pg_stat_activity WHERE datname=current_database()")[0],
    )
    hit = q(
        "SELECT round(100*sum(blks_hit)/nullif(sum(blks_hit)+sum(blks_read),0),2) FROM pg_stat_database WHERE datname=current_database()"
    )[0][0]
    print("cache hit ratio %:", hit, "(<95 → shared_buffers/index problemi)")
    long_q = q(
        "SELECT pid, now()-query_start AS age, left(query,90) FROM pg_stat_activity "
        "WHERE state='active' AND now()-query_start > interval '5 seconds' AND datname=current_database() ORDER BY age DESC LIMIT 5"
    )
    print("long-running (>5s):", long_q or "yoxdur")
    seq = q(
        "SELECT relname, seq_scan, idx_scan, n_live_tup FROM pg_stat_user_tables "
        "WHERE n_live_tup > 20000 AND seq_scan > idx_scan ORDER BY seq_scan DESC LIMIT 8"
    )
    print("seq_scan > idx_scan (böyük cədvəllər):")
    for row in seq:
        print("   ", row)
    if not seq:
        print("    yoxdur")
    dead = q(
        "SELECT relname, n_dead_tup, n_live_tup, last_autovacuum FROM pg_stat_user_tables "
        "WHERE n_dead_tup > 50000 ORDER BY n_dead_tup DESC LIMIT 5"
    )
    print("dead tuples > 50k:", dead or "yoxdur")
    try:
        top = q(
            "SELECT round(mean_exec_time::numeric,1), calls, left(query,110) FROM pg_stat_statements "
            "ORDER BY mean_exec_time DESC LIMIT 8"
        )
        print("pg_stat_statements — ən yavaş (orta ms, çağırış, sorğu):")
        for row in top:
            print("   ", row)
    except Exception as exc:  # noqa: BLE001
        print("pg_stat_statements yoxdur:", str(exc).splitlines()[0][:80])
except Exception as exc:  # noqa: BLE001
    print("DB zondu xətası:", exc)

print()
print("== Tətbiq (superadmin sessiyası, GET, sorğu sayı / ms)")
User = get_user_model()


def _probe_user():
    """Zond hesabı: superadmin çox vaxt 2FA/parol qapısına 302 alır — əvvəl RİM rəhbəri,
    sonra sahib, sonra superadmin (hamısı yalnız OXU GET üçün, parolsuz force_login)."""
    from apps.organizations.models import Membership

    for role_name in ("ikt_rehber", "rector", "teaching_office_head"):
        member = (
            Membership.objects.filter(is_active=True, role__name=role_name, user__is_active=True)
            .select_related("user")
            .order_by("user_id")
            .first()
        )
        if member is not None:
            return member.user, role_name
    owner = User.objects.filter(owned_organizations__isnull=False, is_active=True).order_by("id").first()
    if owner is not None:
        return owner, "org_owner"
    admin = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
    return admin, "superuser"


user, user_kind = _probe_user()
if user is None:
    print("zond üçün uyğun aktiv hesab yoxdur — tətbiq zondu ötürüldü")
else:
    print(f"zond hesabı: {user_kind} (#{user.pk})")
    settings.DEBUG = True
    settings.ALLOWED_HOSTS = ["*"]
    # SECURE_SSL_REDIRECT açıqdır — sorğular HTTPS kimi getməlidir (əks halda hər şey 301).
    client = Client(secure=True)
    client.force_login(user)
    # İnzibati/superadmin hesab admin 2FA qapısına (/manage/verify-otp/) 302 alır — zond
    # yalnız OXU GET üçündür, sessiyada təsdiq bayrağını qoyuruq (parol/OTP yoxdur).
    try:
        from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY

        session = client.session
        session[ADMIN_2FA_VERIFIED_USER_SESSION_KEY] = str(user.pk)
        session.save()
    except Exception as exc:  # noqa: BLE001
        print("2FA bayrağı qoyulmadı:", exc)
    pages = [
        reverse("accounts:profile"),
        reverse("accounts:profile") + "?section=my-exams",
        reverse("accounts:profile") + "?section=groups-registry",
        reverse("accounts:profile") + "?section=people-teachers",
        reverse("accounts:profile") + "?section=student-registry",
        reverse("accounts:profile") + "?section=workload-overview",
        reverse("accounts:profile") + "?section=my-subjects",
        reverse("registrar:journal_list"),
    ]
    try:
        from apps.registrar.models import CourseOffering

        off = CourseOffering.objects.filter(is_active=True, period__is_current=True).order_by("-created_at").first()
        if off:
            pages.append(reverse("registrar:journal_detail", args=[off.pk]))
    except Exception as exc:  # noqa: BLE001
        print("journal_detail seçilmədi:", exc)
    try:
        from apps.exams.models import Exam

        exam = Exam.objects.filter(is_deleted=False, author=user).order_by("-created_at").first()
        if exam:
            pages.append(reverse("exams:teacher_exam_detail", args=[exam.slug]))
            pages.append(reverse("exams:teacher_exam_results", args=[exam.slug]))
    except Exception as exc:  # noqa: BLE001
        print("exam seçilmədi:", exc)
    print(f"{'status':>6} {'q':>4} {'ms':>6}  url")
    slow = []
    for url in pages:
        reset_queries()
        t0 = time.time()
        try:
            resp = client.get(url, HTTP_HOST=HOST, follow=False, secure=True)
            status = resp.status_code
            location = resp.headers.get("Location", "") if status in (301, 302) else ""
        except Exception as exc:  # noqa: BLE001
            status, location = f"ERR {type(exc).__name__}", ""
        ms = int((time.time() - t0) * 1000)
        n = len(connection.queries)
        print(f"{str(status):>6} {n:>4} {ms:>6}  {url}" + (f"  → {location[:80]}" if location else ""))
        if n > 80 or ms > 1500:
            slow.append((url, n, ms))
    print()
    print("⚠️ yavaş/sorğu-ağır (q>80 və ya >1500ms):", slow or "yoxdur")

    # ── Funksional zond (sahib 2026-09-21, OXU-YALNIZ): sillabus həftə cədvəli
    # plandan özü tənzimlənir; cədvəl modalının fənn siyahısı müəllimə görə gəlir.
    print()
    print("== Funksional: sillabus həftə cədvəli (plan → sətir/növ/seçim)")
    # ORM sorğuları RLS altındadır — `manage.py shell`-də təşkilat konteksti
    # olmadığından sətir qayıtmır (2026-09-21 ilk zond «yoxdur» dedi). Oxu-yalnız
    # zond üçün RLS keçilir (`core.rls.bypass_rls`), heç nə yazılmır.
    from core.rls import bypass_rls

    try:
        from apps.accounts.views.syllabus import editor_panels
        from apps.syllabus.models import SyllabusVersion
        from apps.syllabus.public import SectionKey, expected_week_rows, section_data_map

        with bypass_rls():
            versions = list(
                SyllabusVersion.objects.exclude(plan_hours={})
                .exclude(plan_hours__isnull=True)
                .select_related("syllabus__subject")
                .order_by("-updated_at")[:4]
            )
            for version in versions:
                data = section_data_map(version).get(SectionKey.WEEK.value, {})
                rows = editor_panels.week_rows(data, (), version.plan_hours)
                totals = editor_panels.hour_totals(rows, version.plan_hours)
                choices = rows[0]["cells"][0]["choices"] if rows and rows[0]["cells"] else "-"
                print(
                    f"   {version.syllabus.subject.code:<10} {version.status:<9} plan={version.plan_hours} → "
                    f"sətir={len(rows)} (gözlənilən {expected_week_rows(version.plan_hours) or 16}) "
                    f"növlər={totals['kinds']} seçim={choices}"
                )
        if not versions:
            print("   plan saatı olan sillabus versiyası yoxdur")
    except Exception as exc:  # noqa: BLE001
        print("   sillabus zondu xətası:", exc)

    print("== Funksional: cədvəl modalı — fənn siyahısı müəllimə görə")
    try:
        from apps.registrar import schedule_editor
        from apps.registrar.models import CourseOffering

        with bypass_rls():
            off = (
                CourseOffering.objects.filter(is_active=True, period__is_current=True, instructor__isnull=False)
                .select_related("instructor", "organization", "period", "group")
                .order_by("-created_at")
                .first()
            )
            if off is not None:
                base = schedule_editor.allowed_subjects(
                    organization=off.organization, group=off.group, period=off.period
                )
                mine = schedule_editor.allowed_subjects(
                    organization=off.organization, group=off.group, period=off.period, instructor=off.instructor
                )
        if off is None:
            print("   müəllimli aktiv açılış yoxdur")
        else:
            own_present = any(row["id"] == str(off.subject_id) for row in mine)
            print(
                f"   qrup={off.group} müəllim=#{off.instructor_id} → qrup siyahısı {len(base)} fənn, "
                f"müəllimə görə {len(mine)} fənn {[row['code'] for row in mine][:6]} "
                f"öz fənni siyahıda: {'bəli' if own_present else 'XEYR ⚠️'}"
            )
        resp = client.get(reverse("accounts:profile") + "?section=schedule-manage", HTTP_HOST=HOST, secure=True)
        body = resp.content.decode("utf-8", "ignore")
        print(
            f"   schedule-manage GET {resp.status_code}; schedule_editor_subjects.js yüklənir: "
            f"{'bəli' if 'schedule_editor_subjects.js' in body else 'XEYR ⚠️'}"
        )
    except Exception as exc:  # noqa: BLE001
        print("   cədvəl zondu xətası:", exc)
