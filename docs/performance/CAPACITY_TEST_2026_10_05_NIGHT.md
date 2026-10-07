# 2026-10-05 gecə — tutum testi, tapılan darboğazlar və düzəlişlər

## Necə ölçüldü

- **Mühit:** Codex-in izolə stack-i (`emsarena-capacity-20261004`, `internal: true` şəbəkə)
  CANLI image ilə qaldırıldı. Ayrıca Postgres (2 CPU), PgBouncer (1 CPU), Redis, nginx edge
  və 4 (sonda 5) app replikası, hər biri 1 CPU. Baza: 50 000 sintetik tələbə + 1000 müəllim/jurnal.
  Canlı sistemə yük verilmədi; canlı `/health/` hər 10 s yoxlanıldı, heç bir uğursuzluq olmadı.
- **Harness:** `ops/loadtest-2026-10-05` branch-i (`scripts/loadtest/`, `load-test.yml`):
  - `cap_seed.py` — imtahan 30 sual / 3 blok, hər tələbəyə təsadüfi 10;
    müəllim başına bugünkü dərsi olan jurnal.
  - `cap_locust.py` — ssenarilər:
    - login;
    - imtahan: başla → hər sualdan sonra autosave (`autosave_revision` ilə) → finish → nəticə;
    - jurnal: siyahı → jurnal → 25 xana davamiyyət+bal → yenidən açılış → 3 xana düzəliş;
    - kabinet;
    - qarışıq.
  - `cap_reconcile.py` — uğurlu deyilən hər yazını bazada yoxlayır.
  - `cap_run.py` — orkestrator: telemetriya, SQL profili, app xətaları, canlı sağlamlıq qoruyucusu.
- **Overlay:** branch-dəki Python kodu canlı image üzərində mount edildi. Optimallaşdırmalar
  canlıya çıxmazdan əvvəl ölçüldü.
- **Keçid meyarı:** xəta < 1%, hər sorğu növü üçün p95 < 2,5 s.

Test mühitində app-a cəmi 4–5 nüvə düşür. Canlı host 10 vCPU-dur, amma app replikası
tək daphne prosesidir (aşağıda, №6). Bu səbəbdən rəqəmlər canlı tutumun aşağı həddi kimi oxunmalıdır.

## Əsas problem nə idi (qısa)

Server zəif deyildi. İki əsas səbəb var idi.

1. **Kabinetdəki bir sorğu bazanı boğurdu.** Hər tələbə kabinetə girəndə «mənə təyin
   olunmuş imtahanlar» sayılırdı.
   - Sorğu qrupdakı bütün tələbələri (minlərlə sətir) birləşdirib, sonra təkrarları silirdi.
   - Tək istifadəçidə bu hiss olunmurdu. 500 tələbə eyni anda girəndə isə hər sorğu
     3,6–13 saniyə çəkdi və baza tam doldu. Login-dən sonra kabinet açılmadığı üçün
     «login işləmir» görünürdü.
   - Eyni naxışda daha üç kiçik problem tapıldı, hamısı düzəldildi:
     - üzv sayı hər açılışda yenidən sayılırdı;
     - imtahan başlanğıcında sual seçimi sayğacı bütün tələbələr üçün eyni anda yenidən hesablanırdı;
     - jurnal hər açılışda bütün müəllimləri yükləyirdi.
2. **Serverin yarısı boş dururdu.** Hər app replikası tək Python prosesidir və 1 nüvədən
   çox işlədə bilmir. `.env`-də 4 replika olduğu üçün 10 nüvəli serverdən app-a cəmi ~4 nüvə
   düşürdü. 2026-10-05 səhər replika sayı 8-ə qaldırıldı.

