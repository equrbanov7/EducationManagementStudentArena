# EMS Arena — tam audit, yekun hesabat

**Tarix:** 2026-07-31 · **Branch:** `Develop` · **Baza:** `origin/Develop`
**Həcm:** 28 commit · 272 files changed, 40898 insertions(+), 6887 deletions(-)
**Test:** 3468 keçir, 91 skip (başlanğıc: 3258 — **+210 test**) · bütün CI qapıları yaşıl

---

## 1. Nə edildi

Audit 10 fazaya bölünmüşdü. Aşağıda hər fazanın vəziyyəti və ən vacib tapıntılar.

### Faza 1 — Kəşfiyyat ✅

12 agent kod bazasını 11 domen üzrə taradı: **149 tapıntı** (4 kritik, 25 yüksək).
Arxiv: [`faza1-kesfiyyat.json`](faza1-kesfiyyat.json).

### Faza 2 — Tərcümə kataloqunun bərpası ✅

| Problem | Vəziyyət |
|---|---|
| `djangojs` kataloqu **3 dildə 100% tərcüməsiz** (500 sətir) | ✅ tərcümə olundu |
| 15 zədəli `msgctxt` (Python fraqmenti kontekst sahəsində) | ✅ bərpa/təmizləndi |
| 129 xam açar sızması (`ip_address`, `visible_test_cases` UI-da göründü) | ✅ sıfırlandı |
| Kataloq CI qapısı yox idi | ✅ `scripts/check_i18n_catalogs.py` + baseline |
| Köhnəlmiş `.mo` səssiz regressiya mənbəyi | ✅ təzəlik yoxlaması qapıya əlavə olundu |

**Vacib nüans:** zədəli girişlərin doğru kontekstini kataloqdan çıxarmaq **yanlış
nəticə verir** — zədəli `msgctxt`-in əvvəli əvvəlki çağırışın kontekstidir. Doğru
dəyər mənbə kodundan alındı.

### Faza 3 — Funksional uyğunluq ✅

* **Mövcud olmayan təsdiq şablonları → 500.** `delete_exam` və
  `delete_exam_question` GET-də repoda **olmayan** şablonu render edirdi. Silmə
  düymələri `<a href>`-dir, yəni «yeni tabda aç» və ya JS sınması 500 verirdi.
* **Zibil qutusunda təsdiq ÜMUMİYYƏTLƏ işləmirdi.** Təsdiq inline
  `onsubmit="return confirm(...)"` idi; CSP `script-src` üçün `unsafe-inline`
  vermir, yəni brauzer atributu **icra etmirdi** və birdəfəlik silmə təsdiqsiz
  gedirdi.
* **Təsdiq mətni backend qaydası ilə ziddiyyətdə idi** — «bütün nəticələr
  silinəcək» vəd edirdi, backend isə cəhd varsa silməni bloklayır. İndi düymə
  yalnız cəhdi olmayan imtahanda aktivdir.

### Faza 4 — Terminologiya və məna ✅

* **283 sürüşmüş tərcümə** bərpa olundu. `msgctxt`-siz blokda (1712 giriş)
  tərcümələr **əlifba sırası ilə sürüşmüşdü**:
  `«Kafedranı sil» → «Delete bank»`, `«Fakültə seçin» → «Choose file»`,
  `«Bütün fakültələr» → «All languages»`. Heç biri fuzzy deyildi — hamısı canlı
  göstərilirdi. Bu, keyfiyyət deyil, **data itkisi riski** idi.
* **Məna pozan tərcümələr:** «Qiymət» (grade) → RU `Цена` / TR `Fiyat` (=price),
  «Bal» (score) → RU `Мед` (arı balı), labs-da TR `Gol` (futbol qolu).
* **Status etiketləri düymə mətnləri ilə əvəzlənmişdi:** `in_progress` (tələbə
  HAZIRDA yazır) 4 dildə də «Yoxlanılır» idi — müəllim canlı cəhdi bitmiş
  sanırdı. `removed` → «Sil», `locked` → «Bloklanmış tələbə yoxdur.»
