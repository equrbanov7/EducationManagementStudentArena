"""Bərpa əmri ilə girişin açılması — `accounts_reinstate_student_identity` (2026-09-06).

NİYƏ AYRICA FUNKSİYA. `archived → active` keçidi 0016-nın trigger-i ilə qorunur:
sübut sətri olmadan `42501`. 0018 həmin qapıya BİR yol açdı —
`accounts_restore_archived_identity`, «səhv arxiv qərarının geri alınması» üçün:
aktor `member.edit` tələb edir, üzvlüyün rolunu SIFIRLAYIR və səbəb kodları
kimlik-doğrulama kodlarıdır (registry match / manual verification / signed export).

Tələbənin BƏRPA ƏMRİ başqa haldır (sahib qərarı, 2026-09-06 — «açılsın»):

* səlahiyyət mənbəyi rəsmi əmrdir, e-poçt sübutu deyil → yeni səbəb kodu
  `student_reinstatement_order`;
* aktor tələbə xidmətləri əməkdaşıdır: `member.edit` YOX, amma
  `student.movement` + `people.manage_academic` VAR (servis qatındakı eyni
  səlahiyyət ayrılığı — `people/movements.py::_require`). Funksiya HƏR İKİSİNİ
  tələb edir (`?&`), yəni tək açar kifayət etmir;
* üzvlüyün ROLU DƏYİŞDİRİLMİR — tələbə tələbə olaraq qalır; yalnız üzvlük
  passivdirsə yenidən aktivləşir.

Trigger-ə TOXUNULMUR: 0018-in `accounts_accountrestoreevidence` yolu səbəb
kodunu yoxlamır (kod yoxlaması funksiyanın içindədir), ona görə bu funksiya da
həmin cədvələ yazır və eyni GUC-u qoyur.

Geri dönüş funksiyanı silir — mövcud sübut sətirləri append-only qalır.
"""

from django.db import migrations

