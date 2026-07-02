/* Shared registration wizard state. Values are populated after REGISTER_I18N exists. */
window.EMSRegisterWizard = window.EMSRegisterWizard || {};

var i18n = {};
var registrationTypeMap = {};
var emptyRegistrationSelection = { mode: "", orgType: "" };
var orgRoleCombinedMap = {};

var countrySelect = null;
var registrationTypeSelect = null;
var step2a = null;
var step2b = null;
var step2bTitle = null;
var step3Title = null;
var orgTypeCards = null;
var roleCards = null;
var roleCardOwner = null;
var roleCardTeacher = null;
var roleCardStaff = null;
var roleCardStudent = null;
var step2bBackBtn = null;

var individualAccountInfo = null;
var orgCreateFields = null;
var studentJoinFields = null;

var organizationNameInput = null;
var organizationNameLabel = null;
var organizationNameHelp = null;

var orgIdentifierField = null;
var orgIdentifierInput = null;
var orgIdentifierLabel = null;
var orgIdentifierHelp = null;
var licenseIdentifierInput = null;
var licenseIdentifierLabel = null;
var licenseIdentifierHelp = null;

var organizationSearchInput = null;
var organizationSearchLabel = null;
var organizationSearchList = null;
var organizationSearchField = null;
var studentJoinHint = null;
var organizationSelect = null;
var organizationSearchDebounceTimer = null;

var joinChoiceInput = null;
var organizationSelectedChip = null;
var organizationSelectedChipLabel = null;
var organizationSelectedChipClear = null;
var organizationSearchError = null;
var step3ContinueBtn = null;
var registerSubmitBtn = null;

var initialRoleField = null;
var autoRoleInfoField = null;
var autoRoleInfoText = null;
var initialRoleSelect = null;
var registerForm = null;
var privacyCheckbox = null;
var privacyCard = null;
var privacyClientError = null;
var privacyServerError = null;
var privacyAcceptButton = null;
var privacyModalElement = null;
var languageSwitcherForms = [];
var languageSwitcherNextInputs = [];
var signupStepQueryKey = "signup_step";
var signupRestoreDraftQueryKey = "signup_restore";
var signupDraftStorageKey = "accounts.register.draft";
var signupSummary = null;
var signupSummaryCountry = null;
var signupSummaryAccountType = null;
var signupSummaryRole = null;
var signupSummaryOrganization = null;
var signupSummaryOrganizationItem = null;

var phoneField = null;
var studentSpecificFields = null;
var teacherSpecificFields = null;
var staffSpecificFields = null;
var departmentField = null;
var specializationInput = null;
var groupNumberInput = null;

var lookupData = {};
var organizations = [];
var enhancedSelects = [];
var step2bBaseTitle = "";
var individualSignupCard = null;
var _selectedOrgType = null;