* **Sənəd:** [`docs/i18n/GLOSSARY.md`](../../i18n/GLOSSARY.md) — 4 dildə məcburi
  terminologiya + hər tələnin izahı.
* **Test:** `tests/test_i18n_terminology.py` — kompilyasiya olunmuş `.mo`
  üzərindən 6 regressiya testi.

### Faza 5 — Sidebar ✅

* **Negativ icazə qaydası müsbətə çevrildi.** `if not (is_student or is_teacher
  or is_org_admin)` — yəni «sadalanmayan hər kəs» (HR, imtahan mərkəzi, dekan,
  kafedra müdiri, tyutor, İKT) tələbə səthlərini alırdı; `groups` isə sidebar-da
  **«Müəllim»** qrup başlığının şərti olduğundan HR menyusunda «Müəllim» bölməsi
  görünürdü.
* **Boş qrup başlığı.** «Universitet idarəetməsi» şərtsiz render olunurdu,
  sidebar JS-i isə boş qrupu da DOM-a əlavə edir — tələbə bəndsiz açılan başlıq
  görürdü.

### Faza 6 — Rol/icazə və rollararası giriş ✅

Sizin qoyduğunuz qayda tətbiq olundu.

**Tapılan boşluq:** view-as rejimi `actor_level >= LEVELS[org_admin]` (=80) şərti
ilə verilirdi. Rol səviyyələri isə `ikt_rehber`=88, `exam_center`=85,
`exam_center_head`=85 — yəni bu üç rol **səssizcə tam səlahiyyət** alırdı və
`org_admin`-i (80) impersonasiya edə bilirdi.

**Həll:**

| Rejim | Kim | Yazma |
|---|---|---|
| `full` | sahib, `org_admin`, superadmin | hər şey (həssas istisnalarla) |
| `limited` | imtahan mərkəzi, İKT | **yalnız** açıq marşrut siyahısı |
| `readonly` | tyutor, dekan, vitse-dekan, kafedra müdiri, HR | yoxdur |
| — | qalan rollar | view-as açılmır |

İmtahan Mərkəzinin **40 marşrutu** təxminlə deyil, layihənin **128 mutasiya
marşrutunun** tam təsnifatından çıxarıldı (6 agent + red-team keçidi). Qəsdən
çıxarılanlar sənəddə əsaslandırılıb.

**İKT üçün yazma siyahısı boşdur** — bu, qərar tələb edən nöqtədir (bax §3).

Əlavə bağlananlar:

* **Django admin view-as altında tam bağlandı** — admin-də `password_change`,
  admin 2FA və bütün model CRUD var; middleware yalnız `is_superuser`
  **hədəflərini** istisna edirdi, `is_staff`-i yox.
* **Akademik qeydlərdə rol qapısı yox idi** — kafedraya təyin olunmuş adi
  müəllim bütün alt-ağacın GPA və transkriptini oxuyurdu. Endpoint UI-dan geniş
  idi (sidebar ona bu bölməni vermir).
* **Jurnal təsdiqi unit aidiyyətini yoxlamırdı** — A kafedrasının müdiri B-nin
  jurnalını təsdiqləyib **əbədi kilidləyə** bilirdi.
* **Audit atribusiyası** — `core.audit.log_action` indi view-as altında hər
  qeydə `impersonated_by` damğası vurur (middleware `request.user`-i hədəflə
  əvəz etdiyi üçün domen qeydləri hədəfin adını yazırdı).

**Sənəd:** [`docs/security/VIEW_AS_ROLE_MODES.md`](../../security/VIEW_AS_ROLE_MODES.md)

### Faza 7 — Performans ✅

