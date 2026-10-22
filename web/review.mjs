/**
 * review.mjs – Khu "Xem lại dữ liệu đã ghi": nạp CSV (kéo thả, chọn file, hoặc chọn phiên trong data/)
 * rồi vẽ toàn bộ phiên thành 2 đồ thị tách riêng – BMI160 + nút và sEMG (ADS1292R) + nút – trên cùng
 * một trục thời gian, kèm bảng các mốc nút bấm của từng bộ dữ liệu.
 */
import {readCsv, buildSession, nearestIndex, heldIndex} from './review-data.mjs';
import {LAYOUT, BUTTON_COLOR, chartHeight, drawTimeChart} from './timechart.mjs';

const $ = id => document.getElementById(id);
const finite = v => typeof v === 'number' && Number.isFinite(v);
const COLOR = {x: '#518be5', y: '#24a887', z: '#e5a345', emg: '#b55fe6', raw: '#518be5', rms: '#24a887', button: BUTTON_COLOR};
const AXIS = [COLOR.x, COLOR.y, COLOR.z];
const {L, R} = LAYOUT, MIN_SPAN = 0.005;
const KIND_LABEL = {combined: 'gộp sEMG + IMU + nút', semg: 'sEMG', imu: 'IMU'};
const BUTTON_SOURCE = {gộp: 'cột button_state của file gộp (2000 SPS)', sEMG: 'button_state của file sEMG (2000 SPS)', IMU: 'button_state của file IMU (100 Hz)'};
const IMU_GROUPS = {
  accel: {label: 'Gia tốc', unit: 'g', min: 0.3, digits: 3, raw: ['ax_g', 'ay_g', 'az_g'], kal: ['ax_kal_g', 'ay_kal_g', 'az_kal_g'], names: ['X', 'Y', 'Z']},
  gyro: {label: 'Tốc độ góc', unit: '°/s', min: 10, digits: 1, raw: ['gx_dps', 'gy_dps', 'gz_dps'], kal: ['gx_kal_dps', 'gy_kal_dps', 'gz_kal_dps'], names: ['X', 'Y', 'Z']},
  angle: {label: 'Góc nghiêng', unit: '°', min: 10, digits: 1, raw: ['roll_acc_deg', 'pitch_acc_deg'], kal: ['roll_kal_deg', 'pitch_kal_deg'], names: ['Roll', 'Pitch']},
};

let session = null, sessions = [], activeMark = null, frame = 0, loading = false;
const view = {start: 0, end: 1};
const hover = {chart: null, time: null};
const drag = {chart: null, from: null, to: null, x0: 0};
const charts = [
  {canvas: $('review-imu-chart'), tip: $('review-imu-tip'), tracks: [], bands: [], button: null, pw: 0,
    empty: 'Không có dữ liệu IMU (BMI160) trong file đã nạp'},
  {canvas: $('review-emg-chart'), tip: $('review-emg-tip'), tracks: [], bands: [], button: null, pw: 0,
    empty: 'Không có dữ liệu sEMG (ADS1292R) trong file đã nạp'},
];
const [imuChart, emgChart] = charts;

