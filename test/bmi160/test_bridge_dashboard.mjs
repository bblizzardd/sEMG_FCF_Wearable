// Dashboard bridge behavior with no Web Serial API, using DOM/HTTP/SSE mocks.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {TextDecoder,TextEncoder} from 'node:util';
import {Blob} from 'node:buffer';
import {FIELDS,parseLine,LineDecoder,SampleStats} from '../../web/protocol.mjs';
const html=await readFile(new URL('../../web/index.html',import.meta.url),'utf8');
const source=await readFile(new URL('../../web/app.mjs',import.meta.url),'utf8');
let now=100,frame=null,events=null;
const downloads=[],requests=[],elements=new Map(),blobs=new Map();
const context2d=new Proxy({}, {get:()=>()=>{}});
class Element {
  constructor(id){this.id=id;this.handlers={};this.disabled=false;this.hidden=true;this.classList={toggle(){}};this.textContent='';this.innerHTML='';this.value='';}
  addEventListener(name,handler){this.handlers[name]=handler;}
  getBoundingClientRect(){return {width:500,height:220};}
  getContext(){return context2d;}
  replaceChildren(...children){this.children=children;}
  async fire(){return this.handlers.click?.({target:this});}
  click(){downloads.push(this);}
}
for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element(match[1]));
elements.get('display').value='both';elements.get('window').value='6';
const initial={connected:true,device:'COM10',error:'',automatic:true,token:'first-token',ports:[{device:'COM10',description:'CH343'},{device:'COM11',description:'CP210x'}]};
class Events {
  constructor(){events=this;this.handlers={};}
  addEventListener(name,handler){this.handlers[name]=handler;}
  emit(name,data){this.handlers[name]?.({data:JSON.stringify(data)});}
}
const browser=vm.createContext({
  FIELDS,parseLine,LineDecoder,SampleStats,
  document:{getElementById:id=>elements.get(id),createElement:()=>new Element('new')},
  navigator:{},window:{isSecureContext:true}, // Chrome need not expose navigator.serial.
  fetch:async(endpoint,options)=>{
    if(endpoint==='/api/status')return {ok:true,json:async()=>initial};
    requests.push({endpoint,payload:JSON.parse(options.body),token:options.headers['X-BMI-Token']});
    return {ok:true,json:async()=>({ok:true})};
  },EventSource:Events,
  performance:{now:()=>now},devicePixelRatio:1,
  URL:{createObjectURL:blob=>{const id='blob:'+blobs.size;blobs.set(id,blob);return id;},revokeObjectURL(){}},
  requestAnimationFrame:callback=>frame=callback,
  setInterval:()=>1,clearInterval(){},setTimeout:callback=>callback(),
  TextDecoder,TextEncoder,Blob,console,
});
vm.runInContext(source.replace(/^import[^;]+;\n/,''),browser,{filename:'app.mjs'});
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const paint=()=>{now+=40;frame(now);};
await flush();paint();
assert.equal(elements.get('port-controls').hidden,false);
assert.equal(elements.get('connect').textContent,'× Ngắt kết nối');
assert.equal(elements.get('serial-port').children.length,3);
assert.ok(elements.get('source').textContent.includes('COM10'));
const row=[1,0,1000000,25600,0,0,8192,0,0,0,0,0,1,0,0,0,23,0,0,1,0,0,0,0,0,10,5,1];
events.emit('lines',[row.join(',')]);paint();
assert.equal(elements.get('record').disabled,false);
assert.ok(elements.get('roll').innerHTML.startsWith('10.0'));
await elements.get('record').fire();
const next=row.slice();next[1]=1;next[2]+=10000;
events.emit('lines',[next.join(',')]);
await elements.get('reset-filter').fire();
assert.equal(requests.at(-1).endpoint,'/api/command');
assert.equal(requests.at(-1).payload.command,'k');
assert.equal(requests.at(-1).token,'first-token');
events.emit('state',{...initial,connected:false,error:'USB removed'});paint();
assert.equal(downloads.length,1);
assert.equal(elements.get('record').disabled,true);
assert.equal(elements.get('connect').textContent,'↔ Kết nối cảm biến');
const csv=await blobs.get(downloads[0].href).text();
assert.equal(csv.trim().split('\n').length,2);
elements.get('serial-port').value='COM11';
await elements.get('connect').fire();
assert.equal(requests.at(-1).endpoint,'/api/connect');
assert.equal(requests.at(-1).payload.port,'COM11');
events.emit('state',{...initial,device:'COM11',token:'restarted-server-token'});paint();
await elements.get('device-status').fire();
assert.equal(requests.at(-1).token,'restarted-server-token');
await elements.get('connect').fire();
assert.equal(requests.at(-1).endpoint,'/api/disconnect');
events.emit('state',{...initial,connected:false,automatic:false,error:'Disconnected'});paint();
await elements.get('demo').fire();paint();
assert.equal(elements.get('record').disabled,true);
assert.equal(requests.at(-1).endpoint,'/api/disconnect'); // Demo suspends auto-connect.
await elements.get('demo').fire();
elements.get('serial-port').value='';await elements.get('connect').fire();
assert.equal(requests.at(-1).payload.port,'');
events.emit('state',initial);events.emit('lines',[row.join(',')]);paint();
await elements.get('record').fire();events.emit('lines',[next.join(',')]);
events.emit('overflow',{error:'slow client'});paint();
assert.equal(downloads.length,2); // Slow stream cannot silently corrupt a recording.
events.onerror();paint();
assert.equal(elements.get('connect').disabled,true);
events.onopen();events.emit('state',initial);paint();
assert.equal(elements.get('connect').disabled,false);
assert.ok(elements.get('source').textContent.includes('COM10'));
console.log('Dashboard native COM auto-connect, no Web Serial, commands, CSV, reconnect and demo tests passed');
