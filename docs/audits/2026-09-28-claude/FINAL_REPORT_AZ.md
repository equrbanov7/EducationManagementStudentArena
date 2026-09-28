# EMSArena — Tam Texniki Audit Hesabatı

**Tarix:** 2026-09-28 · **Budaq:** `Develop` @ `914a6571` + həmin günün commit olunmamış işi (kurs paneli redizaynı)
**Metod:** 6 müstəqil, yalnız-oxuma rejimli auditor (arxitektura/DevOps, təhlükəsizlik/autentifikasiya, tenant izolyasiyası,
imtahan sistemi, baza/performans, biznes axınları/keyfiyyət) + orkestratorun sintezi və çarpaz yoxlaması.
**Dəlillər:** hər sahənin tam hesabatı `findings/<sahə>.md` (ingiliscə, fayl:sətir, test əmrləri və nəticələri ilə).

> **Təhlükəsizlik qaydası yerinə yetirilib:** heç bir real/prod məlumat dəyişdirilməyib, `:5432` (real baza) və `:55433`
> (QA klon) bağlantısı açılmayıb, prod serverə və GitHub workflow-larına toxunulmayıb, e-poçt/SMS göndərilməyib.
> Bütün sübut-testlər auditorların **öz** sandbox bazalarında (`:55432/ems_audit_*`) aparılıb. Heç bir gizli dəyər bu
> hesabatda yoxdur — yalnız mövcudluq və yer.

---

## 1. Executive Summary

EMSArena — Django 5.2 + Channels/Daphne, PostgreSQL 16 (RLS + PgBouncer), Redis, Celery üzərində qurulmuş,
server-render şablonlar + vanilla JS istifadə edən **modul monolit**dir (React/TypeScript **yoxdur** — təsdiqləndi).
2026-09-13 auditindən sonra görülən iş nəzərəçarpacaqdır: o auditin **bütün P0/P1 düzəlişləri qüvvədədir**
(imtahan 19/19, təhlükəsizlik 95/95 reqressiya testi keçir), prod tətbiq rolu artıq **NOBYPASSRLS**-dir (repo sübutu),
deploy-da SHA-teqli image + avtomatik rollback + məcburi pre-deploy dump var, modul ölçü büdcəsində "grandfathered"
fayl qalmayıb, `pip-audit` məlum zəiflik tapmır, `check --deploy` 0 xəbərdarlıq verir.

**Ən vacib 5 nəticə:**

1. **P0 — İmtahan cavab açarının sızması (EX28-01).** END_QUESTION formatında idxal olunmuş testlərdə düzgün variant
   HTML-də **ən kiçik `option.id`**-dir (8/8 sualda sübut olundu). Tələbə "View Source" ilə finalda da düzgün cavabı
   görə bilər. Növbəti test imtahanından əvvəl düzəldilməlidir.
2. **P1 — Ehtiyat nüsxə (backup) strategiyası real fəlakətə dözümlü deyil (AD-01, AD-02).** Off-site/şifrəli/media
   backup yoxdur; sənədləşmiş bərpa addımları isə canlı bazaya yarımçıq yükləyərək **məlumatı korlayır** (sandboxda
   təkrarlandı). Tək serverin itkisi = bütün akademik məlumatın itkisi.
3. **P1 — Akademik bütövlük boşluqları (EXA-01, EX28-02, SYL-1, S1).** Köhnə cəhd üzrə apellyasiya yeni cəhdin rəsmi
   balını aşağı salır (50→25 sübut); müəllim hələ yazılmaqda olan cəhdi qiymətləndirib jurnala yaza bilir; kafedra
   müdiri öz sillabusunu təsdiqləyə bilir; xaric olunmuş tələbə jurnallarda qalır.
4. **P1 — Sorğu (survey) anonimliyinin pozulması (SV-1).** Rektor/keyfiyyət rolu "universitet − fakültə" fərqi ilə
   3-dən az nəfərlik bölmənin cavablarını hesablaya bilir.
5. **P1 — Lokal inkişaf maşınında prod məlumatı olan sandbox Postgres LAN-a açıqdır (AD-03).** `0.0.0.0:55432`, repoda
   commit olunmuş defolt parol, macOS firewall söndürülüb, bazalar prod-surət adlarındadır.

**Ümumi qiymət:** 22 sahənin orta balı **74 / 100** (sahə dəsti 2026-09-13 auditindən fərqli olduğu üçün 79.4 ilə
birbaşa müqayisə edilməməlidir; eyni sahələrdə tenant izolyasiyası 78→86, DevOps 66→72 yüksəlib).
**İstehsala hazırlıq:** mövcud istifadə səviyyəsi (≈1k eyni-anlı istifadəçi) üçün **şərti hazırdır**; **P0 + backup P1-ləri
bağlanmadan** istifadənin genişləndirilməsi (yeni universitetlər, 5k+ eyni-anlı) tövsiyə olunmur.

**Bu gün (2026-09-28) auditin gedişində artıq düzəldilənlər** (yalnız həmin gün yazılmış kodla bağlı olanlar):
- C1/S1-in kurs hissəsi: qrupla kursa əlavə edəndə xaric olunmuş / məzuniyyətdəki tələbələr artıq düşmür
  (`registrar/course_groups.py` — aktiv+enrolled akademik qeyd şərti) + test;
- T-03: `add_member` POST artıq yalnız tələbə qəbul edir (müəllim/işçi «tələbə» kimi əlavə olunmur) + test;
- DB-04: bir sorğuda ən çox 20 qrup; DB-05: AI plan sorğusunda istifadəçi başına paralel-sorğu kilidi + Gemini
  çağırışına 45 s zaman limiti və 2 modellik zəncir; DB-06: tapşırıq/layihə yaratma-redaktə və lab redaktəsi atomik
  (`@transaction.atomic` + xətada `set_rollback`) + testlər.

---

## 2. Project Architecture

```text
Brauzer (tələbə / müəllim / idarəçi / imtahan zalı kompüteri)
   ↓  HTTPS (nginx: TLS, gzip, şəbəkə zonası X-EMS-Zone, statik/media X-Accel)
Frontend: Django şablonları + vanilla JS (417 fayl, ~81k sətir), EMSReady/EMSDelegate AJAX-safe qat,
          ems_ui komponent sistemi, CSP (script-src self+nonce, unsafe-inline yoxdur)
   ↓
Daphne (ASGI, 8 replika) → Django: middleware (tenant/RLS GUC, view-as, admin 2FA, rate-limit, RequestQueue)
   ↓
Views (28 app) → public.py fasadları → services/ + domain/ (state machine-lər, ledger-lər, audit)
   ↓
PostgreSQL 16 (RLS+FORCE 164 cədvəl, 60+ invariant trigger)  ←PgBouncer (session mode)
Redis (cache, session=cached_db, rate-limit, Channels layer, Celery broker)
Celery (default + heavy növbələr, beat: sweep-lər, bildirişlər, ekstraksiya)
   ↓
Infra: tək host (80 nüvə / 62 GiB), docker compose (23 servis), Prometheus/Alertmanager/Grafana/Loki,
       postgres-backup sidecar (lokal), GitHub Actions (8 shard CI → self-hosted runner ilə deploy)
```

