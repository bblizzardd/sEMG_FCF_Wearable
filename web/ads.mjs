/**
 * ads.mjs – Khu sEMG (ADS1292R) của tab Trực tiếp + nút Ghi phiên.
 * Nhận /api/ads/stream (SSE, event: ads): chuỗi điểm decimation 200/s theo đồng hồ ESP32
 * (kèm trạng thái nút, lead-off) để vẽ sEMG + nút nhấn, cùng số liệu cho đồng hồ % MVC.
 */
import {chartHeight, drawTimeChart, BUTTON_COLOR} from './timechart.mjs';
import {runsOf} from './review-data.mjs';

const $ = id => document.getElementById(id);
const CIRC = 2 * Math.PI * 75;   // r=75 => ~471.24
const KEEP_US = 32e6;            // giữ 32 s điểm (cửa sổ lớn nhất 30 s)
const STATUS_TEXT = {'THA LONG': 'THẢ LỎNG', 'GONG NHE': 'GỒNG NHẸ', 'GONG VUA': 'GỒNG VỪA', 'GONG MANH!': 'GỒNG MẠNH!'};

const pts = {t: [], raw: [], filt: [], env: [], base: [], btn: [], loff: []};
let frozen = null, latestAds = null, lastPoint = 0, isRecording = false;

function token() {
  return document.querySelector('meta[name=bmi-token]')?.content || window.__bmiToken || '';
}
function post(endpoint, body) {
  return fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-BMI-Token': token()}, body: JSON.stringify(body)});
}
function sendAdsCmd(key) {
  post('/api/ads/command', {command: key}).catch(() => {});
}

function notice(text, warn = false, action = null) {
  const box = $('notice');
  if (!box) return;
  box.replaceChildren(text);
  box.classList.toggle('warn', warn);
  if (action) {
    const button = document.createElement('button');
    button.className = 'button light small notice-action';
    button.textContent = action.label;
    button.addEventListener('click', action.run);
    box.append(' ', button);
  }
}

function updateRecordButtons(rec, semgN, imuN, durS) {
  const button = $('btn-dual-record');
  if (button) {
    button.classList.toggle('recording', rec);
    button.textContent = rec ? `■ Dừng ghi · ${durS || 0}s` : '● Ghi sEMG + IMU + nút';
  }
  const dot = $('record-dot');
  if (dot) dot.className = rec ? 'state-dot red' : 'state-dot';
  const status = $('record-status');
  if (status) status.textContent = rec ? `Đang ghi · ${durS || 0}s` : 'Sẵn sàng ghi';
  const caption = $('record-count');
  if (caption) caption.textContent = rec
    ? `sEMG ${(semgN || 0).toLocaleString('vi-VN')} · IMU ${(imuN || 0).toLocaleString('vi-VN')} mẫu`
    : 'Bấm “Ghi sEMG + IMU + nút” ở trên';
}

function dualRecordToggle() {
  if (!isRecording) {
    post('/api/record/start', {}).then(r => r.json()).then(d => {
      if (!d.ok) { notice(d.error || 'Không thể bắt đầu ghi.', true); return; }
      isRecording = true;
      updateRecordButtons(true, 0, 0, 0);
      notice(`Đang ghi phiên ${d.session}: sEMG + IMU + nút vào ${d.combined_file}. Bấm “Dừng ghi” khi xong.`);
    }).catch(e => notice('Lỗi kết nối máy chủ Python: ' + e, true));
    return;
  }
  post('/api/record/stop', {}).then(r => r.json()).then(d => {
    isRecording = false;
    updateRecordButtons(false, 0, 0, 0);
    if (!d.ok) { notice(d.error || 'Lỗi khi dừng ghi.', true); return; }
    window.dispatchEvent(new CustomEvent('dual-record-stopped', {detail: d}));
    notice(`✓ Đã lưu phiên ${d.session} (${d.duration_s}s): ${(d.combined_rows || 0).toLocaleString('vi-VN')} dòng gộp sEMG + IMU + nút · ${d.combined_file}`,
      false, {label: '▤ Xem lại phiên này', run: () => window.openReviewSession?.(d.session)});
  }).catch(e => notice('Lỗi kết nối máy chủ Python: ' + e, true));
}