function el(tag, className = '', text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function setStatus(text, warn = false) {
  const status = $('review-status');
  status.textContent = text;
  status.classList.toggle('warn', warn);
}
const primaryButton = () => session?.buttons.semg ?? session?.buttons.imu ?? null;
const prettySession = id => `${id.slice(6, 8)}/${id.slice(4, 6)}/${id.slice(0, 4)} ${id.slice(9, 11)}:${id.slice(11, 13)}:${id.slice(13, 15)}`;
const fmtRate = rate => !finite(rate) ? '—' : rate >= 500 ? `${Math.round(rate)} SPS` : `${rate.toFixed(1)} Hz`;
const count = n => n.toLocaleString('vi-VN');

// ---------------------------------------------------------------- Track của từng đồ thị
function imuTracks() {
  const imu = session?.imu;
  if (!imu) return [];
  const pick = $('review-imu-signal').value, mode = $('review-imu-mode').value;
  return (pick === 'all' ? ['accel', 'gyro', 'angle'] : [pick]).map(key => {
    const group = IMU_GROUPS[key];
    const hasKal = group.kal.some(name => imu.has[name]);
    const useKal = mode !== 'raw' && hasKal, useRaw = mode !== 'kalman' || !hasKal;
    const series = [];
    group.names.forEach((name, i) => {
      if (useRaw && imu.has[group.raw[i]]) {
        series.push({name, t: imu.t, v: imu.ch[group.raw[i]], color: AXIS[i], width: useKal ? 1 : 1.6, alpha: useKal ? 0.4 : 1, primary: !useKal});
      }
      if (useKal && imu.has[group.kal[i]]) {
        series.push({name, t: imu.t, v: imu.ch[group.kal[i]], color: AXIS[i], width: 1.6, alpha: 1, primary: true});
      }
    });
    return {key, label: `${group.label} · ${useKal ? 'Kalman' : 'gốc'} · ${group.unit}`, short: `${group.label} (${group.unit})`,
      min: group.min, digits: group.digits, gap: 0.06, series};
  }).filter(track => track.series.length);
}

function emgTracks() {
  const emg = session?.semg;
  if (!emg) return [];
  const raw = $('review-emg-signal').value === 'raw', rms = !raw && $('review-emg-rms').checked;
  const series = [raw
    ? {name: 'gốc', t: emg.t, v: emg.raw, color: COLOR.raw, width: 1, alpha: 1, primary: true}
    : {name: 'đã lọc', t: emg.t, v: emg.filt, color: COLOR.emg, width: 1, alpha: 0.85, primary: true}];
  if (rms) series.push({name: 'RMS 100 ms', t: emg.t, v: emg.rms, color: COLOR.rms, width: 1.8, alpha: 1, primary: true});
  return [{key: 'emg', label: raw ? 'sEMG gốc · ch2_raw16 · LSB' : 'sEMG đã lọc · ch2_filtered16 · LSB', short: 'sEMG (LSB)',
    min: 40, digits: 0, gap: 0.006, series, exclude: emg.loff}];
}

function rebuild() {
  // Nút tích hợp vào cả hai đồ thị: thiếu cột nút ở bộ này thì dùng nút của bộ kia (cùng đồng hồ ESP32)
  imuChart.tracks = imuTracks();
  imuChart.button = session ? session.buttons.imu ?? session.buttons.semg : null;
  emgChart.tracks = emgTracks();
  emgChart.button = session ? session.buttons.semg ?? session.buttons.imu : null;
  emgChart.bands = session?.semg?.loffRuns ?? [];
  $('review-emg-rms').disabled = $('review-emg-signal').value === 'raw';
  renderLegends();
  renderCaptions();
  request();
}

// ---------------------------------------------------------------- Vẽ
function request() {
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    for (const chart of charts) drawChart(chart);
    for (const chart of charts) updateTip(chart);
  });
}

function drawChart(chart) {
  const {canvas, tracks} = chart, height = chartHeight(session ? tracks.length : 0, tracks.length > 1 ? 130 : 240) + 'px';
  if (canvas.style.height !== height) canvas.style.height = height;
  chart.pw = drawTimeChart(canvas, {
    start: view.start, end: view.end, tracks: session ? tracks : [], button: chart.button, bands: chart.bands,
    cursor: hover.time, selection: drag.from !== null ? [drag.from, drag.to] : null, activeMark,
    empty: session ? chart.empty : 'Chưa nạp dữ liệu', noButton: 'File không có cột button_state',
  });
}

// ---------------------------------------------------------------- Chú thích & tooltip
function keyItem(color, value, label, kind = '') {
  const span = el('span', 'review-tip-item'), key = el('i', `review-key ${kind}`.trim());
  if (kind === 'dash') key.style.borderTopColor = color; else key.style.background = color;
  span.append(key);
  if (value !== null) span.append(el('b', '', value));
  if (label) span.append(value !== null ? ' ' + label : label);
  return span;
}

function buttonRow(button, time) {
  const row = el('div', 'review-tip-row');
  row.append(el('span', '', 'Nút nhấn'));
  if (!button) { row.append(el('span', '', 'không có cột button_state')); return row; }
  const i = heldIndex(button.t, time), state = i >= 0 ? button.s[i] : -1;
  row.append(keyItem(COLOR.button, state < 0 ? '—' : String(state), state === 1 ? 'đang nhấn' : state === 0 ? 'thả' : ''));
  let k = 0;
  while (k < button.presses.length && button.presses[k].start <= time) k++;
  if (k) row.append(el('span', '', `sau mốc #${k} · +${(time - button.presses[k - 1].start).toFixed(2)} s`));
  return row;
}

