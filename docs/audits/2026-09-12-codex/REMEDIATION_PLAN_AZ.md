# EMSArena — mərhələli düzəliş planı

## Dəyişməz şərtlər

Arxitektura modular monolith qalır: domenlər eyni Django tətbiqi daxilində ayrıca modul və sahiblik sərhədləri ilə işləyir. Mikroservisə bölünmə, ayrıca şəbəkə çağırışı və yeni paylanmış tranzaksiya yaradılmır. Domen xidməti public API-dən, model əlaqəsi ORM-dən, əks istiqamətli inteqrasiya isə mövcud hook/provider pattern-indən istifadə edir. Importu dinamik string-ə çevirməklə xidmət asılılığını gizlətmək həll deyil.

Mövcud real DB, backup və əvvəlcədən dəyişdirilmiş kod qorunur. Yoxlamalar sintetik, ayrıca mühitdə aparılır. Hər mərhələnin tamamlanması ölçülən qəbul şərti ilə qeyd edilir; test edilməyən iş tamamlanmış sayılmır.

## 1. Arxitektura və nəzarət

1.1. Mövcud dependency gate-i AST ilə bütün adi import formalarını və üç və daha çox modullu dövrləri yoxlayacaq şəkildə gücləndirmək. Mövcud borcu artırmadan saxlamaq; testlərlə yeni dövrün rəddini sübut etmək.
1.2. `exams ↔ registrar` və `organizations ↔ registrar` asılılıqlarını ayrı inventarlaşdırmaq: model əlaqələri, domen xidmətləri, təqdimat aqreqatorları, yalnız seed komandalara aid inteqrasiyalar. Public API-ni düzəltmək dövrü avtomatik həll etmir.
1.3. Domen sahibinə əsasən hook/provider və kompozisiya qatını seçərək dövrləri ayırmaq; hər dəyişiklikdən sonra müvafiq davranış testləri, Django check və migration drift yoxlaması. Baseline yalnız real azalmadan sonra kiçildilir.

Qəbul: core→apps sıfır, yeni dövr sıfır, mövcud dövrlər aradan qaldırılıb, cross-module xidmət istehlakı public API-dəndir. İlkin vəziyyət: iki qarşılıqlı dövr var; tam mərhələ açıqdır.

## 2. DB rolları və tenant təhlükəsizliyi

Ayrıca PostgreSQL/PgBouncer mühitində migration və məhdud app hesabını qurmaq; app hesabında superuser/bypassrls olmadığını, tenantlararası oxu/yazının rəddini, worker tranzaksiyalarının scope-u təmizlədiyini sübut etmək. Mövcud provision skriptini nəzərdən keçirmək, əvvəlcədən yoxlama və geri dönüş addımlarını hazırlamaq.

Qəbul: sintetik iki tenant, tətbiq və worker yolları ilə RLS testləri; real DB rolunu dəyişmədən tətbiq edilə bilən keçid sənədi. Canlı keçid ayrıca əməliyyat mərhələsidir.

## 3. Runtime konfiqurasiyası

Image/mənbə uyğunluğunun yoxlanması, HTTPS/proxy trust/Secure cookie parametrləri, Redis yaddaş limiti və health/readiness nəzarəti. Hədəf domen və TLS topologiyası sübutla müəyyənləşdirilməlidir.

Qəbul: ayrıca production-settings mühitində konfiqurasiya yoxlamaları və smoke testləri; səhv konfiqurasiyanın buraxılışı dayandırması. Lokal düzəliş canlı deploy kimi təqdim edilmir.

## 4. Bütövlük və bərpa

Bal protokolunun tenant/əlaqə invariantlarını yoxlamaq; mövcud məlumatda yalnız oxu preflight hazırlamaq. Ayrıca təcrid olunmuş restore mühitində backup bərpası, tətbiq smoke və ölçülmüş bərpa vaxtı. Legacy mənbə əlçatan olduqda sahə-sahə müqayisə.

Qəbul: real bazaya yazmadan bərpa sübutu və invariant nəticələri. Mənbə əlçatan deyilsə legacy attestasiya açıq qalır.

## 5. Funksional keyfiyyət

28 SQLite uğursuzluğunu səbəbə görə düzəltmək; PostgreSQL davranışını qorumaq. EN/RU lokallaşdırma, rol/icazə axınları, mobil ekran və əlçatanlıq. Testləri sadəcə yaşıl etmək üçün skip/əsassız assertion zəiflətməsi yoxdur.

Qəbul: seçilmiş mühərriklərdə dəst nəticələri, rol E2E matrisi və vizual sübut.

## 6. Performans və buraxılış

Sintetik istehsal ölçüsündə sorğu planları, imtahan/WS yükü, reconnect və worker nasazlığı sınaqları. Son tam PostgreSQL regresiyası, lint, modul sərhədi və migrasiya qapıları. Release və rollback addımlarının yekunlaşdırılması.