function setupRegisterWizardState() {
    i18n = window.REGISTER_I18N || {};

    registrationTypeMap = {
        individual: { mode: "individual", orgType: "individual" },
        school: { mode: "organization_create", orgType: "school" },
        university: { mode: "organization_create", orgType: "university" },
        course_center: { mode: "organization_create", orgType: "course_center" },
        school_student: { mode: "student_join", orgType: "school" },
        university_student: { mode: "student_join", orgType: "university" },
        course_student: { mode: "student_join", orgType: "course_center" },
        school_teacher: { mode: "teacher_join", orgType: "school" },
        university_teacher: { mode: "teacher_join", orgType: "university" },
        course_teacher: { mode: "teacher_join", orgType: "course_center" },
        school_staff: { mode: "staff_join", orgType: "school" },
        university_staff: { mode: "staff_join", orgType: "university" },
        course_staff: { mode: "staff_join", orgType: "course_center" },
    };
    orgRoleCombinedMap = {
        individual: { owner: "individual" },
        school: { owner: "school", teacher: "school_teacher", staff: "school_staff", student: "school_student" },
        university: { owner: "university", teacher: "university_teacher", staff: "university_staff", student: "university_student" },
        course_center: { owner: "course_center", teacher: "course_teacher", staff: "course_staff", student: "course_student" },
    };

    countrySelect = document.getElementById("id_country");
    registrationTypeSelect = document.getElementById("id_organization_type");
    step2a = document.getElementById("step2a");
    step2b = document.getElementById("step2b");
    step2bTitle = document.getElementById("step2bTitle");
    step3Title = document.getElementById("step3Title");
    orgTypeCards = document.getElementById("orgTypeCards");
    roleCards = document.getElementById("roleCards");
    roleCardOwner = document.getElementById("roleCardOwner");
    roleCardTeacher = document.getElementById("roleCardTeacher");
    roleCardStaff = document.getElementById("roleCardStaff");
    roleCardStudent = document.getElementById("roleCardStudent");
    step2bBackBtn = document.getElementById("step2bBackBtn");

    individualAccountInfo = document.getElementById("individualAccountInfo");
    orgCreateFields = document.getElementById("orgCreateFields");
    studentJoinFields = document.getElementById("studentJoinFields");
    organizationNameInput = document.getElementById("id_institution_not_listed_name");
    organizationNameLabel = document.getElementById("organizationNameLabel");
    organizationNameHelp = document.getElementById("organizationNameHelp");
    orgIdentifierField = document.getElementById("orgIdentifierField");
    orgIdentifierInput = document.getElementById("id_organization_identifier");
    orgIdentifierLabel = document.getElementById("orgIdentifierLabel");
    orgIdentifierHelp = document.getElementById("orgIdentifierHelp");
    licenseIdentifierInput = document.getElementById("id_organization_license_identifier");
    licenseIdentifierLabel = document.getElementById("licenseIdentifierLabel");
    licenseIdentifierHelp = document.getElementById("licenseIdentifierHelp");

    organizationSearchInput = document.getElementById("organizationSearchInput");
    organizationSearchLabel = document.getElementById("organizationSearchLabel");
    organizationSearchList = document.getElementById("organizationSearchList");
    organizationSearchField = organizationSearchInput ? organizationSearchInput.closest(".register-form-field") : null;
    studentJoinHint = document.getElementById("studentJoinHint");
    organizationSelect = document.getElementById("id_join_organization");
    organizationSearchDebounceTimer = null;
    joinChoiceInput = document.getElementById("id_join_organization_choice");
    organizationSelectedChip = document.getElementById("organizationSelectedChip");
    organizationSelectedChipLabel = document.getElementById("organizationSelectedChipLabel");
    organizationSelectedChipClear = document.getElementById("organizationSelectedChipClear");
    organizationSearchError = document.getElementById("organizationSearchError");
    step3ContinueBtn = document.getElementById("step3ContinueBtn");
    registerSubmitBtn = document.getElementById("registerSubmitBtn");

    initialRoleField = document.getElementById("initialRoleField");
    autoRoleInfoField = document.getElementById("autoRoleInfoField");
    autoRoleInfoText = document.getElementById("autoRoleInfoText");
    initialRoleSelect = document.getElementById("id_initial_role");
    registerForm = document.getElementById("registerForm");
    privacyCheckbox = document.getElementById("id_accept_privacy_policy");
    privacyCard = document.getElementById("privacyConsentCard");
    privacyClientError = document.getElementById("privacyConsentClientError");
    privacyServerError = document.getElementById("privacyConsentServerError");
    privacyAcceptButton = document.querySelector("[data-accept-privacy-policy]");
    privacyModalElement = document.getElementById("privacyPolicyModal");
    languageSwitcherForms = document.querySelectorAll(".language-switcher__form");
    languageSwitcherNextInputs = document.querySelectorAll('.language-switcher__form input[name="next"]');
    signupSummary = document.getElementById("signupSelectionSummary");
    signupSummaryCountry = document.getElementById("signupSummaryCountry");
    signupSummaryAccountType = document.getElementById("signupSummaryAccountType");
    signupSummaryRole = document.getElementById("signupSummaryRole");
    signupSummaryOrganization = document.getElementById("signupSummaryOrganization");
    signupSummaryOrganizationItem = document.getElementById("signupSummaryOrganizationItem");

    phoneField = document.getElementById("phoneField");
    studentSpecificFields = document.getElementById("studentSpecificFields");
    teacherSpecificFields = document.getElementById("teacherSpecificFields");
    staffSpecificFields = document.getElementById("staffSpecificFields");
    departmentField = document.getElementById("departmentField");
    specializationInput = document.getElementById("id_specialization");
    groupNumberInput = document.getElementById("id_group_number");

    lookupData = window.SIGNUP_LOOKUP_DATA || {};
    organizations = lookupData.organizations || [];
    enhancedSelects = [];
    step2bBaseTitle = step2bTitle ? step2bTitle.textContent.trim() : tr("choose_role", "Choose your role");
    individualSignupCard = orgTypeCards
        ? orgTypeCards.querySelector('.register-persona-card[data-org-type="individual"]')
        : null;
    _selectedOrgType = null;
}

function tr(key, fallback) {
    if (!i18n[key] || i18n[key] === key) {
        return fallback;
    }
    return i18n[key];
}

function currentSelection() {
    var selected = registrationTypeSelect ? registrationTypeSelect.value : "";
    if (!individualSignupCard && selected === "individual") {
        return emptyRegistrationSelection;
    }
    if (!selected) return emptyRegistrationSelection;
    return registrationTypeMap[selected] || emptyRegistrationSelection;
}

function isJoinMode(mode) {
    return mode === "student_join" || mode === "teacher_join" || mode === "staff_join";
}

function shouldShowInstitutionStep() {
    return isJoinMode(currentSelection().mode);
}

function selectedOptionText(select) {
    if (!select || !select.options || select.selectedIndex < 0) return "";
    var selectedOption = select.options[select.selectedIndex];
    return selectedOption && selectedOption.value ? selectedOption.textContent.trim() : "";
}

function getRegistrationMeta(value) {
    var selectedValue = value !== undefined ? value : registrationTypeSelect ? registrationTypeSelect.value : "";
    if (!individualSignupCard && selectedValue === "individual") {
        selectedValue = "";
    }

    for (var orgType in orgRoleCombinedMap) {
        if (!Object.prototype.hasOwnProperty.call(orgRoleCombinedMap, orgType)) continue;
        var roles = orgRoleCombinedMap[orgType];
        for (var role in roles) {
            if (!Object.prototype.hasOwnProperty.call(roles, role)) continue;
            if (roles[role] === selectedValue) {
                return { value: selectedValue, orgType: orgType, role: role };
            }
        }
    }

    return {
        value: selectedValue,
        orgType: selectedValue ? "individual" : "",
        role: selectedValue === "individual" ? "owner" : "",
    };
}

function cardTitleText(container, selector) {
    if (!container) return "";
    var title = container.querySelector(selector + " .register-persona-card__title");
    return title ? title.textContent.trim() : "";
}