function updateTip(chart) {
  const {tip} = chart;
  if (!session || hover.chart !== chart || hover.time === null || drag.from !== null || !chart.tracks.length || chart.pw <= 10) {
    tip.hidden = true;
    return;
  }
  const time = hover.time, span = view.end - view.start;
  const rows = chart.tracks.map(track => {
    const row = el('div', 'review-tip-row');
    row.append(el('span', '', track.short));
    for (const series of track.series) {
      if (!series.primary) continue;
      const i = nearestIndex(series.t, time), v = series.v[i];
      const near = series.t.length > 0 && Math.abs(series.t[i] - time) <= track.gap;
      row.append(keyItem(series.color, near && finite(v) ? v.toFixed(track.digits) : '—', series.name));
    }
    return row;
  });
  rows.push(buttonRow(chart.button, time));
  if (chart === emgChart) {
    const emg = session.semg, i = nearestIndex(emg.t, time), off = emg.loff[i];
    const row = el('div', 'review-tip-row');
    row.append(el('span', '', 'Điện cực'), keyItem('#b9c2c5', off === 1 ? 'lead-off' : off === 0 ? 'đã cắm' : '—', '', 'band'));
    rows.push(row);
  }
  tip.replaceChildren(el('strong', 'review-tip-time', `${time.toFixed(span < 2 ? 4 : 3)} s`), ...rows);
  tip.hidden = false;
  const x = L + (time - view.start) / span * chart.pw, width = tip.offsetWidth, wrap = chart.canvas.clientWidth;
  tip.style.left = (x + 14 + width <= wrap - 4 ? x + 14 : Math.max(4, x - 14 - width)) + 'px';
}

function fillLegend(box, items) {
  box.replaceChildren(...items.map(([kind, color, label]) => keyItem(color, null, label, kind)));
}

function renderLegends() {
  const groups = new Set(imuChart.tracks.map(track => track.key)), imuItems = [];
  const xyz = groups.has('accel') || groups.has('gyro'), angle = groups.has('angle');
  const names = xyz && angle ? ['X · roll', 'Y · pitch', 'Z'] : xyz ? ['X', 'Y', 'Z'] : angle ? ['Roll', 'Pitch'] : [];
  names.forEach((name, i) => imuItems.push(['', AXIS[i], name]));
  if (imuChart.tracks.some(track => track.series.some(series => !series.primary))) imuItems.push(['', '#5f7169', 'Kalman'], ['faded', '#5f7169', 'gốc']);
  const emgItems = (emgChart.tracks[0]?.series ?? []).map(series => ['', series.color, series.name === 'RMS 100 ms' ? series.name : `sEMG ${series.name}`]);
  emgItems.push(['band', '#c9d0d3', 'Lead-off']);
  const buttonItems = [['band', COLOR.button, 'Nút nhấn'], ['dash', COLOR.button, 'Mốc nhấn #']];
  fillLegend($('review-imu-legend'), imuChart.tracks.length ? [...imuItems, ...buttonItems] : []);
  fillLegend($('review-emg-legend'), emgChart.tracks.length ? [...emgItems, ...buttonItems] : []);
}

function renderCaptions() {
  if (!session) return;
  const {semg, imu} = session;
  $('review-imu-sub').textContent = imu
    ? `${count(imu.count)} mẫu · ${fmtRate(imu.rate)} · ${imu.file}` : 'Không có dữ liệu IMU trong file đã nạp';
  $('review-emg-sub').textContent = semg
    ? `${count(semg.count)} mẫu · ${fmtRate(semg.rate)} · ${semg.file}` : 'Không có dữ liệu sEMG trong file đã nạp';
  for (const [chart, id] of [[imuChart, 'review-imu-foot'], [emgChart, 'review-emg-foot']]) {
    const button = chart.button;
    $(id).textContent = 'Thời gian từ đầu phiên (s)' + (!chart.tracks.length ? '' : button
      ? ` · ${button.presses.length} mốc nhấn theo ${BUTTON_SOURCE[button.source]}` : ' · không có dữ liệu nút');
  }
}

function setMetric(id, value, unit = '') {
  const node = $(id);
  node.replaceChildren(value);
  if (unit) node.append(' ', el('small', '', unit));
}

