import { reducedMotion } from './utils.js?v=lx20260930';

/* Suallar arası «pərdə» keçidi — TƏK süpürmə (sahib 2026-09-30, «animasiya iki dəfə oynayır»).
 *
 * Səbəb: yeni sualın səhnəsi t=0-da DOM-a yazılırdı, pərdə isə yavaş başlayan easing ilə ekranı
 * yalnız ~0.45 s-də örtürdü → tamaşaçı sualı görür, pərdə onu soldan-sağa örtür, qızılı zolaq
 * (ayrıca panel) yenə soldan-sağa keçir, sonra pərdə sağa çəkilib sualı YENİDƏN açırdı — eyni
 * keçid 2–3 dəfə «süpürürdü». İndi pərdə dərhal ekranı örtür (qısa görünmə), «Sual N / M» yazısı
 * görünür və pərdə BİR dəfə soldan sağa çəkilərək yeni sualı açır; qızılı kənar pərdənin öz
 * arxa kənarıdır (ayrı hərəkət yoxdur). Açarla idempotentdir (eyni sual üçün bir dəfə);
 * taymer həmişə təmizlənir — ilişib qalan örtük olmur. */
const played = new Set();
let wipe = null;
let timer = 0;

function ensureWipe() {
    if (wipe && wipe.isConnected) return wipe;
    wipe = document.createElement("div");
    wipe.className = "hx-wipe";
    wipe.setAttribute("aria-hidden", "true");
    wipe.innerHTML = '<span class="hx-wipe__panel"></span><span class="hx-wipe__label"></span>';
    document.body.appendChild(wipe);
    return wipe;
}

export function playWipe(key, label) {
    if (!key || played.has(key)) return false;
    played.add(key);
    if (played.size > 120) played.delete(played.values().next().value);
    if (reducedMotion()) return false;
    const el = ensureWipe();
    el.querySelector(".hx-wipe__label").textContent = label || "";
    el.classList.remove("is-running");
    void el.offsetWidth; // animasiyanı yenidən başlat
    el.classList.add("is-running");
    window.clearTimeout(timer);
    timer = window.setTimeout(() => el.classList.remove("is-running"), 1150);
    return true;
}

export function cancelWipe() {
    window.clearTimeout(timer);
    if (wipe) wipe.classList.remove("is-running");
}
