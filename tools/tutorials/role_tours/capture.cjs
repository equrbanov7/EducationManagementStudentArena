"use strict";

const fs = require("fs");
const path = require("path");
const {launch} = require("../lib/browser.cjs");
const {controlsInPanel} = require("./controls.cjs");
const [base, sessions, output, roleList] = process.argv.slice(2);
if (!base || !sessions || !output || new URL(base).hostname !== '127.0.0.1') throw Error('Local synthetic demo base URL, sessions and output are required');
const read = file => JSON.parse(fs.readFileSync(file,'utf8'));
const allRoles = Object.keys(read(path.join(sessions,'roles.json')));
const roles = roleList ? roleList.split(',') : allRoles;
const frameSize = {width:1280,height:800};
const sidebar = '#profileSidebar';
const assetIndex = process.env.TOUR_STATIC_INDEX ? read(process.env.TOUR_STATIC_INDEX) : {};
const mime = {'.css':'text/css','.js':'application/javascript','.woff2':'font/woff2','.woff':'font/woff','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.json':'application/json','.gif':'image/gif','.ico':'image/x-icon'};
const assetCache = new Map();
const home = base+'/accounts/profile/?section=dashboard';

async function picture(page, file) {
    await page.screenshot({path:file, type:'jpeg', quality:73, animations:'disabled', timeout:6500});
}
async function mark(link) {
    await link.scrollIntoViewIfNeeded({timeout:2200});
    await link.evaluate(el=>{
        document.querySelectorAll('[data-tour-focus]').forEach(x=>{x.style.outline='';x.style.outlineOffset='';x.removeAttribute('data-tour-focus')});
        el.style.outline='3px solid #e57812';el.style.outlineOffset='-2px';el.setAttribute('data-tour-focus','');
    });
}
// DOM text can stay identical when a tab opens an empty semester or a shared panel.
function selectedTabState(el) {
    const group = el.closest('[role="tablist"],.ems-tabs,.nav-tabs,[class$="__tabs"],[class$="-tabs"]');
    if (el.getAttribute('role') !== 'tab' && !group) return null;
    const visible = node => node && node.getClientRects().length > 0 &&
        node.checkVisibility({visibilityProperty:true});
    if (!visible(el)) return null;
    const ariaSelected = el.getAttribute('aria-selected');
    const ariaCurrent = el.getAttribute('aria-current');
    const selected = ariaSelected !== null ? ariaSelected === 'true' :
        ariaCurrent !== null ? Boolean(ariaCurrent && ariaCurrent !== 'false') :
        Array.from(el.classList).some(name => /(?:^|[-_])(?:active|selected|current)$/.test(name));
    if (!selected) return false;
    const targets = (el.getAttribute('aria-controls') || '').trim().split(/\s+/).filter(Boolean);
    if (targets.length) return targets.some(id => visible(document.getElementById(id)));
    const section = el.closest('[data-profile-section-panel]') || document;
    const key = el.getAttribute('data-ems-tab');
    const panel = key && section.querySelector('[data-ems-tabpanel="' + CSS.escape(key) + '"]');
    return !panel || visible(panel);
}
async function selectionAfterClick(pane, choice) {
    // Server-rendered tabs may replace the original button and its capture marker.
    const control = pane.locator('[data-tutorial-control="'+choice.id+'"]').first();
    for (let attempt=0; attempt<4; attempt++) {
        if (!(await pane.isVisible())) return false;
        if (!(await control.isVisible())) await pane.evaluate(controlsInPanel).catch(()=>{});
        if (await control.isVisible() && await control.evaluate(selectedTabState).catch(()=>false)) return true;
        if (attempt < 3) await pane.page().waitForTimeout(200);
    }
    return false;
}
function settingsGroup(item) {
    if (item.key !== 'system-settings') return '';
    return new URL(item.href,base).searchParams.get('ss_group') || 'overview';
}
function sectionPane(page,key,group='') {
    if (!key) return page.locator('main:visible,#content:visible,.container:visible,body').filter({visible:true}).last();
    const sub = group ? '[data-profile-section-sub="'+group+'"]' : '';
    return page.locator('[data-profile-section-panel="'+key+'"]'+sub+':visible').first();
}
async function anchor(page, origin, item) {
    if (!(await page.locator(sidebar).count())) await page.goto(home,{waitUntil:'domcontentloaded'});
    let link=page.locator(sidebar+' a').filter({hasText:item.label}).first();
    const found=page.locator(sidebar+' a[href="'+item.href.replaceAll('"','\\"')+'"]').first();
    if (await found.count()) link=found;
    const folded=link.locator('xpath=ancestor::details[not(@open)]');
    for (let j=0;j<4 && await folded.count();j++) await folded.first().locator(':scope > summary').click({timeout:2800});
    if (!(await link.isVisible())) {
        const collapsed=link.locator('xpath=ancestor::*[contains(@class,"sidebar-group")][1]').locator('button').first();
        if (await collapsed.count()) await collapsed.click({timeout:1500}).catch(()=>{});
    }
    if (origin) {await mark(link);await picture(page,origin);}
    const timeout=process.env.TOUR_HOME_FIRST ? 6500 : 4500;
    const target=new URL(item.href,base);
    if (target.origin!==base) throw Error('Menyu keçidi lokal tətbiqə aid deyil.');
    if ((await link.getAttribute('target'))==='_blank') {
        [page]=await Promise.all([page.waitForEvent('popup',{timeout:8000}),link.click({timeout})]);
        await page.waitForLoadState('domcontentloaded',{timeout:15000});
    } else {
        await link.click({timeout});
    }
    if (item.key) {
        const group=settingsGroup(item);
        try {
            await page.waitForFunction(({key,group})=>{
                const el=document.querySelector('[data-profile-section-panel="'+key+'"].is-active');
                return el && !el.classList.contains('profile-section-placeholder') &&
                    (!group || el.getAttribute('data-profile-section-sub')===group);
            },{key:item.key,group},{timeout:group?9500:5500});
        } catch(e) {
            const here=new URL(page.url());
            if (!group && !here.pathname.includes('/accounts/profile/') && here.pathname!=='/') return page.locator('main:visible').first();
            throw e;
        }
        return sectionPane(page,item.key,group);
    }
    await page.waitForURL(url=>url.origin===target.origin && url.pathname===target.pathname,{timeout:8000});
    const main=page.locator('main:visible').first();return await main.count()?main:page.locator('body');
}
async function collect(page,dir,role) {
    await page.goto(base+'/preview/'+role,{waitUntil:'domcontentloaded'});
    const menu = await page.locator(sidebar).evaluate(el=>Array.from(el.querySelectorAll('a[href]')).map(a=>{
        const copy=a.cloneNode(true);
        copy.querySelectorAll('.badge,[class*=badge],.sr-only,[aria-hidden=true]').forEach(x=>x.remove());
        return {label:copy.textContent.replace(/\s+/g,' ').trim(), key:a.dataset.section||'',href:a.getAttribute('href')};
    }).filter(a=>a.label && a.href && !a.href.includes('logout')));
    const unique=menu.filter((x,i)=>menu.findIndex(y=>x.href===y.href)===i);
    const manifestFile=path.join(dir,'progress.json');
    const done=fs.existsSync(manifestFile)?read(manifestFile):[];
    for (const [i,item] of unique.entries()) {
        if (done.some(x=>x.href===item.href && x.ok && !x.errors.length && !process.env.TOUR_RECAPTURE)) continue;
        const id=String(i+1).padStart(3,'0');
        const target=path.join(dir,id);
        fs.mkdirSync(target,{recursive:true});
        const row={...item,id,opened:[],errors:[]};
        try {
            if (process.env.TOUR_HOME_FIRST) await page.goto(home,{waitUntil:'domcontentloaded'});
            let pane=await anchor(page,path.join(target,'menu.jpg'),item);
            page=pane.page();
            const subGroup=settingsGroup(item);
            if (subGroup && subGroup!=='overview') {
                row.subGroup=subGroup;
                const crumb=pane.locator('.ems-crumbs [aria-current=page]');
                row.subLabel=(await crumb.innerText()).trim();
                if (!row.subLabel) throw Error('Tənzimləmə qrupunun adı oxunmadı.');
                await crumb.evaluate(el=>el.scrollIntoView({block:'center',behavior:'instant'}));
                const box=await crumb.boundingBox();
                if (!box || box.y<0 || box.y+box.height>frameSize.height) throw Error('Qrupun adı kadrda görünmür.');
                row.subLabelVisible=true;
            }
            if (!(await pane.count())) pane=page.locator('body');
            await page.waitForTimeout(140);
            row.destination=page.url().replace(base,'');row.text=(await pane.innerText({timeout:2500})).replace(/\s+/g,' ').trim().slice(0,280);
            const denied=/^403\b|^500\b|^404\b|server error|server xətası|permission denied|bad gateway/i;
            if (denied.test(row.text)) throw Error(row.text.slice(0,80));
            await picture(page,path.join(target,'open.jpg'));
            const pageUrl=item.key ? new URL(item.href,base).href : page.url();
            const choices=await pane.evaluate(controlsInPanel);
            row.available=choices.map(k=>({label:k.label,tab:k.tab}));
            for(const choice of choices) {
                if(choice.active) {row.opened.push({label:choice.label,frame:'open.jpg',tab:choice.tab,initial:true});continue;}
                try {
                    if (!(await pane.isVisible()) || (item.key && new URL(page.url()).searchParams.get('section')!==item.key)) {
                        await page.goto(pageUrl,{waitUntil:'domcontentloaded'});
                        await pane.waitFor({state:'visible',timeout:3500});
                        await pane.evaluate(controlsInPanel);
                    }
                    let el=pane.locator('[data-tutorial-control="'+choice.id+'"]').first();
                    if (!(await el.isVisible()) || (await el.evaluate(x=>(x.innerText||x.getAttribute('aria-label')||'').trim()).catch(()=>''))==='') {
                        await pane.evaluate(controlsInPanel);
                        el=pane.locator('[data-tutorial-control="'+choice.id+'"]').first();
                    }
                    if (!(await el.isVisible())) throw Error('control no longer visible');
                    await mark(el);
                    const before='step-'+choice.id+'-select.jpg';
                    await picture(page,path.join(target,before));
                    const startAddress=page.url();
                    const beforeView=await page.locator('body').innerText();
                    const selectionBefore=choice.tab ? await el.evaluate(selectedTabState) : null;
                    await el.click({timeout:1800});await page.waitForTimeout(280);
                    if(choice.link && choice.url && choice.url!=='#') {
                        const destination=new URL(choice.url,startAddress);
                        if (destination.origin===base && destination.href!==startAddress && !choice.url.startsWith('#')) {
                            await page.waitForURL(url=>url.pathname===destination.pathname && (!destination.search || url.search===destination.search),{timeout:850}).catch(()=>{});
                        }
                    }
                    const frame='step-'+choice.id+'.jpg';
                    const selectionVerified=selectionBefore===false && await selectionAfterClick(pane,choice);
                    const changed=selectionVerified || beforeView!==await page.locator('body').innerText() || page.url()!==startAddress;
                    await picture(page,path.join(target,frame));
                    row.opened.push({label:choice.label,frame,before,tab:choice.tab,changed,...(selectionVerified?{selectionVerified:true}:{})});
                    if (choice.tab || choice.details) {
                        const nestedRoot=page.locator('[role=dialog]:visible,dialog[open],.modal.show').last();
                        const focus=await nestedRoot.count()?nestedRoot:pane;
                        if(await focus.isVisible()){
                            const additional=await focus.evaluate(controlsInPanel);
                            for(const sub of additional.filter(x=>!choices.some(old=>old.label===x.label) && !x.active && (x.tab || x.details))) {
                                const next=focus.locator('[data-tutorial-control="'+sub.id+'"]').first();
                                if(!await next.isVisible()) continue;
                                try {
                                    await mark(next);await next.click({timeout:1200});await page.waitForTimeout(240);
                                    const child='child-'+choice.id+'-'+sub.id+'.jpg';await picture(page,path.join(target,child));
                                    row.opened.push({label:sub.label,parent:choice.label,frame:child,tab:sub.tab,changed:true});
                                }catch(e){row.errors.push({label:sub.label,parent:choice.label,message:e.message.split('\n')[0]});}
                            }
                        }
                    }
                    if (page.url()!==pageUrl || !(await pane.isVisible()) || await page.locator('dialog[open],.modal.show,[role=dialog]:visible').count()) {
                        await page.goto(pageUrl,{waitUntil:'domcontentloaded'});await pane.waitFor({state:'visible',timeout:5500});
                        await pane.evaluate(controlsInPanel);
                    } else if(choice.tab || choice.details) {
                        await page.goto(pageUrl,{waitUntil:'domcontentloaded'});await pane.waitFor({state:'visible',timeout:5500});
                        await pane.evaluate(controlsInPanel);
                    }
                }catch(error){row.errors.push({label:choice.label,message:String(error.message).split('\n')[0]});}
            }
            row.ok=true;
        }catch(error){if (page.isClosed()) throw error;row.ok=false;row.error=String(error.message).split('\n')[0];await page.goto(home,{waitUntil:'domcontentloaded'}).catch(()=>{});}
        const old=done.findIndex(x=>x.href===item.href);if(old!==-1)done.splice(old,1);
        done.push(row);fs.writeFileSync(manifestFile,JSON.stringify(done));
        console.log(role,id,unique.length,row.ok,row.opened.length,row.errors.length,row.error||'');
    }
}