- **Güclü tərəflər:** 4 "ratchet" qapısı yaşıl (0 statik dövr, 0 özəl cross-app import, context-map, modul ölçüsü);
  tenant qatı iki səviyyəlidir (app scoping + RLS); akademik yazılar kilid ardıcıllığı ilə (`offering → enrollment → cell`).
- **Zəif tərəflər:** 13 app cütü `apps.get_model()` vasitəsilə **gizli iki-tərəfli** asılıdır (organizations↔registrar ən
  ağır; qapı bunu görmür — AD-08); `accounts` 67k sətirlik "UI god-app"-dır, 17 app-dən asılıdır (AD-09).
- **Miqyas:** hazırkı arxitektura 1 universitet / ≈1k eyni-anlı istifadəçi üçün rahatdır; 5k üçün 12–16+ replika, 10k
  üçün ikinci host və transaction pooling tələb olunur (bax §12).

## 3. Backend Analysis

- Xidmət qatı intizamlıdır: jurnal, final, komponent, selfwork yazıları `@transaction.atomic` + sənədləşmiş kilid
  ardıcıllığı; threaded race testləri var. 2026-09-13-dəki F-02/03/04 audit boşluqları və "hard delete" kaskadı bağlanıb.
- **DB-01 (P2, sübut):** `grade_audit.log_grade_changes` atomic blok içində savepoint-siz `try/except` edir — audit
  INSERT-i xəta verərsə **bütün bal yazısı səssizcə geri alınır**, müəllim isə "yadda saxlanıldı" görür
  (`{'written': 1}`, bazada 0 sətir). Düzəliş: savepoint + `logger.exception` (appeals-də artıq belə edilib).
- **DB-07 (P2):** audit izi boşluqları — dərs saatının dəyişdirilməsi/silinməsi, kataloqda müəllim dəyişməsi, lab/tapşırıq
  qiymətləndirməsi, admin bulk əməlləri; audit sətirlərində `request_id` və tələbə id-si yoxdur.
- 505 geniş `except Exception` (29-u səssiz `pass`, əksəriyyəti zərərsiz cache/təmizləmə).
- `.delay` çağırışları `on_commit` olmadan (P3, `ATOMIC_REQUESTS` söndürülüb deyə hazırda zərərsiz).

## 4. Frontend Analysis

- React/TS/SPA yoxdur; 0 icra olunan inline `<script>`/`<style>` (36 uyğunluğun hamısı JSON data bloku). CSRF bütün POST-larda.
- 2026-09-13 frontend tapıntılarının (F1–F22) əksəriyyəti bağlanıb.
- **FQ-FE-1 (P3):** bildiriş şablonlarında 2 `onclick="return confirm(...)"` CSP tərəfindən bloklanır → silmə **təsdiqsiz** gedir.
- **FQ-FE-2 (P3):** `CLAUDE.md`-dəki yoxlama `grep`-i (PCRE look-ahead, `-E` ilə) bu maşında işləmir — qapı faktiki no-op-dur.
- **FQ-FE-4 (P3):** 73 native `alert()` (xüsusən labs/assignments/projects modalları); 21 `fetch` faylı `res.ok` yoxlamır.
- **FQ-FE-3 (P3):** iki əl ilə yazılmış JSON i18n blokunda `escapejs` yoxdur (gələcək tərcümə `JSON.parse`-ı sındıra bilər).
- **FQ-TEST-1 (P2):** 81k sətir JS CI-da heç vaxt icra olunmur (jsdom harness mövcuddur, amma qoşulmayıb).

## 5. Database Analysis

- Sxem güclüdür: UUID PK, bütün FK-lər indeksli, zəngin UNIQUE/CHECK (`FinalGrade.exam_score` 0..100), append-only audit
  trigger-ləri, 28 app / 314 miqrasiya, 0 çox-leaf, hamısı geri qaytarıla bilən, böyük cədvəl indeksi `CONCURRENTLY`.
- **DB-02 (P2):** heç yerdə `statement_timeout` / `lock_timeout` / `idle_in_transaction_session_timeout` yoxdur; nginx və
  Daphne 900 s pəncərə verir; PgBouncer `QUERY_WAIT_TIMEOUT` defoltdur (120 s). Bir ilişmiş jurnal tranzaksiyası həmin
  fənnin jurnalını hamı üçün dondura bilər. (Əvvəl DB-01 düzəlməlidir — timeout gizli audit xətasını real edə bilər.)
- P3: LessonMark-da ≈60 MB sıfır-seçicilikli indekslər; `OrgUnit` qrup adı/kodu üzrə unikallıq yoxdur (əvvəl məlumat
  təmizlənməlidir); bildiriş və audit cədvəlləri üçün retention yoxdur; `TRUNCATE` trigger-i yoxdur.
- `accounts_userprofile` (FİN/telefon/ünvan) RLS-siz qalır — sənədləşmiş dizayn qərarı (login-dən əvvəl oxunur).

## 6. Security Audit

**Keçdi (sübutla):** SQL injection (31 raw-SQL nöqtəsi — hamısı parametrli), şablon XSS (`mark_safe` 0), CSRF (1
`csrf_exempt` — bearer + `compare_digest`), CORS yoxdur, open redirect (hamısı same-origin yoxlamasından keçir), SSRF,
command injection, deserialization, mass assignment (`fields="__all__"` yoxdur), `check --deploy` 0 xəbərdarlıq.
Bugünkü dəyişiklik real bir dəliyi bağladı: tapşırıq/layihə əvvəl **istənilən istifadəçi id-sini** qəbul edirdi.

**Tapıntılar:**
- **SA-05 (P2):** live-exam müəllim səhifəsində AI xülasəsi escape olunmadan `innerHTML`-ə yazılır; oyunçu nik-i prompt-a
  düşür → HTML inyeksiyası (CSP skripti bloklayır, amma forma/link/stil inyeksiyası qalır). 2026-09-13 düzəlişinin
  unudulmuş "qardaşı".
- **SA-06 (P2):** Gemini API açarı URL query-də göndərilir; şəbəkə xətasında loglara düşür (lokal testdə 4 dəfə) —
  sanitizer onu tutmur. Açar `x-goog-api-key` başlığına köçürülməli; loglar hostdan çıxıbsa açar dəyişdirilməlidir.
