"""«Fənn qovluğu» kabinet bölmələrinin KONTEKSTİ (profil kabineti — ``apps.accounts`` shell-i).

Üç bölmə (slug-lar ``constants.SECTION_*``):

* ``subject-folders``      — müəllimin qovluqları və qovluq redaktoru (``teacher``);
* ``subject-folder-review`` — müəllimin göndəriş yoxlaması (``review``);
* ``my-subject-folders``   — tələbənin qovluqları, materialları və tapşırıqları (``student``).

Şablonlar ``subject_folder_cabinet`` tag-ları ilə bu funksiyaları çağırır (surveys
naxışı): ``accounts`` bu app-ı Python səviyyəsində İDXAL ETMİR, yalnız bölməni qeyd
edir və wrapper partial-dan buradakı şablonu daxil edir. Vəziyyət URL-dədir
(``sf_*`` parametrləri) — fraqment endpoint-i sorğunu kanonik profil URL-inə
çevirdiyi üçün tam səhifə və AJAX render eynidir. Yazı YOXDUR (GET) — əməllər
``apps.subject_folder.web``-dədir.
"""
