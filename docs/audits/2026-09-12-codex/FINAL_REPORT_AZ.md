# EMSArena — audit və düzəliş hesabatı

Tarix: 12 sentyabr 2026. Mənbə: `/Users/elvin/Developer/EMSArena`; başlanğıc HEAD: `f6906713`.

## 1. İcra xülasəsi

**Qərar: hazırkı işləyən mühit istehsala hazır kimi təsdiqlənmir.** Mənbədə yarımçıq statistika və bal importu tamamlandı, təhlükəsizlik/bütövlük düzəlişləri və regresiya testləri əlavə edildi. Lakin lokal işləyən image mənbədən geridir, tətbiqin DB hesabı superuser-dir və HTTPS/cookie parametrləri ictimai istehsal üçün uyğun deyil. Uzaq istehsal serverinə giriş və deploy aparılmadı; lokal konteyner barədə tapıntı uzaq serverdə müşahidə kimi təqdim edilmir.

Ümumi texniki qiymət **65,91 → 73,74/100**; işləyən mühitin istehsal hazırlığı **40 → 40/100**. Bunlar mühəndis qiymətləndirmələridir, statistik sertifikat deyil. Kodun düzəlməsi işləyən image-in avtomatik düzəlməsi demək deyil.

Audit bütün funksiyalar üçün tam formal sübut deyil. Əhatə: mənbə inventarı, mövcud testlər, seçilmiş yeni təhlükəsizlik regresiyaları, sintetik brauzer axınları və real bazada yalnız oxu yoxlamaları. Test edilməmiş sahələr aşağıda ayrıca göstərilib.

## 2. Claude-dan qalan işlər

VS Code-da açıq layihə yeni mənbə qovluğu ilə tutuşduruldu. Claude Desktop-da “Qrup və ixtisas filtrləməsi” işi, istifadə limiti və yarımçıq tələbə bölmələri/statistika/bal paneli görüldü. Claude-a mesaj göndərilmədi.

Başlanğıcda statistik metrik paketi və yeni şablon çağırışları var idi, amma çağırılan partial-lar və brauzer JS-i çatışmırdı. Bal importunun backend skeleti var idi; istifadəçi identifikatorlarını səhv modeldən oxuyurdu. Tələbə kartları və bal panelinin əhəmiyyətli hissəsi əvvəlcədən dəyişdirilmişdi. Bunların hamısı bu auditin müəllifliyinə aid edilmir.

`evidence/initial-git-status.txt` ilkin dirty vəziyyəti saxlayır. Monitorinq, Alertmanager və deploy skriptində əvvəlcədən olan dəyişikliklər auditin funksional düzəlişləri kimi göstərilmir. Commit, push və deploy edilmədi.

## 3. Məlumat bütövlüyü

Mövcud `emsarena_db` bazasında yazı, migrasiya, flush, seed və rol dəyişməsi aparılmadı. SQL oxuları `default_transaction_read_only=on` və vaxt limiti ilə icra edildi. Testlər ayrıca `CODEX_TEST_emsarena_pg_20260912` konteynerində və sintetik məlumatla işlədildi. Mövcud bazadan testlərə şəxsi sətirlər köçürülmədi.

| Obyekt | Əvvəl | Sonda |
|---|---:|---:|
| İstifadəçi | 8443 | 8443 |
| Təşkilat | 1 | 1 |
| Akademik qeyd | 7703 | 7703 |
| Fənn qeydiyyatı | 148020 | 148020 |
| Yekun qiymət | 114021 | 114021 |
| Rəqəmsal imtahan cəhdi | 0 | 0 |
| Legacy uyğunluq qeydi | 777901 | 777901 |
| Tətbiq olunmuş migrasiya | 280 | 280 |

Enrollment–offering, final grade–enrollment və membership–role təşkilat uyğunluğu sorğularının hər biri **0 uyğunsuzluq** qaytardı. Bunlar bütün sahələrin sətir-sətir hash müqayisəsi deyil. Sayların eyni qalması təkbaşına hər sahənin dəyişmədiyinə sübut sayılmır; bizim əməliyyatlar mövcud bazaya yazmayıb.

Audit bitdikdə ayrıca test konteyneri silindi, sintetik brauzer sessiyası və test serveri bağlandı; mövcud xidmətlərə toxunulmadı (`evidence/cleanup.json`).

Sübut: `evidence/local-data-counts.txt`, `local-data-counts-final.txt`, `local-db-readonly.txt`.

## 4. Kritik tapıntılar

**P0-01 — tətbiq DB rolu RLS-i yan keçir; açıqdır.** İşləyən tətbiq PgBouncer vasitəsilə `emsarena_user` hesabına qoşulur; hesab `rolsuper=true`, `rolbypassrls=true` daşıyır. FORCE RLS bu rol üçün müdafiə deyil. Bu, faktiki məlumat sızmasının aşkarlandığı iddiası deyil, tenant müdafiəsinin DB qatının işləmədiyinin təsdiqidir.

