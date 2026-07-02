// AJAX-safe: EMSReady re-runs this init after profile section swaps.
(function (window) {
  "use strict";

  var ns = window.EMSUserProfile || (window.EMSUserProfile = {});

  ns.init = function () {
    var ctx = ns.context.create();
    ns.modal.moveModalRoots(ctx);
    ns.context.attachPickerWidgets(ctx);
    ns.create.install(ctx);
    ns.edit.install(ctx);
    ns.deletePost.install(ctx);
    ns.modal.installEscHandler(ctx);
  };

  (window.EMSReady || function (fn) { document.addEventListener("DOMContentLoaded", fn); })(ns.init);
})(window);
