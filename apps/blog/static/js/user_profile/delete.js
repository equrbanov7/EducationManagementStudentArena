(function (window, document) {
  "use strict";

  var ns = window.EMSUserProfile || (window.EMSUserProfile = {});

  function installOpenButtons(ctx) {
    document.querySelectorAll(".js-open-delete").forEach(function (btn) {
      btn.addEventListener("click", function () {
        ctx.currentPostId = this.dataset.postId;
        ctx.currentDeleteUrl = this.dataset.deleteUrl || "";
        var title = this.dataset.title || "";

        ctx.deleteTitleSpan.textContent = title;
        ns.modal.showModal(ctx.deleteModal);
      });
    });
  }

  function installConfirm(ctx) {
    if (ctx.confirmDeleteBtn) ctx.confirmDeleteBtn.addEventListener("click", async function () {
      if (!ctx.currentPostId) return;
      if (!ctx.currentDeleteUrl) return;

      try {
        var response = await fetch(ctx.currentDeleteUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": ns.modal.getCookie("csrftoken"),
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        var data = await response.json();

        if (data.success) {
          ns.modal.hideModal(ctx.deleteModal);
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
    if (ctx.cancelDeleteBtn) ctx.cancelDeleteBtn.addEventListener("click", function () {
      ns.modal.hideModal(ctx.deleteModal);
    });

    if (ctx.deleteModal) ctx.deleteModal.addEventListener("click", function (e) {
      if (e.target === ctx.deleteModal) {
        ns.modal.hideModal(ctx.deleteModal);
      }
    });
  }

  function install(ctx) {
    installOpenButtons(ctx);
    installConfirm(ctx);
    installCloseHandlers(ctx);
  }

  ns.deletePost = {
    install: install
  };
})(window, document);
