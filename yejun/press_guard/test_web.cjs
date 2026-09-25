// 실제 app.js의 차트 함수를 VM에서 실행한다. 제품 파일에는 테스트용 전역을 추가하지 않는다.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = new Map();
function element() { return { innerHTML:'', textContent:'', value:1, style:{}, disabled:false, clientWidth:600,
  listeners:{}, addEventListener(k,f){this.listeners[k]=f;}, classList:{toggle(){}},
  querySelector(){return this.svg ||= element();}, querySelectorAll(){return [];},
  getBoundingClientRect(){return {left:0,width:600};} }; }
const document = {getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];}, createElement:element, body:{appendChild(){}}};
const context={document,window:{addEventListener(){},innerWidth:1200},setTimeout,clearTimeout,setInterval,clearInterval};
let code=fs.readFileSync(__dirname+'/web/app.js','utf8');
code=code.replace('  start();','  globalThis.subject={lineChart,state,renderDetail,numberOrNaN};');
vm.runInNewContext(code,context);
const {lineChart,state,renderDetail,numberOrNaN}=context.subject;
assert(Number.isNaN(numberOrNaN(null)));
const box=element(), series=[{key:'a',name:'A',color:'#333',dash:''}];
const rows=[{a:null},{a:null},{a:3}];
lineChart(box,rows,series,{domainRows:rows});
assert.match(box.innerHTML, /<path d="M588\.0,/); // 첫 두 null 관측을 0으로 그리지 않는다.
lineChart(box,[],series,{domainRows:rows});
assert.doesNotThrow(()=>box.svg.listeners.mousemove({clientX:50,clientY:20}));
const long=Array.from({length:50000},(_,i)=>({a:i,b:i+1,c:i+2}));
assert.doesNotThrow(()=>lineChart(box,long,['a','b','c'].map(key=>({...series[0],key})),{domainRows:long}));
state.selected=3; renderDetail(null);
assert.equal(state.selected,null); assert.equal(document.getElementById('replay').disabled,true);
console.log('web regressions: 4 passed (null gap / empty replay hover / 50k rows / empty selection)');
