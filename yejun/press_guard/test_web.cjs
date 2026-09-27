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
code=code.replace('  start();','  globalThis.subject={lineChart,state,renderDetail,numberOrNaN,filteredCases,levelNow,renderQueue,renderLevelKpis,outcomeOf};');
vm.runInNewContext(code,context);
const {lineChart,state,renderDetail,numberOrNaN,filteredCases,levelNow,renderQueue,renderLevelKpis,outcomeOf}=context.subject;
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
// 2단계 경보와 모의 운용: 커서가 격상 행에 이르기 전에는 1단계로 보이고, 첫 알림 전 건은 대기열에 없다.
const cases=[{record_id:1,first_row:10,level:2,escalation_row:12,priority_rank:1,evidence:'magnitude',first_timestamp:'t1'},
             {record_id:2,first_row:30,level:1,escalation_row:null,priority_rank:2,evidence:'waveform',first_timestamp:'t2'}];
state.result={cases,points:[],split:'B',alpha:0.01,dataset:'mixed',prior:0.01};
state.sim={row:11};
assert.equal(filteredCases().length,1); assert.equal(levelNow(cases[0]),1);
state.sim.row=12; assert.equal(levelNow(cases[0]),2);
state.sim.row=40; assert.equal(filteredCases().length,2);
state.levelFilter='2'; assert.equal(filteredCases().map(c=>c.record_id).join(','),'1');
state.levelFilter='all'; state.sim=null;
renderLevelKpis(); assert.equal(document.getElementById('k-case').textContent,'1'); assert.equal(document.getElementById('k-level1').textContent,'1');
renderQueue(); assert.match(document.getElementById('queue').innerHTML,/badge l2">점검 요청/);
// 저장소가 없어도(사생활 보호 모드) 결과 양식은 빈 값으로 동작한다.
assert.equal(outcomeOf(cases[0]).status,'열림');
console.log('web regressions: 9 passed (null gap / empty replay hover / 50k rows / empty selection / sim visibility / escalation timing / level filter / level KPIs / outcome without storage)');
