const assert = require('node:assert/strict');
const {readFileSync, mkdirSync} = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

(async () => {
  const css = readFileSync('skills/swarm/assets/ui/swarm-hq-host.css', 'utf8');
  const entry = readFileSync('skills/swarm/assets/ui/swarm-projects-bootstrap.mjs', 'utf8');
  const start = entry.indexOf('function theme(ctx){');
  const end = entry.indexOf('app.onhostcontextchanged=theme;', start);
  assert.ok(start >= 0 && end > start, 'existing host context bridge');
  const sdk = process.env.SWARM_HQ_SDK_BUNDLE;
  assert.ok(sdk, 'SWARM_HQ_SDK_BUNDLE must point to the retained official SDK');
  const sdkUrl = 'data:text/javascript;base64,' + readFileSync(sdk).toString('base64');
  const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page = await browser.newPage({viewport:{width:1000,height:700}});
    await page.setContent(`<style>${css}</style><div class="workspace"><aside>Navigation</aside><main id="project-page"><article class="ticket-workspace"><h1>Ticket details</h1><span class="ticket-workspace-status">Unknown</span><div class="ticket-description"><p>Project information</p></div><div class="ticket-composer"><textarea placeholder="Write an update"></textarea><button>Post</button></div></article><div class="velocity"><div class="velocity-header"><h2>Velocity</h2></div><div class="velocity-legend"><span>Current</span></div><div class="velocity-tooltip">Details</div></div></main></div>`);
    await page.emulateMedia({colorScheme:'light'});
    assert.equal(await page.locator('html').evaluate(e=>getComputedStyle(e).backgroundColor), 'rgb(255, 255, 255)', 'no-host fallback follows light system preference');
    await page.evaluate(async ({sdkUrl,themeSource}) => {
      const sdk = await import(sdkUrl);
      window.hostTheme = new Function('applyDocumentTheme','applyHostStyleVariables','root',themeSource+';return theme')(sdk.applyDocumentTheme,sdk.applyHostStyleVariables,document.documentElement);
    }, {sdkUrl,themeSource:entry.slice(start,end)});
    const samples=[];
    for (const [theme,bg,panel,fg,muted,border] of [['dark','#1b1b1b','#292929','#fafafa','#bbbbbb','#4a4a4a'],['light','#f6f6f6','#ffffff','#161616','#555555','#cccccc'],['dark','#101010','#202020','#eeeeee','#aaaaaa','#444444']]) {
      await page.evaluate(({theme,bg,panel,fg,muted,border}) => window.hostTheme({theme,styles:{variables:{'--color-background-primary':bg,'--color-background-secondary':panel,'--color-text-primary':fg,'--color-text-secondary':muted,'--color-border-primary':border}}}),{theme,bg,panel,fg,muted,border});
      const sample=await page.evaluate(()=>{const cs=s=>getComputedStyle(document.querySelector(s));return {root:cs('html').backgroundColor,ticket:cs('#project-page').backgroundColor,velocity:cs('.velocity').backgroundColor,textarea:cs('textarea').backgroundColor,text:cs('#project-page').color,border:cs('textarea').borderTopColor}});
      samples.push({theme,...sample});
      if(process.env.THEME_EVIDENCE){mkdirSync(process.env.THEME_EVIDENCE,{recursive:true});await page.screenshot({path:path.join(process.env.THEME_EVIDENCE,`after-${theme}-${samples.length}.png`)});}
      assert.equal(sample.ticket,sample.root,`${theme} ticket uses host primary`);
      assert.equal(sample.velocity,sample.textarea,`${theme} velocity uses host secondary`);
      assert.equal(sample.text,theme==='light'?'rgb(22, 22, 22)':theme==='dark'&&samples.length===1?'rgb(250, 250, 250)':'rgb(238, 238, 238)',`${theme} host text`);
      assert.equal(sample.border,theme==='light'?'rgb(204, 204, 204)':samples.length===1?'rgb(74, 74, 74)':'rgb(68, 68, 68)',`${theme} host border`);
      const contrast = await page.locator('.ticket-workspace-status').evaluate(e=>{const c=document.createElement('canvas');c.width=c.height=1;const x=c.getContext('2d');function rgb(color){x.clearRect(0,0,1,1);x.fillStyle=color;x.fillRect(0,0,1,1);return [...x.getImageData(0,0,1,1).data].slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4})}function lum(a){return .2126*a[0]+.7152*a[1]+.0722*a[2]}const a=lum(rgb(getComputedStyle(e).color)),b=lum(rgb(getComputedStyle(document.documentElement).backgroundColor));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
      assert.ok(contrast>=4.5,`${theme} status text contrast ${contrast}`);
    }
    await page.evaluate(()=>window.hostTheme({safeAreaInsets:{top:8}}));
    assert.equal(await page.locator('#project-page').evaluate(e=>getComputedStyle(e).backgroundColor),samples[2].root,'partial host context retains theme');
    console.log('PASS actual SDK theme helpers and existing host-context bridge, light/dark/updates/fallback',JSON.stringify(samples));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
