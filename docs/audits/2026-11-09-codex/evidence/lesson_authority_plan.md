# Çatışmayan dərs hadisələri üçün mənbə planı

2026-11-09 yalnız SELECT oxunuşu `lesson_authority_probe.py` ilə təkrarlanır. Mənbə MariaDB repeatable-read / READ ONLY tranzaksiyadır; tətbiq bazasına qoşulmur. İstifadə edilən əvvəlki current capture Stage1-dir; yeni full capture gələndə target route və maskalar yenidən yoxlanmalıdır.

247 aktiv/enrolled baxış sətri 247 fərqli source point və **24 unikal offering × source journal × date × start × kind** hadisəsidir. Hər24 hadisədə point-in tələbə ID-si, tarix, başlanğıc və növü əvvəlki audit sətri ilə üst-üstə düşür. Hər24 hadisənin tək `fake=0` rooms metadata sətri var; metadata tarix/növü də uyğundur. `saatliq_ders=1` yerli köçürmə müqaviləsinin 2024-02-01-dən sonrakı cüt semantikasında **2 akademik saatdır**. Saat burada default deyil.

19 hadisədə teacher-added tarix sətri təkdir; 5-də duplicate tarix sətri var. Point və rooms eyni hadisəni göstərdiyi üçün duplicate tarixlər ayrıca dərs kimi çoxaldılmır.

Legacy journal/point/room cədvəlləri bitmə vaxtını saxlamır. `end_time=None` məlumatı olduğu kimi saxlayan Lesson bərpasıdır; 80/90 dəqiqə əlavə edib son vaxt uydurulmur. ScheduleSlot yaradılmır. Legacy `ders_cedveli` 433 sətir, son əlavə 2023-02-20, from/to tarixləri boşdur; bu cədvəl 2026 dərs intervalı üçün authority deyil.

## Prioritet seçimi

| Mənbə hadisələri | Slot | Cari baxış sətri | Qərar |
|---|---:|---:|---|
| Ən azı bir real iştirak/numeric qiymət | 7 | 173 | Fresh route, roster/maska və cleanup yoxlanandan sonra bərpa namizədi |
| Yalnız QB/boş | 17 | 74 | Sahibin yeni owner_present siyasəti: exact current route/roster/maska varsa dərs bərpa olunur, uyğun source QB yalnız yeni boş xanada i/ə kimi nəzərdən keçirilir |

`absent_only_not_created` tarixi import qaydasıdır və bu17 slotu yeni sahib göstərişinə qarşı avtomatik istisna etmir. Yeni plan həmin QB source ID-lərini ayrıca review siyahısına çıxarır; private native manifestdə yalnız bu ID-lərdə `certain=false` + owner-policy səbəbi tətbiq olunur. Raw source, numeric qiymətlər (0 daxil), əl ilə düzəlişlər və mövcud rəsmi qiymətlər dəyişdirilmir.

7 prioritet hadisədə numeric qiymət sübutu mövcuddur. Konkret jurnal, dərs və tələbə identifikatorları yalnız private artefaktda saxlanır.

Bir hadisədə eyni gün başqa saatlı cari seminar və onun qiymətləri görünür. Native importun eyni gün/növ dərsinə bağlama tarixi və müəllim düzəlişləri araşdırılmadan ikinci seminar açılmır. Vaxt yaxınlığı eynilik sübutu deyil.

Bir tarixi hadisədə mənbə point rosteri cari legacy header rosterindən böyükdür. Tarixçəli roster fərqi çıxarılmır və yeni target rosterə əlavə edilmir; faktiki tarixçə ayrıca tələb olunur.

## Fresh capture ilə tamamlanan authority

1. `LegacyEntityMapVersion` tətbiq edilmiş son canonical mapping-i ilə müəllim/fənn/qrup və hər source tələbə həll edilir; pending review hədəf sayılmır.
2. Yeganə active offering + enrolled sətir sübut olunur; duplicate/transfer/alias route təxmin edilmir.
3. Cari Lecture bütün jurnal üçündür. Seminar/lab üçün `SeminarGroup`, `LabGroup`, enrollment maskaları və varsa mənbə subgroup/roster authority-si tutuşdurulur. Source rosterin bir hissəsinin olması təkbaşına subgroup nömrəsi deyil.
4. Tam Lesson/mark + formal correction/reversal/hygiene/audit closure yoxlanır. Eyni gün başqa saat və ya native merge/delete izi varsa ayrıca reviewed qərar lazımdır.
5. Yalnız sonra `class_authorities` sətrinə exact offering/journal pointer/date/start/kind/hours/instructor/masks, `end_time:null`, source row IDs/digests və nullable-end provenance yazılır. Canlı dry-run bütün targetları və yük tavanını yenidən yoxlayır; digər tələbələrə QB yaradılmır.

`prepare_lesson_authorities.py` fresh decoded snapshot + private source-facts + bu probe SHA-lərini qəbul edir və maksimum24 hadisə üçün bounded `class_authorities`, reviewed owner_present source IDs və qalan hold səbəblərini private0600 çıxarır.9 regression yoxlaması `lesson_authority_checks.py` ilə keçir. Source journalın bütöv canonical rosteri targetin bütün cari rosterinə və ya tək formally declared altqrupuna dəqiq uyğun gəlməlidir; bir neçə source point əsasında maska seçilmir. Formal LessonCorrection/Reversal və audit slot tarixçəsi yoxlanır. Native empty_lesson QB-only cleanup yeni owner siyasəti ilə auditID/hash göstərilərək üstələnə bilər; real qiymət/iştirakı silmiş cleanup və başqa formal retime/delete ayrıca hold-dur. Generator, Builder və canlı Planner eyni `class_history` proyeksiyası ilə tarixçə SHA-sını yoxlayır. Proyeksiya silinmiş dərsin FK-sı boş olsa da formal correction/reversal və strukturlaşdırılmış audit izini saxlayır. Capture-dan sonra yeni silmə, vaxt dəyişikliyi və ya reversal olarsa yeni dərs və ona bağlı owner fill hold edilir. Export və runtime eyni Sept1 sərhədi və dörd audit prefixi ilə işləyir. Mövcud dərsdə mənbə balının bərpası əlavə tarixçə SHA-sı tələb etmir. 8 yeni tarixçə testi və 16 mövcud native repair testi PostgreSQL-də keçib; təkrar tətbiq və dəqiq undo da yoxlanıb.

Hazır ölçü artefaktında `class_authorities=[]`: mənbə saat/hadisə sübutu tamamdır, yeni current capture route/mask/cleanup sübutu hələ birləşdirilməyib. Source28-in29oktyabr ayrı reviewed paketi bu247-yə qatılmır.

Kod istinadları: `apps/legacy_import/services/rehearsal_lesson_recovery_source.py` cüt vahidi; `apps/legacy_import/services/rehearsal_journal_lesson_kinds.py` point növü; `apps/legacy_import/services/delta/lessons.py` native default və absent-only yaratmama qaydası; `apps/registrar/reaudit_cells/planning.py` canlı maska/yük/qoruyucular.
