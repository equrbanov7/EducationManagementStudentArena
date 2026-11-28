(function () {
    "use strict";
    const token = window.location.hash.slice(1);
    if (!token || token.length > 1024) return;
    document.querySelector('input[name="token"]').value = token;
    document.querySelector('button[type="submit"]').disabled = false;
    history.replaceState(null, "", window.location.pathname);
})();