function renderSummary() {
  const {semg, imu} = session, main = primaryButton(), total = session.end - session.start;
  setMetric('review-duration', total.toFixed(2), 's');
  $('review-duration-caption').textContent = (session.session ? `Phiên ${prettySession(session.session)}` : session.files.map(file => file.name).join(' · '))
    + (total >= 60 ? ` · ${Math.floor(total / 60)} phút ${Math.round(total % 60)} giây` : '');
  setMetric('review-emg-count', semg ? count(semg.count) : '—', semg ? 'mẫu' : '');
  $('review-emg-caption').textContent = semg
    ? `${fmtRate(semg.rate)} · mất ${count(semg.dropped)} mẫu · lead-off ${(semg.loffFraction * 100).toFixed(1)}%` : 'Không có dữ liệu sEMG';
  setMetric('review-imu-count', imu ? count(imu.count) : '—', imu ? 'mẫu' : '');
  $('review-imu-caption').textContent = imu
    ? `${fmtRate(imu.rate)} · mất ${count(imu.dropped)} mẫu${imu.has.ax_kal_g ? '' : ' · không có cột Kalman'}` : 'Không có dữ liệu IMU (BMI160)';
  const presses = main?.presses ?? [];
  setMetric('review-press-count', main ? String(presses.length) : '—', main ? 'lần nhấn' : '');
  const released = presses.filter(press => press.released);
  const gaps = presses.filter(press => press.next !== null);
  $('review-press-caption').textContent = !main ? 'File không có cột button_state' : !presses.length ? 'Không có lần nhấn nào'
    : [released.length && `giữ TB ${Math.round(released.reduce((s, p) => s + p.end - p.start, 0) / released.length * 1000)} ms`,
      gaps.length && `cách nhau TB ${(gaps.reduce((s, p) => s + p.next - p.start, 0) / gaps.length).toFixed(2)} s`].filter(Boolean).join(' · ') || 'Mới có 1 lần nhấn';
}

function renderMarks() {
  const main = primaryButton(), other = session.buttons.imu && session.buttons.imu !== main ? session.buttons.imu : null;
  const columns = ['Mốc', other ? 'Nhấn · sEMG (s)' : 'Nhấn (s)', ...(other ? ['Nhấn · IMU (s)'] : []), 'Thả (s)', 'Giữ (ms)', 'Tới mốc sau (s)'];
  const head = el('tr');
  for (const name of columns) head.append(el('th', '', name));
  $('review-mark-head').replaceChildren(head);
  const list = main?.presses ?? [], rows = [];
  $('review-mark-tag').textContent = main ? `${list.length} MỐC` : 'KHÔNG CÓ CỘT NÚT';
  $('review-marks-sub').textContent = main
    ? `Theo ${BUTTON_SOURCE[main.source]}${other ? ', đối chiếu với file IMU' : ''} · nhấp số mốc để phóng to từ lần nhấn đó tới lần nhấn kế tiếp`
    : 'File đã nạp không có cột button_state';
  for (let k = 0; k < Math.max(list.length, other?.presses.length ?? 0); k++) {
    const press = list[k], twin = other?.presses[k], row = el('tr'), go = el('button', 'review-mark-go', `#${k + 1}`);
    go.type = 'button';
    go.disabled = !press;
    if (press) row.dataset.k = k;
    const cells = [
      press ? press.start.toFixed(3) : '—',
      ...(other ? [twin ? twin.start.toFixed(3) : '—'] : []),
      press?.released ? press.end.toFixed(3) : '—',
      press?.released ? String(Math.round((press.end - press.start) * 1000)) : '—',
      press && press.next !== null ? (press.next - press.start).toFixed(2) : '—',
    ];
    const first = el('td');
    first.append(go);
    row.append(first, ...cells.map(text => el('td', '', text)));
    rows.push(row);
  }
  if (!rows.length) {
    const row = el('tr', 'review-empty'), cell = el('td', '', main ? 'Không có lần nhấn nút nào trong dữ liệu đã nạp.' : 'File đã nạp không có cột button_state.');
    cell.colSpan = columns.length;
    row.append(cell);
    rows.push(row);
  }
  $('review-mark-body').replaceChildren(...rows);
  markActiveRow();
}

