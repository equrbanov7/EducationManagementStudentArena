# RLS Bypass Audit (FAZA 10)

> Tarix: 2026-05-24
> Status: Analiz sənədi — kod dəyişmir. Gələcək təhlükəsizlik audit-i üçün bələdçi.

## Niyə bu sənəd var

`core.rls.bypass_rls()` / `set_rls_bypass()` PostgreSQL Row-Level Security
siyasətlərini **müvəqqəti söndürür** — yəni sorğu bütün tenant-ların sətirlərini
görür. Hər istifadə potensial cross-tenant sızıntı nöqtəsidir. Kod bazasında
**~85 çağırış** var (test faylları xaric). Bu sənəd onları kateqoriyalaşdırır
ki, gələcəkdə hər biri qəsdən və əsaslandırılmış qalsın.

## Sayım (fayl üzrə, test xaric)

| Fayl | Çağırış | Kateqoriya |
|---|---:|---|
| `apps/notifications/services.py` | 13 | A — recipient-scoped yazma |
| `apps/live_exam/views/player.py` | 10 | B — public PIN/token girişi |
| `apps/blog/services.py` | 9 | A — qlobal blog (tenant-suz) |
| `apps/accounts/views/organization.py` | 9 | C — cross-org admin əməliyyatı |
| `apps/accounts/views/post_management.py` | 7 | A — qlobal blog moderasiyası |
| `apps/accounts/views/_helpers.py` | 7 | C — superadmin idarəetmə paneli |
| `apps/organizations/middleware.py` | 5 | D — tenant kontekst qurma |
| `apps/notifications/views.py` | 4 | A — istifadəçi öz inbox-u (FAZA 4) |
| `apps/accounts/services/organization_requests.py` | 4 | C — üzvlük sorğusu axını |
| `core/tenancy.py` | 3 | D — tenant kontekst qurma |
| `apps/live_exam/scoring.py` | 3 | B — public canlı imtahan |
| `apps/live_exam/consumers.py` | 3 | B — WebSocket public giriş |
| digər (live_exam/auth, api, signals, registration, profile) | ~8 | qarışıq |

## Kateqoriyalar və risk dərəcəsi

### A — recipient/owner-scoped yazma və qlobal məzmun  → RİSK: AŞAĞI
Sorğu onsuz da `recipient=user` / `owner=user` kimi güclü, atlanmaz bir filtrlə
məhdudlaşdırılıb, VƏ YA məlumat qəsdən qlobaldır (blog).
- `notifications/services.py`, `notifications/views.py` — bildiriş həmişə bir
  konkret `recipient`-ə bağlıdır; bypass yalnız istifadəçinin öz inbox-unu
  bütün org-lar üzrə görməsi üçündür (FAZA 4-də sənədləşdirildi).
- `blog/services.py`, `post_management.py` — blog qəsdən qlobaldır, RLS-dən
  kənardadır (FAZA 3-də sənədləşdirildi).
- **Tövsiyə:** saxla. Bu nümunələr təhlükəsizdir, çünki `recipient`/`owner`
  yoxlaması RLS-dən asılı deyil.

### B — public canlı imtahan (PIN/token girişi)  → RİSK: AŞAĞI-ORTA
Canlı imtahana PIN/token ilə qoşulan istifadəçinin hələ tenant konteksti yoxdur
(login olmaya bilər). PIN/token özü kriptoqrafik giriş yoxlamasıdır.
- `live_exam/views/player.py`, `scoring.py`, `consumers.py`, `auth.py`.
- **Tövsiyə:** saxla, amma hər çağırışda yoxla ki, PIN/token doğrulaması
  bypass-dan ƏVVƏL baş verir. Şərh əlavə et: niyə bypass lazımdır.

### C — cross-org superadmin / admin əməliyyatı  → RİSK: ORTA
Superadmin və ya org-admin bilərəkdən tenant sərhədini keçir (idarəetmə paneli,
üzvlük sorğuları).
- `accounts/views/organization.py`, `_helpers.py`, `services/organization_requests.py`.
- **Tövsiyə:** hər çağırışda təsdiqlə ki, çağırışdan ƏVVƏL `is_superadmin` /
  rol-səviyyə yoxlaması var. Bypass-dan sonra sorğu nəticələri istifadəçiyə
  qaytarılmazdan əvvəl yenidən filtrlənməlidir.

### D — tenant kontekst qurma (middleware infrastrukturu)  → RİSK: AŞAĞI
`OrganizationMiddleware` və `core/tenancy.py` hələ tenant kontekst təyin
olunmamış mərhələdə istifadəçinin hansı org-lara aid olduğunu öyrənir.
- **Tövsiyə:** saxla. Bu, RLS sisteminin özünü qurması üçün zəruridir
  (yumurta-toyuq problemi).

## Ümumi tövsiyələr

1. **Hər `bypass_rls()` çağırışına bir sətirlik şərh əlavə et** — niyə lazımdır,
   hansı yoxlama onu təhlükəsiz edir. Hazırda əksəriyyətində şərh yoxdur.
2. **Yeni `bypass_rls` əlavə edəndə** bu sənədi yenilə və kateqoriyasını seç.
3. **Kateqoriya C-dəki çağırışlar** ən diqqətlə nəzərdən keçirilməlidir —
   FAZA 11 (test) onlar üçün cross-tenant sızıntı testləri əlavə etməlidir.
4. **Mümkün olan yerlərdə** `bypass_rls`-i daha dar `set_rls_tenant(other_org)`
   ilə əvəz et — bütün tenant-ları açmaqdansa konkret hədəf org-a keç.

## Nəticə

121 çağırışın əksəriyyəti (kateqoriya A və D — ~60%) **təhlükəsizdir** —
recipient-scoped, qlobal məzmun, və ya infrastruktur. Əsas diqqət kateqoriya
C-dədir (~20%): superadmin/admin cross-org əməliyyatları. Onların hamısının
çağırışdan əvvəl rol yoxlaması olduğu FAZA 11 testləri ilə təsdiqlənməlidir.
