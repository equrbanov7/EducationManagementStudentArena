"""
Permission definitions and checking functions for the organizations app.
"""

from typing import List, Set

from django.utils.translation import pgettext_lazy

# DEPRECATED (FAZA 10) — legacy permission-prefix aliases.
#
# Canonical names are: grade.*, course.*, exam.*, member.*, role.*, unit.*.
# default_roles.py now emits only the canonical names, and migration
# organizations.0006 rewrites every existing Role.permissions row to the
# canonical spelling.
#
# M3 (2026-07-02): permission-matching core.permissions-a köçürülüb;
# import səthi qorunur (AGENTS §1).
from core.permissions import (  # noqa: F401
    PERMISSION_PREFIX_ALIASES,
    _permission_variants,
    _wildcard_variants,
    has_permission,
)

# Permission definitions by category
PERMISSION_CATEGORIES = {
    "organization": [
        "org.view",
        "org.edit",
        "org.settings",
        "org.manage_members",
        "org.admin.assign",
        "org.owner.assign",
        "org.delete",
    ],
    "structure": [
        "unit.view",
        "unit.create",
        "unit.edit",
        "unit.delete",
    ],
    "members": [
        "member.view",
        "member.invite",
        "member.edit",
        "member.remove",
        "member.student_manage",
    ],
    "roles": [
        "role.view",
        "role.create",
        "role.edit",
        "role.assign",
        "role.delete",
    ],
    "courses": [
        "course.view",
        "course.create",
        "course.edit",
        "course.delete",
        "assignment.delete",
        "project.delete",
        "lab.delete",
    ],
    "grading": [
        "grade.view",
        "grade.input",
        "grade.publish",
        "grade.override",
    ],
    # Jurnal düzəlişi (correction) — 2 saat/bitmiş-semestr limitlərini sənədli
    # (PDF + audit) keçmə hüququ. İKT Rəhbəri rolunun açar icazəsi.
    #
    # `journal.close` (2026-08): SEMESTR SONU toplu jurnal bağlama/açma. Köhnə
    # `grade.approve_chair` / `grade.approve_final` açarlarını əvəz edir —
    # müəllim→kafedra→dekan təsdiq zənciri sahibin qərarı ilə LƏĞV olundu, ona
    # görə "təsdiq" adlı açar saxlamaq mənasızdır. Yeni açar `journal` ailəsindədir
    # (RİM-in digər açarı `journal.correct` ilə yanaşı) və istənilən rola
    # permission-editordan verilə bilər.
    # `journal.roster` (2026-08): jurnal SİYAHISININ idarəsi — başqa (alt) qrupdan
    # tələbənin bir açılışın jurnalına əlavə edilməsi və geri götürülməsi.
    # QƏSDƏN `grade.*` ailəsində DEYİL: bu, müəllim əməli deyil — proqram
    # koordinatoru / dekanlıq səviyyəsindədir və struktur əhatəsinə (scope)
    # tabedir (bax apps/registrar/guest_roster.py).
    # `journal.reassign` (2026-08): fənnin (dərs açılışının) BAŞQA MÜƏLLİMƏ
    # təhvili — «müəllim işdən çıxdı, jurnal artıq Əlinin olsun». Yenə `grade.*`
    # ailəsində DEYİL: bal yazmaqla heç bir əlaqəsi yoxdur, əksinə — KİMİN bal
    # yazacağını təyin edir. Ayrı açar olmasaydı, `grade.*` wildcard-ı daşıyan
    # hər müəllim öz jurnalını başqasının üstünə ata bilərdi.
    "journal": [
        "journal.view",
        "journal.correct",
        "journal.close",
        "journal.roster",
        "journal.reassign",
    ],
    # Sillabus axını (apps.syllabus) — müəllim yazır/göndərir, kafedra müdiri
    # təsdiqləyir. Qərar açarları QƏSDƏN AYRIDIR: `syllabus.review` (növbəni açıb
    # baxmaq) təsdiq hüququ VERMİR; `syllabus.approve`, `syllabus.revise` və
    # `syllabus.reject` ayrı-ayrı verilə bilər ki, «baxan» ilə «qərar verən»
    # bir-birindən ayrıla bilsin (əsasnamə 5.5 səlahiyyət ayrılığı prinsipi).
    # `syllabus.manage` — administrativ əməllər (arxivləmə, kütləvi köçürmə).
    "syllabus": [
        "syllabus.view",
        "syllabus.edit",
        "syllabus.submit",
        "syllabus.review",
        "syllabus.approve",
        "syllabus.revise",
        "syllabus.reject",
        "syllabus.manage",
    ],
    # Dərs yükü (apps.workload) — illik tədris tapşırığı və kafedra bölgüsü.
    # Açarlar QƏSDƏN AYRIDIR: `workload.view` (baxış) təsdiq/bölgü hüququ
    # VERMİR; `workload.distribute` yalnız kafedra müdirindədir, `workload.manage`
    # sənədi yaradıb sətirləri redaktə etməkdir. `submit`/`review`/`approve`
    # açarları F1–F2 (tədris şöbəsi + dekanlıq) fazaları üçün ƏVVƏLCƏDƏN
    # kataloqdadır — hələ heç bir default rola verilmir.
    "workload": [
        "workload.view",
        "workload.manage",
        "workload.submit",
        "workload.review",
        "workload.approve",
        "workload.distribute",
        "workload.report",
    ],
    # Tələbə qrupları (exams.StudentGroup) — qrup yaratmaq/idarə etmək açarı
    # permission-editordan istənilən rola (dekan, koordinator…) verilə bilər.
    # `group.manage` qapısı: apps/exams/views/teacher/groups.py.
    "groups": [
        "group.view",
        "group.manage",
    ],
    # `final_score.entry` (2026-08): KAĞIZ üzərində keçən yazılı/praktiki imtahanın
    # YEKUN balının sistemə əl ilə köçürülməsi (İmtahan Mərkəzi → «İmtahan balının
    # daxil edilməsi»). Test imtahanı avtomatik körpü ilə gəlir.
    # ⚠️ PREFİKS QƏSDƏN `exam.` DEYİL: sahibin qərarı ilə yekun imtahan balını
    # YALNIZ İmtahan Mərkəzi yaza bilər — `exam.*` wildcard-ı daşıyan dekan,
    # kafedra müdiri, prorektor və müəllim bu səlahiyyəti AVTOMATİK almamalıdır.
    # Ayrıca prefiks wildcard əhatəsini struktur olaraq kəsir; lazım olan rola
    # açar permission-editordan AÇIQ verilir (audit izi ilə).
    "exams": [
        "exam.view",
        "exam.create",
        "exam.edit",
        "exam.manage",
        "exam.host",
        "exam.delete",
        "final_score.entry",
    ],
    "appeal": [
        "appeal.create",
        "appeal.respond",
        "appeal.decide",
    ],
    "analytics": [
        "analytics.view_own",
        "analytics.view_unit",
        "analytics.view_all",
    ],
    "qa": [
        "qa.view",
        "qa.review",
        "qa.flag",
    ],
    "audit": [
        "audit.view",
        "audit.export",
    ],
    # RİM (hesab idarəetmə mərkəzi) — köhnə sistemdən idxal olunmuş hesabların
    # kredensial/blok/silmə/redaktə əməliyyatları. Bu icazələr QƏSDƏN `member.*`
    # dəstindən AYRIDIR: `member.edit` təşkilat üzvlüyünü (vəzifə, kafedra,
    # scope_unit) idarə edir, `user.*` isə HESABIN ÖZÜNÜ (parol, giriş bloku,
    # soft-delete, şəxsi məlumat). Birini verib digərini verməmək mümkün olmalıdır.
    "users": [
        "user.search",
        "user.credentials",
        "user.block",
        "user.soft_delete",
        "user.edit",
        # Əsasnamə 5.5 («Təhlükəsizlik üzrə səlahiyyət ayrılığı») — YÜKSƏK RİSKLİ
        # əməliyyat: hədəfə administrator-ekvivalent (level >= 80) səlahiyyət
        # vermək. QƏSDƏN ayrıca açardır: `user.edit`/`user.credentials` daşıyan
        # operator avtomatik olaraq admin YARADA bilməməlidir. Belə əməliyyat
        # ayrıca icazə + ayrıca audit qeydi tələb edir.
        "user.grant_privileged",
    ],
    # «Müəllimlər» / «Tələbələr» kataloqu (apps/accounts/services/people).
    #
    # QƏSDƏN `user.*`-dan AYRI PREFİKSDİR. `user.*` RİM mərkəzinin BÜTÜN
    # hesablar üzrə (org-wide) əməliyyat dəstidir; `people.*` isə struktur
    # SCOPE-una tabe olan kataloqdur — dekan yalnız öz fakültəsini görür.
    # Eyni prefiksdə olsaydılar, RİM-ə verilən `user.*` wildcard-ı kataloqu da
    # avtomatik açardı və əksinə: dekana verilən kataloq açarı onu RİM
    # mərkəzinə buraxardı. Ayrı prefiks bu iki səthi struktur olaraq ayırır.
    #
    # Baxış açarları ayrıdır ki, «yalnız tələbələri görən» tyutor kimi rollar
    # qurula bilsin; əlaqə (telefon/FİN) və demoqrafiya (cins/doğum tarixi)
    # isə ayrıca PII qapılarıdır — siyahını görmək onları görmək demək deyil.
    "people": [
        "people.view_teachers",
        "people.view_students",
        "people.view_contacts",
        "people.view_demographics",
        "people.manage_status",
        "people.manage_teacher_role",
        # `people.manage_academic` (2026-08): tələbənin AKADEMİK qeydini idarə
        # etmək — rəsmi qrup köçürməsi və akademik status (məzuniyyət/xaric/
        # məzun). QƏSDƏN `people.manage_status`-dan AYRIDIR: o, HESABI dayandırır
        # (giriş hüququ), bu isə tələbənin akademik yerini dəyişir. Dekanlıq öz
        # fakültəsinin tələbəsini köçürə bilməli, amma heç kimin hesabını
        # dayandırmamalı ola bilər — iki səlahiyyət bir açara yığılsaydı, biri
        # digərini gizlicə verərdi.
        "people.manage_academic",
    ],
}

