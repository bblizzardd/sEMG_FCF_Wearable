/**
 * review-data.mjs – Đọc lại CSV đã ghi để xem toàn bộ phiên (không đụng DOM).
 * Nhận file gộp Combined_*.csv (sEMG + IMU + nút), sEMG_2000SPS_*.csv và IMU_100Hz_*.csv
 * (kể cả bmi160_*.csv tải từ trình duyệt). Mọi file dùng đồng hồ esp_timer (µs) của ESP32
 * nên các file của cùng một phiên tự khớp trên một trục thời gian.
 */

export const IMU_CHANNELS = [
  'ax_g', 'ay_g', 'az_g', 'gx_dps', 'gy_dps', 'gz_dps',
  'ax_kal_g', 'ay_kal_g', 'az_kal_g', 'gx_kal_dps', 'gy_kal_dps', 'gz_kal_dps',
  'roll_acc_deg', 'pitch_acc_deg', 'roll_kal_deg', 'pitch_kal_deg',
];
const REBOOT_US = 1e6;      // thời gian lùi quá 1 s: ESP32 khởi động lại giữa phiên
const RMS_WINDOW_S = 0.1;   // bao hình RMS 100 ms

class Column {
  constructor(Type) { this.Type = Type; this.data = new Type(4096); this.length = 0; }
  push(value) {
    if (this.length === this.data.length) {
      const grown = new this.Type(this.data.length * 2);
      grown.set(this.data);
      this.data = grown;
    }
    this.data[this.length++] = value;
  }
  last() { return this.length ? this.data[this.length - 1] : -Infinity; }
  done() { return this.data.slice(0, this.length); }
}

// Number('') = 0 nên ô trống phải đổi thành NaN trước
const num = text => text === undefined || text === '' ? NaN : Number(text);
const flag = text => text === '1' ? 1 : text === '0' ? 0 : -1;

// Nối tiếp các đoạn khi ESP32 khởi động lại để trục thời gian luôn tăng
class Clock {
  constructor() { this.offset = 0; this.last = -Infinity; this.resets = 0; }
  map(us) {
    let t = us + this.offset;
    if (t < this.last - REBOOT_US) {
      this.offset = this.last - us + 1000;
      t = us + this.offset;
      this.resets++;
    }
    if (t > this.last) this.last = t;
    return t;
  }
}

class SemgCollector {
  constructor(col) {
    this.col = col;
    this.t = new Column(Float64Array); this.filt = new Column(Float32Array);
    this.raw = new Column(Float32Array); this.loff = new Column(Int8Array);
    this.lastIdx = null; this.dropped = 0;
  }
  add(t, f) {
    if (t <= this.t.last()) return;
    const idx = num(f[this.col.sample_idx]);
    if (this.lastIdx !== null && idx - this.lastIdx > 1) this.dropped += idx - this.lastIdx - 1;
    if (Number.isFinite(idx)) this.lastIdx = idx;
    this.t.push(t);
    this.filt.push(num(f[this.col.ch2_filtered16]));
    this.raw.push(num(f[this.col.ch2_raw16]));
    this.loff.push(flag(f[this.col.lead_off]));
  }
  done() {
    return {tUs: this.t.done(), filt: this.filt.done(), raw: this.raw.done(), loff: this.loff.done(), dropped: this.dropped};
  }
}

class ImuCollector {
  constructor(col) {
    this.col = col;
    this.t = new Column(Float64Array);
    this.ch = Object.fromEntries(IMU_CHANNELS.map(name => [name, new Column(Float32Array)]));
    this.lastSeq = null; this.dropped = 0;
  }
  add(t, f, seq) {
    if (t <= this.t.last()) return;
    if (this.lastSeq !== null && seq - this.lastSeq > 1) this.dropped += seq - this.lastSeq - 1;
    if (Number.isFinite(seq)) this.lastSeq = seq;
    this.t.push(t);
    for (const name of IMU_CHANNELS) this.ch[name].push(num(f[this.col[name]]));
  }
  done() {
    return {
      tUs: this.t.done(),
      ch: Object.fromEntries(IMU_CHANNELS.map(name => [name, this.ch[name].done()])),
      dropped: this.dropped,
    };
  }
}

class ButtonCollector {
  constructor(index) { this.index = index; this.t = new Column(Float64Array); this.s = new Column(Int8Array); }
  add(t, f) {
    if (t < this.t.last()) return;  // dòng IMU-only ghi trễ vài ms trong file gộp
    this.t.push(t);
    this.s.push(flag(f[this.index]));
  }
  done() { return {tUs: this.t.done(), s: this.s.done()}; }
}

export function detectKind(header) {
  const has = name => header.includes(name);
  if (has('timestamp_us') && has('imu_seq')) return 'combined';
  if (has('timestamp_us') && (has('ch2_filtered16') || has('ch2_raw16'))) return 'semg';
  if (has('host_us') && has('ax_g')) return 'imu';
  return null;
}

