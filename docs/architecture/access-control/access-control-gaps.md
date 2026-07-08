# Access-Control Gaps

| Severity | Related file | Object | Description | Impact | Recommended correction | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| High | apps/exams/services/final_center/permissions.py | can_view_final_history | ProfileRole ORG_ADMIN/ORG_OWNER yoxlaması Membership source-of-truth-dan yan keçir. | Multi-org/stale profile role vəziyyətində view scoping-inə həddən artıq güvən yarana bilər. | Active org Membership.role və role permission-ları ilə yenidən bağlayın. | Partially confirmed |
| Medium | apps/accounts/models.py | UserProfile.role | Role cache ilə `organizations.Membership.role` arasında dual role surface var. | Yeni kod yanlış mənbəni oxuya bilər. | Authorization code review checklist-ə `Membership` məcburiyyətini əlavə edin. | Confirmed |
| Medium | apps/accounts/views/_helpers/rbac.py | allowed_sections | Sidebar visibility çox geniş capability məntiqi saxlayır; şərhlər view/consumer-də təkrar yoxlamanı tələb edir. | Frontend-only restriction yanlış təhlükəsizlik hissi yarada bilər. | Hər section üçün backend source linkini testlərlə saxlayın. | Confirmed |
| Medium | apps/organizations/permissions.py | PERMISSION_PREFIX_ALIASES | Legacy permission aliases hələ aktivdir. | Permission matrix və role data auditində qarışıqlıq yarana bilər. | Production role data audit-dən sonra alias cleanup planı yaradın. | Confirmed |
| Low | apps/accounts/views/roles/manage.py | manage_roles | Role assignment profile role setləri ilə Membership role-larını sync edir. | Sync yarıda qalsa profile cache və membership fərqlənə bilər; transaction var, amma observability məhduddur. | Audit/report əlavə etmək və drift detector management command yazmaq faydalıdır. | Inferred |