function markActiveRow() {
  for (const row of $('review-mark-body').rows) row.classList.toggle('active', row.dataset.k !== undefined && Number(row.dataset.k) === activeMark);
  const n = primaryButton()?.presses.length ?? 0;
  $('review-prev').disabled = !n || activeMark === 0;
  $('review-next').disabled = !n || activeMark === n - 1;
}

// ---------------------------------------------------------------- Khung nhìn chung của 2 đồ thị
function updateRange() {
  if (!session) return;
  const span = view.end - view.start, digits = span < 1 ? 3 : span < 20 ? 2 : 1;
  $('review-range').textContent = `${view.start.toFixed(digits)} – ${view.end.toFixed(digits)} s / ${(session.end - session.start).toFixed(2)} s`;
}
function setView(a, b) {
  if (!session) return;
  const full = Math.max(session.end - session.start, MIN_SPAN), span = Math.min(Math.max(b - a, MIN_SPAN), full);
  const start = Math.min(Math.max((a + b) / 2 - span / 2, session.start), session.start + full - span);
  view.start = start; view.end = start + span;
  updateRange();
  request();
}
function fit() {
  activeMark = null;
  setView(session.start, session.end);
  markActiveRow();
}
const zoomAround = (time, factor) => setView(time - (time - view.start) * factor, time + (view.end - time) * factor);
const panBy = dt => setView(view.start + dt, view.end + dt);

function showMark(index) {
  const list = primaryButton()?.presses ?? [];
  if (!list.length) return;
  activeMark = Math.max(0, Math.min(list.length - 1, index));
  const press = list[activeMark], end = press.next ?? Math.min(session.end, press.start + 3);
  const pad = Math.max(0.15, (end - press.start) * 0.08);
  setView(press.start - pad, end + pad);
  markActiveRow();
}

for (const chart of charts) {
  const {canvas} = chart;
  const timeAt = clientX => {
    const rect = canvas.getBoundingClientRect(), pw = Math.max(1, rect.width - L - R);
    const x = Math.min(Math.max(clientX - rect.left, L), L + pw);
    return view.start + (x - L) / pw * (view.end - view.start);
  };
  canvas.addEventListener('pointerdown', event => {
    if (!session || event.button !== 0) return;
    canvas.setPointerCapture(event.pointerId);
    drag.chart = chart; drag.from = drag.to = timeAt(event.clientX); drag.x0 = event.clientX;
    request();
  });
  canvas.addEventListener('pointermove', event => {
    if (!session) return;
    hover.chart = chart; hover.time = timeAt(event.clientX);
    if (drag.chart === chart) drag.to = hover.time;
    request();
  });
  const finish = event => {
    if (drag.chart !== chart) return;
    const a = Math.min(drag.from, drag.to), b = Math.max(drag.from, drag.to);
    const zoom = event.type === 'pointerup' && Math.abs(event.clientX - drag.x0) > 4;
    drag.chart = null; drag.from = drag.to = null;
    if (zoom) setView(a, b); else request();
  };
  canvas.addEventListener('pointerup', finish);
  canvas.addEventListener('pointercancel', finish);
  canvas.addEventListener('pointerleave', () => {
    if (drag.chart || hover.chart !== chart || document.activeElement === canvas) return;
    hover.chart = null; hover.time = null;
    request();
  });
  canvas.addEventListener('dblclick', () => { if (session) fit(); });
  canvas.addEventListener('wheel', event => {
    if (!session) return;
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1;
    // Lăn chuột thường vẫn cuộn trang; Ctrl (hoặc chụm 2 ngón) để phóng to, Shift / vuốt ngang để dời
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      zoomAround(timeAt(event.clientX), Math.exp(event.deltaY * unit * 0.002));
    } else if (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      event.preventDefault();
      const delta = (Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY) * unit;
      panBy(delta / Math.max(1, chart.pw) * (view.end - view.start));
    }
  }, {passive: false});
  canvas.addEventListener('keydown', event => {
    if (!session) return;
    const span = view.end - view.start, center = hover.time ?? (view.start + view.end) / 2;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      // Phím mũi tên dời con trỏ đọc giá trị; chạm mép khung nhìn thì dời khung theo
      const dir = event.key === 'ArrowLeft' ? -1 : 1;
      hover.chart = chart;
      hover.time = Math.min(Math.max(center + dir * span * (event.shiftKey ? 0.1 : 0.01), session.start), session.end);
      if (hover.time < view.start || hover.time > view.end) panBy(dir * span * 0.25);
    } else if (event.key === '+' || event.key === '=') zoomAround(center, 0.5);
    else if (event.key === '-' || event.key === '_') zoomAround(center, 2);
    else if (event.key === '0' || event.key === 'Home' || event.key === 'Escape') fit();
    else return;
    event.preventDefault();
    request();
  });
  canvas.addEventListener('focus', () => {
    if (!session || hover.chart === chart) return;
    hover.chart = chart; hover.time = (view.start + view.end) / 2;
    request();
  });
  canvas.addEventListener('blur', () => {
    if (hover.chart !== chart) return;
    hover.chart = null; hover.time = null;
    request();
  });
  new ResizeObserver(() => request()).observe(canvas);
}

