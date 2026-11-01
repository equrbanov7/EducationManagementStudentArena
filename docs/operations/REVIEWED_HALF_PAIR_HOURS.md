# Mənbə ilə təsdiqlənmiş yarım cütlük saat düzəlişi

`repair_reviewed_half_pair_hours` yalnız kodda qeyd olunmuş mənbə və cari dərs identifikatorlarını qəbul edir. V3 qeydiyyatı iki AZ dərsi və ingilis bölməsinin öz dərsidir: 2026-10-15 seminar, 15:15, mənbə `saatliq_ders=0.5` cütlük = 1 akademik saat; cari saat 2-dir. Mənbə jurnalları15023/15025/14938, metadata319789/319775/319858, ingilis öz təqvim389873. V3 private mənbə faylı `half-pair-three-reviewed-source-v3.json`, SHA `127a1dbe67fcc2f1e5aa9756988032cd6d3b0c36ef8d3be934ee5d79cc4ec96a`. Köhnə iki-hal mənbə faylı və onun SHA `7b4d0f118439f7eb0d7875c9c606e8376cfdf2fee41004e3244c05887f0e509c` dəyişdirilməyib; cari əmr yalnız yeni V3 SHA-nı qəbul edir.

İngilis öz dərsi d9ebc358… sinif səviyyəsində dəqiq worker/catalog/group/semester, təqvim və metadata ilə təsdiqlənib. Onun34 cari markı, o cümlədən mənbə tələbə-partisiyası tutulmayan və yalnız caridəki qeydlər, olduğu kimi saxlanılır. Həmin sinfin cari rəsmi sətri sıfır toplamlı və təyinatsızdır: bu vəziyyət, qrup M2M və dörd ölçü ledger körpüsü yoxlanıb qorunur; tarixi saat düzəlişi müəllim hüququ və ya dərs yükü vermir. AZ1-dəki xarici tarixçə32ab9d99… isə HELD olaraq qalır; eyni slot/saat uyğunluğu onu qeydiyyata daxil etmir. Mənbə üzrə yeni dərs, tələbə, jurnal və xana yaradılmır. Source4/28/58 bərpa qaydaları və ümumi yalnız-q/b guard dəyişmir.

Defolt dry-run:

```
python manage.py repair_reviewed_half_pair_hours --org qku --actor OPERATOR --file PRIVATE_V3_PROOF_JSON --sha256 V3_PINNED_SHA
```

Tətbiq: eyni mənbə ilə `--apply --baseline FRESH_DRY_SHA`. Təkrar dry/apply `already_present`, sıfır dəyişiklik qaytarır. Undo: yalnız həmin apply receipt UUID-si ilə `--undo UUID`; əvvəl dry, sonra yeni undo baseline ilə `--apply`. Workflow inteqrasiyası bu sənədlə nəzərdə tutulmur; əmr enumuna avtomatik əlavə edilmir.

Normal `apply_lesson_correction(new_hours=1)` və mövcud rəsmi reversal işləyir. Mənbə SHA-sı, sabit kurs/qrup/dövr/müəllim, rəsmi fəaliyyət/saat təyinatları, bütün70 mövcud markın UUID/enrollment/status/score/author uyğunluğu yoxlanır. Dərsin tarixi, növü, mövzusu, başlanğıc/son saatı, otağı, syllabus bağı və müəllifliyi dəyişmir. Tam DB fingerprint bütün əvvəlki qiymətləri, sıfır balı, q/b, i/e, imtahan nəticələrini və akademik konteksti qoruyur. Mənbə sübutundakı millisaniyə timestampı tam DB hashı kimi təqdim edilmir; dry/apply cari tam fingerprint hesablayır.

Əlavə AssessmentScheme yaratmaq da bu bərpanın hissəsi deyil: mövcud sxem yoxdursa əməliyyat ayrıca baxış üçün dayanır. Köhnə LessonCorrection və dəqiq tarixə aid birbaşa saat redaktəsi əks sübut sayılır; mənbəyə əsaslanıb sonrakı müəllim düzəlişi səssiz keçilmir. Mövcud audit best-effort olduğuna görə audit yoxluğu mütləq tarixçə yoxluğu kimi təqdim edilmir.

