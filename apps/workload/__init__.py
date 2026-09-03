"""Dərs yükü (tədris tapşırığı) modulu — kafedra bölgüsü + müəllim görünüşü.

Spesifikasiya: ``docs/workload/DERS_YUKU_SPEC.md``.

Bu paket F0 (bünövrə: modellər, RLS, icazələr), F3 (kafedra bölgüsü) və F4
(müəllimin «Dərs yüküm» səthi) fazalarını daşıyır. Tədris şöbəsi redaktoru (F1)
və dekanlıq təsdiqi (F2) sonrakı fazalardır — status kataloqu və modellər onları
QABAQCADAN nəzərə alır (miqrasiya qırılmasın deyə).

Modul sərhədi: burada ``apps.accounts`` importu YOXDUR; registrar/organizations
modellərinə servis qatında ``django_apps.get_model`` və string FK ilə çıxılır.
UI qatı yalnız :mod:`apps.workload.public` fasadını çağırır.
"""
