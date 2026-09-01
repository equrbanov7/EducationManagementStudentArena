"""Bu qovluq PYTEST TƏRƏFİNDƏN TOPLANMIR — istinad materialıdır.

Buradakı qoşqular **Node + jsdom** tələb edir (CI-da node quraşdırılmayıb) və
əl ilə işlədilmək üçündür.  Toplanmasına icazə versək CI hər işləyişdə çökərdi.

Niyə saxlanılır: bunlar sillabus redaktorunun **göndərilən JS-ini həqiqətən icra
edən** yeganə sübutdur.  Repo daxilindəki adi testlər JS-in Python güzgüsünü
(``editor_dom.py``) işlədir və məzmunu pozan mutasiyaları TUTMUR — bax
``docs/frontend/SILLABUS_REDAKTOR_QALAN_IS.md``, 1-ci maddə.

Bu qoşqu 19 mutasiyanın 19-unu öldürmüşdü.  Daimi qapıya çevirmək üçün CI-a
node əlavə olunmalıdır (həmin sənəddə ölçüsü və variantları yazılıb).
"""

collect_ignore_glob = ["*"]
