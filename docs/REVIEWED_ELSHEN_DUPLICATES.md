# Elşən Əmrahov — 345 saat təkrar yükün çıxarılması

Mənbə: Yer kadastrı və meşəçilik kafedrasının `Dərs yükü` vərəqi, 55–64-cü sətirlər; XLSX SHA256 `5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d`. Rəsmi cəm **195 mühazirə +375 seminar =570 saatdır**. `15*2`, `15*4`, `15*6` vurucuları cəmi müəllim yükü kimi nəzərə alınır.

Cari 19 sətirdə 885 saat var: köhnə importun 10 təkrar sətri 18 müsbət bölgü ilə əlavə345 saat yaradır. Ayrı, hazır `civil_source_partition` əməliyyatının 60-cı mənbə sətri çatışmayan30 saatı bərpa edir. Buna görə bu əməliyyat **yalnız civil-partition tətbiqindən sonra** işləyir: **915−345=570**.

Əvvəlcə beş saxlanan rəsmi sətrin qrup əlaqələri UI-də düzəldilib: TSPX1+2; faktiki336F1/F2/T1/T2; faktiki635Qrafik/İnteryer;533T2-nin mövcud patoka daxil edilməsi; müəllimin MR131 göstərişinə əsasən236EKO əvəzinə236BİO+BT. Bu əlaqələr və dəyişməz rəsmi saatlar native əməliyyatda ayrıca məcburi şərtdir. SI alt qrupları qeydiyyatdakı ana əlaqədən açılır.

18 `TeacherAssignment` normal `unassign(sync_offerings=False)` ilə çıxarılır; 10 köhnə yük sətri saxlanılıb yalnız auditoriya tutumu sıfırlanır. Bölgüyə `hours=0` yazılmır — DB bunu qadağan edir. Jurnal sahibi, fiziki jurnal, tələbə, dərs, bal,0bal,q/b,i/e,üzrlü qeyd, imtahan və sillabus dəyişdirilmir. Tam akademik əlaqə qapanması əməliyyatdan əvvəl/sonra müqayisə edilir; əlavə fərq olsa bütün tranzaksiya geri qaytarılır.

## İcra

Yalnız bu kod prod-a deploy olunduqdan və əvvəlki civil-partition yoxlama/tətbiqindən sonra `Reviewed Elşən duplicate workload cleanup` workflow-u çağırılır. Operator deploy olunmuş HEAD-i yoxlayır. Default dry-run normal domain əməliyyatlarını atomik sınaqdan keçirib **rollback** edir.

```bash
python manage.py repair_reviewed_elshen_duplicates --actor OPERATOR
python manage.py repair_reviewed_elshen_duplicates --actor OPERATOR --apply --expected-baseline FRESH_SHA256
```

Workflow inputları: `actor`; tətbiq üçün təzə `baseline`, `apply=true`, `confirm=APPLY`. Gözlənilən nəticə:10sətir,18bölgü,345saat, müəllim915→570. Təkrar icra0dəyişiklik verir. Əvvəlki ümumi18bölgü tam metadatası və ilkin PK-ları ilə receipt-də saxlanılır.

```bash
python manage.py repair_reviewed_elshen_duplicates --actor OPERATOR --undo RECEIPT_UUID
python manage.py repair_reviewed_elshen_duplicates --actor OPERATOR --undo RECEIPT_UUID --apply --expected-baseline FRESH_UNDO_SHA256
```

Geri alma yalnız tətbiqdən sonrakı tam vəziyyət dəyişməyibsə mümkündür; həmin18PK və tarixlər bərpa olunur. Sonradan müəllim xana yazıbsa və ya əlaqəli məlumat dəyişibsə köhnə receipt ilə geri alma qəbul edilmir.

## Ayrı saxlanan işlər

Bu əməliyyat635 tələbələrini köçürmür və köhnə dərsləri klonlamır. Mənbə student-ID→cari istifadəçi-ID uyğunluğu ilə25İnteryer/26Qrafik kohortu ayrıca sübut edilib; onların hazırda birləşmiş jurnal tarixçəsi ayrıca, təkrar q/b yaratmadan düzəldilməlidir. SI1-in23 və SI2-nin22 tələbəsi canlı reyestrdə köhnə mənbə ilə tam eynidir; ana qrupdakı əlavə Əzizə hesabları yalnız ad oxşarlığına görə birləşdirilmir. Müraciətlər bu native əməliyyat təkbaşına işlədiyi üçün avtomatik bağlanmır.
