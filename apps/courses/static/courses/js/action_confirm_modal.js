(function () {
  if (window._COURSE_ACTION_CONFIRM_MODAL_INIT) {
    return;
  }
  window._COURSE_ACTION_CONFIRM_MODAL_INIT = true;

  function init() {
    var modalElement = document.getElementById("courseActionConfirmModal");
    if (!modalElement || !window.bootstrap) {
      return;
    }

    var modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    var titleElement = document.getElementById("courseActionConfirmModalTitle");
    var messageElement = document.getElementById("courseActionConfirmModalMessage");
    var submitButton = document.getElementById("courseActionConfirmModalSubmit");
    if (!titleElement || !messageElement || !submitButton) {
      return;
    }

    var defaultTitle = modalElement.getAttribute("data-default-title") || "";
    var defaultConfirmLabel = modalElement.getAttribute("data-default-confirm-label") || submitButton.textContent.trim();
    var defaultConfirmClass = submitButton.className;
    var currentConfirmHandler = null;

    function resetState() {
      currentConfirmHandler = null;
      titleElement.textContent = defaultTitle;
      messageElement.textContent = "";
      submitButton.disabled = false;
      submitButton.textContent = defaultConfirmLabel;
      submitButton.className = defaultConfirmClass;
    }

    modalElement.addEventListener("hidden.bs.modal", resetState);

    submitButton.addEventListener("click", function () {
      if (typeof currentConfirmHandler !== "function") {
        modal.hide();
        return;
      }

      submitButton.disabled = true;
      var confirmResult;
      try {
        confirmResult = currentConfirmHandler();
      } catch (error) {
        submitButton.disabled = false;
        return;
      }

      Promise.resolve(confirmResult)
        .then(function (shouldClose) {
          if (shouldClose !== false) {
            modal.hide();
          } else {
            submitButton.disabled = false;
          }
        })
        .catch(function () {
          submitButton.disabled = false;
        });
    });

    window.openActionConfirmModal = function (options) {
      var config = options || {};
      currentConfirmHandler = typeof config.onConfirm === "function" ? config.onConfirm : null;

      titleElement.textContent = config.title || defaultTitle;
      messageElement.textContent = config.message || "";
      submitButton.textContent = config.confirmLabel || defaultConfirmLabel;
      submitButton.className = config.confirmButtonClass || defaultConfirmClass;
      submitButton.disabled = false;

      modal.show();
    };

    resetState();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
