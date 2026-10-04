# 2026-10-05 — giriş və imtahan darboğazlarının düzəlişi

## Əhatə və tətbiq vəziyyəti

Bu dəyişiklik 2026-10-04 tarixli ayrıca yük mühitində sübut olunmuş kod
problemlərini düzəldir. Canlı sistemə bu dəyişikliklər hələ yayımlanmayıb.
Serverdə düzəldilmiş randomizer və indeks ayrıca test bazasında yoxlanır;
RLS bərpası lokal, real PostgreSQL bağlantıları ilə yoxlanıb.

Canlı işləyən image-in build SHA-sı
`16bbf3c96a3669b3ea80462e53ca40929843f95f`, lokal checkout isə Develop
branch-indədir. Server checkout-unda çoxlu əvvəlcədən mövcud dəyişiklik və
untracked fayl var. Bütün server checkout-unu rebuild etmək bu düzəlişdən
kənar dəyişiklikləri də yayımlaya bilər. Burada həmin checkout dəyişdirilməyib.

## Hazır düzəlişlər

| Problem | Dəyişiklik | Davranışın qorunması |
|---|---|---|
| Username ilə girişdə də e-poçt üçün 50 005 sətrin skanı | `accounts.0029` tam kanonik e-poçt indeksi və dərhal `ANALYZE auth_user` | NFKC/trim/lower, mövcud unique indeks və username/e-poçt toqquşma qoruması qalır |
| Ayrı tələbələrin imtahan başlanğıcının ortaq exam kilidinə düşməsi | Randomizer yalnız öz `ExamAttempt` sətrini `FOR UPDATE OF self` ilə kilidləyir | Eyni cəhd üçün paralel start bir snapshot yaradır; refresh sualları dəyişmir |
| Qırılmış DB bağlantısında RLS cleanup-ın ikinci xəta yaratması | Uğursuz cleanup bağlantını istifadədən çıxarır; açıq tələb olunan reset xəta qaytarmağa davam edir | Tenant/bypass vəziyyəti təmizlənməmiş bağlantı təkrar istifadə edilmir |
| Uğursuz login GET-dən sonra tokensiz POST və saxta CSRF nəticələri | Generator status + CSRF yoxlayır, uğursuz girişdən sonra istifadəçini dayandırır | Autentifikasiyalı yük yalnız sessiya ilə qəbul edilmiş girişdən sonra başlayır |
| Worker hesablarının bir-birinin zolağına keçməsi | Ayrı offset/count aralıqları, modulo wrap silinib | Hovuz tükənəndə generator bunu ayrıca xəta kimi göstərir |
| Cavab göndərmədə köhnə CSRF tokeni | Login-dən sonra dönmüş `csrftoken` cookie-si istifadə olunur | CSRF qoruması saxlanılır |

Sənəd yazıldıqdan sonra əlavə edilən və 2026-10-05-də tamamlanan iki hissə:

| Problem | Dəyişiklik | Davranışın qorunması |
|---|---|---|
| Login sıçrayışının imtahan sorğularının ortaq slotlarını tutması | `MAX_INFLIGHT_LOGIN_REQUESTS` (defolt 4/replika) — yalnız login **POST**-u (parol hash-i) ayrıca növbədən keçir, sonra ortaq tavana da tabedir | Login forması (GET) ortaq hovuzda qalır — sıçrayışda səhifənin özü 503 almır; `0` köhnə davranışı qaytarır |
| 503/429-dan sonra autosave-in serveri dərhal təkrar vurması | `take_exam/retry.js`: Retry-After (saniyə və ya HTTP tarixi), yoxdursa eksponensial backoff + jitter, ən çox 60 s | Uğurlu cavab backoff-u sıfırlayır; `finish` bloklanmır; cavab localStorage-da qalır |

İndeks migrasiyası `atomic=False` və `CREATE INDEX CONCURRENTLY` istifadə edir.
Yarımçıq concurrent build-dən qalan invalid indeks aşkar edilərək yenidən
qurulur. SQLite-də no-op, geri qaytarılarkən yalnız yeni lookup indeksi silinir.

Yeni indeks təkbaşına kifayət etmədi: statistika yoxkən `ORDER BY id LIMIT 2`
köhnə primary-key skanını seçdi. Test serverində `ANALYZE`-dan əvvəl həmin
sorğu 196,021 ms, sonra yeni indekslə 0,112 ms çəkdi. Bu, konkret SQL
sorğusunun ölçməsidir; bütün login axını üçün eyni sürətlənmə iddiası deyil.

## Lokal yoxlamalar

- SQLite: servis, snapshot, dil variantları, identity access, RLS cleanup və
  generator testləri — **152 passed, 1 skipped**.
- PostgreSQL: identity qoruması, indeks, randomizer paralelliyi, snapshot və
  RLS memo testləri — ilkin paket **31 passed**.
- Son indeks/statistika düzəlişi: **3 PostgreSQL testi passed**. 5 000 boş
  e-poçtlu hesabda real login sorğusunun planner override olmadan yeni indeksi
  seçməsi də yoxlanır.
- Bağlantını driver səviyyəsində bağlayıb yenidən açma daxil olmaqla RLS
  paketi — **11 passed**. Yeni sessiyada köhnə tenant və bypass qalmır.
