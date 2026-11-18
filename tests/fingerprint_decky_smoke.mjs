// Execute the real ES module against deterministic Steam, DOM, and timer stand-ins.
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url'; import {resolve} from 'node:path';
let tick, active=false, successes=0, clears=0, calls=0, connections=0, pending=[], timers=new Map(), next=0, toggle, delayCancel=false, releaseCancel, reduced=false, animations=0, cancels=0, animationLog=[];
const settings=new Map([['boiler.fingerprint.enabled','0']]); globalThis.localStorage={getItem:k=>settings.has(k)?settings.get(k):null,setItem:(k,v)=>settings.set(k,v)};
globalThis.setInterval=fn=>(tick=fn,1); globalThis.clearInterval=()=>{};
globalThis.setTimeout=(fn,ms)=>{const id=++next;timers.set(id,{fn,ms});return id};globalThis.clearTimeout=id=>timers.delete(id);
globalThis.SP_REACT={createElement:(type,props,...children)=>{if(type==='Toggle')toggle=props.onChange;return {type,props,children}},useState:v=>[v,()=>{}],useEffect:()=>{}};globalThis.DFL={ToggleField:'Toggle'};
globalThis.window={__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit:{connect:()=>{connections++;return {callable:method=>method==='verify'?()=>{calls++;return new Promise(r=>pending.push(r))}:method==='cancel'?()=>delayCancel?new Promise(r=>{releaseCancel=r}):Promise.resolve({}):async()=>({})}}},securitystore:{IsLockScreenActive:()=>active,GetActiveLockScreenProps:()=>({onSuccess:()=>successes++}),SetActiveLockScreenProps:v=>{if(v===null)clears++}}};
const module=await import(pathToFileURL(resolve(process.argv[2])).href);assert.equal(connections,0);assert.equal(calls,0);assert.equal(tick,undefined);
const keypad={marker:'unchanged'}, focus={};const body={children:[keypad],appendChild(n){this.children.push(n);n.parentNode=this},removeChild(n){this.children.splice(this.children.indexOf(n),1);n.parentNode=null},contains(n){return this.children.includes(n)}};
const doc={body,activeElement:focus,defaultView:{innerWidth:1280,innerHeight:800,matchMedia:()=>({matches:reduced}),getComputedStyle:()=>({borderTopColor:'rgb(99, 111, 122)',color:'white'})},createElementNS(ns,tag){return {tag,style:{},children:[],setAttribute(k,v){this[k]=v},appendChild(c){this.children.push(c)},animate(frames,options){animations++;animationLog.push({tag,frames,options});return {cancel(){cancels++}}}}}};
let layout={indicators:{left:250,right:476,top:505,bottom:542},digit:{left:250,right:274,top:505,bottom:529},blocked:[{left:700,right:1200,top:100,bottom:650},{left:700,right:1200,top:700,bottom:750}],color:'rgb(99, 111, 122)'};
const renderer=module.createFingerprintStatusRenderer(()=>doc,()=>layout);
for(const state of ['waiting','retrying','unavailable']){assert.equal(renderer.render(state),true);const n=body.children[1];assert.equal(n.style.color,layout.color);assert.equal(n.style.left,'333px');assert.equal(n.style.top,'572px');assert.equal(n.style.pointerEvents,'none');assert.equal(doc.activeElement,focus);assert.equal(body.children[0],keypad)}
assert.equal(renderer.render('no-match'),true);assert.equal(body.children[1].style.color,'#cf6b6b');assert.equal(animations,1);renderer.render('no-match');assert.equal(animations,1);
assert.equal(animationLog[0].options.duration,340);assert.ok(animationLog[0].frames.some(f=>f.transform==='translateX(-5px)'));
renderer.render('success');assert.equal(body.children[1].style.color,'#78b985');assert.equal(cancels,1);assert.equal(animationLog[1].tag,'circle');assert.equal(animationLog[1].options.duration,600);assert.equal(animationLog[1].options.iterations,Infinity);assert.equal(animationLog[1].frames[1].opacity,.22);assert.equal(successes,0);assert.equal(clears,0);assert.equal(calls,0);
reduced=true;renderer.render('no-match');renderer.render('success');assert.equal(animations,2);reduced=false;renderer.render('no-match');const beforeRemove=cancels;renderer.remove();assert.equal(cancels,beforeRemove+1);assert.deepEqual(body.children,[keypad]);
const original=layout;layout={...original,blocked:[{left:300,right:400,top:570,bottom:650}]};assert.equal(renderer.render('waiting'),false);layout={...original,blocked:[{left:300,right:400,top:600,bottom:750}]};assert.equal(renderer.render('waiting'),false);layout={...original,digit:null};assert.equal(renderer.render('waiting'),false);layout=original;
layout={...original,blocked:[{left:394,right:450,top:570,bottom:650}]};assert.equal(renderer.render('waiting'),true);assert.equal(renderer.render('no-match'),false);layout=original;
let footerRects=[], screenPresent=true, screenOpacity='1', parentOpacity='1', clock=0;
Date.now=()=>clock;
const parent={nodeType:1,parentElement:null};const screen={nodeType:1,isConnected:true,ownerDocument:doc,parentElement:parent,getBoundingClientRect:()=>({width:1000,height:700})};
const originalComputed=doc.defaultView.getComputedStyle;doc.defaultView.getComputedStyle=el=>el===screen?{display:'block',visibility:'visible',opacity:screenOpacity}:el===parent?{display:'block',visibility:'visible',opacity:parentOpacity}:originalComputed(el);
const rect=r=>({getBoundingClientRect:()=>r,closest:()=>screenPresent?screen:null}); doc.querySelector=sel=>sel==='.indicators'?rect(layout.indicators):sel==='.digit'?rect(layout.digit):null;doc.querySelectorAll=sel=>sel==='.key'? [rect(layout.blocked[0])]:sel==='.footer'?footerRects.map(rect):[];
DFL.findSP=()=>({document:doc});DFL.findModule=predicate=>{const c={Container:'container',Indicators:'indicators',DigitIndicator:'digit',NumericButtonInput:'key',ForgotPINButton:'footer'};return predicate(c)?c:null};
const plugin=module.default();plugin.content.type();const flush=async()=>{await new Promise(r=>setImmediate(r))};const finish=async r=>{pending.shift()(r);await flush()};const fire=async ms=>{const [id,t]=[...timers].find(([,t])=>t.ms===ms);timers.delete(id);t.fn();await flush()};
active=true;tick();await flush();assert.equal(calls,0);delayCancel=true;toggle(true);await flush();assert.equal(calls,0);delayCancel=false;releaseCancel({});await flush();assert.equal(calls,1);
assert.equal(body.children.length,2); // Game mode: keypad present, footer absent.
footerRects=[{left:300,right:400,top:570,bottom:650}];tick();assert.deepEqual(body.children,[keypad]);
footerRects=[];tick();assert.equal(body.children.length,2);
await finish({result:'unavailable',reason:'timeout'});await fire(500);assert.equal(calls,2);await finish({result:'unavailable',reason:'no-match'});assert.equal(body.children[1].style.color,'#cf6b6b');await fire(1050);assert.equal(calls,3);assert.equal(body.children[1].style.color,layout.color);
await finish({result:'match'});assert.equal(successes,1);assert.equal(clears,1);assert.equal(body.children[1].style.color,'#78b985');assert.ok([...timers.values()].some(t=>t.ms===50));active=false;tick();assert.equal(body.children.length,2);await fire(50);assert.equal(body.children.length,2);screenOpacity='.5';parentOpacity='.5';await fire(50);assert.equal(body.children[1].style.opacity,'0.25');parentOpacity='1';screenOpacity='0';await fire(50);assert.deepEqual(body.children,[keypad]);screenOpacity='1';
active=true;tick();await flush();assert.equal(calls,4);await finish({result:'unavailable',reason:'error'});assert.equal(timers.size,0);active=false;tick();active=true;tick();await flush();assert.equal(calls,5);toggle(false);assert.deepEqual(body.children,[keypad]);await finish({result:'match'});assert.equal(successes,1);
toggle(true);await flush();assert.equal(calls,6);active=false;tick();await finish({result:'match'});assert.equal(successes,1);active=true;tick();await flush();assert.equal(calls,7);active=false;tick();active=true;tick();assert.equal(calls,7);await finish({result:'match'});await fire(500);assert.equal(calls,8);
await finish({result:'match'});assert.equal(successes,2);assert.equal(body.children[1].style.color,'#78b985');active=false;tick();active=true;tick();assert.deepEqual(body.children,[keypad]);await flush();assert.equal(calls,9);assert.equal(body.children[1].style.color,layout.color);assert.ok(![...timers.values()].some(t=>t.ms===50));
await finish({result:'unavailable',reason:'no-match'});const beforeUnload=cancels;plugin.onDismount();assert.equal(cancels,beforeUnload+1);assert.deepEqual(body.children,[keypad]);assert.equal(successes,2);

