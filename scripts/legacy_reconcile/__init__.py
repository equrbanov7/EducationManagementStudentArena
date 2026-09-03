"""``scripts/legacy_reconcile_report.py`` üçün OXU-ONLY uzlaşdırma paketi.

Bu paket MariaDB mənbəsi ilə köçürülmüş PostgreSQL bazasını tutuşdurur və
insanın oxuya biləcəyi Markdown hesabat çıxarır.  HEÇ BİR yazı əməliyyatı
yoxdur — hər iki tərəfə yalnız ``SELECT`` gedir (bax ``transport``).

Django-dan asılı deyil: repetisiya işləyərkən müdaxilə riski olmasın deyə
birbaşa SQL işlədilir.
"""