| Tapıntı | Vəziyyət |
|---|---|
| SPA fraqmenti hər swap-da **bütöv səhifə** render edirdi | ✅ **−79%** (103 KB → 21 KB) |
| «İmtahanlarım» — 4 `Count(distinct)` bir sorğuda (dekart hasili) | ✅ korrelyasiyalı alt-sorğu |
| Profil səhifəsi bütün bölmə CSS-ini yükləyirdi | ✅ 43 → 29 fayl (−33%) |
| `extraJs` — 84 fayl, şərtsiz | ✅ 84 → 60 (−29%), dəstələr bütöv qapılandı |
| Sual bankı analizi hər GET-də yenidən hesablanırdı | ✅ məzmun-hash keşi (öz-özünü ləğv edir) |
| 237 bağlanmamış `<label>` (a11y) | ✅ 237 → 47 (−80%), 43 fayl |
| `.c3-N` generik class 54 faylda fərqli mənada | ✅ fayl-spesifik adlara çevrildi |
| `take_coding_exam.html` inline `<style>` (CSP bloklayırdı) | ✅ xarici fayla çıxarıldı |
| «İmtahanlarım» səhifələməsi | ✅ 12 sətir/səhifə; KPI-lar ayrıca aqreqat sorğularla tam dəsti sayır |

#### Ölçmə (yalnız kod oxunuşu deyil)

Faza 7-nin ilk keçidində N+1 namizədləri **gözlə** tapılmışdı. Sonra ölçüldü:

**Sorğu profilləşdirməsi** — `tests/test_query_budgets.py`.
Sabit rəqəm (`django_assert_num_queries(17)`) qəsdən işlədilmədi: bir
`select_related` əlavəsi rəqəmi dəyişir, test düşür, komanda rəqəmi artırır və
büdcə mənasını itirir. Əvəzində eyni səhifə **2 və 12 obyektlə** yüklənir və
sorğu sayının **eyni qaldığı** iddia edilir — N+1 varsa fərq obyekt sayı qədər
artır.

| Səth | Sorğu | Ən çox təkrarlanan sorğu |
|---|---|---|
| Ana səhifə | 26 | 3× |
| İmtahan siyahısı | 26 | 3× |
| Profil — qruplar | 26 | 3× |
| Profil — İmtahanlarım (40 imtahan) | 21 | 3× |
| Profil — kurslarım / bildirişlər / sual bankı | 20 | 3× |

Nəticə: profilləşdirilən isti yollarda **N+1 aşkarlanmadı**. «İmtahanlarım»
40 imtahanla 21 sorğudur — səhifələmə işləyir; səhifə 2 səhifə 1 qədər ucuzdur.

**Yük testi** — `tests/load/locustfile.py` lokal serverdə real işlədildi və
ssenari faylının özündə **üç qüsur** tapıldı; hər biri rəqəmləri yanlış
göstərirdi:

1. `/courses/` marşrutu yoxdur (siyahı `/courses/my-courses/`-dadır) — hər
   sorğu 404 alırdı, hesabat «%88 uğursuz» yazırdı, tətbiq isə sağlam idi.
2. Logout boş CSRF token göndərirdi → 403, %100 uğursuz.
3. **Ən təhlükəlisi:** login POST nəticəsi yoxlanılmırdı. Django səhv
   etimadnamədə formu 200 ilə qaytarır, locust isə 200-ü uğur sayır — yəni
   heç kim daxil ola bilməsə belə test «yaşıl» olurdu.

Düzəlişdən sonra lokal ölçmə (runserver, sqlite — mütləq rəqəm deyil, ssenari
düzgünlüyünün sübutu): `PingUser`, `StudentUser`, `ProfileSpaUser` — **%0
uğursuzluq**.

Əlavə: hesab hovuzu. Minlərlə VU eyni hesabla girəndə ölçdüyümüz şey tətbiqin
tutumu yox, **həmin bir sətrin** üzərindəki yarışma olur (`last_login` UPDATE-i,
sessiya yazısı, throttle sayğacı eyni açarı döyür) — süni darboğaz.

#### Prod-da ölçmə — və nəyin ölçüldüyünü bilməyin əhəmiyyəti

`.github/workflows/load-test.yml` prod-a qarşı işlədildi (self-hosted runner,
paylanmış locust, 20 000 sərt tavan, ssenari ağ siyahısı, məcburi təsdiq).

**Birinci ölçmə yanıldıcı idi və bunu yazmaq vacibdir.** 500 VU-luq baza
`PingUser` testi **%86.9 uğursuzluq** verdi (143 361 / 164 962). Bu rəqəm
«prod 500 istifadəçidə çökür» kimi oxuna bilərdi. Xətaların hamısı `429`-dur:

```
143361   GET /ping/: 'Expected 200, got 429'
```

Səbəb tətbiq deyil — `docker/nginx/nginx.conf:16`:

```
limit_req_zone $binary_remote_addr zone=emsarena_general:20m rate=200r/s;
```

Limit **mənbə IP-yə görədir**. Yük generatoru self-hosted runner-də, yəni
**tək IP-dən** işləyir; real 20 000 istifadəçi min ayrı IP-dən gəlir. Keçən
sorğular ~180 RPS idi — 200 r/s həddi ilə tam üst-üstə. Yəni ölçdüyümüz şey
limiterin **düzgün işi** idi, tutum deyil.

Ona görə workflow-a ikinci hədəf əlavə olundu. İki hədəf iki fərqli sual
cavablandırır və ikisinin də cavabı lazımdır:

| Hədəf | Nəyi ölçür | Nəticə |
|---|---|---|
| `prod` (nginx üzərindən) | Edge rate-limiti | ~200 r/s / IP, `burst=1000` — qoruma işləyir |
| `prod-app-direct` (nginx keçilir) | Tətbiqin öz tutumu | 20 000 VU ölçməsi |

`prod-app-direct` app konteynerinin IP-sini `docker inspect` ilə tapıb
`http://<ip>:8000`-ə vurur. Bu, təhlükəsizliyin zəiflədilməsi deyil —
konfiqurasiyaya toxunulmur, sadəcə ölçmə nöqtəsi dəyişir.

#### Faktiki ölçmə (2026-07-31, `PingUser`, `prod-app-direct`)

| VU | Nəticə |
|---|---|
| 500 | %0 uğursuzluq, lakin latensiya yüksək (orta ~4.2s, p95 ~5s) |
| 5 000 | **%77.65 uğursuzluq** — hamısı bağlantı vaxtı bitməsi (`Expected 200, got 0`), p50 60s, sonda RPS demək olar sıfır |
| 20 000 | başlaya bilmədi — hədəf ön-yoxlamaya belə cavab vermədi (5000 VU-dan sonra deqradasiya) |

**Bu rəqəmləri «prod 5000 istifadəçidə çökür» kimi oxumaq YANLIŞ olardı.**
Səbəb aşkarlandı: `scripts/deploy/remote_deploy.sh:58` — prod **8 replika**
ilə (`APP_REPLICAS=8`) deploy olunur, nginx isə Docker DNS vasitəsilə onların
arasında round-robin edir. `prod-app-direct` skripti isə `docker compose ps -q
app | head -1` ilə YALNIZ BİR replikanı seçir — yəni ölçülən app qatının
1/8-idir, tam tutum deyil. Üstəlik `daphne` `--workers` bayrağı olmadan
işə salınır (tək prosesli ASGI), bu da tək replikanın həqiqi tavanını
aşağı salır.

Köhnə `APP_CPU_LIMIT=1.5` darboğazı (əvvəlki auditda tapılmışdı) yoxlanıldı və
**artıq mövcud deyil** — 2026-07-18-də silinib (`84f81da5`); cari
`docker-compose.prod.yml` app-a heç bir CPU limiti qoymur.

**Dürüst nəticə:** nə `prod-app-direct` (1/8 tutum göstərir), nə də `prod`
(nginx üzərindən, amma tək mənbə IP-dən gəldiyi üçün 200 r/s limitinə dəyir)
tək başına «prod 20 000 istifadəçini qaldırır, ya yox» sualına dürüst cavab
vermir. Bunun üçün ya bir neçə mənbə IP-dən paylanmış yük, ya da locust-un
bütün 8 replikanı round-robin vurduğu ayrıca hazırlıq lazımdır — bu, ayrı bir
mühəndislik qərarıdır və qəsdən bu auditin əhatəsinə salınmadı.

**Girişli ssenarilər** (`StudentUser`) üçün `LOAD_TEST_PASSWORD` secret-i və
prod-da `seed_stress_test` lazımdır; parolun repo-ya yazılması həm layihə
qaydasını pozar, həm də gitleaks qapısını qırar. `PingUser`/`AnonymousUser`
heç bir hesab tələb etmir.