// Success with no capturable DOM cleans up immediately without delaying unlock.
active=false;screenPresent=false;const plugin2=module.default();plugin2.content.type();toggle(true);active=true;tick();await flush();
await finish({result:'match'});assert.equal(successes,3);assert.deepEqual(body.children,[keypad]);assert.equal(timers.size,0);plugin2.onDismount();
// A stale mounted DOM cannot retain the decoration forever.
active=false;screenPresent=true;clock=0;const plugin3=module.default();plugin3.content.type();active=true;tick();await flush();await finish({result:'match'});
assert.equal(successes,4);assert.equal(body.children.length,2);active=false;tick();clock=10001;await fire(50);assert.deepEqual(body.children,[keypad]);plugin3.onDismount();

// Detachment, disabling and unloading all remove an active success decoration.
active=false;clock=0;const plugin4=module.default();plugin4.content.type();active=true;tick();await flush();await finish({result:'match'});
assert.equal(body.children.length,2);screen.isConnected=false;await fire(50);assert.deepEqual(body.children,[keypad]);screen.isConnected=true;
active=false;tick();active=true;tick();await flush();await finish({result:'match'});toggle(false);assert.deepEqual(body.children,[keypad]);assert.equal(timers.size,0);
toggle(true);await flush();await finish({result:'match'});assert.equal(body.children.length,2);plugin4.onDismount();assert.deepEqual(body.children,[keypad]);assert.equal(timers.size,0);