- **SF-1 (P2):** plagiat ekstraktorunda Office "decompression bomb" — 1.6 MB `.pptx` → 2.34 GB RSS; istənilən tələbə
  Celery worker-i yaddaşdan çıxara bilər.
- **SA-07 (P3):** admin 2FA şlüzü `/media/`-ni istisna edir — yalnız parolu bilən superuser OTP-siz özəl fayl yükləyə bilər.
- Fayl yükləmələri (§8), gizli açarlar (§21) ayrıca.

## 7. Authentication & Authorization

**Autentifikasiya (73):** 2026-09-13 düzəlişləri qüvvədədir (95 test). Sessiya: `cached_db`, HttpOnly, SameSite=Lax,
Secure, 24 s mütləq / 8 s boşda, `login()` açarı fırladır. İmtahan PIN-i: 8 rəqəm, `secrets`, hash-lənmiş, IP+istifadəçi
limitləri, zaman bərabərləşdirməsi.
- **SA-02 (P2):** UI-da istifadə olunmayan `/accounts/verify-otp/` (`purpose=login`) yalnız e-poçta gələn kodla —
  **parolsuz** — daxil edir, login rate-limit-lərini və tələbə/işçi portal qapısını keçir; superadmin üçün "iki faktor"un
  hər ikisi eyni poçt qutusuna gedir. **SA-01 (P2):** `send-otp` e-poçtun qeydiyyatda olub-olmadığını göstərir.
  Tövsiyə: bu üç JSON OTP marşrutunu silmək.
- **SA-03 (P2):** hesab səviyyəsində limit yoxdur — 80 fərqli IP-dən 80 səhv parol 429 vermədi, sonra düzgün parol keçdi.
- **SA-08 (P3):** `ikt_rehber`, rektor kimi yüksək səlahiyyətli rolların ikinci faktoru yoxdur (2FA yalnız `is_staff`).

**Avtorizasiya (76):** server tərəfində yoxlanır; 978 marşrutun hamısı triaj edildi, qorunmamış həssas marşrut yoxdur.
- **SA-04 (P2, prod-da belə hesab varsa P1):** "superadmin"in iki tərifi var (`is_superuser` vs `profile.role`).
  `profile.role='superadmin'` olan hesab 2FA-sız superadmin səhifələrinə girir, rektor onu "view-as" ilə açıb bütün
  tenantlarda superadmin kimi işləyə bilir (sübut: view-as ilə 200, olmadan 403). Sahib üçün yalnız-oxuma sayma sorğusu
  `findings/security_auth.md` SA-04-dədir.
- **TT-1 (P2, sahib qərarı):** bir fakültəyə məhdud koordinator təşkilat üzrə cədvəl siyasətini dəyişə bilir.
- **SYL-1 (P1):** müəllif-təsdiqləyici eyni şəxs ola bilər (bax §10).

## 8. Multi-Tenant Isolation — **86/100** (əvvəl 78)

- Prod tətbiq rolu NOBYPASSRLS-dir (repo sübutu: `NEW_SERVER_TASKS_2026-09-14.md`, commit `6e71c4f2`) → RLS real ikinci qatdır.
- 37 çılpaq `get_object_or_404` və 87 id-lookup ayrı-ayrı yoxlanıldı. İki təşkilatlı sübut-testlərdə **17/17 IDOR cəhdi
  bloklandı** (bugünkü qrup/AI/üzv/tapşırıq/lab/layihə endpoint-ləri daxil).
- **T-01 (P2, ən vacib):** "Bildiriş dərc et" `org_<id>` hədəfi yalnız "hədəf təşkilatda üzvlük" yoxlayır:
  - **adi müəllim bütün universitetə** (≈8.4k nəfər) istənilən link və fayl əlavəsi ilə sistem bildirişi göndərə bilir
    (fişinq vektoru; RLS bunu **bloklamır**);
  - A təşkilatının admini, B-də tələbə üzvlüyü ilə, B-nin bütün üzvlərinə yaza bilir — prod-da RLS bunu bloklayır
    (tək qat).
  - Düzəliş kiçikdir: yalnız aktiv təşkilat + org-admin.
- **T-02 (P3):** `auth_user` / `userprofile` RLS-siz olduğundan istifadəçi bağlama qərarları yalnız app kodundan asılıdır (bu gün düzgündür).
- **T-04 (P3):** `bypass_rls()` inventarı sürüşüb (179 çağırış / 82 fayl, 11-i təsnifsiz), CI-da yoxlanılmır.
- **T-05 (P3):** `EMS_DB_ROLE_ENFORCE=warn`; `APP_DATABASE_USER` itərsə compose səssizcə sahib roluna keçir → RLS qatı yox olur.

## 9. Exam System — **70/100**

**Düzgün işləyənlər (sübutla):** server tərəfli deadline + sətir kilidi + OCC 409; ikiqat göndəriş idempotentdir; DB
unikallıq məhdudiyyətləri (açıq cəhd, cəhd nömrəsi); hər tələbə endpoint-i `user=request.user`; `take_exam` HTML/JSON-da
`is_correct` yoxdur; coding testlərinin gizli hissələri redaktə olunur; media yalnız çatdırılmadan sonra; nəzarət WS
yalnız sahib/müəllif; jurnal sinxronu `on_commit` ilə, yalnız `final` kateqoriyası.

**Tapıntılar:**

| ID | Səviyyə | Qısa |
|---|---|---|
| EX28-01 | **P0** | END_QUESTION idxalında ən kiçik `option.id` = düzgün cavab (8/8); finallara da aiddir |
| EX28-02 | **P1** | Hələ yazılan (in_progress) cəhd qiymətləndirilir, jurnala yazılır, 5 dəq sonra kilidlənir |
| EX28-03 | P2 | Çox-cəhdli imtahanda 1-ci cəhdin cavab açarı dərhal görünür → boş cəhd, sonra 3/3 (sahib qərarı) |
| EX28-04 | P2 | Deadline-dan sonrakı 15 s güzəşt 60 s-lik sweep və ya istənilən GET tərəfindən pozulur → son cavablar itir; zalda bütün otağa eyni anda təsir edir |
| EX28-05 | P2 (latent) | `RLS_TRANSACTION_SCOPED` yandırılsa sweep bütün açıq cəhdləri kilidləyir → hər dəqiqə autosave donur (bayraq prod-da söndürülüb) |
| EX28-06 | P2 | Jurnal balı "son yazan qalib" — köhnə cəhdə apellyasiya yeni balı əzir (EXA-01 ilə sübut) |
| EX28-10 | P2 | Live-quiz: cavabın düzgünlüyü açıqlamadan əvvəl oyunçuya qayıdır + limitsiz çoxlu qoşulma |
| EX28-07/08/09/11 | P3 | `end_datetime` başlanmış cəhdə tətbiq olunmur; deadline-dan sonra coding submit; coding ZIP-i təşkilatın istənilən müəllimi yükləyə bilir; apellyasiyada "daxili qeyd" tələbəyə görünür |

