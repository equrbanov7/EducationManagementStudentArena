document.addEventListener("DOMContentLoaded", function () {
  // Modal elementləri
  const editModal = document.getElementById("editModal");
  const deleteModal = document.getElementById("deleteModal");
  const warningModal = document.getElementById("warningModal");

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

  // State idarəetməsi
  let currentPostId = null;
  let originalFormData = {};
  let hasUnsavedChanges = false;
  let pendingClose = false;

  // ============= EDIT FUNKSIONALLARI =============

  // Edit düyməsinə klik (yalnız post kartındakı düymələr)
  document.querySelectorAll(".js-edit-post").forEach((btn) => {
    btn.addEventListener("click", function () {
      currentPostId = this.dataset.postId;

      const title = this.dataset.title || "";
      const content = this.dataset.content || "";
      const category = this.dataset.category || "";
      const excerpt = this.dataset.excerpt || "";
      const imageUrl = this.dataset.imageUrl || "";
      const fileImage = this.dataset.fileImage || "";
      const isPublished = this.dataset.isPublished === "true";
      const slug = this.dataset.slug || "";
      const createdAt = this.dataset.createdAt || "";
      const updatedAt = this.dataset.updatedAt || "";

      // Form sahələrini doldur
      editTitle.value = title;
      editContent.value = content;
      editCategory.value = category;
      editExcerpt.value = excerpt;
      editImageUrl.value = imageUrl;
      editIsPublished.checked = isPublished;

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
        is_published: isPublished,
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
    if (!hasUnsavedChanges) return;

    const formData = new FormData(editForm);

    // Checkbox üçün: seçilməyibsə də backend-də düzgün getsin
    formData.set("is_published", editIsPublished.checked ? "on" : "");

    try {
      const response = await fetch(`/blog/post/${currentPostId}/edit/`, {
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
      if (data.success) {
        hasUnsavedChanges = false;
        hideModal(editModal);
        location.reload();
      } else {
        alert("Xəta baş verdi: " + (data.message || "Naməlum xəta"));
      }
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
      const title = this.dataset.title || "";

      deleteTitleSpan.textContent = title;
      showModal(deleteModal);
    });
  });

  // Silməni təsdiqlə
  confirmDeleteBtn.addEventListener("click", async function () {
    if (!currentPostId) return;

    try {
      const response = await fetch(`/blog/post/${currentPostId}/delete/`, {
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
      } else if (editModal && editModal.classList.contains("active")) {
        attemptCloseEditModal();
      } else if (deleteModal && deleteModal.classList.contains("active")) {
        hideModal(deleteModal);
      }
    }
  });
});