// Unknown device failures retry only twice in a lock session, with bounded delays.
active=false;const plugin5=module.default();plugin5.content.type();active=true;tick();await flush();
await finish({result:'unavailable',reason:'device-error'});assert.ok([...timers.values()].some(t=>t.ms===1000));await fire(1000);
await finish({result:'unavailable',reason:'device-error'});assert.ok([...timers.values()].some(t=>t.ms===3000));await fire(3000);
await finish({result:'unavailable',reason:'device-error'});assert.equal(timers.size,0);const afterExhaustion=calls;
// Toggling cannot reset the budget within the same lock screen.
toggle(false);toggle(true);await flush();await finish({result:'unavailable',reason:'device-error'});assert.equal(timers.size,0);assert.equal(calls,afterExhaustion+1);
// A new lock restores the budget; disable cancels an outstanding delayed retry.
active=false;tick();active=true;tick();await flush();await finish({result:'unavailable',reason:'device-error'});assert.ok([...timers.values()].some(t=>t.ms===1000));
toggle(false);assert.equal(timers.size,0);toggle(true);await flush();await finish({result:'unavailable',reason:'device-error'});assert.ok([...timers.values()].some(t=>t.ms===3000));
// Unlock and relock cancel an old timer and start a fresh session.
active=false;tick();assert.equal(timers.size,0);active=true;tick();await flush();await finish({result:'unavailable',reason:'device-error'});await fire(1000);await finish({result:'match'});
assert.equal(successes,8);active=false;tick();screen.isConnected=false;await fire(50);screen.isConnected=true;
// Unload cancels the retry and cannot trigger subsequent attempts.
active=true;tick();await flush();await finish({result:'unavailable',reason:'device-error'});assert.ok([...timers.values()].some(t=>t.ms===1000));plugin5.onDismount();assert.equal(timers.size,0);