# Kateqoriya və icazə açarlarının AZ etiketləri.
#
# Niyə server tərəfdə? İcazə redaktoru öz etiketlərini JS-də saxlayır
# (`permission_editor/labels.js`), amma icazə adları həm də SERVER tərəfdə
# render olunan səthlərdə (RİM mərkəzinin "sizin səlahiyyətləriniz" paneli,
# audit izahatları) göstərilir. Orada JS xəritəsi əlçatan deyil.
#
# Xəritə natamam ola bilər — etiketi olmayan açar üçün çağıran tərəf açarın
# özünü göstərir (`permission_label()` belə davranır).
PERMISSION_CATEGORY_LABELS = {
    "organization": "Təşkilat",
    "structure": "Struktur",
    "members": "Üzvlər",
    "roles": "Rollar",
    "courses": "Kurslar",
    "grading": "Qiymətləndirmə",
    "journal": "Jurnal",
    "syllabus": "Sillabus",
    "workload": "Dərs yükü",
    "exams": "İmtahanlar",
    "appeal": "Apellyasiya",
    "analytics": "Analitika",
    "qa": "Keyfiyyət",
    "audit": "Audit jurnalı",
    "users": "Hesab idarəetməsi (RİM)",
    "people": "Müəllim və tələbə kataloqu",
}

