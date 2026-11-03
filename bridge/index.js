// Derived from podothecat/decky-fingerprint-unlock, MIT; see upstream/LICENSE.
// Decoration only; callers provide geometry and color, never PIN state.
let rendererId = 0;
export function createFingerprintStatusRenderer(getDocument, getLayout) {
  let node = null, halo = null, documentOwner = null, animation = null, lastState = null;
  const states = ['waiting', 'retrying', 'no-match', 'success', 'unavailable'];
  function cancelAnimation() { if (animation) { animation.cancel(); animation = null; } }
  function remove() {
    cancelAnimation();
    try { if (node && node.parentNode) node.parentNode.removeChild(node); } catch (_) {}
    node = null; halo = null; documentOwner = null; lastState = null;
  }
  function render(state) {
    try {
      const doc = getDocument(), layout = doc && getLayout(doc), view = doc?.defaultView;
      const i = layout?.indicators, dot = layout?.digit, blocked = layout?.blocked;
      const valid = r => r && ['top','bottom','left','right'].every(k => Number.isFinite(r[k])) && r.right > r.left && r.bottom > r.top;
      if (!states.includes(state) || !doc?.body || !view || !valid(i) || !valid(dot) || !Array.isArray(blocked) || !blocked.length || !blocked.every(valid) ||
          !Number.isFinite(view.innerWidth) || !Number.isFinite(view.innerHeight)) { remove(); return false; }
      const size = Math.max(56, Math.min(64, (dot.right - dot.left) * 2.5));
      const x = (i.left + i.right - size) / 2, y = i.bottom + 30;
      const motionMargin = state === 'no-match' ? 5 : 0;
      const box = {left:x-motionMargin, top:y, right:x+size+motionMargin, bottom:y+size};
      if (box.left < 0 || y < 0 || box.right > view.innerWidth || box.bottom > view.innerHeight ||
          blocked.some(r => box.left < r.right && box.right > r.left && box.top < r.bottom && box.bottom > r.top)) { remove(); return false; }
      if (node && (documentOwner !== doc || !doc.body.contains(node))) remove();
      if (!node) {
        node = doc.createElementNS('http://www.w3.org/2000/svg', 'svg'); documentOwner = doc;
        node.setAttribute('viewBox','0 0 64 64'); node.setAttribute('aria-hidden','true');
        Object.assign(node.style, {position:'fixed', zIndex:'7000', pointerEvents:'none', fill:'none', stroke:'currentColor', strokeWidth:'2.8', strokeLinecap:'round', strokeLinejoin:'round'});
        const id = `boiler-fingerprint-glow-${++rendererId}`;
        const defs = doc.createElementNS('http://www.w3.org/2000/svg', 'defs');
        const gradient = doc.createElementNS('http://www.w3.org/2000/svg', 'radialGradient');
        gradient.setAttribute('id', id);
        for (const [offset, opacity] of [['0%', '1'], ['100%', '0']]) {
          const stop = doc.createElementNS('http://www.w3.org/2000/svg', 'stop');
          stop.setAttribute('offset', offset); stop.setAttribute('stop-color', '#78b985'); stop.setAttribute('stop-opacity', opacity); gradient.appendChild(stop);
        }
        defs.appendChild(gradient); node.appendChild(defs);
        halo = doc.createElementNS('http://www.w3.org/2000/svg', 'circle');
        halo.setAttribute('cx','32'); halo.setAttribute('cy','32'); halo.setAttribute('r','25');
        halo.setAttribute('fill', `url(#${id})`); halo.setAttribute('stroke','none');
        Object.assign(halo.style, {opacity:'0', transformOrigin:'32px 32px'}); node.appendChild(halo);
        for (const d of ['M13 31c0-11 8-19 19-19s19 8 19 19', 'M19 32c0-8 5-14 13-14s13 6 13 14c0 9 1 15 4 20', 'M25 32c0-5 3-8 7-8s7 3 7 8c0 12 1 20 4 25', 'M32 30c1 0 1 2 1 4 0 12 0 20 3 25', 'M19 38c0 7-1 12-4 17', 'M25 38c0 10-1 15-3 19', 'M51 37c0 4 1 7 2 10']) {
          const path = doc.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', d); node.appendChild(path);
        }
        doc.body.appendChild(node);
      }
      node.style.left = `${x}px`; node.style.top = `${y}px`; node.style.width = `${size}px`; node.style.height = `${size}px`;
      node.style.color = state === 'no-match' ? '#cf6b6b' : state === 'success' ? '#78b985' : (layout.color || '#68747e');
      if (state !== lastState) {
        cancelAnimation();
        const reduce = view.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        if (!reduce && state === 'no-match' && typeof node.animate === 'function')
          animation = node.animate([{transform:'translateX(0)'},{transform:'translateX(-5px)'},{transform:'translateX(5px)'},{transform:'translateX(-2px)'},{transform:'translateX(0)'}], {duration:340, easing:'ease-out'});
        if (!reduce && state === 'success' && typeof halo.animate === 'function')
          animation = halo.animate([{opacity:0,transform:'scale(.7)'},{opacity:.22,transform:'scale(1)'},{opacity:0,transform:'scale(1.25)'}], {duration:200,easing:'ease-out'});
        lastState = state;
      }
      return true;
    } catch (_) { remove(); return false; }
  }
  return {render, remove};
}