Kənar hallar: refresh/tab bağlanması/bağlantı kəsilməsi zamanı autosave qorunur (≤1 s test, ≤3 s yazılı itki pəncərəsi);
Redis dayansa `/exams/final/` PIN girişi 500 verir (P3). Brauzer, yük və Redis-down canlı testləri **aparılmayıb**.

## 10. Business Logic

Axınlar kod üzrə izləndi, P1/P2-lər sandboxda sübut-testləri ilə təsdiqləndi. Sahə balı **71**.

- **Sillabus (80):** tək fail-closed state machine, DB məhdudiyyətləri, hər keçid audit olunur. **SYL-1 (P1):** müəllif +
  təsdiq icazəsi olan (kafedra müdiri müəllim kimi) öz sillabusunu təsdiqləyir. P2: rədd edilmiş v2.0-dan "minor" v2.1
  ilə struktur dəyişikliyi təsdiqlənə bilir (SYL-2); autosave artıq göndərilmiş versiyaya yaza bilir (SYL-3); `submit()`
  icazəni yoxlamadan əvvəl yazır (SYL-4).
- **Jurnal (80):** instructor-yalnız redaktə, 2 saatlıq dondurma həm servisdə, həm PG trigger-də. **J-01 (P2):**
  `save_finals` imtahan/resit balını ledger və keçmiş-dövr kilidindən yan keçərək yazır, rəqəm olmayan giriş → 0.
  **J-02 (P2):** `update_lesson` `hours=0` və təkrar vaxt qəbul edir, audit yoxdur — 25% buraxılış qərarını dəyişə bilər.
- **İmtahan → apellyasiya (62):** **EXA-01 (P1)** köhnə cəhdə apellyasiya rəsmi balı 50→25 salır; EXA-02 qiymətlənməmiş
  yazılı cəhdə apellyasiya; **EXA-03** sahibin 2026-09-07 memo tələbi (cəhd tarixçəsi) səhv faiz göstərir, midterm-i rəsmi
  sayır, apellyasiya sətirləri yoxdur; EXA-04 davamiyyət buraxılış qapısı zal/PIN yolunda yoxdur.
- **Tələbə həyat dövrü (68):** **S1 (P1)** xaric/məzuniyyət statusu `Enrollment`-ə toxunmur — tələbə jurnalda və imtahan
  vərəqində qalır (kurs qrupu hissəsi bu gün düzəldildi); S2 qrup bölünməsi müəllimsiz açılış yaradır.
- **Dərs yükü → cədvəl (66):** W1 kafedranın öz qaralaması koordinator/dekan təsdiqini keçir; W2 sətir saatları təyin
  olunmuşdan aşağı salına bilər; **W3** müəllim/qrup/otaq ikiqat rezervasiyasına DB qoruması yoxdur, yoxlama tranzaksiyadan kənardır.

## 11. Performance — **82/100**

- 21 əsas səhifə 2→30 tələbə və 2→12 dərs arasında **sabitdir** (N+1 yoxdur); 2026-09-13-dəki 4 N+1 və 4 ağır səhifə düzəlib.
- Hər səhifə 32–65 sorğu, bunlardan ≈15–25-i qabıq (5–9 təkrar `organizations_membership` SELECT — DB-13).
- Jurnal şəbəkəsi HTML-i 490–700 KB (gzip ilə ötürülür); şəbəkə yadda saxlama tələbə başına ≈3.2 sorğu (36→125).
- Hesablama: `DB-13` (sorğu-daxili memo) hər səhifədə ≈5 sorğu qənaət edər — ən ucuz miqyas qazancı.

## 12. Scalability — **64/100**

**DB-03 (P2, sübut):** `ASGI_THREADS=12` sync view paralelliyini məhdudlaşdırmır (60 paralel sorğu = 60 thread); hər
uçuşdakı sorğu PgBouncer (session mode) bağlantısı tutur; ümumi backpressure yoxdur → yüklənmədə hamı yavaşlayır,
503 əvəzinə. Sənədlərdəki tutum hesabları səhvdir.

| Eyni-anlı istifadəçi | Qiymətləndirmə (**TƏXMİN**, ölçü deyil) |
|---|---:|
| 100 | Asan |
| 500 | 8 replika ilə rahat |
| 1 000 | Rahat (login fırtınası istisna) |
| 5 000 | 12–16+ replika lazımdır (RAM 32 GB+); 5k-lıq login fırtınası ölçülmüş ≈55–60 login/s həddini aşır |
| 10 000 | Tək hostda konfiqurasiya edildiyi kimi **mümkün deyil** (RAM, hovuz, `max_connections`) — ikinci host + transaction pooling |

Giriş məlumatı: iyul k6 login testi (≈105–112 RPS plato, p95 0.9 s → 16 s 50→1000 VU), 2026-09-13 klon ölçüsü (~40 RPS/proses).

## 13. Concurrency

Jurnal/final/komponent/sillabus yolları kilidli və race-testlidir (82). Açıq qalanlar: EX28-04 (güzəşt pəncərəsi),
EX28-05 (latent qlobal kilid), SYL-3 (autosave köhnə obyekt üzərində), W3 (cədvəl check-then-write), DB-09 (müraciət
statusu kilidsiz yoxlanır — iki eyni anda son status), J-06 (mümkün deadlock ardıcıllığı, PLAUSIBLE),
kurs "qrup əlavə" `group_name` oxu-yaz (P3). DB-06 bu gün düzəldildi.

## 14. Redis & Celery

`acks_late` + prefetch 1, yumşaq/sərt limitlər (240/300 s; heavy 840/900 s), `default`/`heavy` növbə ayrılığı, sweep-lər
CAS/idempotent, `reap_stuck_extraction_jobs`, broker visibility 3600 s > bütün limitlər, Redis AOF + `noeviction`, cache
və sessiya Redis xətasına dözümlü. **Nə olur:** Redis çökərsə — sessiyalar DB-dən oxunur, rate-limit/imtahan PIN girişi
500 verə bilər (P3), Channels canlı funksiyalar dayanır; worker çökərsə — tapşırıq "failed" olur (təkrar göndərilmir,
reaper təmizləyir); tapşırıq iki dəfə icra olunarsa — sweep-lər idempotentdir; e-poçt provayderi yoxdursa — sərhədli retry.
Zəiflik: bəzi sinxron fallback-lar broker olmadıqda ağır işi request thread-ində icra edir (DB-03 ilə birlikdə risk).

