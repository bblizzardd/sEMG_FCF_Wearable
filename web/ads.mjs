/**
 * ads.mjs – ADS1292R sEMG panel for Combined Dashboard
 * Connects to /api/ads/stream (SSE, event: ads) and renders 3 oscilloscopes + gauge.
 */

const $ = id => document.getElementById(id);
const MAX_PTS = 400;
const CIRC = 2 * Math.PI * 75;   // r=75 => ~471.24

const rawH   = new Array(MAX_PTS).fill(0);
const filtH  = new Array(MAX_PTS).fill(0);
const envH   = new Array(MAX_PTS).fill(0);
const baseH  = new Array(MAX_PTS).fill(0);

let smoothRangeF = 60, smoothMaxE = 20;
let maxFlexPeak = 100;
let latestAds = null;
let isRecording = false;

function sendAdsCmd(key) {
  const token = document.querySelector('meta[name=bmi-token]')?.content || window.__bmiToken || '';
  fetch('/api/ads/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-BMI-Token': token },
    body: JSON.stringify({ command: key })
  }).catch(() => {});
}

function adsRecordToggle() {
  const btn = $('ads-btn-record');
  if (!isRecording) {
    const token = document.querySelector('meta[name=bmi-token]')?.content || window.__bmiToken || '';
    fetch('/api/ads/record/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-BMI-Token': token },
      body: JSON.stringify({})
    }).then(r => r.json()).then(d => {
      isRecording = true;
      if (btn) { btn.textContent = '⏹ Đang Ghi…'; btn.classList.add('primary'); }
    }).catch(() => {});
  } else {
    const token = document.querySelector('meta[name=bmi-token]')?.content || window.__bmiToken || '';
    fetch('/api/ads/record/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-BMI-Token': token },
      body: JSON.stringify({})
    }).then(r => r.json()).then(d => {
      isRecording = false;
      if (btn) { btn.textContent = '● Ghi CSV sEMG'; btn.classList.remove('primary'); }
      alert(`✅ Ghi xong: ${d.filename}\nMẫu: ${(d.samples||0).toLocaleString()}`);
    }).catch(() => {});
  }
}

window.sendAdsCmd = sendAdsCmd;
window.adsRecordToggle = adsRecordToggle;

async function refreshAdsPorts() {
  try {
    const res = await fetch('/api/ads/ports');
    if (!res.ok) return;
    const { ports } = await res.json();
    const sel = $('ads-serial-port');
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">Tự động tìm cổng ADS</option>';
    (ports || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.device;
      opt.textContent = `${p.device} (${p.description || 'USB Serial'})`;
      sel.appendChild(opt);
    });
    if (currentVal) sel.value = currentVal;
  } catch {}
}

async function adsConnectToggle() {
  const token = document.querySelector('meta[name=bmi-token]')?.content || window.__bmiToken || '';
  const isConn = latestAds && latestAds.connected;
  if (isConn) {
    await fetch('/api/ads/disconnect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-BMI-Token': token },
      body: JSON.stringify({})
    }).catch(() => {});
  } else {
    const sel = $('ads-serial-port');
    const port = sel ? sel.value : '';
    await fetch('/api/ads/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-BMI-Token': token },
      body: JSON.stringify({ port: port || null })
    }).catch(() => {});
  }
}
window.adsConnectToggle = adsConnectToggle;
window.refreshAdsPorts = refreshAdsPorts;

function drawGrid(ctx, w, h) {
  ctx.fillStyle = '#05080e';
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let y = 25; y < h; y += 25) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }
}

