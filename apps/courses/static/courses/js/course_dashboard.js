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
    if (!confirm(d("i18nCourseDelete"))) return;

    var form = document.createElement("form");
    form.method = "POST";
    form.action = "/courses/" + courseId + "/delete/";

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
  }

  if (window.EMSDelegate) {
    EMSDelegate.on("click", "[data-delete-course-id]", function (event, btn) {
      event.preventDefault();
      deleteCourse(btn.dataset.deleteCourseId);
    });
  }

  window.deleteMember = function (memberId, userName) {
    if (!confirm(userName + d("i18nMemberDeleteSuffix"))) return;
    fetch(d("deleteMemberUrlTpl").replace("0", memberId), {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { return data.success ? location.reload() : alert(data.error); })
      .catch(function () { alert(d("i18nGenericError")); });
  };
})();