# ---------------------------------------------------------------------------
# İnsan-oxunaqlı icazə etiketləri (permission-editor üçün).
#
# Hər kataloq açarının AZ etiketi — editor UI-da açar kodu ilə YANAŞI göstərilir
# (məs. «Qrup yaratmaq/idarə etmək (group.manage)»). msgid toqquşmalarından
# qaçmaq üçün kontekstli pgettext_lazy istifadə olunur; default dil AZ olduğundan
# msgid-in özü ekranda görünən mətndir. Yeni açar əlavə edəndə buraya da etiket
# yazılmalıdır — testlə qorunur (test_permissions.py: kataloq ↔ etiket tam üst-üstə).
# ---------------------------------------------------------------------------
_PERM_CTX = "organizations.permission.label"

PERMISSION_LABELS = {
    # organization
    "org.view": pgettext_lazy(_PERM_CTX, "Təşkilat məlumatına baxış"),
    "org.edit": pgettext_lazy(_PERM_CTX, "Təşkilat məlumatını redaktə etmək"),
    "org.settings": pgettext_lazy(_PERM_CTX, "Təşkilat ayarlarını idarə etmək"),
    "org.manage_members": pgettext_lazy(_PERM_CTX, "Təşkilat üzvlərini idarə etmək"),
    "org.admin.assign": pgettext_lazy(_PERM_CTX, "Təşkilat administratoru təyin etmək"),
    "org.owner.assign": pgettext_lazy(_PERM_CTX, "Təşkilat sahibi təyin etmək"),
    "org.delete": pgettext_lazy(_PERM_CTX, "Təşkilatı silmək"),
    # structure
    "unit.view": pgettext_lazy(_PERM_CTX, "Struktur vahidlərinə baxış"),
    "unit.create": pgettext_lazy(_PERM_CTX, "Struktur vahidi yaratmaq"),
    "unit.edit": pgettext_lazy(_PERM_CTX, "Struktur vahidini redaktə etmək"),
    "unit.delete": pgettext_lazy(_PERM_CTX, "Struktur vahidini silmək"),
    # members
    "member.view": pgettext_lazy(_PERM_CTX, "Üzvlərə baxış"),
    "member.invite": pgettext_lazy(_PERM_CTX, "Üzv dəvət etmək"),
    "member.edit": pgettext_lazy(_PERM_CTX, "Üzv məlumatını redaktə etmək"),
    "member.remove": pgettext_lazy(_PERM_CTX, "Üzvü təşkilatdan çıxarmaq"),
    "member.student_manage": pgettext_lazy(_PERM_CTX, "Tələbə üzvlüyünü idarə etmək"),
    # roles
    "role.view": pgettext_lazy(_PERM_CTX, "Rollara baxış"),
    "role.create": pgettext_lazy(_PERM_CTX, "Rol yaratmaq"),
    "role.edit": pgettext_lazy(_PERM_CTX, "Rolu redaktə etmək"),
    "role.assign": pgettext_lazy(_PERM_CTX, "Rol təyin etmək"),
    "role.delete": pgettext_lazy(_PERM_CTX, "Rolu silmək"),
    # courses
    "course.view": pgettext_lazy(_PERM_CTX, "Kurslara baxış"),
    "course.create": pgettext_lazy(_PERM_CTX, "Kurs yaratmaq"),
    "course.edit": pgettext_lazy(_PERM_CTX, "Kursu redaktə etmək"),
    "course.delete": pgettext_lazy(_PERM_CTX, "Kursu silmək"),
    "assignment.delete": pgettext_lazy(_PERM_CTX, "Sərbəst işi silmək"),
    "project.delete": pgettext_lazy(_PERM_CTX, "Kurs işini silmək"),
    "lab.delete": pgettext_lazy(_PERM_CTX, "Lab işini silmək"),
    # grading
    "grade.view": pgettext_lazy(_PERM_CTX, "Qiymətlərə baxış"),
    "grade.input": pgettext_lazy(_PERM_CTX, "Qiymət yazmaq"),
    "grade.publish": pgettext_lazy(_PERM_CTX, "Qiymətləri dərc etmək"),
    "grade.override": pgettext_lazy(_PERM_CTX, "Qiyməti məcburi dəyişmək"),
    # journal
    "journal.view": pgettext_lazy(_PERM_CTX, "Jurnala baxış"),
    "journal.correct": pgettext_lazy(_PERM_CTX, "Jurnalda sənədli düzəliş etmək"),
    "journal.close": pgettext_lazy(_PERM_CTX, "Semestr sonu jurnalları bağlamaq/açmaq"),
    "journal.roster": pgettext_lazy(_PERM_CTX, "Jurnala alt qrupdan tələbə əlavə etmək/çıxarmaq"),
    "journal.reassign": pgettext_lazy(_PERM_CTX, "Fənni başqa müəllimə təhvil vermək"),
    # syllabus
    "syllabus.view": pgettext_lazy(_PERM_CTX, "Sillabuslara baxış"),
    "syllabus.edit": pgettext_lazy(_PERM_CTX, "Sillabus qaralamasını redaktə etmək"),
    "syllabus.submit": pgettext_lazy(_PERM_CTX, "Sillabusu təsdiqə göndərmək / geri çağırmaq"),
    "syllabus.review": pgettext_lazy(_PERM_CTX, "Sillabus təsdiq növbəsinə baxmaq"),
    "syllabus.approve": pgettext_lazy(_PERM_CTX, "Sillabusu təsdiqləmək"),
    "syllabus.revise": pgettext_lazy(_PERM_CTX, "Sillabusu düzəliş üçün geri qaytarmaq"),
    "syllabus.reject": pgettext_lazy(_PERM_CTX, "Sillabusu rədd etmək"),
    "syllabus.manage": pgettext_lazy(_PERM_CTX, "Sillabusları idarə etmək (arxiv, köçürmə)"),
    # workload
    "workload.view": pgettext_lazy(_PERM_CTX, "Dərs yükünə baxış"),
    "workload.manage": pgettext_lazy(_PERM_CTX, "Tədris tapşırığını yaratmaq/redaktə etmək"),
    "workload.submit": pgettext_lazy(_PERM_CTX, "Tapşırığı dekanlığa göndərmək"),
    "workload.review": pgettext_lazy(_PERM_CTX, "Tapşırıq sətirlərinə viza vermək"),
    "workload.approve": pgettext_lazy(_PERM_CTX, "Tapşırığı təsdiqləmək"),
    "workload.distribute": pgettext_lazy(_PERM_CTX, "Dərs yükünü müəllimlərə bölmək"),
    "workload.report": pgettext_lazy(_PERM_CTX, "Dərs yükü hesabatları və ixracı"),
    # groups
    "group.view": pgettext_lazy(_PERM_CTX, "Qruplara baxış"),
    "group.manage": pgettext_lazy(_PERM_CTX, "Qrup yaratmaq/idarə etmək"),
    # exams
    "exam.view": pgettext_lazy(_PERM_CTX, "İmtahanlara baxış"),
    "exam.create": pgettext_lazy(_PERM_CTX, "İmtahan yaratmaq"),
    "exam.edit": pgettext_lazy(_PERM_CTX, "İmtahanı redaktə etmək"),
    "exam.manage": pgettext_lazy(_PERM_CTX, "İmtahan prosesini idarə etmək"),
    "exam.host": pgettext_lazy(_PERM_CTX, "İmtahan keçirmək"),
    "exam.delete": pgettext_lazy(_PERM_CTX, "İmtahanı silmək"),
    "final_score.entry": pgettext_lazy(_PERM_CTX, "İmtahan balını sistemə daxil etmək"),
    # appeal
    "appeal.create": pgettext_lazy(_PERM_CTX, "Apellyasiya yaratmaq"),
    "appeal.respond": pgettext_lazy(_PERM_CTX, "Apellyasiyaya cavab vermək"),
    "appeal.decide": pgettext_lazy(_PERM_CTX, "Apellyasiya qərarı vermək"),
    # analytics
    "analytics.view_own": pgettext_lazy(_PERM_CTX, "Öz analitikasına baxış"),
    "analytics.view_unit": pgettext_lazy(_PERM_CTX, "Struktur üzrə analitikaya baxış"),
    "analytics.view_all": pgettext_lazy(_PERM_CTX, "Bütün analitikaya baxış"),
    # qa
    "qa.view": pgettext_lazy(_PERM_CTX, "Keyfiyyət yoxlamalarına baxış"),
    "qa.review": pgettext_lazy(_PERM_CTX, "Keyfiyyət rəyi vermək"),
    "qa.flag": pgettext_lazy(_PERM_CTX, "Keyfiyyət işarəsi qoymaq"),
    # audit
    "audit.view": pgettext_lazy(_PERM_CTX, "Audit jurnalına baxış"),
    "audit.export": pgettext_lazy(_PERM_CTX, "Audit jurnalını ixrac etmək"),
    # users (RİM hesab idarəetməsi)
    "user.search": pgettext_lazy(_PERM_CTX, "İstifadəçi axtarışı"),
    "user.credentials": pgettext_lazy(_PERM_CTX, "Parol təyini / bərpası"),
    "user.block": pgettext_lazy(_PERM_CTX, "Hesabı bloklamaq / blokdan çıxarmaq"),
    "user.soft_delete": pgettext_lazy(_PERM_CTX, "Hesabı silmək / bərpa etmək"),
    "user.edit": pgettext_lazy(_PERM_CTX, "Şəxsi məlumatların redaktəsi"),
    "user.grant_privileged": pgettext_lazy(_PERM_CTX, "İmtiyazlı (administrator) səlahiyyət vermək"),
    # people (müəllim/tələbə kataloqu — struktur scope-una tabe)
    "people.view_teachers": pgettext_lazy(_PERM_CTX, "Müəllim kataloquna baxış"),
    "people.view_students": pgettext_lazy(_PERM_CTX, "Tələbə kataloquna baxış"),
    "people.view_contacts": pgettext_lazy(_PERM_CTX, "Kataloqda əlaqə məlumatını görmək"),
    "people.view_demographics": pgettext_lazy(_PERM_CTX, "Kataloqda cins və yaş məlumatını görmək"),
    "people.manage_status": pgettext_lazy(_PERM_CTX, "Kataloqdan hesabı dayandırmaq / bərpa etmək"),
    "people.manage_teacher_role": pgettext_lazy(_PERM_CTX, "Müəllim statusunu vermək / çıxarmaq"),
    "people.manage_academic": pgettext_lazy(_PERM_CTX, "Tələbənin qrupunu köçürmək və akademik statusunu dəyişmək"),
}


