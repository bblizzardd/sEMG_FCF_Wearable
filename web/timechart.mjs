/**
 * timechart.mjs – Vẽ đồ thị theo thời gian dùng chung cho tab Trực tiếp và tab Xem lại:
 * nhiều track xếp chồng (mỗi track một trục Y riêng), làn trạng thái nút nhấn ở đáy
 * và vạch mốc tại mỗi lần nhấn chạy xuyên qua mọi track.
 */

export const LAYOUT = {L: 64, R: 18, T: 24, B: 28, LANE: 16, LANE_GAP: 10, TRACK_GAP: 20};
export const BUTTON_COLOR = '#cd6459';
const {L, R, T, B, LANE, LANE_GAP, TRACK_GAP} = LAYOUT;
const INK = '#192e32', MUTED = '#7d8d87', GRID = '#edf1ee', ZERO = '#d6dfda';

/** Chiều cao canvas cho n track, mỗi track cao trackH px. */
export const chartHeight = (n, trackH) => !n ? 150 : T + B + LANE + LANE_GAP + (n - 1) * TRACK_GAP + n * trackH;

export function lowerBound(a, v) {
  let lo = 0, hi = a.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] < v) lo = mid + 1; else hi = mid; }
  return lo;
}

function canvasContext(canvas) {
  const size = canvas.getBoundingClientRect(), ratio = Math.min(devicePixelRatio || 1, 2);
  const w = Math.max(1, size.width), h = Math.max(1, size.height);
  if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
    canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio);
  }
  const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, w, h);
  return {ctx, w, h};
}

function niceStep(span, target) {
  const raw = span / Math.max(1, target), mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag;
}
const decimals = step => Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9)));
const tickText = (v, step, digits) => (Math.abs(v) < step * 1e-6 ? 0 : v).toFixed(digits);

function visibleRange(t, start, end) {
  return [Math.max(0, lowerBound(t, start) - 1), Math.min(t.length - 1, lowerBound(t, end))];
}

function yRange(track, start, end) {
  if (track.fixed) return track.fixed;
  // Bỏ qua mẫu bị đánh dấu exclude (vd lead-off) khi tự co giãn trục, nếu còn mẫu tốt trong khung nhìn
  let lo = Infinity, hi = -Infinity, cleanLo = Infinity, cleanHi = -Infinity;
  const exclude = track.exclude;
  for (const series of track.series) {
    const [i0, i1] = visibleRange(series.t, start, end), v = series.v;
    for (let i = i0; i <= i1; i++) {
      const x = v[i];
      if (x !== x || x === null) continue;
      if (x < lo) lo = x;
      if (x > hi) hi = x;
      if (exclude && exclude[i] !== 1) {
        if (x < cleanLo) cleanLo = x;
        if (x > cleanHi) cleanHi = x;
      }
    }
  }
  if (exclude && cleanLo <= cleanHi) { lo = cleanLo; hi = cleanHi; }
  if (!(lo <= hi)) { lo = -track.min / 2; hi = track.min / 2; }
  const mid = (lo + hi) / 2, half = Math.max(hi - lo, track.min) / 2 * 1.16;
  return [mid - half, mid + half];
}

function drawSeries(ctx, series, xOf, yOf, gap, pw, start, end) {
  const {t, v} = series, [i0, i1] = visibleRange(t, start, end), n = i1 - i0 + 1;
  if (n <= 0) return;
  ctx.save();
  ctx.strokeStyle = series.color; ctx.globalAlpha = series.alpha ?? 1; ctx.lineWidth = series.width ?? 1.6;
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  ctx.setLineDash(series.dash ?? []);
  ctx.beginPath();
  let open = false, prevT = -Infinity;
  const bad = value => value !== value || value === null;
  if (n <= pw * 1.5) {
    for (let i = i0; i <= i1; i++) {
      const value = v[i];
      if (bad(value) || t[i] - prevT > gap) open = false;
      prevT = t[i];
      if (bad(value)) continue;
      const x = xOf(t[i]), y = yOf(value);
      if (open) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      open = true;
    }
  } else {
    // Nhiều mẫu hơn điểm ảnh: mỗi cột điểm ảnh vẽ 1 vạch min-max để không mất đỉnh tín hiệu
    let col = null, first = 0, mn = 0, mx = 0, last = 0;
    const flush = () => {
      if (col === null) return;
      const x = col + 0.5;
      if (open) ctx.lineTo(x, yOf(first)); else ctx.moveTo(x, yOf(first));
      ctx.lineTo(x, yOf(mn)); ctx.lineTo(x, yOf(mx)); ctx.lineTo(x, yOf(last));
      open = true; col = null;
    };
    for (let i = i0; i <= i1; i++) {
      const value = v[i];
      if (bad(value) || t[i] - prevT > gap) { flush(); open = false; }
      prevT = t[i];
      if (bad(value)) continue;
      const c = Math.floor(xOf(t[i]));
      if (c !== col) { flush(); col = c; first = mn = mx = last = value; }
      else { if (value < mn) mn = value; else if (value > mx) mx = value; last = value; }
    }
    flush();
  }
  ctx.stroke();
  // Phóng to tới mức thấy từng mẫu: đánh dấu điểm lấy mẫu
  if (series.primary && pw / n >= 9) {
    ctx.setLineDash([]);
    ctx.fillStyle = series.color; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.globalAlpha = 1;
    for (let i = i0; i <= i1; i++) {
      if (bad(v[i])) continue;
      ctx.beginPath(); ctx.arc(xOf(t[i]), yOf(v[i]), 2.5, 0, Math.PI * 2); ctx.stroke(); ctx.fill();
    }
  }
  ctx.restore();
}

