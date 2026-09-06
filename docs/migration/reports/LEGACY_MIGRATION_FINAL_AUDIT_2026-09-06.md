# EMSArena legacy məlumat miqrasiyası — yekun texniki audit

**Hesabat tarixi:** 2026-09-06  
**Mənbə:** MyEdu MariaDB snapshot-u  
**Hədəf:** iki ayrı disposable lokal PostgreSQL repetisiyası  
**Production:** toxunulmayıb  
**Audit qərarı:** **lokal repetisiya keçib; production keçidi şərtlidir**

> **Vacib:** Bu hesabat “production-a köçürmə tamamlandı” demir. Eyni snapshot
> iki dəfə sıfırdan lokal PostgreSQL-ə köçürülüb və aşağıdakı texniki
> invariantlar keçib. Real serverdə preflight, backup/restore, rol attestasiyası
> və İmtahan Mərkəzinin insan qərarları bitmədən cutover icazəli deyil.

## 1. Qısa cavab

Köhnə sistemdəki **Giriş, Çıxış/imtahan, Yekun və Təkrar imtahan nəticə
faktları üzrə səssiz itki tapılmadı**. Dörd mənbə cədvəlindən yenidən qurulan
171 080 faktın 171 080-i hədəfdə var; açar, xam bal payload-u, source hash və
tenant/review guard fərqlərinin hamısı sıfırdır. 52 386 çap edilmiş bal-vərəqi
artifact-i də açılıb yenidən hash-lənərək tam tutuşdurulub.

Lakin iki fərqli anlayışı qarışdırmaq olmaz:

- **İtkisiz sübut:** 171 080 nəticə faktının hamısı dəyişdirilməz xam sübut
  kimi saxlanıb.
- **Kanonik tətbiq:** 153 507 fakt tələbənin yazılışına təhlükəsiz bağlanıb;
  17 573 fakt xam sübut kimi qalır, amma qeyri-müəyyənlik səbəbindən cari
  nəticəyə avtomatik tətbiq edilmir.

17 573 fakt “yoxa çıxmış data” deyil. Onların avtomatik bağlanması
dayandırılıb ki, yanlış tələbəyə və ya yanlış fənnə bal yazılmasın.

### Audit matrisi

| Sahə | Nəticə | Qısa sübut |
|---|---|---|
| Snapshot identikliyi | Keçib | 2 142 912 818 bayt; sabit SHA-256 |
| İki tam repetisiya | Keçib | 24/24 faza, hər ikisi `succeeded` |
| Determinizm | Keçib | iki run üçün eyni determinism digest |
| Nəticə faktlarının itkisizliyi | Keçib | 171 080 mənbə = 171 080 hədəf; bütün fərqlər 0 |
| Bal-vərəqi artifact-ləri | Keçib | 52 386 = 52 386; 979 137 679 bayt; bütün fərqlər 0 |
| Jurnal xana mühasibatı | Keçib | 5 911 322 xana; izah olunmamış fərq 0 |
| Tenant/RLS/append-only | Lokal PG-də keçib | FORCE RLS, siyasətlər, guard trigger-ləri, runtime rol testi |
| Tələbə UI-si | Keçib | dörd bal ayrıca; bağlı paneldə də daimi qırmızı xəbərdarlıq |
| Production cutover | Keçməyib / icra edilməyib | ayrıca preflight və insan təsdiqi tələb olunur |

## 2. Audit sərhədi və təhlükəsizlik

- Real production bazasına bağlantı açılmayıb və heç bir production yazısı
  edilməyib.
- Mənbə MariaDB lokal konteynerdə həm global, həm sessiya səviyyəsində
  read-only işlədilib.
- Dərin auditor hər iki DB-də read-only transaction açıb; `INSERT`, `UPDATE`
  və `DELETE` icra etməyib.
- Hədəf DB adları disposable formatda, host loopback, port qeyri-standartdır.
- Miqrasiya rolu və audit rolu `NOSUPERUSER`, `NOBYPASSRLS` vəziyyətindədir.
- Repetisiya hesabatında xam PII çıxışı 0, credential çıxışı 0-dır.
- Fərdi tələbə adları, FİN-lər və identifikatorlar bu paylaşım hesabatına
  daxil edilməyib.

