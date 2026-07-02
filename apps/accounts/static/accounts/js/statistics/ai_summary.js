(function (window, document) {
  "use strict";

  var ns = window.EMSStatistics || (window.EMSStatistics = {});

  function init(ctx) {
    var i18n = ctx.i18n;
    var aiBtn = document.getElementById("statsAiSummaryBtn");
    var aiBody = document.getElementById("statsAiSummaryBody");
    var aiMeta = document.getElementById("statsAiSummaryMeta");
    var aiBtnLabel = aiBtn ? aiBtn.querySelector(".stats-ai-btn__label") : null;
    var aiDefaultLabel = aiBtnLabel ? aiBtnLabel.textContent : "";

    if (aiBtn && aiBody) {
      aiBtn.addEventListener("click", function () {
        var loadingMsg = i18n.ai_loading || "AI summary is loading...";
        aiBtn.disabled = true;
        aiBtn.classList.add("is-loading");

        if (aiBtnLabel) {
          aiBtnLabel.textContent = loadingMsg;
        }

        aiBody.innerHTML =
          '<div class="stats-ai-state stats-ai-state--loading">' +
          '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>' +
          '<span class="ms-2 text-muted">' + loadingMsg + "</span>" +
          "</div>";

        if (aiMeta) {
          aiMeta.innerHTML =
            '<span class="stats-ai-meta__pill">Cari filtrlər tətbiq olunur</span>' +
            '<span class="stats-ai-meta__pill">AI cavabı hazırlanır</span>';
        }

        var params = new URLSearchParams(window.location.search);
        params.set("section", "statistics");
        params.set("stat_ai_summary", "1");

        fetch(window.location.pathname + "?" + params.toString(), {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin"
        })
          .then(function (response) { return response.json(); })
          .then(function (json) {
            if (json.ok && json.summary) {
              aiBody.innerHTML = '<div class="ai-summary-content">' + ns.utils.markdownToHtml(json.summary) + "</div>";
              if (aiMeta) {
                var metaParts = ['<span class="stats-ai-meta__pill">Filtr üzrə AI xülasə</span>'];
                if (json.remaining !== undefined) {
                  metaParts.push(
                    '<span class="stats-ai-meta__pill">' +
                    (i18n.ai_remaining || "Remaining requests") + ": " + json.remaining + "/" + (json.limit || "?") +
                    "</span>"
                  );
                }
                if (json.cached) {
                  metaParts.push('<span class="stats-ai-meta__pill stats-ai-meta__pill--success">Keşdən cavab</span>');
                }
                aiMeta.innerHTML = metaParts.join("");
              }
            } else {
              aiBody.innerHTML =
                '<div class="stats-ai-state stats-ai-state--warning">' +
                (json.error || i18n.ai_not_received || "AI summary could not be received.") +
                "</div>";
              if (aiMeta) {
                aiMeta.innerHTML = '<span class="stats-ai-meta__pill stats-ai-meta__pill--warning">AI xülasə alınmadı</span>';
              }
            }
          })
          .catch(function () {
            aiBody.innerHTML =
              '<div class="stats-ai-state stats-ai-state--error">' +
              (i18n.ai_error || "An error occurred during the AI request.") +
              "</div>";
            if (aiMeta) {
              aiMeta.innerHTML = '<span class="stats-ai-meta__pill stats-ai-meta__pill--danger">AI xətası</span>';
            }
          })
          .finally(function () {
            aiBtn.disabled = false;
            aiBtn.classList.remove("is-loading");
            if (aiBtnLabel) {
              aiBtnLabel.textContent = aiDefaultLabel;
            }
          });
      });
    }
  }

  ns.aiSummary = {
    init: init
  };
})(window, document);