function fillRuns(ctx, runs, xOf, start, end, top, height, color) {
  ctx.fillStyle = color;
  for (const run of runs) {
    if (run.end < start || run.start > end) continue;
    const x0 = xOf(run.start);
    ctx.fillRect(x0, top, Math.max(1, xOf(run.end) - x0), height);
  }
}

/**
 * spec: {start, end, tracks, button: {runs, presses} | null, bands, cursor, selection: [a, b] | null,
 *        activeMark, empty, tickFormat}
 * track: {label, min, digits, gap, series: [{t, v, color, width, alpha, dash, primary}], exclude?, fixed?: [lo, hi]}
 * Trả về độ rộng vùng vẽ (px) để tính toạ độ chuột.
 */
export function drawTimeChart(canvas, spec) {
  const {ctx, w, h} = canvasContext(canvas), pw = w - L - R, tracks = spec.tracks ?? [];
  if (pw <= 10) return pw;
  if (!tracks.length) {
    ctx.fillStyle = MUTED; ctx.font = '13px Segoe UI'; ctx.textAlign = 'center';
    ctx.fillText(spec.empty ?? '', w / 2, h / 2 + 4);
    return pw;
  }
  const {start, end} = spec, span = Math.max(1e-9, end - start), xOf = t => L + (t - start) / span * pw;
  const laneTop = h - B - LANE, plotBottom = laneTop - LANE_GAP, button = spec.button;
  const trackH = (plotBottom - T - TRACK_GAP * (tracks.length - 1)) / tracks.length;

  // Nền: đoạn đánh dấu (vd lead-off, xám) và lúc đang giữ nút (đỏ nhạt) phủ qua mọi track
  ctx.save(); ctx.beginPath(); ctx.rect(L, T, pw, plotBottom - T); ctx.clip();
  fillRuns(ctx, spec.bands ?? [], xOf, start, end, T, plotBottom - T, 'rgba(118,132,137,.15)');
  if (button) fillRuns(ctx, button.runs, xOf, start, end, T, plotBottom - T, 'rgba(205,100,89,.10)');
  ctx.restore();

  // Lưới dọc theo vạch thời gian + nhãn trục thời gian
  const step = niceStep(span, Math.max(2, Math.floor(pw / 90))), digits = decimals(step);
  const tickLabel = spec.tickFormat ?? (v => tickText(v, step, digits));
  ctx.font = '10px Segoe UI'; ctx.lineWidth = 1; ctx.strokeStyle = '#f2f5f3'; ctx.fillStyle = MUTED;
  for (let k = Math.ceil(start / step); k * step <= end + step * 1e-9; k++) {
    const x = Math.round(xOf(k * step)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, plotBottom); ctx.stroke();
    ctx.textAlign = x > w - R - 14 ? 'right' : 'center';
    ctx.fillText(tickLabel(k * step), Math.min(x, w - 2), h - 9);
  }

  tracks.forEach((track, i) => {
    const top = T + i * (trackH + TRACK_GAP);
    const [lo, hi] = yRange(track, start, end), yOf = v => top + (hi - v) / (hi - lo) * trackH;
    const target = Math.max(2, Math.floor(trackH / 30));
    let yStep = niceStep(hi - lo, target);
    if (Math.floor(hi / yStep) - Math.ceil(lo / yStep) < 2) yStep = niceStep(hi - lo, target * 2);  // luôn ≥ 3 vạch chia
    const yDigits = decimals(yStep);
    ctx.font = '10px Segoe UI'; ctx.textAlign = 'right'; ctx.lineWidth = 1;
    for (let k = Math.ceil(lo / yStep); k * yStep <= hi; k++) {
      const y = Math.round(yOf(k * yStep)) + 0.5;
      ctx.strokeStyle = k === 0 ? ZERO : GRID;
      ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + pw, y); ctx.stroke();
      ctx.fillStyle = MUTED; ctx.fillText(tickText(k * yStep, yStep, yDigits), L - 8, y + 3);
    }
    ctx.save(); ctx.beginPath(); ctx.rect(L, top, pw, trackH); ctx.clip();
    for (const series of track.series) drawSeries(ctx, series, xOf, yOf, track.gap ?? Infinity, pw, start, end);
    ctx.restore();
    // Tên track ở góc trên, nền trắng mờ để chữ không lẫn vào đường dữ liệu
    ctx.font = '600 11px Segoe UI'; ctx.textAlign = 'left';
    ctx.fillStyle = 'rgba(255,255,255,.88)'; ctx.fillRect(L + 4, top + 2, ctx.measureText(track.label).width + 12, 18);
    ctx.fillStyle = '#3f574e'; ctx.fillText(track.label, L + 10, top + 15);
  });

  // Làn trạng thái nút ở đáy
  ctx.fillStyle = '#f1f4f2'; ctx.fillRect(L, laneTop, pw, LANE);
  ctx.font = '600 10px Segoe UI'; ctx.fillStyle = '#5f7169'; ctx.textAlign = 'right';
  ctx.fillText('Nút', L - 8, laneTop + LANE / 2 + 4);
  if (!button) {
    ctx.font = '10px Segoe UI'; ctx.fillStyle = MUTED; ctx.textAlign = 'left';
    ctx.fillText(spec.noButton ?? 'Không có dữ liệu nút nhấn', L + 8, laneTop + LANE / 2 + 4);
  } else {
    ctx.save(); ctx.beginPath(); ctx.rect(L, laneTop, pw, LANE); ctx.clip();
    ctx.fillStyle = BUTTON_COLOR;
    for (const run of button.runs) {
      if (run.end < start || run.start > end) continue;
      const x0 = xOf(run.start);
      ctx.beginPath(); ctx.roundRect(x0, laneTop + 2, Math.max(3, xOf(run.end) - x0), LANE - 4, 3); ctx.fill();
    }
    ctx.restore();
    // Vạch mốc tại mỗi lần nhấn (cạnh 0 → 1)
    ctx.save(); ctx.font = '600 10px Segoe UI'; ctx.textAlign = 'center';
    let lastLabel = -Infinity;
    for (const press of button.presses) {
      if (press.start < start || press.start > end) continue;
      const x = Math.round(xOf(press.start)) + 0.5, active = press.k !== undefined && press.k - 1 === spec.activeMark;
      ctx.strokeStyle = BUTTON_COLOR; ctx.globalAlpha = active ? 1 : 0.75; ctx.lineWidth = active ? 1.6 : 1;
      ctx.setLineDash(active ? [] : [4, 3]);
      ctx.beginPath(); ctx.moveTo(x, T - 6); ctx.lineTo(x, laneTop + LANE); ctx.stroke();
      if (press.k !== undefined && (x - lastLabel >= 28 || active)) {
        ctx.globalAlpha = 1; ctx.fillStyle = active ? INK : '#5f7169';
        ctx.fillText('#' + press.k, x, T - 10);
        lastLabel = x;
      }
    }
    ctx.restore();
  }

  // Vùng đang kéo chọn hoặc con trỏ đọc giá trị
  const bottom = laneTop + LANE;
  ctx.setLineDash([]); ctx.lineWidth = 1;
  if (spec.selection) {
    const a = xOf(Math.min(...spec.selection)), b = xOf(Math.max(...spec.selection));
    ctx.fillStyle = 'rgba(8,123,101,.09)'; ctx.fillRect(a, T, b - a, bottom - T);
    ctx.strokeStyle = 'rgba(8,123,101,.6)';
    for (const x of [a, b]) { ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, T); ctx.lineTo(Math.round(x) + 0.5, bottom); ctx.stroke(); }
  } else if (spec.cursor !== null && spec.cursor !== undefined && spec.cursor >= start && spec.cursor <= end) {
    const x = Math.round(xOf(spec.cursor)) + 0.5;
    ctx.strokeStyle = 'rgba(25,46,50,.45)';
    ctx.beginPath(); ctx.moveTo(x, T - 4); ctx.lineTo(x, bottom); ctx.stroke();
  }
  return pw;
}
