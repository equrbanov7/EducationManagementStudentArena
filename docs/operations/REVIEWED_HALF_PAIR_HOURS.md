# Mənbə ilə təsdiqlənmiş yarım cütlük saat düzəlişi

`repair_reviewed_half_pair_hours` yalnız kodda qeyd olunmuş mənbə və cari dərs identifikatorlarını qəbul edir. Cari qeydiyyat iki AZ dərsidir: 2026-10-15 seminar, 15:15, mənbə `saatliq_ders=0.5` cütlük = 1 akademik saat; cari saat 2-dir. Mənbə jurnalları 15023/15025, metadata319789/319775; tam private mənbə sübutunun SHA-sı `7b4d0f118439f7eb0d7875c9c606e8376cfdf2fee41004e3244c05887f0e509c`.

İngilis bölməsinin öz dərsi və AZ1-dəki xarici tarixçə ayrıca sübut baxışındadır; eyni slot/saat uyğunluğu onları bu qeydiyyata avtomatik əlavə etmir. Mənbə üzrə yeni dərs, tələbə, jurnal və xana yaradılmır. Source4/28/58 bərpa qaydaları və ümumi yalnız-q/b guard dəyişmir.

Defolt dry-run:

```
python manage.py repair_reviewed_half_pair_hours --org qku --actor OPERATOR --file PRIVATE_PROOF_JSON --sha256 PINNED_SHA
```

Tətbiq: eyni mənbə ilə `--apply --baseline FRESH_DRY_SHA`. Təkrar dry/apply `already_present`, sıfır dəyişiklik qaytarır. Undo: yalnız həmin apply receipt UUID-si ilə `--undo UUID`; əvvəl dry, sonra yeni undo baseline ilə `--apply`. Workflow inteqrasiyası bu sənədlə nəzərdə tutulmur; əmr enumuna avtomatik əlavə edilmir.

Normal `apply_lesson_correction(new_hours=1)` və mövcud rəsmi reversal işləyir. Mənbə SHA-sı, sabit kurs/qrup/dövr/müəllim, rəsmi fəaliyyət/saat təyinatları, bütün 36 mövcud markın UUID/enrollment/status/score/author uyğunluğu yoxlanır. Dərsin tarixi, növü, mövzusu, başlanğıc/son saatı, otağı, syllabus bağı və müəllifliyi dəyişmir. Tam DB fingerprint bütün əvvəlki qiymətləri, sıfır balı, q/b, i/e, imtahan nəticələrini və akademik konteksti qoruyur. Mənbə sübutundakı millisaniyə timestampı tam DB hashı kimi təqdim edilmir; dry/apply cari tam fingerprint hesablayır.

Əlavə AssessmentScheme yaratmaq da bu bərpanın hissəsi deyil: mövcud sxem yoxdursa əməliyyat ayrıca baxış üçün dayanır. Köhnə LessonCorrection və dəqiq tarixə aid birbaşa saat redaktəsi əks sübut sayılır; mənbəyə əsaslanıb sonrakı müəllim düzəlişi səssiz keçilmir. Mövcud audit best-effort olduğuna görə audit yoxluğu mütləq tarixçə yoxluğu kimi təqdim edilmir.

Qayıb sayı dəyişmir. AZ1-də beş xam q/b xanasının hərəsinin saat çəkisi 2→1 olur, ümumi xam qayıb saatı 5 azalır; AZ2-də 19 iştirak markı saxlanır. Təsirli qayıb saatı isə kreditlər və dəqiq DROPPED→superseded eyni tələbə/fənn/dövr keçidləri ilə mərkəzi qaydadan hesablanır. Aktiv kredit kökü çıxılır, reversal sətri ikinci dəfə çıxılmır. Kreditlər və i/e heç vaxt silinmir və dəyişdirilmir.

Dry xülasə `cached_before`, `derived_before`, `derived_after`, `stale_before`, `preview_sha256` verir. Tam enrolment-ID səviyyəli preview apply audit receipt-də saxlanır; stdout ad/əlaqə/səbəb mətni daşımır. Mövcud köhnəlmiş keş fərqi təkbaşına daimi blok deyil: kanonik fərq açıq göstərilir, xam/credit/carry konteksti dəyişmədən normal servis yenidən hesablayır. Saat düzəlişi bütün 36 markın qeydiyyatını və etibarlı varis sayğaclarını yenidən hesablaya bildiyi üçün icazəli keş sahəsi yalnız beş q/b sətri ilə məhdudlaşdırılmır.

Undo yeni rəsmi reversal saxlayır, orijinal audit/sənədləri silmir, saatı 1→2 qaytarır. Qayıb sayğacı əvvəlki kanonik xam/credit hesabına qaytarılır; əvvəlki köhnəlmiş keş rəqəmi saxtalaşdırılmır. Sonrakı mark/credit/reversal/kurs/təyinat/sxem dəyişməsi və ya audit drift-i avtomatik undo-nu saxlayır. Bu, köhnəlmiş keşin bayt-bayt bərpası vədi deyil.

Hər əmr PG xarici atomic + tenant RLS kontekstindədir; dry RR READ ONLY-dir. İfadə/kilid vaxt hədləri, ümumi sorğu/vaxt və sətir tavanları var. Sərhəd keçilirsə heç bir hissəvi yazı saxlanmır. Xətalar mətn/SQL/PII əvəzinə kodla məhdudlaşdırılmış guard və class/function/line diaqnostikasını göstərir.