Mənbə dump-u:

| Atribut | Dəyər |
|---|---|
| Ölçü | 2 142 912 818 bayt |
| SHA-256 | `177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0` |
| Gözlənilən cədvəl | 81 |
| Gözlənilən ümumi mənbə sətri | 9 044 531 |

Bu SHA-256 cutover günü yenidən hesablanmalıdır. Hash dəyişərsə bu audit yeni
snapshot üçün keçərli sayılmır.

## 3. İki müstəqil tam repetisiya

| Ölçü | Run 1 | Run 2 |
|---|---:|---:|
| Status | succeeded | succeeded |
| Faza | 24/24 | 24/24 |
| Əsas mənbə uçotu | 15 496 | 15 496 |
| Migrated | 15 232 | 15 232 |
| Quarantine | 264 | 264 |
| Skipped | 0 | 0 |
| Blocking issue | 0 | 0 |
| PII çıxışı | 0 | 0 |
| Credential çıxışı | 0 | 0 |

Hər iki run üçün deterministik digest:

`1bf5d78e7a41f0c3d3dfbfe0def22cf6c4bc522881f1b54de75d72af11109379`

Bu o deməkdir ki, eyni snapshot, eyni schema/transform/policy ilə iki təmiz
DB eyni deterministik nəticəni verib. UUID və vaxt kimi qaçılmaz run-spesifik
provenance hissələri digest müqayisəsindən qaydaya uyğun ayrılıb.

Hədəf obyektlərinin hər iki run-da eyni sayları:

| Obyekt | Say |
|---|---:|
| CourseOffering | 11 115 |
| Enrollment | 150 157 |
| Lesson | 304 805 |
| LessonMark | 3 921 304 |
| ComponentScore | 696 204 |
| FinalGrade | 115 403 |
| ResitRecord | 5 121 |
| SelfWorkTopic | 69 404 |
| LegacyGradeFact | 171 080 |
| LegacyGradeArtifact | 52 386 |

## 4. Giriş, Çıxış, Yekun və Təkrar balları

Bir fakt eyni anda bir neçə sahə daşıya bildiyi üçün aşağıdakı sayları
toplamaq olmaz.

| Xam bal sahəsi | Dəyər olan fakt |
|---|---:|
| **Giriş** | **29 738** |
| **Çıxış / imtahan** | **158 210** |
| **Yekun** | **17 194** |
| **Təkrar imtahan** | **5 728** |

Mənbə cədvəli üzrə tamlıq:

| Mənbə cədvəli | Mənbə | Hədəf | Fərq |
|---|---:|---:|---:|
| `imthngrscxsblr` | 12 544 | 12 544 | 0 |
| `journals_dates_points` | 138 737 | 138 737 | 0 |
| `journals_dates_points_archive` | 2 605 | 2 605 | 0 |
| `yekun` | 17 194 | 17 194 | 0 |
| **Cəmi** | **171 080** | **171 080** | **0** |

Sətir-səviyyəli invariantlar:

| Yoxlama | Fərq / pozuntu |
|---|---:|
| Təkrarlanan mənbə `(cədvəl, PK)` | 0 |
| Təkrarlanan hədəf `(cədvəl, PK)` | 0 |
| Hədəfdə çatışmayan mənbə açarı | 0 |
| Mənbəsiz artıq hədəf açarı | 0 |
| Bal payload fərqi | 0 |
| Müstəqil source hash fərqi | 0 |
| Materialization digest / ledger / tenant / review guard pozuntusu | 0 |

Mapping statusu:

| Status | Fakt | Mənası |
|---|---:|---|
| linked | 151 228 | birbaşa kanonik yazılışa bağlıdır |
| conflict | 2 279 | alternativ/toqquşan sübut qorunub |
| discarded_source | 7 728 | mənbə qalibi olmayıb, xam sübut qorunub |
| group_mismatch | 1 964 | qrup uyğunsuzluğu səbəbindən avtomatik tətbiq edilməyib |
| unresolved | 7 881 | təhlükəsiz kanonik bağ tapılmayıb |

`linked + conflict = 153 507` fakt enrollment FK daşıyır. Qalan 17 573 fakt
FK-sızdır, amma balı, mənşə açarı, source hash-i və mapping səbəbi ilə hədəfdə
qalır.

