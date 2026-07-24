/*
 * pin_lookup.js
 * Source: exams/exam_center/_pin_lookup_body.html
 * Exam-center PIN lookup (master-detail): live student search + selected
 * student's ticket/PIN detail. URLs come from data-* on .pl2; i18n from the
 * #pl2-i18n JSON island. Runs as a bare IIFE (re-executed by the profile SPA
 * loader on each section swap, matching the original inline behaviour).
 */
(function () {
  var root = document.querySelector(".pl2");
  if (!root) { return; }
  var searchUrl = root.getAttribute("data-search-url");
  var detailTpl = root.getAttribute("data-detail-url-template");
  var input = root.querySelector(".js-pl2-search");
  var results = root.querySelector(".js-pl2-results");
  var detail = root.querySelector(".js-pl2-detail");
  var DEBOUNCE = 280, timer = null, seq = 0, dseq = 0;
  var PAGE_SIZE = 15, offset = 0, hasMore = false, loadingMore = false, currentQuery = "";
  var i18nEl = document.getElementById("pl2-i18n");
  var T = i18nEl ? JSON.parse(i18nEl.textContent) : {};
  function esc(s){ var d=document.createElement("div"); d.textContent=(s==null?"":s); return d.innerHTML; }
  function initials(n){ var p=(n||"").trim().split(/\s+/); return ((p[0]||"?")[0]+((p[1]||"")[0]||"")).toUpperCase(); }
  function state(box, icon, text){ box.innerHTML='<div class="pl2-state"><i class="fas '+icon+'"></i>'+esc(text)+'</div>'; }
  function skeletonRows(box, n){
    var row='<div class="pl2-row" aria-hidden="true"><span class="skeleton skeleton-circle" style="width:2.3rem;height:2.3rem"></span>'+
      '<span class="pl2-who" style="flex:1 1 auto"><span class="skeleton skeleton-line" style="width:60%;margin-bottom:.35rem"></span>'+
      '<span class="skeleton skeleton-line skeleton-line--sm" style="width:35%"></span></span></div>';
    box.innerHTML = new Array(n+1).join(row);
  }
  function skeletonDetail(box){
    box.innerHTML='<div class="pl2-exam" aria-hidden="true"><span class="skeleton skeleton-line" style="width:45%;margin-bottom:.6rem"></span>'+
      '<span class="skeleton skeleton-block" style="height:56px"></span></div>';
  }

  function renderResults(items, append){
    if (!append && !items.length){ state(results,"fa-user-slash",T.noResults); return; }
    if (!append) { results.innerHTML=""; }
    items.forEach(function(u){
      var row=document.createElement("div");
      row.className="pl2-row"; row.setAttribute("role","option");
      var kaf=u.kafedra?'<span class="pl2-kaf">'+esc(u.kafedra)+'</span>':'';
      row.innerHTML='<span class="pl2-avatar">'+esc(initials(u.name))+'</span>'+
        '<span class="pl2-who"><div class="pl2-name">'+esc(u.name)+'</div><div class="pl2-user">@'+esc(u.username)+'</div></span>'+
        '<span class="pl2-tail">'+kaf+'<span class="pl2-cnt">'+u.ticket_count+' '+T.exams+'</span></span>';
      row.addEventListener("click", function(){
        results.querySelectorAll(".pl2-row").forEach(function(r){ r.classList.remove("is-active"); });
        row.classList.add("is-active");
        openStudent(u.id, u.name);
      });
      results.appendChild(row);
    });
  }
  // `reset`=true → yeni axtarış (səhifə 1-dən); `reset`=false → aşağı
  // sürüşdürdükcə növbəti səhifə (lazy, bütün PIN-li tələbələr bir dəfəyə
  // yüklənmir).
  function doSearch(q, reset){
    if (reset) { offset=0; hasMore=false; currentQuery=q; }
    if (!reset) { if (loadingMore || !hasMore) return; loadingMore=true; }
    var mine = reset ? ++seq : seq;
    if (reset) { skeletonRows(results, 3); }
    fetch(searchUrl+"?q="+encodeURIComponent(q)+"&offset="+offset+"&limit="+PAGE_SIZE, {headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(function(r){ return r.ok?r.json():{results:[], has_more:false}; })
      .then(function(d){
        if (reset && mine!==seq) return;
        var items=(d&&d.results)||[];
        renderResults(items, !reset);
        offset+=items.length;
        hasMore=Boolean(d&&d.has_more);
        if (!reset) loadingMore=false;
      })
      .catch(function(){
        if (reset) { if(mine===seq) state(results,"fa-triangle-exclamation","—"); }
        else { loadingMore=false; }
      });
  }
  results.addEventListener("scroll", function(){
    if (loadingMore || !hasMore) return;
    if (results.scrollTop + results.clientHeight >= results.scrollHeight - 40) {
      doSearch(currentQuery, false);
    }
  });
  function openStudent(id, name){
    var mine=++dseq; skeletonDetail(detail);
    fetch(detailTpl.replace(/0\/?$/, id+"/"),{headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(d){ if(mine===dseq) renderDetail(d, name); })
      .catch(function(){ if(mine===dseq) state(detail,"fa-triangle-exclamation","—"); });
    if (window.matchMedia && window.matchMedia("(max-width: 900px)").matches){ detail.scrollIntoView({behavior:"smooth", block:"start"}); }
  }
  function renderDetail(d, fallbackName){
    if (!d){ state(detail,"fa-triangle-exclamation","—"); return; }
    var s=d.student||{name:fallbackName, username:""};
    var t=d.tickets||[];
    var head='<div class="pl2-detail__head"><span class="pl2-avatar">'+esc(initials(s.name))+'</span>'+
      '<div><div class="pl2-detail__name">'+esc(s.name)+'</div><div class="pl2-detail__user">@'+esc(s.username)+'</div></div></div>';
    if (!t.length){ detail.innerHTML=head+'<div class="pl2-state"><i class="fas fa-inbox"></i>'+T.noTickets+'</div>'; return; }
    var body="";
    t.forEach(function(x){
      var pin=x.pin_available
        ?'<div class="pl2-pinbox"><span class="pl2-pinbox__label">'+T.pin+'</span><span class="pl2-pin">'+esc(x.pin)+'</span></div>'
        :'<div class="pl2-pinbox"><span class="pl2-pin pl2-pin--none">'+T.noPin+'</span></div>';
      var meta=['<span class="pl2-status">'+esc(x.status)+'</span>'];
      if (x.subject) meta.push('<span><b>'+T.subject+':</b> '+esc(x.subject)+'</span>');
      if (x.room) meta.push('<span><b>'+T.room+':</b> '+esc(x.room)+'</span>');
      if (x.scheduled_start) meta.push('<span><b>'+T.time+':</b> '+esc(x.scheduled_start)+(x.scheduled_end?('–'+esc(x.scheduled_end)):'')+'</span>');
      if (x.seat) meta.push('<span><b>'+T.seat+':</b> '+esc(x.seat)+'</span>');
      if (x.language) meta.push('<span><b>'+T.lang+':</b> '+esc(x.language)+'</span>');
      body+='<div class="pl2-exam"><div class="pl2-exam__top"><div><div class="pl2-exam__title">'+esc(x.exam_title)+'</div>'+
        (x.subject?'<div class="pl2-exam__subject">'+esc(x.subject)+'</div>':'')+'</div>'+pin+'</div>'+
        '<div class="pl2-meta">'+meta.join("")+'</div></div>';
    });
    detail.innerHTML=head+body;
  }
  input.addEventListener("input", function(){
    if (timer) clearTimeout(timer);
    var q=input.value.trim();
    timer=setTimeout(function(){ doSearch(q, true); }, DEBOUNCE);
  });
  doSearch("", true); // ilk səhifə (biletli tələbələr)
})();
