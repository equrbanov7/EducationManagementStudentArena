/* ════════════════════════════════════════════════════════════════════════════
   EMSArena — Kurs forması (reusable enhancer)
   Cover dropzone önizləmə + sil, başlıq sayğacı.
   Idempotent: həm tam səhifədə (DOMContentLoaded), həm də AJAX modalında
   (modal JS `EMSCourseForm.init(scope)` çağırır) işləyir.
   ════════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
  "use strict";

  function initCover(form) {
    var dropzone = form.querySelector("[data-ems-cover]");
    if (!dropzone) return;

    var input = dropzone.querySelector('input[type="file"]');
    var preview = form.querySelector("[data-ems-preview]");
    var previewImg = preview && preview.querySelector("[data-ems-preview-img]");
    var removeBtn = preview && preview.querySelector("[data-ems-preview-remove]");
    if (!input || !preview || !previewImg) return;

    function showPreview(file) {
      var reader = new FileReader();
      reader.onload = function (e) {
        previewImg.src = e.target.result;
        preview.classList.add("show");
        dropzone.style.display = "none";
      };
      reader.readAsDataURL(file);
    }

    function clearPreview() {
      input.value = "";
      previewImg.src = "";
      preview.classList.remove("show");
      dropzone.style.display = "";
    }

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (file && /^image\//.test(file.type)) {
        showPreview(file);
      } else {
        clearPreview();
      }
    });

    if (removeBtn) {
      removeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        clearPreview();
      });
    }

    // drag-over vizual geri-bildiriş (fayl seçimi native <input> üzərindən)
    ["dragenter", "dragover"].forEach(function (ev) {
      dropzone.addEventListener(ev, function (e) {
        e.preventDefault();
        dropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      dropzone.addEventListener(ev, function () {
        dropzone.classList.remove("dragover");
      });
    });
  }

  function initCounter(form) {
    var counters = form.querySelectorAll("[data-ems-counter-for]");
    Array.prototype.forEach.call(counters, function (counter) {
      var fieldId = counter.getAttribute("data-ems-counter-for");
      var max = parseInt(counter.getAttribute("data-ems-counter-max"), 10) || 0;
      var field = form.querySelector("#" + (window.CSS && CSS.escape ? CSS.escape(fieldId) : fieldId));
      if (!field) return;

      function update() {
        var len = (field.value || "").length;
        counter.textContent = max ? len + "/" + max : String(len);
      }
      field.addEventListener("input", update);
      update();
    });
  }

  var EMSCourseForm = {
    /**
     * Verilmiş scope (document/element) daxilindəki bütün kurs formalarını
     * gücləndirir. Təkrar çağırışa qarşı qorunur (data flag).
     */
    init: function (scope) {
      scope = scope || document;
      var forms = scope.querySelectorAll
        ? scope.querySelectorAll("[data-ems-course-form]")
        : [];
      // scope özü forma ola bilər (modal body daxilində)
      if (scope.matches && scope.matches("[data-ems-course-form]")) {
        enhance(scope);
      }
      Array.prototype.forEach.call(forms, enhance);
    }
  };

  function enhance(form) {
    if (form.dataset.emsCourseFormReady === "1") return;
    form.dataset.emsCourseFormReady = "1";
    initCover(form);
    initCounter(form);
  }

  window.EMSCourseForm = EMSCourseForm;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      EMSCourseForm.init(document);
    });
  } else {
    EMSCourseForm.init(document);
  }
})(window, document);