## 15. API Analysis — **79/100**

Ardıcıl JSON 403/404, tenant-scoped lookup, bal/idxal/AI üçün rate-limit. Zəifliklər: rəqəm sahələri doğrulanmadan
`int()` → 500 (SA-10), timetable-da səhv UUID → 500 və `str(exc)` brauzerə (TT-3/TT-4), istifadəsiz köhnə OTP API
marşrutları (SA-01/02). Versiyalama yoxdur (daxili API — qəbul edilə bilər).

## 16. UX/UI — **77/100**

`ems_ui` üstünlük təşkil edir (3 082 istifadə), köhnə `card` 1 194 → 586, EMSConfirm hər yerdə, boş/yükləmə vəziyyətləri
geniş (96/55 şablon). Bugünkü redizayn: kurs paneli, profil kurs kartları, yoxlama səhifələri, vahid təsdiq dialoqu,
skeletonlar, redaktə modalı. Qalanlar: labs/assignments/projects modallarında native `alert()` xəta UX-i, 5 paralel BEM
sistemi, bildirişlərdə təsdiqsiz silmə (FQ-FE-1).

## 17. Accessibility — **76/100**

0 `alt`-sız şəkil, 0 fokuslanmayan klik hədəfi, 214 `:focus-visible` qaydası, 44 faylda `prefers-reduced-motion`.
Qalanlar: `--ems-neutral-400` mətn rəngi kimi 45 qaydada (2.56:1 — AA keçmir; bugünkü fayllarda düzəldildi);
xəta səhifələrində sərt `lang="az"`; ≈77 etiketsiz kontrol və 34 adsız ikon düyməsi (evristik); ekran oxuyucu ilə
real sınaq aparılmayıb.

## 18. Internationalization — **76/100**

- Kataloq qapısı yaşıldır (4 dil × 2 domen: 0 çatışmayan, 0 placeholder xətası, 0 raw-key sızması).
- **Bu gün kurs sahəsində 1 060 səhv tərcümə düzəldildi** — məsələn: kontekstsiz «Sil» → az «Dil»; uğur mesajı
  «yaratmaq mümkün olmadı»; ru/tr-də «sərbəst iş» frilans kimi («Добавьте свою первую вакансию фрилансера»),
  «Max. Honey», «Save to memory», «Награжден!».
- **Qalanlar:**
  - FQ-I18N-1 (P2): şifrə bərpası səhifələri 4 dildə ingiliscədir.
  - FQ-I18N-2 (P2): ru/tr qeydiyyatda müəllim/işçi rolları təşkilat adı ilə eyni, «kurs işçisi» = «kurs tələbəsi».
  - FQ-I18N-3 (P2): en işçi idarəsinin tələbə tablarında «teacher» yazılır.
  - FQ-I18N-4 (P3): ≈20 deasciified tr sətri, 16 Python sətri gettext-siz.
  - Yoxlayıcıda kor nöqtələr: az-da ingiliscə, ru-da kirilsiz mətn tutulmur.

## 19. Testing — **75/100**

726 test faylı, **≈10.5k test** (10 317 keçdi + 224 ötürüldü), 8 shard CI (≈12 dəq), RLS üçün ayrıca 2 shard, güclü qoruyucu testlər (URL auth sweep,
sorğu büdcələri, modul qapıları). Bugünkü tam dəst: bax §32 "Yoxlama nəticəsi". Boşluqlar: bugünkü P1/P2 axın
bug-larının heç birini örtən test yox idi; JS CI-da icra olunmur; `time_machine`/`freezegun` yoxdur; race testləri
nazikdir; coverage qapısı (68%) yalnız PR/3.11-də işləyir — `main`-ə gedən yolda yoxdur (AD-07).

## 20. Code Quality — **80/100**

flake8/black/isort təmiz (bugünkü iş daxil), 1 TODO, 0 "grandfathered" böyük fayl, bugünkü silinmələrdən sonra 0
asılı istinad. Qalanlar: 505 geniş `except`, ölü `appeals/services/state_machine.py`, 114 birdəfəlik `scripts/i18n_*.py`,
34 fayl 600 sətir limitinə "söykənir" (bölünmə cavabdehliyə görə deyil, sətirə görə edilir).

## 21. DevOps & Infrastructure — **72/100** (əvvəl 66)

- **Yaxşılaşmalar:** SHA-teqli image, avtomatik rollback, fail-closed pre-deploy dump, stop grace period-lar, IPAM
  pin, worker healthcheck-ləri, `--proxy-headers`, 94 infra testi yaşıl, `check --deploy` 0.
- **AD-04 (P2):** `production.py`/`local.py`-dakı açıq `from .base import (...)` siyahısı **22 ayarı prod-da səssizcə
  itirir**: `AI_ASSISTANT_ENABLED=false`, OTP/PIN cəhd limitləri, monitorinq URL-ləri `.env`-dən təsir etmir (sübut).
- **AD-05 (P2):** CI-da skan olunan image deploy olunmur (server özü build edir, `apt upgrade` layı keşdən gəlir → OS
  yamaları prod-a çatmır).
- **AD-06 (P2):** lock faylı yoxdur — 141 paketdən 73-ü (Celery runtime daxil) pinlənməyib.
- **AD-07 (P2):** `main`-ə birbaşa push — coverage, 3.11 testləri və PR review buraxılır.
- **AD-08 (P2):** gizli runtime dövrləri (§2).
- **P3:** X-Forwarded-Host nginx-də yazılmır (AD-10); konteyner sərtləşdirməsi yoxdur (AD-13); action-lar teq ilə
  pinlənib (AD-14); staging yoxdur (AD-19).
- **Gizli açarlar:**
  - işçi ağacda gitleaks 0 tapıntı verdi;
  - təmizlənmiş tarix 2 lokal worktree budağında və offline mirror-da qalır (AD-11);
  - prod açarlarının təmizlikdən sonra dəyişdirildiyi yoxlanıla bilmədi.

## 22. Monitoring & Logging — **70/100**

JSON loglar + `request_id` + e-poçt/telefon maskalanması, `pg_stat_statements`, Watchdog / bildiriş-xətası /
heavy-queue alert-ləri (əvvəlki tapıntılar bağlanıb), append-only audit modeli. Boşluqlar (DB-08): PgBouncer gözləmə,
deadlock, uzun tranzaksiya alert-i yoxdur; Grafana 5 paneldir (Celery/Redis/PgBouncer yoxdur); yavaş sorğu və
lock-wait loqu yoxdur; tətbiqdə in-flight metrikası yoxdur; istifadəçi adları loglarda maskasızdır (SA-10).
**Hadisə diaqnozu:** HTTP/5xx səviyyəsində mümkündür; DB doyması (DB-03) isə yalnız latency alert-i yananda görünür.