Mənbədə ayrıca app/migration hesabı üçün dəstək var, amma compose fallback-i köhnə hesabı seçə bilir; yoxlama default `warn`-dır. Mövcud yeganə login rolunu yerində dəyişmək idarəetməni və işləyən tətbiqi poza bilərdi; istifadəçinin baza qoruma tələbinə görə edilmədi. Ayrı NOSUPERUSER/NOBYPASSRLS app hesabı, minimum grant-lar və PgBouncer ilə RLS sınağından sonra planlı keçid tələb olunur.

## 5. Yüksək prioritetli tapıntılar

| ID | Problem və təsir | Vəziyyət |
|---|---|---|
| P1-01 | Statistika çatışmayan partial-lara görə 500 verirdi | Düzəldildi |
| P1-02 | Import `User.fin` kimi mövcud olmayan sahədən identifikasiya oxuyurdu | `UserProfile` üzərindən düzəldildi |
| P1-03 | Paralel ilk bal yazıları əvvəlki balı əvəz edə bilərdi | Enrollment sətri kilidlənir; yarış testi əlavə edildi |
| P1-04 | İdentifikator/FİN ziddiyyəti və username–institusional nömrə toqquşması yanlış tələbəyə yazı riski yaradırdı | Ziddiyyət və qeyri-müəyyən alias rədd edilir; roster sırasından asılı deyil |
| P1-05 | Yeni qrup protokolu mediasında təşkilat icazəsi struktur əhatəsini əvəz edirdi | Qrup/alt-ağac yoxlaması və regresiya əlavə edildi |
| P1-06 | İcazə əhatəsi dəyişdikdən sonra statistika keşi əvvəlki geniş nəticəni saxlaya bilərdi | Əhatə ID-ləri keş açarına əlavə edildi |
| P1-07 | İşləyən image mənbədən və təhlükəsizlik yeniliklərindən geridir | Açıq; deploy edilməyib |
| P1-08 | Lokal production-settings image-də Secure cookie/HTTPS/HSTS söndürülüb | İctimai rollout üçün açıq maneə; uzaq server yoxlanmayıb |

