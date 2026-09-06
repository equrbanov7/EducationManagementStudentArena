# Legacy miqrasiyası audit checkpoint-i

**Tarix:** 2026-09-06  
**Status:** yekun hesabat deyil; uzunmüddətli müstəqil reconciliation davam edir  
**Production:** toxunulmayıb  
**Kod bazası:** `Develop` @ `adb7e07f2a0a9764b9e5b9d24b9f16f6d961c8b0`

Bu checkpoint limit və ya proses kəsilərsə görülmüş işin itirilməməsi üçündür.
Yekun qərar yalnız aşağıdakı açıq addımlar tamamlandıqdan sonra verilməlidir.

## 1. İndiyə qədər dəqiq təsdiqlənənlər

- Eyni köhnə snapshot-dan iki ayrı, sıfırdan qurulmuş disposable PostgreSQL
  repetisiyası 24 fazanın hamısını uğurla tamamlayıb.
- Hər iki repetisiyanın deterministik hissəsi bit-bit eynidir:
  `1bf5d78e7a41f0c3d3dfbfe0def22cf6c4bc522881f1b54de75d72af11109379`.
- Hər run-da əsas import uçotu: 15 496 mənbə sətri, 15 232 migrated,
  264 quarantine, 0 skipped, 0 blocking issue.
- Hesabat çıxışında xam PII sahəsi 0, credential sahəsi 0-dır.
- Köhnə snapshot: 2 142 912 818 bayt; SHA-256
  `177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0`.
- Mənbə MariaDB global və sessiya səviyyəsində read-only, hədəf isə loopback,
  qeyri-standart portlu, disposable marker-li PostgreSQL-dir. İcra rolu
  superuser və `BYPASSRLS` deyil.
- 62 PostgreSQL/RLS testi keçib, 1 gözlənilən skip var.
- J12 determinism düzəlişindən sonra 158 fokuslanmış SQLite testi keçib.
- Saf reconciliation CLI düzəlişindən və yeni izolyasiya regresiya testindən
  sonra 193 əlaqəli SQLite testi keçib.

## 2. İki təmiz run

| Run | Disposable DB | Run ID | Status |
|---|---|---|---|
| 1 | `emsarena_rehearsal_43f4ed790519` | `0ba6ed83-4b5e-450a-852b-254a4f8d0c22` | succeeded |
| 2 | `emsarena_rehearsal_66a6dfed1f70` | `4fd9bab8-8214-40f7-beb8-8f591c779b52` | succeeded |

Run 1-də uzun mənbə oxunuşu zamanı bir MariaDB bağlantısı düşüb. Eyni run
checkpoint-dən təhlükəsiz davam edib və yekun nəticə Run 2 ilə tam eyni olub;
bu hal məlumat itkisi yaratmayıb.

Hər iki hədəf DB-də tenant-scoped obyekt sayları da eynidir:

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

## 3. Köhnə qiymət sübutunun hədəfdəki tamlığı

Hər iki hədəf DB-də eyni nəticə alınıb:

| Ölçü | Say |
|---|---:|
| `LegacyGradeFact` | 171 080 |
| Qırmızı İmtahan Mərkəzi xəbərdarlığı tələb edən fakt | 171 080 |
| Qeydiyyata təhlükəsiz bağlanan fakt | 153 507 |
| Qeydiyyata avtomatik bağlanmayan, amma xam saxlanan fakt | 17 573 |
| Yanlış source hash | 0 |
| Yanlış materialization digest | 0 |
| Dublikat `(source_table, source_pk)` | 0 |
| Dublikat materialization digest | 0 |
| Sıxılmış bal-vərəqi artifact-i | 52 386 |
| Yanlış artifact payload hash | 0 |
| Boş artifact payload | 0 |

17 573 sətir **itməyib**: xam, hash-lənmiş və dəyişdirilməz sübut kimi
saxlanıb. Lakin onlar kanonik qeydiyyata bağlanmadığı üçün İmtahan Mərkəzi
qərarı olmadan tələbənin cari nəticəsinə avtomatik tətbiq edilə bilməz.

## 4. Giriş, Çıxış, Yekun və Təkrar balları

Sahələr bir-birini istisna edən sətirlər deyil; bir köhnə fakt eyni anda bir
neçə bal sahəsi daşıya bilər.

| Xam sahə | Dəyər olan fakt sayı |
|---|---:|
| Giriş | 29 738 |
| Çıxış / imtahan | 158 210 |
| Yekun | 17 194 |
| Təkrar imtahan | 5 728 |

Mənbə cədvəli üzrə qorunan sətirlər:

| Mənbə | Fakt | Əsas məzmun |
|---|---:|---|
| `yekun` | 17 194 | Giriş + Çıxış + Yekun |
| `imthngrscxsblr` | 12 544 | Giriş + Çıxış cəhdi |
| `journals_dates_points` | 138 737 | imtahan/təkrar/xüsusi xana |
| `journals_dates_points_archive` | 2 605 | arxiv imtahan/təkrar xanası |