_FORWARD = """
CREATE OR REPLACE FUNCTION accounts_reinstate_student_identity(
    p_evidence_id uuid,
    p_user_id bigint,
    p_organization_id uuid,
    p_actor_id bigint,
    p_evidence_digest text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    membership_count integer;
    current_role_ref text;
BEGIN
    IF p_evidence_id IS NULL OR p_evidence_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'accounts_reinstate_evidence_invalid';
    END IF;
    IF COALESCE(current_setting('app.current_user_id', true), '') <> p_actor_id::text THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_reinstate_actor_context_mismatch';
    END IF;
    PERFORM 1
      FROM public.auth_user AS actor
      JOIN public.accounts_userprofile AS actor_profile
        ON actor_profile.user_id = actor.id
     WHERE actor.id = p_actor_id
       AND actor.is_active
       AND actor_profile.access_state = 'active'
     FOR UPDATE OF actor;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_reinstate_actor_inactive';
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM public.organizations_organization AS organization
         WHERE organization.id = p_organization_id
           AND organization.is_active
           AND organization.status = 'active'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_reinstate_tenant_inactive';
    END IF;
    -- Səlahiyyət: superadmin / təşkilat sahibi, yaxud HƏR İKİ açarı daşıyan rol.
    -- `?&` (hamısı) QƏSDƏNDİR — `student.movement` tək başına kifayət etmir.
    IF NOT EXISTS (
        SELECT 1
          FROM public.auth_user AS actor
         WHERE actor.id = p_actor_id
           AND (
               actor.is_superuser
               OR EXISTS (
                   SELECT 1 FROM public.organizations_organization AS organization
                    WHERE organization.id = p_organization_id
                      AND organization.owner_id = p_actor_id
               )
               OR EXISTS (
                   SELECT 1
                     FROM public.organizations_membership AS membership
                     JOIN public.organizations_role AS role ON role.id = membership.role_id
                    WHERE membership.user_id = p_actor_id
                      AND membership.organization_id = p_organization_id
                      AND membership.is_active
                      AND role.organization_id = p_organization_id
                      AND role.is_active
                      AND (
                          role.permissions ? '*'
                          OR role.permissions ?& ARRAY['student.movement', 'people.manage_academic']
                      )
               )
           )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'accounts_reinstate_actor_permission_denied';
    END IF;
    PERFORM 1
      FROM public.auth_user AS account
     WHERE account.id = p_user_id
       AND account.is_active
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_reinstate_target_state_invalid';
    END IF;
    PERFORM 1
      FROM public.accounts_userprofile AS profile
     WHERE profile.user_id = p_user_id
       AND profile.organization_id = p_organization_id
       AND profile.access_state = 'archived'
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_reinstate_profile_state_invalid';
    END IF;
    SELECT COUNT(*) INTO membership_count
      FROM public.organizations_membership AS membership
     WHERE membership.user_id = p_user_id
       AND membership.organization_id = p_organization_id;
    IF membership_count <> 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_reinstate_membership_set_mismatch';
    END IF;
    -- Sübut sətri hesabın BƏRPA ANINDAKI rolunu saxlayır (rol dəyişdirilmir,
    -- amma audit «hansı rolla açıldı» sualına cavab verə bilməlidir).
    SELECT membership.role_id::text INTO current_role_ref
      FROM public.organizations_membership AS membership
     WHERE membership.user_id = p_user_id
       AND membership.organization_id = p_organization_id;

    PERFORM set_config('app.account_restore_evidence_id', p_evidence_id::text, true);
    INSERT INTO public.accounts_accountrestoreevidence (
        id, organization_id, user_ref, role_ref, actor_ref,
        evidence_digest, reason_code, transaction_id, created_at, consumed_at
    ) VALUES (
        p_evidence_id, p_organization_id, p_user_id::text,
        COALESCE(current_role_ref, ''),
        p_actor_id::text, p_evidence_digest, 'student_reinstatement_order',
        txid_current(), clock_timestamp(), NULL
    );
    UPDATE public.accounts_userprofile
       SET access_state = 'active', updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND organization_id = p_organization_id
       AND access_state = 'archived';
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_reinstate_profile_stale';
    END IF;
    -- Rol DƏYİŞDİRİLMİR (0018-dən fərq): tələbə tələbə qalır. Yalnız üzvlük
    -- passiv qalıbsa yenidən açılır ki, rol həlli (ACTIVE üzvlük tələb edir)
    -- işləsin.
    UPDATE public.organizations_membership
       SET is_active = TRUE,
           updated_at = clock_timestamp()
     WHERE user_id = p_user_id
       AND organization_id = p_organization_id
       AND NOT is_active;
    UPDATE public.accounts_accountrestoreevidence
       SET consumed_at = clock_timestamp()
     WHERE id = p_evidence_id
       AND consumed_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'accounts_reinstate_evidence_stale';
    END IF;
END;
$function$;

REVOKE ALL ON FUNCTION accounts_reinstate_student_identity(
    uuid, bigint, uuid, bigint, text
) FROM PUBLIC;

DO $grant$
DECLARE
    target_role text;
BEGIN
    FOR target_role IN
        SELECT rolname FROM pg_roles WHERE rolname IN ('rls_app_role', 'emsarena_app')
    LOOP
        EXECUTE format(
            'GRANT EXECUTE ON FUNCTION public.accounts_reinstate_student_identity('
            'uuid,bigint,uuid,bigint,text) TO %I', target_role
        );
    END LOOP;
END;
$grant$;
"""

_BACKWARD = """
DROP FUNCTION IF EXISTS accounts_reinstate_student_identity(uuid, bigint, uuid, bigint, text);
"""


class Migration(migrations.Migration):

    dependencies = [("accounts", "0020_rim_staff_role_choice")]

    operations = [
        migrations.RunSQL(sql=_FORWARD, reverse_sql=_BACKWARD),
    ]
