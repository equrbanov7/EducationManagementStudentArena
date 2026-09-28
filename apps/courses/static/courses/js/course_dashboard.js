/* courses/js/course_dashboard.js
 * Source: courses/course_dashboard.html (extracted inline <script>)
 * Reads i18n / URLs from #courseDashboardRoot data-* attributes (no template
 * tags in this file). window.deleteMember stays a plain (immediately assigned)
 * global so the modal partial's EMSReady-time override still wins, as before.
 */
(function () {
  "use strict";

  function root() {
    return document.getElementById("courseDashboardRoot");
  }
  function d(name, fallback) {
    var el = root();
    return el && el.dataset[name] != null ? el.dataset[name] : (fallback || "");
  }
  function csrf() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function deleteCourse(courseId) {
    // 2026-09-14 (audit FE-F19): native confirm() → EMSConfirm (vahid dialoq); ləğv = sorğu yoxdur.
    window.EMSConfirm.open({
      title: d("i18nCourseDeleteTitle"),
      body: d("i18nCourseDelete"),
      confirmLabel: d("i18nDelete"),
      danger: true
    }).then(function (ok) {
      if (!ok) return;

      var form = document.createElement("form");
      form.method = "POST";
      form.action = d("deleteCourseUrl") || "/courses/" + courseId + "/delete/";

      var csrfInput = document.createElement("input");
      csrfInput.type = "hidden";
      csrfInput.name = "csrfmiddlewaretoken";
      csrfInput.value = csrf();
      form.appendChild(csrfInput);

      var profileReturnUrl = d("profileReturnUrl");
      if (profileReturnUrl) {
        var returnToInput = document.createElement("input");
        returnToInput.type = "hidden";
        returnToInput.name = "return_to";
        returnToInput.value = profileReturnUrl;
        form.appendChild(returnToInput);
      }

      document.body.appendChild(form);
      form.submit();
    });
  }

  if (window.EMSDelegate) {
    EMSDelegate.on("click", "[data-delete-course-id]", function (event, btn) {
      event.preventDefault();
      deleteCourse(btn.dataset.deleteCourseId);
    });
  }

  /* ── Kursu redaktə et (modal, 2026-09-28) ────────────────────────────────
     Ayrıca redaktə səhifəsi silindi: forma multipart AJAX ilə göndərilir; 400-də
     server gövdəni (xətalarla) yenidən render edib qaytarır. */
  if (window.EMSDelegate) {
    EMSDelegate.on("submit", "#editCourseForm", function (event, form) {
      event.preventDefault();
      var btn = form.querySelector('button[type="submit"]');
      var label = btn ? btn.innerHTML : "";
      if (btn) {
        btn.disabled = true;
        btn.textContent = btn.getAttribute("data-saving-text") || label;
      }
      window.EMSCore.fetchJSON(form.action, { method: "POST", body: new FormData(form) })
        .then(function (res) {
          var target = (res && res.redirect) || window.location.pathname;
          // eyni səhifədirsə yenilə — aktiv tab (#sec-…) itməsin
          if (target.split("?")[0] === window.location.pathname) { window.location.reload(); }
          else { window.location.href = target; }
        })
        .catch(function (err) {
          if (btn) { btn.disabled = false; btn.innerHTML = label; }
          var body = form.querySelector("[data-edit-course-body]");
          if (err && err.payload && err.payload.html && body) {
            body.innerHTML = err.payload.html;
            delete form.dataset.emsCourseFormReady;
            if (window.EMSCourseForm) { window.EMSCourseForm.init(form); }
            var bad = body.querySelector(".has-error input, .has-error textarea");
            if (bad) { bad.focus(); }
            return;
          }
          var msg = (err && err.payload && err.payload.error) || d("i18nGenericError");
          if (window.EMSToast && window.EMSToast.show) { window.EMSToast.show(msg, "error"); } else if (window.console) { window.console.error(msg); }
        });
    });
  }

  function openEditFromUrl() {
    if (d("openEdit") !== "1" || !window.bootstrap) return;
    var el = document.getElementById("editCourseModal");
    if (el) { window.bootstrap.Modal.getOrCreateInstance(el).show(); }
    try {
      var url = new URL(window.location.href);
      url.searchParams.delete("edit");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    } catch (e) { /* noop */ }
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", openEditFromUrl); }
  else { openEditFromUrl(); }

  window.deleteMember = function (memberId, userName) {
    window.EMSConfirm.open({ body: userName + d("i18nMemberDeleteSuffix"), danger: true }).then(function (ok) {
      if (!ok) return;
      // Audit 2026-09-28 FQ-FE-4: alert() → EMSToast; EMSCore.fetchJSON 403/500 və
      // qeyri-JSON cavabı `catch`-ə salır (əvvəl JSON parse xətası kimi itirdi).
      var toastError = function (msg) {
        if (!msg) { return; }
        if (window.EMSToast && window.EMSToast.show) { window.EMSToast.show(msg, "error"); } else if (window.console) { window.console.error(msg); }
      };
      window.EMSCore.fetchJSON(d("deleteMemberUrlTpl").replace("0", memberId), { method: "POST" })
        .then(function (data) {
          if (data && data.success) { location.reload(); return; }
          toastError((data && data.error) || d("i18nGenericError"));
        })
        .catch(function (err) {
          var payload = err && err.payload;
          if (payload && typeof payload === "object" && payload.view_as_blocked) { return; }
          toastError((payload && typeof payload === "object" && payload.error) || d("i18nGenericError"));
        });
    });
  };
})();
