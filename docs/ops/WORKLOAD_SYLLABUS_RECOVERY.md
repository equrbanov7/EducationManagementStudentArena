# Rəsmi yük yoxlaması: öz köhnə sillabusunun bərpası

Canlı 29Oct yoxlaması dörd məzmun namizədindən yalnız Bilal müəllimin
135T / Tarix fəlsəfəsi jurnalında boşluq olduğunu göstərdi. Arzunun QKU1499
və QKU1160, Əşrəfin QKU1409 jurnalları artıq 28Oct təsdiqli v1.0 sillabusa
malikdir; onların məzmununa toxunulmur.

`recover_workload_syllabi` yalnız aşağıdakı sabit müqaviləni qəbul edir:

- QKU / 2026–2027 payız, jurnal `6467692a-edd0-4651-9b6e-246c19bbbc40`;
- müəllif/sahib 8143, 135T qrupu `964edf4c-26ed-4bb3-b5e6-9afe70bf9712`, QKU771;
- köhnə müəllif 679, jurnal 14080, sillabus 8430, uniqid WaccQbauu5QCDnYunfZL;
- mənbə 628 «Tarixin fəlsəfəsi», jurnal 771 «Tarix fəlsəfəsi»;
- bütün 8 mövzu tarix fəlsəfəsidir;15 mühazirə + 15 seminar = 30 saat rəsmi Fəlsəfə
  faylının 5-ci sətri ilə eynidir. Mənbənin bir sərbəst iş peyk sətri boşdur: kanonik konverter sıfır tapşırıq bərpa edir, tapşırıq uydurmur. Bütün dolu bölmələr saxlanır.

Mənbə və müəllif fərqi operatorun verdiyi istənilən ID ilə genişləndirilə bilməz.
Komanda cari sahib/qrup/fənn/period/profil/icazə qapılarını və source SHA-nı
yoxlayır. Hədəfdə istənilən aktiv/passiv dosye, qaralama və ya başqa uyğun
sillabus varsa üzərinə yazılmır. Jurnal, müəllim, tələbə və qiymətlər dəyişmir.

MR46-nın bərpa nüvəsi `exact_syllabus_recovery.py` moduluna çıxarılıb.
`mr46_syllabus` public çağırışları və yalnız 8891/7942/acc97… əhatəsi saxlanır;
yeni müqavilə MR46 əhatəsini genişləndirmir.

```sh
python scripts/build_workload_syllabus_plan.py --out PRIVATE.json
python manage.py recover_workload_syllabi --org qku --actor SUPERUSER \
  --file PRIVATE.json --sha256 SHA256
# Quru yoxlama və backup-dan sonra eyni arqumentlərə --apply əlavə olunur.
python manage.py recover_workload_syllabi --org qku --actor SUPERUSER \
  --undo wksyl-YYYYMMDD-HHMMSS-xxxx --apply
```

Prod Data Ops: `command=recover_workload_syllabi`, `batch=plaintext SHA256`,
`roster_tag=workload-syllabi-…`, asset `workload-syllabi.json.enc`.
Undo üçün boş roster_tag, `batch=wksyl-…`, apply=true və confirm=APPLY tələb olunur.
Log yalnız rəqəmli sayları və opaque batch-ni göstərir. Şifrələmə, müvəqqəti
fayl təmizliyi və backup mövcud workflow müqaviləsinə uyğundur.

Audit receipti bölmə məzmunundan əlavə dosye və versiyanın bütün lokal
metadatasının hash-lərini saxlayır. Sonradan plan saatları, müəllif,
proqram/kafedra, status və ya versiya göstəriciləri dəyişsə undo dayanır.
Raw metadata və şəxsi məlumat loga çıxmır.

Undo dəyişməmiş idxalı kanonik xidmətlə arxivləşdirib dosyeni passivləşdirir;
məzmun silinmir. Sonrakı versiya, bölmə dəyişikliyi, paylaşım və reuse varsa
bütün əməliyyat yazıdan əvvəl dayanır. Eyni planın təkrar tətbiqi idempotentdir.