$('review-left').addEventListener('click', () => panBy(-(view.end - view.start) / 2));
$('review-right').addEventListener('click', () => panBy((view.end - view.start) / 2));
$('review-zoom-in').addEventListener('click', () => zoomAround((view.start + view.end) / 2, 0.5));
$('review-zoom-out').addEventListener('click', () => zoomAround((view.start + view.end) / 2, 2));
$('review-fit').addEventListener('click', () => { if (session) fit(); });
$('review-prev').addEventListener('click', () => showMark(activeMark === null ? (primaryButton()?.presses.length ?? 0) - 1 : activeMark - 1));
$('review-next').addEventListener('click', () => showMark(activeMark === null ? 0 : activeMark + 1));
$('review-mark-body').addEventListener('click', event => {
  const row = event.target.closest('tr[data-k]');
  if (!row || !session) return;
  showMark(Number(row.dataset.k));
  $('review-toolbar').scrollIntoView({behavior: 'smooth', block: 'start'});
});
for (const id of ['review-imu-signal', 'review-imu-mode', 'review-emg-signal', 'review-emg-rms']) $(id).addEventListener('change', rebuild);

// ---------------------------------------------------------------- Nạp dữ liệu
async function load(sources) {
  if (loading || !sources.length) return;
  loading = true;
  $('review-body').classList.add('loading');
  const parts = [];
  try {
    for (const [i, source] of sources.entries()) {
      const label = (sources.length > 1 ? `(${i + 1}/${sources.length}) ` : '') + source.name;
      let shown = -1;
      setStatus(`Đang đọc ${label}…`);
      parts.push(await readCsv(await source.open(), source.name, source.size, progress => {
        const pct = progress === null ? -1 : Math.floor(progress * 100);
        if (pct !== shown) { shown = pct; setStatus(`Đang đọc ${label}… ${pct}%`); }
      }));
    }
    const next = buildSession(parts);
    if (!next) throw new Error('File đã chọn chưa có mẫu dữ liệu nào (chỉ có dòng tiêu đề).');
    session = next;
    hover.chart = null; hover.time = null;
    $('review-body').hidden = false;
    $('review-clear').hidden = false;
    $('review-dot').classList.add('ready');
    $('review-files').replaceChildren(...session.files.map(file => {
      const chip = el('span', 'review-file');
      chip.append(el('b', '', file.name), ` · ${KIND_LABEL[file.kind]} · ${count(file.rows)} dòng`);
      return chip;
    }));
    renderSummary();
    renderMarks();
    rebuild();
    fit();
    const loaded = [session.semg && `${count(session.semg.count)} mẫu sEMG`, session.imu && `${count(session.imu.count)} mẫu IMU`].filter(Boolean).join(' + ');
    setStatus([`Đã nạp ${loaded} · ${(session.end - session.start).toFixed(2)} s.`, ...session.warnings].join(' '), session.warnings.length > 0);
  } catch (error) {
    setStatus(error?.message || String(error), true);
  } finally {
    loading = false;
    $('review-body').classList.remove('loading');
  }
}

function loadFiles(list) {
  const files = [...list].filter(file => /\.csv$/i.test(file.name));
  if (!files.length) { setStatus('Chỉ nhận file .csv (Combined_*, sEMG_2000SPS_*, IMU_100Hz_*).', true); return; }
  load(files.map(file => ({name: file.name, size: file.size, open: async () => file.stream()})));
}