Üçüncü, təbii hədd **parol yoxlamasıdır**. PBKDF2 hər girişdə CPU yeyir və bu qəsdəndir
(təhlükəsizlik). Ona görə minlərlə tələbənin eyni dəqiqədə daxil olması məhduddur.
Login növbəsi artıq 503 vermir, 15 saniyəyə qədər gözlədir. İmtahan günü girişi bir neçə
dəqiqəyə yaymaq lazımdır.

## Nəticələr

| Ssenari | Baza (canlı image) | Düzəlişlərdən sonra (eyni 4 CPU) |
|---|---|---|
| Kabinet 500 | ❌ 96,6% xəta, p95 15 s | ✅ **0 xəta**, p95 1,1 s |
| Login 500 / 60 s | ❌ 34,9% (DB 205%) | 5–14% (app CPU, PBKDF2) |
| Login 500 / 120 s | — | ✅ **0 xəta**, p95 0,5 s |
| Login 300 / 60 s | — | ✅ 0 xəta |
| İmtahan 500 (düşünmə 8–20 s) | ✅ 0 xəta, p95 0,44 s | — |
| İmtahan 1000 (düşünmə 20–40 s) | ❌ 11,3% | 1,4% (qalanı test edge-in nginx 500-ü + başlanğıc timeout-u) |
| Jurnal 300 | — | ✅ 0 xəta, p95 0,37 s |
| Jurnal 500 | ❌ 2% xəta, p95 11 s | ✅ 0 xəta, p95 0,26 s (5 replika) |
| Qarışıq 1500 (5 replika) | — | 5% (CPU doyur) |

**Bütövlük:**
- İmtahan: 2281 bitmiş cəhd, 22 810 cavab — **0 uyğunsuzluq**.
- Jurnal: 4600 xana — **0 uyğunsuzluq**.

Yük altında heç bir cavab və ya qiymət itmədi. Uğursuz sorğular 503 ilə rədd edildi, səssiz itki olmadı.

## Tapılan səbəblər və düzəlişlər

1. **Kabinet «təyin olunmuş imtahanlar» sorğusu** (`apps/accounts/queries/assignments.py`,
   tələbə imtahan siyahıları, `student_list_batch`).
   - **Səbəb:** `allowed_users | allowed_groups__students | allowed_units | kurs üzvlüyü` OR ilə
     LEFT JOIN + DISTINCT edilirdi. Postgres `user_id = X`-i hər JOIN-ə ayrıca tətbiq edə bilmirdi
     və 2500 tələbəli qrupların hamısını birləşdirirdi.
   - **Təsir:** yük altında sorğu orta 3,6 s, maksimum 13 s çəkirdi. Login-dən sonra açılan kabinet
     DB-ni 2 nüvədə doyururdu. Login sıçrayışını yıxan da bu idi, parol hash-i deyil.
   - **Düzəliş:** hər yol ayrıca `pk IN (subquery)` (semi-join), DISTINCT yoxdur
     (`student_assigned_exams_q`).
2. **Təşkilat üzv sayı** (`_build_user_organization_access_rows`).
   - **Səbəb:** hər kabinet açılışında 50 000 üzvlü təşkilat üçün `COUNT` işləyirdi
     (orta 80 ms, maksimum 2 s, 500 tələbədə 1870 dəfə).
   - **Düzəliş:** təşkilat üzrə 5 dəqiqə keş.
3. **Randomizer istifadə sayğacı.**
   - **Səbəb:** 30 saniyəlik keş bitəndə bütün paralel başlanğıclar `COUNT(DISTINCT user)`
     aqreqatını eyni anda yenidən hesablayırdı. Hər biri 2,8–2,9 s çəkirdi (cache stampede).
   - **Düzəliş:** single-flight + köhnə dəyərin istifadəsi.
4. **İmtahan başlanğıcı tutum qapısı.**
   - **Səbəb:** sıfıra enən açar silinirdi. Paralel `add`→`incr` arasında «Key not found» çıxırdı
     və qapı səssizcə söndürülürdü («bypassing the gate»).
   - **Düzəliş:** açar silinmir, `incr` yarışı atomik `add` ilə həll olunur.