İşləyən image Django **5.2.15**, lokal mənbə/test mühiti **5.2.17** istifadə edir. Django 5.2.17 təhlükəsizlik buraxılışıdır: [rəsmi Django bildirişi](https://www.djangoproject.com/weblog/2026/aug/04/security-releases/). Uyğun yeniləmələrin konkret bu tətbiqdə istismar olunduğu iddia edilmir.

## 6. Orta prioritetli tapıntılar

- **P2-01, düzəldildi:** NaN/Infinity bal girişləri adi validasiya xətasına çevrilir.
- **P2-02, düzəldildi:** CSV/XLSX sətir limiti artıq səssiz truncation etmir; sütun, ZIP genişlənmə və fayl ölçüsü limitləri var.
- **P2-03, düzəldildi:** ixracdakı formula başlanğıcları neytrallaşdırılır; qorunmuş identifikatorların CSV/XLSX geri importu testlə yoxlanır. “Tələbə №” Unicode normallaşdırması və CSV quote seçimi də düzəldildi.
- **P2-04, düzəldildi:** yoxlanmamış yazılı iş nəticə ortalamasına və keçid faizinin məxrəcinə daxil edilmir; “gözləyir” göstərilir.
- **P2-05, düzəldildi:** zal tutumu kompüter JOIN-i ilə çoxalmır; eyni tutumlu iki zal və üç kompüter testi var.
- **P2-06, açıq:** EN/RU ekranlarında yeni AZ mətnlər fallback kimi görünür; kataloq ratchet-in keçməsi tam tərcümə demək deyil.
- **P2-07, açıq:** SQLite/no-migrations bütöv dəst PostgreSQL davranışını əvəz etmir; parser, UUID və trigger fərqləri qalır.
- **P2-08, açıq:** işləyən Redis-də `maxmemory=0`, konteynerdə 512 MiB limit var. Hazırkı istifadə təxminən 2 MiB-dir; OOM müşahidə edilməyib.
- **P2-09, açıq:** yeni bal vərəqinin tenant/offering əlaqəsi servis səviyyəsində qorunur; bütün əlaqələr üçün ayrıca DB trigger attestasiya olunmayıb.
- **P2-10, açıq:** lokal venv-də setuptools 65.5.0 üçün scanner xəbərdarlıqları var; işləyən image-də setuptools 83.0.0-dır. Bu iki mühit qarışdırılmamalıdır.

## 7. Aşağı prioritetli tapıntılar

`AGENTS.md` sıfır tarixi dövr yazsa da real modul baseline-i iki dondurulmuş dövr göstərir. Sənəd köhnəlib; baseline böyüdülmədi. Statistik CSV əvvəlki göndəriş selector-larını ixrac edir; düymə “Göndərişlər (CSV)” adlandırıldı ki, yeni bütün akademik KPI-ların ixracı kimi anlaşılmasın. Standart pyproject pytest konfiqurasiyası setup.cfg-dəki paralel bölməni üstələyir və xəbərdarlıq yaradır.

## 8. Arxitektura qiymətləndirilməsi

Bu layihə Django monolitidir: domen servisləri, tətbiqlər, public fasadlar, Django şablonları və vanilla JS. React/TypeScript tətbiqi kimi qiymətləndirilməyib. Django resolver inventarı **945 route**, app registry **151 model**, sintetik universitetin default konfiqurasiyası **24 rol** göstərir. Route sayı ayrıca API əməliyyatı sayı deyil: admin, include və uyğunluq yolları da daxildir.

Müsbət tərəflər: domen bölgüsü, mərkəzi permission/scope mexanizmi, kiçik modullar üçün ratchet, audit ledger-ləri. Risklər: kabinet kontekstinin böyük koordinasiya səthi, iki tarixi modul dövrü, bəzi dərin domen importları. Yeni bal servisi istehlakı registrar public fasadına keçirildi; yeni dövr yaradılmadı.

Sübut: `django-routes.json`, `django-models.json`, `role-permissions.json`, `final-boundaries.txt`.

## 9. Məlumat bazası

Real lokal bazada 171 public cədvəl, 141 RLS-enabled və 139 FORCE RLS cədvəli görüldü; unvalidated constraint sayı 0 idi. Bu göstəricilər hər biznes invariantının constraint-lə qorunduğu demək deyil. `pg_stat_user_tables` qiymətləndirmələri köhnə göründüyü üçün real saylar ayrıca COUNT ilə alındı.

0071/0072 bal vərəqi migrasiyaları yalnız ayrıca test bazasında tətbiq edildi. `makemigrations --check --dry-run` əlavə model drift-i göstərmədi. Forward/reverse rehearsal sintetik final grade və score entry sətirlərini qorudu; yeni batch metadata cədvəli downgrade zamanı silinir. Real sistemdə məlumat daxil edildikdən sonra bu downgrade istifadə edilməməlidir.

## 10. Legacy migrasiya

777901 uyğunluq qeydi və çoxsaylı rehearsal testləri mövcuddur. Mənbə–hədəf sahə müqavilələri, identifikasiya, qiymət, iştirak, yerləşdirmə və mapping testləri geniş dəstə daxildir.

**Tam real MariaDB mənbə–PostgreSQL hədəf tutuşdurması aparılmayıb.** Beş MariaDB testinin deselect edilməsi ayrıca göstərilir. Mənbə snapshot-ının attestasiya edilmiş bağlantısı olmadan “legacy miqrasiya 100% doğrudur” nəticəsi verilmir. Aggregate saylar və üç tenant sorğusu bunun əvəzi deyil. Eyni qayda dublikatların, bütün FK-ların və bütün keçmiş qiymət komponentlərinin tam təsdiqinə aiddir.

## 11. Təhlükəsizlik

Yoxlanan konkret vektorlar: tenant/scope girişləri, media protokolu, yanlış identifikator, səhv UUID, mənfi/qeyri-sonlu bal, təkrar import, sənədsiz düzəliş, CSV formula və sıxılmış XLSX ölçüsü. Server icazə yoxlaması brauzer düyməsinin görünməsindən asılı deyil; tətbiq zamanı fayl yenidən yoxlanır.

Dependency scanner lokal venv üzrə bir paketdə səkkiz xəbərdarlıq qeydi qaytardı; onlar **dörd unikal advisory ID**-yə uyğun gəlir. Lokal setuptools üçün düzəliş versiyaları scanner JSON-da saxlanır. Bu auditdə venv paketləri kor-koranə upgrade edilmədi. Scanner ayrıca `/tmp` mühitində quruldu. Mənbədə sabitlənmiş Django versiyası yoxlandı; Bandit high severity/high confidence skanında apps/core/config üzrə 0 tapıntı çıxdı; bu bütün zəifliklərin yoxluğu demək deyil. Tam container OS CVE scan və exploit pentest aparılmadı.

Sessiya/OTP/CSRF üzrə mövcud avtomatik testlər var. Real email, AI provider, xarici audit/alert çatdırılması sınağı göndərilmədi. Autentifikasiyalı kabinetdə Clarity aktiv görünür; şəxsi məlumat maskalanması və saxlanma siyasəti ayrıca yoxlanmalıdır. Sintetik brauzer mühitində bu telemetriya söndürüldü.

## 12. Rollar, icazələr və tenant izolyasiyası

24 default rol üçün 665 görünən kabinet keçidi 200 qaytardı. Bu, boş/sintetik scope ilə səhifə-açılma matrisidir; hər rolun bütün yazı səlahiyyətlərinin əl ilə sübutu deyil. Mənfi girişlər ayrıca servis/integration testləri ilə yoxlanır.

Tələbə və adi müəllim bal importu endpoint-lərindən 403 alır. Başqa tenantın açılışı template-dən əldə edilmir. Qrup protokolu tələbəyə açılmır; müəllim və mərkəz üçün mövcud qanuni giriş qorunur, scope-suz UNIT icazəsi rədd edilir. Real bazanın superuser tətbiq rolu ayrıca P0 maneəsi olaraq qalır.

## 13. İmtahan sistemi

Tamamlanan axın: qrup/açılış seçimi → doldurulmuş XLSX/CSV şablonu → ön baxış → serverdə yenidən validasiya → bal servisi → dəyişiklik jurnalı/partiya xülasəsi. Brauzerdə sintetik tələbəyə 32 bal yazıldı. Eyni bal yenidən verildikdə “eyni bal” görünür və tətbiq düyməsi açılmır. İki paralel ilk yazıdan yalnız biri keçir; digəri sənədli düzəliş tələb edir.

Fayl seçimi dəyişəndə köhnə preview etibarsızlaşır; drag/drop, fayl adı, busy və səhv vəziyyətləri işləyir. HTTP tətbiq cavabında yazılmış sayla planlaşdırılmış say qarışdırılmır.

Mövcud imtahan nəticəsini dərhal göstərmə davranışı kodda sahibin açıq məhsul qərarı kimi qeyd olunub; audit bunu gizli release qaydası ilə əvəz etmədi. 5000 paralel imtahan, real zal şəbəkəsi, reconnect fırtınası və coding runtime sandbox penetration testi edilməyib.

## 14. Elektron jurnal

Enrollment üzrə kilidləmə yalnız bal daxil etmə servisinin yarış problemini hədəfləyir; bütün digər qiymət yazı yollarının eyni yarış sınağından keçdiyi iddia edilmir. Mövcud jurnal bağlama və final exam balının ayrıca daxil edilməsi məhsul qaydası saxlanıldı.

Tələbə ekranı sorğu büdcəsi bir fəndən dörd fənnə keçiddə sabit qaldı: fənlər 87→87, jurnal 60→60, gözləyən cavablar 50→50, jurnal detalı 82→82. Bu ölçü N+1 artımını yoxlayır; 87 sorğu ideal mütləq büdcə kimi qəbul edilmir.

## 15. Tədris yükü

Mövcud bölgü/servis testləri ümumi PostgreSQL dəstində işlədildi. Qiymət yazma icazəsi olmayan müəllim üçün registrar trigger-i və fallback davranışı PostgreSQL-ə bağlıdır; no-migrations SQLite nəticəsi ilə istehsal qüsuru elan edilmədi. Bütün tarixi planların real məlumat üzərində müqayisəsi aparılmayıb.

## 16. Dərs cədvəli

Schedule servis/view testləri və rol üzrə səhifə keçidləri əhatəyə daxildir. Mövcud konflikt və struktur qaydaları yenidən yazılmadı. Bütün otaq–müəllim–qrup konflikt kombinasiyalarının real həftəlik cədvəldə əl ilə sınağı tamamlanmış kimi göstərilmir.

## 17. Sillabus axını

Draft/təsdiq/kilid və icazə servis quruluşu, editor/render testləri nəzərdən keçirildi. Tələbə kartında yalnız təsdiqlənmiş sillabusun görünmə müqaviləsi kart partial-ına uyğun testlə qorundu. Sillabusun bütün dillərdə PDF/çap vizual attestasiya prosesi bu auditdə yoxdur.

## 18. Tələbə idarəetməsi

Fənn, jurnal, gözləyən cavablar və statistika ekranları sintetik tələbə ilə yoxlandı. FIN və institusional identifikator düzgün profil əlaqəsindən götürülür. Importda ziddiyyətli identifikator və təkrarlanan sətir rədd edilir. Bütün real tələbə həyat dövrü, transfer, bərpa və silinmə əməliyyatları mövcud bazada icra edilmədi.

## 19. Frontend və UX/UI

Çatışmayan altı statistika partial-ı, statistika CSS/JS-i və import JS-i əlavə edildi. `my_subjects.css` ölçü limitinə uyğun iki fayla bölündü və yeni asset düzgün qoşuldu. Mövcud vizual dil saxlanıldı.

Masaüstü və 390 px mobil tələbə ekranı, müəllim statistikası, imtahan mərkəzi importu brauzerdə açıldı; yoxlanan səhifələrdə konsol xətası görünmədi. Mobil sənəd eni viewport-u aşmadı. İlk resize zamanı açıq sidebar ayrıca müşahidə edildi; yeni mobil naviqasiyada bağlı vəziyyət screenshot-u da saxlandı.

Progress elementləri, cədvəl başlıqları, fokus görünüşü və aria-live nəticəsi əlavə/istifadə edildi. Screen reader, bütün klaviatura marşrutları və tam WCAG uyğunluğu sertifikatlaşdırılmayıb. Vizual sübutlar `output/playwright/codex-*.png` fayllarıdır.

## 20. Lokallaşdırma

Mövcud i18n ratchet qapısı keçir. Lakin EN seçilmiş brauzerdə yeni AZ mətnləri görünür; tam ingilis/rus tərcüməsi hazır deyil. Köhnə kod sözləri/placeholder-ları kor əvəzlənmədi. PostgreSQL-də RU sual bankı testi ilə SQLite parser xətası bir-birindən ayrılmalıdır.

## 21. Performans

Sintetik PostgreSQL məlumatı və Django DEBUG runserver ilə 5 paralel istifadəçi/60 GET sınağı: **60/60 uğurlu**, p50 **304 ms**, p95 **783,2 ms**, p99 **889,2 ms**, ümumi **4,4 saniyə**. Eyni kompüterdə regresiya testləri işləyirdi.

Bu, HTTP smoke yüküdür; production throughput/SLA və ya 5000 istifadəçi tutumu deyil. Böyük real dataset query planları, soyuq/isti Redis, PgBouncer transaction pooling və çox node davranışı ayrıca ölçülməlidir. Qeyri-məhdud performans iddiası verilmir.

## 22. İnfrastruktur və DevOps

İşləyən app/DB/Redis health məlumatları, restart sayları və resurs limitləri oxundu. App qeyri-root `appuser` ilə və privileged olmadan işləyir. App/DB/Redis healthy idi; Celery konteynerində health status yox idi. Mənbə ilə işləyən image arasında versiya və config drift-i təsdiqləndi.

Redis PING uğurlu, AOF aktiv, son RDB save `ok`, evicted_keys=0 idi. Brokerə test email/job göndərilmədi. CI-də lint, unit, təhlükəsizlik, secret scan, container scan, RLS transaction pool və smoke workflow-ları var; bu audit onların uzaq GitHub run-larını yaşıl elan etmir.

## 23. Monitorinq

Konteyner health və resurs snapshot-ları sübut kimi saxlandı. Grafana/Postgres exporter/backup konteyneri görünür. Prometheus alert qaydalarının mövcudluğu son istifadəçiyə bildiriş çatmasını sübut etmir; real xəbərdarlıq kanallarına mesaj göndərilmədi. Monitorinqdə əvvəlcədən olan user/Claude dəyişiklikləri saxlanıldı.

## 24. Avtomatik testlər

| Yoxlama | Nəticə | Sübut |
|---|---|---|
| İlkin SQLite dəsti | 48 uğursuz, 8118 keçən, 232 skip, 282 deselected | `evidence/baseline-tests.txt` |
| Son tam PostgreSQL dəsti | **8474 keçən, 219 skip, 0 uğursuz; 9 dəq 47 san** | `evidence/final-postgres-verified.txt` |
| Son SQLite/coverage dəsti | **28 uğursuz, 8155 keçən, 232 skip, 283 deselected; 7 dəq 29 san** | `evidence/final-sqlite-verified.txt` |
| Son tarix-render düzəlişindən sonra fokuslu dəst | **70 keçən, 120 deselected, 0 uğursuz** | `evidence/final-render-checks.txt` |

Tam PostgreSQL dəsti migrasiyalarla və dörd worker ilə işlədildi; MariaDB testləri bu mühərrik üçün seçilmədi. 219 skip uğurlu test kimi sayılmır. Tam dəstin toplanmasından sonra statistika şablonunda ISO tarix sətirlərinə uyğun olmayan `date` filtrinin çıxarılması və onun yeni regresiya testi ayrıca 70 testlik yoxlamada təsdiqləndi; 8474 rəqəmi həmin yeni testi ehtiva etmir.

SQLite nəticəsi yaşıl deyil. Qalan xətalar sual bankında SQLite parser limiti, migrasiyasız identity sxemi, UUID/struktur sorğuları və workload trigger davranışı ilə əlaqəlidir. Eyni ssenarilər PostgreSQL dəstində keçib; bununla SQLite uyğunluğu təsdiqlənmiş sayılmır. İlkin və son dəstlərdə test sayı yeni regresiyalar və seçim şərtləri səbəbindən fərqlənir.

Aralıq PostgreSQL çalışmasında yeddi köhnə UI müqaviləsi testi uğursuz oldu və uyğunlaşdırıldı. Sonrakı çalışmada bir Clarity settings testi audit konfiqurasiyasının override-ına görə uğursuz oldu; test mühiti düzəldildikdən sonra yuxarıdakı tam dəst təkrar uğurla keçdi. Aralıq nəticələr sübut qovluğunda saxlanılıb.

SQLite coverage ölçüsü: statement **82,99%**, branch **67,83%**, birgə göstərici **79,54%** (apps/core/config, tests/migrations çıxarılıb). Ölçü uğursuzluqları da olan SQLite çalışmasına aiddir; PostgreSQL coverage və ya bütün deployment yollarının əhatəsi deyil. Əvvəlki coverage ölçülmədiyindən “coverage X qədər artdı” iddiası verilmir.

Yeni testlər: import identifikasiyası/validasiyası/təkrar tətbiq, icazəsiz giriş, media scope, yanlış UUID, iki paralel bal yazısı, yoxlanmamış nəticələrin statistikası və zal JOIN fan-out-u. Köhnə DOM adlarına bağlı testlər yeni komponent müqaviləsinə uyğunlaşdırıldı; tenant və nəticə məzmunu yoxlamaları saxlanıldı. Mövcud uğursuz testlər xətanı gizlətmək üçün silinmədi və skip-ə çevrilmədi. Yeni yarış testi yalnız PostgreSQL row-lock semantikasına aiddir.

## 25. Kod keyfiyyəti

Black, isort, flake8, modul ölçü və modul sərhədi qapıları işlədildi. İlkin Black 11 faylda format problemi, flake8 bir unused loop dəyişəni, ölçü qapısı isə 715 sətirlik CSS problemi göstərirdi. Bunlar düzəldildi. Son Django check və migrasiya drift yoxlaması keçdi.

İki dondurulmuş modul dövrü qalır; “arxitektura tam dövrsüzdür” deyilmir. Yeni fayllar 600 sətir qaydasına uyğundur. SQL/XSS/unsafe deserialization üzrə tam formal analiz deyil, konkret risk əsaslı yoxlama aparılıb.

## 26. İcra edilən düzəlişlər

| Fayl/qrup | Dəyişiklik | Risk və yoxlama |
|---|---|---|
| `registrar/exam_score_entry.py` | Enrollment kilidi, sonlu bal, unknown enrollment rəddi, written ID-lər, profile prefetch | Orta; servis, import və PostgreSQL yarış testi |
| `registrar/exam_score_import.py`, `exam_score_import_safety.py` | Profil identifikatorları, ziddiyyət rəddi, parser/ZIP limitləri, formula qorunması, düzgün sayğac | Orta; CSV/XLSX regresiyaları |
| `accounts/views/exam_score_entry.py` | Yanlış UUID üçün idarə olunan cavab | Aşağı; 404 testi |
| `core/media_policies.py` | Yeni qrup protokolu üçün permission-specific scope | Orta; qanuni giriş və scope-suz rədd testi |
| `accounts/views/profile/_sections/statistics.py` | Əhatəli cache key, filtr descriptor-u, şəxsi metriklərdə tətbiq olunmayan filtrin təmizlənməsi | Orta; scope/integration testləri |
| `statistics_metrics/_shared.py`, `student.py`, `presenter.py`, `exam_center.py` | Gözləyən nəticə və zal tutumu aqreqatının düzəlişi | Orta; xüsusi statistik regresiyalar |
| Statistika partial/CSS/JS | Çatışmayan təqdimat, tarix intervalının görünməsi və AI panelinin UI bağlantısı | Orta; render, rol matrisi, brauzer; real AI çağırışı yoxdur |
| `profile/exam_score_import.js`, import partial/CSS | Preview/apply, CSRF, stale file, drag/drop, düzgün nəticə, fokus/aria-live | Orta; brauzer ön baxış/tətbiq/təkrar sınağı |
| `my_subjects.css`, `my_subjects_cards.css`, `_section_assets.html` | Asset bölünməsi | Aşağı; ölçü qapısı və mobil screenshot |
| `registrar/public.py` və istehlakçılar | Yeni xidmətlər üçün public giriş | Aşağı; import və boundary qapısı |
| Regresiya testləri | Yeni davranış və təhlükəsizlik müqavilələri | Test məlumatı yalnız ayrıca bazada |

0071/0072 model/migrasiya skeleti və bir sıra tələbə/panel dəyişiklikləri başlanğıcda mövcud idi. Bu cədvəl həmin işin bütün müəllifliyini iddia etmir. Tam git diff ilkin dirty işlə audit dəyişikliklərini birlikdə göstərir.

## 27. Qalan problemlər

Açıq: DB app rolu, işləyən image/config drift-i, ictimai HTTPS/cookie tənzimləməsi, lokallaşdırma, SQLite bütöv test uyğunluğu, real legacy attestasiyası, backup restore/failover, böyük paralel imtahan/WS yükü, xarici email/AI/alert inteqrasiyaları.

708 503 750 baytlıq backup gzip faylı tam oxunub bütövlüyü və SHA-256 ölçüldü (açılmış axın 2 456 665 751 bayt); **bərpa edilmədi**. Gzip-in oxunması backup-dan tətbiqin ayağa qalxacağına zəmanət deyil. Real backup faylları dəyişdirilmədi; fon backup xidməti audit aralığında ayrıca yeni fayl yarada bilər. Sübut: `backup-integrity.json`.

Tamamlanmayan yoxlamalar gizlədilmir: tam production deploy, 5000+ yük, bütün rolların bütün yazı axınlarının əl ilə E2E-si, bütün dillərdə vizual baxış, uzaq CI, bütün legacy sətirlərinin mənbə ilə müqayisəsi. Bu məhdudiyyətlər istehsal qərarını aşağı saxlayır.

## 28. Sahələr üzrə qiymətlər

Qiymətlər müşahidə olunan kod, test və əməliyyat sübutunun mühəndis qiymətləndirməsidir. Yoxlanmamış sahələr avtomatik yüksək qiymət almır. “Əvvəl” git HEAD deyil, auditin qəbul etdiyi ilkin dirty mənbə vəziyyətidir.

| Sahə | Əvvəl | Sonra | Əsaslandırma |
|---|---:|---:|---|
| Architecture | 76 | 79 | Modullar ayrılıb; yeni dövr yoxdur, iki tarixi dövr qalır. |
| Backend | 71 | 80 | Import validasiyası, idempotentlik və rəqabətli yazı qorunması gücləndi. |
| Frontend | 48 | 73 | Çatışmayan statistika və import axınları tamamlandı; brauzer sınağı var. |
| Database Design | 78 | 78 | PK/FK, Decimal, indeks və migrasiya quruluşu var; əsas sxem dəyişdirilmədi. |
| Database Integrity | 68 | 76 | Bal importu və identifikasiya düzəldi; üç real tenant yoxlaması sıfır uyğunsuzluq verdi. |
| Legacy Data Migration | 56 | 56 | Geniş rehearsal testləri var; real mənbə–hədəf tam tutuşdurması yoxdur. |
| Security | 53 | 64 | Upload və media əhatəsi düzəldi; işləyən DB hesabı hələ superuser-dir. |
| Authentication | 75 | 75 | OTP və sessiya testləri mövcuddur; real SMTP çatdırılması yoxlanmadı. |
| Authorization / RBAC | 65 | 76 | Scope regresiyaları və yeni media giriş testi; rol adından üstün icazə modeli. |
| Multi-Tenancy Isolation | 64 | 75 | RLS testləri və scope keş açarı; işləyən mühitdə RLS bypass maneəsi qalır. |
| Exam System | 76 | 84 | Import, bal tarixçəsi və paralel yazı yoxlanıb; böyük zal yükü ölçülməyib. |
| Electronic Journal | 78 | 82 | Bal əməliyyatları və tələbə sorğu büdcəsi yoxlanıb; model yenidən yazılmayıb. |
| Teaching Workload | 72 | 72 | Bölgü və vəziyyət testləri; PostgreSQL trigger davranışı əsasdır. |
| Schedule System | 70 | 70 | Mövcud servis/view testləri keçid meyarıdır; bütün əl ilə CRUD kombinasiyaları yoxlanmayıb. |
| Syllabus Workflow | 77 | 77 | Vəziyyət maşını və təsdiq axını testləri; bütün dillərdə insan baxışı yoxdur. |
| Student Management | 74 | 78 | Şəxsi kabinet və akademik məlumat axını yoxlandı; real qeydlər dəyişdirilmədi. |
| API Design | 70 | 77 | 945 route inventarı, 403/404 və səhv UUID/CSV cavabları; tam OpenAPI yoxdur. |
| Performance | 64 | 70 | N+1 artımı üçün regresiya və məhdud HTTP ölçüsü; mütləq sorğu sayı yüksəkdir. |
| Scalability | 55 | 55 | 5000 istifadəçi, çox worker və reconnect yükü ilə attestasiya aparılmadı. |
| Reliability | 62 | 66 | Geniş regresiya və migrasiya rehearsal; real failover sübutu yoxdur. |
| Celery / Background Jobs | 68 | 68 | 49 xarici DB giriş nöqtəsinin atomic gate-i keçir; real broker failover yoxlanmayıb. |
| Redis / Caching | 60 | 60 | PING/AOF yoxlandı; işləyən Redis maxmemory=0, limit drift-i qalır. |
| WebSocket / Realtime | 62 | 62 | ASGI origin/auth qapısı və mövcud testlər; geniş socket yükü yoxlanmayıb. |
| DevOps | 58 | 58 | CI qapıları və konteyner limitləri var; lokal işləyən image mənbədən geridir. |
| Deployment | 42 | 42 | Bu audit deploy etmədi; təhlükəsiz cookie/HTTPS və DB rol konfiqurasiyası uyğunlaşdırılmalıdır. |
| Monitoring / Observability | 66 | 66 | Health və resurs sübutu var; xarici alert çatdırılması yoxlanmayıb. |
| Logging | 72 | 74 | Bal partiyası/jurnal audit izi; bütün hadisələr üzrə tamlıq attestasiya edilməyib. |
| Automated Tests | 76 | 85 | Yeni mənalı regresiyalar və tam PostgreSQL dəsti; SQLite məhdudiyyətləri açıq saxlanılıb. |
| Code Quality | 71 | 80 | Black/isort/flake8 və ölçü qapıları düzəldi. |
| Maintainability | 72 | 79 | CSS bölündü, yeni servis istehlakı fasada keçdi, domain sərhədi qorundu. |
| UX/UI | 60 | 74 | Boş vəziyyətlər, import ön baxışı, səhv və nəticə axını işləyir. |
| Accessibility | 62 | 70 | Progress, aria-live, fokus və mobil baxış; screen-reader attestasiya yoxdur. |
| Localization | 52 | 52 | Kataloq qapısı keçir; yeni EN/RU mətnlərində AZ fallback görünür. |
| Documentation | 69 | 78 | Sübut inventarı, məhdudiyyətlər və rollout planı əlavə edildi. |
| Production Readiness | 40 | 40 | İşləyən mühit dəyişməyib; açıq P0/P1 maneələri var. |

## 29. Çəkili ümumi qiymət

| Kateqoriya | Çəki | Əvvəl | Sonra |
|---|---:|---:|---:|
| Təhlükəsizlik | 15% | 53.00 | 64.00 |
| Baza və məlumat bütövlüyü | 12% | 73.00 | 77.00 |
| Backend/biznes məntiqi | 12% | 71.00 | 80.00 |
| İmtahan | 10% | 76.00 | 84.00 |
| Arxitektura | 8% | 76.00 | 79.00 |
| Performans/miqyas | 8% | 59.50 | 62.50 |
| İcazələr/tenant | 8% | 64.50 | 75.50 |
| Frontend | 6% | 48.00 | 73.00 |
| Testlər | 6% | 76.00 | 85.00 |
| DevOps/etibarlılıq | 5% | 60.00 | 62.00 |
| Digər kateqoriyalar | 10% | 66.40 | 69.60 |

Digər kateqoriyalar əvvəlki qruplara daxil edilməyən sahələrin sadə ortasıdır; ayrıca Production Readiness ümumi hesaba yenidən qatılmır. Dəqiq girişlər `scorecard.json` və `weighted-score.json` fayllarındadır.

Texniki bal: **65,91 → 73,74**. Mənbə üçün 65–74 aralığı məhdud pilot səviyyəsini göstərsə də, bu avtomatik rollout icazəsi deyil. İşləyən mühitdə açıq maneələr olduğundan istehsal hazırlığı ayrıca **40/100** qiymətləndirilir.

## 30. İstehsal qərarı

**NOT PRODUCTION READY — 40/100.** Mövcud işləyən mühitdə DB müdafiəsi və konfiqurasiya maneələri bağlanmadan ictimai production təsdiqi verilmir. Təhlükəsiz RLS app hesabı, uyğun image, HTTPS parametrləri və real backup bərpa sınağı əsas buraxılış şərtləridir.

Bu audit real bazanı dəyişdirmədən təhlükəsiz kod düzəlişlərini həyata keçirdi. İstehsal qərarını yaxşı göstərmək üçün məlum risklər “qəbul edilmiş” kimi bağlanmadı. Uzaq serverin vəziyyəti məlum olmadığı üçün ona dair uydurma health və deployment nəticəsi yoxdur.

## 31. Növbəti addımlar

**Dərhal:** ayrı app/migration DB hesabları ilə staging keçidini hazırlamaq; production-shaped PgBouncer/RLS testini işlətmək; doğrulanmış image-i planlı rollout-a hazırlamaq; cookie/HTTPS/Redis limitlərini hədəf mühitə uyğunlaşdırmaq. Mövcud bazada bu dəyişiklikləri kor tətbiq etməmək.

**Qısa müddət:** ayrıca bərpa mühitində backup restore və tətbiq smoke testi; real legacy source attestasiyası və sahə-sahə müqayisə; EN/RU mətnlərini tamamlamaq; protokol əlaqələrinin DB səviyyəsi invariantlarını qiymətləndirmək; CI-də bütün environment qapılarını təsdiqləmək.

**Sonra:** production dataset ölçüsündə query-plan və böyük yük testləri; websocket/reconnect/worker failover; bütün rol axınları üçün E2E matrisi; mütləq query saylarını azaltmaq və qalan modul dövrlərini daraltmaq.

Audit sübutları `docs/audits/2026-09-12-codex/evidence/` qovluğundadır. Onlar sintetik test çıxışları və redaktə edilmiş/aqreqat əməliyyat məlumatlarıdır; production parolları hesabatda saxlanılmayıb.
