# İki hadisə üçün rəsmi iştirak düzəlişi

`owner_present_conflict` mövcud structure command/workflow, ehtiyat nüsxə,
tam kilidlənmiş qraf, baseline və receipt protokolundan istifadə edir.
Ümumi UI-nin aktiv jurnal qapısı dəyişmir. Bu əməliyyat yalnız SHA ilə
möhürlənmiş şəxsi authority-dəki iki qeyri-aktiv mənbə → aktiv hədəf
predecessor hadisəsinə aiddir. Aktor, profil, tenant və cari semestr yoxlanır.

Authority orijinal legacy QB və düzgün hədəf jurnalındakı PRESENT faktını
dəyişməz saxlayır; sahibin mövcud iştirak qərarı ayrıca qeyd olunur.
Native parser tarix≤21oktyabr, eyni tələbə/hadisə/fənn, müəllim/qrup və
tam tətbiq edilmiş canonical mapping/version zəncirini yoxlayır. Source markın
balı, o cümlədən0, varsa əməliyyat dayanır. Cari hədəfdə zidd insan qeydi,
bal, dəyişmiş source pin və ya əvvəlki rəsmi source düzəlişi də hold yaradır.

Yalnız iki source attendance statusu rəsmi `JournalCorrection` ilə PRESENT
olur. Bal, `entered_by`, digər xanalar, predecessor əlaqəsi və bütün kredit
qeydləri qorunur. Düzəldən actual yoxlanmış operatordur; mövcud superadmin
sənədsiz keçid PDF-i və authority/source SHA-lı izahlı qeyd saxlanır.

Hər hədəfin əvvəl/sonra counter proqnozu şəxsi authority-dədir. Native dry
onu bütün cari kredit və successor/predecessor qrafından hesablayıb tutuşdurur;
uyğunsuzluq hold-dur. Counter-lər native rəsmi servislə yenidən hesablanır.
Postcondition iki PRESENT markı, dəqiq iki rəsmi correction, bal/müəlliflik
qorunması və kanonik counter uyğunluğunu ayrıca tələb edir. Per-row preview
receipt-in tenant daxilindəki audit gövdəsində saxlanır; CLI-yə çıxmır.

Dry də authority tələb edir və yazı etmir. Apply təzə baseline və uğurlu
backup tələb edir; repeat eyni receipt və dəyişməz qrafla no-op-dur. Undo
yalnız ilkin receipt-in dəqiq iki correction-ını append-only reversal ilə
geri qaytarır. Qeyri-müəyyən workflow nəticəsi avtomatik təkrar edilmir.
