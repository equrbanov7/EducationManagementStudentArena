// Source: exams/exam_center/room_list.html — auto-submit the status filter form on change (CSP-safe, no inline onchange).

window.EMSReady(function () {
    document.querySelectorAll(".js-fxc-autosubmit").forEach(function (sel) {
        sel.addEventListener("change", function () {
            if (sel.form) { sel.form.submit(); }
        });
    });
});
