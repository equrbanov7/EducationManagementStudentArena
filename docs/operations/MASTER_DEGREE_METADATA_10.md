# Magistratura dərəcəsinin 10 sətirdə düzəldilməsi

`repair_master_degree_metadata` yalnız sabit reyestrdəki on yük sətrinin
`degree_level` sahəsini `bachelor` → `master` dəyişir. Saat, ödəniş,
kredit, müəllim bölgüsü, qrup, jurnal, tələbə, qiymət və sillabus dəyişmir.
Model `save()` və jurnal sinxronizasiya servisləri çağırılmır.

Mənbə: “Magistratura şöbəsinin I kurs üzrə dərs cədvəli”, 15 sentyabr 2026.
SHA-256: `144e19ff80b04eaa33260a2a116ddd195ea5169064ce437973461cbeeb1f2a2c`.
Mənbə qrupun magistratura səviyyəsini təsdiqləyir; müəllim və saat bölgüsünün
dəyişdirilməsi üçün istifadə olunmur.

Əməliyyat təşkilatın aktiv superadmin aktorunu, PostgreSQL-i, sabit qrup/fənn/
dövr/tapşırıq kimliklərini, bütün qrupların açıq `master` metadatasını və hər
qrupun canlı aktiv akademik qeydlərində magistr proqramını tələb edir.
Boş akademik qeyd, başqa proqram səviyyəsi və dəyişmiş kimlik əməliyyatı dayandırır.

Dry-run standartdır və yalnız baseline, say, status və receipt çıxarır:

```sh
python manage.py repair_master_degree_metadata --actor ACTOR
```

Yoxlanmış dry-run baseline-i ilə tətbiq:

```sh
python manage.py repair_master_degree_metadata --actor ACTOR --apply --expected-baseline SHA256
```

Audit receipt-i tam əvvəlki/sonrakı yük vəziyyətini və qorunan akademik
məlumatların heşlərini saxlayır. Eyni receipt vəziyyətində təkrar tətbiq no-op-dur.
Geri qaytarma əvvəlcə ayrıca dry-run-dan keçir:

```sh
python manage.py repair_master_degree_metadata --actor ACTOR --undo APPLY_RECEIPT
python manage.py repair_master_degree_metadata --actor ACTOR --undo APPLY_RECEIPT --apply --expected-baseline SHA256
```

Sonrakı bölgü, qiymət, sillabus və digər qorunan dəyişiklik undo-nu dayandırır.
Geri qaytarma da yalnız dərəcə sahəsini əvvəlki vəziyyətə gətirir.

Qadir müəllimin iki mövcud jurnalının ayrıca GET tarixçəsi cari yük təyinatı
yaratmır. Yalnız sabit jurnal kimliyi, cari kanonik sahiblik və aktiv tenant
icazəsi ilə açılır; anonim köçürülmüş qeydlər müəllifin dərs saatına yazılmır.