5. **Jurnal səhifəsi.**
   - **Səbəb:** hər açılışda təşkilatın bütün dərs deyən müəllimləri yüklənirdi
     (814 açılış → 407 814 `auth_user` sətri). Şablon isə yalnız siyahının boş olub-olmadığına baxır.
   - **Düzəliş:** `EXISTS`; siyahı onsuz da lazy axtarış endpoint-indən gəlir.

Hər düzəliş üçün reqressiya testi var. Tam paket: 11 381 passed.

## Qalan darboğazlar və tövsiyələr (sahib qərarı)

6. **App replikası = tək daphne prosesi.**
   - **Problem:** GIL səbəbindən replika ~1 nüvədən çox işlədə bilmir. Daphne HTTP-ni Python-da
     parse edir, hər sorğuya ayrıca thread açılır. Testdə sorğu başına ~120 ms CPU ölçüldü;
     eyni sorğu lokal `runserver`-də 18–36 ms çəkir.
   - **Canlıda:** `.env`-də `APP_REPLICAS=4` idi, yəni app 10 nüvədən faktiki ~4-ünü istifadə edirdi.
   - **✅ Tətbiq olundu (2026-10-05 səhər):** `APP_REPLICAS=8`, 8 replika sağlam. Kod defoltu onsuz da 8-dir, və 8 × 24 slot = 192 ≤ PgBouncer
     150 + 50 ehtiyat. Daha sonra HTTP üçün uvicorn/gunicorn çox-prosesli işçiyə keçidi ölçmək lazımdır.
7. **Login sıçrayışı.**
   - **Problem:** PBKDF2 (600k iterasiya) CPU-ya bağlıdır. 4 app nüvəsi 60 saniyədə ~300–400
     girişi xətasız qəbul edir; 500 giriş 2 dəqiqəyə yayılanda xəta yoxdur.
   - **Tövsiyə:**
     - imtahan günü girişi 2–5 dəqiqəlik pəncərəyə yaymaq (imtahandan əvvəl daxil olmaq);
     - **✅ tətbiq olundu:** login növbəsində 15 s gözləmə (`MAX_INFLIGHT_LOGIN_WAIT_SECONDS`), 503 əvəzinə növbə.
   - Parol hash-i zəiflədilmir.
8. **Test edge-in nginx 500-ü və başlanğıc timeout-u** (imtahan 1000–1500-də ~1%).
   - 500 cavabını Django yox, test nginx-i qaytarır (`Server: nginx`). App-da ERROR yoxdur.
   - Canlı nginx konfiqi fərqlidir: DNS ilə `app`, `worker_processes auto`. Ona görə bu,
     canlıda təkrarlanmış problem kimi qəbul edilmir. Yenə də replika artımından sonra canlı
     konfiqlə təkrar ölçülməlidir.

## İkinci gecə (2026-10-05 axşam): 8 replika → darboğaz DB-yə keçdi

8 replika × 0.5 CPU (eyni 4 CPU büdcəsi), DB 2 CPU, canlı image (gündüzkü düzəlişlər daxil):

| Pillə | Xəta % | ən pis p95 | Qeyd |
|---|---:|---:|---|
| login 500 / 120 s | 0 | 2.2 s | ✅ |
| kabinet 500 | 0 | 7.7 s | ❌ p95; **DB CPU 205 %**, PgBouncer gözləmə 87 |
| jurnal 500 | 0 | 0.23 s | ✅ (harness-in cədvəl parser-i yeni UX markup-ını tanımadı — 495 fixture xətası, yükə aid deyil) |
| imtahan 1000 | 5.1 | 30 s | ❌ **DB CPU 208 %**, autosave/finish 503, confirm timeout |

Bütövlük: 689 cəhd, 6890 cavab — 0 uyğunsuzluq.

