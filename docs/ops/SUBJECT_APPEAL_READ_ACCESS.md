# Fənn apellyasiyası — müəllim çağırışı və kafedra baxışı

Yeni apellyasiya veriləndə mövcud İmtahan Mərkəzi bildirişi saxlanılır.
Fənnin faktiki müəlliminə «Apellyasiya ilə bağlı İmtahan Mərkəzinə yaxınlaşın»
bildirişi gedir. Tələbəyə bu çağırış göndərilmir; tələbənin qərar/nəticə
bildirişləri dəyişmir. Yeni iş əvvəlki apellyasiya bildirişlərini təkrar göndərmir.

`appeal.view_subject` yalnız oxu açarıdır. Universitet rol şablonu və 0079
miqrasiyası bu açarı kafedra müdirinə və laboranta verir. UNIT əhatəsi həmin
icazəni daşıyan aktiv üzvlüyün `scope_unit`-indən gəlir. Başqa müəllim üzvlüyü
bu əhatəyə əlavə kafedra «borc vermir». Açarı olan xüsusi rollar da eyni mərkəzi
RBAC qaydası ilə işləyir; runtime rol adına görə xüsusi hal yoxdur.

Apellyasiyanın kafedrası tələbənin məktəbindən və müəllimin iş yerindən çıxarılmır:

1. Tələbənin imtahan fənni üzrə qeydiyyatı və explicit imtahan-jurnal bağlantısı;
   əlaqə yoxdursa imtahan vaxtının semestri, sonra ən son qeydiyyat semestri.
2. Eyni fənn + həmin semestr + fiziki qrup üzrə kafedraya çatmış rəsmi dərs yükü.
3. Belə sətir yoxdursa fənnin explicit `Subject.chair_unit` göstəricisi.

Başqa ilin yükü, tələbənin qrup ağacı, müəllimin əsas və ya əlavə kafedra üzvlüyü
əvəzləyici sübut deyil. Sahibi məlum olmayan fənn əlavə kafedraya açılmır.

İcazəli kafedra müdiri və laborant eyni apellyasiya barədə müəllimin adını,
tələbənin ad/soyad/ata adını, istifadəçi adını, qrupunu, fənnini və imtahanını
görür. Qrup adı yalnız apellyasiyanın tenantındakı aktiv tələbə reyestrindən gəlir.
Onlar mövcud «Fənnimə aid apellyasiyalar» panelini, oxu çekməcəsini və ixracını
istifadə edir; cavab/imtahan qərarı/yazma və qorunan sənəd endirmə hüququ verilmir.

Yeni bildirişlər eyni hadisədə təkrarsızdır: tələbə həmişə çıxarılır; müəllim həm
də kafedra baxıcısıdırsa iki bildiriş almır; mərkəzin əvvəlki alıcısı təkrar almır.
Yalnız `*` daşıyan rəhbərlər yeni kafedra hadisələrinə avtomatik abunə edilmir.
Faktiki müəllim dəqiqləşməyibsə kafedra bildirişi dəvət edildiyi barədə iddia etmir.

0079 idempotentdir; geri dönüş yalnız yeni oxu açarını götürür. Yeni oxu əhatəsi
bal, jurnal, sillabus, dərs yükü, qeydiyyat və apellyasiya qərarını dəyişmir.
