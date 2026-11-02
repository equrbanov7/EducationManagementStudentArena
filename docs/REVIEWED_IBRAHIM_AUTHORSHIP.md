# İbrahim Yaqublu — yalnız sübut edilmiş tarixi dərs müəllifliyi

**Tətbiq edilməyib.** Sabit təşkilat,2026/2027 payız,8311`ibrahim.yaqublu2`,
Ibrahim Yaqublu Mail, köhnə `worker872`, mənbə jurnal14190/QKU847 ilə məhduddur.

## Səbəb və sübut

Deploydan sonra şəxsi jurnal səhifəsi500xətası vermir. Lakin müəllimdə cari yük0dır,
2026/2027 üzrə6dolu açılışın Lesson.instructor/created_by və LessonMark.entered_by məlumatları
boşdur. Buna görə həmin ilin jurnalları müəllimin öz görünüşündən kənarda qalır.
2025/2026 tarixi qeydləri işləyir; bu problem ümumi owner-fallback açmaqla həll edilmir.

14190patoku üç cari fiziki açılışa bölünüb:633(2),633(Q),633(İ). Sabit3açılışın18dərsi
və243qiymət/davamiyyət xanası mənbə ilə ID+tarix+saat+növ+status+bal səviyyəsində tam uyğundur.
Mənbədəki244sətirdən biri həqiqətən boşdur; o xanaya məlumat uydurulmur.
Mənbə worker872→8311, subject847→QKU847 və615/671/676→cari qrupların typed ledger
bağları dəqiq yoxlanılıb. Publik pin faylında tələbə şəxsiyyəti və bal yoxdur, yalnız
şəxsiyyətsiz dərs metadata-sı və dəyişiklik aşkarlayan hash-lər var.

Qalan3jurnal üzrə15dərs bu əmələ daxil deyil. Marketinq14378-də köhnə studentID-lərlə
cari roster arasında ayrıca canonical identity/merge-lineage yoxlaması lazımdır.
Tək ad oxşarlığı və ümumi say əsasında müəlliflik və qiymət yazılmır.

## Əməliyyat

Anar müəllifliyi əməliyyatının eyni qorunan pattern-i istifadə edilir:

- yalnız18sabit `Lesson.instructor_id: NULL →8311`;
- `created_by` və `entered_by` boş qalır: dərsi keçirən müəllim məlumat daxil edən şəxslə eyniləşdirilmir;
- başqa müəllifli və ya qismən əvvəlcədən dəyişmiş dərslər bloklanır;
- bütün243xana, qeydiyyatlar, q/b, proqram/status, sillabus, yük və jurnal sahibi dəyişmir;
- cari yük və gələcək yazı girişi verilmir; yalnız sübut edilmiş tarixi dərslər müəllimə görünür;
- live tenant/RBAC, aktiv müəllim, açıq cari period, source bridge, müəllim/qrup/fənn tam uyğunluğu;
- yeni Lesson, yeni xana, başqa müəllim bölgüsü/share/handover və sonradan dəyişmiş qiymət varsa əməl dayanır;
- fullSQLreverse graph fresh baseline ilə mikrosekund səviyyəsində qorunur; sourceRAWhash ayrıca yoxlanılır;
- audit receipt, idempotent təkrar və dəqiq NULL-a geri qaytarma var.

Workflow: **Reviewed İbrahim fixed source lesson attribution**. Əvvəl CI/deploy bitir;
workflow yalnız işləyən konteynerin HEAD-i bu commitə uyğundursa davam edir.
Dry-run→baseline, sonra `apply=true`, `confirm=APPLY`. Geri alma üçün receiptUUID+freshundo baseline.

```sh
python manage.py repair_reviewed_ibrahim_authorship --actor OPERATOR
python manage.py repair_reviewed_ibrahim_authorship --actor OPERATOR --apply --expected-baseline FRESH_SHA
python manage.py repair_reviewed_ibrahim_authorship --actor OPERATOR --undo RECEIPT_UUID
python manage.py repair_reviewed_ibrahim_authorship --actor OPERATOR --undo RECEIPT_UUID --apply --expected-baseline FRESH_UNDO_SHA
```

Tətbiqdən sonra müəllimin öz hesabında `Əvvəlki jurnal qeydlərim`→2026/2027 açılmalı,
633patokunun3fiziki jurnalı hərəsi6dərs/12saat tarixi kimi görünməlidir. Cari yük yenə0qalır.
Tarixi hüceyrələr dəyişmir; normal jurnalın başqa müəllimə aid məlumatlarına giriş genişlənmir.

Ayrıca UI commit tarixi görünüşdə faktiki `Lesson.instructor=user` olduqda `entered_by=NULL`
xanalarını yalnız oxunan göstərir və «Daxil edən şəxs məlum deyil» işarəsi qoyur. Şəxsin
`created_by` olması təkbaşına bu xanaları açmır; başqa müəllimin daxil etdiyi qeydlər
öz müəllifliyi kimi təqdim edilmir və bu görünüşdə gizli qalır. Mənbə müəllifliyi NULL saxlanır;
normal jurnalın yazı və roster/final qiymət səlahiyyətləri artırılmır.
