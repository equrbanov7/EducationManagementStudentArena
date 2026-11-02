# Müraciətdə istənmiş ilkin parolların məhdud çatdırılması

Bu alət parol istəyən **7 müəllimə** və MR27 üzrə yaradılmış **2 magistr tələbəyə** aiddir. Ayrıca `behruz-one` yalnız7363 Bəhruz Quluzadə Kərimin9622 kodlu aktivləşməmiş hesabıdır.
`staff-seven`, `magistr-two`, `behruz-one` xaric hədəf qəbul etmir. İstifadəçi adı, dəyişməz istifadəçi ID-si,
ad/soyad/ata adı, təşkilat və aktiv rol tam uyğun gəlməlidir. Magistrlərdə tələbə kodu
10127/10128, cari 510/6BİEO magistr qrupu və qeydiyyat statusu da yoxlanılır.

Mənbə: magistr/kafedra problem blankları, 27 oktyabr şəxsiyyət müqayisəsi, MR27-in
30 oktyabr bərpası, 1 noyabr `chair-cells-040-part-002` mapping ledger-i və 2 noyabr canlı RİM
kartları. Magistr ID-ləri12030/12031 ayrıca canlı RİM-də təsdiqlənib. Vəfa/Türkan ad
uyğunsuzluğuna görə daxil edilməyib; digər4 giriş şikayəti aktiv hesab diaqnostikasıdır.

Aktivləşmiş, bloklanmış, arxivdə və silinmiş hesabların parolları dəyişmir. Arxiv və ya
akademik status bərpa olunmur. `force`, fakültə və sərbəst istifadəçi siyahısı yoxdur.
Yalnız aktivləşməmiş hesabda mövcud `issue_staff_credentials._issue` ilk-giriş axını
istifadə edilir: e-poçt/OTP və şəxsi yeni parol yenə tələb olunur.

## İcra

Əvvəl CI və deploy tamamlanmalıdır. Workflow deploy olunmuş HEAD-i yoxlayır.
`Reviewed targeted pending credentials` daxilində uyğun batch ilə dry-run edin; sonra
həmin SHA256 baseline, `apply=true`, `confirm=APPLY` ilə tətbiq edin. Arada hesab,
parol hash-i, aktivləşmə, şəxsiyyət və ya üzvlük dəyişibsə əməl dayanır. İcra zamanı
User/Profile/Membership/SAR kilidləri aktivləşmə yarışından qoruyur.

CLI (eyni təşkilatın aktiv superadmini):

```sh
python manage.py issue_reviewed_targeted_credentials --actor OPERATOR --batch magistr-two
python manage.py issue_reviewed_targeted_credentials --actor OPERATOR --batch magistr-two --apply --baseline FRESH_SHA --public-key PUBLIC_PEM --output NEW_ENCRYPTED_FILE
```

Açıq parol stdout/stderr-ə və diskə yazılmır. CSV RAM-də hazırlanır, mövcud pinned
RSA-OAEP/AES-256-GCM ixrac protokolu ilə konteynerdə şifrələnir. Runner yalnız təsdiqlənmiş
şifrəli zərfi götürür. Artifaktın saxlanması1gündür. Xəta olarsa çıxış loga açılmır.

Yalnız yerli səlahiyyətli operator şəxsi açarla belə açır (çıxış0600, mövcud fayl əvəz edilmir):

```sh
python scripts/ops/decrypt_targeted_credentials.py --input credentials.enc.json --private-key PRIVATE_PEM --output NEW_PRIVATE_CSV
```

CSV sütunları: **Ad soyad ata adı → username → ilkin parol**. Sonra yalnız müvafiq müraciət
sahibinə çatdırılmalıdır. Parollar git və ümumi hesabatlara daxil edilməməlidir.

## Bəhruz: ayrıca akademik uyğunsuzluq

`behruz-one` canlı olaraq təsdiqlənmiş **404/5IHT / İqtisadiyyatın tənzimlənməsi / academic_leave** vəziyyətini baseline-ə daxil edir və dəyişmir. Bu, göndərilmiş rosterdəki proqram uyğunsuzluğunu həll etmir. Logdakı `academic_review_required=1` həmin formal yoxlamanın açıq qaldığını bildirir. Yalnız ilkin giriş parolu verilir; tələbə bərpası, proqram dəyişikliyi və imtahan buraxılışı edilmir.