## 23. Backup & Disaster Recovery — **45/100**

Gündəlik sidecar dump (7/4/3), ikinci systemd dump, təzəlik alert-i, pre-deploy dump, bir real-ölçülü `pg_restore`
(2026-09-14) var. **Amma:**
- **AD-01 (P1):** off-site, şifrəli və media backup-ı yoxdur, PITR yoxdur (DB RPO = 24 s, media RPO = limitsiz).
- **AD-02 (P1):** `deployment.md`-dəki "Restore procedure (tested!)" və "Database rollback" addımları dump-ı **canlı
  bazaya** yükləyir və səhv servis adları işlədir. Sandboxda təkrarlandı:
  - PK-li cədvəllər geri qaytarılmadı;
  - PK-siz cədvəl ikiqat oldu (2 → 4 sətir);
  - sxem yeni versiyada qaldı.

  Bu təlimata əməl etmək bərpa oluna bilən insidenti **məlumat korlanmasına** çevirir. Yalnız "təzə host" yolu düzgündür.
- RTO ölçülməyib; heç bir bərpa məşqi cədvəl üzrə aparılmır.

## 24. Data Migration Integrity

Real/klon bazası bu auditin qaydaları üzrə **oxunmayıb**. Kod və hesabat səviyyəsində:
- Uzlaşdırma aləti düzgün yalnız-oxumadır (`scripts/legacy_reconcile/transport.py`): `READ ONLY` tranzaksiya,
  `statement_timeout`, superuser/BYPASSRLS rədd olunur.
- `MISSING_SCORES_2026-09-25.md` üzrə 3 649 cari tələbə MyEdu ilə uzlaşdırılıb, 3 təmir addımı məşq edilib, "prod-a
  hələ heç nə yazılmayıb".
- 2026-09-13-dəki L1–L10 miras tapıntıları və 349 `exam_score>50` sətri **yoxlanılmayıb** (klon qadağan idi).
- Struktur riski: `OrgUnit` ad/kod unikallığı yoxdur (C3/C4 — əvvəl məlumat təmizliyi).

## 25. Critical Findings (P0 + P1 icmalı)

| # | ID | Səviyyə | Sahə | Qısa | Status |
|---|---|---|---|---|---|
| 1 | EX28-01 | **P0** | İmtahan | Ən kiçik `option.id` düzgün cavabı göstərir | Açıq |
| 2 | AD-01 | P1 | Backup | Off-site / şifrəli / media backup yoxdur | Açıq |
| 3 | AD-02 | P1 | Backup | Bərpa təlimatı məlumatı korlayır | Açıq |
| 4 | AD-03 | P1 | Lokal host | Prod-surət sandbox PG LAN-a açıq, defolt parol | Açıq (sahib) |
| 5 | EX28-02 | P1 | İmtahan | Bitməmiş cəhdin qiymətləndirilib jurnala yazılması | Açıq |
| 6 | EXA-01 | P1 | Apellyasiya | Köhnə cəhdə apellyasiya rəsmi balı aşağı salır | Açıq |
| 7 | SYL-1 | P1 | Sillabus | Öz sillabusunu təsdiqləmə | Açıq |
| 8 | S1 | P1 | Həyat dövrü | Xaric/məzuniyyət tələbəsi jurnalda qalır | Qismən (kurs hissəsi bu gün) |
| 9 | SV-1 | P1 | Sorğu | Fərq üsulu ilə k<3 anonimliyin pozulması | Açıq |

## 26. Technical Debt

- Gizli runtime iki-tərəfli asılılıqlar (13 cüt) və `accounts` aqreqasiyası — e-jurnalın mikroservisə çıxarılmasının əsas maneəsi.
- Tutum modeli və sənədlər real ASGI davranışına uyğun deyil (DB-03).
- Settings whitelist tələsi (AD-04) — hər yeni ayar üçün təkrarlanacaq.
- Lock faylsız asılılıqlar, host-da build, staging yoxluğu (AD-05/06/19).
- Audit izində boşluqlar və zəif identifikatorlar (DB-07); retention siyasəti yoxdur (DB-12).
- JS test icrası yoxdur; zaman/race testləri nazikdir.
- 600-sətir limitinə "söykənən" 34 fayl; 505 geniş `except`; ölü kod (appeals state machine, köhnə Dockerfile).

## 27. Scores

| Sahə | Bal | Qısa əsaslandırma |
|---|---:|---|
| Architecture | 77/100 | 4 yaşıl qapı, public fasadlar; 13 gizli runtime dövr, `accounts` hub |
| Backend | 77/100 | İntizamlı servis qatı; DB-01 səssiz rollback, DB-07 audit boşluqları |
| Frontend | 83/100 | CSP-uyğun, 0 inline icra; 73 `alert()`, JS testsiz |
| Database | 80/100 | Güclü sxem/trigger/RLS; timeout yoxdur (DB-02) |
| Security | 80/100 | OWASP əsasları təmiz; LLM→innerHTML, açar loglarda, decompression bomb |
| Authentication | 73/100 | Parolsuz gizli OTP girişi, hesab-səviyyəli limit yox, 2FA dar |
| Authorization | 76/100 | Server tərəfli; superadmin iki tərifi, TT scope boşluqları |
| Multi-tenancy | 86/100 | NOBYPASSRLS + 17/17 IDOR bloklandı; T-01 bildiriş yayımı |
| Exam System | 70/100 | Güclü taymer/kilid; P0 açar sızması, P1 bitməmiş cəhd qiymətləndirməsi |
| Business Logic | 71/100 | State machine-lər sağlam; 3 P1 + ≈14 P2 bütövlük boşluğu |
| Performance | 82/100 | Bütün səhifələr miqyasa sabit; qabıq sorğuları çox |
| Scalability | 64/100 | ≈1k rahat; backpressure yox; 10k tək hostda mümkün deyil |
| Reliability | 68/100 | Celery dizaynı sağlam; səssiz itki yolu, timeout yox, yük atma yox |
| UX/UI | 77/100 | ems_ui geniş; alert() xəta UX-i, paralel stil sistemləri |
| Accessibility | 76/100 | Əsas qoruyucular var; kontrast/etiket qalıqları |
| Testing | 75/100 | 9 155 test, shard CI; JS/race/zaman boşluqları, coverage `main`-də yox |
| Code Quality | 80/100 | Lint təmiz; geniş except, ölü kod |
| DevOps | 72/100 | Rollback/SHA; host build, pinsiz dep, gate-siz release |
| Monitoring | 70/100 | Əsas alert-lər var; DB səviyyəsi kor |
| Backup/Recovery | 45/100 | Off-site yox, bərpa təlimatı zərərli |
| Internationalization | 76/100 | Qapı yaşıl, 1 060 düzəliş; şifrə bərpası/qeydiyyat qalıqları |
| Maintainability | 74/100 | Limit tətbiq olunur, amma whitelist və runtime dövrlər xərci artırır |
| **Orta** | **74/100** | (əlavə: API 79, Privacy 68, Configuration 74, Concurrency 82) |

