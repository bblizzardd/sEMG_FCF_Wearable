// UI behavior tests in a DOM/Serial mock; does not claim real-browser or hardware QA.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {ReadableStream,WritableStream} from 'node:stream/web';
import {TextDecoder,TextEncoder} from 'node:util';
import {Blob} from 'node:buffer';
import {FIELDS,parseLine,LineDecoder,SampleStats} from '../../web/protocol.mjs';
const html=await readFile(new URL('../../web/index.html',import.meta.url),'utf8');
const source=await readFile(new URL('../../web/app.mjs',import.meta.url),'utf8');
let now=100,frame=null,strokes=0;
const downloads=[],elements=new Map();
const context2d=new Proxy({stroke(){strokes++;}}, {get:(target,key)=>target[key]??(()=>{})});
class Element {
  constructor(id){this.id=id;this.handlers={};this.disabled=false;this.classList={toggle(){}};this.textContent='';this.innerHTML='';this.value='';}
  addEventListener(name,handler){this.handlers[name]=handler;}
  getBoundingClientRect(){return {width:500,height:220};}
  getContext(){return context2d;}
  async fire(name='click'){return this.handlers[name]?.({target:this});}
  click(){downloads.push(this);}
}
for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element(match[1]));
elements.get('display').value='both';elements.get('window').value='6';
const fakePort={
  readable:null,writable:new WritableStream({write(){}}),closed:false,controller:null,
  async open(){this.readable=new ReadableStream({start:controller=>this.controller=controller});},
  async setSignals(){},getInfo(){return {usbVendorId:0x10c4};},
  async close(){this.closed=true;this.readable=null;}
};
const blobs=new Map();let timerId=0;
const browser=vm.createContext({
  ...{FIELDS,parseLine,LineDecoder,SampleStats},
  document:{getElementById:id=>elements.get(id),createElement:()=>new Element('download')},
  navigator:{serial:{requestPort:async()=>fakePort,addEventListener(){}}},window:{isSecureContext:true},
  performance:{now:()=>now},devicePixelRatio:1,
  URL:{createObjectURL:blob=>{const id='blob:'+blobs.size;blobs.set(id,blob);return id;},revokeObjectURL(){}},
  requestAnimationFrame:callback=>frame=callback,
  setInterval:()=>++timerId,clearInterval(){},setTimeout:callback=>{callback();},
  TextDecoder,TextEncoder,Blob,console,
});
vm.runInContext(source.replace(/^import[^;]+;\n/,''),browser,{filename:'app.mjs'});
const paint=()=>{now+=40;frame(now);};
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const enqueue=row=>fakePort.controller.enqueue(new TextEncoder().encode(row.join(',')+'\n'));
paint();assert.equal(elements.get('record').disabled,true);
await elements.get('connect').fire();assert.equal(elements.get('connect').textContent,'× Ngắt kết nối');
const row=[1,0,1000000,25600,0,0,8192,0,0,0,0,0,1,0,0,0,23,0,0,1,0,0,0,0,0,10,5,1,0];
enqueue(row);await flush();paint();
assert.equal(elements.get('record').disabled,false);
assert.ok(elements.get('roll').innerHTML.startsWith('10.0'));
assert.ok(strokes>10);
assert.equal(elements.get('button-state').textContent,'Đã thả · 0');
await elements.get('pause').fire();
await elements.get('record').fire();
const next=row.slice();next[1]=1;next[2]+=10000;next[25]=20;next[28]=1;
enqueue(next);await flush();paint();
assert.ok(elements.get('roll').innerHTML.startsWith('10.0')); // Plot frozen, recording continues.
assert.equal(elements.get('record-count').textContent,'1 mẫu');
assert.equal(elements.get('button-state').textContent,'Đang nhấn · 1'); // Live state remains live while chart is paused.
assert.equal(elements.get('button-count').textContent,'1');
const restarted=next.slice();restarted[0]=2;restarted[1]=2;restarted[2]+=10000;
enqueue(restarted);await flush();paint();
assert.equal(downloads.length,1); // Session boundary closes CSV, doesn't mix sessions.
const csv=await blobs.get(downloads[0].href).text();
assert.ok(csv.startsWith(FIELDS.join(',')));assert.equal(csv.trim().split('\n').length,2);
assert.equal(csv.trim().split('\n')[1].split(',')[28],'1');
await elements.get('connect').fire();paint();assert.equal(fakePort.closed,true);
await elements.get('demo').fire();paint();assert.equal(elements.get('record').disabled,true);
await elements.get('demo').fire(); // Stop demo then export: retain DEMO provenance.
await elements.get('export').fire();assert.ok(downloads.at(-1).download.startsWith('bmi160_DEMO'));
console.log('Dashboard mocked Serial, pause, recording, restart, disconnect and demo tests passed');