### İmtahan Mərkəzi xəbərdarlığı

171 080 faktın hamısında `requires_exam_center_review = true` saxlanır.
Tələbənin **Nəticələrim** ekranında Giriş, Çıxış (imtahan), Yekun və Təkrar
imtahan ayrıca göstərilir; xam mətn clamp, round və ya yeni düsturla dəyişmir.

**İmtahan Mərkəzi ilə dəqiqləşdirilsin** qeydi:

- bağlı xam-sübut panelinin görünən başlığında qırmızı qalır;
- panel açıldıqda hər xam rəqəmin yanında ayrıca qırmızı göstərilir;
- review `verified` olsa belə legacy mənşə xəbərdarlığı silinmir;
- mavi məlumat qeydi ilə qırmızı daimi mənşə xəbərdarlığı semantik olaraq
  ayrıdır.

Desktop və 390×844 mobil viewport real Chromium renderi ilə yoxlanıb. Dörd
balın ayrı görünməsi, bağlı paneldə xəbərdarlığın itməməsi və responsive iki
sütun düzülüşü təsdiqlənib.

## 5. Çap edilmiş bal-vərəqi sübutu

| Invariant | Nəticə |
|---|---:|
| Mənbə export sətri | 52 386 |
| Hədəf immutable artifact | 52 386 |
| Mənbə payload baytı | 979 137 679 |
| Hədəfdə möhürlənmiş açılmamış bayt | 979 137 679 |
| Çatışmayan / artıq açar | 0 / 0 |
| Metadata uyğunsuzluğu | 0 |
| Müstəqil source hash uyğunsuzluğu | 0 |
| Zlib açılma / ledger / tenant / digest pozuntusu | 0 |

Auditor 52 386 sıxılmış artifact-in hər birini açıb, bayt ölçüsünü və
SHA-256-sını mənbədən müstəqil hesablayıb. Xam HTML hesabatda paylaşılmayıb.

## 6. Bütün jurnal xanalarının mənbə–hədəf mühasibatı

Bu hissə “hamısı eyni sayda target row olmalıdır” demir. Boş xana, canlı/arxiv
örtüşməsi, eyni hüceyrənin dublikat versiyası, orphan jurnal və həll olunmayan
yazılış target business row-a çevrilməməlidir. Auditor hər xananı importer-in
qərar alqoritmi ilə ayrıca təkrar işlədib.

| Ölçü | Say |
|---|---:|
| Xam canlı + arxiv jurnal xanası | 5 911 322 |
| Hədəfdə materiallaşan sətir | 4 587 875 |
| Səbəbi tam izah olunan fərq | 1 323 447 |
| **İzah olunmamış fərq** | **0** |

Domen nərdivanları:

| Domen | Gözlənilən | Faktiki | Fərq |
|---|---:|---:|---:|
| Təqvim: davamiyyət + gündəlik bal | 3 921 304 | 3 921 304 | 0 |
| Komponent: kollokvium + sərbəst iş | 546 047 | 546 047 | 0 |
| İmtahan: `im` / `im2` | 120 524 | 120 524 | 0 |

**Sərt şərh:** 1 323 447 xana target business row deyil. Onlar səssiz yox
olmayıb — səbəb nərdivanında hesablanıb və mənbə snapshot-u hash ilə qorunur.
Amma bütün 5,9 milyon xananın xam payload-unu yeni əməliyyat cədvəllərində
queryable saxlamaq ayrıca tələb olarsa, bu hazır həll onu etmir. Buna görə
source dump və onun hash-i qanuni retention müddəti ərzində silinməməlidir.

## 7. Köhnə bal hesabı və yeni sistemlə münasibəti

İstifadəçinin təqdim etdiyi əlyazma və kodlaşdırılmış characterization testləri
köhnə giriş balını belə təsvir edir:

`giriş = (((fəaliyyət ortası + kollokvium ortası) / 2) × 3) + davamiyyət + sərbəst iş`

