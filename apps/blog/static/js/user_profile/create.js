(function (window, document) {
  "use strict";

  var ns = window.EMSUserProfile || (window.EMSUserProfile = {});

  function showCreateError(ctx, message) {
    if (!ctx.createFormError) return;
    ctx.createFormError.hidden = false;
    ctx.createFormError.textContent = message || gettext("Xəta baş verdi.");
  }

  function hideCreateError(ctx) {
    if (!ctx.createFormError) return;
    ctx.createFormError.hidden = true;
    ctx.createFormError.textContent = "";
  }

  function resetCreateForm(ctx) {
    if (!ctx.createForm) return;
    ctx.createForm.reset();
    if (ctx.createCategoryPicker) {
      ctx.createCategoryPicker.reset();
    }
    if (ctx.createIsPublished) {
      if (ctx.createFormRequiresApproval) {
        ctx.createIsPublished.checked = false;
        ctx.createIsPublished.disabled = true;
      } else {
        ctx.createIsPublished.checked = true;
        ctx.createIsPublished.disabled = false;
      }
    }
    hideCreateError(ctx);
  }

  function openCreateModal(ctx) {
    resetCreateForm(ctx);
    if (ctx.createModal) {
      ns.modal.showModal(ctx.createModal);
    }
    if (ctx.createTitle) {
      ctx.createTitle.focus();
    }
  }

  function installSubmit(ctx) {
    ctx.createForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      hideCreateError(ctx);

      var selectedCreateImage =
        ctx.createImage && ctx.createImage.files && ctx.createImage.files.length
          ? ctx.createImage.files[0]
          : null;
      var createImageError = ns.context.getImageValidationError(selectedCreateImage);
      if (createImageError) {
        showCreateError(ctx, createImageError);
        return;
      }

      var formData = new FormData(ctx.createForm);
      var publishValue =
        !ctx.createFormRequiresApproval &&
        ctx.createIsPublished &&
        ctx.createIsPublished.checked;
      formData.set("is_published", publishValue ? "on" : "");

      try {
        var response = await fetch(ctx.createPostUrl, {
          method: "POST",
          body: formData,
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        var data = await response.json();
        if (data.success) {
          if (ctx.createModal) {
            ns.modal.hideModal(ctx.createModal);
          }
          location.reload();
          return;
        }

        var errorText =
          (data.errors &&
            Object.values(data.errors)
              .flat()
              .join(" ")) ||
          data.message ||
          gettext("Post yaradılmadı.");
        showCreateError(ctx, errorText);
      } catch (error) {
        console.error("Error:", error);
        showCreateError(ctx, gettext("Əlaqə xətası baş verdi."));
      }
    });
  }

  function install(ctx) {
    if (!ctx.createForm) {
      window.openCreatePostModal = function () { openCreateModal(ctx); };
      return;
    }

    document.querySelectorAll(".js-open-create-post").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openCreateModal(ctx);
      });
    });

    installSubmit(ctx);

    if (ctx.cancelCreateBtn) {
      ctx.cancelCreateBtn.addEventListener("click", function () {
        ns.modal.hideModal(ctx.createModal);
      });
    }

    if (ctx.closeCreateModalBtn) {
      ctx.closeCreateModalBtn.addEventListener("click", function () {
        ns.modal.hideModal(ctx.createModal);
      });
    }

    if (ctx.createModal) {
      ctx.createModal.addEventListener("click", function (e) {
        if (e.target === ctx.createModal) {
          ns.modal.hideModal(ctx.createModal);
        }
      });
    }

    if (ctx.createImage) {
      ctx.createImage.addEventListener("change", function () {
        var selectedFile =
          ctx.createImage.files && ctx.createImage.files.length
            ? ctx.createImage.files[0]
            : null;
        var imageError = ns.context.getImageValidationError(selectedFile);
        if (imageError) {
          ctx.createImage.value = "";
          showCreateError(ctx, imageError);
          return;
        }
        hideCreateError(ctx);
      });
    }

    window.openCreatePostModal = function () { openCreateModal(ctx); };
  }

  ns.create = {
    install: install,
    openCreateModal: openCreateModal
  };
})(window, document);