## 28. P0 Critical Issues

**EX28-01 — Variant id-ləri END_QUESTION idxalında düzgün cavabı açır.**
- **Yer:** `apps/exams/services/parsing/_core.py:258-262`; `views/teacher/question_bank/_views_misc.py:357-371`;
  `templates/exams/student/take_exam.html:241,256` (`value="{{ opt.id }}"`); `services/randomizer.py:60-76`.
- **Sübut:** müəllim real saxlama view-u ilə 8 sual idxal edir, tələbə `take_exam` açır → **8/8** sualda ən kiçik radio
  `value` düzgün variantdır (göstərmə sırası isə düzgün variantı yalnız 2/8 dəfə birinci qoyub).
- **Kök səbəb:** ardıcıl PK cavab dəyəri kimi işlədilir; yaradılma sırası = müəllifin A→E sırası.
- **Düzəliş:** (1) hər cəhd üçün qeyri-şəffaf token (deterministik qarışdırmanın indeksi və ya
  `salted_hmac(attempt, option)`), serverdə geri çevirmə — artıq idxal olunmuş bankları da qoruyur; (2) bütün yaradılma
  yollarında `bulk_create`-dən əvvəl qarışdırma; (3) reqressiya testi.
- **Səy:** Orta. **Prioritet:** növbəti test imtahanından əvvəl.

## 29. P1 High-Priority Issues

| ID | Problem | Tövsiyə | Səy |
|---|---|---|---|
| AD-01 | Off-site/şifrəli/media backup yoxdur | rclone/restic ilə şifrəli off-site sync + media snapshot + təzəlik metrikası; istəyə görə WAL/PITR | Orta |
| AD-02 | Bərpa təlimatı məlumatı korlayır | Yeni bazaya bərpa (`ON_ERROR_STOP`), düzgün servis adları, aylıq `restore_drill.sh`, RTO qeydi | Kiçik |
| AD-03 | Sandbox PG `0.0.0.0` + defolt parol + prod surətləri | `127.0.0.1:` bind, parolu məcburi et, köhnə surətləri sil, firewall-u aç, dump-lara `chmod 600` | Kiçik (sahib) |
| EX28-02 | Bitməmiş cəhdin qiymətləndirilməsi | `is_finished` yoxlaması qiymətləndirmə və jurnal sinxronunda; açıq sətirlərdə «Yoxla»-nı gizlət | Kiçik |
| EXA-01 | Apellyasiya rəsmi balı regressiya edir | Sonrakı rəsmi cəhd varsa köhnəni sinxronlaşdırma (və ya həmişə sonuncunu) + `source_attempt_id` | Kiçik |
| SYL-1 | Öz sillabusunu təsdiqləmə | `forbid_author` approve/revise/reject üçün, dekana yönləndir | Kiçik |
| S1 | Xaric/məzuniyyət tələbəsi qeydiyyatda qalır | Status dəyişəndə cari dövr qeydiyyatlarını `suspended`-ə keçir (bərpada qaytar); göstərmə qaydasını sahib təsdiqləsin | Orta |
| SV-1 | Sorğu anonimliyinin fərq üsulu ilə pozulması | Fakültə/kafedra filtrlərini "daraldıcı" say, valideyn−uşaq ≥ k qaydası, sayları yuvarlaqlaşdır | Orta |

## 30. P2 Medium Issues

**Təhlükəsizlik və autentifikasiya:** SA-01/02 (JSON OTP marşrutları), SA-03 (hesab səviyyəli limit), SA-04 (superadmin
predikatı — prod sayını yoxla), SA-05 (live-exam escape), SA-06 (API açarı başlıqda + sanitizer), SF-1 (decompression
cap), TT-1 (sahib qərarı), SV-2/SV-3 (sorğu), T-01 (bildiriş yayımı).

**İmtahan:** EX28-03 (açar siyasəti — sahib qərarı), EX28-04 (sweep/GET-də güzəşt), EX28-05 (flag-dan əvvəl), EX28-06,
EX28-10.

**Biznes məntiqi:** SYL-2/3/4, J-01, J-02, EXA-02/03/04, S2, S3/S4, W1–W4.

**Baza, etibarlılıq, DevOps:** DB-01 (**birinci**), DB-02, DB-03, DB-07, AD-04, AD-05, AD-06, AD-07, AD-08.

**Keyfiyyət:** FQ-I18N-1/2/3, FQ-TEST-1.

## 31. P3 Improvements

- **Təhlükəsizlik:** SA-07/08/09/10, TT-2..5, SF-2/3, SV-4/5.
- **Tenant:** T-02..05, FORCE RLS iki evidence cədvəlində.
- **İmtahan və axınlar:** EX28-07/08/09/11 + qeydlər, J-03..09, EXA-05..08, SYL-5..7, W5/W6, S5.
- **Baza və performans:** DB-08..13, LessonMark indeks təmizliyi.
- **İnfra:** AD-09..19.
- **Frontend və a11y:** FQ-FE-1..6, FQ-A11Y-1..3, FQ-I18N-4, FQ-TEST-2.

## 32. Production Readiness Assessment

| Ölçü | Vəziyyət | Qısa |
|---|---|---|
| Security | 🟡 | OWASP əsasları təmiz; gizli OTP girişi, API açarı loglarda |
| Data integrity | 🔴→🟡 | P0 açar sızması, apellyasiya/qiymətləndirmə regressiyası, səssiz rollback yolu |
| Performance | 🟢 | Səhifələr miqyasa sabit |
| Scalability | 🟡 | ≈1k rahat; 5k üçün replika/RAM planı, backpressure lazımdır |
| Reliability | 🟡 | Timeout yoxdur, yük atma yoxdur |
| Observability | 🟡 | DB səviyyəsi kor |
| Testing | 🟢/🟡 | Böyük dəst; JS/race boşluqları |
| Backup | 🔴 | Off-site yoxdur, bərpa təlimatı zərərli |
| Deployment | 🟢/🟡 | Rollback var; host build, gate-siz release |
| Operational readiness | 🟡 | Runbook-lar qismən səhv, staging yoxdur |

