"""Bərpa əmri təşkilatsız (``organization IS NULL``) profilin də girişini açır (2026-11-27).

PROBLEM. Xaric/məzun əmri girişi ``registrar.movements._sync_access_state``-də bağlayır və o, profili
``organization = org OR organization IS NULL`` ilə tapır (köhnə idxal / nümunə hesablar). 0021-in
``accounts_reinstate_student_identity`` funksiyası isə profili yalnız ``organization_id = p_organization_id`` ilə
axtarırdı — təşkilatsız profilin girişi bağlanır, amma «Bərpa et» onu heç vaxt aça bilmirdi
(``accounts_reinstate_profile_state_invalid``; Python qatında ``identity_target_cross_tenant``).

DÜZƏLİŞ (yalnız profil axtarışı + bağlanma, qalan BÜTÜN qapılar 0021-dəki kimi):

* profil ``organization_id = p_organization_id`` VƏ YA ``organization_id IS NULL`` ilə kilidlənir;
* təşkilatsız profil yalnız hesabın BAŞQA təşkilatda heç bir üzvlüyü YOXDURSA qəbul olunur
  (``accounts_reinstate_profile_cross_tenant``) — bu təşkilatda dəqiq bir üzvlük şərti onsuz da qalır;
* açılış UPDATE-i profili ``p_organization_id``-yə BAĞLAYIR. Bu həm datanı düzəldir, həm də 0018-in
  ``accounts_reject_active_staged_profile`` trigger-inin ``evidence.organization_id = NEW.organization_id`` şərtini
  ödəyir — trigger-ə TOXUNULMUR.

Aktor qapısı (``student.movement`` + ``people.manage_academic`` / ``*`` / sahib / superadmin), aktor konteksti, tenant
aktivliyi, sübut sətri və birdəfəlik istehlak DƏYİŞMİR. Geri dönüş 0021-in gövdəsini hərfi bərpa edir.
"""

import importlib

from django.db import migrations

_BASE = importlib.import_module("apps.accounts.migrations.0021_student_reinstatement_identity")

_REPLACEMENTS = (
    (
        # 1) Kilid: təşkilatsız profil də.
        """       AND profile.organization_id = p_organization_id
       AND profile.access_state = 'archived'
     FOR UPDATE;""",
        """       AND (profile.organization_id = p_organization_id OR profile.organization_id IS NULL)
       AND profile.access_state = 'archived'
     FOR UPDATE;""",
    ),
    (
        # 2) Təşkilatsız profil başqa tenant-ın hesabı ola bilməz.
        """    -- Sübut sətri hesabın BƏRPA ANINDAKI rolunu saxlayır""",
        """    IF EXISTS (
        SELECT 1 FROM public.accounts_userprofile AS profile
         WHERE profile.user_id = p_user_id AND profile.organization_id IS NULL
    ) AND EXISTS (
        SELECT 1 FROM public.organizations_membership AS membership
         WHERE membership.user_id = p_user_id
           AND membership.organization_id <> p_organization_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_reinstate_profile_cross_tenant';
    END IF;
    -- Sübut sətri hesabın BƏRPA ANINDAKI rolunu saxlayır""",
    ),
    (
        # 3) Açılış + təşkilata bağlama (trigger NEW.organization_id = sübutun təşkilatı görür).
        """       SET access_state = 'active', updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND organization_id = p_organization_id
       AND access_state = 'archived';""",
        """       SET access_state = 'active',
           organization_id = p_organization_id,
           updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND (organization_id = p_organization_id OR organization_id IS NULL)
       AND access_state = 'archived';""",
    ),
)


def _forward_sql() -> str:
    sql = _BASE._FORWARD
    for old, new in _REPLACEMENTS:
        if sql.count(old) != 1:  # pragma: no cover — 0021 dondurulub; dəyişsə miqrasiya yüksək səslə dayanır
            raise RuntimeError(f"0039: 0021 gövdəsində gözlənilən fraqment tapılmadı: {old[:60]!r}")
        sql = sql.replace(old, new)
    return sql


FORWARD = _forward_sql()
REVERSE = _BASE._FORWARD


class Migration(migrations.Migration):

    dependencies = [("accounts", "0038_remote_journal_access_2026_11_20")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