def get_permission_label(permission: str) -> str:
    """İcazənin insan-oxunaqlı etiketi; kataloqda yoxdursa boş sətir."""
    label = PERMISSION_LABELS.get(permission)
    return str(label) if label is not None else ""


def get_all_permissions() -> List[str]:
    """
    Get a flat list of all available permissions.

    Returns:
        List of all permission strings
    """
    all_perms = []
    for category_perms in PERMISSION_CATEGORIES.values():
        all_perms.extend(category_perms)
    return all_perms


def get_permissions_for_category(category: str) -> List[str]:
    """
    Get all permissions for a specific category.

    Args:
        category: The category name (e.g., 'courses', 'grading')

    Returns:
        List of permission strings for that category
    """
    return PERMISSION_CATEGORIES.get(category, [])


# Delegasiya prefiksi: `grant:<permission>` — rol bu icazəni başqa (aşağı) rola
# verə bilər, amma prefiks özü icazəni aktiv etmir. Yuxarı səlahiyyət sahibi
# bununla aşağıya "bu icazəni sən də paylaya bilərsən" hüququ ötürür.
GRANT_PREFIX = "grant:"


def is_grant_entry(permission: str) -> bool:
    return permission.startswith(GRANT_PREFIX)


def strip_grant_prefix(permission: str) -> str:
    return permission[len(GRANT_PREFIX) :].strip() if is_grant_entry(permission) else permission