function drawScopes() {
  // --- Raw ADC ---
  const cR = $('ads-canvas-raw');
  if (cR) {
    const wR = cR.width, hR = cR.height;
    const ctxR = cR.getContext('2d', { alpha: false });
    drawGrid(ctxR, wR, hR);
    let mn = rawH[0], mx = rawH[0];
    for (let i = 1; i < MAX_PTS; i++) { if (rawH[i] < mn) mn = rawH[i]; if (rawH[i] > mx) mx = rawH[i]; }
    const range = Math.max(1200, mx - mn), mid = (mx + mn) / 2;
    ctxR.strokeStyle = '#518be5'; ctxR.lineWidth = 1.5; ctxR.beginPath();
    for (let i = 0; i < MAX_PTS; i++) {
      const x = (i / (MAX_PTS - 1)) * wR;
      const y = hR / 2 - ((rawH[i] - mid) / range) * hR * 0.42;
      i === 0 ? ctxR.moveTo(x, y) : ctxR.lineTo(x, y);
    }
    ctxR.stroke();
  }

  // --- Filtered sEMG ---
  const cF = $('ads-canvas-filt');
  if (cF) {
    const wF = cF.width, hF = cF.height;
    const ctxF = cF.getContext('2d', { alpha: false });
    drawGrid(ctxF, wF, hF);
    let maxAbs = 8;
    for (let i = 0; i < MAX_PTS; i++) { const a = Math.abs(filtH[i]); if (a > maxAbs) maxAbs = a; }
    smoothRangeF += (Math.max(30, maxAbs * 2.3) - smoothRangeF) * 0.08;
    ctxF.strokeStyle = '#b55fe6'; ctxF.lineWidth = 1.5; ctxF.beginPath();
    for (let i = 0; i < MAX_PTS; i++) {
      const x = (i / (MAX_PTS - 1)) * wF;
      const y = hF / 2 - (filtH[i] / (smoothRangeF / 2)) * hF * 0.44;
      i === 0 ? ctxF.moveTo(x, y) : ctxF.lineTo(x, y);
    }
    ctxF.stroke();
  }

  // --- Envelope ---
  const cE = $('ads-canvas-env');
  if (cE) {
    const wE = cE.width, hE = cE.height;
    const ctxE = cE.getContext('2d', { alpha: false });
    drawGrid(ctxE, wE, hE);
    let maxInH = 6;
    for (let i = 0; i < MAX_PTS; i++) { if (envH[i] > maxInH) maxInH = envH[i]; if (baseH[i] > maxInH) maxInH = baseH[i]; }
    smoothMaxE += (Math.max(16, maxInH * 1.35) - smoothMaxE) * 0.08;
    // Baseline
    ctxE.strokeStyle = 'rgba(81,139,229,0.6)'; ctxE.lineWidth = 1.4; ctxE.setLineDash([4, 4]); ctxE.beginPath();
    for (let i = 0; i < MAX_PTS; i++) {
      const x = (i / (MAX_PTS - 1)) * wE;
      const y = hE - Math.min(1, Math.max(0, baseH[i] / smoothMaxE)) * hE * 0.82 - 8;
      i === 0 ? ctxE.moveTo(x, y) : ctxE.lineTo(x, y);
    }
    ctxE.stroke(); ctxE.setLineDash([]);
    // Fill
    const grad = ctxE.createLinearGradient(0, 0, 0, hE);
    grad.addColorStop(0, 'rgba(8,123,101,0.25)'); grad.addColorStop(1, 'rgba(8,123,101,0)');
    ctxE.fillStyle = grad; ctxE.beginPath(); ctxE.moveTo(0, hE);
    for (let i = 0; i < MAX_PTS; i++) {
      const x = (i / (MAX_PTS - 1)) * wE;
      const y = hE - Math.min(1, Math.max(0, envH[i] / smoothMaxE)) * hE * 0.82 - 8;
      ctxE.lineTo(x, y);
    }
    ctxE.lineTo(wE, hE); ctxE.closePath(); ctxE.fill();
    // Line
    ctxE.strokeStyle = '#24a887'; ctxE.lineWidth = 2; ctxE.beginPath();
    for (let i = 0; i < MAX_PTS; i++) {
      const x = (i / (MAX_PTS - 1)) * wE;
      const y = hE - Math.min(1, Math.max(0, envH[i] / smoothMaxE)) * hE * 0.82 - 8;
      i === 0 ? ctxE.moveTo(x, y) : ctxE.lineTo(x, y);
    }
    ctxE.stroke();
  }

  requestAnimationFrame(drawScopes);
}

function resizeCanvases() {
  ['ads-canvas-raw', 'ads-canvas-filt', 'ads-canvas-env'].forEach(id => {
    const c = $(id);
    if (c && c.parentElement) { c.width = c.parentElement.clientWidth - 28; c.height = 95; }
  });
}

