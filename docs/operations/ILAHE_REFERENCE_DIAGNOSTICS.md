# İlahə336T1: yalnız təzə metadata diaqnostikası

Standart `export_wcu_workload_snapshot` şifrəli, `REPEATABLE READ READ ONLY`
exportuna üç ayrıca açar əlavə olunur: `ilahe_reference_graph`,
`ilahe_subject_cohorts`, `ilahe_typed_maps`. Mövcud genişlənən snapshot formatı
və şifrələmə müqaviləsi saxlanır. Bu collector heç bir yük, jurnal, cədvəl,
qiymət və sillabus yazmır, rebind icazəsi vermir.

Sabit əsas yük sətri `d835f4a8-6b30-4776-b998-6480960cadd1`, jurnal
`caad2073-173d-48e1-89fd-3c4405c4b87d`, müəllim7776, semestr2026/27 payızdır.
QKU535/536-nın həmin semestrdəki bütün təşkilatdaxili bounded cohortları və
yük sətrləri götürülür; başqa müəllim və gözlənilməyən qrup gizlədilmir.
336T2 üçün təzə metadata-da görünmüş sibling
`f1882bc7-c5d0-43ac-ba3f-7ce8c30f4e76` ayrıca sabit kökdür.

Reverse graph bütün hidden M2M əlaqələrini, bağlı və paylaşılan sillabusların
bütün versiya/section referenslərini saxlayır. Çıxış yalnız PK/FK, lifecycle,
say və tam-sətir hash-ləridir; qiymət, topic, tələbə adı və sillabus mətni
çıxarılmır. İnsan qaralamaları və köhnə təsdiqlənmiş məzmun dəyişmir.

Typed map source namespace `myedu_mariadb` ilə dəqiq aşağıdakı açarlar üçün
yoxlanır: worker209 və worker_materialisation209, group_unit934/935,
lesson_subject535/536, course_offering15047/15051,
syllabus_document8668/6117. Eyni rəqəmli başqa entity namespace alias sayılmır.
Çatışmayan mapping, yanlış model/target/state, etibarsız UUID və cari tenantda
olmayan target ayrıca görünür. Sillabus8668 doğru direct source namizədidir;
6117 tarixi ikinci hissə məzmunu kimi yalnız nəzərdən keçirilir və qorunur.

İstənilən real düzəlişdən əvvəl bütün yeni graph, map və conflict cohortları
ayrıca nəzərdən keçirilməlidir. Leyla collector açarları və writer qoruyucuları
bu collector-dan asılı deyil.
