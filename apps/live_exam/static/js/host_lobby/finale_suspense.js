import { UI } from './dom.js?v=lx20260930';
import { FINAL_SUSPENSE_MS, PHASES } from './constants.js?v=lx20260930';
import { state } from './state.js?v=lx20260930';
import { playRiser } from './audio.js?v=lx20260930';
import { icon } from './icons.js?v=lx20260930';
import { setPresentationMarkup } from './presentation.js?v=lx20260930';
import { controlsEnabled, esc, tr } from './utils.js?v=lx20260930';

/* Sahib 2026-09-30: SON sualdan sonra liderlər lövhəsi göstərilmir — yerlər final səhnəsində
 * sürpriz kimi açılır. Son sualın nəticə fazasından sonra bu qısa «Nəticələr…» səhnəsi gəlir
 * (yüksələn səs + işıq), avtomatik rejimdə server `next_question_at`-da (final_suspense_ms)
 * finişə keçir və mövcud final səhnəsi (stage.js) başlayır. Əl rejimində səhnə «Növbəti»
 * basılana qədər qalır (səs bir dəfə çalır). Serverin son sual paketində `top`/`rank` yoxdur. */

/** Son sualın reveal-idirmi: server bayrağı (`final_question`) və ya sual sırası (ehtiyat). */
export function isFinalReveal(payload, question) {
    if (payload && payload.final_question === true) return true;
    const index = Number(question?.index || 0);
    const total = Number(question?.total || 0);
    return total > 0 && index >= total;
}

export function renderFinalSuspenseStage(payload) {
    const signature = `${state.revealKey}:${PHASES.SUSPENSE}`;
    if (state.phase === PHASES.SUSPENSE && state.phaseSignature === signature) return;
    const seconds = Math.max(1, Number(payload?.final_suspense_ms || FINAL_SUSPENSE_MS) / 1000);
    const manual = controlsEnabled() && !UI.autoMode?.checked;
    const fresh = setPresentationMarkup(
        PHASES.SUSPENSE,
        signature,
        `
            <section class="hx-scene hx-suspense" aria-live="polite">
                <div class="hx-suspense__glow" aria-hidden="true"></div>
                <span class="hx-suspense__trophy" aria-hidden="true">${icon("trophy")}</span>
                <h1 class="hx-suspense__title">${esc(tr("finalSuspenseTitle", "Nəticələr…"))}</h1>
                <p class="hx-suspense__sub">${esc(tr("finalSuspenseSub", "Kim qalib gəldi? Final səhnəsi başlayır!"))}</p>
                <span class="hx-dots" aria-hidden="true"><i></i><i></i><i></i></span>
                ${manual ? `<p class="hx-suspense__hint">${esc(tr("finalSuspenseHint", "Final səhnəsini açmaq üçün «Növbəti» düyməsini basın"))}</p>` : ""}
            </section>
        `
    );
    if (fresh) playRiser(`suspense:${state.revealKey}`, seconds);
}
