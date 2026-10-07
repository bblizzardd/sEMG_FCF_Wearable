import {FIELDS, parseLine, LineDecoder, SampleStats} from './protocol.mjs';
const $ = id => document.getElementById(id);
const ui = Object.fromEntries(['connect','demo','status','status-dot','source','notice','sps','sample-count','lost-count','temp','norm','gravity-caption','rate-caption','session-label','display','window','pause','record','export','record-status','record-count','record-dot','io-errors','serial-drops','invalid','max-gap','reset-filter','device-status','roll','pitch','tilt-note','logs','last-log','serial-port','port-controls'].map(id=>[id,$(id)]));
let port=null, reader=null, readTask=null, closing=false, connecting=false;
let bridgeMode=false, bridgeToken='', bridgeStream=null, bridgeDevice=null, bridgeError='';
let demoTimer=null, demoStart=0, demoSeq=0, demoFiltered=null;
let sourceKind='none';
let samples=[], latest=null, stats=new SampleStats(), lastArrival=0, invalid=0;
let paused=false, frozen=[], recording=false, recorded=[], logLines=[], firmwareCounters=null;
const COLORS=['#518be5','#24a887','#e5a345'];
const finite = v => typeof v==='number' && Number.isFinite(v);
const fmt = (v,d=2) => finite(v) ? v.toFixed(d) : '—';
function notice(text,warn=false) { ui.notice.textContent=text; ui.notice.classList.toggle('warn',warn); }
function log(text) { logLines.push(text); if(logLines.length>80)logLines.shift(); ui.logs.textContent=logLines.join('\n');ui['last-log'].textContent=text; }
function connection(text,color='') { ui.status.textContent=text; ui['status-dot'].className='dot '+color; }
function resetData() { samples=[]; latest=null;stats.reset();lastArrival=0;invalid=0;firmwareCounters=null;frozen=[];paused=false;ui.pause.textContent='Ⅱ Tạm dừng đồ thị'; }
function download(rows,prefix) {
  if(!rows.length)return;
  const contents=[FIELDS.join(','),...rows.map(row=>FIELDS.map((_,i)=>row[i]===null?'nan':row[i]??'').join(','))].join('\r\n')+'\r\n';
  const url=URL.createObjectURL(new Blob([contents],{type:'text/csv;charset=utf-8'}));
  const anchor=document.createElement('a');anchor.href=url;anchor.download=prefix+'_'+new Date().toISOString().replace(/[:.]/g,'-')+'.csv';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
function finishRecording(reason='Đã dừng ghi và tải CSV.') {
  if(!recording)return;
  recording=false;download(recorded,'bmi160');ui.record.textContent='● Bắt đầu ghi CSV';ui['record-dot'].className='dot';ui['record-status'].textContent='Đã tải '+recorded.length.toLocaleString('vi-VN')+' mẫu';recorded=[];notice(reason);
}
function accept(line) {
  const event=parseLine(line);
  if(event.type==='log') {
    log(event.text);
    const io=event.text.match(/io_errors=(\d+)/), drop=event.text.match(/serial_drops=(\d+)/);
    if(io||drop)firmwareCounters={io:io?Number(io[1]):firmwareCounters?.io??null,drop:drop?Number(drop[1]):firmwareCounters?.drop??null};
    return;
  }
  if(event.type==='invalid') { invalid++;return; }
  if(event.type!=='sample')return;
  const values=event.values;
  // Never mix old and extended schemas, MCU restarts, or sensor sessions in a recording.
  if(recording && latest && (values[0]!==latest[0] || values[2]<=latest[2] || values.length!==latest.length)) finishRecording('Phiên cảm biến thay đổi: CSV đã được tải. Bắt đầu phiên ghi mới khi sẵn sàng.');
  const restarted=stats.update(values);
  if(restarted) { samples=[];firmwareCounters=null;frozen=[];log('Bắt đầu session '+values[0]+'.'); }
  latest=values;lastArrival=performance.now();samples.push(values);
  if(samples.length>2500)samples.splice(0,samples.length-2500);
  if(recording) {
    recorded.push(values);
    ui['record-count'].textContent=recorded.length.toLocaleString('vi-VN')+' mẫu';
    if(recorded.length>=100000)finishRecording('Đã đạt 100.000 mẫu; CSV được tải và phiên ghi đã dừng.');
  }
  if(!event.filtered && samples.length===1)notice('Firmware cũ: đang xem tín hiệu gốc. Nạp firmware Kalman mới để có dữ liệu lọc và góc nghiêng.',true);
}
async function send(command) {
  if(bridgeMode) {
    if(!port)return;
    try { await bridgeRequest('/api/command',{command}); } catch(error) { notice(error.message,true); }
    return;
  }
  if(!port?.writable || closing)return;
  const writer=port.writable.getWriter();
  try { await writer.write(new TextEncoder().encode(command)); }
  catch(error) { notice('Gửi lệnh thất bại: '+error.message,true); }
  finally { writer.releaseLock(); }
}
async function readLive(currentPort) {
  const decoder=new TextDecoder();const lines=new LineDecoder(accept,()=>invalid++);
  try {
    while(currentPort.readable && !closing) {
      reader=currentPort.readable.getReader();
      try {
        while(!closing) { const {value,done}=await reader.read();if(done)break;lines.push(decoder.decode(value,{stream:true})); }
      } catch(error) {
        if(!closing)log('Serial: '+error.message);
        if(!currentPort.readable)break;
      } finally { reader.releaseLock();reader=null; }
    }
  } finally {
    finishRecording('Kết nối đã đóng; dữ liệu đã ghi được tải xuống.');
    try { await currentPort.close(); } catch(error) { log('Đóng cổng: '+error.message); }
    if(port===currentPort)port=null;
    closing=false;ui.connect.disabled=false;ui.connect.textContent='↔ Kết nối cảm biến';ui.demo.disabled=false;
    connection('Đã ngắt kết nối');ui.source.textContent='Dữ liệu vừa nhận vẫn giữ trên đồ thị';
  }
}
async function disconnect() {
  closing=true;ui.connect.disabled=true;
  try { if(reader)await reader.cancel(); if(readTask)await readTask; }
  catch(error) { notice(error.message,true); }
}
ui.connect.addEventListener('click',async()=>{
  if(bridgeMode) {
    if(connecting)return;
    connecting=true;ui.connect.disabled=true;
    try {
      if(port) await bridgeRequest('/api/disconnect',{});
      else { stopDemo();await bridgeRequest('/api/connect',{port:ui['serial-port'].value});notice('Đang mở cổng USB-UART qua Python…'); }
    } catch(error) { notice(error.message,true); }
    finally { connecting=false;ui.connect.disabled=false; }
    return;
  }
  if(port) { await disconnect();return; }
  if(connecting)return;
  if(!navigator.serial || !window.isSecureContext) { notice('Trình duyệt chưa hỗ trợ Serial hoặc trang chưa ở localhost/HTTPS. Mở bằng Chrome/Edge tại http://localhost:8765.',true);return; }
  stopDemo();connecting=true;ui.connect.disabled=true;
  let selectedPort;
  try {
    selectedPort=await navigator.serial.requestPort();
    await selectedPort.open({baudRate:460800,bufferSize:65536});
    // Keep DTR/RTS deasserted so USB-UART boards do not stay in reset/boot mode.
    try { await selectedPort.setSignals({dataTerminalReady:false,requestToSend:false}); } catch(error) { log('Adapter không hỗ trợ DTR/RTS: '+error.message); }
    resetData();sourceKind='serial';port=selectedPort;closing=false;
    ui.connect.textContent='× Ngắt kết nối';ui.demo.disabled=true;
    connection('Đã mở cổng · chờ dữ liệu','amber');
    const info=port.getInfo();ui.source.textContent='USB-UART'+(info.usbVendorId?' · VID '+info.usbVendorId.toString(16).toUpperCase():'');
    notice('Đang đọc BMI160 trực tiếp. Để Serial Monitor đóng trong khi sử dụng web.');
    readTask=readLive(selectedPort);
    // Metadata works even if the board did not reset when the port opened.
    await send('s');
  } catch(error) {
    if(selectedPort && !port)try { await selectedPort.close(); }catch{}
    if(error.name==='NotFoundError')notice('Chưa chọn cổng Serial. Bấm Kết nối cảm biến khi sẵn sàng.');
    else notice('Không mở được cổng: '+error.message+'. Đóng Serial Monitor và kiểm tra cáp USB.',true);
  } finally { connecting=false;ui.connect.disabled=false; }
});
navigator.serial?.addEventListener('disconnect',()=>{log('Thiết bị USB đã ngắt.');});
function stopDemo() {
  if(!demoTimer)return;
  clearInterval(demoTimer);demoTimer=null;ui.demo.textContent='Xem demo';connection('Demo đã dừng');ui.source.textContent='Chọn cổng USB-UART để xem cảm biến thật';
}
ui.demo.addEventListener('click',async()=>{
  if(demoTimer) { stopDemo();return; }
  if(port||connecting)return;
  if(bridgeMode) {
    connecting=true;
    try { await bridgeRequest('/api/disconnect',{}); } catch(error) { notice(error.message,true);return; }
    finally { connecting=false; }
    if(port)return;
  }
  resetData();sourceKind='demo';demoStart=performance.now();demoSeq=0;demoFiltered=null;
  ui.demo.textContent='Dừng demo';connection('DEMO · dữ liệu mô phỏng','amber');ui.source.textContent='Không kết nối phần cứng';
  notice('DEMO: dữ liệu mô phỏng để xem giao diện. Kết nối cảm biến để đo và ghi CSV thật.');
  const tick=()=>{
    const t=(performance.now()-demoStart)/1000,r=22*Math.sin(t*.7),p=16*Math.sin(t*.43),rr=r*Math.PI/180,pr=p*Math.PI/180;
    const clean=[-Math.sin(pr),Math.sin(rr)*Math.cos(pr),Math.cos(rr)*Math.cos(pr),15.4*Math.cos(t*.7),6.88*Math.cos(t*.43),8*Math.sin(t*.5)];
    const noisy=clean.map((v,i)=>v+(i<3 ? 0.045 : 1.4)*Math.sin(t*(43+i*11)+i));
    if(!demoFiltered)demoFiltered=noisy.slice();else noisy.forEach((v,i)=>demoFiltered[i]+=(i<3 ? 0.245 : 0.358)*(v-demoFiltered[i]));
    const rollA=Math.atan2(noisy[1],noisy[2])*180/Math.PI,pitchA=Math.atan2(-noisy[0],Math.hypot(noisy[1],noisy[2]))*180/Math.PI;
    const row=[1,demoSeq++,Math.round(t*1e6)+1000000,Math.round(t*25600)%0x1000000,...noisy.map((v,i)=>Math.round(v*(i<3?8192:65.6))),...noisy,26.4+.3*Math.sin(t*.1),...demoFiltered,rollA,pitchA,r,p,1];
    accept(row.join(','));
  };tick();demoTimer=setInterval(tick,10);
});
ui.pause.addEventListener('click',()=>{paused=!paused;frozen=paused?samples.slice():[];ui.pause.textContent=paused?'▶ Tiếp tục đồ thị':'Ⅱ Tạm dừng đồ thị';});
ui.record.addEventListener('click',()=>{
  if(recording) { finishRecording();return; }
  if(!port || !latest || performance.now()-lastArrival>1500)return;
  recorded=[];recording=true;ui.record.textContent='■ Dừng & tải CSV';ui['record-dot'].className='dot red';ui['record-status'].textContent='Đang ghi';ui['record-count'].textContent='0 mẫu';notice('Đang ghi mẫu cảm biến thật. Bấm Dừng & tải CSV để lưu file.');
});
ui.export.addEventListener('click',()=>{
  const data=paused?frozen:samples;if(!data.length)return;
  const cutoff=data.at(-1)[2]-Number(ui.window.value)*1e6;
  download(data.filter(row=>row[2]>=cutoff),sourceKind==='demo'?'bmi160_DEMO':'bmi160_preview');
});
ui['reset-filter'].addEventListener('click',()=>send('k'));
ui['device-status'].addEventListener('click',()=>send('s'));
function canvasContext(id) {
  const canvas=$(id),size=canvas.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2);
  const w=Math.max(1,size.width),h=Math.max(1,size.height);
  if(canvas.width!==Math.round(w*ratio)||canvas.height!==Math.round(h*ratio)) { canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio); }
  const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);return {ctx,w,h};
}
function chart(id,data,series,minRange) {
  const {ctx,w,h}=canvasContext(id),L=46,R=16,T=12,B=28,pw=w-L-R,ph=h-T-B;
  if(pw<=0||ph<=0)return;
  const seconds=Number(ui.window.value),last=data.at(-1)?.[2]??0,rows=data.filter(row=>row[2]>=last-seconds*1e6);
  let lo=Infinity,hi=-Infinity;
  for(const row of rows)for(const s of series)if(finite(row[s.index])){lo=Math.min(lo,row[s.index]);hi=Math.max(hi,row[s.index]);}
  if(!finite(lo)||!finite(hi)){lo=-minRange/2;hi=minRange/2;}
  const center=(lo+hi)/2,range=Math.max(hi-lo,minRange)*1.2;lo=center-range/2;hi=center+range/2;
  ctx.font='9px Segoe UI';ctx.lineWidth=1;ctx.fillStyle='#96a79c';ctx.textAlign='right';
  for(let i=0;i<5;i++){const y=T+ph*i/4;ctx.beginPath();ctx.strokeStyle='#edf1ee';ctx.moveTo(L,y);ctx.lineTo(w-R,y);ctx.stroke();ctx.fillText((hi-range*i/4).toFixed(range<10?2:0),L-9,y+3);}
  ctx.textAlign='center';for(let i=0;i<=4;i++){const x=L+pw*i/4;ctx.fillText((-(seconds-seconds*i/4)).toFixed(0),x,h-8);}
  if(!rows.length){ctx.fillStyle='#a4b2a8';ctx.font='12px Segoe UI';ctx.fillText('Chờ dữ liệu từ cảm biến',L+pw/2,T+ph/2);return;}
  ctx.save();ctx.beginPath();ctx.rect(L,T,pw,ph);ctx.clip();
  for(const s of series){ctx.beginPath();ctx.strokeStyle=s.color;ctx.lineWidth=s.raw?1.1:1.8;ctx.globalAlpha=s.raw ? 0.42 : 1;ctx.setLineDash(s.raw?[3,4]:[]);let started=false,previous=null;
    for(const row of rows){const v=row[s.index];if(!finite(v)){started=false;continue;}const x=L+pw*(1-(last-row[2])/(seconds*1e6)),y=T+ph*(hi-v)/range;if(!started||previous&&row[2]-previous>150000)ctx.moveTo(x,y);else ctx.lineTo(x,y);started=true;previous=row[2];}ctx.stroke();}
  ctx.restore();ctx.setLineDash([]);ctx.globalAlpha=1;
}
function drawBoard(row) {
  const {ctx,w,h}=canvasContext('attitude');const roll=finite(row?.[25])?row[25]*Math.PI/180:0,pitch=finite(row?.[26])?row[26]*Math.PI/180:0;
  const rotate=(v)=>{let[x,y,z]=v;[y,z]=[y*Math.cos(roll)-z*Math.sin(roll),y*Math.sin(roll)+z*Math.cos(roll)];[x,z]=[x*Math.cos(pitch)+z*Math.sin(pitch),-x*Math.sin(pitch)+z*Math.cos(pitch)];[x,z]=[x*.82+z*.57,-x*.57+z*.82];[y,z]=[y*.86-z*.51,y*.51+z*.86];return[x,y,z];};
  const project=v=>{const[x,y,z]=rotate(v),scale=Math.min(w*.29,h*.38)*3.8/(3.8+z);return[w/2+x*scale,h/2+y*scale,z];};
  const vertices=[[-1,-.08,-.62],[1,-.08,-.62],[1,-.08,.62],[-1,-.08,.62],[-1,.08,-.62],[1,.08,-.62],[1,.08,.62],[-1,.08,.62]].map(project);
  ctx.fillStyle='#edf4ef';ctx.beginPath();ctx.ellipse(w/2,h*.77,w*.27,h*.055,0,0,Math.PI*2);ctx.fill();
  const faces=[{ids:[0,1,2,3],color:'#309b79'},{ids:[4,5,6,7],color:'#76b998'},{ids:[0,1,5,4],color:'#1c6652'},{ids:[1,2,6,5],color:'#237b62'},{ids:[2,3,7,6],color:'#286f57'},{ids:[3,0,4,7],color:'#4c9876'}];
  faces.sort((a,b)=>b.ids.reduce((s,i)=>s+vertices[i][2],0)-a.ids.reduce((s,i)=>s+vertices[i][2],0));
  for(const face of faces){ctx.beginPath();face.ids.forEach((id,i)=>{const[x,y]=vertices[id];i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.closePath();ctx.fillStyle=face.color;ctx.fill();ctx.strokeStyle='#ffffff50';ctx.lineWidth=.8;ctx.stroke();}
  const origin=project([0,0,0]);for(const[v,color,label]of[[[1.5,0,0],COLORS[0],'X'],[[0,1.1,0],COLORS[1],'Y'],[[0,0,1.15],COLORS[2],'Z']]){const end=project(v);ctx.beginPath();ctx.moveTo(origin[0],origin[1]);ctx.lineTo(end[0],end[1]);ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();ctx.fillStyle=color;ctx.font='bold 10px Segoe UI';ctx.fillText(label,end[0]+5,end[1]+4);}
  if(!finite(row?.[25])){ctx.fillStyle='#86988b';ctx.font='10px Segoe UI';ctx.textAlign='center';ctx.fillText('Chưa có góc Kalman',w/2,h-10);ctx.textAlign='left';}
}
let lastPaint=0;
function render(now) {
  requestAnimationFrame(render);if(now-lastPaint<33)return;lastPaint=now;
  const fresh=!!latest&&now-lastArrival<1500;
  if(port)connection(fresh?'Đang nhận trực tiếp':'Đã mở cổng · chưa có mẫu mới',fresh?'green':'amber');
  ui.sps.innerHTML=(fresh?fmt(stats.sps,1):'—')+' <small>Hz</small>';
  ui['rate-caption'].textContent=demoTimer?'Dữ liệu demo mô phỏng':fresh?(stats.sps?'Tính theo timestamp ESP32':'Đang tính tốc độ…'):'Chờ dữ liệu cảm biến';
  ui['sample-count'].textContent=stats.count.toLocaleString('vi-VN');ui['lost-count'].textContent=stats.missing.toLocaleString('vi-VN');
  ui.temp.innerHTML=fmt(latest?.[16],1)+' <small>°C</small>';
  const norm=latest?Math.hypot(...latest.slice(10,13)):null;
  ui.norm.innerHTML=fmt(norm,3)+' <small>g</small>';ui['gravity-caption'].textContent=latest?(norm>=.85&&norm<=1.15?'Gần 1 g · có thể hiệu chỉnh góc':'Có gia tốc chuyển động'):'Chưa có dữ liệu';
  ui['session-label'].textContent='SESSION '+(latest?.[0]??'—');
  ui['io-errors'].textContent=firmwareCounters?.io??'—';ui['serial-drops'].textContent=firmwareCounters?.drop??'—';ui.invalid.textContent=invalid;ui['max-gap'].textContent=stats.maxGapUs?fmt(stats.maxGapUs/1000,2)+' ms':'—';
  ui.record.disabled=!recording&&(!port||!fresh);ui.export.disabled=!samples.length;ui['reset-filter'].disabled=!port;ui['device-status'].disabled=!port;
  const data=paused?frozen:samples,row=data.at(-1),mode=ui.display.value;
  ui.roll.innerHTML=fmt(row?.[25],1)+'<small>°</small>';ui.pitch.innerHTML=fmt(row?.[26],1)+'<small>°</small>';
  ui['tilt-note'].textContent=!row||row.length<28?'Nạp firmware Kalman để xem góc.':!finite(row[25])?'Giữ yên, gần 1 g để khởi tạo góc.':row[27]?'Accel gần 1 g · đang hiệu chỉnh gyro.':'Ưu tiên gyro; accel chưa đủ tin cậy.';
  const series=(rawBase,filteredBase)=>COLORS.flatMap((color,i)=>[...(mode!=='kalman'?[{index:rawBase+i,color,raw:true}]:[]),...(mode!=='raw'?[{index:filteredBase+i,color,raw:false}]:[])]);
  chart('accel-chart',data,series(10,17),.3);chart('gyro-chart',data,series(13,20),10);
  chart('tilt-chart',data,[...(mode!=='kalman'?[{index:23,color:COLORS[0],raw:true},{index:24,color:COLORS[1],raw:true}]:[]),...(mode!=='raw'?[{index:25,color:COLORS[0]},{index:26,color:COLORS[1]}]:[])],10);
  drawBoard(row);
}
async function bridgeRequest(endpoint,payload) {
  const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-BMI-Token':bridgeToken},body:JSON.stringify(payload)});
  const result=await response.json();
  if(!response.ok)throw new Error(result.error || 'Máy chủ Serial không nhận yêu cầu.');
  return result;
}
function applyBridgeState(state) {
  if(state.token)bridgeToken=state.token;
  const selected=ui['serial-port'].value;
  const automatic=document.createElement('option');automatic.value='';automatic.textContent='Tự nhận cổng ESP32';
  const options=(state.ports||[]).map(info=>{const option=document.createElement('option');option.value=info.device;option.textContent=info.device+' · '+info.description;return option;});
  ui['serial-port'].replaceChildren(automatic,...options);
  ui['serial-port'].value=options.some(option=>option.value===selected)?selected:'';
  ui['serial-port'].disabled=state.connected;
  if(state.connected) {
    stopDemo();
    if(bridgeDevice!==state.device) {
      finishRecording('Cổng cảm biến thay đổi; CSV đã ghi được tải.');
      resetData();sourceKind='serial';bridgeDevice=state.device;
      log('Python đã mở '+state.device+' ở 460800 baud.');
      notice('Đã tự kết nối '+state.device+'. SPI chạy trên ESP32; dữ liệu chuyển qua USB-UART.');
    }
    port={bridge:true,device:state.device};ui.connect.textContent='× Ngắt kết nối';ui.demo.disabled=true;
    ui.source.textContent=state.device+' · USB-UART → Python → web';
    connection('Đã mở cổng · chờ dữ liệu','amber');
  } else {
    if(port?.bridge) {
      finishRecording('Kết nối đã đóng; dữ liệu đã ghi được tải xuống.');
      log('Đã đóng '+bridgeDevice+'.');
    }
    port=null;bridgeDevice=null;ui.connect.textContent='↔ Kết nối cảm biến';ui.demo.disabled=false;
    if(!demoTimer) {
      connection(state.automatic?'Đang tìm cảm biến':'Đã ngắt kết nối');
      ui.source.textContent='Python tự nhận USB-UART · không cần quyền Serial của trình duyệt';
      if(state.error && state.error!==bridgeError)notice(state.error,true);
    }
  }
  bridgeError=state.error||'';
}
function openBridgeStream() {
  bridgeStream=new EventSource('/api/events');
  bridgeStream.addEventListener('state',event=>applyBridgeState(JSON.parse(event.data)));
  bridgeStream.addEventListener('lines',event=>{for(const line of JSON.parse(event.data))accept(line);});
  bridgeStream.addEventListener('overflow',event=>{
    finishRecording('Luồng nhận bị gián đoạn; CSV đã ghi được tải.');
    invalid++;notice(JSON.parse(event.data).error,true);log('Luồng HTTP nhận chậm; đã tách CSV.');
  });
  bridgeStream.onerror=()=>{
    finishRecording('Mất kết nối máy chủ Python; CSV đã ghi được tải.');
    port=null;bridgeDevice=null;ui.connect.disabled=true;ui.demo.disabled=true;
    connection('Mất kết nối Python','amber');notice('Máy chủ Python bị ngắt. Chạy lại live_bmi_visualizer.py; web sẽ tự nối lại.',true);
  };
  bridgeStream.onopen=()=>{ui.connect.disabled=false;};
}
async function initializeConnection() {
  ui.connect.disabled=true;
  try {
    const signal=typeof AbortSignal!=='undefined' && AbortSignal.timeout?AbortSignal.timeout(1500):undefined;
    const response=await fetch('/api/status',{signal});
    if(!response.ok)throw new Error('No local bridge');
    const state=await response.json();
    if(typeof state.token!=='string' || !Array.isArray(state.ports))throw new Error('Invalid bridge');
    bridgeMode=true;bridgeToken=state.token;ui['port-controls'].hidden=false;
    applyBridgeState(state);openBridgeStream();
  } catch {
    if(!navigator.serial || !window.isSecureContext)notice('Chạy python live_bmi_visualizer.py rồi mở http://localhost:8765 để tự nhận cổng COM.',true);
    else notice('Chưa có máy chủ Python. Có thể chọn Serial trực tiếp, hoặc chạy live_bmi_visualizer.py để tự nhận COM.');
  } finally { ui.connect.disabled=false; }
}
initializeConnection();
requestAnimationFrame(render);