function createSink(kind, header) {
  const col = Object.fromEntries(header.map((name, i) => [name, i]));
  const clock = new Clock();
  const button = col.button_state !== undefined ? new ButtonCollector(col.button_state) : null;
  const semg = kind !== 'imu' ? new SemgCollector(col) : null;
  const imu = kind !== 'semg' ? new ImuCollector(col) : null;
  let lastImuSeq = '';
  const row = f => {
    if (kind === 'imu') {
      const host = num(f[col.host_us]);
      if (!Number.isFinite(host)) return false;
      const t = clock.map(host);
      imu.add(t, f, num(f[col.seq]));
      button?.add(t, f);
      return true;
    }
    const ts = num(f[col.timestamp_us]);
    if (!Number.isFinite(ts)) return false;
    const t = clock.map(ts);
    if (kind === 'semg' || f[col.sample_idx]) semg.add(t, f);
    if (kind === 'combined') {
      // Mẫu IMU lặp lại trên ~20 dòng sEMG: chỉ lấy khi imu_seq đổi
      const seqText = f[col.imu_seq];
      if (seqText && seqText !== lastImuSeq) {
        lastImuSeq = seqText;
        const host = num(f[col.imu_host_us]);
        if (Number.isFinite(host)) imu.add(host + clock.offset, f, num(seqText));
      }
    }
    button?.add(t, f);
    return true;
  };
  const finish = () => ({
    semg: semg?.done() ?? null,
    imu: imu?.done() ?? null,
    button: button?.done() ?? null,
    resets: clock.resets,
  });
  return {row, finish, columns: header.length};
}

/** Đọc một luồng CSV theo từng đoạn; onProgress nhận tỉ lệ 0..1 (nếu biết kích thước). */
export async function readCsv(stream, name, size, onProgress) {
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let carry = '', sink = null, kind = null, read = 0, rows = 0, bad = 0;
  const handle = (line, final = false) => {
    if (line.endsWith('\r')) line = line.slice(0, -1);
    if (!line || line.charCodeAt(0) === 35 /* # */) return;
    if (!sink) {
      const header = line.split(',').map(cell => cell.trim());
      kind = detectKind(header);
      if (!kind) throw new Error(`Không nhận ra định dạng của ${name}: cần cột timestamp_us (sEMG / file gộp) hoặc host_us (IMU).`);
      sink = createSink(kind, header);
      return;
    }
    const fields = line.split(',');
    // Dòng cuối không có xuống dòng = file đang ghi dở: bỏ nếu thiếu cột
    if (final && fields.length !== sink.columns) return;
    if (sink.row(fields)) rows++; else bad++;
  };
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    read += value.length;
    const text = carry + value;
    let start = 0, nl;
    while ((nl = text.indexOf('\n', start)) !== -1) {
      handle(text.slice(start, nl));
      start = nl + 1;
    }
    carry = text.slice(start);
    onProgress?.(size ? Math.min(1, read / size) : null);
  }
  if (carry) handle(carry, true);
  if (!sink) throw new Error(`${name} trống, chưa có dòng tiêu đề.`);
  return {name, kind, rows, bad, ...sink.finish()};
}

const sessionOf = name => name.match(/\d{8}_\d{6}/)?.[0] ?? null;

function lowerBound(a, v) {
  let lo = 0, hi = a.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] < v) lo = mid + 1; else hi = mid; }
  return lo;
}

/** Các đoạn liên tục có giá trị 1; edge = bắt đầu từ cạnh 0 → 1 thật (không phải đầu file). */
export function runsOf(t, s) {
  const runs = [];
  let open = null, prev = -1;
  for (let i = 0; i < s.length; i++) {
    const v = s[i];
    if (v === 1) {
      if (!open) open = {start: t[i], end: t[i], edge: prev === 0, released: false};
      else open.end = t[i];
    } else if (open) {
      open.end = t[i];
      open.released = v === 0;
      runs.push(open);
      open = null;
    }
    prev = v;
  }
  if (open) runs.push(open);
  return runs;
}

function movingRms(v, window) {
  const n = v.length, out = new Float32Array(n), sum = new Float64Array(n + 1), half = Math.max(1, window >> 1);
  for (let i = 0; i < n; i++) { const x = v[i]; sum[i + 1] = sum[i] + (x === x ? x * x : 0); }
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, i - half), b = Math.min(n, i + half + 1);
    out[i] = Math.sqrt((sum[b] - sum[a]) / (b - a));
  }
  return out;
}

const rateOf = t => t.length > 1 && t[t.length - 1] > t[0] ? (t.length - 1) / (t[t.length - 1] - t[0]) : NaN;

