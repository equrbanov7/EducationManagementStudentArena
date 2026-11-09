# Sillabus gövdələri və akademik məlumat ixracı

Bütün tenantın sillabus gövdələri 512 MiB həddini aşdı. Cari jurnal/donor
zənciri ilə daralma da kifayət etmədi. Hədd artırılmır. `SyllabusSection`
cədvəlində yalnız `data` gövdəsi bu ixracdan çıxarılır; bütün təşkilatın bütün
bölmə sətirlərinin metadatası, başlıqları, versiyaları, paylaşım əlaqələri və
`SyllabusReview` qərar tarixçəsi bütöv saxlanır. Digər77cədvəlin sorğuları və
sahələri dəyişmir; ballar, iştirak, mapping/version, audit və tarixi final
məlumatlarının əhatəsi sillabus gövdəsindən asılı deyil.

Siyasət schema hash-ına və manifestə bağlanır:
`body_policy=metadata-only-bodies-deferred-to-native-connected-batches/1`,
`body_complete=false`, `excluded_body_fields=["data"]`. Decoder bu məlumatları
schema ilə yoxlayır. Bu capture metadata/akademik sətirlər üzrə tamdır;
**sillabus məzmunu üzrə tam deyil**. Gövdənin ixracda olmaması boş sillabus və
ya itmiş məzmun kimi şərh edilə bilməz. Offline məzmun tamlığı qərarı UNKNOWN
qalmalıdır; metadata batch planner məzmunu təsdiqləmir.

Sillabus source packet-i dəqiq legacy mənbədən ayrıca hazırlanır. Canlı native
syllabus dry/apply/undo hər explicit əlaqəli batch üçün bütün reviziyaların
**tam gövdələrini** PostgreSQL-dən oxuyur, kilidləyir və qorunan tarixçə
fingerprint-inə daxil edir. Batch≤100, donor və tarixçə closure-u, təzə baseline,
ehtiyat nüsxə, receipt və repeat şərtləri dəyişmir. Metadata ixracı bu yoxlamanı
əvəz etmir; lazımi body oxunmadan sillabus nə təsdiqlənir, nə də yayımlanır.

Oxu-yalnız RR transaction, RLS, sətir/bayt/vaxt hədləri əvvəlki kimidir.
