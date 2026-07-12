# Performans Qeydləri (FAZA 12)

> Tarix: 2026-05-24
> Status: Bir hissəsi tətbiq olundu (dashboard caching), bir hissəsi gələcək
> iş üçün sənədləşdirilmiş tövsiyədir.

## Bu fazada tətbiq olundu

### Dashboard statistika caching

`apps/accounts/services/statistics_selectors.py` — 4 statistika funksiyası
(`get_student/teacher/org_admin/superadmin_statistics`) cəmi ~44
aggregate/annotate/count sorğusu işlədir. Profil səhifəsinin "statistika"
bölməsi hər açılışda bunları yenidən hesablayırdı.

Həll: `core/cache.py`-a `get_or_set_cached_statistics()` əlavə olundu —
`(rol, scope, filters)` kombinasiyasına görə 180 saniyəlik Redis kəşi. Həm
dashboard view, həm CSV export eyni kəşi paylaşır. Redis əlçatmaz olduqda
funksiya təmiz şəkildə birbaşa hesablamaya keçir (graceful degradation).

## Gələcək iş üçün tövsiyələr (bu fazada tətbiq olunmadı)

### 1. RLS subquery performansı

`organizations/migrations/0004_expand_rls_scope.py`-də join cədvəllərinin RLS
siyasətləri iç-içə `IN (SELECT ... JOIN ...)` subquery-lərindən ibarətdir
(məs. `exams_examanswer` üçün `attempt_id IN (SELECT ... JOIN exams_exam ...)`).
Hər sorğuda bu subquery icra olunur.

**Tövsiyə:** böyük imtahan data-sı ilə production-da `EXPLAIN ANALYZE` işlət.
Əgər subquery-lər bottleneck-dirsə, uşaq cədvəllərə (məs. `exams_examanswer`)
denormalizə edilmiş `organization_id` sütunu əlavə et və RLS siyasətini
birbaşa o sütuna bağla — FAZA 4-də `notifications_inappnotification` üçün
edildiyi kimi. Bu, JOIN-siz, sürətli olar.

**Niyə indi edilmədi:** hər uşaq cədvəl üçün yeni sütun + backfill migration +
RLS siyasətinin yenidən yazılması tələb olunur. Hər biri ayrıca, ölçülmüş
qərar tələb edir — kor-koranə denormalizə texniki borc yaradar.

### 2. RLS `set_config` round-trip-ləri

`core/rls.py` — hər HTTP sorğusunda `OrganizationMiddleware` 3+ `SELECT
set_config(...)` icra edir (`set_rls_user`, `set_rls_tenant`/`bypass`,
cleanup). Hər biri ayrıca DB round-trip-dir.

**Tövsiyə:** `_set_rls_setting` çağırışlarını tək cursor-da batch et — bir
`SELECT set_config(a), set_config(b), set_config(c)` ifadəsi. Sorğu başına
2-3 round-trip qənaət edər.

**Niyə indi edilmədi:** `core/rls.py` tenant izolyasiyasının mərkəzidir;
batch-ləmə diqqətli test tələb edir (xüsusən `local=True` transaction-scoped
hal). Kiçik optimizasiya, yüksək risk — ayrıca, fokuslanmış dəyişiklik olmalı.

### 3. WebSocket / canlı imtahan yük testi

`tests/load/locustfile.py` mövcuddur. Production buraxılışından əvvəl canlı
imtahanda yüzlərlə eyni vaxtlı tələbə ssenarisi `locust` ilə işlədilməlidir —
Redis channel layer və Daphne worker sayı bu yük altında ölçülməlidir.

### 4. Statistika kəşinin invalidasiyası

Hazırda statistika kəşi yalnız TTL (180s) ilə köhnəlir. Əgər real-time-a
yaxın dəqiqlik lazım olarsa, imtahan/tapşırıq qiymətləndirildikdə kəşi açıq
invalidasiya etmək olar. Hazırkı 180s TTL əksər dashboard istifadəsi üçün
kifayətdir — invalidasiya əlavə mürəkkəblikdir, yalnız tələb olunarsa.

## Yekun

Performans bünövrəsi sağlamdır: Redis kəş infrastrukturu (`core/cache.py`)
mövcuddur, FAZA 7-də kritik indekslər əlavə olundu, FAZA 12-də dashboard
statistikası kəşləndi. Qalan 3 tövsiyə (RLS subquery, set_config batch, yük
testi) production miqyası böyüdükcə, ölçmə əsasında həll edilməlidir —
qabaqcadan optimizasiya deyil.