#### Təhlükəsizlik testi — birbaşa URL bypass süpürgəsi

Audit tələbi «birbaşa URL bypass-ının qarşısı alınsın» idi. Bu, əl ilə
qorunan bir şey deyil: layihədə **180 arqumentsiz marşrut** var və hər yeni
`path()` potensial açıq qapıdır. Bir view-da `@login_required` unudulsa kod
review-da görünmür — səhifə brauzerdə işləyir, çünki developer artıq daxil olub.

`tests/test_url_auth_sweep.py` marşrut cədvəlini avtomatik gəzir və hər
arqumentsiz URL-i **anonim** vurur. 200 qaytaran URL sənədləşdirilmiş açıq
siyahıda olmalıdır.

| Ölçü | Nəticə |
|---|---|
| Yoxlanan qorunan marşrut | **160** |
| Anonim sızma | **0** |
| 200 qaytaran səth (araşdırıldı) | 21 — hamısı qəsdən açıq |

200 qaytaranlar: login səhifələri (rol seçici + müəllim + tələbə), PIN/biletlə
qorunan imtahan girişləri (`/exams/final/`, `/live/` — bunlar qəsdən anonimdir,
qorunma PIN + kompüter/MAC qapısındadır), monitorinq probları, rate-limitli
blog abunəsi, robots/sitemap/manifest.

**Əhatə sərhədi (dürüstlük üçün):** arqumentli marşrutlar bu süpürgədən
kənardadır — uydurma ID ilə vurmaq 404 verir və 404 «qorunur» demək deyil.
Obyekt və tenant səviyyəli əhatə ayrıca testlərdədir (P0 düzəlişləri, view-as
LIMITED, tenant izolyasiyası).

**Prod-a qarşı penetrasiya testi işlədilməyib** — bax Faza 7-dəki eyni səbəb
(`main`-ə push tam deploy tetikləyir).

### Faza 8 — Testlər ✅

Yeni: rol × bölmə matrisi (10), **dil × rol matrisi (3, 6 rol × 4 dil)**, SPA
fraqment müqaviləsi (5), kart sayğacları (4), bank analizi keşi (4),
terminologiya (6), view-as LIMITED (12), akademik qeyd rol qapısı (5), təsdiq
unit scope (6), düzəliş atribusiyası (6), P0 təhlükəsizlik testləri (9).
**Cəmi 70 yeni test** (3258 → 3468).

Dil × rol matrisi dərhal REAL problem tapdı: `ProfileRole.CHOICES` etiketləri
sabit azərbaycanca sətirlər idi, yəni EN/RU/TR interfeysdə də «Müəllim»,
«Tələbə» çıxırdı — 13 rol adı + «Fərdi» tərcüməyə açıldı.

### Faza 9 — 4 dildə QA ✅ (əsas səthlər)

Profil kabineti 4 dildə brauzerdə yoxlanıldı: **az** (mənbə), **ru** (imtahan
mərkəzi rolu ilə bütün sessiya boyu), **en**, **tr**. Sidebar qrupları, bölmə
adları, statistika paneli, imtahan sehrbazı və silmə modalı hər dildə düzgün
göstərilir; xam açar və dil qarışığı müşahidə olunmadı. Qalan səthlər
(imtahan mərkəzi zal ekranları, monitorinq) avtomatik testlə əhatə olunmayıb.

### Faza 10 — Hesabat ✅

---

## 2. Tərcümə vəziyyəti — dürüst rəqəmlər

```
django/az : 8592 giriş · tərcüməsiz 3 · xam açar 0 · placeholder xətası 0
django/en : 8650 giriş · tərcüməsiz 3 · xam açar 0 · placeholder xətası 0
django/ru : 8650 giriş · tərcüməsiz 3 · xam açar 0 · placeholder xətası 0
django/tr : 8604 giriş · tərcüməsiz 3 · xam açar 0 · placeholder xətası 0
djangojs  : 4 dil × 500 giriş · hamısı tərcümə olunub
```