export default () => {
const internal = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
let api;
try { api = internal.connect(2, 'Boiler Fingerprint Unlock'); }
catch (_) { api = internal.connect(1, 'Boiler Fingerprint Unlock'); }
const backend = { verify: api.callable('verify'), cancel: api.callable('cancel'), status: api.callable('status') };
const key = 'boiler.fingerprint.enabled';
const enabled = () => { try { return localStorage.getItem(key) === '1'; } catch { return false; } };
const store = () => window.securitystore;
const locked = () => { try { return !!store()?.IsLockScreenActive(); } catch { return false; } };
let generation = 0, previous = false, timer, retryTimer, inFlight = false, mounted = true;
let cancelBarrier = Promise.resolve(), visualState = null, successTimer;
const visual = createFingerprintStatusRenderer(
  () => { try { return DFL.findSP()?.document || null; } catch (_) { return null; } },
  doc => {
    try {
      const classes = DFL.findModule(m => m && typeof m === 'object' &&
        ['Container','Indicators','DigitIndicator','NumericButtonInput','ForgotPINButton'].every(k => typeof m[k] === 'string'));
      if (!classes) return null;
      const indicators = doc.querySelector('.' + classes.Indicators);
      const digit = doc.querySelector('.' + classes.DigitIndicator);
      const keypad = [...doc.querySelectorAll('.' + classes.NumericButtonInput)];
      const footer = [...doc.querySelectorAll('.' + classes.ForgotPINButton)];
      if (!indicators || !digit || !keypad.length) return null;
      const computed = doc.defaultView.getComputedStyle(digit);
      const usable = c => c && c !== 'transparent' && c !== 'rgba(0, 0, 0, 0)';
      const footerRects = footer.map(el => el.getBoundingClientRect()).filter(r =>
        ['top','bottom','left','right'].every(k => Number.isFinite(r[k])) && r.right > r.left && r.bottom > r.top);
      return {indicators:indicators.getBoundingClientRect(), digit:digit.getBoundingClientRect(),
        blocked:[...keypad.map(el => el.getBoundingClientRect()), ...footerRects],
        color:usable(computed.borderTopColor) ? computed.borderTopColor : usable(computed.color) ? computed.color : '#68747e'};
    } catch (_) { return null; }
  });
function show(state) { visualState = state; visual.render(state); }
function abort(preserveSuccess = false) {
  generation++; clearTimeout(retryTimer); retryTimer = undefined;
  if (!preserveSuccess) { clearTimeout(successTimer); successTimer = undefined; visualState = null; visual.remove(); }
  cancelBarrier = cancelBarrier.then(() => backend.cancel()).catch(() => {});
}
function schedule(current, delay = 500) {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(() => { retryTimer = undefined; if (current === generation && mounted && enabled() && locked()) attempt(); }, delay);
}
async function attempt() {
  const current = generation;
  if (inFlight) { schedule(current); return; }
  inFlight = true;
  try {
    await cancelBarrier;
    if (current !== generation || !mounted || !enabled() || !locked()) return;
    show('waiting');
    const response = await backend.verify(30);
    if (current !== generation || !mounted || !enabled() || !locked()) return;
    if (response?.result === 'match') {
      show('success');
      const sec = store(), props = sec.GetActiveLockScreenProps();
      if (typeof props?.onSuccess === 'function') props.onSuccess();
      sec.SetActiveLockScreenProps(null);
      successTimer = setTimeout(() => { successTimer = undefined; visualState = null; visual.remove(); }, 200);
    } else if (response?.result === 'unavailable' && ['timeout', 'no-match'].includes(response.reason)) {
      show(response.reason === 'no-match' ? 'no-match' : 'retrying');
      schedule(current, response.reason === 'no-match' ? 1050 : 500);
    } else { show('unavailable'); }
  } catch (_) { if (current === generation && mounted && enabled() && locked()) show('unavailable'); }
  finally { inFlight = false; }
}
function Content() {
  const [on, setOn] = SP_REACT.useState(enabled());
  const [status, setStatus] = SP_REACT.useState(null);
  const refresh = async () => { try { setStatus(await backend.status()); } catch (_) { setStatus({available:false}); } };
  SP_REACT.useEffect(() => { refresh(); }, []);
  const row = (label, value) => SP_REACT.createElement(DFL.PanelSectionRow, {key:label},
    SP_REACT.createElement(DFL.Field, {label, focusable:false}, value));
  return SP_REACT.createElement(DFL.PanelSection, {title:'Fingerprint / 指纹'},
    SP_REACT.createElement(DFL.PanelSectionRow, null, SP_REACT.createElement(DFL.ToggleField, {
      label:'Fingerprint unlock / 指纹解锁', description:'Experimental, off by default / 实验功能，默认关闭', checked:on,
      onChange: value => { try { localStorage.setItem(key, value ? '1':'0'); } catch (_) {} setOn(enabled()); if (!value) abort(); else if (locked()) { abort(); attempt(); } }
    })),
    row('Status / 状态', status ? (status.available ? (status.enrolled ? 'Enrolled / 已录入' : 'No prints / 未录入') : 'Unavailable / 不可用') : 'Checking / 检查中'),
    row('Enroll / 录入', 'Desktop → System Settings → Users → Configure Fingerprints / 桌面 → 系统设置 → 用户 → 配置指纹'),
    SP_REACT.createElement(DFL.PanelSectionRow, null, SP_REACT.createElement(DFL.ButtonItem, {onClick:refresh}, 'Refresh / 刷新')),
    SP_REACT.createElement(DFL.PanelSectionRow, null, SP_REACT.createElement(DFL.ButtonItem, {onClick:() => { const sec=store(); if (sec) sec.SetActiveLockScreenProps({preventCancel:false}); }}, 'Test lock (B to cancel) / 测试锁屏（B 取消）')));
}
  timer = setInterval(() => { const active = locked(); if (active !== previous) { previous = active; if (active && enabled()) { if (successTimer) { clearTimeout(successTimer); successTimer = undefined; visualState = null; visual.remove(); } attempt(); } else abort(!active && !!successTimer); } else if (active && enabled() && visualState) { visual.render(visualState); } }, 300);
  return {name:'Boiler Fingerprint Unlock', titleView:SP_REACT.createElement('div', null, 'Fingerprint / 指纹'), content:SP_REACT.createElement(Content), icon:SP_REACT.createElement('div', null, '◉'), onDismount(){mounted = false; clearInterval(timer); abort();}};
};
