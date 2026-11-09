"""Render only IDs/counts from the current read-only audit evidence."""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def load(name):
    return json.loads((OUT / name).read_text())


def main():
    src = load("cells_legacy_coverage.json")["summary"]
    meta = load("cells_current_metadata.json")["summary"]
    pack = load("cells_pack_coverage.json")["summary"]
    comparison = load("cells_source_mapping.json")["summary"]
    qb = load("qb_pack_findings.json")["summary"]
    reviewed = load("qb_reviewed_current_status.json")["summary"]
    counts = comparison["counts"]
    primary = load("cells_primary_review_queue.json")["summary"]
    grades = load("cells_grade_preservation_cutoff.json")["summary"]
    gp = grades["source_point_primary_partition"]
    components = load("cells_component_inventory.json")
    cs = components["summary"]
    component_table = "\n".join(
        f"| `{code}` | {row['total']} | {row.get('numeric', 0)} | {row.get('blank', 0)} | {row.get('zero_numeric', 0)} |"
        for code, row in components["by_component_code"].items()
    )
    ops = load("cells_recent_operations.json")["aggregate_successful_apply_counters"]
    text = f"""# Jurnal xanaları, köhnə mənbə və QB — 9 noyabr 2026

**Mərhələ 1: yalnız hesabat. Cari vəziyyət üzrə yeni sübut alınıb, lakin bütün tətbiq olunan boş xanalar və bütün QB qərarları 100% yoxlanmış sayılmır.** Yeni lab/seminar altqrup sahələri və absence-credit/reversal məlumatları ixrac sxemində yoxdur. Qalan əhatə və sübut boşluqları aşağıda dəqiq ayrılıb. Heç bir məlumat düzəlişi, tətbiq kodu dəyişikliyi, miqrasiya, restore və deploy edilməyib.

Kod əsası: `45892d9011e6e31d9ad39f9999fa3cb7f6717f84`. Təzə production metadata: `{meta['captured_at']}`, run `42539120177`. Jurnal çəkilişləri `{pack['capture_start']}`–`{pack['capture_end']}` aralığındadır; ayrı yalnız oxunan tranzaksiyalardır, bir ümumi an deyil. Hər jurnalın son tam çəkilişi seçilir; fərqli versiyalar ayrıca qeyd olunur. Şəxsi ad/FİN/username/e-poçt/telefon/topic/bodytext hesabat sübutlarına yazılmayıb.

## Əhatə — tam say, qismən xana məlumatı

| Qat | Təsdiqlənən əhatə | Məhdudiyyət |
|---|---:|---|
| Cari Payız metadata | {meta['active_current_offerings']} aktiv + {meta['inactive_current_offerings']} passiv jurnal | Tam current-period aggregate inventarı |
| Aktiv jurnallarda dərs / bütün statusların mark-ları | {meta['active_lessons']} / {meta['active_marks_all_roster_statuses']} | Mark sayı yalnız cari enrolled grid deyil |
| Aktiv enrolled sətir / student×lesson tam hasili | {meta['active_enrolled_rows']} / {meta['active_structural_grid_pairs']} | Altqrupa aid olmayan xanalar hələ çıxılmayıb |
| Dərssiz aktiv jurnal | {meta['active_no_lessons']} | {meta['active_no_lessons_with_enrolled']}-də enrolled tələbə var |
| Marksız aktiv jurnal / enrolled tələbəsiz aktiv jurnal | {meta['active_no_marks']} / {meta['active_no_enrolled']} | Boşluğun səbəbi ayrıca yoxlanır |
| Metadata daxilində raw subset | {meta['subset_offerings']} jurnal, {meta['subset_lessons']} dərs, {meta['subset_marks']} mark | Hamısı həmin capture-ın aggregate sayları ilə tutuşur |
| Yeni pack raw əhatəsi | {pack['capture_batches']}/91 batch, {pack['unique_captured_offerings_including_history']} unikal jurnal | Tarixçə açılışları daxildir |
| Cari aktiv jurnallardan raw əhatə | {pack['metadata_active_current_captured']}/{pack['metadata_active_current_offerings']} | {pack['metadata_active_current_missing']} aktiv jurnal bu qatda yoxdur |
| Raw qatda doldurulmamış student×lesson cütü (aktiv / passiv tarixçə) | {pack.get("active_structural_unfilled_pairs", 0)} / {pack.get("inactive_structural_unfilled_pairs", 0)} | Bu, tətbiq olunan real boş xana sayı deyil; lab/seminar maskası məlum deyil |

Spring 2027-nin 611 dərssiz açılışı cari Payız probleminə qatılmır. Metadata subset-i pack saylarına əlavə edilmir: çoxluqlar üst-üstə düşə bilər. Raw qatda cari fiziki bal həddi/status/FK anomaliyası sayı **{pack['numeric_or_cross_fk_anomalies']}**-dır. Yoxlanılmayan hissə üçün “0 problem” yazılmır.

## Təsdiqlənmiş owner qaydası — 21 oktyabr daxil olmaqla balın qorunması

Owner həm bal, həm boş xana sərhədini **21 oktyabr 2026 daxil** təsdiqləyib. İ/ə **present** deməkdir. Mənbənin rəqəmli balı, o cümlədən **0 bal**, qorunmalıdır. Mənbəsiz və ya şübhəli, tətbiq olunduğu təsdiqlənmiş **boş** xanaya owner qaydası ilə present nəzərdə tutulur; belə halda QB təxmin edilmir. Cari dolu xana, son müəllim balı, rəsmi correction və apellyasiya nəticəsi avtomatik dəyişdirilmir. **Təsdiqlənmiş qayda mövcuddur; Mərhələ 1 yenə yalnız hesabatdır, bütün sətirlər `eligible_for_apply=false` qalır.**

`cells_grade_preservation_cutoff.json` hər source point-i bal rəqəmi göstərmədən ID, tarix, typed identity, target nəticəsi və hold səbəbi ilə verir. Tarix source dərs tarixidir; added/updated vaxtı ayrıca saxlanır. Jurnalın təqvim xanalarındakı bütün source numeric qalibləri **{grades['source_calendar_numeric_winners']}**: 20 oktyabradək **{grades['date_partition_counts'].get('through_october_20', 0)}**, 21 oktyabrda **{grades['date_partition_counts'].get('october_21_only', 0)}**, daha sonra **{grades['date_partition_counts'].get('after_october_21', 0)}**. Təsdiqlənmiş sərhəddə **{grades['through_cutoff_unique_source_points']} unikal source point**, bunlardan **{grades['through_cutoff_zero_grade_source_points']} sıfır baldır**. Bu kəsim final imtahan nəticələri üçün ayrıca sübut deyil.

| ≤21 oktyabr source point-in müşahidə olunan vəziyyəti | Unikal source point |
|---|---:|
| Cari namizəd xanada eyni rəqəmli dəyər görünür | {gp.get('numeric_value_matches_in_candidate', 0)} |
| Cari rəqəmli dəyər fərqlidir — cari bal qorunur | {gp.get('numeric_value_differs_preserve_current', 0)} |
| Cari fiziki attendance xanası doludur, rəqəmli bal yoxdur | {gp.get('filled_current_cell_without_numeric_grade', 0)} |
| Cari namizəd fiziki xana boşdur | {gp.get('physically_blank_current_candidate', 0)} |
| Exact dərs slot-u tapılmır | {gp.get('exact_lesson_slot_missing', 0)} |
| Captured aktiv target üçün source route tapılmır | {gp.get('no_active_source_route_in_captured_scope', 0)} |
| Typed tələbə əlaqəsi yoxdur və ya ambiguous-dur | {gp.get('student_identity_missing_or_ambiguous', 0)} |
| Cari enrollment yoxdur və ya ambiguous-dur | {gp.get('current_enrollment_missing_or_ambiguous', 0)} |

Bu cədvəl **itmiş bal və ya tətbiqə hazır düzəliş sayı deyil**. Eyni dəyər müşahidəsi də offering route və rəsmi apply receipt-i sübut etmir. Route tapılmayan hər mənbə balının `legacy_point_id/journal_id/student_id`-si artefaktda ayrıca var; adı oxşar tələbə/fənnə yazmaq olmaz. {grades['through_cutoff_presemester_points']} pre-semester point və {grades['through_cutoff_flagged_source_points']} source flag-li point də məxrəcdə saxlanıb, əvvəlki cleanup/authority ayrıca araşdırılmalıdır. Bu yeni siyahının **{grades['source_points_already_in_primary_review_queue']} source point-i** əvvəlki 347 baxış siyahısında da var; saylar toplanmır.

| Gələcək plan siyasəti | Şərt |
|---|---|
| `source_score_preserve` | Rəqəmli source balı ilk prioritetdir; route/student/slot açılmayıbsa hold qalır, i/ə ilə örtülmür. |
| `confirmed_attendance` | Source davamiyyəti və tətbiq olunan tələbə/dərs əlaqəsi rəsmi sübutla uyğun gəlir; mövcud xana qorunur. |
| `owner_assigned_present` | Rəqəmli source-grade hold-u olmayan, tətbiq olunduğu sübut edilən həqiqətən boş xana üçün owner-in açıq i/ə qaydası; auditdə source faktı kimi təqdim edilmir. |

Yazıdan əvvəl student identity, group mask, exact lesson və current baseline yoxlanmalıdır. Sonradan doldurulmuş xanaya overwrite yoxdur. Repro: `cells_grade_preservation.py`; mənbə/target raw qiymətlər yalnız yaddaşda işlənir, reporta və JSON-a çıxmır.

## Təqvimdən kənar komponent qeydləri — əlavə bal qorunması boşluğu

Yuxarıdakı təqvim ballarına **daxil olmayan {cs['source_rows']} qeydin** ayrıca inventarı `cells_component_inventory.json`-dadır: **{cs['numeric_rows']} numeric**, **{cs['value_class_counts'].get('blank', 0)} boş**, **{cs['status_or_other_token_rows']} status/başqa token**. Numeric qeydlərin **{cs['numeric_zero_rows']}-u sıfırdır**. Hər qeyd source point/journal/student ID, komponent kodu və bal-presence/zero flag-i ilə saxlanılıb; fərdi rəqəm yoxdur.

| Komponent kodu | Bütün qeydlər | Numeric | Boş | Sıfır bal |
|---|---:|---:|---:|---:|
{component_table}

Bu kodlardan dərs tarixi alınmır. Tarix əsası source **added/updated timestamp**-dır: {cs['added_date_cutoff_counts'].get('on_or_before_cutoff', 0)} qeydin added tarixi 21 oktyabr daxil sərhəddədir; updated tarixi {cs['updated_date_cutoff_counts'].get('on_or_before_cutoff', 0)} qeyddə məlum və həmin sərhəddə, {cs['updated_date_cutoff_counts'].get('unknown', 0)} qeyddə isə **unknown**-dur. Unknown tarix sıfır bal və ya sonradan dəyişməyib sübutu sayılmır.

Native J5 rehearsal `k1/k2/k3 → kollokvium`, `si → self_work` komponentlərini tanıyır: **{cs['recognized_component_rows']} source qeyd**, bunlardan **{cs['native_rehearsal_scored_rows']}** native numeric/range qaydasına uyğundur. Mövcud komponent xanası overwrite edilmir. Lakin cari `delta/finals.py` bu 4 növü `component.<kind>_not_imported` sayır, yazmır; səbəb kodda 2026/27 qiymətləndirmə sxemi kimi göstərilib. J5-də saxlanmış `si` balı da öz-özünə giriş balına əlavə edilmir; giriş hesabı SelfWorkMark checklist-indən istifadə edir. Kod davranışı production-da həmin qeydin olmadığı sübutu deyil.

Qalan **{cs['unsupported_component_code_rows']}** qeyd (`pa/wr/ss/ww/ll/rr/ga`) üçün aktiv bal semantikası tanınmır: J6 unknown quarantine edir; LegacyGradeFact OTHER yolu tarixi sübutu saxlaya bilər, lakin bu aktiv komponent/Midterm balına çevrilmə deyil. Bu qeydlər, o cümlədən numeric olanlar, qorunur və **safe hold** qalır. Naməlum komponenti sıfıra, gündəlik bala, Midterm-ə və ya i/ə-yə çevirmək olmaz; owner-in i/ə qaydası tətbiq olunan boş davamiyyət xanalarına aiddir.

**Cari komponent balı əhatəsi unknown-dur:** raw ixracda `component_corrections` var, `AssessmentComponent/ComponentScore` cədvəlləri yoxdur. Correction sətrindən actual cari bal inventarı çıxarmaq olmaz. Növbəti sübut: current komponent/score və scheme oxunuşu, source→enrollment əlaqəsi, exact component semantikası və rəsmi hesablama qərarı. Final imtahan əhatəsinin əvvəlki boşluğu dəyişməyib. Repro `cells_component_inventory.py`; bütün sətirlər `eligible_for_apply=false`.

## Mənbə bütövlüyü

Semestr14 `2026/2027 Payız`: **{src['journals']} jurnal**, {src['nonfake_journals']} nonfake, {src['active_journals']} active; {src['raw_point_rows']} point, {src['teacher_date_rows']} teacher-date sətri. Bütün jurnal başlıqları University-dir. İstinad edilən 260 group ID-dən259-u University, biri yoxdur (`journal14037 → group893`); kollec istinadı yoxdur. `14964/15069` roster JSON-u array deyil, point yoxdur; roster sayı0 kimi təqdim olunmur.

| Source təqvim dəyəri | Say |
|---|---:|
| 0–10 bal | {src['winner_distribution']['score']} |
| İştirak | {src['winner_distribution']['present']} |
| Qayıb | {src['winner_distribution']['absent']} |
| Üzrlü | {src['winner_distribution']['excused']} |
| Mənbənin özündə boş point | {src['winner_distribution']['blank']} |
| Qeyri-təqvim point | {src['noncalendar_point_rows']} |

Eyni source cell açarında J-V4 duplicate0, tanınmayan/həddən kənar təqvim balı0, teacher-slot-suz təqvim point0, qarışıq source slot növü0. J-V4 qalibi update_counter→updated_at→ID ilə seçilir; maksimum bal qaydası işlədilmir. Mənbə son point update-i **{src['point_last_updated']}**-dır. Oxu günü9 noyabr olsa da mənbə 21 oktyabrdan sonrakı cari EMS dəyişikliklərinin tam sübutu deyil. `im/im2` bu source semestrində yoxdur; bu, production final nəticəsi yoxdur demək deyil.

## F-CELLS-01 — Dərssiz/marksız jurnallar və tam boş-xana əhatəsi

**Kateqoriya3/4/11; yüksək əhatə prioriteti.** {meta['active_no_lessons']} aktiv jurnal dərssizdir, {meta['active_no_lessons_with_enrolled']}-də tələbə var. Hər biri `cells_current_metadata.json`-da ID ilə verilib. Təzə raw qatda source tuple namizədi olan dərssiz aktiv jurnal sayı **{len(comparison.get('active_empty_offering_source_candidates', []))}**-dır; bu başlıq uyğunluğudur. Bunlardan nonblank source point-i olan jurnal sayı **{len(comparison.get("active_empty_offering_with_nonblank_source_points", []))}**, yalnız source date-i olanı **{len(comparison.get("active_empty_offering_with_source_dates_only", []))}**. Source əlaqəsi olmayan qalan jurnalların düzgün və ya səhv olduğu bununla müəyyən edilmir.

Yoxlama qaydası: hər enrolled tələbə×own lesson cütü sayılır; sonra `Lesson.lab_group/seminar_group` və `Enrollment.lab_group/seminar_group` maskası tətbiq olunmalıdır. **Mövcud 0 bal, present, absent və excused xanası boş deyil.** Group maskası olmadığı üçün hazırkı {pack['structural_unfilled_pairs']} cütün hamısını doldurmaq olmaz. Actor UI-də görünən roster all-org məxrəci sayılmır.

Sübut: `cells_current_metadata.json`, `cells_pack_coverage.json`, `cells_pack_unfilled_pairs.json`. Repro: `cells_metadata_analysis.py`, `cells_pack_analysis.py`; icra olunmamış parametrli SQL: `cells_current_grid.sql`. `applicable=filled+blank` və `structural=applicable+off_group` tam invariantı üçün qalan sahələr lazımdır.

**Təklif:** Stage2-də yalnız tam grid, source authority və exact mapping təsdiqlənən cütlərə `fill_legacy_cells_20261108 --org qku --actor <operator> --file <reviewed-plan>` hazırlanır. Hazırda bütün sətirlər `eligible_for_apply=false`. Komandanın default dry-run-ı write+rollback işlədə bilər; bu audit onu çağırmayıb. Undo ümumi run-ları yox, təsdiqlənən receipt-in dəyişməz yaratdığı ID-ləri əhatə etməlidir. Owner hər bərpa qrupunu ayrıca təsdiqləməlidir.

## F-CELLS-02 — Mənbəli boş xanalar, artıq dolular və qeyri-müəyyən əlaqələr

**Kateqoriya4/11; yüksək.** {comparison['unique_captured_offerings']} captured jurnalın {comparison['mapping_offerings_unique_entity_tuple']}-i üçün tək typed subject+group+worker source namizədi, {comparison['mapping_offerings_ambiguous_sources']}-i üçün bir neçə source namizədi var. Direct `course_offering` ledger xətti olan jurnal sayı **{comparison['mapping_offerings_direct_ledger']}**-dır. Typed tuple namizədi exact offering ledger kimi təqdim edilmir; alias/rebound/merge authority ixracda tam deyil.

- Source-a bağlanan doldurulmamış cari student×lesson namizədi: **{comparison['unfilled_candidates']}**. Dəyər bölgüsü: `{comparison.get('unfilled_candidate_values', {})}`.
- Artıq dolu olduğuna görə fill-dən çıxarılan target xana: **{counts.get('already_filled_cells_excluded_from_fill', 0)}**.
- Source ilə eyni dəyəri olan target xana: **{counts.get('current_value_matches_source', 0)}**.
- Exact lesson slot-u olmayan/ambiguous source point yoxlama cəhdi: **{comparison['missing_or_ambiguous_slot_source_points']}**, active+enrolled hissəsi **{comparison.get('active_enrolled_missing_slot_source_points', 0)}**.
- Unique source point: considered **{comparison.get('unique_source_points_considered', 0)}**, current cell-ə bağlı **{comparison.get('unique_source_points_linked_to_current_cell', 0)}**, eyni dəyər **{comparison.get('unique_source_points_equal_current_value', 0)}**.

“Yoxlama cəhdi” source point×target offering dənəsindədir; çoxqruplu source jurnal üçün eyni source point təkrarlana bilər. Bu saylar unikal problem/tələbə sayı deyil. Name/FIN fallback, tarix-only və majority kind təxmini yoxdur. Missing mapping cari xananın itdiyini sübut etmir.

Sübut: `cells_source_mapping.json`, `cells_source_blank_candidates.json`, `cells_source_missing_slots.json`; repro `cells_source_compare.py`. Risk: yanlış route/student və ya altqrup başqa tələbəyə bal/QB yazar. **Təklif:** exact typed identity, source→target merge/transfer audit-i, group masks və correction/deletion tarixçəsi alındıqdan sonra ayrı manifest; sonradan edit edilmiş xananı qoruyan undo. Məlumat yazısı və approval bu mərhələdə yoxdur.

## F-CELLS-03 — Source/current dəyər fərqləri

**Cari aktiv/enrolled prioritet siyahı:** `cells_primary_review_queue.json` hər namizədi `CELL-NNNN` ID-si, target/source IDs, capture batch, konkret hold səbəbi və tələb olunan addımla verir. Cəmi **{primary['current_active_enrolled_cell_review_rows']} baxış sətri**; bunlar unikal tələbə və təsdiqlənmiş səhv sayı deyil. Fərdi numeric qiymət repoda yoxdur; yalnız presence/zero flags və müqayisə sinfi saxlanır.

| Cari aktiv/enrolled baxış səbəbi | Say |
|---|---:|
| Q/B var, source iştirak/bal/üzrlü göstərir | {primary['priority_counts'].get('P1_i_e_qb_source_disagreement', 0)} |
| Source balı var, cari fiziki xanada bal yoxdur | {primary['priority_counts'].get('P1_source_score_missing_in_current_cell', 0)} |
| Boş xana üçün source iştirak/bal var | {primary['priority_counts'].get('P1_source_present_or_score_in_empty_cell', 0)} |
| Boş xana üçün source Q/B var; authority tələb olunur | {primary['priority_counts'].get('P2_source_qb_empty_cell_requires_authority', 0)} |
| Exact tarix/saat/növ dərsi yoxdur və ya dəyişib | {primary['priority_counts'].get('P2_exact_lesson_slot_missing_or_changed', 0)} |

Bütün {primary['current_active_enrolled_cell_review_rows']} sətirdə offering route, altqrup maskası və cleanup/düzəliş authority-si tam deyil; {primary['hold_reason_counts'].get('multiple_source_journal_candidates', 0)} sətirdə birdən çox source jurnal namizədi var. Bunlar mənbə təsdiqlənmədən avtomatik fill və ya QB silmə planı deyil.

**Kateqoriya9; yüksək namizəd yoxlama prioriteti.** Aşağıdakılar göstərilən mapping tier altında müşahidə edilən fərqdir; avtomatik “cari bal yanlışdır” qərarı deyil.

| Fərq | Target xana |
|---|---:|
| Current absent, source present/score/excused | {counts.get('current_absent_source_present_score_or_excused', 0)} |
| Source score, current score yoxdur | {counts.get('source_score_current_no_score', 0)} |
| Current score source-dan aşağı | {counts.get('numeric_score_lower_than_source', 0)} |
| Current score source-dan yuxarı | {counts.get('numeric_score_increased_vs_source', 0)} |
| Current score, source yalnız present idi | {counts.get('current_score_source_attendance_only_not_error', 0)} |
| Current excused, source absent idi | {counts.get('current_excused_source_absent_not_automatic_error', 0)} |
| Digər status/bal fərqi | {counts.get('attendance_or_score_differs', 0)} |

Mövcud rəsmi correction ID-ləri hər sətirdə saxlanılıb. Source-dan sonrakı normal qiymət əlavəsi, yüksəldilmiş bal və üzrlü qərar geriyə qaytarılmır. Strict source match-i olmayan {comparison['current_score_without_strict_source_match']} cari score-un {comparison['current_score_after_source_capture_day']}-i 21 oktyabrdan sonrakı dərs tarixlidir; bu siyahı səhvlər siyahısı deyil.

Sübut: `cells_source_conflicts.json`, `cells_source_unmatched_scores.json`. **Təklif:** hər konkret mark/source point/tarixçəni rəsmi müəllim qərarı ilə tutuşdurmaq; native journal correction servisi yalnız ayrıca təsdiqdən sonra, old/new baseline və reversal sübutu ilə. Generic fill mövcud xananın üzərinə yazmaq üçün istifadə edilmir. Risk: qanuni son balı köhnə source dəyəri ilə itirmək.

## F-CELLS-04 — Source tarix, roster və duplicate slot məhdudiyyətləri

**Kateqoriya3/4/9/11; orta/yüksək source riski.** {src['duplicate_teacher_slot_groups']} təkrar teacher slot qrupu var; ayrı saat/növ dərsləri birləşdirilmir.5 yararsız date ID: `380428,380430,380431,380433,380434`, journal14951. {src['calendar_points_outside_listed_journal_roster']} point348 jurnal/513 legacy student üzrə source roster-dən kənardır; tarixi transfer ola bilər, yanlış tələbə sübutu deyil.

Mənbədə {src["teacher_slots_without_any_point"]} teacher slot-da point yoxdur, {src["calendar_slots_with_only_blank_points"]} slot yalnız blank, {src["calendar_slots_only_absent_or_excused_nonblank"]} slot yalnız QB/excused daşıyır. Bare-date və QB-only sütunlar əvvəlki cleanup/idxal qaydasına görə ayrıca authority tələb edir; avtomatik bərpa siyahısı deyil.

15 sentyabrdan əvvəl {src['before_semester_start_points']} point; 21 oktyabrdan sonrakı dərs tarixinə yazılmış {src['after_source_capture_day_points']} point, bunların {src['after_audit_day_points']}-sı9 noyabrdan sonradır. **Pre-semester source xanaları copy plan-dan çıxarılıb.** Sonrakı generic cutoff halları da ayrıca reviewed istisna olmadan fill plan-a girmir. İcazəli cleanup-dan sonra source-da qalması “EMS-də bərpa edilməlidir” demək deyil.

Sübut: `cells_legacy_exceptions.json` hər point/date ID-ni verir; `cells_legacy_queries.json`, `cells_legacy_inventory.py` təkrar çıxarmadır. Təklif: source tarix/identity authority, exact gün+saat+növ və current cleanup audit-i. Əmr: ümumi auto-copy yoxdur; əvvəl source qərarı. Dublikatın native silinməsi yalnız `fix_mexanika_lessons_20261108` exact twin guard-ları ilə və ayrıca təsdiqli plan/undo snapshot əsasında nəzərdən keçirilə bilər.

## F-QB-01 — Cached QB ilə cari raw sübutun uyğunsuzluğu

**Kateqoriya9; cari sayğac faktı.** Captured qatda **{qb['cache_above_canonical_upper_bound_rows']}** enrollment-də cached saat current raw+exact carry raw yuxarı həddindən böyükdür; **{qb['zero_raw_and_carry_positive_cache_rows']}** halda raw+carry0-dır. Active+enrolled hissəsi **{qb['active_enrolled_overshoot_rows']}**. Bunlar fərdi ID/capture vaxtı ilə `qb_pack_findings.json`-dadır.

Current canonical qayda: `max(0, own_raw + Σmax(0, exact_source_raw − source_credit) − target_credit)`. Source dropped, eyni org/student/subject/period və nonself olmalıdır. Credit ixrac olunmasa da yalnız azalda bildiyindən cached>raw upper bound faktı sübut edilə bilər; raw+carry0 olduqda canonical0 dəqiqdir. Qalan hallarda credits olmadan “counter düzgündür” nəticəsi çıxarılmır. `groups_half_pair_raw.json`-dakı ayrıca3 dərs üzrə yarım-cüt araşdırması lesson.hours-in akademik düzgünlüyünə aiddir: hipotetik own-raw fərqi16 saatdır; bu, burada təsdiqlənmiş effective counter düzəlişinə əlavə edilmir.

**Bu, akademik olaraq tələbənin qayıbının silinməsi qərarı deyil.** Tarixi dərs/mark niyə çıxarılıb, qanuni QB mənbəyi və cleanup authority hələ ayrıca tələb olunur. Dəqiq formulu yoxlayan `qb_current_counter.sql` icra edilməyib. Repro `qb_pack_analysis.py` current snapshots-da yalnız offline hesablayır. Stage2-də source authority təsdiqlənərsə mövcud `gradebook_marks.recompute_absence_hours_many` servisinə yalnız təsdiqlənən enrollment ID-lərini verən dar yeni əmr dizaynı lazımdır: reviewed manifest, fresh expected-baseline, exact before/after və receipt-bound undo. Mövcud `recompute_carried_absences_20261108` generic cache əmri deyil: həm mark bərpa edir, həm predecessor bağı açır. Onu bu siyahıya kor-koranə işlətmək olmaz; avtomatik sıfırlama yoxdur.

## F-QB-02 — Təkrar qayıb hadisəsi namizədləri

**Kateqoriya9; yüksək yoxlama prioriteti.** Eyni jurnal/student/tarix/saat/növ absent qrupu **{qb['same_journal_same_slot_absent_groups']}**; exact predecessor→target eyni slot absent cütü **{qb['source_target_same_slot_absent_pairs']}** (active+enrolled target hissəsi **{qb.get("active_enrolled_source_target_absent_pairs", 0)}**); iki aktiv offering-də eyni student+canonical subject+slot absent qrupu **{qb.get('active_cross_offering_same_subject_slot_absent_groups', 0)}**; exact history qaydasına uyğun olmayan pointer **{qb['invalid_exact_history_pointers']}**.

Sübut: `qb_pack_findings.json` lesson/mark/enrollment/subject IDs və pointer səbəbləri. Bunlar duplicate namizədləridir: group masks, rəsmi ayrı dərs və credits yoxlanmadan silinmir. Canonical subject ID-si ayrı alias-lar bu exact-key yoxlaması ilə tam həll olunmur; catalog/workload hesabatı ilə birləşdirilməlidir. Risk: tarixi source-u silmək və ya eyni real dərsi iki dəfə QB-yə qatmaq. Təklif: exact event+source/target audit müqayisəsi, native approved duplicate/carry correction və qorunan qraf+receipt undo; owner ayrıca təsdiqləyir.

## F-QB-03 — REVIEWED source və tarixçə statusu

| İş | Təzə source faktı | Təzə target faktı |
|---|---|---|
| Source58 | 58/58 pinned journal/student/date/time/qb uyğundur | {reviewed['source58']['covered_cases']}/58 captured; {reviewed['source58']['physical_value_matches']} fiziki xana source dəyəri ilə eyni |
| Source28 | 28/28 pinned present uyğundur | {reviewed['source28']['covered_cases']}/28 captured; {reviewed['source28']['physical_value_matches']} fiziki xana eyni |
| Reviewed authorship14190 | Source244 point/243 nonblank | {reviewed['authorship']['covered_lessons']}/18 lesson captured; instructor8311 uyğunluğu {reviewed['authorship']['instructor_matches']} |

Source28 target `1aca3f3c-5677-494e-af12-5622d2c1ea0a` üzrə 28 exact enrollment enrolled və studentID uyğundur; 29 oktyabr tarixli dərs yoxdur. Bu **OPEN fiziki boşluq**dur. Native Source28 üçün13 history pin, full closure və apply/undo receipt ayrıca lazımdır. Source58-də fiziki xana var/yox/dəyər dəyişib ayrımı `qb_reviewed_current_status.json`-da verilir; təkcə source `qb` olduğuna görə current present və ya score dəyişdirilmir.

**Saylar üst-üstə düşür:** Source58-in 31 açıq slot boşluğunun hamısı 347 sətirlik prioritet siyahının 247 slot boşluğu kateqoriyasına artıq daxildir; onları yenidən toplamaq olmaz. Source28-in 28 açıq boşluğu həmin 347 sətirdən kənardadır, çünki 29 oktyabr generic source cutoff-dan sonradır və ayrıca REVIEWED paketlə yoxlanır. Bunlar yenə baxış sətirləridir, unikal tələbə və ya təsdiqlənmiş səhv sayı deyil.

Kodda writer-in olması production apply sübutu deyil. Exporter `source58_audit_row_budget`/credit UNKNOWN flag-i də kodda native writer olmadığı iddiası deyil. Fresh receipt və tam guard alınmadan “resolved/apply-ready” yazılmır. `REVIEWED_ELSHEN_DUPLICATES` workload scope-dur; bunun uğuru cell/QB bərpası sayılmır. Reviewed journal-history2 destination map-i üçün full authority yenə lazımdır.

Yeni owner qaydasına görə şübhəli boş xana üçün Source58-in native QB yazısı avtomatik seçilmir. Aşağıdakı əmrlər mövcud kod yollarının inventarıdır, təsdiqlənmiş apply planı deyil; hər xana əvvəl `source_score_preserve`, `confirmed_attendance` və ya `owner_assigned_present` siyasəti üzrə ayrılmalıdır.

Sübut: `qb_reviewed_source_status.json`, `qb_reviewed_current_status.json`; repro `qb_reviewed_source_inventory.py`, `qb_reviewed_current.py`. Native yollar (bu auditdə icra edilməyib):

```text
repair_reviewed_source58 --actor <operator> --manifest <sealed-source> --manifest-sha256 <fixed-sha>
repair_reviewed_journal_content --org qku --actor <operator> --manifest <sealed-source28> --manifest-sha256 <fixed-sha> --targets 1aca3f3c-5677-494e-af12-5622d2c1ea0a
repair_reviewed_ibrahim_authorship --actor <operator>
```

Risk/undo: fresh native baseline, qorunan qraf, exact receipt və dəyişməz yaradılmış obyektlər; generic blanket undo yoxdur. Source58 saatını58×2 artırmaq yanlış olar: mövcud xana, credits və carry nəzərə alınmalıdır. Stage2 owner qərarı hər sabit paket üzrə ayrıdır.

## Son əməliyyatlar — əvvəl doldurulanları yenidən problem saymamaq

`cells_recent_operations.json` yalnız safe run summary-lərini saxlayır; **əməliyyat sayları cari state və unikal obyekt sayı deyil**. Uğursuz run-da counter yoxdursa0 qəbul edilmir. Təkrar dry-run sayları apply nəticəsinə qatılmır.

-6 uğurlu `fill_legacy_cells_20261108` apply run-unda **{ops['fill_legacy_cells_20261108']['cells_filled']} xana**,23 dərs bildirilib. Rəqəmli/scored detalı bəzi köhnə run versiyalarında tam deyil; natamam alt saylar275-ə süni tamamlanmır.
- `remove_pre_semester_lessons_20261108`, run `42487257659`: **59 dərs/917 mark/48 jurnal** owner-authorized silinib. Source-only pre-semester sətirləri buna görə copy plan deyil.
- Mechanics5 uğurlu apply run-unda27 duplicate lesson/436 eyni-twin mark silinməsi,6 lesson/84 mark köçürməsi bildirilib; current snapshot ayrıca yoxlanır.
- Carry2 uğurlu apply run-unda90 counter change,204 predecessor unlink və76 mark restore bildirilib. Bu, qalan cached drift-in avtomatik həll olunduğu demək deyil.
- Lab binding2 successful apply-də2 bağlama; subgroup merge3 apply-də6 family/1218 copied mark bildirilib. Yeni lab/seminar maskası exporter-də yoxdur; onları boş xana kimi saymaq riski qalır.

## Təkrar çıxarma və yoxlama

Audit worktree-də `PYTHONDONTWRITEBYTECODE=1 /Users/elvin/Developer/EMSArena/venv/bin/python <evidence-script>` istifadə edilir. Source üçün `cells_legacy_inventory.py`; metadata üçün `cells_metadata_analysis.py`; pack üçün `cells_pack_analysis.py`, `cells_source_compare.py`, `qb_pack_analysis.py`, `qb_reviewed_current.py`; sonda bu renderer və `cells_validate.py`.

`cells_query_plan.json` bütün sorğu planını, `cells_legacy_queries.json` icra olunmuş source SELECT-ləri, `cells_current_grid.sql` və `qb_current_counter.sql` icra olunmamış target SELECT planını verir. `cells_validation.json` arifmetik/SQL müqayisəsi, privacy-field yoxlaması və SHA-256 manifestidir. Private ciphertext/key/raw source report qovluğuna köçürülməyib.

Mərhələ2-yə keçməzdən əvvəl qalan current raw journals, lab/seminar masks, source→target authority və credit/reversal/cleanup history tamamlanmalıdır. Hər yeni düzəliş qrupu üçün konkret input manifest/hash, old/new nəticə, qorunan qraf və undo planı owner-ə təqdim edilməlidir. **Bu hesabat heç bir apply icazəsi və ya bütün auditin100% tamamlandığı iddiası deyil.**
"""
    text = text.replace("\n-6 ", "\n- 6 ")
    (OUT.parent / "CELLS_QB_AZ.md").write_text(text)
    print(
        json.dumps(
            {"report": "CELLS_QB_AZ.md", "capture_batches": pack["capture_batches"], "lines": len(text.splitlines())}
        )
    )


if __name__ == "__main__":
    main()