def validate_permissions(permissions: List[str]) -> bool:
    """
    Validate that all permissions in a list are valid.
    `grant:<permission>` formalı delegasiya girişləri də qəbul olunur —
    suffix adi icazə kimi validasiya edilir.

    Args:
        permissions: List of permission strings to validate

    Returns:
        True if all permissions are valid, False otherwise
    """
    if not permissions:
        return True

    if "*" in permissions:
        return True

    # Delegasiya girişlərinin suffix-ini adi icazə kimi yoxla.
    permissions = [strip_grant_prefix(perm) for perm in permissions]

    all_valid_perms = set(get_all_permissions())

    for perm in permissions:
        if perm.endswith(".*"):
            prefix = perm[:-2]
            has_match = False
            for wildcard in _wildcard_variants(prefix):
                wildcard_prefix = wildcard[:-1]
                if any(valid_permission.startswith(wildcard_prefix) for valid_permission in all_valid_perms):
                    has_match = True
                    break
            if not has_match:
                return False
        elif not _permission_variants(perm).intersection(all_valid_perms):
            return False

    return True


def expand_wildcard_permissions(permissions: List[str]) -> Set[str]:
    """
    Expand wildcard permissions to their full permission set.

    Args:
        permissions: List of permission strings, may include wildcards

    Returns:
        Set of all expanded permission strings
    """
    if "*" in permissions:
        return set(get_all_permissions())

    expanded = set()
    all_perms = get_all_permissions()

    for perm in permissions:
        if perm.endswith(".*"):
            prefix = perm[:-2]
            for wildcard in _wildcard_variants(prefix):
                wildcard_prefix = wildcard[:-1]
                for valid_permission in all_perms:
                    if valid_permission.startswith(wildcard_prefix):
                        expanded.add(valid_permission)
        else:
            matching_permissions = _permission_variants(perm).intersection(all_perms)
            if matching_permissions:
                expanded.update(matching_permissions)
            else:
                expanded.add(perm)

    return expanded
