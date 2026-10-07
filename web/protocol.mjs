export const FIELDS = 'session,seq,host_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,temp_c,ax_kal_g,ay_kal_g,az_kal_g,gx_kal_dps,gy_kal_dps,gz_kal_dps,roll_acc_deg,pitch_acc_deg,roll_kal_deg,pitch_kal_deg,accel_trusted'.split(',');
const optional = new Set([16,23,24,25,26]);
export function parseLine(line) {
  line = line.trim();
  if (!line) return {type:'empty'};
  if (line.startsWith('#')) return {type:'log', text:line.slice(1).trim()};
  if (line.startsWith('session,')) {
    const names=line.split(',');
    return (names.length===17 || names.length===28) && names.every((v,i)=>v===FIELDS[i]) ? {type:'header'} : {type:'invalid'};
  }
  const parts=line.split(',');
  if (parts.length!==17 && parts.length!==28) return {type:'invalid'};
  const values=parts.map((v,i)=> optional.has(i) && /^nan$/i.test(v) ? null : v.trim()==='' ? NaN : Number(v));
  if (values.some((v,i)=>v===null ? !optional.has(i) : !Number.isFinite(v))) return {type:'invalid'};
  if (values.slice(0,4).some(v=>!Number.isSafeInteger(v)||v<0) || values[1]>0xFFFFFFFF || values[3]>0xFFFFFF) return {type:'invalid'};
  if (values.slice(4,10).some(v=>!Number.isInteger(v)||v < -32768||v>32767)) return {type:'invalid'};
  if (values.length===28 && ![0,1].includes(values[27])) return {type:'invalid'};
  return {type:'sample', values, filtered:values.length===28};
}
export class LineDecoder {
  constructor(onLine,onOverflow=()=>{}) { this.buffer=''; this.dropping=false; this.onLine=onLine; this.onOverflow=onOverflow; }
  push(text) {
    // Bound unterminated/corrupt lines without losing the next valid frame.
    for (const character of text) {
      if (character==='\n') { if (!this.dropping) this.onLine(this.buffer); this.buffer=''; this.dropping=false; }
      else if (!this.dropping) { this.buffer+=character; if(this.buffer.length>4096) { this.buffer=''; this.dropping=true; this.onOverflow(); } }
    }
  }
}
export class SampleStats {
  constructor() { this.reset(); }
  reset() { this.count=0; this.missing=0; this.maxGapUs=0; this.sps=0; this.previous=null; this.window=[]; }
  update(values) {
    const [session,seq,us]=values;
    const p=this.previous;
    const restarted=!!p && (session!==p[0] || us<=p[2] || ((seq-p[1])>>>0)>0x7FFFFFFF);
    if(restarted) this.reset();
    if(this.previous) {
      const gap=(seq-this.previous[1])>>>0;
      this.missing+=Math.max(0,gap-1);
      this.maxGapUs=Math.max(this.maxGapUs,us-this.previous[2]);
    }
    this.count++; this.previous=[session,seq,us]; this.window.push(us);
    while(this.window.length>2 && us-this.window[1]>=1000000) this.window.shift();
    const span=us-this.window[0];
    this.sps=span>=900000 ? (this.window.length-1)*1000000/span : 0;
    return restarted;
  }
}
