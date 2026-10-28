# 235 SBİO üzrə dar yük bərpası

2026/2027 payız, İnformatika, Rəna Hacıyeva (7721). Mənbə: 25 sentyabr
Forma 1, 29 sentyabr 16:19 poçt qəbulu; cədvəlin 6-cı sətri: 30 mühazirə,
15*2 seminar. Mənbə SHA256:
`7630be3cbe9bfe7050e2f308fae8c4959c35bd298967f5e3f2b77a0ab4a9cb09`.

`repair_sbio235_workload` yalnız kodda sabit təşkilat, task, subject, dövr,
iki load sətri və iki açılışı qəbul edir. Valideyn/alt qrup əlaqələri reyestrdən
sübut edilir. Başqa hədəf, müəllim, mənbə və ya yeni jurnal qəbul etmir.

Əvvəl: anchor yalnız SBİO-1-ə bağlıdır, 30 mühazirə + 30 seminar cəmi,
seminar planı15, subgroup_count2; əlavə SBİO-2 sətri33+12-dir.
Sonra: anchor mövcud SBİO-1 və SBİO-2-yə bağlanır, 30 mühazirə axını,
hər alt qrupa15 seminar (cəmi30); əlavə load sətri auditli backup ilə silinir.
Hər iki jurnalın sahibi7721 və semestr saatı45 saxlanır.

Task AMENDED qalır; ümumi təsdiq çağırılmır. Distributed metadata, mövcud
amendments, reviews, objections və slices dəyişmir. Canonical save_row-un avtomatik
sinxronu bu atomik paketdə təxirə salınır, sonra yalnız hədəf sətirlərin dar
`sync_task_offerings(create=False)` keçidi edilir. Yeni/yenilənmiş açılış sayı0 olmalıdır.

## İcra

Aktiv superadmin aktoru ilə:

```sh
python manage.py repair_sbio235_workload --org qku --actor USER \
  --source-sha256 7630be3cbe9bfe7050e2f308fae8c4959c35bd298967f5e3f2b77a0ab4a9cb09
```

Defolt dry-run bütün eyni yazı yollarını tranzaksiyada sınayıb geri alır.
Çıxışdakı `baseline` təzə dry-run-dan götürülür. Tətbiqə `--apply
--expected-baseline HASH` əlavə edilir; dəyişmiş baseline rədd olunur.
ProdDataOps whitelist: `repair_sbio235_workload`, `batch=baselineSHA`,
`apply=true`, `confirm=APPLY`; source hash workflow-da sabitdir, encrypted plan yoxdur.

Undo preview: `--undo sbio235-…`; tətbiq üçün onun fresh baseline-ı da verilir.
Workflow: preview `batch=sbio235-…`; apply `batch=sbio235-…:baselineSHA`.
Audit receipt-dən əvvəlki load sətrləri və assignment ID-ləri bərpa olunur.
Sonrakı workload/task/history dəyişibsə undo dayanır. Sonradan əlavə olunan
akademik qeydlər saxlanır: undo vaxtının öz əvvəl/son akademik fingerprinti eyni olmalıdır.

Hər iki istiqamətdə tam-field count+SHA yoxlaması jurnal, müəlliflər,
qiymət/davamiyyət, enrollment, syllabus/version/sections/reviews, paylaşım,
təhvil, selfwork və yekun/komponent ballarını qoruyur. Başqa row/offering və ya
qorunan məzmun fərqində bütün paket rollback olunur. Audit yalnız fingerprint
və workload backup saxlayır; stdout yalnız saylar, baseline və opaque batch çap edir.