Qəbul: ölçülmüş yük nəticəsi, keçən qapılar və açıq maneələrin konkret siyahısı. Sübut olmadan production-ready qiyməti yüksəldilmir.

## İcra qeydi

Başlanıb: mərhələ 1.1 və ilk public API pozuntusunun düzəlişi. Sonrakı bəndlər tamamlanana qədər açıq saxlanılır.

### İlk icra nəticəsi

1.1 tamamlandı: AST import yoxlaması və istənilən uzunluqlu dövr üçün yeni kənar qadağası əlavə edildi; baseline böyüdülmədi. Altı gate regresiyası və 22 jurnal/sorğu büdcəsi testi — cəmi 28 test keçdi. Django check, migration drift, modul ölçü/sərhəd və format yoxlamaları keçdi. `journal_sync` daxilində batch uyğunluq sorğusunun dərin importu registrar public API-si ilə əvəz edildi.

1.2 üçün çağırış inventarı: `remediation-stage1/cycle-import-inventory.json`. İki mövcud qarşılıqlı dövr və daha uzun dövrlərdəki kənarlar `remediation-stage1/dependency-snapshot.json` sənədində açıq saxlanılıb. Mərhələ 1 bütövlükdə hələ tamamlanmayıb; növbəti iş domen sahiblik sərhədlərinə uyğun asılılıq ayırmasıdır.

### Dövrlərin ayrılması — icra nəticəsi

- `registrar → exams`: fərdi plan view-u imtahan view helper-i əvəzinə eyni davranışlı `core.tenancy.get_request_organization` istifadə edir.
- Qrup görünürlüğü sorğusu təşkilatın oxu xidmətinə çıxarıldı, private köhnə import adı yerli alias ilə saxlandı. Registrar yalnız organizations public API-sindən istifadə edir.
- `organizations → registrar`: tələbə köçürmə üçün təşkilatın müəyyən etdiyi hook registrar AppConfig.ready-də qoşulur. Domen yazıları registrar xidmətində qalır; handler yoxdursa əməl ValidationError ilə rədd edilir.
- Təşkilat ekranlarının akademik model oxuları mövcud Django app registry pattern-inə keçirildi. Bu, ORM əlaqələrini ləğv etmir və onları xidmət sərhədləri ilə qarışdırmır.
- Akademik jurnal/qiymət də yaradan `seed_western_caspian` komandası registrar moduluna köçürüldü. Əmr adı və 598 sətirlik implementasiya bayt-bayt saxlandı; komanda sintetik testlərdə yoxlandı, real bazada işlədilmədi.

Nəticə: statik qarşılıqlı dövr **2 → 0**, bütün uzunluqlu dövrlərdə kənar **11 → 0**, core→apps **0**. Baseline real azalmadan sonra sıfıra endirildi. Runtime hook-lar və model münasibətləri bu statik rəqəmin əhatəsinə daxil deyil; həmin inteqrasiya ayrıca davranış testləri ilə qorunur.

Yoxlama: 96 qrup/struktur/transkript/kabinet/seed testi + 11 hook/gate testi = **107 keçən test** (SQLite, migrasiyasız, sintetik). Django check və migrasiya drift təmizdir; Black/isort/flake8, modul ölçü və modul sərhəd qapıları keçdi. Bu dəyişikliklərdən sonra tam PostgreSQL dəsti hələ təkrar işlədilməyib.

Mərhələ 1-in dövr bəndi tamamlandı. Qalan arxitektura işi: bütün layihədə public API-dən yan keçən xidmət importlarının mərhələli təmizlənməsi; sonra planın DB/PgBouncer təhlükəsizlik mərhələsi. Mövcud DB, backup və işləyən konteynerlərə dəyişiklik edilmədi.


### Avtonom davam — 13 sentyabr

Mərhələ 1-in statik sərhəd işi tamamlandı: private cross-app importlar 246→0, bütün uzunluqlu modul dövrləri 0, core→apps 0. CI hər iki qapını işlədərək absolute və relative importları nəzarətdə saxlayır. Domenlər eyni Django modular monolith daxilində qalır; yeni şəbəkə xidməti və ya ayrıca domen bazası yaradılmadı.

Mərhələ 2-nin lokal təhlükəsizlik hazırlığı və session-PgBouncer/RLS sınağı keçdi; canlı keçid edilməyib. Mərhələ 4 üçün sintetik restore sübutu var, real backup restore yoxdur. Mərhələ 5-də əvvəlki 28 SQLite uğursuzluğu düzəldildi; son tam SQLite checkpoint yaşıl oldu. Geniş public API keçidinin son testləri və açıq rollout sərhədləri `PROGRESS_AZ.md` sənədində izlənir.