function buttonInfo(data, origin, source) {
  if (!data || !data.s.some(v => v >= 0)) return null;
  const t = Float64Array.from(data.tUs, us => (us - origin) / 1e6);
  const runs = runsOf(t, data.s);
  const presses = runs.filter(run => run.edge);
  presses.forEach((press, k) => { press.k = k + 1; press.next = presses[k + 1]?.start ?? null; });
  return {t, s: data.s, runs, presses, source};
}

/** Gộp kết quả các file của 1 lần nạp thành 1 phiên: sEMG, IMU và nút của từng bộ dữ liệu. */
export function buildSession(parts) {
  const warnings = [];
  let semgPart = null, imuPart = null;
  // File gộp xử lý sau cùng để luôn được ưu tiên nếu nạp lẫn file riêng
  for (const part of [...parts].sort((a, b) => (a.kind === 'combined') - (b.kind === 'combined'))) {
    if (part.semg?.tUs.length) {
      if (semgPart && semgPart !== part) warnings.push(`Chỉ dùng 1 nguồn sEMG: bỏ qua ${semgPart.name}.`);
      semgPart = part;
    }
    if (part.imu?.tUs.length) {
      if (imuPart && imuPart !== part) warnings.push(`Chỉ dùng 1 nguồn IMU: bỏ qua ${imuPart.name}.`);
      imuPart = part;
    }
    if (part.bad) warnings.push(`${part.name}: bỏ qua ${part.bad.toLocaleString('vi-VN')} dòng hỏng.`);
    if (part.resets) warnings.push(`${part.name}: thời gian bị reset ${part.resets} lần (ESP32 khởi động lại?), các đoạn được nối tiếp nhau.`);
  }
  if (!semgPart && !imuPart) return null;

  const firsts = [semgPart?.semg.tUs[0], imuPart?.imu.tUs[0]].filter(Number.isFinite);
  const lasts = [semgPart?.semg.tUs.at(-1), imuPart?.imu.tUs.at(-1)].filter(Number.isFinite);
  const origin = Math.min(...firsts);
  const toSec = tUs => Float64Array.from(tUs, us => (us - origin) / 1e6);

  let semg = null, imu = null;
  if (semgPart) {
    const d = semgPart.semg, t = toSec(d.tUs), rate = rateOf(t);
    const loffCount = d.loff.reduce((n, v) => n + (v === 1), 0);
    semg = {
      t, filt: d.filt, raw: d.raw, loff: d.loff, count: t.length, rate, dropped: d.dropped,
      rms: movingRms(d.filt, Math.round(RMS_WINDOW_S * (Number.isFinite(rate) ? rate : 2000))),
      loffRuns: runsOf(t, d.loff), loffFraction: loffCount / t.length, file: semgPart.name,
    };
  }
  if (imuPart) {
    const d = imuPart.imu, t = toSec(d.tUs);
    const has = Object.fromEntries(IMU_CHANNELS.map(name => [name, d.ch[name].some(Number.isFinite)]));
    imu = {t, ch: d.ch, has, count: t.length, rate: rateOf(t), dropped: d.dropped, file: imuPart.name};
  }

  // Nút của từng bộ dữ liệu; file gộp chỉ có 1 cột button_state (2000 SPS) dùng chung cho cả hai
  const semgButton = semgPart ? buttonInfo(semgPart.button, origin, semgPart.kind === 'combined' ? 'gộp' : 'sEMG') : null;
  const imuButton = imuPart === semgPart ? semgButton
    : imuPart ? buttonInfo(imuPart.button, origin, imuPart.kind === 'combined' ? 'gộp' : 'IMU') : null;

  if (semg && imu && (semg.t.at(-1) < imu.t[0] || imu.t.at(-1) < semg.t[0])) {
    warnings.push('sEMG và IMU không trùng khoảng thời gian nào: có thể không cùng một phiên.');
  }
  const ids = new Set([semgPart?.name, imuPart?.name].filter(Boolean).map(sessionOf).filter(Boolean));
  if (ids.size > 1) warnings.push(`Các file thuộc ${ids.size} phiên khác nhau (${[...ids].join(', ')}).`);

  return {
    semg, imu, buttons: {semg: semgButton, imu: imuButton},
    start: 0, end: (Math.max(...lasts) - origin) / 1e6,
    files: parts.map(part => ({name: part.name, kind: part.kind, rows: part.rows})),
    session: [...ids][0] ?? null, warnings,
  };
}

/** Chỉ số mẫu gần time nhất trong mảng thời gian tăng dần. */
export function nearestIndex(t, time) {
  const i = lowerBound(t, time);
  if (i <= 0) return 0;
  if (i >= t.length) return t.length - 1;
  return time - t[i - 1] <= t[i] - time ? i - 1 : i;
}

/** Trạng thái giữ tới mẫu kế tiếp: chỉ số mẫu cuối cùng có t <= time (-1 nếu chưa có). */
export function heldIndex(t, time) {
  return lowerBound(t, time + 1e-9) - 1;
}

export {lowerBound};