window.sendAdsCmd = sendAdsCmd;
window.dualRecordToggle = dualRecordToggle;
window.adsRecordToggle = dualRecordToggle;
window.updateRecordButtons = updateRecordButtons;

// ---------------------------------------------------------------- Đồ thị sEMG + nút
function addPoints(points) {
  for (const [ts, raw, filt, env, base, btn, loff] of points) {
    const last = pts.t.at(-1);
    if (last !== undefined && ts <= last) {
      if (ts < last - 1e6) for (const key in pts) pts[key].length = 0;  // ESP32 khởi động lại
      else continue;
    }
    pts.t.push(ts); pts.raw.push(raw); pts.filt.push(filt); pts.env.push(env); pts.base.push(base);
    pts.btn.push(btn); pts.loff.push(loff);
  }
  const cutoff = (pts.t.at(-1) ?? 0) - KEEP_US;
  let drop = 0;
  while (drop < pts.t.length && pts.t[drop] < cutoff) drop++;
  if (drop) for (const key in pts) pts[key].splice(0, drop);
  if (points.length) lastPoint = performance.now();
}

function renderChart() {
  requestAnimationFrame(renderChart);
  const canvas = $('live-emg-chart');
  if (!canvas || canvas.offsetParent === null) return;  // tab đang ẩn
  const paused = $('pause')?.dataset.paused === '1';
  if (paused && !frozen) frozen = Object.fromEntries(Object.entries(pts).map(([key, list]) => [key, list.slice()]));
  if (!paused) frozen = null;
  const data = frozen ?? pts, seconds = Number($('window')?.value || 12), last = data.t.at(-1) ?? 0;
  const i0 = Math.max(0, data.t.findIndex(ts => ts >= last - seconds * 1e6 - 20000));
  const t = data.t.slice(i0).map(ts => (ts - last) / 1e6), slice = key => data[key].slice(i0);
  const raw = $('ads-signal')?.value === 'raw';
  const height = chartHeight(1, 230) + 'px';
  if (canvas.style.height !== height) canvas.style.height = height;
  const series = raw
    ? [{t, v: slice('raw'), color: '#518be5', width: 1.2, primary: true}]
    : [{t, v: slice('filt'), color: '#b55fe6', width: 1, alpha: 0.85},
       {t, v: slice('env'), color: '#24a887', width: 2},
       {t, v: slice('base'), color: '#518be5', width: 1.2, dash: [4, 4], alpha: 0.8}];
  const loff = Int8Array.from(slice('loff')), btn = Int8Array.from(slice('btn'));
  const runs = btn.some(v => v >= 0) ? runsOf(t, btn) : null;
  drawTimeChart(canvas, {
    start: -seconds, end: 0,
    tracks: t.length ? [{label: raw ? 'sEMG gốc · ch2_raw16 · LSB' : 'sEMG đã lọc · LSB', min: 40, gap: 0.05, series, exclude: loff}] : [],
    bands: runsOf(t, loff), button: runs ? {runs, presses: runs.filter(run => run.edge)} : null,
    empty: 'Chờ dữ liệu sEMG từ ADS1292R', noButton: 'Firmware chưa gửi button_state',
  });
}

function renderLegend() {
  const raw = $('ads-signal')?.value === 'raw';
  const items = (raw ? [['', '#518be5', 'sEMG gốc']] : [['', '#b55fe6', 'sEMG đã lọc'], ['', '#24a887', 'Bao hình'], ['dash', '#518be5', 'Baseline']])
    .concat([['band', '#c9d0d3', 'Lead-off'], ['band', BUTTON_COLOR, 'Nút nhấn'], ['dash', BUTTON_COLOR, 'Lúc nhấn']]);
  $('live-emg-legend').replaceChildren(...items.map(([kind, color, label]) => {
    const span = document.createElement('span'), key = document.createElement('i');
    key.className = `review-key ${kind}`.trim();
    if (kind === 'dash') key.style.borderTopColor = color; else key.style.background = color;
    span.append(key, label);
    return span;
  }));
}

// ---------------------------------------------------------------- Số liệu (25 Hz)
function setCheck(id, ok, text) {
  const value = $(id.replace('chk', 'hi'));
  if (value && text !== undefined) value.textContent = text;
  const mark = $(id);
  if (mark) { mark.textContent = ok ? '✓' : '✗'; mark.className = 'ads-hi-chk ' + (ok ? 'ok' : 'bad'); }
}

