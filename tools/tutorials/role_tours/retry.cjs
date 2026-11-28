"use strict";
const fs=require("fs"), path=require("path"), {launch}=require("../lib/browser.cjs");
const [base,root,inventoryFile,...requested]=process.argv.slice(2);
if (new URL(base).hostname!=="127.0.0.1") throw Error("Use the local demo");
const load=f=>JSON.parse(fs.readFileSync(f,"utf8")), inventory=load(inventoryFile);
const norm=s=>s.toLocaleLowerCase("az").replace(/[0-9—–:…()]/gu," ").replace(/\s+/g," ").trim();
async function fetchStatic(context){
    const index=process.env.TOUR_STATIC_INDEX?load(process.env.TOUR_STATIC_INDEX):{};
    const types={".css":"text/css",".js":"application/javascript",".woff2":"font/woff2",".woff":"font/woff",".svg":"image/svg+xml",".png":"image/png",".jpg":"image/jpeg",".webp":"image/webp",".json":"application/json"};
    await context.route("**/*",route=>{const r=route.request(),url=new URL(r.url());
        if(url.origin!==base||!["GET","HEAD","OPTIONS"].includes(r.method()))return route.abort();
        const file=index[url.pathname];
        if(file)return route.fulfill({path:file,contentType:types[path.extname(file)]||"application/octet-stream"});
        return route.continue();});
}
async function findControl(pane,label){
    const possible=await pane.locator('a,button,summary,input[type="button"],[role="tab"],[role="button"]').evaluateAll(items=>items.map((el,i)=>({i,
        label:el.getAttribute('aria-label')||el.innerText||el.getAttribute('title')||el.value||'',
        title:el.getAttribute('title')||'', hidden:!el.checkVisibility({visibilityProperty:true}),
        disabled:el.disabled || el.getAttribute("aria-disabled")==="true"})));
    const wanted=norm(label),matches=possible.filter(x=>[x.label,x.title].some(v=>norm(v)===wanted));
    const similar=possible.filter(x=>{const plain=norm(x.label);return wanted.length>=12 && plain.length>=12 && (plain.startsWith(wanted.slice(0,21))||wanted.startsWith(plain.slice(0,21)))});
    const pick=[...matches,...similar].sort((a,b)=>Number(a.hidden||a.disabled)-Number(b.hidden||b.disabled))[0];
    if(!pick)return {status:"Məlumat yükləndikdən sonra bu seçim göstərilmir"};
    if(pick.disabled)return {status:"Düymə cari nümunədə passivdir"};
    const el=pane.locator('a,button,summary,input[type="button"],[role="tab"],[role="button"]').nth(pick.i);
    const closed=el.locator('xpath=ancestor::details[not(@open)]');for(let i=0;i<3 && await closed.count();i++)await closed.first().locator(':scope > summary').click();
    if(!await el.isVisible())return {status:"Bu seçim cari vəziyyətdə gizlidir"};
    return {el};
}
async function repair(context,role,rows,dir){
    const p=await context.newPage();p.setDefaultTimeout(4000);p.setDefaultNavigationTimeout(18000);
    p.on("dialog",d=>d.dismiss());
    await p.goto(base+"/preview/"+role,{waitUntil:"domcontentloaded"});
    for(const row of rows){
        if(!row.ok||!row.errors.length)continue;
        const residual=[];
        for(const [i,e] of row.errors.entries()){
            if(row.opened.some(o=>o.label===e.label && (o.parent||"")===(e.parent||"")))continue;
            try{
                await p.goto(new URL(row.href,base).href,{waitUntil:"domcontentloaded"});await p.waitForTimeout(480);
                let pane=row.key?p.locator('[data-profile-section-panel="'+row.key+'"]:visible').first():p.locator('main:visible').first();
                if(!await pane.count())pane=p.locator('body');
                if(e.parent){const first=await findControl(pane,e.parent);if(first.el)await first.el.click();}
                const match=await findControl(pane,e.label);
                if(match.status){(row.unavailable??=[]).push({label:e.label,why:match.status});continue;}
                const el=match.el;await el.scrollIntoViewIfNeeded();
                await el.evaluate(x=>{x.style.outline="3px solid #e57812";x.style.outlineOffset="-2px"});
                const before="recovered-"+i+"-select.jpg",after="recovered-"+i+".jpg";
                const dest=path.join(dir,row.id);
                await p.screenshot({path:path.join(dest,before),quality:73});
                await el.click();await p.waitForTimeout(360);
                await p.screenshot({path:path.join(dest,after),quality:73});
                row.opened.push({label:e.label,frame:after,before,changed:true,tab:row.available.some(v=>v.label===e.label&&v.tab),parent:e.parent});
            }catch(err){residual.push({...e,message:String(err.message).slice(0,450)});}
        }
        row.errors=residual;
    }
    fs.writeFileSync(path.join(dir,"progress.json"),JSON.stringify(rows));
}
(async()=>{const b=await launch();const roles=requested.length?requested:Object.keys(inventory);
    async function run(){while(roles.length){const role=roles.shift(),dir=path.join(root,role),f=path.join(dir,"progress.json");if(!fs.existsSync(f))continue;
        const rows=load(f);if(!inventory[role].every(i=>rows.some(r=>r.href===i.href && r.ok)))continue;
        if(!rows.some(r=>r.errors.length))continue;
        const ctx=await b.newContext({viewport:{width:1280,height:800},locale:"az-AZ",reducedMotion:"reduce"});
        try{await fetchStatic(ctx);await repair(ctx,role,rows,dir);console.log(role,rows.reduce((n,r)=>n+r.errors.length,0),"unresolved");}finally{await ctx.close();}
    }}
    try{await Promise.all([run(),run(),run()])}finally{await b.close()}
})().catch(e=>{console.error(e);process.exit(1)});
