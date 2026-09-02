"""E-poçt qüsuru olan legacy kimliyi HESABSIZ qoymamaq üçün sintetik e-poçt.

Problem (2026-09-02 auditi, P0-2)
---------------------------------
``account_cutover`` e-poçtun formasına görə üç qərar verir və üçünün də nəticəsi
eynidir — sətir staging-ə buraxılmır:

* ``legacy_account_email_invalid`` — mənbədə ``…@wcu.edu.a``, ``sohretaga``,
  ``resadbagirov@hotmailcom`` kimi sınıq dəyər (85 sətir);
* ``legacy_account_email_blank`` — dəyər yoxdur (1 sətir);
* ``legacy_account_email_duplicate_source`` — İKİ fərqli legacy sətri eyni
  e-poçtu paylaşır; qayda **hər iki tərəfi** karantinə salır (28 sətir = 14 cüt).

Ölçülmüş nəticə: **100 tələbə + 14 işçi hədəfdə ÜMUMİYYƏTLƏ yoxdur** — nə hesab,
nə üzvlük, nə akademik qeyd.  14 cütün heç birində «qalib» seçilmədiyi üçün
``xeyalebalayeva0@wcu.edu.az``, ``lalazeinaal@gmail.com`` kimi e-poçtlar hədəfdə
**heç bir sətirdə** yoxdur, sahibləri isə sistemdən tamamilə silinib.  12 belə
işçiyə bağlı 62 legacy jurnal müəllimsiz qalıb.

Qərar
-----
E-poçt **kimlik açarı deyil** — o, əlaqə kanalıdır.  Kimlik açarı username-dir
(``myedu.{entity_type}.{legacy_pk}``) və o, tərifinə görə unikaldır.  Ona görə
e-poçt qüsuru artıq hesabı ləğv etmir: sətir **deterministik yer-tutucu**
e-poçtla staged olunur

    myedu.{entity_type}.{legacy_pk}@placeholder.invalid

və toqquşma/qüsur faktı ``LegacyMigrationIssue`` xəbərdarlığı kimi qeydə düşür.

``.invalid`` TLD RFC 2606 ilə **rezerv edilib** — belə ünvana heç vaxt poçt
göndərilə bilməz, yəni yer-tutucu səhvən real ünvan kimi işlənə bilməz.
Hesab onsuz da ``email_verified=False``, parolsuz və ``password_change_required``
ilə gəlir; real e-poçt ilk girişdə / RİM tərəfindən toplanır.

Nə DƏYİŞMİR
-----------
* Mənbə dəyəri **pozulmur**: xam e-poçt ``source_row_hash``-in içindədir və
  ledger-də olduğu kimi qalır — yer-tutucu yalnız HƏDƏF sətrinə yazılır.
* Username toqquşması, username formatı, probe xətası kimi **e-poçtdan kənar**
  hər bloklayıcı qayda öz gücündə qalır: belə sətir yenə karantindədir.
* E-poçta heç bir authority verilmir; ``authoritative_email_policy`` yer-tutucunu
  da rədd edir və sətir ``legacy_account_email_untrusted`` ilə contact-pending
  zolağına düşür (``stage_contact_pending`` açarı ilə idarə olunur).
"""

from __future__ import annotations

from dataclasses import replace

from .account_cutover import ProjectedAccountIdentity, classify_projected_account_cutover
from .field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    LegacySafeProjection,
)
from .rehearsal_contracts import LegacyRehearsalEvidenceError

#: RFC 2606 ilə rezerv edilmiş TLD — bu domenə poçt getməsi mümkün deyil.
PLACEHOLDER_EMAIL_DOMAIN = "placeholder.invalid"

#: Yer-tutucunun yazıldığı sətir üçün əlavə edilən qayda kodu.
PLACEHOLDER_RULE_CODE = "legacy_account_email_placeholder_synthesised"

#: MƏHZ e-poçtun formasına/təkrarına görə bloklanan qaydalar.  Username tərəfli
#: kolliziyalar (``legacy_account_username_collision`` və s.) QƏSDƏN yoxdur:
#: onlar kimlik açarının özünə toxunur və yer-tutucu ilə həll olunmur.
EMAIL_SHAPE_RULES = frozenset(
    {
        "legacy_account_email_blank",
        "legacy_account_email_collision",
        "legacy_account_email_duplicate_existing",
        "legacy_account_email_duplicate_source",
        "legacy_account_email_invalid",
        "legacy_account_username_email_collision",
        "legacy_account_username_email_duplicate_source",
    }
)

#: Yer-tutucu ilə birlikdə qala bilən, bloklamayan qayda.
_TOLERATED_RULES = frozenset({"legacy_account_email_untrusted"})