setInterval(() => {
  if (!latestAds) return;
  const d = latestAds, h = d.health || {};
  const fresh = d.connected && performance.now() - lastPoint < 1500;

  const pct = Math.max(0, Math.min(100, d.percent || 0));
  const fill = $('ads-gauge-fill');
  fill.style.strokeDashoffset = CIRC - (pct / 100) * CIRC;
  fill.style.stroke = pct >= 60 ? '#da6157' : pct >= 25 ? '#e5a345' : pct >= 8 ? '#518be5' : '#087b65';
  $('ads-pct-num').textContent = pct;

  const status = d.status || '', badge = $('ads-status-badge');
  badge.textContent = STATUS_TEXT[status] ?? status ?? '—';
  badge.dataset.level = status.includes('MANH') ? 'strong' : status.includes('VUA') ? 'medium' : status.includes('NHE') ? 'light'
    : (status.includes('CAM') || status.includes('CẮM')) ? 'off' : 'rest';

  $('ads-stat-base').textContent = (d.base || 0).toLocaleString('vi-VN');
  $('ads-stat-env').textContent = (d.env || 0).toLocaleString('vi-VN');
  $('ads-stat-peak').textContent = (d.peak || 0).toLocaleString('vi-VN');
  $('ads-port-pill').textContent = `ADS1292R · kênh CH2 · ${d.connected ? (d.port || 'ESP32') + ' · trực tuyến' : 'chờ ESP32'} · độ nhạy ${d.sens || 'x1.00'}`;
  const dsp = $('ads-btn-dsp');
  if (d.dsp) {
    const on = d.dsp.includes('ON');
    dsp.textContent = on ? 'DSP: BẬT' : 'DSP: TẮT';
    dsp.classList.toggle('warn-button', !on);
  }

  // Thẻ trạng thái sEMG
  $('ads-hi-sps').replaceChildren(fresh ? String(Math.round(h.sps || 0)) : '—', ' ', Object.assign(document.createElement('small'), {textContent: 'SPS'}));
  $('ads-card-caption').textContent = !d.connected ? 'Chờ kết nối ESP32'
    : !fresh ? 'Đã kết nối · chưa có mẫu sEMG'
    : `${h.lead_off ? '⚠ Điện cực hở (lead-off)' : 'Điện cực đã cắm'} · mất ${(h.dropped || 0).toLocaleString('vi-VN')} mẫu`;
  $('ads-live-dot').className = 'state-dot' + (!fresh ? '' : h.lead_off || !h.healthy ? ' amber' : ' green');

  // Chất lượng dữ liệu
  $('ads-hi-recv').textContent = (h.received || 0).toLocaleString('vi-VN');
  setCheck('ads-chk-drop', h.dropped === 0, (h.dropped || 0).toLocaleString('vi-VN'));
  setCheck('ads-chk-gap', h.max_gap_us <= 3000, `${h.max_gap_us ?? '—'} µs`);
  setCheck('ads-chk-clip', h.clipping_pct < 1, `${h.clipping_pct ?? 0}%`);
  setCheck('ads-chk-loff', !h.lead_off, h.lead_off ? 'HỞ' : 'ĐÃ CẮM');
  const health = $('ads-health-badge');
  health.textContent = !fresh ? 'CHỜ sEMG' : h.healthy ? '✓ sEMG ỔN' : '⚠ KIỂM TRA sEMG';
  health.className = 'ads-health-badge ' + (!fresh || h.healthy ? 'healthy' : 'warn');

  if (d.dual_recording) {
    const rec = d.dual_recording;
    isRecording = rec.recording;
    updateRecordButtons(rec.recording, rec.semg_samples, rec.imu_samples, rec.duration_s);
  }
}, 40);

function connectAdsSSE() {
  const es = new EventSource('/api/ads/stream');
  es.addEventListener('ads', e => {
    try {
      const data = JSON.parse(e.data);
      addPoints(data.points || []);
      latestAds = data;
    } catch {}
  });
  es.onerror = () => { es.close(); setTimeout(connectAdsSSE, 2000); };
}

$('ads-signal').addEventListener('change', renderLegend);
renderLegend();
requestAnimationFrame(renderChart);
connectAdsSSE();
