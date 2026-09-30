// Sahib 2026-09-30: SON sualdan sonra telefon liderlər lövhəsini və öz yerini GÖSTƏRMİR —
// finalın sürprizi qalsın. Son sualın nəticəsindən sonra «Nəticələr ekranda!» gözləmə görünüşü;
// `finished` gələndə də görünüş qalır və oyunçunun yeri yalnız final səhnəsi (aparıcının
// stage.js-i) həmin yeri AÇAN anda göstərilir. Səhnənin zaman xətti aparıcının saf
// stage_logic.js modulundan götürülür (tək həqiqət mənbəyi — iki yerdə təkrarlanmır).
// Server də son sualın reveal paketində `top`/`rank` göndərmir (reveal.py).
import { PHASES } from './config.js?v=lx20260930';
import { state } from './state.js?v=lx20260930';
import { announce, setQuestionChip, setRank, setTimer, stopTimeBar } from './ui.js?v=lx20260930';
import { esc, isOwnRow, normalizeTopRows, toInt, tr } from './utils.js?v=lx20260930';
import { mountView } from './views.js?v=lx20260930';
import { buildStageModel, stageTimeline } from '../host_lobby/stage_logic.js?v=lx20260930';

const TROPHY_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 3.5h10v5a5 5 0 0 1-10 0z" fill="currentColor"/><path d="M7 5.5H4v1.5A3.5 3.5 0 0 0 7.4 10.5M17 5.5h3v1.5a3.5 3.5 0 0 1-3.4 3.5M12 13.5v3.5M8 20.5h8M9.5 17h5v3.5h-5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

// Görünüş açarı sabitdir: son reveal → finished keçidində görünüş YENİDƏN qurulmur (ikiqat animasiya yox).
const SUSPENSE_KEY = "final-suspense";
// Səhnədə yer «açılır» (reveal addımı) → xal sayılmağa başlayır; telefon eyni ana düşsün.
const OWN_REVEAL_LAG_MS = 300;
// Podiumdan kənar oyunçular: qalib açılandan az sonra (hamı birlikdə).
const AFTER_WINNER_MS = 900;

/** Son sualın reveal-idirmi: server bayrağı və ya (ehtiyat) sualın sırası. */
export function isFinalReveal(payload) {
    if (payload && payload.final_question === true) return true;
    const question = state.currentQuestion || {};
    const index = toInt(question.index, 0);
    return index > 0 && index >= toInt(question.total, 0);
}

export function renderFinalSuspense() {
    const title = tr("finalSuspenseTitle", "Nəticələr ekranda!");
    const { created } = mountView(
        SUSPENSE_KEY,
        `<div class="lxp-suspense">` +
            `<div class="lxp-suspense__badge" aria-hidden="true">${TROPHY_SVG}</div>` +
            `<h1 class="lxp-title">${esc(title)}</h1>` +
            `<p class="lxp-sub">${esc(tr("finalSuspenseBody", "Yerin final səhnəsində açılacaq — gözün böyük ekranda olsun 👀"))}</p>` +
            `<div class="lxp-dots lxp-dots--lg" aria-hidden="true"><span></span><span></span><span></span></div>` +
            `</div>`,
        { tone: "suspense" }
    );
    state.phase = PHASES.SUSPENSE;
    if (!created) return;
    setQuestionChip(null);
    setTimer(false);
    stopTimeBar();
    setRank(null);
    announce(title);
}

function ownRank(payload) {
    const rank = toInt(payload && payload.rank, 0);
    if (rank > 0) return rank;
    const index = normalizeTopRows(payload && payload.top).findIndex(isOwnRow);
    return index >= 0 ? index + 1 : 0;
}

/** Final səhnəsinin başlanğıcından (ms) bu oyunçunun yerinin açıldığı ana qədər. */
export function stageRevealOffsetMs(payload) {
    const top = Array.isArray(payload && payload.top) ? payload.top : [];
    const model = buildStageModel(top, { totalPlayers: payload && payload.total_players });
    const steps = stageTimeline(model, { reduced: false });
    const revealAt = (place) => {
        const step = steps.find((item) => item.action === "reveal" && item.place === place);
        return step ? step.at : null;
    };
    const rank = ownRank(payload);
    if (rank >= 1 && rank <= 3) {
        const at = revealAt(rank);
        if (at !== null) return at + OWN_REVEAL_LAG_MS;
    }
    const winner = revealAt(1);
    if (winner !== null) return winner + AFTER_WINNER_MS;
    const empty = steps.find((item) => item.action === "empty");
    return empty ? empty.at : 0;
}
