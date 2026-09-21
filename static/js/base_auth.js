/* base_auth.js — auth səhifələri (login, register, şifrə sıfırlama, OTP).
 * Mənbə: templates/base_auth.html (inline nonce script, 2026-09-21-də xarici fayla
 * çıxarıldı — CSP `script-src` yalnız SELF + NONCE).
 *
 * bfcache düzəlişi: brauzer səhifəni back/forward keşindən bərpa edəndə forma
 * KÖHNƏ csrfmiddlewaretoken-i saxlayır, yeni CSRF cookie isə artıq qoyulmuş ola
 * bilər → POST 403 verir. `pageshow(persisted)`-də səhifə yenidən yüklənir və
 * forma təzə token ilə render olunur. <head>-də, defer-siz, əvvəlki mövqedə.
 */
window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
        window.location.reload();
    }
});