// The SP window's Steam language selects one language only, with English fallback.
for(const [query,expected] of [['schinese','zh'],['tchinese','zh'],['zh-CN','zh'],['zh-TW','zh'],['zh-Hant','zh'],['en-US','en'],['koreana','en'],['','en']]) assert.equal(module.fingerprintLanguage(query),expected);
active=false;let panelEffect,statusRequests=0;DFL.findSP=()=>({document:doc,location:{search:'?LANGUAGE=schinese'}});
window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit.connect=()=>({callable:method=>method==='fingerprints'?async()=>{statusRequests++;return {result:'available',count:2,limit:6}}:async()=>({})});
const chinesePlugin=module.default();SP_REACT.useEffect=fn=>{panelEffect=fn};
const chinesePanel=JSON.stringify(chinesePlugin.content.type());assert.ok(chinesePanel.includes('指纹解锁'));assert.ok(chinesePanel.includes('添加指纹'));assert.ok(!chinesePanel.includes('Fingerprint unlock'));assert.ok(!chinesePanel.includes('Test lock'));assert.ok(!chinesePanel.includes('Refresh'));
const dispose=panelEffect();await flush();assert.equal(statusRequests,1);dispose();chinesePlugin.onDismount();
DFL.findSP=()=>({document:doc,location:{search:'?LANGUAGE=english'}});SP_REACT.useEffect=()=>{};const englishPlugin=module.default();const englishPanel=JSON.stringify(englishPlugin.content.type());assert.ok(englishPanel.includes('Fingerprint unlock'));assert.ok(englishPanel.includes('Add fingerprint'));assert.ok(!englishPanel.includes('指纹'));assert.ok(!englishPanel.includes('Test lock'));assert.ok(!englishPanel.includes('Refresh'));englishPlugin.onDismount();

// Observed SharedJSContext document language takes precedence over navigator and SP URL.
globalThis.document={documentElement:{lang:'zh-cn'}};Object.defineProperty(globalThis,'navigator',{value:{language:'en-US'},configurable:true});
DFL.findSP=()=>({document:doc,location:{search:'?LANGUAGE=english'}});const documentLanguagePlugin=module.default();assert.ok(JSON.stringify(documentLanguagePlugin.content.type()).includes('指纹解锁'));documentLanguagePlugin.onDismount();
globalThis.document.documentElement.lang='';DFL.findSP=()=>({document:doc,location:{search:''}});Object.defineProperty(globalThis,'navigator',{value:{language:'zh-TW'},configurable:true});const navigatorLanguagePlugin=module.default();assert.ok(JSON.stringify(navigatorLanguagePlugin.content.type()).includes('指纹解锁'));navigatorLanguagePlugin.onDismount();

// Opening the panel while locked does not issue a status query.
active=true;SP_REACT.useEffect=fn=>{panelEffect=fn};const lockedPanel=module.default();lockedPanel.content.type();const disposeLocked=panelEffect();await flush();assert.equal(statusRequests,1);disposeLocked();lockedPanel.onDismount();active=false;

// First use defaults on; explicit disable survives remount and invalid settings fail closed.
let toggleProps;const savedCreate=SP_REACT.createElement;SP_REACT.createElement=(type,props,...children)=>{if(type==='Toggle')toggleProps=props;return savedCreate(type,props,...children)};
let firstVerify=0;window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit.connect=()=>({callable:method=>method==='verify'?async()=>{firstVerify++;return {result:'unavailable',reason:'error'}}:async()=>({})});
settings.delete('boiler.fingerprint.enabled');const firstPlugin=module.default();firstPlugin.content.type();assert.equal(toggleProps.checked,true);active=true;tick();await flush();assert.equal(firstVerify,1);active=false;tick();toggleProps.onChange(false);assert.equal(settings.get('boiler.fingerprint.enabled'),'0');firstPlugin.onDismount();
const reloadedPlugin=module.default();reloadedPlugin.content.type();assert.equal(toggleProps.checked,false);reloadedPlugin.onDismount();
for(const value of ['invalid','', 'true']){settings.set('boiler.fingerprint.enabled',value);const badPlugin=module.default();badPlugin.content.type();assert.equal(toggleProps.checked,false);badPlugin.onDismount()}
settings.set('boiler.fingerprint.enabled','1');const enabledPlugin=module.default();enabledPlugin.content.type();assert.equal(toggleProps.checked,true);enabledPlugin.onDismount();
const savedStorage=globalThis.localStorage;globalThis.localStorage={getItem(){throw Error('denied')},setItem(){throw Error('denied')}};const deniedPlugin=module.default();deniedPlugin.content.type();assert.equal(toggleProps.checked,false);deniedPlugin.onDismount();
globalThis.localStorage={getItem(){return null},setItem(){throw Error('denied')}};const writeDeniedPlugin=module.default();writeDeniedPlugin.content.type();assert.equal(toggleProps.checked,true);toggleProps.onChange(false);writeDeniedPlugin.content.type();assert.equal(toggleProps.checked,false);writeDeniedPlugin.onDismount();globalThis.localStorage=savedStorage;SP_REACT.createElement=savedCreate;

