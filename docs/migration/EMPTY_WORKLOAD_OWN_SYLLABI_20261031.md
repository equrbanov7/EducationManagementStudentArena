# Boş yük jurnallarının öz mənbə sillabusları — 2026-10-31

## Əhatə və qərar

18:02 UTC snapshot: cari payız yük sətri ilə fənn/semestr/qrup/müəllimi eyni, aktiv və sıfır dərsli 248 açılış. Bu, bütün müəllim-jurnal bağlantılarının tamlığı iddiası deyil.

Köhnə read-only klonun immutable `worker` + `lesson_subject` + `group_unit` ledger-i ilə 16 açılışın köhnə 14-cü semestr jurnalı dəqiq uyğun gəlir. Heç birində qiymət/davamiyyət xanası yoxdur; birində yalnız eyni slotun 6 tarix təkrarı var. Mənbəsiz dərs və qiymət yaradılmır. 159 açılışda köhnə klon ledger-i natamamdır; bu, mənbənin olmadığı demək deyil.

Effektiv sillabusu olmayan boş açılışlar içindən 15 hədəf seçilib. Hər biri üçün müəllif/fənn immutable ledger-i, tam məzmun, ümumi saat və rəsmi yük sətrinin mühazirə/seminar/laboratoriya planı dəqiq uyğundur; yalnız bir uyğun aktiv mənbəsi olan hədəflər qəbul edilir. 7 çoxnamizədli açılış bu paketə daxil deyil. Qoşqar Əliyevin açılışları ayrıca düzəlişə saxlanılıb.

Köhnə `status=0` təsdiq sübutu kimi təqdim edilmir. Cari təsdiq istifadəçinin yoxlanılmış köçürməni təsdiqlənmiş formada gətirmək göstərişinə əsaslanır. Öz müəllifliyi, bütün mənbə bölmələri və mənbə mənşəyi saxlanır.

## Sabit hədəflər

| Açılış | Fənn / qrup | Mənbə sillabus | Saatlar M/S/L |
|---|---|---:|---|
| `0a07d580-61ac-445b-b4a3-8628633c8e43` | Büdcə sistemi / 2536 MU | 4450 | 10/5/0 |
| `55294223-9170-49ca-93a9-a965c7d62a33` | Maliyyə hesabatlarının beynəlxalq standartları / 2532 ML | 7360 | 10/10/0 |
| `652915de-80af-41c6-8150-715f828da34e` | Mühasibat uçotu / 2535 T | 8253 | 10/10/0 |
| `6817a9ac-ffee-47a9-b6ba-4143c19238b6` | Akademik yazı və etika / 409/6MBA | 7711 | 30/15/0 |
| `6c416b69-9229-4fd6-8a18-646570c1205c` | Rəqəmsal sistemlər / 2233K | 7444 | 15/10/0 |
| `6c6a7276-958b-4f6e-8231-94f66a41e837` | Mülki müdafiə / 336 T | 2714 | 15/15/0 |
| `8cbb37d4-7c9b-40df-8cd4-dae9ec27bbd8` | Mülki müdafiə / 635 İ | 2714 | 15/15/0 |
| `a136ae15-4847-4009-a1e1-e0ab277025ed` | Rəqəmsal sistemlər / 2232 K | 7444 | 15/10/0 |
| `ad0e61b1-5b18-44ca-863b-a4d7931782f3` | İnformasiya kommunikasiya sistemləri / 2234 İT | 7064 | 10/5/0 |
| `b52ff85a-448b-4096-b1ff-449b8f66c5e2` | İT layihələrin idarəedilməsi / 2232 İT | 8208 | 10/10/0 |
| `c931e768-a9ef-47aa-bbf3-598bb1733feb` | Müəssisənin maliyyəsi / 2532 i | 7349 | 15/10/0 |
| `d0410b1c-f874-4b6e-9cc5-6d753b09191c` | Müqayisəli beynəlxalq münasibətlər nəzəriyyəsi / 213/6BM ing | 8936 | 30/15/0 |
| `d764add6-56bf-401d-bfe5-3b082ad744be` | Müəssisənin maliyyəsi / 2532 ML | 7349 | 15/10/0 |
| `e6eb947a-b498-4eca-823f-0fbfd746ed6b` | Mülki müdafiə / 336 F | 2714 | 15/15/0 |
| `ed75cc7f-2634-457b-bad9-f1897afea895` | Mülki müdafiə / 635 Q | 2714 | 15/15/0 |

## İcra müqaviləsi

`recover_empty_workload_syllabi` default dry-run, atomik apply və auditli undo verir. Mənbə payload-u repoya daxil edilmir; 15 hədəfin 10 unikal mənbəsi private evidence faylındadır. SHA-256: `159c8752e38ac17868cc5c2de5554b88b6078ea77790a6d98087c22334d9d490`.

Runtime hədəfin aktivliyini, müəllim icazəsini, təyin olunmasını, eyni yük sətrini/qrupu/fənni/semestri, növ-saat planını, cari açıq semestr tarixini və jurnalın hələ boş olduğunu yoxlayır. Canonical `syllabus_for_offering` effektiv paylaşım/baza sillabusu da görür; mövcud sillabusun üstünə yazılmır. Canonical `import_migrated_version` təsdiqlənmiş versiya yaradır və çevirilən bütün bölmələrin eyniliyini yoxlayır. Qiymət, davamiyyət, qeydiyyat və dərslər dəyişmir.

Paket hələ production-da tətbiq edilməyib. Apply-dan əvvəl tam paketlə dry-run, sonra təkrar tətbiq/idempotence receipt və təzə snapshot ilə 15 açılışın təsdiqlənmiş öz müəllifli sillabusunun yoxlanması tələb olunur.
