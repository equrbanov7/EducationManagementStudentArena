/*
 * nginx texniki xidmət səhifəsi — avtomatik yenidən cəhd.
 *
 * ~15 s sonra eyni ünvan GET ilə yenidən açılır. `location.reload()` deyil: forma
 * göndərilərkən (POST) bu səhifə gəlibsə, reload brauzerdə «formanı yenidən
 * göndər» dialoqu açır və təkrar göndərmə riski yaradır. Kiçik təsadüfi gecikmə
 * deploy bitəndə minlərlə açıq tabın eyni saniyədə qayıtmasının qarşısını alır.
 */
(function () {
  "use strict";

  var BASE_SECONDS = 15;
  var JITTER_SECONDS = 5;
  var remaining = BASE_SECONDS + Math.floor(Math.random() * (JITTER_SECONDS + 1));

  function retry() {
    window.location.replace(window.location.href);
  }

  function render(status) {
    if (status) {
      status.textContent = remaining + " saniyədən sonra avtomatik yenidən yoxlanılacaq.";
    }
  }

  function start() {
    var status = document.getElementById("ems-maint-status");
    var button = document.getElementById("ems-maint-retry");

    if (button) {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        retry();
      });
    }

    render(status);
    var timer = window.setInterval(function () {
      remaining -= 1;
      if (remaining <= 0) {
        window.clearInterval(timer);
        retry();
        return;
      }
      render(status);
    }, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
