document.addEventListener("DOMContentLoaded", function () {
  const profilePageWrapper = document.querySelector(".profile-page-wrapper");
  const createPostUrl =
    profilePageWrapper?.dataset.createPostUrl || "/posts/create/";

  // Modal elementləri
  const editModal = document.getElementById("editModal");
  const deleteModal = document.getElementById("deleteModal");
  const warningModal = document.getElementById("warningModal");
  const createModal = document.getElementById("createModal");

  // Edit modal elementləri
  const editForm = document.getElementById("editForm");
  const editTitle = document.getElementById("editTitle");
  const editCategory = document.getElementById("editCategory");
  const editExcerpt = document.getElementById("editExcerpt");
  const editContent = document.getElementById("editContent");
  const editImageUrl = document.getElementById("editImageUrl");
  const editIsPublished = document.getElementById("editIsPublished");
  const editImage = document.getElementById("editImage");

  const saveEditBtn = document.getElementById("saveEdit");
  const cancelEditBtn = document.getElementById("cancelEdit");
  const closeEditModalBtn = document.getElementById("closeEditModal");

  // Meta info elementləri
  const editSlugInfo = document.getElementById("editSlugInfo");
  const editCreatedAtInfo = document.getElementById("editCreatedAtInfo");
  const editUpdatedAtInfo = document.getElementById("editUpdatedAtInfo");
  const editApprovalNotice = document.getElementById("editApprovalNotice");

  // Image preview elementləri
  const editImagePreview = document.getElementById("editImagePreview");
  const editImagePreviewWrapper = document.getElementById(
    "editImagePreviewWrapper"
  );
  const noImageText = document.getElementById("noImageText");

  // Delete modal elementləri
  const deleteTitleSpan = document.getElementById("deleteTitle");
  const confirmDeleteBtn = document.getElementById("confirmDelete");
  const cancelDeleteBtn = document.getElementById("cancelDelete");

  // Warning modal elementləri
  const stayOnModalBtn = document.getElementById("stayOnModal");
  const discardChangesBtn = document.getElementById("discardChanges");

  // Create modal elementləri
  const createForm = document.getElementById("createForm");
  const createTitle = document.getElementById("createTitle");
  const createCategory = document.getElementById("createCategory");
  const createNewCategory = document.getElementById("createNewCategory");
  const createExcerpt = document.getElementById("createExcerpt");
  const createContent = document.getElementById("createContent");
  const createImageUrl = document.getElementById("createImageUrl");
  const createImage = document.getElementById("createImage");
  const createIsPublished = document.getElementById("createIsPublished");
  const createFormError = document.getElementById("createFormError");
  const closeCreateModalBtn = document.getElementById("closeCreateModal");
  const cancelCreateBtn = document.getElementById("cancelCreate");
  const createFormRequiresApproval =
    createForm && createForm.dataset.requiresApproval === "true";

  // State idarəetməsi
  let currentPostId = null;
  let currentEditUrl = "";
  let currentDeleteUrl = "";
  let currentPostRequiresApproval = false;
  let originalFormData = {};
  let hasUnsavedChanges = false;
  let pendingClose = false;
  const allowedImageExtensions = new Set(["jpg", "jpeg", "jfif", "png", "gif", "webp"]);
  const maxImageSizeBytes = 25 * 1024 * 1024;

  function getFileExtension(fileName) {
    if (!fileName || typeof fileName !== "string") {
      return "";
    }
    const parts = fileName.split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
  }

  function getImageValidationError(file) {
    if (!file) {
      return "";
    }

    const extension = getFileExtension(file.name || "");
    if (!allowedImageExtensions.has(extension)) {
      return "Yalnız JPG, JPEG, JFIF, PNG, GIF və WEBP formatları dəstəklənir.";
    }

    if (file.size > maxImageSizeBytes) {
      return "Şəkil ölçüsü maksimum 25 MB ola bilər.";
    }

    return "";
  }

  // ============= CREATE FUNKSIONALLARI =============
  function showCreateError(message) {
    if (!createFormError) return;
    createFormError.hidden = false;
    createFormError.textContent = message || "Xəta baş verdi.";
  }

  function hideCreateError() {
    if (!createFormError) return;
    createFormError.hidden = true;
    createFormError.textContent = "";
  }

  function resetCreateForm() {
    if (!createForm) return;
    createForm.reset();
    if (createIsPublished) {
      if (createFormRequiresApproval) {
        createIsPublished.checked = false;
        createIsPublished.disabled = true;
      } else {
        createIsPublished.checked = true;
        createIsPublished.disabled = false;
      }
    }
    hideCreateError();
  }

  function openCreateModal() {
    resetCreateForm();
    showModal(createModal);
    if (createTitle) {
      createTitle.focus();
    }
  }

  if (createModal && createForm) {
    if (createModal.parentElement !== document.body) {
      document.body.appendChild(createModal);
    }

    document.querySelectorAll(".js-open-create-post").forEach((btn) => {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openCreateModal();
      });
    });

    createForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      hideCreateError();

      const selectedCreateImage =
        createImage && createImage.files && createImage.files.length
          ? createImage.files[0]
          : null;
      const createImageError = getImageValidationError(selectedCreateImage);
      if (createImageError) {
        showCreateError(createImageError);
        return;
      }

      const formData = new FormData(createForm);
      const publishValue =
        !createFormRequiresApproval &&
        createIsPublished &&
        createIsPublished.checked;
      formData.set("is_published", publishValue ? "on" : "");

      try {
        const response = await fetch(createPostUrl, {
          method: "POST",
          body: formData,
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
        });

        const data = await response.json();
        if (data.success) {
          hideModal(createModal);
          location.reload();
          return;
        }

        const errorText =
          (data.errors &&
            Object.values(data.errors)
              .flat()
              .join(" ")) ||
          data.message ||
          "Post yaradılmadı.";
        showCreateError(errorText);
      } catch (error) {
        console.error("Error:", error);
        showCreateError("Əlaqə xətası baş verdi.");
      }
    });

    if (cancelCreateBtn) {
      cancelCreateBtn.addEventListener("click", function () {
        hideModal(createModal);
      });
    }

    if (closeCreateModalBtn) {
      closeCreateModalBtn.addEventListener("click", function () {
        hideModal(createModal);
      });
    }

    createModal.addEventListener("click", function (e) {
      if (e.target === createModal) {
        hideModal(createModal);
      }
    });

    if (createImage) {
      createImage.addEventListener("change", function () {
        const selectedFile =
          createImage.files && createImage.files.length
            ? createImage.files[0]
            : null;
        const imageError = getImageValidationError(selectedFile);
        if (imageError) {
          createImage.value = "";
          showCreateError(imageError);
          return;
        }
        hideCreateError();
      });
    }

    window.openCreatePostModal = openCreateModal;
  }

  // ============= EDIT FUNKSIONALLARI =============

  // Edit düyməsinə klik (yalnız post kartındakı düymələr)
  document.querySelectorAll(".js-edit-post").forEach((btn) => {
    btn.addEventListener("click", function () {
      currentPostId = this.dataset.postId;
      currentEditUrl = this.dataset.editUrl || "";

      const title = this.dataset.title || "";
      const content = this.dataset.content || "";
      const category = this.dataset.category || "";
      const excerpt = this.dataset.excerpt || "";
      const imageUrl = this.dataset.imageUrl || "";
      const fileImage = this.dataset.fileImage || "";
      const isPublished = this.dataset.isPublished === "true";
      const requiresApproval = this.dataset.requiresApproval === "true";
      const slug = this.dataset.slug || "";
      const createdAt = this.dataset.createdAt || "";
      const updatedAt = this.dataset.updatedAt || "";
      currentPostRequiresApproval = requiresApproval;

      // Form sahələrini doldur
      editTitle.value = title;
      editContent.value = content;
      editCategory.value = category;
      editExcerpt.value = excerpt;
      editImageUrl.value = imageUrl;
      if (editIsPublished) {
        if (requiresApproval) {
          editIsPublished.checked = false;
          editIsPublished.disabled = true;
        } else {
          editIsPublished.checked = isPublished;
          editIsPublished.disabled = false;
        }
      }

      if (editApprovalNotice) {
        editApprovalNotice.hidden = !requiresApproval;
      }

      // Meta məlumatları doldur
      editSlugInfo.textContent = slug;
      editCreatedAtInfo.textContent = createdAt;
      editUpdatedAtInfo.textContent = updatedAt;

      if (editCategory) {
        const catValue = String(category);
        let found = false;

        Array.from(editCategory.options).forEach((opt) => {
          if (opt.value === catValue) {
            opt.selected = true;
            found = true;
          }
        });

        if (!found) {
          editCategory.selectedIndex = -1; // heç nə seçilməsin
        }
      }

      // Şəkil preview
      const previewSrc = fileImage || imageUrl;
      if (previewSrc) {
        editImagePreview.src = previewSrc;
        editImagePreview.style.display = "block";
        if (noImageText) noImageText.style.display = "none";
      } else {
        editImagePreview.src = "";
        editImagePreview.style.display = "none";
        if (noImageText) noImageText.style.display = "block";
      }

      // File input-u reset et
      if (editImage) {
        editImage.value = "";
      }

      // Orijinal datanı saxla (file image-i ayrıca izləməyə ehtiyac yoxdur)
      originalFormData = {
        title: title,
        content: content,
        category: category,
        excerpt: excerpt,
        image_url: imageUrl,
        is_published: requiresApproval ? false : isPublished,
      };

      hasUnsavedChanges = false;
      saveEditBtn.disabled = true;
      saveEditBtn.classList.remove("active");

      showModal(editModal);
    });
  });

  // Form dəyişikliklərini izlə
  const formInputs = [
    editTitle,
    editCategory,
    editExcerpt,
    editContent,
    editImageUrl,
    editIsPublished,
  ];
  formInputs.forEach((input) => {
    const eventName = input.type === "checkbox" ? "change" : "input";
    input.addEventListener(eventName, checkForChanges);
  });

  // Yeni şəkil seçiləndə də dəyişiklik say
  if (editImage) {
    editImage.addEventListener("change", function () {
      const selectedFile =
        editImage.files && editImage.files.length ? editImage.files[0] : null;
      const imageError = getImageValidationError(selectedFile);
      if (imageError) {
        editImage.value = "";
        alert(imageError);
        return;
      }
      hasUnsavedChanges = true;
      updateSaveButtonState();
    });
  }

  function checkForChanges() {
    const currentData = {
      title: editTitle.value.trim(),
      content: editContent.value.trim(),
      category: editCategory.value,
      excerpt: editExcerpt.value.trim(),
      image_url: editImageUrl.value.trim(),
      is_published: editIsPublished.checked,
    };

    hasUnsavedChanges =
      currentData.title !== originalFormData.title ||
      currentData.content !== originalFormData.content ||
      currentData.category !== originalFormData.category ||
      currentData.excerpt !== originalFormData.excerpt ||
      currentData.image_url !== originalFormData.image_url ||
      currentData.is_published !== originalFormData.is_published ||
      (editImage && editImage.files && editImage.files.length > 0);

    updateSaveButtonState();
  }

  function updateSaveButtonState() {
    if (hasUnsavedChanges) {
      saveEditBtn.disabled = false;
      saveEditBtn.classList.add("active");
    } else {
      saveEditBtn.disabled = true;
      saveEditBtn.classList.remove("active");
    }
  }

  // Formu submit et
  editForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    if (!currentPostId) return;
    if (!currentEditUrl) return;
    if (!hasUnsavedChanges) return;

    const formData = new FormData(editForm);

    // Checkbox üçün: seçilməyibsə də backend-də düzgün getsin
    formData.set(
      "is_published",
      !currentPostRequiresApproval && editIsPublished.checked ? "on" : ""
    );

    try {
      const response = await fetch(currentEditUrl, {
        method: "POST",
        body: formData,
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      const data = await response.json();

      if (data.success) {
        hasUnsavedChanges = false;
        hideModal(editModal);
        location.reload();
      } else {
        alert("Xəta baş verdi: " + (data.message || "Naməlum xəta"));
      }
    } catch (error) {
      console.error("Error:", error);
      alert("Əlaqə xətası baş verdi");
    }
  });

  // Edit modalı bağlama cəhdləri
  function attemptCloseEditModal() {
    if (hasUnsavedChanges) {
      pendingClose = true;
      showModal(warningModal);
    } else {
      hideModal(editModal);
    }
  }

  cancelEditBtn.addEventListener("click", attemptCloseEditModal);
  closeEditModalBtn.addEventListener("click", attemptCloseEditModal);

  // Overlay-ə klik edəndə
  editModal.addEventListener("click", function (e) {
    if (e.target === editModal) {
      attemptCloseEditModal();
    }
  });

  // Warning modal davranışları
  stayOnModalBtn.addEventListener("click", function () {
    hideModal(warningModal);
    pendingClose = false;
  });

  discardChangesBtn.addEventListener("click", function () {
    hasUnsavedChanges = false;
    hideModal(warningModal);
    hideModal(editModal);
    pendingClose = false;
  });

  // ============= DELETE FUNKSIONALLARI =============

  // Delete düyməsinə klik (yalnız post kartındakı delete düymələri)
  document.querySelectorAll(".js-open-delete").forEach((btn) => {
    btn.addEventListener("click", function () {
      currentPostId = this.dataset.postId;
      currentDeleteUrl = this.dataset.deleteUrl || "";
      const title = this.dataset.title || "";

      deleteTitleSpan.textContent = title;
      showModal(deleteModal);
    });
  });

  // Silməni təsdiqlə
  confirmDeleteBtn.addEventListener("click", async function () {
    if (!currentPostId) return;
    if (!currentDeleteUrl) return;

    try {
      const response = await fetch(currentDeleteUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCookie("csrftoken"),
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      const data = await response.json();

      if (data.success) {
        hideModal(deleteModal);
        location.reload();
      } else {
        alert("Xəta baş verdi: " + (data.message || "Naməlum xəta"));
      }
    } catch (error) {
      console.error("Error:", error);
      alert("Əlaqə xətası baş verdi");
    }
  });

  // Delete modalı bağla
  cancelDeleteBtn.addEventListener("click", function () {
    hideModal(deleteModal);
  });

  deleteModal.addEventListener("click", function (e) {
    if (e.target === deleteModal) {
      hideModal(deleteModal);
    }
  });

  // ============= HELPER FUNKSIYALAR =============

  function showModal(modal) {
    if (!modal) return;
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }

  function hideModal(modal) {
    if (!modal) return;
    modal.classList.remove("active");
    document.body.style.overflow = "";
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // ESC düyməsi ilə modalları bağla
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (warningModal && warningModal.classList.contains("active")) {
        hideModal(warningModal);
      } else if (createModal && createModal.classList.contains("active")) {
        hideModal(createModal);
      } else if (editModal && editModal.classList.contains("active")) {
        attemptCloseEditModal();
      } else if (deleteModal && deleteModal.classList.contains("active")) {
        hideModal(deleteModal);
      }
    }
  });
});
