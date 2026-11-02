# Günay Həsənova — 536 TB Etnoqrafiya

Bu əməliyyat yalnız müəllim7847, fənn1672, Payız2026/2027, mövcud iki jurnal və üç yük sətrinə aiddir.

Mənbə: Tarix kafedrası.xlsx, «Dərs yükü», sətir10,
SHA256 `57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d`:
30saat mühazirə +30saat seminar. Köhnə bazanın tiplənmiş jurnal başlıqları
14989=ortaq961+962 mühazirə30,14990=961 seminar15,14991=962 seminar15;
müəllim311=Günay Həsənova Çapay, fənn1672, öz sillabusu2032=45saat.
Köhnə aylıq qeydlər ortaq mühazirəni və ayrıca seminar tarixlərini təsdiqləyir.

Nəticə: ortaq yük sətri30L/0S; iki altqrup sətri0L/15S. Müəllimin cəmi60saatdır,
HƏR tələbə jurnalının planı30L+15S=45saatdır. Qruplar, müəllim, kreditlər,
roster, dərs/qiymət/qayıb/i/e, sillabusun məzmunu və təsdiqi dəyişmir.

`TeacherAssignment.hours>0` DB məhdudiyyəti saxlanır. Üç artıq fəaliyyət təyinatı
normal `unassign(sync_offerings=False)` yolu ilə çıxır; üç qalan təyinatın ID-si
saxlanır. Receipt ilkin altı təyinatın bütün sahələrini saxlayır. Undo silinmiş
üç təyinatı əvvəlki dəqiq PK ilə bərpa edir. Akademik data silinmir.

Əvvəl quru yoxlama, sonra onun tam baseline SHA256-sı ilə tətbiq. Hər iki addım
aktiv təşkilat superadmini, müəllim səlahiyyəti, açıq semestr, üç rəsmi sətrin
kimliyi, altı təyinat və iki jurnalın kimliyi ilə qorunur. Qapalı reverse graph,
kredit mənbəyi və digər müəllim yükləri tətbiqdən əvvəl/sonra dəyişməz qalır.
Yeni dərs və ya bal yaranarsa əvvəlki baseline keçmir; yeni yoxlama lazımdır.

Əmr: `repair_reviewed_gunay_ethnography --actor USER` (dry default).
Tətbiq: `--apply --expected-baseline SHA`. Geri alma:
`--undo RECEIPT --apply --expected-baseline FRESH_SHA`.
Workflow `reviewed-gunay-ethnography.yml` yalnız canlı işləyən dəqiq HEAD ilə,
production mutex altında işləyir. Jurnal məzmununun bərpası ayrıca işdir.