assert.match(module.enrollmentPrompt({result:'sampling',samples:3,total:8,guided:true,scan_type:'press'},'en'), /3\/8.*center/);
assert.match(module.enrollmentPrompt({result:'sampling',samples:4,total:8,guided:true,scan_type:'press'},'en'), /4\/8.*same finger/);
assert.match(module.enrollmentPrompt({result:'sampling',samples:4,total:8,guided:true,scan_type:'press'},'zh'), /4\/8.*同一根手指/);
assert.match(module.enrollmentPrompt({result:'identifying'},'en'), /authentication.*unenrolled/);
assert.match(module.enrollmentPrompt({result:'retry',samples:4,total:8,guided:true,scan_type:'press'},'zh'), /4\/8.*再按一次/);
assert.match(module.enrollmentPrompt({result:'unavailable',reason:'retry-timeout'},'zh'), /录入已结束/);
assert.match(module.enrollmentPrompt({result:'sampling',samples:1,total:3,guided:false,scan_type:'press'},'zh'), /1\/3.*轻触/);
assert.match(module.enrollmentPrompt({result:'sampling',samples:1,total:3,guided:false,scan_type:'swipe'},'zh'), /1\/3.*划过/);
assert.match(module.enrollmentPrompt({result:'retry',samples:1,total:3,guided:false,scan_type:'swipe'},'zh'), /1\/3.*划过/);
assert.equal(module.enrollmentPrompt({result:'sampling',samples:0,total:null,guided:false,scan_type:'unknown'},'zh'), '请再次采集同一根手指。');
assert.equal(module.enrollmentPrompt({result:'retry',samples:0,total:null,guided:false,scan_type:'unknown'},'zh'), '这次采样未通过，请再次采集同一根手指。');
// Exercise the list, the single add action, the limit, and cancellation on lock.
{
  let state = [], cursor = 0, lockActive = false, finishCancel, settleEnroll, verifyCount = 0, cancelCount = 0;
  let effect, count = 0;
  const oldReact = globalThis.SP_REACT, oldDFL = globalThis.DFL, oldWindow = globalThis.window;
  globalThis.SP_REACT = {createElement:(type,props,...children)=>({type,props,children}),
    useState:initial=>{const i=cursor++; if (!(i in state)) state[i]=initial; return [state[i], value=>{state[i]=value}];}, useEffect:fn=>{effect=fn}};
  globalThis.DFL = {PanelSection:'section', PanelSectionRow:'row', Field:'field', ToggleField:'toggle', ButtonItem:'button'};
  globalThis.localStorage = {getItem:()=> '1', setItem:()=>{}};
  globalThis.window = {__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit:{connect:()=>({callable:method=>
    method==='fingerprints'?async()=>({result:'available',count,limit:6}):
    method==='enroll'?(...args)=>{assert.deepEqual(args,[]);return new Promise(r=>{settleEnroll=r})}:
    method==='enroll_progress'?async()=>({result:'identifying'}):
    method==='cancel'?()=>{cancelCount++;return new Promise(r=>{finishCancel=r})}:
    method==='verify'?async()=>{verifyCount++;return {result:'unavailable'}}:async()=>({})})},
    securitystore:{IsLockScreenActive:()=>lockActive}};
  const instance=module.default();
  const render=()=>{cursor=0;return instance.content.type()};
  const nodes=(node,type)=>!node || typeof node!=='object'?[]:[...(node.type===type?[node]:[]),...(node.children||[]).flatMap(child=>nodes(child,type))];
  render(); effect(); await flush();
  assert.equal(nodes(render(),'field').length,0);
  assert.equal(nodes(render(),'button').length,1);
  count=6; effect(); await flush();
  assert.equal(nodes(render(),'field').length,6);
  assert.equal(nodes(render(),'button')[0].props.disabled,true);
  count=2; effect(); await flush();
  assert.equal(nodes(render(),'field').length,2);
  nodes(render(),'button')[0].props.onClick(); await flush();
  lockActive=true; tick(); await flush(); assert.equal(cancelCount,1); assert.equal(verifyCount,0);
  finishCancel({}); await flush(); assert.equal(verifyCount,0);
  settleEnroll({result:'cancelled'}); await flush(); assert.equal(verifyCount,1); instance.onDismount();
  globalThis.SP_REACT=oldReact;globalThis.DFL=oldDFL;globalThis.window=oldWindow;
}