(async()=>{
    const browser=await launch();
    async function worker(){
        while(roles.length){
            const role=roles.shift();const dir=path.join(output,role);fs.mkdirSync(dir,{recursive:true});
            const c=await browser.newContext({viewport:frameSize,locale:'az-AZ',reducedMotion:'reduce'});
            try {
                await c.route('**/*', route=>{
                    const req=route.request(),url=new URL(req.url());
                    // All writes in the recorded operational lessons use independent disposable fixtures.
                    if (assetIndex[url.pathname] && url.origin===base) {
                        const file=assetIndex[url.pathname];
                        if(!assetCache.has(file)) assetCache.set(file,fs.readFileSync(file));
                        return route.fulfill({body:assetCache.get(file),contentType:mime[path.extname(file)] || 'application/octet-stream'});
                    }
                    if(url.origin!==base || !['GET','HEAD','OPTIONS'].includes(req.method())) return route.abort();
                    return route.continue();
                });
                const page=await c.newPage();page.setDefaultTimeout(4300);page.setDefaultNavigationTimeout(18000);
                page.on('dialog',dialog=>dialog.dismiss());
                await collect(page,dir,role);
            }catch(e){console.error(role,e.message);}finally{await c.close();}
        }
    }
    try{await Promise.all(Array.from({length:Math.min(Number(process.env.TOUR_WORKERS||5),roles.length)},worker));}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
