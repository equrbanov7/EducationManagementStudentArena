# Tam boş 132 F dublikatı üçün məhdud bərpa

Bu command yalnız WCU/QKU təşkilatında legacy `388` → `367` cütünü əhatə edir:
`6edca0eb-0ad6-4c2d-aa5e-83cbec3e69d1` (`132 F`) →
`86a79572-7de8-45d0-a800-bec9d918d58e` (`132F`). Production-da icra edilməyib.

2026-11-01 read-only köhnə clone yoxlamasında hər iki source group-un specialty=21,
University, Əyani, curricula=117, bachelor, az, start_year=2022 və department=11
sahələri eyni idi. Legacy388-də heç bir tələbə yoxdur;367-də7 tarixi tələbə var.
2026-10-31 cari export-da mənbənin student academic record/enrollment dəsti boşdur.
Köhnə clone-da OrgUnit-a istinad edən40 FK sahəsinin hamısı yoxlanıb və388-in
hədəf OrgUnit-ına heç bir istinad tapılmayıb. Bu müşahidələr cari production üçün
boşluq zəmanəti deyil: command bütün FK/one-to-one və gizli M2M through modellərini
`_base_manager` ilə yenidən yoxlayır; hər hansı əlaqə apply-ni dayandırır.

Command məlumat köçürmür/silmir. Yalnız mənbənin `is_active=False` və
`settings.canonical_group=<target>` sahələrini dəyişir. Hədəfə və tarixi tələbələrə
toxunmur. Tam raw `settings` daxilində legacy provenance, admission year, language
sector və əlaqəsiz nested metadata saxlanılır; export-un üç-sahəli proyeksiyası
raw settings əvəzinə yazılmır. Mənbə/hədəfin reviewed legacy ID/cohort metadata-sı
yenidən yoxlanır. KE233 alias resolution registry-si dəyişmir; bu boş source üçün tarixi
jurnal əlaqəsinin canonical həllinə ehtiyac yoxdur.

Əvvəl uyğun environment və active superadmin ilə dry-run icra edin, tam JSON
snapshot-ı saxlayın:

```sh
python manage.py repair_empty_132f_alias --org qku --actor USER > before.json
```

CI/workflow logları üçün `--summary` əlavə edin: snapshot çıxarılmır, yalnız
`empty132f: mode=... baseline=... blocked=0|1 applied=0|1 receipt=none|UUID` yazılır.
Tam snapshot yalnız ayrıca private faylda saxlanılmalıdır.

`blocked=false` olmalıdır. Sonra dry-run-dakı exact `baseline` istifadə edilir:

```sh
python manage.py repair_empty_132f_alias --org qku --actor USER \
  --apply --expected-baseline BASELINE > after.json
```

Apply PostgreSQL tələb edir; eyni transaction-da source/target lock edilir,
metadata, legacy mapping və bütün əlaqələr yenidən yoxlanır. `AuditLog` bütün
source/target concrete field snapshot-larını, batch ID-ni və əməliyyatı saxlayır.
Undo əvvəl cari dry-run baseline-ını alır, sonra apply receipt batch-ini qəbul edir:

```sh
python manage.py repair_empty_132f_alias --org qku --actor USER
python manage.py repair_empty_132f_alias --org qku --actor USER \
  --apply --expected-baseline CURRENT_BASELINE --undo APPLY_BATCH
```

Undo yalnız receipt-dəki exact after snapshot dəyişməyibsə işləyir. Yeni əlaqə,
hədəf/metadatanın dəyişməsi və ya təkrar undo əməliyyatı rədd edilir.

## Digər namizədlər niyə bu plana daxil deyil

- `2535 Bİ` legacy784 və `132 P` legacy387: köhnə clone-da hər birində bir
  CourseOffering var; sıfır active student/journal onları tam boş etmir.
- `233 İ rus/RUS` legacy600/588: source department24/51 fərqlidir.
- `213/5 BM` legacy819/821: köhnə source groups cədvəlində yoxdur;
  cohort/source identity sübutu tamamlanmayıb.
- `132 T/132T`: fərqli enrolled tələbələr və tarixi qeydlər var.
- `532 TB/532TB`, `532 T ing`: graduation/academic history var.
- `235 K`: dublikat namizədində iki jurnal var.
- `Kollec`: eyni adlı faculty və specialty ayrı struktur vahidləridir.
- `233KE`: əvvəlki ayrıca bərpa/alias planı ilə idarə olunur.
