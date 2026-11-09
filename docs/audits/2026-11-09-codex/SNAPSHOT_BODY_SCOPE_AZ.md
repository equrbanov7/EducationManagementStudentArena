# Cari sillabus gövdələrinin ixrac sərhədi

Native oxu-yalnız ixrac bütün tenantın bütün tarixli sillabus gövdələrini
daşıdıqda ümumi 512 MiB həddində dayandı. Hədd artırılmır. Yeni seçim siyasəti
`schemas.json` hash-ına və manifestin gövdə cədvəlinə daxil edilir:
`current-period-all-offerings-nonarchived-and-referenced-lineage/1`.

Yalnız `SyllabusSection` sətirləri versiya seçimi ilə
məhdudlaşır. Bütün tenantın sillabus başlıqları, bütün versiya və paylaşım
metadatası, bütün `SyllabusReview` qərar tarixçəsi əvvəlki kimi qalır. Bal, dərs, xəritə, apellyasiya, tarixi final və
digər cədvəllərin sorğuları dəyişmir.

Köklər bütün cari semestr açılışlarıdır; qeyri-aktiv və birləşmədən əvvəlki
jurnallar çıxarılmır. Cari semestr dosyeləri, bağlı dosyelər, paylaşım və dil
kohortunun mənbə dosyeləri, eyni fənn+müəllim üzrə digər semestr/baza namizədləri
daxildir. `reused_from`, bütün versiyaların `source_version` zənciri və
current/approved istinadları donorların köhnə semestrinə qədər izlənir.

Bu əlaqələrdə arxivlənməmiş bütün versiyaların gövdələri saxlanılır; qaralama,
təqdim edilmiş, baxışda, düzəliş tələb olunan, təsdiqlənmiş və rədd edilmiş
versiyalar buna daxildir. Arxiv versiyası current/approved istinadı və ya
mənbə-versiya əlaqəsi ilə istifadə edilirsə onun gövdəsi də saxlanılır.
Əlaqəsiz köhnə və istinadsız arxiv gövdələri bu proyeksiyaya daxil deyil.

Ona görə həmin gövdənin ixracda olmaması boş sillabus və ya itmiş məlumat
sübutu deyil. Offline batch helper bütün metadata ilə əvvəlki kimi əlaqəli
komponentləri qurur; köhnə semestrə/qeyri-aktiv və icazəsiz açılışa yayılan
komponentlər hold qalır. Bu ixrac universal sillabus tarixçəsi arxivi deyil.

Canlı sillabus dry/apply/undo əmrləri hər reviziyanın tam gövdəsini yenə
PostgreSQL-dən oxuyur, kilidləyir və qorunan tarixçə fingerprint-inə daxil edir.
İxrac həmin native qraf, təzə baseline, receipt və geri qaytarma sübutlarını
əvəz etmir. RLS, oxu-yalnız RR transaction, sətir/bayt/vaxt hədləri dəyişmir.
