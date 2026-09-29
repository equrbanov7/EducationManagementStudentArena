/* fx.js — final səhnəsinin kanva effektləri: sol+sağ konfetti TOPLARI (mərkəzə
 * doğru qövslə uçur, sonra yellənərək düşür) və qalibin üstündə fişəng partlayışı.
 * Bir kanva, bir RAF dövrəsi; hissəcik limiti 300; heç nə qalmayanda dövrə dayanır.
 * DPR ≤ 1.5 (proyektorda artıq piksel xərci yox). reduced-motion → statik kadr.
 */

const MAX_PARTICLES = 300;
const COLORS = ["#ffd166", "#ff5d8f", "#4cc9f0", "#9b5de5", "#06d6a0", "#ffffff", "#ff9f1c"];

export function createFx(canvas) {
    const ctx = canvas.getContext("2d");
    const parts = [];
    let raf = 0;
    let last = 0;
    let width = 0;
    let height = 0;
    let dpr = 1;
    const timers = new Set();

    function resize() {
        dpr = Math.min(1.5, window.devicePixelRatio || 1);
        width = canvas.clientWidth || window.innerWidth;
        height = canvas.clientHeight || window.innerHeight;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    const rand = (a, b) => a + Math.random() * (b - a);
    const pick = (list) => list[Math.floor(Math.random() * list.length)];

    function add(p) {
        if (parts.length >= MAX_PARTICLES) return;
        parts.push(p);
    }

    function confetti(x, y, angleDeg, speed, spread) {
        const ang = ((angleDeg + rand(-spread, spread)) * Math.PI) / 180;
        const v = speed * rand(0.72, 1.12);
        const shape = Math.random();
        add({
            kind: "confetti",
            x, y,
            vx: Math.cos(ang) * v,
            vy: Math.sin(ang) * v,
            rot: rand(0, Math.PI * 2),
            vr: rand(-0.25, 0.25),
            w: rand(7, 13),
            h: shape < 0.25 ? rand(7, 11) : rand(12, 20),
            round: shape < 0.25,
            color: pick(COLORS),
            wob: rand(0, Math.PI * 2),
            wobV: rand(0.08, 0.18),
            life: 1,
            decay: rand(0.0016, 0.0028),
        });
    }

    /** Sol və sağ kənardan eyni anda iki top atəşi (2 zərbə). */
    function cannons() {
        if (!width) resize();
        const s = Math.max(0.7, height / 1080);
        const y = height * 0.8;
        [0, 170].forEach((delay) => {
            const id = window.setTimeout(() => {
                timers.delete(id);
                for (let i = 0; i < 55; i += 1) {
                    confetti(-8, y + rand(-20, 20), -54, 31 * s, 11);
                    confetti(width + 8, y + rand(-20, 20), -126, 31 * s, 11);
                }
                start();
            }, delay);
            timers.add(id);
        });
    }

    function burst(x, y, count = 40) {
        if (!width) resize();
        const s = Math.max(0.7, height / 1080);
        const hue = pick(COLORS);
        for (let i = 0; i < count; i += 1) {
            const ang = (i / count) * Math.PI * 2 + rand(-0.08, 0.08);
            const v = rand(5.5, 9.5) * s;
            add({ kind: "spark", x, y, px: x, py: y, vx: Math.cos(ang) * v, vy: Math.sin(ang) * v, color: Math.random() < 0.3 ? "#ffffff" : hue, life: 1, decay: rand(0.012, 0.02), size: rand(2, 3.4) });
        }
        start();
    }

    function step(dt) {
        const g = 0.36;
        for (let i = parts.length - 1; i >= 0; i -= 1) {
            const p = parts[i];
            if (p.kind === "confetti") {
                p.vy += g * dt;
                const drag = p.vy > 0 ? 0.9 : 0.985; // düşəndə havada yellənərək yavaşlayır
                p.vx *= drag ** dt;
                p.vy *= drag ** dt;
                if (p.vy > 3.2) p.vy = 3.2;
                p.wob += p.wobV * dt;
                p.x += (p.vx + (p.vy > 0 ? Math.sin(p.wob) * 1.1 : 0)) * dt;
                p.y += p.vy * dt;
                p.rot += p.vr * dt;
                p.life -= p.decay * dt;
            } else {
                p.px = p.x;
                p.py = p.y;
                p.vy += 0.09 * dt;
                p.vx *= 0.97 ** dt;
                p.vy *= 0.97 ** dt;
                p.x += p.vx * dt;
                p.y += p.vy * dt;
                p.life -= p.decay * dt;
            }
            if (p.life <= 0 || p.y > height + 40 || p.x < -80 || p.x > width + 80) parts.splice(i, 1);
        }
    }

    function draw() {
        ctx.clearRect(0, 0, width, height);
        for (let i = 0; i < parts.length; i += 1) {
            const p = parts[i];
            ctx.globalAlpha = Math.max(0, Math.min(1, p.life * 1.4));
            if (p.kind === "confetti") {
                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rot);
                ctx.scale(1, Math.cos(p.wob)); // 3D çevrilmə illüziyası
                ctx.fillStyle = p.color;
                if (p.round) {
                    ctx.beginPath();
                    ctx.arc(0, 0, p.w / 2, 0, Math.PI * 2);
                    ctx.fill();
                } else {
                    ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
                }
                ctx.restore();
            } else {
                ctx.strokeStyle = p.color;
                ctx.lineWidth = p.size;
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(p.px, p.py);
                ctx.lineTo(p.x, p.y);
                ctx.stroke();
            }
        }
        ctx.globalAlpha = 1;
    }

    function frame(now) {
        const dt = last ? Math.min(3, (now - last) / 16.667) : 1;
        last = now;
        step(dt);
        draw();
        if (parts.length) {
            raf = requestAnimationFrame(frame);
        } else {
            raf = 0;
            last = 0;
            ctx.clearRect(0, 0, width, height);
        }
    }

    function start() {
        if (!raf) raf = requestAnimationFrame(frame);
    }

    /** reduced-motion: bir dəfə çəkilən statik bayram kadrı. */
    function staticFrame() {
        resize();
        for (let i = 0; i < 110; i += 1) {
            const p = { kind: "confetti", x: rand(0, width), y: rand(0, height * 0.55), rot: rand(0, 6.28), w: rand(7, 12), h: rand(12, 18), round: Math.random() < 0.25, color: pick(COLORS), wob: rand(0, 6.28), life: 0.9 };
            parts.push(p);
        }
        draw();
        parts.length = 0;
    }

    function stop() {
        timers.forEach((id) => window.clearTimeout(id));
        timers.clear();
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        last = 0;
        parts.length = 0;
        if (width) ctx.clearRect(0, 0, width, height);
    }

    resize();
    window.addEventListener("resize", resize);
    return {
        cannons,
        burst,
        staticFrame,
        stop,
        destroy() {
            stop();
            window.removeEventListener("resize", resize);
        },
        get count() {
            return parts.length;
        },
    };
}
