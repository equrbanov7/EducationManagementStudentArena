"use strict";
const lessons = JSON.parse(document.getElementById("lessons").textContent);
const video = document.getElementById("v"), list = document.getElementById("list");
const query = document.getElementById("query"), audience = document.getElementById("audience");
const chapters = document.getElementById("chapters"), pager = document.getElementById("pager");
let selected = 0, page = 1, captionUrl = "";
const format = s => Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0");
const normalize = s => s.toLocaleLowerCase("az").replace(/ə/g,"e").replace(/ı/g,"i").normalize("NFD").replace(/\p{M}/gu,"");
function button(text, handler) {
  const b = document.createElement("button");
  b.type = "button"; b.textContent = text; b.addEventListener("click",handler); return b;
}
for (const role of new Set(lessons.map(l=>l.audience))) audience.add(new Option(role, role));
function renderList() {
  const terms=normalize(query.value).split(/\s+/).filter(Boolean);
  const visible=lessons.filter(l=>(!audience.value||l.audience===audience.value)&&terms.every(t=>normalize([l.title,l.summary,l.section,l.audience,...l.chapters.map(c=>c.title)].join(" ")).includes(t)));
  const pages=Math.max(1,Math.ceil(visible.length/7));page=Math.min(page,pages);list.replaceChildren();pager.replaceChildren();
  let role="";
  for(const l of visible.slice((page-1)*7,page*7)){
    if(role!==l.audience){role=l.audience;const heading=document.createElement("h3");heading.textContent=role;list.append(heading);}
    const i=lessons.indexOf(l),b=button("",()=>selectLesson(i,true));
    for(const [cls, label] of [["n",l.order],["t",l.title],["d",format(l.duration)]]){
      const s=document.createElement("span");s.className=cls;s.textContent=label;b.append(s);
    }
    b.classList.toggle("on",i===selected);list.append(b);
  }
  if(!visible.length)list.textContent="Uyğun dərs tapılmadı.";
  for(let n=1;n<=pages&&pages>1;n++){const b=button(n,()=>{page=n;renderList();}); if(n===page)b.setAttribute("aria-current","page");pager.append(b);}
}
function selectLesson(i,auto){
  selected=i;const l=lessons[i];
  video.pause();video.replaceChildren();
  if(captionUrl)URL.revokeObjectURL(captionUrl);
  video.src=l.src;
  const track=document.createElement("track");track.kind="subtitles";track.srclang="az";track.label="Azərbaycanca";track.default=true;
  captionUrl=URL.createObjectURL(new Blob([l.vtt],{type:"text/vtt"}));track.src=captionUrl;video.append(track);
  document.getElementById("sec").textContent=l.audience+" · "+l.section+" · "+l.order;
  document.getElementById("ttl").textContent=l.title;document.getElementById("sum").textContent=l.summary;
  document.getElementById("prev").disabled=i===0;document.getElementById("next").disabled=i===lessons.length-1;
  chapters.replaceChildren();
  const chapterSearch = document.getElementById("chapter-query");
  chapterSearch.value = "";
  chapterSearch.hidden = l.chapters.length <= 14;
  chapterSearch.oninput = () => {
    const terms = normalize(chapterSearch.value).trim().split(/\s+/);
    for (const item of chapters.children) item.hidden = !terms.every(t => normalize(item.textContent).includes(t));
  };
  for(const ch of l.chapters){
    const row = document.createElement("div");
    row.append(button(format(ch.start)+"  "+ch.title,()=>{
      const go=()=>{video.currentTime=ch.start;video.play().catch(()=>{});};
      if(video.readyState)go();else{video.addEventListener("loadedmetadata",go,{once:true});video.load();}
    }));
    for (const item of ch.related || (ch.guide ? [{key:ch.guide,title:"Bu əməliyyatın təlimatı"}] : [])) {
      const related = document.createElement("a");
      related.textContent = item.title;
      const params = new URLSearchParams({role:l.role,guide:item.key});
      related.href = "FAQ.html?" + params;
      row.append(related);
    }
    chapters.append(row);
  }
  try{localStorage.setItem("emsTutLast",String(i));}catch(_){}
  renderList();if(auto)video.play().catch(()=>{});
}
audience.onchange=query.oninput=()=>{page=1;renderList();};
document.getElementById("prev").onclick=()=>selected>0&&selectLesson(selected-1,true);
document.getElementById("next").onclick=()=>selected+1<lessons.length&&selectLesson(selected+1,true);
video.addEventListener("ended",()=>selected+1<lessons.length&&selectLesson(selected+1,true));
let remembered=0;try{remembered=Number(localStorage.getItem("emsTutLast"))||0;}catch(_){}
selected=Math.max(0,Math.min(lessons.length-1,remembered));page=Math.floor(selected/7)+1;selectLesson(selected,false);
const linked = new URLSearchParams(location.search);
const linkedIndex = lessons.findIndex(l => l.id === linked.get("lesson"));
if (linkedIndex !== -1) {
  page = Math.floor(linkedIndex / 7) + 1;
  selectLesson(linkedIndex, false);
  const point = Number(linked.get("t")) || 0;
  if (point > 0) video.addEventListener("loadedmetadata", () => {video.currentTime = point;}, {once:true});
}
