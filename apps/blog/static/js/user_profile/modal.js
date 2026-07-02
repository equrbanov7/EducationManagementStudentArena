(function (window, document) {
  "use strict";

  var ns = window.EMSUserProfile || (window.EMSUserProfile = {});

  function moveModalRoots(ctx) {
    [ctx.editModal, ctx.warningModal].forEach(function (modal) {
      if (!modal || !modal.id) {
        return;
      }
      document.querySelectorAll("#" + modal.id).forEach(function (dup) {
        if (dup !== modal && dup.parentElement === document.body) {
          dup.remove();
        }
      });
      if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
      }
    });
  }

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
    var cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      var cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function installEscHandler(ctx) {
    if (window.__emsPostEscHandler) {
      document.removeEventListener("keydown", window.__emsPostEscHandler);
    }
    window.__emsPostEscHandler = function (e) {
      if (e.key !== "Escape") {
        return;
      }
      if (ctx.warningModal && ctx.warningModal.classList.contains("active")) {
        hideModal(ctx.warningModal);
      } else if (ctx.createModal && ctx.createModal.classList.contains("active")) {
        hideModal(ctx.createModal);
      } else if (ctx.editModal && ctx.editModal.classList.contains("active")) {
        ns.edit.attemptCloseEditModal(ctx);
      } else if (ctx.deleteModal && ctx.deleteModal.classList.contains("active")) {
        hideModal(ctx.deleteModal);
      }
    };
    document.addEventListener("keydown", window.__emsPostEscHandler);
  }

  ns.modal = {
    getCookie: getCookie,
    hideModal: hideModal,
    installEscHandler: installEscHandler,
    moveModalRoots: moveModalRoots,
    showModal: showModal
  };
})(window, document);