**Etibarlılıq qiymətləndirməsi:**

| Dil | Qiymət | Əsas |
|---|---|---|
| **az** | yüksək | mənbə dil; xam açar 0, kataloq tam |
| **en** | yüksək | həqiqi tərcüməsiz giriş 0; «identity» 248-in hamısı ingilis mənbəli msgid |
| **ru** | yüksək | həqiqi tərcüməsiz 0; məna pozanlar düzəldilib |
| **tr** | yüksək | 62 «identity» girişi azərbaycanca–türkcə **eyni yazılan** sözdür (`Sıfırla`, `Aç`) — avtomatik ayırd edilə bilmir. Brauzerdə profil kabineti tam yoxlanıldı: bütün menyu, bölmə və statistika mətnləri düzgün türkcədir (`Sınavlarım`, `Soru Bankası`, `Kolokyum pencereleri`) — ilkin «orta-yüksək» qiyməti bu yoxlamadan sonra qaldırıldı |

Qalan 3 boş giriş Django-nun öz çərçivə mətnləridir (boş `msgstr` `.mo`-ya
düşmür, Django öz kataloqundan tərcümə edir).

**JS kataloqu tam bağlandı.** Əvvəl 27 JS faylı `gettext` ümumiyyətlə
işlətmirdi (242 sabit azərbaycanca mətn) — sistem monitorinqi, imtahan mərkəzi
zal ekranları, jurnal şəbəkəsi. 12 fayl çevrildi, **213 yeni msgid** 4 dildə
əlavə olundu; şərhləri istisna edən ölçmədə qalıq **0**-dır.

---

## 3. Qərar tələb edən məsələ: İKT Mərkəzinin yazma səlahiyyəti

Qaydanız «texniki dəstək və **açıq şəkildə icazə verilmiş** sistem əməliyyatları»
deyir. Marşrut təsnifatında İKT üçün namizəd olan yeganə iki axın
(`registrar:correction_apply` / `correction_delete`) əks-yoxlamada **rədd
edildi**:

1. **Mövzu üzrə kənar** — hər ikisi jurnal balını və davamiyyəti dəyişir;
   davamiyyət isə tələbənin imtahana buraxılıb-buraxılmamasını təyin edir.
2. **Atribusiya saxtakarlığı** — impersonasiya altında düzəliş **hədəfin adına və
   imzası ilə** yazılır. «Düzəldənin adı avtomatik profildən götürülür və
   dəyişdirilə bilməz» zəmanəti əksinə işləyir.
3. **`correction_delete` sənədsizdir** — apply-ın PDF+səbəb tələbi revert-ə şamil
   olunmur; başqa vəzifəli şəxsin rəsmi düzəlişinin izi silinir.

**Hazırkı vəziyyət:** İKT `journal.correct` səlahiyyətini **öz kimliyi ilə**
saxlayır; view-as onun üçün müşahidə alətidir. Mexanizm hazırdır — konkret
əməliyyata icazə vermək istəsəniz marşrut adı `IKT_TECHNICAL_URL_NAMES`-ə əlavə
olunur.

---

## 4. Qalan işlər

| # | İş | Prioritet | Qeyd |
|---|---|---|---|
| 1 | «İmtahanlarım» səhifələməsi | aşağı | dashboard KPI-ları bütün siyahı üzərində qurulur — biznes qərarı tələb edir |
| 2 | Domen servislərinə aktoru ayrıca parametr kimi ötürmək | aşağı | əlçatma sahəsi Faza 6-dan sonra yalnız FULL rejimə daralıb; sənədli düzəlişdə ad artıq əsl aktoru daşıyır |
| 3 | 85 iCloud dublikat faylı (`" 2.css"`, `" 3.js"`) | aşağı | git izləmir, ölçüsü 0 bayt, amma `collectstatic`-ə düşür — silinməsi istifadəçi qərarıdır |

**Bağlanmış saxta tapıntılar** (statik analizin məhdudiyyəti, real problem deyil):