function sessionLabel(info) {
  const kinds = info.files.combined ? 'gộp' : [info.files.semg && 'sEMG', info.files.imu && 'IMU'].filter(Boolean).join(' + ');
  const bytes = Math.max(...Object.values(info.files).map(file => file.bytes));
  const extra = info.recording ? 'đang ghi' : bytes < 1024 ? 'trống'
    : finite(info.duration_s) ? `${info.duration_s.toFixed(1)} s` : `${(bytes / 1048576).toFixed(1)} MB`;
  return `${prettySession(info.id)} · ${extra} · ${kinds}`;
}

async function refreshSessions(select) {
  const controls = ['review-session-box', 'review-open', 'review-refresh'];
  let list;
  try {
    const response = await fetch('/api/sessions', {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    list = (await response.json()).sessions;
    if (!Array.isArray(list)) throw new Error('Danh sách phiên không hợp lệ');
  } catch {
    // Không chạy qua live_combined_visualizer.py: chỉ dùng chọn file / kéo thả
    for (const id of controls) $(id).hidden = true;
    return false;
  }
  sessions = list;
  const box = $('review-session'), keep = select ?? box.value;
  box.replaceChildren(...(sessions.length ? sessions.map(info => new Option(sessionLabel(info), info.id)) : [new Option('Chưa có phiên nào trong data/', '')]));
  box.value = sessions.some(info => info.id === keep) ? keep : sessions[0]?.id ?? '';
  for (const id of controls) $(id).hidden = false;
  $('review-open').disabled = !sessions.length;
  return true;
}

function openSession() {
  const info = sessions.find(entry => entry.id === $('review-session').value);
  if (!info) return;
  const files = info.files.combined ? [info.files.combined] : [info.files.semg, info.files.imu].filter(Boolean);
  load(files.map(file => ({name: file.name, size: file.bytes, open: async () => {
    const response = await fetch('/api/data/' + encodeURIComponent(file.name), {cache: 'no-store'});
    if (!response.ok || !response.body) throw new Error(`Không tải được ${file.name} (HTTP ${response.status}).`);
    return response.body;
  }})));
}

const drop = $('review-drop');
const hasFiles = event => [...(event.dataTransfer?.types ?? [])].includes('Files');
for (const type of ['dragenter', 'dragover']) {
  drop.addEventListener(type, event => { if (hasFiles(event)) { event.preventDefault(); drop.classList.add('dragover'); } });
}
drop.addEventListener('dragleave', event => { if (!drop.contains(event.relatedTarget)) drop.classList.remove('dragover'); });
drop.addEventListener('drop', event => {
  event.preventDefault(); event.stopPropagation();
  drop.classList.remove('dragover');
  loadFiles(event.dataTransfer.files);
});
// Thả file ra ngoài vùng nạp: vẫn nạp để trình duyệt không mở file thay cho dashboard
window.addEventListener('dragover', event => { if (hasFiles(event)) event.preventDefault(); });
window.addEventListener('drop', event => {
  if (!hasFiles(event)) return;
  event.preventDefault();
  window.showTab?.('review');
  loadFiles(event.dataTransfer.files);
});
$('review-pick').addEventListener('click', () => $('review-file').click());
$('review-file').addEventListener('change', event => { loadFiles(event.target.files); event.target.value = ''; });
$('review-open').addEventListener('click', openSession);
$('review-refresh').addEventListener('click', () => refreshSessions());
$('review-clear').addEventListener('click', () => {
  session = null; activeMark = null; hover.chart = null; hover.time = null;
  $('review-body').hidden = true;
  $('review-clear').hidden = true;
  $('review-files').replaceChildren();
  $('review-dot').classList.remove('ready');
  setStatus('Chưa nạp dữ liệu.');
});
// ads.mjs phát sự kiện này khi dừng ghi: phiên mới có ngay trong danh sách
window.addEventListener('dual-record-stopped', async event => {
  const id = event.detail?.session;
  if (await refreshSessions(id) && id) setStatus(`Phiên ${prettySession(id)} vừa ghi xong · bấm "Mở phiên" để xem lại.`);
});

// Nút "Xem lại phiên này" sau khi dừng ghi (ads.mjs): sang tab Xem lại và mở luôn phiên đó
window.openReviewSession = async id => {
  window.showTab?.('review');
  if (await refreshSessions(id) && $('review-session').value === id) openSession();
};
window.addEventListener('tab-shown', request);

refreshSessions();
