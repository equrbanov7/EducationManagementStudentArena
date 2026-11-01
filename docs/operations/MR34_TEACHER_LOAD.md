# MR-000034: mövcud jurnal sahibinin yük təyinatını uyğunlaşdırmaq

Bu komanda yalnız təsdiqlənmiş MR-000034 dublikat hesab keçidindən sonra
qalmış beş `TeacherAssignment` qeydini `11588` hesabından mövcud jurnal sahibi
`9510` hesabına bağlayır. Sabit seçim `mr34_teacher_spec.py` modulundadır:
üç rəsmi yük sətri, beş təyinat, cəmi 135 saat. Yeni təyinat yaradılmır.

Təsdiq sənədinin SHA-256 izi:
`fbdce9adf89e3b0af72afbc64e7f5face1743edce7cf225cbfa4f649b7bcf934`.
Şəxsiyyət müqaviləsi bu konkret təsdiqə və iki hesabın tam ad üçlüyünün
hash-lərinə əsaslanır; soyad oxşarlığından ümumi hesab birləşdirməsi etmir.

## Yoxlama və tətbiq

Aktiv superadmin istifadəçi adı ilə əvvəlcə yalnız oxuyan hesabat alın:

```bash
python manage.py repair_mr34_teacher_load --actor ACTOR
```

Nəticədəki `baseline` bütün qorunan cari qrafın izidir. Hesabatı nəzərdən
keçirdikdən sonra məhz həmin izi tətbiqə verin:

```bash
python manage.py repair_mr34_teacher_load --actor ACTOR --apply --expected-baseline BASELINE
```

Tətbiq atomikdir və mərkəzi `assign_amended` yolu ilə ayrıca düzəliş tarixçəsi
yaradır. Mövcud beş jurnalın hamısının sahibi artıq `9510` olmalıdır. Tenant,
dövr, fənn, qrup, fəaliyyət və saat pinləri; aktiv profil və `grade.input`
səlahiyyəti; əllə təhvil/share qrafı; əlavə təyinatın olmaması yoxlanır.
Cari vəziyyət dəyişibsə tətbiq dayanır. Təkrar tətbiq `already_canonical`
qaytarır.

AZ kafedrasına yeni üzvlük və ya rol verilmir. Normal müəllim təyin etmə yolu
öz kafedra qəbul yoxlamasını saxlayır. Daxili authority yalnız bu beş mövcud
təyinat üçün, pinlənmiş sahibə və eyni actor/tenant daxilində işləyir.
Daxili authority verildiyi DB bağlantısı və PostgreSQL tranzaksiyasına
bağlıdır; başqa tranzaksiyada təkrar istifadə edilə bilməz.

## Geri qaytarmaq

Tətbiqin `receipt` dəyəri ilə yeni yalnız oxuyan yoxlama alın:

```bash
python manage.py repair_mr34_teacher_load --actor ACTOR --undo RECEIPT
```

Sonra bu yoxlamanın yeni `baseline` dəyərindən istifadə edin:

```bash
python manage.py repair_mr34_teacher_load --actor ACTOR --undo RECEIPT --apply --expected-baseline BASELINE
```

Geri qaytarma yalnız tətbiqdən sonrakı qraf tam eyni qaldıqda mümkündür.
Yeni qiymət, jurnal qeydi, üzvlük və ya başqa qorunan dəyişiklik geri
qaytarmanı saxlayır. Köhnə audit qeydləri silinmir.

Hər iki istiqamətdə dərs, qiymət, i/e, q/b, tələbə qeydiyyatı, SAR, saat,
qrup, cədvəl, sillabus, rol və üzvlüklər qorunur. `sync_offerings=False`
sayəsində jurnal sahibinin və share-lərin avtomatik dəyişdirilməsi çağırılmır.
Bu əməliyyat köhnə 46 dərs/730 qiymət hüceyrəsinin cari saxlanmasını saylardan
sübut etmir; onların ayrıca UUID üzrə müqayisəsi tələb olunur.
