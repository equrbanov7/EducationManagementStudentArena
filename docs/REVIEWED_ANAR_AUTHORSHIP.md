# Anar 9490: iki mövcud jurnalın dar müəlliflik bərpası

Bu əməliyyat yeni dərs yükü, sillabus, tarix, xana və ya qeydiyyat yaratmır.
Yalnız 28 sabit dərsin `instructor=NULL` sahəsini 9490 edir. `created_by`,
`LessonMark.entered_by`, bütün qiymətlər, tarixlər və transfer əlaqələri dəyişmir.

## Sübut və səbəb

- Mənbə müəllimi1021 və cari9490 üçün tam ad/ata adı dəqiq uyğun gəlir.
  Cari hər iki jurnalın sahibi9490-dır. Ayrı typed worker-map mövcudluğu
  iddia edilmir; bu, ayrıca nəzərdən keçirilmiş sabit şəxsin bərpasıdır.
- Mənbə14360, subject285, group816 → cari
  `8cc86c4b-eee6-43a8-ba18-5a69ab94e99b` /535Bİ2.
  Mənbə qrupunun adı535Bİ1dir; dəqiq mövcud816→BI2 map istifadə olunur,
  ad əsasında tələbə/qrup birləşdirməsi aparılmır.
- Mənbə14362, subject285, group788 → cari
  `3a56acc0-cb00-43ba-976a-6eae2afbe666` /535MRK.
- Hər jurnal14 real dərs:8mühazirə+6seminar,16+12=28saat.
  Mövcud28dərsdə instructor/created_byNULL-dır.
- Yerli immutable1027 müqayisəsi: köhnə immutable1027-də809xana (MRK442,BI2367), mənbə823.
  Dəqiq birləşən795xanada status/bal fərqi0dır. Qalan transfer/materialisation
  xanaları uyğunlaşdırılmır və dəyişdirilmir; bütün xanalar toxunulmaz qalır. Köhnə source-only28 və current-only14
  xananın uyğunlaşdırılması aparılmır.
- Mənbə journal inventory SHA:
  `757203ba98db56d9ad675ef8428b229354acfcf44bb9317eab66117eea3c8020`.
  Özəl mənbə/immutable graph sübut SHA:
  `dd3cabf0fc2aabb048e5bcce492dce34a18734e6d7224b9b41594fe9dd862cf2`.

BI2 üçün müsbət rəsmi yük sətri yoxdur. Mövcud filtr bu səbəbdən onu cari
load-a daxil etmir, NULL müəlliflik isə tarixçəni də boş göstərir. Bərpa
mövcud `ownhistory` yolunu aktiv edir və keçilmiş14dərs/28saatı göstərir.
BI2 “keçmiş dərslər”də görünəcək; gələcək dərs yükü/yazı səlahiyyəti verilmir.
MRK-nın hazırkı14dərs/28saat hesabatı da düzəlir.

75saatın qalan bölgüsü bu əməliyyatın hissəsi deyil. MRK source curriculum64
plan1697də45L+30S var, cari import38L+37Sdir; BI source816 curriculum126da
subject285 üçün uyğun plan yoxdur. MRK bölgüsü BI2-yə kopyalanmır.
Öz mənbə8393 mövzuları22L+22S=44saatdır; çatışmayan31saat uydurulmur.

## Təhlükəsizlik və icra

`reviewed-anar-authorship.yml` mövcud `production-deploy` mutex və production
mühitini istifadə edir. Host deployedHEAD yoxlamasını, sabit komandanı,
strict input/summary/count/error whitelist-i saxlayır. Default dry-dir.
NativeCLI: `repair_reviewed_anar_authorship --actor <aktiv-superadmin>`.

Native xidmət PostgreSQL, aktiv tenant/superadmin, dəqiq müəllim, iki course,
28dəqiq dərs və817xananın exact RAW projection hash-i tələb edir. Başqa müsbət müəllim yükü,
aktiv başqa müəllim share-i, handover, named creator, qismən instructor bərpası,
köhnə sıfır bal daxil istənilən xana dəyişikliyi və source slot dəyişikliyi HOLDdur.
Tam reversegraph və cari əlaqəli workload rows tranzaksiyada kilidlənir.

Təzə dry baseline olmadan apply mümkün deyil. Tək apply yalnız28instructor
sahəsini dəyişir; tam graphın digər sahələrinin bərabərliyi yoxlanır. Receipt
hash/count saxlayır, şəxsi məlumat və qiymət gövdəsi loga çıxmır. Repeat0dır.
Explicitundo yalnız öz applyreceipt-i və dəyişməyən tam postgraph ilə mümkündür;
automatikundo yoxdur. Source/mark pin köhnədirsə runtime HOLD verəcək; pinlər
sadəcə əməliyyatı keçirmək üçün yumşaldılmamalıdır.

Prod əməliyyatından əvvəl operator təzə iki RAW scope və standard metadata
sübutunu, sonra native dry→singleapply→repeat0→postRAW/standard tam müqayisəsini
etməlidir. Mövcud mark/source/roster istisnaları toxunulmaz qalır. Bu paket
hazırlanarkən production dispatch/apply edilməyib.

## 817 xananın yenilənmiş, etibarlı sübutu

1 noyabr RAW049/run41277551140 MRK442, RAW083/run41278064463 Bİ2375
xana göstərir. RAW024/run41277079398 ayrıca Bİ2375 nəticəsini təsdiqləyir.
Bütün28mənbə dərsi və köhnə809xana ixracın codec-i ilə tam eynidir;
əlavə8xanada `entered_by=NULL`dır. Onların insan tərəfindən yazıldığını
iddia etmirik. Heç biri silinmir, müəllifi dəyişmir və yenidən yaradılmır.
İki RAW payload SHA-sı compiled pinlərdədir. Özəl refresh proof SHA:
`7e6afe2ea3cdc5e91654805d7af9f5ba11c2271a26150cc670039290329973bb`.

Bu iki etibarlı RAW snapshot `DjangoJSONEncoder` istifadə edir: datetime
microseconds millisaniyəyə floor edilir (123456→123), UTC `Z` olur;
Decimal bal stringdir (`0.00`). Yalnız sabit817xananın və28dərsin RAW pin
müqayisəsi eyni codec ilə aparılır. Source dərslərinin sabit məzmunu və
köhnə dəqiq timestamps ayrıca yoxlanır. Native tam SQL reversegraph,
baseline, before/after preservation və undo digest bu codec-i işlətmir:
bütün database sütunları və tam microseconds qalır. Millisaniyə daxilində
123456→123457 dəyişmə belə native freshbaseline-i köhnəldir və apply dayanır.
Təzə PRE ixracı yenə məcburidir; bu817pin sonrakı dəyişikliyi qəbul etmir.
