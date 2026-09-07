/* Qrup YARATMA təsdiqi — «Yarat» basılanda əvvəlcə xülasə modalı açılır:
 * qrupun adı, seçilmiş tələbələr (ixtisas şifri + qeydiyyat qrupu ilə) və
 * ümumi say; yalnız «Təsdiqlə və yarat» forma göndərir (sahib, 2026-09-07).
 * Redaktə rejimində (mövcud qrup) xülasə açılmır — dəyişiklik birbaşa gedir.
 *
 * Xülasə yaratma modalının İÇİNDƏ örtük paneldir — ikinci Bootstrap modalı
 * yoxdur (stack backdrop-u qarışdırır, 7 600 sətirli siyahını gizlət/göstər
 * 5 s çəkirdi). «Geri» paneli bağlayır, forma vəziyyəti olduğu kimi qalır. */
(function (ns, document, window) {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function selectedStudents(select) {
    return Array.from(select ? select.selectedOptions : []).map(function (option) {
      return {
        label: option.textContent || "",
        specialty: option.getAttribute("data-specialty") || "",
        specialtyCode: option.getAttribute("data-specialty-code") || "",
        group: option.getAttribute("data-academic-group") || option.getAttribute("data-student-group-number") || ""
      };
    });
  }

  function summaryBySpecialty(students) {
    var counts = {};
    students.forEach(function (s) {
      var key = s.specialty || "—";
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.keys(counts).sort().map(function (key) {
      return { label: key, count: counts[key] };
    });
  }

  function bind(ctx) {
    var panel = ctx.modalElement.querySelector("[data-confirm-panel]");
    if (!panel || !ctx.form) {
      return;
    }
    var nameEl = panel.querySelector("[data-confirm-name]");
    var countEl = panel.querySelector("[data-confirm-count]");
    var listEl = panel.querySelector("[data-confirm-list]");
    var specEl = panel.querySelector("[data-confirm-specialties]");
    var emptyEl = panel.querySelector("[data-confirm-empty]");
    var okBtn = panel.querySelector("[data-confirm-submit]");
    var confirmed = false;

    function isCreateMode() {
      return (ctx.form.getAttribute("action") || "") === ctx.createUrl;
    }

    function render() {
      var students = selectedStudents(ctx.studentsSelect);
      if (nameEl) nameEl.textContent = ctx.nameInput ? ctx.nameInput.value : "";
      if (countEl) countEl.textContent = String(students.length);
      if (emptyEl) emptyEl.hidden = students.length > 0;
      if (specEl) {
        specEl.innerHTML = summaryBySpecialty(students).map(function (item) {
          return '<span class="group-confirm__chip">' + esc(item.label) + ' <b>' + item.count + "</b></span>";
        }).join("");
        specEl.hidden = !students.length;
      }
      if (listEl) {
        listEl.innerHTML = students.map(function (s) {
          var meta = [];
          if (s.specialtyCode) meta.push(s.specialtyCode);
          if (s.specialty) meta.push(s.specialty);
          if (s.group) meta.push(s.group);
          return (
            '<li class="group-confirm__row"><span class="group-confirm__name">' + esc(s.label) + "</span>" +
            (meta.length ? '<span class="group-confirm__meta">' + esc(meta.join(" · ")) + "</span>" : "") +
            "</li>"
          );
        }).join("");
      }
    }

    function openPanel() {
      render();
      panel.hidden = false;
      var back = panel.querySelector("[data-confirm-back]");
      if (back) back.focus();
    }

    function closePanel() {
      panel.hidden = true;
    }

    ctx.form.addEventListener("submit", function (event) {
      if (confirmed || !isCreateMode()) {
        confirmed = false;
        return;
      }
      if (ctx.nameInput && !String(ctx.nameInput.value || "").trim()) {
        return; // brauzerin öz «required» xəbərdarlığı görünsün
      }
      event.preventDefault();
      openPanel();
    });

    Array.prototype.forEach.call(panel.querySelectorAll("[data-confirm-back]"), function (button) {
      button.addEventListener("click", closePanel);
    });
    ctx.modalElement.addEventListener("hidden.bs.modal", closePanel);
    // Escape panel açıq ikən YALNIZ paneli bağlayır. Bootstrap öz `keydown.dismiss`
    // dinləyicisini modal elementinə BİZDƏN ƏVVƏL qoşur (instance entry.js-də
    // yaranır), ona görə tutma (capture) fazasında sənəd səviyyəsində kəsirik.
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || panel.hidden || !panel.isConnected) {
        return;
      }
      if (!ctx.modalElement.contains(event.target) && event.target !== document.body) {
        return;
      }
      event.stopImmediatePropagation();
      event.preventDefault();
      closePanel();
    }, true);

    if (okBtn) {
      okBtn.addEventListener("click", function () {
        confirmed = true;
        closePanel();
        if (typeof ctx.form.requestSubmit === "function") {
          ctx.form.requestSubmit();
        } else {
          ctx.form.submit();
        }
      });
    }
  }

  ns.confirm = { bind: bind };
})(window.EMSProfileGroupModal = window.EMSProfileGroupModal || {}, document, window);
