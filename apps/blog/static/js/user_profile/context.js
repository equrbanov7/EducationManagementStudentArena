(function (window, document) {
  "use strict";

  var ns = window.EMSUserProfile || (window.EMSUserProfile = {});
  var allowedImageExtensions = new Set(["jpg", "jpeg", "jfif", "png", "gif", "webp"]);
  var maxImageSizeBytes = 25 * 1024 * 1024;

  function getFileExtension(fileName) {
    if (!fileName || typeof fileName !== "string") {
      return "";
    }
    var parts = fileName.split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
  }

  function getImageValidationError(file) {
    if (!file) {
      return "";
    }

    var extension = getFileExtension(file.name || "");
    if (!allowedImageExtensions.has(extension)) {
      return gettext("Yalnız JPG, JPEG, JFIF, PNG, GIF və WEBP formatları dəstəklənir.");
    }

    if (file.size > maxImageSizeBytes) {
      return gettext("Şəkil ölçüsü maksimum 25 MB ola bilər.");
    }

    return "";
  }

  function create() {
    var profilePageWrapper = document.querySelector(".profile-page-wrapper");
    var createFormContainer = document.querySelector("[data-create-post-form-container]");
    return {
      profilePageWrapper: profilePageWrapper,
      createPostUrl: (profilePageWrapper && profilePageWrapper.dataset.createPostUrl) || "/posts/create/",
      createFormContainer: createFormContainer,
      editModal: document.getElementById("editModal"),
      deleteModal: document.getElementById("deleteModal"),
      warningModal: document.getElementById("warningModal"),
      createModal: document.getElementById("createModal"),
      editForm: document.getElementById("editForm"),
      editTitle: document.getElementById("editTitle"),
      editCategory: document.getElementById("editCategory"),
      editSubcategory: document.getElementById("editSubcategory"),
      editExcerpt: document.getElementById("editExcerpt"),
      editContent: document.getElementById("editContent"),
      editImageUrl: document.getElementById("editImageUrl"),
      editIsPublished: document.getElementById("editIsPublished"),
      editImage: document.getElementById("editImage"),
      saveEditBtn: document.getElementById("saveEdit"),
      cancelEditBtn: document.getElementById("cancelEdit"),
      closeEditModalBtn: document.getElementById("closeEditModal"),
      editSlugInfo: document.getElementById("editSlugInfo"),
      editCreatedAtInfo: document.getElementById("editCreatedAtInfo"),
      editUpdatedAtInfo: document.getElementById("editUpdatedAtInfo"),
      editApprovalNotice: document.getElementById("editApprovalNotice"),
      editImagePreview: document.getElementById("editImagePreview"),
      editImagePreviewWrapper: document.getElementById("editImagePreviewWrapper"),
      noImageText: document.getElementById("noImageText"),
      deleteTitleSpan: document.getElementById("deleteTitle"),
      confirmDeleteBtn: document.getElementById("confirmDelete"),
      cancelDeleteBtn: document.getElementById("cancelDelete"),
      stayOnModalBtn: document.getElementById("stayOnModal"),
      discardChangesBtn: document.getElementById("discardChanges"),
      createForm: document.getElementById("createForm"),
      createTitle: document.getElementById("createTitle"),
      createCategory: document.getElementById("createCategory"),
      createSubcategory: document.getElementById("createSubcategory"),
      createExcerpt: document.getElementById("createExcerpt"),
      createContent: document.getElementById("createContent"),
      createImageUrl: document.getElementById("createImageUrl"),
      createImage: document.getElementById("createImage"),
      createIsPublished: document.getElementById("createIsPublished"),
      createFormError: document.getElementById("createFormError"),
      closeCreateModalBtn: document.getElementById("closeCreateModal"),
      cancelCreateBtn: document.getElementById("cancelCreate"),
      createFormRequiresApproval: false,
      currentPostId: null,
      currentEditUrl: "",
      currentDeleteUrl: "",
      currentPostRequiresApproval: false,
      originalFormData: {},
      hasUnsavedChanges: false,
      pendingClose: false,
      createCategoryPicker: null,
      editCategoryPicker: null
    };
  }

  function attachPickerWidgets(ctx) {
    ctx.createFormRequiresApproval = ctx.createForm && ctx.createForm.dataset.requiresApproval === "true";
    ctx.createCategoryPicker = window.createPostCategoryPicker
      ? window.createPostCategoryPicker(
          ctx.createFormContainer
            ? ctx.createFormContainer.querySelector(".js-post-category-picker")
            : null
        )
      : null;
    ctx.editCategoryPicker = window.createPostCategoryPicker
      ? window.createPostCategoryPicker(
          ctx.editModal ? ctx.editModal.querySelector(".js-post-category-picker") : null
        )
      : null;
  }

  ns.context = {
    attachPickerWidgets: attachPickerWidgets,
    create: create,
    getImageValidationError: getImageValidationError
  };
})(window, document);