- seminar olduqda fəaliyyət ortası seminar ortasıdır;
- lab və seminar birlikdə olduqda birləşdirilmiş fəaliyyət ortası işlənir;
- seminar olmadıqda fəaliyyət ortası lab ortasıdır;
- davamiyyət və sərbəst işin hər biri 0…10 olmalıdır;
- tələb olunan kateqoriya yoxdursa hesab “fail closed” olur;
- yuvarlaqlaşdırma ayrıca `ROUND_HALF_UP` qaydası ilə edilir.

Test nümunələri 44,5; 44 və 42,5 nəticələrini verir, maksimum normal nümunə
50-dir. Bu düstur **tarixi interpretasiyadır**, universitet normativ sənədini
əvəz etmir; son söz İmtahan Mərkəzinindir.

Yeni sistem fərqli bal siyasəti işlədə bilər. Ona görə:

- köhnə xam bal yeni düsturla yenidən hesablanmır;
- köhnə xam bal cari `FinalGrade` üzərinə səssiz yazılmır;
- legacy sübut və yeni sistemin kanonik nəticəsi UI-də ayrı bloklarda qalır;
- insan təsdiqindən sonra düzəliş original faktı dəyişmir, ayrıca append-only
  review/decision izi yaradır.

## 8. Tenant təhlükəsizliyi və dəyişdirilməzlik

Disposable PostgreSQL-də yoxlanılanlar:

- `registrar_legacygradefact`, `registrar_legacygradereview` və
  `registrar_legacygradeartifact` üçün RLS aktiv və **FORCE** vəziyyətindədir;
- hər cədvəldə tenant isolation siyasəti var;
- hər cədvəldə insert guard və UPDATE/DELETE/TRUNCATE append-only guard-ları
  mövcuddur;
- runtime DB rolu `rolsuper=false`, `rolbypassrls=false` qaytarıb;
- cross-tenant read/insert, icazəsiz review/import və append-only dəyişmə
  sınaqları real PostgreSQL engine-də keçib;
- tətbiq qatında organization iki dəfə scope edilir: faktın öz tenant-ı və
  əlaqəli enrollment/student tenant-ı.

Miqrasiya başlığında ən azı bunlar olmalıdır:

- `0052_legacy_grade_evidence`
- `0053_legacy_grade_write_authorization`
- `0054_legacy_grade_attempts_and_artifacts`

Repetisiya DB-də bunlar və sonrakı registrar migrasiyaları tətbiq olunub.
Production preflight eyni vəziyyəti ayrıca təsdiqləməlidir.

## 9. Tapılan və düzəldilən qüsurlar

1. **J12 determinism qüsuru.** 1 472 təqvim toqquşmasında disposable Lesson
   UUID-si digest-ə düşürdü. Locator `calendar:{ay}:{gün}:{saat}` sabit
   mənbə formasına keçirildi; transform family v3/J12 namespace v2 edildi.
2. **Reconciliation CLI-nin gizli Django asılılığı.** `CellElection` saf
   modula çıxarıldı; importer və auditor eyni seçki kodunu işlədir. CLI artıq
   `DJANGO_SETTINGS_MODULE` olmadan yüklənir.
3. **Auditorun J12 false-positive-i.** İlk deep run 1 849 digest və 87
   enrollment-map guard pozuntusu göstərdi. Səbəb data deyil: J12 writer
   qəsdən seyrək payload hash-ləyirdi, auditor tam default payload qururdu;
   həll olunmayan 87 təqvim faktında enrollment məlum olsa da lesson mümkün
   deyildi. Auditor writer payload-unu eynilə rekonstruksiya edəcək şəkildə
   düzəldildi. Real 171 080 sətir üzrə guard scan və hər iki deep audit bundan
   sonra 0 pozuntu verdi.
4. **Bağlı paneldə görünməyən qırmızı qeyd.** Hər rəqəmin yanında qeyd vardı,
   amma panel bağlı olanda görünmürdü. Daimi warning panel summary-sinə də
   əlavə edildi; desktop/mobil render və testlə kilidləndi.
5. **SQLite repair-guard testinin yanlış mühit fərziyyəsi.** Məhsul kodu
   SQLite-ı qəsdən disposable test bazası saydığı halda bir test onu markersiz
   PostgreSQL kimi qəbul edirdi. Test real branch-i açıq mock etməyə keçirildi;
   tətbiq təhlükəsizlik qapısı dəyişdirilmədi.