// DOM update 25 Hz
setInterval(() => {
  if (!latestAds) return;
  const d = latestAds;

  // Gauge
  const gf = $('ads-gauge-fill');
  if (gf) {
    const pct = Math.max(0, Math.min(100, d.percent || 0));
    gf.style.strokeDashoffset = CIRC - (pct / 100) * CIRC;
    gf.style.stroke = pct >= 60 ? '#da6157' : pct >= 25 ? '#e5a345' : pct >= 8 ? '#518be5' : '#087b65';
  }
  const pn = $('ads-pct-num'); if (pn) pn.textContent = d.percent || 0;

  const sb = $('ads-status-badge');
  if (sb) {
    sb.textContent = d.status || '—';
    const s = d.status || '';
    if (s.includes('MANH')) { sb.style.background='#fde8e6';sb.style.color='#da6157';sb.style.borderColor='rgba(218,97,87,.4)'; }
    else if (s.includes('VUA')) { sb.style.background='#fff8e6';sb.style.color='#e5a345';sb.style.borderColor='rgba(229,163,69,.4)'; }
    else if (s.includes('NHE')) { sb.style.background='#e8f4fc';sb.style.color='#518be5';sb.style.borderColor='rgba(81,139,229,.4)'; }
    else { sb.style.background='#e6f7f0';sb.style.color='#087b65';sb.style.borderColor='#a3d9c5'; }
  }

  // Scope labels
  const rv = $('ads-val-raw'); if (rv) rv.textContent = `Raw: ${(d.raw||0).toLocaleString()}`;
  const fv = $('ads-val-filt'); if (fv) fv.textContent = `Filt: ${(d.filt||0).toLocaleString()}`;
  const ev = $('ads-val-env'); if (ev) ev.textContent = `Env:${d.env||0} Base:${d.base||0}`;

  // Stats
  const sv = $('ads-stat-base'); if (sv) sv.textContent = (d.base||0).toLocaleString();
  const se = $('ads-stat-env'); if (se) se.textContent = (d.env||0).toLocaleString();
  const sp = $('ads-stat-peak'); if (sp) sp.textContent = maxFlexPeak.toLocaleString();
  const pp = $('ads-port-pill'); if (pp) pp.textContent = d.port || '—';

  // Health
  if (d.health) {
    const h = d.health;
    const set = (id, txt, cls) => { const el=$(id); if(el){el.textContent=txt;if(cls)el.className='ads-hi-chk '+(cls==='ok'?'ok':'bad');} };
    set('ads-hi-sps', `${h.sps} SPS`); set('ads-chk-sps', h.sps >= 1500 ? '✓' : '✗', h.sps >= 1500 ? 'ok' : 'bad');
    set('ads-hi-recv', (h.received||0).toLocaleString());
    set('ads-hi-drop', (h.dropped||0).toLocaleString()); set('ads-chk-drop', h.dropped===0?'✓':'✗', h.dropped===0?'ok':'bad');
    set('ads-hi-gap', `${h.max_gap_us}µs`); set('ads-chk-gap', h.max_gap_us<=2000?'✓':'✗', h.max_gap_us<=2000?'ok':'bad');
    set('ads-hi-clip', `${h.clipping_pct}%`); set('ads-chk-clip', h.clipping_pct<1?'✓':'✗', h.clipping_pct<1?'ok':'bad');
    set('ads-hi-loff', h.lead_off?'LEAD-OFF':'CONNECTED'); set('ads-chk-loff', !h.lead_off?'✓':'✗', !h.lead_off?'ok':'bad');
    const recEl=$('ads-hi-rec'); if(recEl) recEl.textContent = h.recording ? `REC (${(h.record_count||0).toLocaleString()})` : 'STANDBY';
    const badge=$('ads-health-badge');
    if(badge){ badge.textContent=h.healthy?'✓ HEALTHY':'✗ INVALID'; badge.className='ads-health-badge '+(h.healthy?'healthy':'warn'); }
    const dot=$('ads-live-dot');
    if(dot){ dot.className='ads-dot '+(d.connected?'live':''); }
  }

  const cb = $('ads-connect-btn');
  if (cb) {
    if (d.connected) {
      cb.textContent = '⏹ Ngắt kết nối sEMG';
      cb.classList.remove('primary');
      cb.classList.add('light');
    } else {
      cb.textContent = '↔ Kết nối sEMG';
      cb.classList.remove('light');
      cb.classList.add('primary');
    }
  }
}, 40);

// SSE connection
function connectAdsSSE() {
  const es = new EventSource('/api/ads/stream');
  es.addEventListener('ads', e => {
    try {
      const data = JSON.parse(e.data);
      rawH.push(data.raw||0); rawH.shift();
      filtH.push(data.filt||0); filtH.shift();
      envH.push(data.env||0); envH.shift();
      baseH.push(data.base||0); baseH.shift();
      if ((data.env||0) > maxFlexPeak) maxFlexPeak = data.env;
      latestAds = data;
    } catch {}
  });
  es.onerror = () => setTimeout(connectAdsSSE, 2000);
}

window.addEventListener('DOMContentLoaded', () => {
  resizeCanvases();
  window.addEventListener('resize', resizeCanvases);
  requestAnimationFrame(drawScopes);
  connectAdsSSE();
  refreshAdsPorts();
  setInterval(refreshAdsPorts, 5000);
});