**Nə dəyişdi:** app replikası artınca DB-yə eyni anda gələn sorğu sayı 2 qat artdı və darboğaz app-dan
DB-yə keçdi. DB-də ən çox gözləmə **`LWLock:LockManager`** idi (kabinetdə 75 sessiya, imtahanda 37).

**Səbəb:** PostgreSQL 16 hər backend üçün yalnız 16 «fast-path» kilid saxlayır. Sorğu cədvəli və
onun BÜTÜN indekslərini kilidləyir. Hər sorğuda oxunan cədvəllərdə indeks çox idi:

| Cədvəl | İndeks (əvvəl → sonra) | Canlıda istifadə |
|---|---:|---|
| `accounts_userprofile` | 24 → 6 | silinənlərin hamısı idx_scan ≈ 0 (DB yaradılandan bəri) |
| `registrar_studentacademicrecord` | 25 → 9 | silinənlər 0 və ya kompozitin prefiksi |
| `organizations_membership` | 14 → 8 | silinənlər 0 və ya kompozitin prefiksi |
| `exams_exam` / `exams_examattempt` | 15 / 16 → 10 / 12 | yalnız prefiks-təkrar və boolean indekslər |

Limit aşılanda kilid paylaşılan cədvələ düşür və bütün backend-lər bir LWLock üstündə növbəyə durur.
Miqrasiyalar yalnız `DROP INDEX` edir (FK məhdudiyyətinə toxunmur; geri qaytarma `CREATE INDEX`).

Digər düzəlişlər:
- Kabinet bölmələri hər açılışda bütün sütunlar üzrə `COUNT(DISTINCT …)` edirdi (semi-join-dən sonra
  lazımsız `.distinct()`) — silindi.
- Navbar oxunmamış bildiriş sayğacı imtahan/nəticə səhifəsində 2 dəfə (2 × COUNT + 4 `set_config`)
  hesablanırdı — sorğu daxilində bir dəfə.

### İndeks düzəlişindən sonra (canlı image cf89a57f, eyni 8×0.5 CPU + DB 2 CPU)

| Pillə | Xəta % | p50 / p95 | Qeyd |
|---|---:|---|---|
| login 500 / 120 s | 0 | 1.0 / 2.0 s | ✅ |
| kabinet 500 | 0 | **0.52 / 4.1 s** (əvvəl 2.4 / 7.7 s) | LockManager gözləməsi 75 → 6 |
| jurnal 500 (real qiymət yazısı) | 3.2 | 2.0 / 6.9 s (save) | 500 eyni anlı login + DB 200 % → 503 |
| imtahan 1000 | 4.7 | 5.3 / 7.6 s (autosave) | DB 208 % (2 CPU limiti), LockManager 37 → 27 |
| tələbə jurnalı 1000 | **38.6** | 6–8 s | app CPU: hər bölmə tam profil kontekstini qurur (~150 ms CPU) |
| kollokvium/final balı 300 | 7.7 | — | **deadlock** (aşağıda) + 503 |
| final mərkəzi 500 (PIN girişi) | **56** | PIN 40 s | PBKDF2: bir girişdə 3–4 PIN hash-i |
| export 100 | 0 | jurnal xlsx 0.19 s, nəticə xlsx 7.5 s | ✅ |
| canlı imtahan 300 (WS) | 8.9 | WS qoşulma 35 ms | host «start» 30 s timeout, join səhifəsi timeout |

Bütövlük: imtahan 6990, final 110, jurnal 10 425, midterm 5025, final balı 775 xana — **0 uyğunsuzluq**.

Bu gecə düzəldilənlər (testli):
- **Deadlock — imtahan balı daxiletməsi** (`registrar/exam_score_entry.save_roster_scores`): hər sətir
  Enrollment-i kilidləyir; iki işçi eyni siyahını fərqli ardıcıllıqla saxlayanda deadlock (500).
  Sətirlər indi sabit `enrollment_id` ardıcıllığı ilə yazılır.