// Preserve automatic package recovery and only offer repair when the backend permits it.
{
  let state = [], cursor = 0, effect, inventoryCalls = 0, repairCalls = 0, locked = false;
  let status = {available:false, busy:true, repairable:true};
  let inventory = {result:'unavailable',reason:'list'};
  const oldReact = globalThis.SP_REACT, oldDFL = globalThis.DFL, oldWindow = globalThis.window;
  globalThis.SP_REACT = {createElement:(type,props,...children)=>({type,props,children}),
    useState:initial=>{const i=cursor++; if (!(i in state)) state[i]=initial; return [state[i], value=>{state[i]=value}];}, useEffect:fn=>{effect=fn}};
  globalThis.DFL = {PanelSection:'section', PanelSectionRow:'row', Field:'field', ToggleField:'toggle', ButtonItem:'button', findSP:()=>({location:{search:'?LANGUAGE=schinese'}})};
  globalThis.window = {__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit:{connect:()=>({callable:method=>
    method==='fingerprints'?async()=>{inventoryCalls++; return inventory}:
    method==='status'?async()=>status:
    method==='repair'?async()=>{repairCalls++;return {ok:true}}:async()=>({})})},
    securitystore:{IsLockScreenActive:()=>locked}};
  const instance=module.default();
  const render=()=>{cursor=0;return instance.content.type()};
  const nodes=(node,type)=>!node || typeof node!=='object'?[]:[...(node.type===type?[node]:[]),...(node.children||[]).flatMap(child=>nodes(child,type))];
  const repair=()=>nodes(render(),'button').find(node=>node.children.includes('重新安装指纹支持'));
  render(); const dispose=effect(); await flush();
  assert.equal(inventoryCalls,1); assert.equal(repair(),undefined);
  status={available:false,repairable:true}; await fire(2000);
  assert.ok(repair());
  locked=true; await repair().props.onClick(); assert.equal(repairCalls,0);
  locked=false; await repair().props.onClick(); assert.equal(repairCalls,1);
  status={available:true,enrolled:true,repairable:false}; inventory={result:'available',count:2,limit:6};
  await fire(2000); assert.equal(inventoryCalls,2); assert.equal(nodes(render(),'field').length,2); assert.equal(repair(),undefined);
  dispose(); instance.onDismount();
  globalThis.SP_REACT=oldReact;globalThis.DFL=oldDFL;globalThis.window=oldWindow;
}
// A Boiler-managed reader cannot expose the stock-package repair action.
{
  let state=[], cursor=0, effect;
  const oldReact=globalThis.SP_REACT, oldDFL=globalThis.DFL, oldWindow=globalThis.window;
  globalThis.SP_REACT={createElement:(type,props,...children)=>({type,props,children}),useState:initial=>{const i=cursor++;if(!(i in state))state[i]=initial;return [state[i],v=>{state[i]=v}]},useEffect:fn=>{effect=fn}};
  globalThis.DFL={PanelSection:'section',PanelSectionRow:'row',Field:'field',ToggleField:'toggle',ButtonItem:'button',findSP:()=>({location:{search:'?LANGUAGE=schinese'}})};
  globalThis.window={__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit:{connect:()=>({callable:method=>method==='fingerprints'?async()=>({result:'available',count:3,limit:6}):method==='status'?async()=>({available:true,repairable:false}):async()=>({})})},securitystore:{IsLockScreenActive:()=>false}};
  const instance=module.default(), render=()=>{cursor=0;return instance.content.type()};
  render(); const dispose=effect(); await flush(); assert.ok(!JSON.stringify(render()).includes('重新安装指纹支持'));
  dispose();instance.onDismount();globalThis.SP_REACT=oldReact;globalThis.DFL=oldDFL;globalThis.window=oldWindow;
}