Qayıb sayı dəyişmir. AZ1-də beş xam q/b xanasının hərəsinin saat çəkisi 2→1 olur, ümumi xam qayıb saatı 5 azalır; AZ2-də19 iştirak markı, ingilis öz dərsində34 cari mark saxlanır; ingilis11 q/b əlavə xam saat azalması ilə üç dərs üzrə xam öz qayıb saatı cəmi16 azalır, q/b sayı isə dəyişmir. Təsirli qayıb saatı isə kreditlər və dəqiq DROPPED→superseded eyni tələbə/fənn/dövr keçidləri ilə mərkəzi qaydadan hesablanır. Aktiv kredit kökü çıxılır, reversal sətri ikinci dəfə çıxılmır. Kreditlər və i/e heç vaxt silinmir və dəyişdirilmir.

Dry xülasə `planned_lessons=3`, `preserved_marks=70`, `raw_qb_count_delta=0`, `raw_own_hours_delta=-16`, eləcə də `cached_before`, `derived_before`, `derived_after`, `stale_before`, `preview_sha256` verir. Undo dry üçün `derived_after` məhz geri-almadan sonrakı kanonik dəyərdir və xam saat delta+16-dır; idempotent təkrarda plan və delta0-dır. Tam enrolment-ID səviyyəli preview apply audit receipt-də saxlanır; stdout ad/əlaqə/səbəb mətni daşımır. Mövcud köhnəlmiş keş fərqi təkbaşına daimi blok deyil: kanonik fərq açıq göstərilir, xam/credit/carry konteksti dəyişmədən normal servis yenidən hesablayır. Saat düzəlişi bütün70 markın qeydiyyatını və etibarlı varis sayğaclarını yenidən hesablaya bildiyi üçün icazəli keş sahəsi yalnız beş q/b sətri ilə məhdudlaşdırılmır.

Undo yeni rəsmi reversal saxlayır, orijinal audit/sənədləri silmir, saatı 1→2 qaytarır. Qayıb sayğacı əvvəlki kanonik xam/credit hesabına qaytarılır; əvvəlki köhnəlmiş keş rəqəmi saxtalaşdırılmır. Sonrakı mark/credit/reversal/kurs/təyinat/sxem dəyişməsi və ya audit drift-i avtomatik undo-nu saxlayır. Bu, köhnəlmiş keşin bayt-bayt bərpası vədi deyil.

Hər əmr PG xarici atomic + tenant RLS kontekstindədir; dry RR READ ONLY-dir. İfadə/kilid vaxt hədləri, ümumi sorğu/vaxt və sətir tavanları var. Sərhəd keçilirsə heç bir hissəvi yazı saxlanmır. Xətalar mətn/SQL/PII əvəzinə kodla məhdudlaşdırılmış guard və class/function/line diaqnostikasını göstərir.

İngilis dərsi üçün köhnə tələbə xana xəritəsi cari sinif müddətinin səlahiyyət mənbəyi sayılmır: öz sinif/calendar/worker/catalog/group/period körpüsü təsdiqdir. Cari70 markın baseline və tam DB fingerprint-i dəyişməzlik müqaviləsidir. Heç bir bal/status həmin köhnə mənbədən geri yazılmır. İngilis qiymətləri kodda açıq siyahı ilə deyil,34-sətirlik kanonik metadata hashı ilə pinlənir. V3 audit namespace `workload.reviewed_half_pair_hours_v3`-dür; köhnə iki-hal receipt-i səssiz mənimsənilmir.

Operatorun aktiv hesabı ilə yanaşı profil access_state=active, is_deleted=False, deleted_at/deleted_by/blocked_at/blocked_by boşluğu fresh DB-dən yoxlanır; hətta artıq-tətbiq/idempotent/undo cavabları da bu guard-dan keçməlidir. CLI yalnız finite guard+class/function/line diaqnostikasını buraxır və orijinal exception səbəb zəncirini traceback-dən gizlədir. İngilis bölməsi burada Bulud texnologiyaları fənninin ingilisdilli qrupudur; LEVEL qiymətləndirmə siyasəti dəyişdirilmir.