def placeholder_email(entity_type: str, legacy_pk: int) -> str:
    """Deterministik yer-tutucu — username konvensiyası ilə eyni forma."""

    if type(entity_type) is not str or not entity_type:
        raise ValueError("legacy_account_placeholder_entity_type_invalid")
    if type(legacy_pk) is not int or legacy_pk <= 0:
        raise ValueError("legacy_account_placeholder_legacy_pk_invalid")
    return f"myedu.{entity_type}.{legacy_pk}@{PLACEHOLDER_EMAIL_DOMAIN}"


def is_placeholder_email(value: object) -> bool:
    """Hədəfdəki e-poçtun yer-tutucu olub-olmadığı (təmiz funksiya)."""

    return type(value) is str and value.strip().lower().endswith(f"@{PLACEHOLDER_EMAIL_DOMAIN}")


def needs_placeholder(rule_codes) -> bool:
    """Sətri MƏHZ e-poçt qüsuru bloklayırmı?

    ``True`` yalnız o halda ki, ən azı bir e-poçt-forma qaydası var VƏ bütün
    qaydalar ya e-poçt-forma, ya da dözümlü (``untrusted``) qaydadır.  Bir
    username qaydası belə varsa cavab ``False``-dur — sətir karantində qalır.
    """

    codes = frozenset(rule_codes or ())
    if not codes & EMAIL_SHAPE_RULES:
        return False
    return codes <= (EMAIL_SHAPE_RULES | _TOLERATED_RULES)


#: ``source_kind`` → sətrin gəldiyi audited kontrakt.
_CONTRACTS = {"student": STUDENT_IDENTITY_FIELDS, "worker": WORKER_IDENTITY_FIELDS}


def substituted_identity(identity: ProjectedAccountIdentity, *, entity_type: str, legacy_pk: int):
    """Eyni proyeksiya, yalnız ``email`` sütunu yer-tutucu ilə əvəzlənib.

    Sətir dəyişməzdir, ona görə yenisi EYNİ audited kontraktdan, EYNİ sahə
    sırası və EYNİ barmaq izi ilə qurulur — ``account_cutover._source_kind``
    yoxlaması (sahə adlarının bire-bir eyniliyi) beləcə pozulmur.  Heç bir yeni
    sütun proyeksiyaya girmir: yalnız mövcud ``email`` dəyəri əvəzlənir.
    """

    if not isinstance(identity, ProjectedAccountIdentity):
        raise ValueError("legacy_account_placeholder_identity_invalid")
    contract = _CONTRACTS.get(identity.source_kind)
    if contract is None:
        raise ValueError("legacy_account_placeholder_source_kind_invalid")
    values = dict(identity.projected_row.to_transform_dict())
    values["email"] = placeholder_email(entity_type, legacy_pk)
    projection = LegacySafeProjection._from_contract(
        contract=contract,
        source_field_count=len(contract.allowed_fields),
        credential_field_count=0,
    )
    return ProjectedAccountIdentity(
        projected_row=projection.accept_extracted_row(values),
        proposed_username=identity.proposed_username,
    )


def apply_email_placeholders(context, rows, classifications):
    """P0-2: e-poçtu sınıq/təkrar olan sətri hesabsız qoymaq ƏVƏZİNƏ yer-tutucu ver.

    İki keçidli təsnifat: birinci keçid kim bloklanıb deyir, ikinci keçid isə
    əvəzlənmiş kohortu BÜTÖV halda yenidən təsnif edir — yer-tutucular
    ``legacy_pk``-yə görə unikal olduğu üçün ikinci keçiddə yeni dublikat
    yaranmır, mövcud hədəf sətirləri ilə də toqquşmur.  Sətrin ORİJİNAL qayda
    kodları ``placeholder_rules``-da saxlanılır və issue kimi yazılır: toqquşma
    faktı ledger-dən silinmir, sadəcə artıq hesabı ləğv etmir.
    """

    targets = [index for index, item in enumerate(classifications) if needs_placeholder(item.rule_codes)]
    if not targets:
        return rows, classifications, 0
    patched = list(rows)
    for index in targets:
        row = rows[index]
        patched[index] = replace(
            row,
            identity=substituted_identity(row.identity, entity_type=row.entity_type, legacy_pk=row.legacy_pk),
            placeholder_rules=tuple(classifications[index].rule_codes),
        )
    reclassified = classify_projected_account_cutover(
        [row.identity for row in patched],
        authoritative_email_policy=context.authoritative_email_policy,
        target_identity_snapshot=context.target_identity_snapshot,
    )
    if len(reclassified) != len(patched):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_classification_shape_invalid")
    return patched, reclassified, len(targets)


__all__ = [
    "EMAIL_SHAPE_RULES",
    "apply_email_placeholders",
    "PLACEHOLDER_EMAIL_DOMAIN",
    "PLACEHOLDER_RULE_CODE",
    "is_placeholder_email",
    "needs_placeholder",
    "placeholder_email",
    "substituted_identity",
]
