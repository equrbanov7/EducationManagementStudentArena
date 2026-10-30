# Müəllimin cari jurnalları və öz qeydlərinin tarixçəsi

Adi müəllimin `/jurnal/` səhifəsi ilkin olaraq **Cari dərs yüküm** görünüşünü açır.
Mənbə kafedraya çatmış (approved/distributed/amended və göndərilmiş distributing)
yük sətrinin həmin müəllimə müsbət saatla təyin edilmiş mühazirə/seminar/lab növüdür.
Boş, vakant, ləğv edilmiş, köhnə sahibi qalmış və ya yalnız manual/legacy payı olan
jurnal cari yükün sübutu sayılmır. Normal yazı/giriş siyasəti ayrıca qüvvədədir.

Fənn, semestr və fiziki qrup birlikdə uyğunlaşdırılır. İdarə edilmiş 233KE logical
alias metadata-sı oxunur; tarixi FK dəyişmir. Ana qrupa qeydiyyatlı alt qruplar yalnız
explicit parent_group izi, eyni təşkilat/ixtisas və ziddiyyətsiz dil/sektor/təhsil
metadatası ilə tanınır. Konkret alt qrup qeydi digər alt qruplara yayılmır.

**Əvvəlki jurnal qeydlərim** görünüşü cari yükü olmayan, lakin müəllimin real
Lesson.instructor/created_by və ya LessonMark.entered_by qeydi olan jurnalları
göstərir. Əvvəlki təhvil müşahidəçisinin mövcud oxu girişi də saxlanılır.
Tarixçə cari yük kimi hesablanmır. Keçilmiş saat yalnız explicit Lesson.instructor
üzərindən göstərilir; yaratma/xana daxil etmə ayrıca dərs sayıdır. Patok və alt
qrup jurnallarının bu rəqəmlərindən ödəniş və ya ümumi əmək haqqı hesablanmır.

Müəllim təyinatı silinib əvvəlki sahibi NULL olduqda normal jurnal girişi
genişlənmir. Canlı eyni-tenant grade.input səlahiyyətli müəllim üçün ayrıca dar
yalnız-oxu səth açılır: yalnız real müəlliflik izi olan dərslər və özünün daxil
etdiyi xanalar. Başqa müəllimin dərsləri/xanaları, yekun ballar, ixrac və tam
tələbə reyestri bu səthə daxil edilmir. Bu səth POST qəbul etmir və sxem yaratmır.

Admin, dekanlıq, koordinator və digər geniş struktur görünüşləri bu müəllim
süzgəcindən keçmir. Heç bir yük sətri, jurnal, dərs, bal, sillabus və ya qeydiyyat
silinmir. Məlumat bərpası/backfill əmri lazım deyil; dəyişiklik oxu proyeksiyasıdır.
