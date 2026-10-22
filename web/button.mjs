/**
 * button.mjs – Thẻ "Nút mốc Rep" của tab Trực tiếp: trạng thái nhấn/thả, số lần nhấn, lần nhấn gần nhất.
 * Nhận /api/button/stream (SSE, event: button). Trạng thái nút theo thời gian được vẽ ngay trong
 * đồ thị sEMG (ads.mjs) và đồ thị BMI160 (app.mjs).
 */

const $ = id => document.getElementById(id);
let latest = null, lastArrival = 0, lastTs = null;

function onButton(d) {
  latest = d;
  if (d.connected && (d.state === 0 || d.state === 1) && d.ts_us !== lastTs) {
    lastTs = d.ts_us;
    lastArrival = performance.now();
  }
}

function render() {
  const d = latest, hasButton = d && (d.state === 0 || d.state === 1);
  const fresh = hasButton && d.connected && performance.now() - lastArrival < 1500;
  const state = $('button-state');
  state.textContent = !hasButton ? 'Chưa có dữ liệu' : !fresh ? 'Không có mẫu mới' : d.state ? '● Đang nhấn' : 'Đã thả';
  state.classList.toggle('pressed', !!fresh && d.state === 1);
  $('button-count').textContent = hasButton ? d.presses.toLocaleString('vi-VN') : '—';
  $('button-last').textContent = hasButton && d.last_press_us ? ((d.ts_us - d.last_press_us) / 1e6).toFixed(1) + ' s trước' : '—';
  $('button-live-dot').className = 'state-dot' + (!fresh ? '' : d.state ? ' red' : ' green');
}

function connect() {
  const es = new EventSource('/api/button/stream');
  es.addEventListener('button', e => { try { onButton(JSON.parse(e.data)); } catch {} });
  es.onerror = () => { es.close(); setTimeout(connect, 2000); };
}

$('button-reset').addEventListener('click', () => { fetch('/api/button/reset').catch(() => {}); });
setInterval(render, 50);
connect();