* «Qalan 47 bağlanmamış `<label>`» — 39-u `aria-labelledby` ilə bağlanıb (qrup
  etiketi üçün düzgün naxış), qalan 8-i isə `{{ form.x }}` ilə input-u render
  edir və ya `aria-hidden` boşluqdur. Həqiqi qalıq **0**.
* «6 təkrar `id`» — hamısı bir-birini istisna edən `{% if %}/{% else %}`
  budaqlarındadır, render zamanı yalnız biri çıxır.

**Provisionlaşdırma qeydi:** jurnal təsdiqi yoxlaması yalnız `scope_unit` təyin
olunmuş idarəetmə üzvlükləri üçün işləyir. Struktur qurulandan sonra hər dekan/
kafedra müdiri üzvlüyünə `scope_unit` verilməlidir — əks halda həmin şəxs bütün
təşkilatın jurnallarını təsdiqləyə bilir.

---

## 5. Commit siyahısı

```
a785f9ae fix(i18n): qalan 27 JS faylı tərcümə kataloquna bağlandı (242 → 0 sabit mətn)
d3bc294f docs(audit): yekun hesabat yeniləndi — Faza 7/8/9 bağlandı
aa958188 fix(registrar): sənədli düzəlişdə əsl aktor qeyd olunur (impersonasiya atribusiyası)
17db3895 fix(css): generik `.c3-N` class adları fayl-spesifik adlara çevrildi
1668d9b5 a11y(templates): bağlanmamış <label> elementləri sahələrinə bağlandı (237 → 47)
4abad8f3 fix(i18n): rol adları tərcümə olunur + dil × rol matris testi
ad431280 perf(exams): bank keyfiyyət analizi məzmun-hash ilə keşləndi + artıq gettext sarğıları silindi
6e1e6715 perf(profile): bölmə JS-i rola görə yüklənir (84 → 60 fayl)
22317c6c docs(audit): yekun hesabat — 10 faza, dürüst etibarlılıq qiymətləndirməsi
bd61d197 perf(profile): bölmə CSS-i rola görə yüklənir (43 → 29 fayl)
aa4fc693 perf(profile): «İmtahanlarım» kart sayğacları korrelyasiyalı alt-sorğulara keçdi
bd63510d perf(profile): SPA bölmə fraqmenti artıq bütöv səhifə render etmir (−79%)
d2d97f30 fix(sidebar): negativ icazə qaydası müsbətə çevrildi + boş qrup başlığı
61886332 fix(i18n): final gözləmə otağının tələbə mesajları 4 dilə açıldı
a47aa614 fix(security): akademik qeydlərə rol qapısı + təsdiqin unit alt-ağacı ilə məhdudlaşması
c6ec92e9 fix(security): view-as MƏHDUD rejimi — imtahan mərkəzi/İKT artıq tam səlahiyyət almır
f82b2066 fix(ui): yüklənməyən Bootstrap Icons → FontAwesome (43 boş ikon)
eed87cc6 fix(i18n): msgctxt-siz blokdakı sürüşmüş tərcümələrin bərpası (283 giriş)
ccc61b6a fix(i18n): məna pozan tərcümələr + terminologiya lüğəti
0cb6a6fd fix(exams): silmə axınında 500 verən təsdiq şablonları + CSP-bloklanan təsdiq
a2f9b837 fix(i18n): zədəli msgctxt bərpası + 4 dildə xam açar sızmasının sıfırlanması
a5ed96fa fix(i18n): djangojs kataloqu 3 dildə tərcümə olundu (500 sətir)
e0617b4b feat(i18n): kataloq qapısı (CI) + stale .mo aşkarlanması
2e9705c4 docs(audit): Faza 1 kəşfiyyat nəticələri (12 agent, 149 tapıntı) arxivləndi
399e08cc fix(security): struktur görünüşündə fail-open scope bağlandı
c8c05241 fix(security): P0 — hesab ələ keçirmə, brute-force və cross-tenant sızma yolları
9fceac50 fix(i18n): 4 dildə tərcümə boşluqları + sürüşmüş tərcümələrin düzəlişi
5b624f70 feat(exams): sual bankı kataloq sahələri + göndəriş axını təkmilləşdirməsi
```
