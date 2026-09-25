"""«Fənn qovluğu» kabinet ekranlarının HTTP qatı (JSON endpoint-lər).

Ekranların özü profil kabinetinin bölmələridir (``apps.subject_folder.cabinet`` +
``templates/subject_folder/cabinet``); bu paket YALNIZ yazı əməllərini və
çekməcə/önizləmə kimi GET fraqmentlərini verir. Hər əməl ``public`` fasadındakı
servis funksiyasını çağırır — icazə orada fail-closed yoxlanılır, burada yalnız
obyektlər AKTİV təşkilat daxilində yüklənir (tenant sərhədi RLS-ə tək qalmır).
"""