**Nəticə:** hazırkı yük (bir universitet, ≈1k eyni-anlı) üçün sistem **işləkdir və idarə olunandır**. İstifadəni
genişləndirməzdən **əvvəl mütləq**:
- EX28-01;
- AD-01 + AD-02 (off-site backup + düzgün bərpa təlimatı və bir real məşq);
- EX28-02 və EXA-01;
- DB-01.

5k+ eyni-anlı hədəf üçün əlavə olaraq DB-02, DB-03 və replika/RAM planı lazımdır.

**Yoxlama nəticəsi (bu audit zamanı):** tam dəst sandbox bazasında (`-n 8`) — **10 317 keçdi, 224 ötürüldü, 1 düşdü**
(15 dəq 52 s). Düşən test bu günün yeni `AuditGuardsTest::test_parallel_ai_plan_request_is_refused` idi: test ayarlarında
`DummyCache` olduğu üçün kilid heç vaxt tutulmurdu (kod düzgün, test səhv qurulmuşdu) — `LocMemCache` ilə düzəldildi,
fayl 11/11 keçir.

## 33. Prioritized Remediation Roadmap

| Faza | Prioritet | Problem → Əməl | Asılılıq | Risk | Səy | Fayda |
|---|---|---|---|---|---|---|
| **0 — Təcili** | P0 | EX28-01: per-attempt variant tokenləri + yaradılışda qarışdırma | — | Orta (autosave/OCC xəritələmə testləri) | O | Açar sızması bağlanır |
| 0 | P1 | AD-02: bərpa təlimatını düzəlt + məşq skripti | — | Aşağı | K | Bərpa real olur |
| 0 | P1 | AD-03: sandbox PG loopback + parol + firewall (lokal) | Sahib | Aşağı | K | LAN PII riski bağlanır |
| 0 | P2 | DB-01: grade audit savepoint | — | Çox aşağı | K | Səssiz bal itkisi bağlanır |
| **1 — Təhlükəsizlik və düzgünlük** | P1 | EX28-02, EXA-01 (+EX28-06) | — | Aşağı/Orta | K/O | Rəsmi ballar düzgün |
| 1 | P1 | SYL-1, S1 (sahib göstərmə qaydası) | Sahib | Orta | K/O | 4 göz prinsipi, təmiz jurnallar |
| 1 | P1 | SV-1 (+SV-2/3/4) | — | Aşağı | O | Anonimlik vədi bərpa olunur |
| 1 | P2 | T-01, SA-04 (+sayma sorğusu), SA-01/02, SA-05, SA-06, SF-1 | — | Aşağı | K | Yayım/eskalasiya/sızma yolları bağlanır |
| 1 | P2 | J-01/J-02, SYL-2/3/4, EXA-02/03/04, W1/W2 | EXA-03 üçün memo | Aşağı | K/O | Akademik bütövlük |
| **2 — Performans və baza** | P2 | DB-02 timeouts (DB-01-dən sonra), DB-03 admission control + sənədlər | Staging yük testi | Orta | K/O | Yükdə zərif deqradasiya |
| 2 | P2 | W3 advisory lock → exclusion constraint | — | Orta | O | İkiqat rezervasiya yoxdur |
| 2 | P3 | DB-13 memo, DB-10 bulk grid save, indeks təmizliyi | — | Aşağı | K/O | ≈10% az sorğu |
| **3 — Etibarlılıq və DevOps** | P1 | AD-01 off-site + media backup + alert | Bucket/NAS | Aşağı | O | Host itkisi ≠ məlumat itkisi |
| 3 | P2 | AD-04 settings, AD-05 build-once/GHCR, AD-06 lock faylı, AD-07 release qapısı, DB-08 alert-lər | GHCR token | Orta | K/O | Təkrarlanan, yamalı buraxılışlar |
| 3 | P3 | AD-10..14, AD-19 staging | Server tutumu | Orta | O | Daha təhlükəsiz deploy |
| **4 — Arxitektura və kod** | P2 | AD-08 runtime asılılıq qapısı, organizations↔registrar | — | Aşağı/Yüksək | K/B | E-jurnal ayrılması mümkün olur |
| 4 | P3 | AD-09 `accounts` bölmələrinin sahib app-lərə köçürülməsi, ölü kod, 550-sətir xəbərdarlığı | — | Orta | B | Aşağı dəyişiklik xərci |
| **5 — UX/UI və a11y** | P2 | FQ-I18N-1/2/3 + yoxlayıcı qaydaları | — | Aşağı | K | Düzgün dil auth/qeydiyyatda |
| 5 | P3 | `alert()` → toast, `onclick=confirm` → EMSConfirm, `lang` xəta səhifələrində, kontrast/etiketlər | — | Aşağı | K/O | Ardıcıl, əlçatan UX |
| **6 — Test və sərtləşdirmə** | P2 | FQ-TEST-1 JS icrası / gecəlik Playwright; `time_machine`; race testləri; coverage `main`-də | CI dəqiqələri | Aşağı | O | Reqressiyalar erkən tutulur |
| 6 | — | Hər bağlanan tapıntı üçün `test_audit_2026_09_28_*` reqressiya testi; yük testi (staging) | — | — | O | Yekun yoxlama |

(K = Kiçik, O = Orta, B = Böyük)

## 34. Final Technical Conclusion

EMSArena texniki cəhətdən **yetkin, yaxşı idarə olunan modul monolitdir**: tenant izolyasiyası iki qatlıdır və bugünkü
yeni kodda belə 17/17 IDOR cəhdini dayandırdı; akademik yazılar kilidli və audit olunur; CI qapıları, deploy rollback-i
və əvvəlki auditin düzəlişləri real və sübutludur. Zəif nöqtələr kod keyfiyyətində deyil, iki yerdə cəmləşib:
**(1) akademik bütövlüyün kənar halları** — imtahan açarının id vasitəsilə sızması (P0), cəhdlər/apellyasiya arasında
"son yazan qalib" məntiqi, müəllif-təsdiqləyici ayrılığı, status dəyişikliyinin qeydiyyatlara yayılmaması; və
**(2) əməliyyat dözümlülüyü** — off-site backup-ın yoxluğu, bərpa təlimatının zərərli olması, DB timeout-larının və
yük atmanın olmaması. Birinci qrup əsasən kiçik, test-örtüklü düzəlişlərdir; ikinci qrup sahib səviyyəsində
infrastruktur qərarları tələb edir. Faza 0–1 bağlandıqdan sonra sistem hazırkı universitet üçün tam, yeni
universitetlərə genişlənmə üçün isə Faza 2–3 (timeout, backpressure, off-site backup, build-once) ilə hazır olacaq.
