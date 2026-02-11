document.addEventListener("DOMContentLoaded", () => {
    // 1) Double execution prevention
    if (window.ASSIGNMENT_JS_LOADED) return;
    window.ASSIGNMENT_JS_LOADED = true;
  
    const qs = (sel, root = document) => root.querySelector(sel);
    const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  
    function getCsrfToken() {
      const input = qs('input[name="csrfmiddlewaretoken"]');
      if (input) return input.value;
  
      let cookieValue = null;
      if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
          const cookie = cookies[i].trim();
          if (cookie.startsWith("csrftoken=")) {
            cookieValue = decodeURIComponent(cookie.substring("csrftoken=".length));
            break;
          }
        }
      }
      return cookieValue;
    }
  
    function closeModal(modalId) {
      const el = document.getElementById(modalId);
      if (!el) return;
      const inst = bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
      inst.hide();
    }
  
    // ========== ADD MODAL selection + search ==========
    function initAddSelectionLogic() {
      const modal = document.getElementById("addAssignmentModal");
      if (!modal) return;
  
      const groupCheckboxes = modal.querySelectorAll(".js-group-checkbox");
      const studentCheckboxes = modal.querySelectorAll(".js-student-checkbox");
  
      const container = modal.querySelector("#selected-items-container");
      const placeholder = modal.querySelector(".js-placeholder");
  
      const hiddenGroups = modal.querySelector('input[name="target_groups"]');
      const hiddenUsers = modal.querySelector('input[name="target_user_ids"]');
  
      // search inputs
      modal.querySelectorAll(".js-search-input").forEach((input) => {
        input.addEventListener("input", (e) => {
          const term = e.target.value.toLowerCase();
          const listContainer = e.target.closest(".tab-pane")?.querySelector(".js-source-list");
          if (!listContainer) return;
  
          listContainer.querySelectorAll("label").forEach((lbl) => {
            const text = (lbl.textContent || "").toLowerCase();
            lbl.style.display = text.includes(term) ? "" : "none";
          });
        });
      });
  
      function createBadge(text, color, onRemove) {
        const badge = document.createElement("div");
        badge.className = `badge bg-${color} text-dark border d-flex align-items-center me-1 mb-1 p-2`;
        badge.innerHTML = `
          <span>${text}</span>
          <i class="bi bi-x-circle-fill ms-2 text-danger" style="cursor:pointer"></i>
        `;
        badge.querySelector("i").addEventListener("click", onRemove);
        container.appendChild(badge);
      }
  
      function renderSelectedItems() {
        if (!container) return;
        container.innerHTML = "";
  
        let selectedGroups = [];
        let selectedUsers = [];
        let hasSelection = false;
  
        groupCheckboxes.forEach((cb) => {
          if (cb.checked) {
            hasSelection = true;
            selectedGroups.push(cb.value);
            createBadge(cb.dataset.name || cb.value, "warning", () => {
              cb.checked = false;
              renderSelectedItems();
            });
          }
        });
  
        studentCheckboxes.forEach((cb) => {
          if (cb.checked) {
            hasSelection = true;
            selectedUsers.push(cb.value);
            createBadge(cb.dataset.name || cb.value, "info", () => {
              cb.checked = false;
              renderSelectedItems();
            });
          }
        });
  
        if (!hasSelection && placeholder) {
          container.appendChild(placeholder);
        }
  
        if (hiddenGroups) hiddenGroups.value = selectedGroups.join(",");
        if (hiddenUsers) hiddenUsers.value = selectedUsers.join(",");
      }
  
      [...groupCheckboxes, ...studentCheckboxes].forEach((cb) => {
        cb.addEventListener("change", renderSelectedItems);
      });
  
      renderSelectedItems();
    }
  
    const addModalEl = document.getElementById("addAssignmentModal");
    if (addModalEl) {
      addModalEl.addEventListener("shown.bs.modal", initAddSelectionLogic);
    }
  
    // ========== DELETE (single click safe) ==========
    let deleteInProgress = false;
  
    document.body.addEventListener("click", async (e) => {
      const btn = e.target.closest(".js-delete-assignment");
      if (!btn) return;
  
      e.preventDefault();
      e.stopImmediatePropagation();
  
      if (deleteInProgress) return;
  
      if (!confirm("Bu sərbəst işi silmək istədiyinizə əminsiniz?")) return;
  
      deleteInProgress = true;
  
      const url = btn.dataset.url;
      const csrf = getCsrfToken();
  
      const originalHtml = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
      btn.disabled = true;
  
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
          },
        });
  
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || "Silinmə zamanı xəta baş verdi");
  
            // ... fetch uğurlu olduqdan sonra:
        const item = btn.closest(".list-group-item");
        if (item) item.remove();

        // badge sayı da azalsın istəyirsənsə:
        const badge = document.querySelector("#assignmentHeading .badge");
        if (badge) {
        const current = parseInt(badge.innerText || "0");
        badge.innerText = Math.max(current - 1, 0);
        }

      } catch (err) {
        alert("Xəta: " + err.message);
        btn.innerHTML = originalHtml;
        btn.disabled = false;
      } finally {
        deleteInProgress = false;
      }
    });
  
    // ========== EDIT LOAD ==========
    const editModalEl = qs("#editAssignmentModal");
    const editBody = qs("#editAssignmentModalContent");
  
    document.body.addEventListener("click", async (e) => {
      const btn = e.target.closest(".js-edit-assignment");
      if (!btn) return;
  
      e.preventDefault();
      const url = btn.dataset.url;
      if (!url) return;
  
      const inst = bootstrap.Modal.getInstance(editModalEl) || new bootstrap.Modal(editModalEl);
      inst.show();
  
      if (editBody) {
        editBody.innerHTML = `
          <div class="d-flex justify-content-center align-items-center p-5">
            <div class="spinner-border text-primary"></div>
          </div>
        `;
      }
  
      try {
        const res = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        const data = await res.json();
  
        if (!res.ok || !data.success) {
          editBody.innerHTML = `<div class="alert alert-danger">Xəta: ${data.error}</div>`;
          return;
        }
  
        editBody.innerHTML = data.html;
  
        // submit
        const form = editBody.querySelector("form");
        if (form) {
          form.action = url;
  
          form.addEventListener("submit", async (ev) => {
            ev.preventDefault();
  
            const csrf = getCsrfToken();
            const formData = new FormData(form);
  
            const resp = await fetch(form.action, {
              method: "POST",
              body: formData,
              headers: {
                "X-CSRFToken": csrf,
                "X-Requested-With": "XMLHttpRequest",
              },
            });
  
            const result = await resp.json();
            if (!resp.ok || !result.success) {
              alert("Xəta: " + (result.error || "Yadda saxlamaq olmadı"));
              return;
            }
  
            closeModal("editAssignmentModal");
            window.location.reload();
          });
        }
      } catch (err) {
        editBody.innerHTML = `<div class="alert alert-danger">Xəta: ${err.message}</div>`;
      }
    });
  
    // ========== ADD SUBMIT (AJAX) ==========
    const addForm = document.getElementById("addAssignmentForm");
    if (addForm) {
      addForm.addEventListener("submit", async (e) => {
        e.preventDefault();
  
        const formData = new FormData(addForm);
  
        try {
          const res = await fetch(addForm.action, {
            method: "POST",
            body: formData,
            headers: { "X-Requested-With": "XMLHttpRequest" },
          });
  
          const data = await res.json();
          if (!res.ok || !data.success) {
            alert("Xəta: " + JSON.stringify(data.errors || data.error));
            return;
          }
  
          window.location.reload();
        } catch (err) {
          alert("Sistem xətası");
        }
      });
    }
  });
  