# MR-000046: müəllimin köhnə jurnal sillabusunun bərpası

`recover_mr46_syllabus` yalnız QKU-nun 2026/2027 payız dövründəki
`acc97b99-90bc-4fb3-b01b-b56ff630b7d2` jurnalına mənbə 8891 sillabusunu
bərpa edir. Müəllif 7942-dir. Mənbə müəllifi 442 olan 15363 jurnalında
`sillabus_id=8891`, fənn 1500 göstərilib; sillabus başlığında köhnə fənn 457-dir.
Müəllimin öz köhnə sillabusunu istəməsi və sistem sahibinin bu konkret bərpanı
təsdiqləməsi həmin uyğunsuzluğun audit əsasını təşkil edir. Qlobal fənn və
müəllim xəritələri dəyişmir.

Kanonik sillabus konverteri və `import_migrated_version` istifadə olunur.
23 mövzu, 18 sərbəst iş və bütün 10 bölmənin tam JSON məzmunu saxlanır.
Versiya `approved`, təsdiq mənbəyi `migration` olur; başqa şəxsin təsdiqi
uydurulmur. Hədəfdə sillabus varsa yazı dayandırılır. Digər müəllimlərin eyni
fənnə aid sillabusları və jurnal sahibliyi dəyişmir. Cari müəllifin aktiv
müəllim icazəsi, profil girişi və jurnal sahibliyi və ya mövcud legacy paylaşımı
yoxlanılır. Canlı jurnala 28 oktyabrda təhvil verilmiş sahib 7942-dir;
27 oktyabr snapshotında əvvəlki sahibin qalması canlı vəziyyət sayılmır.

## Mənbə və tətbiq

`scripts/build_mr46_syllabus_plan.py --out PRIVATE.json` lokal read-only
legacy Docker mənbəsindən 0600 JSON çıxarır. Faylın SHA-256 dəyəri tələb olunur.
Məzmunu və şəxsi məlumatları açıq iş loguna çıxarmayın.

```sh
python manage.py recover_mr46_syllabus --org qku --actor SUPERUSER \
  --file PRIVATE.json --sha256 SHA256
# Eyni arqumentlərlə --apply yalnız backup və quru yoxlamadan sonra.
```

Standart rejim bütün yazıları transaction rollback ilə yoxlayır. Tətbiq auditə
mənbə/hədəf ID-lərini, bölmə hash-lərini və `mr46-YYYYMMDD-HHMMSS-xxxx`
batch-ni yazır. Eyni SHA ilə təkrar tətbiq yalnız əvvəlki təsdiqli məzmun
qorunubsa `already_present=1` qaytarır.

Prod Data Ops: `command=recover_mr46_syllabus`, `batch=SHA256`,
`roster_tag=mr46-syllabus-...`; release asset `mr46-syllabus.json.enc`.
Mövcud şifrələmə, backup və APPLY təsdiqi müqavilələri saxlanılır.

## Auditli geri alma

```sh
python manage.py recover_mr46_syllabus --org qku --actor SUPERUSER \
  --undo mr46-YYYYMMDD-HHMMSS-xxxx --apply
```

Yalnız bu batch-in dəyişməmiş tək versiyası, əlavə paylaşımı olmayan sillabus
arxivləşdirilir və passivləşdirilir. Mənbə məzmunu silinmir. Yeni versiya,
bölmə dəyişikliyi və ya paylaşım varsa bütün əməliyyat dayanır. Workflow-da
undo üçün `apply=true`, `batch=mr46-...`, boş `roster_tag` istifadə olunur.
