/*
 * appeal_stats.js
 * Source: apps/accounts/templates/accounts/profile/sections/_appeal_stats.html
 * Appeal statistics dashboard (filters, table, charts, AI summary).
 * URLs are bridged via data-* on .aps; i18n via data-i18n-* on .aps (read below).
 * Idempotent: guarded by root.dataset.apsInit; safe to re-run on profile AJAX swap.
 */
(function boot() {
  // searchable_select.js hələ yüklənməyibsə (skript sırası) — apsInit qoymadan
  // gözlə, sonra başlat (cədvəl "Yüklənir…"-də ilişib qalmasın).
  if (!window.EMSSearchableSelect) { setTimeout(boot, 30); return; }
  var root = document.querySelector(".aps");
  if (!root || root.dataset.apsInit === "1") { return; }
  root.dataset.apsInit = "1";
  var U = { data:root.dataset.dataUrl, charts:root.dataset.chartsUrl, filters:root.dataset.filtersUrl,
            ai:root.dataset.aiUrl, subject:root.dataset.subjectUrl, group:root.dataset.groupUrl,
            faculty:root.dataset.facultyUrl, department:root.dataset.departmentUrl, teacher:root.dataset.teacherUrl,
            detail:root.dataset.detailUrlTemplate, review:root.dataset.reviewUrlTemplate };
  var T = { total:root.dataset.i18nTotal, students:root.dataset.i18nStudents, exams:root.dataset.i18nExams,
            none:root.dataset.i18nNone, prev:root.dataset.i18nPrev, next:root.dataset.i18nNext,
            page:root.dataset.i18nPage, view:root.dataset.i18nView,
            ai_loading:root.dataset.i18nAiLoading, ai_error:root.dataset.i18nAiError,
            ai_quota:root.dataset.i18nAiQuota, ai_cached:root.dataset.i18nAiCached, hint:root.dataset.i18nHint };
  var COLORS = ["#2563eb","#059669","#f59e0b","#ef4444","#8b5cf6","#0ea5e9","#14b8a6","#f97316","#ec4899","#64748b"];
  var q = root.querySelector(".js-aps-q");
  // Sabit qısa siyahılar native bootstrap-select olaraq qalır.
  var sel = { type:root.querySelector(".js-aps-type"),
              format:root.querySelector(".js-aps-format"), status:root.querySelector(".js-aps-status"),
              semester:root.querySelector(".js-aps-semester"), year:root.querySelector(".js-aps-year") };
  // Fakültə/kafedra/müəllim — lazy axtarışlı seçicilər (paylaşılan komponent).
  var SS = window.EMSSearchableSelect;
  var facultyPick = SS.create(root.querySelector(".js-aps-faculty"), { url:U.faculty, onChange:reload });
  var deptPick    = SS.create(root.querySelector(".js-aps-department"), {
    url:U.department, dependParam:"faculty",
    getDependValue:function(){ return facultyPick.value(); }, onChange:reload });
  var teacherPick = SS.create(root.querySelector(".js-aps-teacher"), { url:U.teacher, onChange:reload });
  facultyPick.on("change", function(){ deptPick.reset(); });
  var cards = root.querySelector(".js-aps-cards"), rows = root.querySelector(".js-aps-rows"),
      pager = root.querySelector(".js-aps-pager"), thead = root.querySelector(".js-aps-thead");
  var page = 1, sort = "-date", timer = null, charts = {};
  function esc(s){ var d=document.createElement("div"); d.textContent=(s==null?"":s); return d.innerHTML; }
  function detailUrl(id){ return U.detail ? U.detail.replace(/\/0\/?$/, "/"+id+"/") : "#"; }
  function reviewUrl(id){ return U.review ? U.review.replace(/\/0\/?$/, "/"+id+"/") : "#"; }

  var subjectMS = SS.create(root.querySelector(".js-aps-subject"), { url:U.subject, multi:true, onChange:reload });
  var groupMS   = SS.create(root.querySelector(".js-aps-group"),   { url:U.group,   multi:true, onChange:reload });

  function params(extra){
    var p=new URLSearchParams();
    if(q.value.trim()) p.set("q", q.value.trim());
    if(subjectMS.ids().length) p.set("subjects", subjectMS.ids().join(","));
    if(groupMS.ids().length) p.set("groups", groupMS.ids().join(","));
    if(facultyPick.value()) p.set("faculties", facultyPick.value());
    if(deptPick.value()) p.set("departments", deptPick.value());
    if(teacherPick.value()) p.set("teachers", teacherPick.value());
    if(sel.type.value) p.set("type", sel.type.value);
    if(sel.format.value) p.set("format", sel.format.value);
    if(sel.status.value) p.set("status", sel.status.value);
    if(sel.semester.value) p.set("semester", sel.semester.value);
    if(sel.year.value) p.set("year", sel.year.value);
    if(sort) p.set("sort", sort);
    if(extra) Object.keys(extra).forEach(function(k){ p.set(k, extra[k]); });
    return p;
  }
  function card(n,l,mod){ return '<div class="aps-card'+(mod?" aps-card--"+mod:"")+'"><div class="aps-card__n">'+n+'</div><div class="aps-card__l">'+esc(l)+'</div></div>'; }
  function renderCards(s){
    var html = card(s.total,T.total)+card(s.students,T.students)+card(s.exams,T.exams);
    (s.by_status||[]).forEach(function(x){ html += card(x.n, x.label, x.code); });
    cards.innerHTML = html;
  }
  function renderArrows(){
    thead.querySelectorAll("th.is-sortable").forEach(function(th){
      var key=th.getAttribute("data-sort"), a=th.querySelector(".aps-arrow");
      th.classList.toggle("is-active", sort===key||sort==="-"+key);
      a.className="fas aps-arrow "+(sort===key?"fa-sort-up":(sort==="-"+key?"fa-sort-down":"fa-sort"));
    });
  }
  function skeletonRows(){
    var tr=""; for(var i=0;i<8;i++){ tr+='<tr>'; for(var c=0;c<10;c++){ tr+='<td><div class="aps-skel"></div></td>'; } tr+='</tr>'; }
    rows.innerHTML=tr;
  }
  function renderRows(data){
    var list=data.results||[];
    if(!list.length){ rows.innerHTML='<tr><td colspan="10"><div class="aps-state"><i class="fas fa-folder-open"></i>'+T.none+'</div></td></tr>'; pager.innerHTML=""; return; }
    function clip(v){ v=v||"—"; return '<td class="aps-clip" title="'+esc(v)+'">'+esc(v)+'</td>'; }
    rows.innerHTML=list.map(function(r){
      var badge='<span class="aps-badge aps-badge--'+esc(r.status_code)+'">'+esc(r.status)+'</span>';
      return '<tr><td><b>'+esc(r.student)+'</b><br><span class="aps-uname">@'+esc(r.username)+'</span></td>'+
        clip(r.group)+clip(r.teacher)+clip(r.exam)+clip(r.subject)+
        '<td>'+esc(r.type||"—")+'</td><td>'+esc(r.items)+'</td><td>'+badge+'</td><td>'+esc(r.date)+'</td>'+
        '<td><a class="aps-view" href="'+reviewUrl(r.appeal_id)+'" data-appeal-review-url="'+reviewUrl(r.appeal_id)+'" data-no-route-loading><i class="fas fa-eye"></i> '+T.view+'</a></td></tr>';
    }).join("");
    var pg=data.pagination;
    pager.innerHTML='<button class="js-aps-prev"'+(pg.has_prev?"":" disabled")+'>'+T.prev+'</button>'+
      '<span>'+T.page+' '+pg.page+' / '+pg.num_pages+' · '+pg.count+'</span>'+
      '<button class="js-aps-next"'+(pg.has_next?"":" disabled")+'>'+T.next+'</button>';
    var pv=pager.querySelector(".js-aps-prev"), nx=pager.querySelector(".js-aps-next");
    if(pv) pv.addEventListener("click", function(){ if(pg.has_prev){ page=pg.page-1; load(); } });
    if(nx) nx.addEventListener("click", function(){ if(pg.has_next){ page=pg.page+1; load(); } });
  }

  function whenChart(cb){ if(typeof window.Chart==="function"){ cb(); return; } var n=0, iv=setInterval(function(){ if(typeof window.Chart==="function"||n++>50){ clearInterval(iv); if(typeof window.Chart==="function") cb(); } }, 100); }
  function draw(key, canvas, cfg){ if(!canvas) return; if(charts[key]) charts[key].destroy(); charts[key]=new window.Chart(canvas, cfg); }
  function baseOpts(extra){ return Object.assign({responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}, extra||{}); }
  function renderCharts(d){
    whenChart(function(){
      draw("status", root.querySelector(".js-aps-c-status"), {type:"doughnut",
        data:{labels:d.by_status.labels, datasets:[{data:d.by_status.counts, backgroundColor:COLORS}]},
        options:baseOpts({cutout:"62%", plugins:{legend:{display:true, position:"bottom"}}})});
      draw("type", root.querySelector(".js-aps-c-type"), {type:"bar",
        data:{labels:d.by_type.labels, datasets:[{data:d.by_type.counts, backgroundColor:"#2563eb", borderRadius:6}]},
        options:baseOpts({scales:{y:{beginAtZero:true, ticks:{precision:0}}}})});
      draw("monthly", root.querySelector(".js-aps-c-monthly"), {type:"line",
        data:{labels:d.monthly.labels, datasets:[{data:d.monthly.counts, borderColor:"#2563eb", backgroundColor:"rgba(37,99,235,.12)", fill:true, tension:.3}]},
        options:baseOpts({scales:{y:{beginAtZero:true, ticks:{precision:0}}}})});
      draw("subject", root.querySelector(".js-aps-c-subject"), {type:"bar",
        data:{labels:d.by_subject.labels, datasets:[{data:d.by_subject.counts, backgroundColor:"#059669", borderRadius:6}]},
        options:baseOpts({indexAxis:"y", scales:{x:{beginAtZero:true, ticks:{precision:0}}}})});
      draw("teacher", root.querySelector(".js-aps-c-teacher"), {type:"bar",
        data:{labels:d.by_teacher.labels, datasets:[{data:d.by_teacher.counts, backgroundColor:"#8b5cf6", borderRadius:6}]},
        options:baseOpts({indexAxis:"y", scales:{x:{beginAtZero:true, ticks:{precision:0}}}})});
    });
  }

  function load(){
    skeletonRows(); renderArrows();
    fetch(U.data+"?"+params({page:page}).toString(), {headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(d){ if(!d) return; renderCards(d.summary); renderRows(d); });
    fetch(U.charts+"?"+params().toString(), {headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(d){ if(d) renderCharts(d); });
  }
  function reload(){ page=1; load(); }

  thead.querySelectorAll("th.is-sortable").forEach(function(th){
    th.addEventListener("click", function(){ var key=th.getAttribute("data-sort"); sort=(sort===key)?("-"+key):key; reload(); });
  });
  q.addEventListener("input", function(){ if(timer) clearTimeout(timer); timer=setTimeout(reload, 300); });
  Object.keys(sel).forEach(function(k){ sel[k].addEventListener("change", reload); });
  root.querySelector(".js-aps-reset").addEventListener("click", function(){
    q.value=""; subjectMS.clear(); groupMS.clear();
    facultyPick.reset(); deptPick.reset(); teacherPick.reset();
    Object.keys(sel).forEach(function(k){ sel[k].value=""; if(typeof sel[k]._refreshBootstrapSelect==="function") sel[k]._refreshBootstrapSelect(); });
    sort="-date"; reload();
  });

  // AI xülasə
  var aiOut = root.querySelector(".js-aps-ai-out");
  root.querySelector(".js-aps-ai-btn").addEventListener("click", function(){
    aiOut.innerHTML='<div class="aps-ai__loading"><i class="fas fa-spinner fa-spin"></i>'+esc(T.ai_loading)+'</div>';
    fetch(U.ai+"?"+params().toString(), {headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d || !d.ok){ aiOut.innerHTML='<div class="aps-ai__error">'+esc((d&&d.error)||T.ai_error)+'</div>'; return; }
        var html='<div class="aps-ai__text">'+markdown(d.summary||"")+'</div>';
        if(d.limit!=null){ html+='<div class="aps-ai__quota">'+esc(T.ai_quota)+': '+esc(d.remaining)+'/'+esc(d.limit)+(d.cached?' · '+esc(T.ai_cached):'')+'</div>'; }
        aiOut.innerHTML=html;
      })
      .catch(function(){ aiOut.innerHTML='<div class="aps-ai__error">'+esc(T.ai_error)+'</div>'; });
  });
  function markdown(t){
    var h=esc(t);
    h=h.replace(/^### (.*)$/gm,"<h4>$1</h4>").replace(/^## (.*)$/gm,"<h3>$1</h3>").replace(/^# (.*)$/gm,"<h3>$1</h3>");
    h=h.replace(/\*\*(.+?)\*\*/g,"<b>$1</b>");
    h=h.replace(/^\s*[-*] (.*)$/gm,"<li>$1</li>").replace(/(<li>[\s\S]*?<\/li>)/g,"<ul>$1</ul>");
    h=h.replace(/\n{2,}/g,"</p><p>").replace(/\n/g,"<br>");
    return "<p>"+h+"</p>";
  }

  fetch(U.filters, {headers:{"X-Requested-With":"XMLHttpRequest"}})
    .then(function(r){ return r.ok?r.json():null; })
    .then(function(d){ if(!d) return;
      function fill(s, arr, valKey, labKey){ (arr||[]).forEach(function(x){ var o=document.createElement("option"); o.value=x[valKey]; o.textContent=x[labKey]; s.appendChild(o); }); }
      (d.academic_years||[]).forEach(function(y){ var o=document.createElement("option"); o.value=y.value; o.textContent=y.label; sel.year.appendChild(o); });
      // Fakültə/kafedra/müəllim artıq lazy axtarışlı seçicilərdir → burada doldurulmur.
      fill(sel.type, d.types, "value", "label");
      fill(sel.format, d.formats, "value", "label");
      fill(sel.status, d.statuses, "value", "label");
      fill(sel.semester, d.semesters, "value", "label");
      Object.keys(sel).forEach(function(k){ if(typeof sel[k]._refreshBootstrapSelect==="function") sel[k]._refreshBootstrapSelect(); });
    });
  load();
})();
