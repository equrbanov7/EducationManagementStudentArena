(function () {
    "use strict";
    var form = document.querySelector(".ems-contact__form");
    if (!form) { return; }
    var button = form.querySelector("button[type=submit]");
    form.addEventListener("submit", function (event) {
        if (button.disabled) {
            event.preventDefault();
            return;
        }
        button.disabled = true;
    });
    window.addEventListener("pageshow", function () { button.disabled = false; });
})();
