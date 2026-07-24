/*
 * exam_center_stats_boot.js
 * Source: apps/accounts/templates/accounts/profile/sections/_exam_center_stats.html
 * Exam-center statistics table: filters, searchable pickers, sort, pagination,
 * Excel export. All URLs are read from data-* on the .ecs root; the translated
 * UI strings (the old inline `T` object) are bridged via the
 * #ecs-boot-i18n JSON block kept in the template. Logic moved verbatim.
 * Self-executes on load; the section loader re-runs it verbatim on each swap.
 */
(function boot() {
  // Axtarışlı seçici komponenti (searchable_select.js) hələ yüklənməyibsə
  // (skript sırası) — ecsInit qoymadan gözlə, sonra başlat. Beləcə cədvəl heç
  // vaxt "Yüklənir…"-də ilişib qalmır.
  if (!window.EMSSearchableSelect) { setTimeout(boot, 30); return; }
  var root = document.querySelector(".ecs");
  if (!root || root.dataset.ecsInit === "1") { return; }
  root.dataset.ecsInit = "1";
  var U = { data:root.dataset.dataUrl, filters:root.dataset.filtersUrl, export:root.dataset.exportUrl,
            subject:root.dataset.subjectUrl, group:root.dataset.groupUrl,
            faculty:root.dataset.facultyUrl, department:root.dataset.departmentUrl, teacher:root.dataset.teacherUrl,
            view:root.dataset.viewUrlTemplate };
  var q = root.querySelector(".js-ecs-q"),
      typeSel = root.querySelector(".js-ecs-type"), yearSel = root.querySelector(".js-ecs-year"),
      cards = root.querySelector(".js-ecs-cards"), rows = root.querySelector(".js-ecs-rows"),
      pager = root.querySelector(".js-ecs-pager"), thead = root.querySelector(".js-ecs-thead");
  var T = (function () {
    var el = document.getElementById("ecs-boot-i18n");
    if (!el) { return {}; }
    try { return JSON.parse(el.textContent) || {}; } catch (e) { return {}; }
  })();
  var page = 1, sort = "-date", timer = null;
  function esc(s){ var d=document.createElement("div"); d.textContent=(s==null?"":s); return d.innerHTML; }
  function viewUrl(slug, id){ return U.view ? U.view.replace("__SLUG__", encodeURIComponent(slug)).replace("/attempt/0/", "/attempt/"+id+"/") : ""; }

  // Axtarışlı seçicilər — paylaşılan komponent (debounce + lazy infinite-scroll
  // + kaskad + kəsilmə-önləyən yerləşdirmə). Fənn/qrup çoxseçimli (chips),
  // fakültə/kafedra/müəllim təkseçimli.
  var SS = window.EMSSearchableSelect;
  var subjectMS = SS.create(root.querySelector(".js-ecs-subject"), { url:U.subject, multi:true, onChange:reload });
  var groupMS   = SS.create(root.querySelector(".js-ecs-group"),   { url:U.group,   multi:true, onChange:reload });
  var facultyPick = SS.create(root.querySelector(".js-ecs-faculty"), { url:U.faculty, onChange:reload });
  var deptPick    = SS.create(root.querySelector(".js-ecs-department"), {
    url:U.department, dependParam:"faculty",
    getDependValue:function(){ return facultyPick.value(); }, onChange:reload });
  var teacherPick = SS.create(root.querySelector(".js-ecs-teacher"), { url:U.teacher, onChange:reload });
  // Fakültə → kafedra kaskadı: fakültə dəyişəndə kafedra seçimi sıfırlanır
  // (növbəti sorğu yeni fakültəyə görə daralacaq).
  facultyPick.on("change", function(){ deptPick.reset(); });

  function params(extra){
    var p = new URLSearchParams();
    if (q.value.trim()) p.set("q", q.value.trim());
    if (subjectMS.ids().length) p.set("subjects", subjectMS.ids().join(","));
    if (groupMS.ids().length) p.set("groups", groupMS.ids().join(","));
    if (facultyPick.value()) p.set("faculties", facultyPick.value());
    if (deptPick.value()) p.set("departments", deptPick.value());
    if (teacherPick.value()) p.set("teachers", teacherPick.value());
    if (typeSel.value) p.set("type", typeSel.value);
    if (yearSel.value) p.set("year", yearSel.value);
    if (sort) p.set("sort", sort);
    if (extra) Object.keys(extra).forEach(function(k){ p.set(k, extra[k]); });
    return p;
  }
  function card(n, l){ return '<div class="ecs-card"><div class="ecs-card__n">'+n+'</div><div class="ecs-card__l">'+esc(l)+'</div></div>'; }
  function renderCards(s){
    cards.innerHTML = card(s.total, T.total) + card(s.students, T.students) + card(s.exams, T.exams) +
      (s.by_type||[]).map(function(x){ return card(x.n, (x["exam__exam_type_extended"]||"—")); }).join("");
  }
  function renderArrows(){
    thead.querySelectorAll("th.is-sortable").forEach(function(th){
      var key = th.getAttribute("data-sort"); var a = th.querySelector(".ecs-arrow");
      var active = (sort===key || sort==="-"+key);
      th.classList.toggle("is-active", active);
      a.className = "fas ecs-arrow " + (sort===key ? "fa-sort-up" : (sort==="-"+key ? "fa-sort-down" : "fa-sort"));
    });
  }
  function renderRows(data){
    var list = data.results||[];
    if (!list.length){ rows.innerHTML = '<tr><td colspan="13"><div class="ecs-state"><i class="fas fa-folder-open"></i>'+T.none+'</div></td></tr>'; pager.innerHTML=""; return; }
    function clip(v){ v = v || "—"; return '<td class="ecs-clip" title="'+esc(v)+'">'+esc(v)+'</td>'; }
    rows.innerHTML = list.map(function(r){
      var vu = viewUrl(r.exam_slug, r.attempt_id);
      var view = vu ? '<a class="ecs-view" href="'+vu+'" target="_blank" rel="noopener"><i class="fas fa-eye"></i> '+T.view+'</a>' : '—';
      // İmtahandan uzaqlaşdırılmış tələbə — qırmızı sətir + status + səbəb.
      var statusCell = r.removed
        ? '<td class="ecs-status-removed"><b>'+esc(T.removed)+'</b>'+
            (r.removal_reason ? '<div class="ecs-removed-reason" title="'+esc(r.removal_reason)+'">'+esc(r.removal_reason)+'</div>' : '')+'</td>'
        : '<td>'+esc(r.status)+'</td>';
      return '<tr'+(r.removed?' class="ecs-row--removed"':'')+'><td><b>'+esc(r.student)+'</b><br><span class="ecs-uname">@'+esc(r.username)+'</span></td>'+
        clip(r.group)+clip(r.kafedra)+clip(r.faculty)+clip(r.teacher)+clip(r.exam)+clip(r.subject)+
        '<td>'+esc(r.type||"—")+'</td><td>'+esc(r.score||"—")+'</td><td class="ecs-pct">'+esc(r.percentage||"—")+'</td>'+
        statusCell+'<td>'+esc(r.date)+'</td><td>'+view+'</td></tr>';
    }).join("");
    var pg = data.pagination;
    pager.innerHTML = '<button class="js-ecs-prev"'+(pg.has_prev?"":" disabled")+'>'+T.prev+'</button>'+
      '<span>'+T.page+' '+pg.page+' '+T.of+' '+pg.num_pages+' · '+pg.count+'</span>'+
      '<button class="js-ecs-next"'+(pg.has_next?"":" disabled")+'>'+T.next+'</button>';
    var pv=pager.querySelector(".js-ecs-prev"), nx=pager.querySelector(".js-ecs-next");
    if(pv) pv.addEventListener("click", function(){ if(pg.has_prev){ page=pg.page-1; load(); } });
    if(nx) nx.addEventListener("click", function(){ if(pg.has_next){ page=pg.page+1; load(); } });
  }
  function skeletonRows(){
    var tr=""; for(var i=0;i<8;i++){ tr+='<tr>'; for(var c=0;c<13;c++){ tr+='<td><div class="ecs-skel"></div></td>'; } tr+='</tr>'; }
    rows.innerHTML=tr;
  }
  function load(){
    skeletonRows();
    renderArrows();
    // Qrafik modulu (exam_center_stats_charts.js) cari filtrlərlə sinxronlaşır.
    try { document.dispatchEvent(new CustomEvent("ecs:filters", { detail: { query: params().toString() } })); } catch (e) {}
    fetch(U.data + "?" + params({page:page}).toString(), {headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(d){ if(!d) return; renderCards(d.summary); renderRows(d); });
  }
  function reload(){ page = 1; load(); }

  thead.querySelectorAll("th.is-sortable").forEach(function(th){
    th.addEventListener("click", function(){
      var key = th.getAttribute("data-sort");
      sort = (sort === key) ? ("-"+key) : key;   // ilk klik ▲ (asc), ikinci ▼ (desc)
      reload();
    });
  });
  q.addEventListener("input", function(){ if(timer) clearTimeout(timer); timer=setTimeout(reload, 300); });
  [typeSel, yearSel].forEach(function(s){ s.addEventListener("change", reload); });
  root.querySelector(".js-ecs-export").addEventListener("click", function(e){ e.preventDefault(); window.location.href = U.export + "?" + params().toString(); });

  // Fakültə/kafedra/müəllim artıq lazy axtarışlı seçicilərdir → filters yalnız
  // sabit qısa siyahıları (il, tip) doldurur.
  fetch(U.filters, {headers:{"X-Requested-With":"XMLHttpRequest"}})
    .then(function(r){ return r.ok?r.json():null; })
    .then(function(d){ if(!d) return;
      (d.academic_years||[]).forEach(function(y){ var o=document.createElement("option"); o.value=y.value; o.textContent=y.label; yearSel.appendChild(o); });
      (d.types||[]).forEach(function(t){ var o=document.createElement("option"); o.value=t.value; o.textContent=t.label; typeSel.appendChild(o); });
      // Bootstrap select-lər dinamik option-lardan sonra yenilənməlidir.
      [typeSel, yearSel].forEach(function(s){ if (typeof s._refreshBootstrapSelect === "function") { s._refreshBootstrapSelect(); } });
    });
  load();
})();
