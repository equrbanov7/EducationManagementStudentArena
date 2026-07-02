(function (window, document) {
  "use strict";

  var ns = window.EMSUserProfile || (window.EMSUserProfile = {});

  function setPostFields(ctx, btn) {
    var title = btn.dataset.title || "";
    var content = btn.dataset.content || "";
    var categoryRoot = btn.dataset.categoryRoot || "";
    var subcategory = btn.dataset.subcategory || "";
    var excerpt = btn.dataset.excerpt || "";
    var imageUrl = btn.dataset.imageUrl || "";
    var fileImage = btn.dataset.fileImage || "";
    var isPublished = btn.dataset.isPublished === "true";
    var requiresApproval = btn.dataset.requiresApproval === "true";
    var isModeratorEdit = btn.dataset.moderatorEdit === "true";
    var approvalStatus = btn.dataset.approvalStatus || "";
    var slug = btn.dataset.slug || "";
    var createdAt = btn.dataset.createdAt || "";
    var updatedAt = btn.dataset.updatedAt || "";
    ctx.currentPostRequiresApproval = requiresApproval && !isModeratorEdit;

    ctx.editTitle.value = title;
    ctx.editContent.value = content;
    ctx.editExcerpt.value = excerpt;
    ctx.editImageUrl.value = imageUrl;
    if (ctx.editIsPublished) {
      if (isModeratorEdit) {
        ctx.editIsPublished.checked = isPublished;
        ctx.editIsPublished.disabled = true;
      } else if (requiresApproval) {
        ctx.editIsPublished.checked = false;
        ctx.editIsPublished.disabled = true;
      } else {
        ctx.editIsPublished.checked = isPublished;
        ctx.editIsPublished.disabled = false;
      }
    }

    if (ctx.editApprovalNotice) {
      ctx.editApprovalNotice.textContent = "Bu post saxlananda yenidən müəllim təsdiqini gözləyəcək.";
      ctx.editApprovalNotice.hidden = !requiresApproval || isModeratorEdit;
    }

    ctx.editSlugInfo.textContent = slug;
    ctx.editCreatedAtInfo.textContent = createdAt;
    ctx.editUpdatedAtInfo.textContent = updatedAt;

    if (ctx.editCategoryPicker) {
      ctx.editCategoryPicker.setValues(categoryRoot, subcategory);
    } else if (ctx.editCategory) {
      ctx.editCategory.value = categoryRoot;
    }

    if (ctx.editSubcategory && !ctx.editCategoryPicker) {
      ctx.editSubcategory.value = subcategory;
    }

    var previewSrc = fileImage || imageUrl;
    if (previewSrc) {
      ctx.editImagePreview.src = previewSrc;
      ctx.editImagePreview.style.display = "block";
      if (ctx.noImageText) ctx.noImageText.style.display = "none";
    } else {
      ctx.editImagePreview.src = "";
      ctx.editImagePreview.style.display = "none";
      if (ctx.noImageText) ctx.noImageText.style.display = "block";
    }

    if (ctx.editImage) {
      ctx.editImage.value = "";
    }

    ctx.originalFormData = {
      title: title,
      content: content,
      category: categoryRoot,
      subcategory: subcategory,
      excerpt: excerpt,
      image_url: imageUrl,
      is_published: requiresApproval ? false : isPublished
    };

    ctx.hasUnsavedChanges = approvalStatus === "needs_changes";
    ctx.saveEditBtn.disabled = !ctx.hasUnsavedChanges;
    if (ctx.hasUnsavedChanges) {
      ctx.saveEditBtn.classList.add("active");
    } else {
      ctx.saveEditBtn.classList.remove("active");
    }
  }

  function checkForChanges(ctx) {
    var currentData = {
      title: ctx.editTitle.value.trim(),
      content: ctx.editContent.value.trim(),
      category: ctx.editCategory.value,
      subcategory: ctx.editSubcategory ? ctx.editSubcategory.value : "",
      excerpt: ctx.editExcerpt.value.trim(),
      image_url: ctx.editImageUrl.value.trim(),
      is_published: ctx.editIsPublished.checked
    };

    ctx.hasUnsavedChanges =
      currentData.title !== ctx.originalFormData.title ||
      currentData.content !== ctx.originalFormData.content ||
      currentData.category !== ctx.originalFormData.category ||
      currentData.subcategory !== ctx.originalFormData.subcategory ||
      currentData.excerpt !== ctx.originalFormData.excerpt ||
      currentData.image_url !== ctx.originalFormData.image_url ||
      currentData.is_published !== ctx.originalFormData.is_published ||
      (ctx.editImage && ctx.editImage.files && ctx.editImage.files.length > 0);

    updateSaveButtonState(ctx);
  }

  function updateSaveButtonState(ctx) {
    if (ctx.hasUnsavedChanges) {
      ctx.saveEditBtn.disabled = false;
      ctx.saveEditBtn.classList.add("active");
    } else {
      ctx.saveEditBtn.disabled = true;
      ctx.saveEditBtn.classList.remove("active");
    }
  }

  function attemptCloseEditModal(ctx) {
    if (ctx.hasUnsavedChanges) {
      ctx.pendingClose = true;
      ns.modal.showModal(ctx.warningModal);
    } else {
      ns.modal.hideModal(ctx.editModal);
    }
  }

  function installOpenButtons(ctx) {
    document.querySelectorAll(".js-edit-post").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!ctx.editModal || !ctx.editTitle || !ctx.editForm) {
          return;
        }
        ctx.currentPostId = this.dataset.postId;
        ctx.currentEditUrl = this.dataset.editUrl || "";
        setPostFields(ctx, this);
        ns.modal.showModal(ctx.editModal);
      });
    });
  }

  function installChangeTracking(ctx) {
    var formInputs = [
      ctx.editTitle,
      ctx.editCategory,
      ctx.editSubcategory,
      ctx.editExcerpt,
      ctx.editContent,
      ctx.editImageUrl,
      ctx.editIsPublished
    ].filter(Boolean);
    formInputs.forEach(function (input) {
      var eventName =
        input.type === "checkbox" || input.tagName === "SELECT" ? "change" : "input";
      input.addEventListener(eventName, function () { checkForChanges(ctx); });
    });

    if (ctx.editImage) {
      ctx.editImage.addEventListener("change", function () {
        var selectedFile =
          ctx.editImage.files && ctx.editImage.files.length ? ctx.editImage.files[0] : null;
        var imageError = ns.context.getImageValidationError(selectedFile);
        if (imageError) {
          ctx.editImage.value = "";
          alert(imageError);
          return;
        }
        ctx.hasUnsavedChanges = true;
        updateSaveButtonState(ctx);
      });
    }
  }

  function installSubmit(ctx) {
    if (!ctx.editForm) return;
    ctx.editForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      if (!ctx.currentPostId) return;
      if (!ctx.currentEditUrl) return;
      if (!ctx.hasUnsavedChanges) return;

      var formData = new FormData(ctx.editForm);
      formData.set(
        "is_published",
        !ctx.currentPostRequiresApproval && ctx.editIsPublished.checked ? "on" : ""
      );

      try {
        var response = await fetch(ctx.currentEditUrl, {
          method: "POST",
          body: formData,
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        var data = await response.json();

        if (data.success) {
          ctx.hasUnsavedChanges = false;
          ns.modal.hideModal(ctx.editModal);
          location.reload();
        } else {
          alert("Xəta baş verdi: " + (data.message || "Naməlum xəta"));
        }
      } catch (error) {
        console.error("Error:", error);
        alert("Əlaqə xətası baş verdi");
      }
    });
  }

  function installCloseHandlers(ctx) {
    if (ctx.cancelEditBtn) ctx.cancelEditBtn.addEventListener("click", function () { attemptCloseEditModal(ctx); });
    if (ctx.closeEditModalBtn) ctx.closeEditModalBtn.addEventListener("click", function () { attemptCloseEditModal(ctx); });
    if (ctx.editModal) ctx.editModal.addEventListener("click", function (e) {
      if (e.target === ctx.editModal) {
        attemptCloseEditModal(ctx);
      }
    });
    if (ctx.stayOnModalBtn) ctx.stayOnModalBtn.addEventListener("click", function () {
      ns.modal.hideModal(ctx.warningModal);
      ctx.pendingClose = false;
    });
    if (ctx.discardChangesBtn) ctx.discardChangesBtn.addEventListener("click", function () {
      ctx.hasUnsavedChanges = false;
      ns.modal.hideModal(ctx.warningModal);
      ns.modal.hideModal(ctx.editModal);
      ctx.pendingClose = false;
    });
  }

  function install(ctx) {
    installOpenButtons(ctx);
    installChangeTracking(ctx);
    installSubmit(ctx);
    installCloseHandlers(ctx);
  }

  ns.edit = {
    attemptCloseEditModal: attemptCloseEditModal,
    install: install
  };
})(window, document);
