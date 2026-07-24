/*
 * _member_form_modal.js
 * Source: apps/courses/templates/courses/partials/_member_form_modal.html
 * Add-students / add-groups modals: live search + counter + row-click
 * selection, AJAX submit (reload on success), and window.deleteMember.
 * Config (delete-member URL + i18n) is read from #memberFormModalConfig data-*;
 * CSRF from EMSCore. window.deleteMember is assigned at EMSReady time so this
 * partial's definition wins over course_dashboard.js's immediate assignment.
 */
(function () {
    "use strict";

    var bound = false;

    function init() {
        var cfg = document.getElementById("memberFormModalConfig");
        if (!cfg) { return; }
        var d = cfg.dataset;

        window.deleteMember = function (memberId, name) {
            if (!confirm(name + d.i18nDeleteMemberConfirmSuffix)) { return; }
            var url = d.deleteMemberUrl.replace("0", memberId);
            fetch(url, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": EMSCore.getCsrfToken()
                }
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert(d.i18nDeleteFailedPrefix + (data.error || d.i18nError));
                    }
                })
                .catch(function (error) {
                    console.error("Error:", error);
                    alert(d.i18nServerError);
                });
        };

        if (bound) { return; }
        bound = true;

        function initSelectorLogic(containerId, searchInputId, counterId) {
            var container = document.getElementById(containerId);
            var searchInput = document.getElementById(searchInputId);
            var counter = document.getElementById(counterId);
            if (!container) { return; }

            function updateCount() {
                var count = container.querySelectorAll('input[type="checkbox"]:checked').length;
                if (counter) { counter.innerText = count; }
            }

            if (searchInput) {
                searchInput.addEventListener("keyup", function (e) {
                    var term = e.target.value.toLowerCase();
                    var rows = container.querySelectorAll(".list-item-row");
                    rows.forEach(function (row) {
                        var searchData = row.getAttribute("data-search") || "";
                        row.style.display = searchData.includes(term) ? "flex" : "none";
                    });
                });
            }

            container.addEventListener("click", function (e) {
                var row = e.target.closest(".list-item-row");
                if (!row) { return; }
                if (e.target.closest('input[type="checkbox"]')) { return; }
                if (e.target.closest("label")) {
                    setTimeout(updateCount, 0);
                    return;
                }
                var checkbox = row.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.checked = !checkbox.checked;
                    updateCount();
                }
            });

            container.addEventListener("change", function (e) {
                if (e.target.type === "checkbox") { updateCount(); }
            });

            updateCount();
        }

        initSelectorLogic("student_list_container", "student_search_input", "student_counter");
        initSelectorLogic("group_list_container", "group_search_input", "group_counter");

        var studentForm = document.getElementById("addStudentForm");
        if (studentForm) {
            studentForm.addEventListener("submit", function (e) {
                e.preventDefault();
                var btn = this.querySelector('button[type="submit"]');
                var formData = new FormData(this);
                var userIds = formData.getAll("user_ids");
                if (userIds.length === 0) {
                    alert(d.i18nMinOneStudent);
                    return;
                }
                var originalText = btn.innerText;
                btn.innerText = d.i18nAdding;
                btn.disabled = true;
                fetch(this.action, {
                    method: "POST",
                    body: formData,
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                })
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        if (data.success) {
                            location.reload();
                        } else {
                            alert(d.i18nErrorPrefix + (data.error || d.i18nUnknownError));
                            btn.innerText = originalText;
                            btn.disabled = false;
                        }
                    })
                    .catch(function (error) {
                        console.error("Error:", error);
                        alert(d.i18nServerError);
                        btn.innerText = originalText;
                        btn.disabled = false;
                    });
            });
        }

        var groupForm = document.getElementById("addGroupForm");
        if (groupForm) {
            groupForm.addEventListener("submit", function (e) {
                e.preventDefault();
                var btn = this.querySelector('button[type="submit"]');
                var formData = new FormData(this);
                var groupIds = formData.getAll("group_ids");
                if (groupIds.length === 0) {
                    alert(d.i18nMinOneGroup);
                    return;
                }
                var originalText = btn.innerText;
                btn.innerText = d.i18nAdding;
                btn.disabled = true;
                fetch(this.action, {
                    method: "POST",
                    body: formData,
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                })
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        if (data.success) {
                            location.reload();
                        } else {
                            alert(d.i18nErrorPrefix + (data.error || d.i18nUnknownError));
                            btn.innerText = originalText;
                            btn.disabled = false;
                        }
                    })
                    .catch(function (error) {
                        console.error("Error:", error);
                        btn.innerText = originalText;
                        btn.disabled = false;
                    });
            });
        }
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();