Bu düzəlişlər köhnə bal payload-unu dəyişməyib.

## 10. Mənbədə qalan şübhələr və insan qərarları

### Bal üzrə prioritet yoxlama

| Səviyyə | Tapıntı | Tələbə | İzah |
|---|---:|---:|---|
| Tier 1 | 48 | 47 | 43 şkala pozuntusu + 5 absurd üç-rəqəmli dəyər |
| Tier 2 əsas | 261 | 238 | keçid xətti/kəsr ziddiyyəti kimi risklər |

Bu rəqəmlər “səhvdir” hökmü deyil. Onlar İmtahan Mərkəzinin çap bal-vərəqi,
protokol və digər rəsmi sənədlə yoxlamalı olduğu namizədlərdir. Şəxsi siyahı
PII səbəbindən bu paylaşım PDF-nə daxil edilməyib.

### Mənbə keyfiyyəti

| Fakt | Say |
|---|---:|
| Qrupsuz tələbə | 1 |
| Mövcud olmayan qrupa istinad edən tələbə | 16 |
| Təkrarlanan FİN namizədi | 2 |
| Eyni ad/soyad/ata adı dublikat namizədi | 70 |
| Mövcud olmayan müəllimə istinad edən jurnal | 1 531 |
| Mövcud olmayan tələbəyə istinad edən `yekun` | 58 |
| Hədəfdə SAR-sız tələbə | 17 |
| Hədəfdə müəllimsiz açılış | 1 172 |

Bunlar miqrasiya zamanı yaranmayıb; mənbənin öz vəziyyətidir. Avtomatik
“düzəltmək” yanlış şəxsə data bağlaya biləcəyi üçün quarantine/review yolu
seçilib.

## 11. Test və yoxlama sübutu

Son audit dövründə icra olunan əsas qapılar:

- 62 PostgreSQL/RLS testi keçib, 1 məqsədli skip;
- yekun tam `apps/legacy_import/tests` SQLite run-ında 1 594 test keçib,
  68 PostgreSQL/xarici inteqrasiya testi mühərrikə görə məqsədli skip olub;
- J12 auditor düzəlişindən sonra 94 fokuslanmış digest/replay testi keçib;
- UI summary düzəlişindən sonra 41 nəticə/warning testi keçib;
- ayrıca agent auditində 24 PG legacy-evidence və 96 UI/read testi keçib;
- `manage.py check` və `makemigrations --check` keçib;
- module-size və module-boundary gate-ləri keçib;
- dəyişən audit faylları üzrə Black, isort və flake8 keçib;
- real Chromium desktop/mobil component renderi vizual yoxlanıb.

Bu saylar qismən üst-üstə düşən test qruplarıdır; onları bir-birinə toplamaq
olmaz.

### PII-siz sübut paketi

`docs/migration/reports/final-2026-09-06-evidence/` qovluğunda iki run JSON-u,
iki deep report, PII-siz CLI xülasələri və checksum manifesti saxlanır.

| Sübut | SHA-256 |
|---|---|
| Run 1 JSON | `f993558f195df496bcb5615e2f5065a8dfdcd7aadacc64ba5263445ed0f5f6c8` |
| Run 2 JSON | `0617698e152161bbb96ff2c5d541c9e6596d36287282681b1af3d01e55c992a4` |
| Deep Run 1 | `c45c8ee62d3eb2d5ab91c1bf32e4c1ad8b9b4648f12ebc93814cdab158e9fbd8` |
| Deep Run 2 | `ac6c4c60ba9d0aa57b647ef0154716cc9a33a2660c0c2626677cf22433e5c556` |
| Normalized byte-identik deep məzmun | `15e66b46e43062500abe22ef985479d59833c61e8c8e0b24a12d020d3141c1e2` |

## 12. Claude-un hesabatı ilə müqayisə

2026-08-27 tarixli Claude hesabatları həmin günün kodunu düzgün olaraq natamam
sayırdı: 17 faza vardı, journal recovery və bütün nəticə sübutu tamamlanmamışdı.
Bu sənədlər tarixi checkpoint-dir, cari yekun sübut deyil.

Cari vəziyyətdə:

- faza sayı 17-dən 24-ə çıxıb;
- iki sıfırdan PostgreSQL run eyni digest verib;
- J12 synthetic lesson/recovery və conflict evidence işləyib;
- bütün dörd legacy nəticə mənbəyi immutable fact store-a daxil olub;
- dərin auditor xana seçkisini importerdən müstəqil təkrar edib;
- artifact və fact hash-ləri sıfır fərqlə bağlanıb;
- RLS/append-only və daimi qırmızı xəbərdarlıq testlə kilidlənib.

### Claude-un yenə mütləq yoxlamalı olduğu şeylər

1. İki JSON-dakı `determinism_digest`, `status`, 24 faza və total-ları
   byte-level müqayisə etsin.
2. Hər iki deep report-da üç xana nərdivanının, 171 080 fact invariantının və
   52 386 artifact invariantının 0 fərqlə bağlandığını yoxlasın.
3. `scripts/legacy_reconcile/grade_facts.py` içində J12 sparse payload digest-i
   ilə writer-in eyni sahələri hash-lədiyini yoxlasın.
4. `cell_election.py`-nin saf olduğunu, importer və auditorun eyni kodu
   istifadə etdiyini yoxlasın.
5. UI template-də summary warning-in panel bağlı ikən görünməsini və hər balda
   score warning-in qalmasını desktop + mobil yoxlasın.
6. Production-da 0052–0054 və sonrakı migrasiyaları, FORCE RLS, policy/trigger
   saylarını və runtime rolun `NOSUPERUSER/NOBYPASSRLS` olduğunu təkrar
   attestasiyadan keçirsin.
7. 17 573 bağlanmayan faktı və 48 Tier-1 şübhəni İmtahan Mərkəzi workflow-una
   salmadan “bütün nəticələr rəsmi təsdiqlənib” deməsin.
8. Snapshot hash-i, backup restore sınağı, freeze window və rollback qərar
   nöqtəsi olmadan production cutover etməsin.

## 13. Production keçidi üçün məcburi şərtlər

1. Yeni source snapshot çıxarılır və SHA-256 bu auditlə eynidirsə reuse edilir;
   fərqlidirsə iki-run repetisiyası yenidən edilir.
2. Production backup alınır və ayrıca mühitdə restore testi edilir.
3. Schema preflight: bütün migration-lar, constraint-lər, RLS/policy/trigger-lər
   və indekslər yoxlanır.
4. Runtime və migration rolları attestasiya olunur; gündəlik runtime roluna
   superuser/BYPASSRLS verilmir.
5. Yazı freeze window elan edilir; source dəyişməz vəziyyətə gətirilir.
6. Dry-run plan digest-i bu hesabatdakı policy/schema/transform ilə müqayisə
   edilir.
7. Cutover eyni snapshot üzərində icra olunur; dərhal deep reconciliation
   işlədilir.
8. `unexplained difference`, fact mismatch, artifact mismatch və ya RLS guard
   pozuntusundan hər hansı biri 0-dan böyükdürsə rollback edilir.
9. İmtahan Mərkəzi 17 573 bağlanmayan faktı və şübhəli bal siyahısını ayrıca
   review edir; heç biri avtomatik “doğru” elan edilmir.
10. Mənbə dump və audit sübutları retention siyasətinə uyğun read-only arxivdə
    saxlanır.

## 14. Yekun hökm

**Texniki lokal hökm: PASS.** Eyni snapshot-dan iki təmiz PostgreSQL
repetisiyası deterministikdir. 171 080 legacy nəticə faktı və 52 386 çap
artifact-i itkisiz/hash-dəqiqdir. Jurnal mühasibatında izah olunmamış fərq
sıfırdır. Tenant/RLS/append-only testləri və dörd balın qırmızı warning-li UI
göstərişi keçib.

**Rəsmi bal hökmü: insan təsdiqi gözləyir.** 17 573 fakt kanonik yazılışa
avtomatik bağlanmır; Tier-1/Tier-2 şübhələr rəsmi sənədlə yoxlanmalıdır.

**Production hökmü: hələ NO-GO.** Bu audit production-a toxunmayıb. §13-dəki
preflight və rollback şərtləri tamamlanıb eyni deep audit production nəticəsi
üzərində sıfır fərq vermədən sistem GO sayıla bilməz.