- **Final PIN girişi:** eyni PIN eyni hash-ə qarşı iki dəfə yoxlanırdı (fərdi PIN yolu + `can_user_start`).
  Uğurlu yoxlama 60 s proses daxilində yadda saxlanır (açar = saxlanan hash + PIN-in HMAC-ı; səhv PIN
  həmişə tam hash). Hash gücü dəyişmir.

Qalan (növbəti iş, sahib qərarı lazım deyil):
- **Tələbə kabinet bölmələri** — bölmə endpoint-i tam profil kontekst qurucusunu işə salır; bölmə üzrə
  yüngül qurucu lazımdır (ən böyük app CPU qazancı).
- **Final mərkəzi PIN** — imtahan günü girişi zallara/dalğalara bölmək; PIN-in təyinatı (qrup əlavə
  edəndə hər tələbəyə sinxron `make_password`) fona köçürülməlidir.
- **Canlı imtahan host «start»** — 300 oyunçuda 30 s; hər oyunçu soketi öz auto-reveal taymerini qurur.
- **DB CPU** — test DB-si 2 CPU ilə məhdud idi; canlıda DB ilə app eyni 10 vCPU-nu bölür. VM-in 24–32
  vCPU-ya böyüdülməsi hər iki darboğazı birbaşa açır.

## Üçüncü dalğa (2026-10-06/07): qalan tapıntılar düzəldildi

Hamısı testli, canlıya üç paketlə çıxdı (main 53b9f5e0, 1d8b9389, sonra RLS paketi):

| Sahə | Əvvəl → sonra |
|---|---|
| Kabinet bölmə fraqmenti (tələbə) | qabıq dəyərləri tənbəl (`LazyValue`): ~13 sorğu az, ~30 % sürətli, HTML bayt-bayt eyni |
| Autosave (1 MCQ) | 26 → 19 sorğu; attempt BİR dəfə sətir kilidi altında, bütün audit zəmanətləri eyni ardıcıllıqla |
| Finish (5 sual) / start | 43 → 28 / 51 → 42 sorğu |
| Jurnal saxlama (25 xana) | 93 → 14 sorğu; fənnin bütün dərs/qiymətləri artıq yüklənmir |
| Final mərkəzi PIN girişi | uğurlu giriş 2–3 → 1 hash; uğursuz cəhd də 1 (istifadəçi-mövcudluq zaman sızması bağlandı) |
| Qrupa final/midterm təyini (300 tələbə) | ~17.6 s sinxron hash → ~3 ms; hash fon tapşırığında (`heavy` növbəsi) |
| Export / mətn çıxarışı | sorğuda 3 s gözləmə yoxdur; klient 1→5 s artan intervalla yoxlayır |
| Canlı imtahan (300 oyunçu) | hər keçiddə host-a 303 → 5 göndəriş; auto-reveal kilidi 82 → 1 |
| Hər sorğu: üzvlük + RLS | kabinet 30 → 26, imtahan səhifəsi 22 → 20; middleware üzvlüyü tenant RLS altında (bypass-sız) |
| Müraciət nişanı | 3–4 `COUNT(DISTINCT bütün sütunlar)` → 1 aqreqat |
| Autosave cavabı itəndə | eyni məzmunlu təkrar 409 yox, idempotent uğur |

Qəsdən dəyişdirilməyənlər: imtahan start-ındakı qısa `sleep` (tutum növbəsi və istifadəçi kilidi — admission
control); PIN hash gücü.

## Dördüncü ölçmə (2026-10-07 gecə, üç paket canlıda) + daphne/uvicorn A/B

Eyni plan, eyni test stack-i (8 app × 0.5 CPU, DB 2 CPU), canlı image c46f772e:

| Pillə | 10-05 axşam | 10-07 gecə |
|---|---|---|
| login 500 | 0 %, p95 2.0 s | 0 %, p95 **1.3 s** |
| kabinet 500 | 0 %, p50/p95 0.52 / 4.1 s | 0 %, **0.17 / 0.30 s** ✅ |
| jurnal 500 (real yazı) | 3.2 % | **1.2 %** |
| imtahan 1000 | 4.7 % | **3.3 %** (autosave p50 5.3 → 3.2 s) |
| tələbə jurnalı 1000 | 38.6 % | **17.5 %** |
| kollokvium/final balı 300 | 7.7 % | **4.0 %** |
| final mərkəzi 500 | **56 %**, PIN 40 s | **0 %**, PIN p95 **0.99 s** ✅ |
| export 100 | 0 % | 0 % |
| canlı imtahan 300 | 8.9 % | 2.1 % — host «start» hələ 28 s (ayrıca araşdırılır) |

Bütövlük: imtahan 7650, final 5000, jurnal 11 725, midterm 6025, final balı 900, canlı 1616 cavab — **0 uyğunsuzluq**.
Qalan xətaların hamısı tutum qapısının səliqəli 503-ləridir (Django tracebacki yoxdur); darboğaz test DB-sinin 2 CPU limitidir.

**daphne vs uvicorn (eyni 4 CPU):** uvicorn 4 konteyner × 2 worker — login p50 970 → 460 ms (CPU-ya bağlı
PBKDF2), kabinet eyni, amma imtahan 3.3 → 7.4 %, tələbə jurnalı 17.5 → 21.9 % xəta (limit worker başınadır,
konteyner daxilində yük qeyri-bərabər paylanır → daha çox 503). **Qərar: canlıda daphne qalır**; `ASGI_SERVER`
açarı A/B üçün saxlanılır.

## 50 000 nəfər haqqında

Tək 10 vCPU-luq serverdə 50 000 **eyni anda aktiv** istifadəçi mümkün deyil.

- **Ölçülən:** 4–5 app nüvəsində sərt temp (düşünmə 20–40 s) ilə ~1000 eyni-anlı imtahan
  ~1% xəta ilə keçdi. Bunun üçün təxminən 30–35 sorğu/s lazımdır.
- **Real temp:** tələbə sual başına 1–3 dəqiqə düşünür. Bu tempdə eyni sorğu axını
  ~3000 tələbəyə bərabərdir.
- **Təxmini canlı tutum:**
  - `APP_REPLICAS=8` ilə ~2 qat app CPU-su: **~4000–6000 eyni-anlı imtahan iştirakçısı**.
  - Bu, təxmindir, ölçülməyib. Replika artımından sonra canlı konfiqlə yoxlanmalıdır.
- **50 000 üçün lazım olanlar:**
  - ikinci app hostu (və ya daha çox nüvə);
  - çox-prosesli ASGI serveri;
  - imtahanların pəncərələrə bölünməsi.

## Eyni gecədə canlıya çıxanlar (main 21cef98b)

- Yuxarıdakı 5 performans düzəlişi.
- Təhlükəsizlik auditi (11 düzəliş):
  - `.xht`/`+xml` yükləmə XSS-i və qeyri-təhlükəsiz tiplərin attachment kimi verilməsi;
  - AI köməkçi vasitəsilə imtahan ortasında bal sızması;
  - coding gizli testlərin çıxışı;
  - ⌘K / FİN axtarış scope-u;
  - kurs resursu və sillabus köçürməsində sahiblik yoxlaması;
  - blog `visible_users`;
  - dərs yükü IDOR-ları;
  - dırnaq escape-i;
  - AI limitinin atomik sayılması;
  - apellyasiya şərhinin uzunluğu.
- UX review:
  - imtahanda daimi autosave statusu (şəbəkə / 503 / konflikt);
  - telefonda imtahan və jurnal düzülüşü;
  - stilli 503 səhifəsi;
  - kontrast və ARIA.
- Təhlükəsizlik tabında IP / şəbəkə filtri və «bu IP-dən uğurlu girişlər».