- `manage.py check`, `makemigrations --check --dry-run`, modul ölçüsü,
  modul sərhədləri, public API, Black, isort, flake8 və `git diff --check` keçdi.

Test sayları ayrı paketlərdir və bəzi testlər təkrarlanır; cəmlənmiş unikal
test sayı kimi təqdim edilməməlidir.

## Server sınağının sərhədləri

Test mühiti canlı məlumatdan ayrıdır: 50 000 sintetik tələbə, test Redis,
test PostgreSQL/PgBouncer, dörd test app və test HTTPS edge. Tətbiqə ümumi
3 CPU, bazaya 1 CPU ayrılıb. Canlı host 10 vCPU və təxminən 30 GiB RAM-dır.
Bu mühitin tavanı canlı hostun maksimum istifadəçi tutumu deyil.

İlk overlay sınağında fayl icazəsi tətbiqin startını pozdu; həmin nəticələr
tutum hesabına daxil edilmir. İcazə düzələndən sonra, statistika yenilənməmiş
20 nəfərlik axında 1 125 sorğu, 0 xəta və p95 1 200 ms görüldü. 50 nəfərlik
axın 37 giriş, 255 sorğu, 3 xəta və p95 8 500 ms ilə keçmədi. Bu ölçmə
statistika düzəlişindən əvvəl olduğu üçün yekun düzəliş nəticəsi deyil.

Statistika yeniləndikdən sonrakı təkrar (`fix-v3.log`):

| Axın | Hədəf | Daxil olmuş hesab | Sorğu | Xəta | p95, ms | Qiymətləndirmə |
|---|---:|---:|---:|---:|---:|---|
| Tam imtahan | 1 | 1 | 44 | 0 | 1 200 | Keçdi |
| Tam imtahan | 20 | 20 | 1 020 | 0 | 1 300 | Keçdi |
| Tam imtahan | 50 | 50 | 695 | 0 | 2 800 | Xətasız, amma 2 500 ms həddini aşır |
| Kütləvi giriş + kabinet | 500 | 11 | 381 | 265 | 10 000 | Keçmədi; erkən dayandırıldı |

Son təkrarın fayl adlarındakı `fix-v2` etiketi əvvəlki skriptdən qalıb;
etibarlı run ayrımı `fix-v3.log`-dur. CSV faylları son təkrarla yenilənib.
1 727 bitmiş cəhdin **17 270 cavabı** DB ilə uyğunlaşdırıldı, **0 uyğunsuzluq**
tapıldı. Bu say həmin test bazasında əvvəlki və yeni sınaqların ümumi cəmidir.
Test konteynerləri dayandırıldı; canlı TLS health yoxlaması sağlamdır.

500 mərhələsində login GET/POST 503-ləri və 8/10 saniyəlik cavab gözləmə
timeout-ları qaldı. Tam düzəliş böyük login sıçrayışını bu məhdud test
resursları daxilində həll etmədi. Bu səbəbdən «bütün performans problemi
həll edildi» və ya «50 000 istifadəçi dəstəklənir» nəticəsi çıxarılmır.
50 nəfərlik mərhələdə DB ayrılmış bir CPU limitinə çatırdı; hansı əlavə
sorğunun nə qədər xərc yaratdığını müəyyən etmək üçün ayrıca query/wait
profilinə ehtiyac var. CPU nümunəsi təkbaşına bütün gecikmənin səbəbini sübut
etmir.

## Qalan tutum işi və buraxılış ardıcıllığı

1. Yalnız bu düzəlişləri daşıyan, dəyişiklikləri məlum release hazırlanmalı;
   əvvəlki image və DB backup saxlanmalıdır. Mövcud deploy runbook-un
   migration/health/rollback yoxlamaları tətbiq olunmalıdır.
2. Yeni indeks DB owner/migration roluyla yaradılmalı; app roluna yeni DDL
   və ya RLS bypass icazəsi verilməməlidir. SQL planı canlıya yayım zamanı da
   yeni indeksi seçməlidir.
3. Giriş sıçrayışı və əvvəlcədən daxil olmuş tələbələrin imtahan yükü ayrı
   ölçülməlidir. Parol yoxlamasının CPU xərci imtahanın öz tutumu deyil.
4. 500 → 1 000 → 2 000 → 5 000 → 10 000 → 20 000 → 50 000 pillələrində
   generator yükü ayrıca ölçülməli; p95/p99, HTTP xətası, faktiki daxil olmuş
   tələbə sayı, CPU throttling, DB wait, PgBouncer queue və cavab bütövlüyü
   birlikdə qiymətləndirilməlidir. Qəbul olunmayan pillə maksimum tutum
   kimi təsdiqlənməməlidir.
5. 24 slot/replika qorumasının kor-koranə artırılması həll sayılmır.
   Ölçmədən sonra replika/DB/pool tutumu birlikdə uyğunlaşdırılmalıdır.
   Parol hash-i, CSRF və tenant izolyasiyası zəiflədilməməlidir.
6. İki IP eyni hosta çıxırsa, onları iki ayrı serverin CPU/RAM tutumu kimi
   saymaq olmaz. Həqiqi ikinci host ayrıca təsdiqlənməlidir.

Məxfi giriş məlumatları, DB URL-ləri və parollar bu sənədə daxil edilməyib.
