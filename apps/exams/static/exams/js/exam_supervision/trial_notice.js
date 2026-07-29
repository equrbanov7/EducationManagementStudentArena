import { ExamSupervision } from "./state.js?v=20260716-intervention";

// Sınaq (trial) cəhdi: pozuntu limiti aşılsa da imtahan DAYANDIRILMIR — müəllim
// yalnız real imtahanda nə olacağını görür. Kilid overlay-i əvəzinə bağlana
// bilən xəbərdarlıq banneri göstərilir. Ayrıca modul saxlanılır, çünki ui.js
// modul-ölçü büdcəsinin (600 sətir) sərhədindədir.
Object.assign(ExamSupervision, {
    _showTrialViolationNotice: function () {
        if (document.getElementById("supervision-trial-banner")) return;

        var i18n = window.SUPERVISION_ACK_I18N || {};
        var title = i18n.trialViolationTitle || "Sınaq rejimi — imtahan dayandırılmadı";
        var message =
            i18n.trialViolationMsg ||
            "Real imtahanda bu pozuntulara görə imtahandan uzaqlaşdırılardınız. " +
                "Sınaq yalnız yoxlama məqsədilidir, ona görə davam edə bilərsiniz.";

        var banner = document.createElement("div");
        banner.id = "supervision-trial-banner";
        banner.className = "supervision-trial-banner";
        banner.innerHTML =
            '<div class="supervision-trial-banner__inner">' +
            '<i class="fas fa-vial supervision-trial-banner__icon" aria-hidden="true"></i>' +
            "<div>" +
            '<div class="supervision-trial-banner__title"></div>' +
            '<div class="supervision-trial-banner__text"></div>' +
            "</div>" +
            '<span class="supervision-trial-banner__count"></span>' +
            '<button type="button" id="supervision-trial-dismiss" class="supervision-trial-banner__btn">OK</button>' +
            "</div>";

        // Mətn textContent ilə yazılır ki, tərcümə sətri HTML kimi şərh olunmasın.
        banner.querySelector(".supervision-trial-banner__title").textContent = title;
        banner.querySelector(".supervision-trial-banner__text").textContent = message;
        banner.querySelector(".supervision-trial-banner__count").textContent =
            (this._violationLabel || "Pozuntu") + ": " + this.violationCount + " / " + this.maxViolations;
        document.body.appendChild(banner);

        document.getElementById("supervision-trial-dismiss").addEventListener("click", function () {
            if (banner.parentNode) banner.remove();
        });
    },
});
