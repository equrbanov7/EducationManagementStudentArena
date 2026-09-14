# EMSArena — mərhələli düzəlişlərin vəziyyəti

13 sentyabr 2026. Mənbə `/Users/elvin/Developer/EMSArena`. Modular monolith saxlanılır. İlkin auditin nəticələri tarixi snapshot-dır; aşağıdakılar sonrakı düzəlişlərdir.

## Arxitektura

Statik qarşılıqlı dövrlər 2-dən 0-a, istənilən uzunluqlu dövrlərdə kənarlar 11-dən 0-a düşdü. Core→apps sıfırdır. Tenant resolver ortaq core modulundan istifadə edir; qrup görünürlüğü təşkilatın public oxu API-sindədir. Tələbə köçürməsi registrar-ın qeyd etdiyi, qoşulmadıqda əməliyyatı rədd edən hook ilə işləyir. Akademik seed komandası öz domeninə köçürüldü; komanda adı və məntiqi saxlanıldı.

Sillabus–jurnal arasındakı 12 daxili import public API-yə keçirildi. Yeni private cross-app importların qarşısını alan `public_api_boundaries.py` CI-də işləyir. Baseline mövcud borcun inventarıdır, keyfiyyət təsdiqi deyil; yalnız kiçildilə bilər. Sonrakı keçiddə 246 inventar qeydi sıfıra endirildi: registrar üçün 77 import/44 fayl, digər modullar üçün 71 istehlakçı fayl public API-yə keçirildi. Hər modulun explicit export faylı domenin öz daxilindədir; modellər public fasada əlavə edilmədi. Nisbi cross-app importlar da gate tərəfindən yoxlanır. Runtime hook/ORM əlaqələri statik dövrsüzlük nəticəsinin əhatəsindən kənardır, ayrıca davranış testləri var.

## DB təhlükəsizliyi və bərpa

Provision və fresh-init yolları owner, imtiyazlı, rol üzvlüyü olan və obyekt sahibi hesabın app roluna çevrilməsini rədd edir. Provision tranzaksiyası rollback ilə qorunur. Strict Django check DB-yə qoşula bilmədikdə xəta verir və məxfi exception mətnini göstərmir.

Ayrıca PostgreSQL 16 + PgBouncer session pooling mühitində məhdud app hesabı sınaqdan keçirildi. Current user qorunur; scope-suz oxu və başqa tenant yazısı rədd edilir; yeni bağlantıda scope qalmır. Tətbiqin həqiqi organizations_orgunit cədvəlində də eyni iki-tenant yoxlaması keçdi. Owner roluna keçid, public schema-da DDL və hər iki evidence ledger-inə birbaşa INSERT 42501 ilə rədd edildi. Ledger grant-ları qorunur. Owner runtime check-dən keçmir, app keçir.

Sintetik DB dump/restore keçdi: 282 migration qeydi, 173 cədvəl, 2 tenant-probe sətri uyğun gəldi. Bu, real backup bərpasının sübutu deyil. Mövcud real DB, backup və konteynerlərə dəyişiklik edilmədi. Canlı rol/config/image keçidi edilməyib; hazırlıq addımları `remediation-stage2/ROLLOUT_AZ.md` sənədindədir.

## SQLite və davranış düzəlişləri

- Sual bankı barmaq izi SQLite-də JSON sətirləri və deterministik GROUP_CONCAT/MD5 ilə DB daxilində hesablanır; PostgreSQL StringAgg yolu qalır. Əlavə, silmə, redaktə, dil və sıralama keş regresiyaları keçdi.
- Şəxslər kataloqunda FK Subquery nəticələri açıq UUIDField tipindədir; SQLite hex sətirləri ilə ORM UUID açarlarının uyğunsuzluğu düzəldi. Tenant və sorğu büdcəsi sınaqları saxlandı.
- Struktur adlarının SQLite dəqiq müqayisəsi Unicode hərflərini tanıyır; regex istifadəçi mətnini escape edir. PostgreSQL iexact yolu saxlanıldı.
- Dərs yükü sinxronu registrar public API-dən icazəli müəllimləri bir dəfə alır. Bal yazma səlahiyyəti olmayan namizəd üçün müəllimsiz açılış və blocked sayğacı davranışı artıq yalnız DB trigger-inə bağlı deyil.
- `--no-migrations` kimlik schema testində raw indeks və trigger-ləri yaratmırdı. TestClass real migrasiya installer-ini öz rollback olunan tranzaksiyasında çağırır; migrasiyalı rejimdə itkin schema yenə test uğursuzluğu olmalıdır. Tam SQLite migration zənciri PostgreSQL SQL-i səbəbindən ayrıca dəstəklənmiş sayılmır.

## Yoxlamaların vəziyyəti

Fokuslu dəstlər keçib: 107 arxitektura/qrup/struktur, 6 DB check, 252 sual bankı, 54 şəxslər, 24 struktur, 20 kimlik, 19 workload/command, 240 sillabus (+4 skip), 11 public API/gate. Bu dəstlər kəsişir, cəmlənib unikal test sayı kimi verilmir.

Aralıq tam PostgreSQL: 8492 keçən, 219 skip və köçürülmüş seed komandasının köhnə yoluna görə 4 subtest uğursuzluğu. Yol düzəldildi; production komanda qadağası testləri saxlandı. Son tam dəstlərin yekun nəticəsi tamamlandıqda ayrıca əlavə ediləcək.

## Qalan sərhədlər

Canlı deploy/DB rol keçidi, real backup restore, legacy mənbə tutuşdurması, uzaq TLS, real e-poçt/AI/alert çatdırılması və geniş WS/yük/failover sınaqları təsdiqlənməyib. Production readiness bu işlər görülmədən yüksəldilmiş sayılmır. Statik public API borcu sıfırdır; dinamik/runtime inteqrasiya review-u və lokallaşdırma ayrıca açıqdır.


## Tam dəst — geniş public API keçidindən əvvəlki checkpoint

PostgreSQL: **8490 keçən, 221 skip, 0 uğursuz**, 528,55 saniyə. SQLite: **8201 keçən, 232 skip, 283 seçilməyən, 0 uğursuz**, 263,02 saniyə. SQLite əvvəlki 28 uğursuzluğun olduğu eyni migrasiyasız seçimlə işlədildi.

Bu nəticələr daha sonrakı 115 istehlakçı-fayl dəyişikliklərinin yekun yoxlaması kimi təqdim edilmir. Public API keçidindən sonra hər iki tam dəst yenidən işlədilir; 13 gate testi ayrıca keçib. Dəstlərdəki skip-lər keçən test sayına qatılmır.