UI read-model xam mətni birinci seçim kimi verir, round/clamp etmir. Tələbənin
`Nəticələrim` detalında Giriş, Çıxış (imtahan), Yekun və Təkrar imtahan ayrıca
göstərilir və hər rəqəmin yanında daimi qırmızı **“İmtahan Mərkəzi ilə
dəqiqləşdirilsin”** mətni qalır. Review statusu ayrıca göstərilir; `verified`
olması legacy mənşə xəbərdarlığını silmir.

## 5. Tapılan və düzəldilən texniki qüsurlar

1. **J12 qeyri-determinizmi.** 1 472 təqvim toqquşmasında disposable `Lesson`
   UUID-si digest-ə düşürdü. Mənbə balında fərq yox idi, amma iki təmiz run
   müqayisəsi yalnış fərqlənirdi. Locator stabil
   `calendar:{ay}:{gün}:{saat}` formasına keçirilib; transform family v3 və J12
   namespace v2 edilib ki, köhnə yarımçıq run qarışmasın.
2. **Müstəqil reconciliation CLI Django-ya gizli bağlı idi.** Dərin replay
   başlayanda `CellElection` importu model/settings qaldırır və təmiz CLI-ni
   dayandırırdı. Seçki alqoritmi saf `cell_election.py` moduluna çıxarılıb,
   importer və auditor eyni kodu paylaşır. `DJANGO_SETTINGS_MODULE` olmadan
   CLI help və əlaqəli testlər keçir.

## 6. Şübhələr və insan qərarı tələb edənlər

- 171 080 faktın hamısı qəsdən İmtahan Mərkəzi yoxlaması tələb edir.
- 17 573 fakt qeydiyyata avtomatik bağlanmayıb; bunların səbəbi status üzrə
  ayrıca reconciliation hesabatında göstərilməlidir.
- J12-də 1 762 toqquşma sübutu və 87 həll olunmamış təqvim sübutu qorunub.
  Bunlar fakt itkisi deyil, avtomatik qalib seçiminin təhlükəsiz dayandığı
  hallardır.
- Şübhəli bal auditi ayrıca saxlanır: Tier 1-də 48 tapıntı/47 tələbə
  (43 şkala pozuntusu + 5 absurd üç-rəqəmli dəyər), əsas Tier 2-də 261
  tapıntı/238 tələbə. Bu siyahı hökm deyil; İmtahan Mərkəzi/rəsmi sənədlə
  təsdiqlənməlidir.
- Mövcud yeni hesab düsturu köhnə rəqəmlərin üzərinə tətbiq edilmir. Legacy
  rəqəm ayrıca xam sübutdur; yeni sistem hesabı ayrıca kanonik nəticədir.

## 7. Claude üçün yoxlama siyahısı

Claude bu checkpoint-i yekun təsdiq kimi qəbul etməməlidir. Əmin olmaq üçün:

1. Cari diff-də J12 stabil locator-un importer və independent replay-də eyni
   qurulduğunu yoxlasın.
2. `CellElection` modulunun Django import etmədiyini və həm importer, həm CLI
   tərəfindən istifadə olunduğunu yoxlasın.
3. Run 1 və Run 2 JSON-un `deterministic` obyektlərini byte-level müqayisə
   etsin və hər ikisinin `status=succeeded` olduğunu təsdiqləsin.
4. Deep reconciliation hesabatında bütün source/target saylarının, replay
   qərarlarının, `LegacyGradeFact` hash-lərinin və 52 386 artifact payload-un
   sıfır fərqlə bağlandığını görmədən “tam hazırdır” deməsin.
5. PostgreSQL-də RLS, cross-tenant insert/read, append-only
   update/delete/truncate və unauthorized review/import testlərinin real
   engine-də keçdiyini yoxlasın.
6. Tələbə UI-sində dörd xam sahəni və qırmızı daimi xəbərdarlığı real brauzer
   renderində desktop + mobil ölçüdə yoxlasın.
7. Production cutover-dan əvvəl backup/restore sınağı, runtime rol attestasiyası,
   freeze window və rollback qərar nöqtəsinin ayrıca təsdiqini tələb etsin.

## 8. Hazırda yarım qala biləcək hissə

- Run 1 üçün müstəqil deep reconciliation işləyir; Run 2 də eyni yoxlamadan
  keçirilməlidir. İlk Run 1 cəhdi artifact axınında defolt 600 saniyəlik
  PostgreSQL statement timeout-a çatdı; bu məlumat uyğunsuzluğu deyil.
  Read-only auditor sənədləşdirilmiş `2h` limitlə sıfırdan yenidən başladılıb.
- Deep nəticələrdən sonra yekun Markdown/PDF hesabat yaradılmalı, vizual və
  mətn QA edilməlidir.
- Dəyişikliklərin tam repo lint/check/migration-test matrisi yenidən
  işlədilməlidir.
- Production cutover bu auditin daxilində deyil və hələ icazəli deyil.

Bu dörd bənd bitmədən avtomatlaşdırma dayandırılmamalı və “production-ready”
hökmü verilməməlidir.
